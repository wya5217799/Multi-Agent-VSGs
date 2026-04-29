"""PHI sweep probe — find PHI_H/PHI_D that brings r_f% into 3-8% target band.

Locked config has PHI_H=PHI_D=1e-4 (post credibility-close, commit a9ad2ea).
P0 baseline showed last-100 r_f% = 0.2% — far below the 3-8% design target.
This probe sweeps PHI ∈ {1e-3, 3e-3, 5e-3, 1e-2} via env-instance monkey-
patch (does NOT touch locked config_simulink.py PHI constants), each with a
fresh 4-agent MultiAgentSACManager, 100 episodes from-scratch training.

CRITICAL HISTORY (commit 3711ea6 root-cause probe):
The earlier sweep run hardcoded KUNDUR_DISTURBANCE_TYPE=loadstep_paper_random_bus
which is documented as a weak-signal protocol (commit 97f6d3a) — Series RLC
R block Resistance is frozen at .slx compile time, runtime workspace var
writes are ineffective. The earlier sweep saw only IC kickoff residual
(~0.015 Hz), not real Pm-step disturbance, so the r_f% ~ 0 finding was
on a noise floor, NOT an architecture limit. This probe now requires
KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus explicitly — no
setdefault fallback — and gates the sweep behind a first-cell sanity
check (max|df| mean ≥ 0.05 Hz over first 10 episodes).

Output: results/harness/kundur/cvs_v3_phi_resweep_v2/{cell_<phi>}_metrics.json
        + per-episode total / r_f / r_h / r_d / max|df| / settled
        + cell summary stats (last-50 mean / r_f% decomp)
        + sanity_gate.json with cell-1 disturbance-reach evidence

Single MATLAB engine cold start (env constructed once, reused across cells).
Each cell uses fresh seeds / fresh manager — no cross-cell state contamination.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Lock pre-flight env-vars BEFORE importing config_simulink
# ---------------------------------------------------------------------------
for k in ("KUNDUR_PHI_H", "KUNDUR_PHI_D", "KUNDUR_ALLOW_LEGACY_PROFILE"):
    os.environ.pop(k, None)
os.environ["KUNDUR_MODEL_PROFILE"] = str(
    REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
)
# Strict protocol guard: this sweep MUST run under pm_step_proxy_random_bus.
# Earlier sweep (pre-commit 3711ea6) silently used loadstep_paper_random_bus
# via setdefault — that protocol is documented as weak-signal (commit 97f6d3a)
# and produced an invalid r_f% measurement. No silent fallback this time.
_REQUIRED_DISTURBANCE_TYPE = "pm_step_proxy_random_bus"
_user_dtype = os.environ.get("KUNDUR_DISTURBANCE_TYPE")
if _user_dtype is None:
    os.environ["KUNDUR_DISTURBANCE_TYPE"] = _REQUIRED_DISTURBANCE_TYPE
elif _user_dtype != _REQUIRED_DISTURBANCE_TYPE:
    raise RuntimeError(
        f"_phi_resweep.py requires KUNDUR_DISTURBANCE_TYPE="
        f"{_REQUIRED_DISTURBANCE_TYPE!r}; got {_user_dtype!r}. Refusing "
        f"to run a PHI sweep under a different (potentially weak-signal) "
        f"protocol — see commit 3711ea6 for the original protocol-mismatch "
        f"finding. Unset the env-var or set it to "
        f"{_REQUIRED_DISTURBANCE_TYPE!r} to proceed."
    )
assert os.environ["KUNDUR_DISTURBANCE_TYPE"] == _REQUIRED_DISTURBANCE_TYPE

import numpy as np
from env.simulink.kundur_simulink_env import KundurSimulinkEnv
from agents.multi_agent_sac_manager import MultiAgentSACManager
from scenarios.kundur.config_simulink import (
    OBS_DIM, ACT_DIM, HIDDEN_SIZES,
    LR, GAMMA, TAU_SOFT, BATCH_SIZE,
    BUFFER_SIZE, WARMUP_STEPS, N_AGENTS,
    PHI_F, PHI_H as LOCKED_PHI_H, PHI_D as LOCKED_PHI_D,
    STEPS_PER_EPISODE,
)

# ---------------------------------------------------------------------------
# Sweep configuration
# ---------------------------------------------------------------------------
PHI_VALUES = [1e-3, 3e-3, 5e-3, 1e-2]
EPISODES_PER_CELL = 100
SEED_BASE = 4242
UPDATE_REPEAT = 10  # match train_simulink default
OUT_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phi_resweep_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Sanity gate (post-commit 3711ea6): cell-1 first-10-ep mean max|df| must
# exceed this threshold; otherwise the disturbance is not reaching the
# system and the entire sweep is invalid. Threshold 0.05 Hz is well above
# the historical IC-kickoff noise floor (~0.015 Hz) but well below the
# expected Pm-step proxy peak (~0.2-0.4 Hz).
SANITY_MAX_DF_MIN_HZ = 0.05
SANITY_RF_ABS_MIN = 1e-5


def run_cell(env, phi: float, cell_idx: int, total_cells: int) -> dict:
    """Train a fresh 4-agent manager for EPISODES_PER_CELL episodes at given PHI."""
    print()
    print("=" * 72)
    print(f"Cell {cell_idx}/{total_cells} — PHI_H = PHI_D = {phi:.4g} "
          f"(locked baseline = {LOCKED_PHI_H:.4g}, ratio = {phi / LOCKED_PHI_H:.0f}×)")
    print("=" * 72)
    t0 = time.time()

    # Monkey-patch env instance to override locked _PHI_H / _PHI_D for this cell.
    # The class attribute lookup `self._PHI_H` finds the instance attr first.
    env._PHI_H = float(phi)
    env._PHI_D = float(phi)
    print(f"  env._PHI_H={env._PHI_H}  env._PHI_D={env._PHI_D}  "
          f"env._PHI_F={env._PHI_F}")

    # Fresh manager — independent learners (G6 default), default per-agent split.
    manager = MultiAgentSACManager(
        n_agents=N_AGENTS,
        obs_dim=OBS_DIM,
        act_dim=ACT_DIM,
        hidden_sizes=HIDDEN_SIZES,
        lr=LR,
        gamma=GAMMA,
        tau=TAU_SOFT,
        buffer_size=BUFFER_SIZE,
        batch_size=BATCH_SIZE,
        warmup_steps=WARMUP_STEPS,
        reward_scale=1e-3,
        alpha_max=5.0,
        alpha_min=0.05,
    )

    cell_records = []
    global_step = 0
    for ep in range(EPISODES_PER_CELL):
        obs, _ = env.reset(seed=SEED_BASE + cell_idx * 10000 + ep)
        env.apply_disturbance()  # default random magnitude in [DIST_MIN, DIST_MAX]
        ep_total = 0.0
        ep_rf, ep_rh, ep_rd = 0.0, 0.0, 0.0
        max_df = 0.0
        any_settled = False
        n_steps = 0
        for step in range(STEPS_PER_EPISODE):
            action = manager.select_actions_multi(obs, deterministic=False)
            next_obs, rewards, terminated, truncated, info = env.step(action)
            done_flags = np.array(
                [float(terminated)] * N_AGENTS, dtype=np.float32
            )
            manager.store_multi_transitions(
                obs, action, rewards, next_obs, done_flags
            )
            global_step += 1
            if (
                global_step > manager.per_agent_warmup_steps
                and global_step % 1 == 0
            ):
                for _ in range(UPDATE_REPEAT):
                    manager.update()

            ep_total += float(np.sum(rewards))
            rc = info.get("reward_components", {}) or {}
            ep_rf += float(rc.get("r_f", 0.0))
            ep_rh += float(rc.get("r_h", 0.0))
            ep_rd += float(rc.get("r_d", 0.0))
            mfd = float(info.get("max_freq_dev_hz", 0.0))
            if mfd > max_df:
                max_df = mfd
            n_steps += 1
            obs = next_obs
            if terminated or truncated:
                break

        cell_records.append({
            "episode": ep,
            "total_reward": ep_total,
            "r_f": ep_rf,
            "r_h": ep_rh,
            "r_d": ep_rd,
            "max_freq_dev_hz": max_df,
            "n_steps": n_steps,
        })
        if (ep + 1) % 10 == 0:
            recent = cell_records[-10:]
            mean_total = statistics.mean(r["total_reward"] for r in recent)
            mean_rf = statistics.mean(r["r_f"] for r in recent)
            mean_rh = statistics.mean(r["r_h"] for r in recent)
            mean_rd = statistics.mean(r["r_d"] for r in recent)
            asum = abs(mean_rf) + abs(mean_rh) + abs(mean_rd)
            rf_pct = 100 * abs(mean_rf) / asum if asum > 0 else 0.0
            print(
                f"  ep {ep+1:3d}: "
                f"total={mean_total:+.4f}  "
                f"r_f={mean_rf:+.5f}  r_h={mean_rh:+.5f}  r_d={mean_rd:+.5f}  "
                f"r_f%={rf_pct:.2f}%  max|df|={max_df:.4f}Hz"
            )

    elapsed = time.time() - t0
    last50 = cell_records[-50:]
    mean_total = statistics.mean(r["total_reward"] for r in last50)
    mean_rf = statistics.mean(r["r_f"] for r in last50)
    mean_rh = statistics.mean(r["r_h"] for r in last50)
    mean_rd = statistics.mean(r["r_d"] for r in last50)
    asum = abs(mean_rf) + abs(mean_rh) + abs(mean_rd)
    rf_pct = 100 * abs(mean_rf) / asum if asum > 0 else 0.0
    rh_pct = 100 * abs(mean_rh) / asum if asum > 0 else 0.0
    rd_pct = 100 * abs(mean_rd) / asum if asum > 0 else 0.0
    mean_mfd = statistics.mean(r["max_freq_dev_hz"] for r in last50)
    summary = {
        "cell_idx": cell_idx,
        "phi": phi,
        "phi_ratio_vs_locked": phi / LOCKED_PHI_H,
        "episodes": EPISODES_PER_CELL,
        "elapsed_sec": elapsed,
        "last50_mean_total": mean_total,
        "last50_mean_rf": mean_rf,
        "last50_mean_rh": mean_rh,
        "last50_mean_rd": mean_rd,
        "last50_rf_pct": rf_pct,
        "last50_rh_pct": rh_pct,
        "last50_rd_pct": rd_pct,
        "last50_mean_max_freq_dev_hz": mean_mfd,
    }
    print(
        f"  CELL {cell_idx} SUMMARY: total={mean_total:+.4f}  "
        f"r_f%={rf_pct:.2f}%  r_h%={rh_pct:.2f}%  r_d%={rd_pct:.2f}%  "
        f"max|df|={mean_mfd:.4f}Hz  wall={elapsed:.0f}s"
    )

    out_path = OUT_DIR / f"cell_phi{phi:.0e}_metrics.json"
    out_path.write_text(
        json.dumps(
            {
                "phi": phi,
                "summary": summary,
                "per_episode": cell_records,
                "config": {
                    "episodes": EPISODES_PER_CELL,
                    "seed_base": SEED_BASE,
                    "n_agents": N_AGENTS,
                    "buffer_size": BUFFER_SIZE,
                    "batch_size": BATCH_SIZE,
                    "warmup_steps": WARMUP_STEPS,
                    "lr": LR,
                    "gamma": GAMMA,
                    "tau": TAU_SOFT,
                    "update_repeat": UPDATE_REPEAT,
                    "phi_f": PHI_F,
                    "locked_phi_h": LOCKED_PHI_H,
                    "locked_phi_d": LOCKED_PHI_D,
                    "disturbance_type": os.environ["KUNDUR_DISTURBANCE_TYPE"],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  Saved {out_path}")
    return summary


def main() -> int:
    print("=" * 72)
    print(f"PHI Resweep Probe v2 — {len(PHI_VALUES)}-cell sweep of "
          f"PHI_H = PHI_D ∈ {PHI_VALUES}")
    print(f"Locked baseline (post a9ad2ea): PHI_H = PHI_D = {LOCKED_PHI_H}")
    print(f"Disturbance protocol (REQUIRED): {os.environ['KUNDUR_DISTURBANCE_TYPE']}")
    print(f"Episodes per cell              : {EPISODES_PER_CELL}")
    print(f"Seed base                      : {SEED_BASE}")
    print(f"Sanity gate (cell-1 first-10ep): mean max|df| >= "
          f"{SANITY_MAX_DF_MIN_HZ} Hz AND mean |r_f| >= {SANITY_RF_ABS_MIN}")
    print("=" * 72)
    print()
    print("Constructing KundurSimulinkEnv (cold start) ...")
    t0 = time.time()
    env = KundurSimulinkEnv()
    print(f"env constructed in {time.time() - t0:.1f}s; "
          f"_PHI_H={env._PHI_H} _PHI_D={env._PHI_D} _PHI_F={env._PHI_F}")
    print(f"env._disturbance_type = {env._disturbance_type!r}")
    assert env._disturbance_type == "pm_step_proxy_random_bus", (
        f"env._disturbance_type must be 'pm_step_proxy_random_bus', "
        f"got {env._disturbance_type!r}"
    )

    summaries = []
    sanity_gate_record: dict | None = None
    for ci, phi in enumerate(PHI_VALUES, start=1):
        s = run_cell(env, phi, ci, len(PHI_VALUES))
        summaries.append(s)

        # Cell-1 sanity gate: verify disturbance is actually reaching the
        # system. If max|df| or |r_f| are too low, abort the sweep —
        # indicates wrong disturbance protocol or a deeper bug.
        if ci == 1:
            from pathlib import Path as _Path
            cell_path = OUT_DIR / f"cell_phi{phi:.0e}_metrics.json"
            cell_data = json.loads(_Path(cell_path).read_text(encoding="utf-8"))
            first10 = cell_data["per_episode"][:10]
            mean_mfd = statistics.mean(r["max_freq_dev_hz"] for r in first10)
            mean_abs_rf = statistics.mean(abs(r["r_f"]) for r in first10)
            sanity_pass = (
                mean_mfd >= SANITY_MAX_DF_MIN_HZ
                and mean_abs_rf >= SANITY_RF_ABS_MIN
            )
            sanity_gate_record = {
                "cell_phi": phi,
                "first10_mean_max_freq_dev_hz": mean_mfd,
                "first10_mean_abs_r_f": mean_abs_rf,
                "threshold_max_df_hz": SANITY_MAX_DF_MIN_HZ,
                "threshold_abs_r_f": SANITY_RF_ABS_MIN,
                "passed": sanity_pass,
                "disturbance_type": os.environ["KUNDUR_DISTURBANCE_TYPE"],
            }
            (OUT_DIR / "sanity_gate.json").write_text(
                json.dumps(sanity_gate_record, indent=2),
                encoding="utf-8",
            )
            print()
            print("=" * 72)
            print("SANITY GATE (cell 1, first 10 episodes)")
            print(f"  mean max|df|        = {mean_mfd:.4f} Hz  "
                  f"(threshold {SANITY_MAX_DF_MIN_HZ})")
            print(f"  mean |r_f| per ep   = {mean_abs_rf:.6f}  "
                  f"(threshold {SANITY_RF_ABS_MIN})")
            print(f"  passed              = {sanity_pass}")
            print("=" * 72)
            if not sanity_pass:
                print("ABORT: sanity gate failed — disturbance not reaching "
                      "system. Skipping remaining cells.")
                break

    # Cross-cell comparison
    print()
    print("=" * 72)
    print("Cross-cell summary (last-50 mean per cell)")
    print("=" * 72)
    print(f"{'PHI':>8s} {'r_f%':>8s} {'r_h%':>8s} {'r_d%':>8s} "
          f"{'total':>10s} {'mfd_Hz':>8s} {'wall_s':>7s}")
    print("-" * 72)
    print(f"{LOCKED_PHI_H:>8.0e} {'0.20':>8s} {'83.90':>8s} {'15.90':>8s} "
          f"{'-0.0353':>10s} {'0.0165':>8s} {'(P0)':>7s}  ← locked baseline")
    for s in summaries:
        print(
            f"{s['phi']:>8.0e} {s['last50_rf_pct']:>8.2f} "
            f"{s['last50_rh_pct']:>8.2f} {s['last50_rd_pct']:>8.2f} "
            f"{s['last50_mean_total']:>+10.4f} "
            f"{s['last50_mean_max_freq_dev_hz']:>8.4f} "
            f"{s['elapsed_sec']:>7.0f}"
        )

    # Verdict
    print()
    target_low, target_high = 3.0, 8.0
    in_band = [s for s in summaries
               if target_low <= s["last50_rf_pct"] <= target_high]
    if in_band:
        rec = min(in_band, key=lambda s: abs(s["last50_rf_pct"] - 5.0))
        print(f"VERDICT: {len(in_band)} cell(s) in r_f% target band [3, 8]; "
              f"recommended PHI = {rec['phi']:.0e} "
              f"(r_f%={rec['last50_rf_pct']:.2f})")
    else:
        # Find closest-to-band candidate
        closest = min(summaries,
                      key=lambda s: min(
                          abs(s["last50_rf_pct"] - target_low),
                          abs(s["last50_rf_pct"] - target_high)))
        print(f"VERDICT: 0 cells in target band [3, 8]; "
              f"closest = PHI={closest['phi']:.0e} (r_f%={closest['last50_rf_pct']:.2f}). "
              f"Sweep range may need extension or 100 ep insufficient.")

    out_summary = OUT_DIR / "phi_resweep_summary.json"
    out_summary.write_text(
        json.dumps(
            {
                "locked_phi_h": LOCKED_PHI_H,
                "locked_phi_d": LOCKED_PHI_D,
                "phi_values_tested": PHI_VALUES,
                "p0_reference": {
                    "phi": LOCKED_PHI_H,
                    "last100_rf_pct": 0.20,
                    "last100_rh_pct": 83.90,
                    "last100_rd_pct": 15.90,
                    "last100_total": -0.0353,
                    "source": "kundur_simulink_20260429_013017 (P0 baseline 2000-ep)",
                },
                "cells": summaries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {out_summary}")

    try:
        env.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
