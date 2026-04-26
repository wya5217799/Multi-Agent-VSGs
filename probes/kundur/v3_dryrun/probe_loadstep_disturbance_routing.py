"""P4.1 — disturbance-routing smoke for Phase 4 Gap 1 Path (C) Pm-step proxy.

Plan: quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md
Audit: results/harness/kundur/cvs_v3_phase4/phase4_p40_audit_verdict.md

NOT a 50-ep gate run; NOT SAC training. Per-mode flow:

  1. Construct KundurSimulinkEnv(training=True, disturbance_type=<mode>)
  2. env.reset() -> warmup
  3. env.apply_disturbance(magnitude=+0.4 sys-pu)
  4. Read back Pm_step_amp_1..4 from MATLAB workspace via bridge.session.eval()
     -> verify only the expected ES index is nonzero (Bus 7 -> ES1=idx 0,
        Bus 9 -> ES4=idx 3); legacy single_vsg honors DISTURBANCE_VSG_INDICES
        class attr (default (0,)).
  5. Run STEPS_PER_EPISODE zero-action steps; record max |omega-1|*F_NOM.
  6. Assert:
       (a) max_freq_dev_hz nonzero and finite,
       (b) workspace amp matches expected target index,
       (c) no NaN/Inf in omega/Pe across the episode,
       (d) no tds_failed.

Modes covered:
  - pm_step_proxy_bus7   (1 episode)
  - pm_step_proxy_bus9   (1 episode)
  - pm_step_proxy_random (4 episodes -> see both buses sampled)
  - pm_step_single_vsg   (1 episode, regression check vs. existing default)

Hard boundaries (per plan §0 + user GO message):
  - No build / .slx / IC / runtime.mat edit (read-only on those files).
  - No bridge edit (uses existing apply_workspace_var).
  - No NE39 touch.
  - No 50-ep / 2000-ep training.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def _read_pm_step_amps(env) -> list[float]:
    """Read Pm_step_amp_1..4 from MATLAB base workspace via bridge."""
    amps: list[float] = []
    eng = env.bridge.session._get_engine()  # private but stable
    for i in range(1, 5):
        # Use evalin to read the base-workspace scalar; force double cast.
        val = eng.eval(f"double(Pm_step_amp_{i})", nargout=1)
        amps.append(float(val))
    return amps


def _run_one_episode(env, steps: int, magnitude: float, mode_label: str) -> dict:
    """Reset env, apply disturbance, run zero-action steps, collect metrics."""
    obs, _ = env.reset()
    pre_amps = _read_pm_step_amps(env)

    cap = StringIO()
    with redirect_stdout(cap):
        env.apply_disturbance(magnitude=magnitude)
    dist_log = cap.getvalue().strip().splitlines()

    post_amps = _read_pm_step_amps(env)

    zero_action = np.zeros((4, 2), dtype=np.float32)

    omega_hist: list[list[float]] = []
    pe_hist: list[list[float]] = []
    freq_dev_hist: list[float] = []
    nan_inf = False
    tds_failed = False

    for t in range(steps):
        obs, reward, terminated, truncated, info = env.step(zero_action)
        omega = info["omega"]
        pe = info["P_es"]
        if not (np.all(np.isfinite(omega)) and np.all(np.isfinite(pe))):
            nan_inf = True
        omega_hist.append([float(x) for x in omega])
        pe_hist.append([float(x) for x in pe])
        freq_dev_hist.append(float(info["max_freq_dev_hz"]))
        if info.get("tds_failed", False):
            tds_failed = True
        if terminated:
            tds_failed = True
            break

    omega_arr = np.asarray(omega_hist, dtype=np.float64)
    return {
        "mode": mode_label,
        "magnitude_sys_pu": float(magnitude),
        "pre_apply_amps_pu": pre_amps,
        "post_apply_amps_pu": post_amps,
        "n_steps_run": len(omega_hist),
        "max_freq_dev_hz": float(np.max(freq_dev_hist)) if freq_dev_hist else 0.0,
        "max_abs_omega_dev_pu": (
            float(np.max(np.abs(omega_arr - 1.0))) if omega_arr.size else 0.0
        ),
        "omega_min": (float(omega_arr.min()) if omega_arr.size else 1.0),
        "omega_max": (float(omega_arr.max()) if omega_arr.size else 1.0),
        "nan_inf_seen": nan_inf,
        "tds_failed": tds_failed,
        "disturbance_log_lines": dist_log,
    }


def main() -> int:
    profile_path = (
        REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
    )
    os.environ["KUNDUR_MODEL_PROFILE"] = str(profile_path)
    # Ensure the env-default disturbance type is the legacy one for the
    # single_vsg regression case; per-mode probes will override via the
    # constructor disturbance_type kwarg.
    os.environ.pop("KUNDUR_DISTURBANCE_TYPE", None)

    out_dir = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phase4"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_out = out_dir / "p41_disturbance_routing_smoke.json"

    print(f"RESULT: KUNDUR_MODEL_PROFILE={profile_path}")
    print("RESULT: starting Phase 4.1 disturbance-routing smoke")

    import scenarios.kundur.config_simulink as cfg
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv

    print(
        f"RESULT: profile.model_name={cfg.KUNDUR_MODEL_PROFILE.model_name} "
        f"profile_id={cfg.KUNDUR_MODEL_PROFILE.profile_id} T_WARMUP={cfg.T_WARMUP}"
    )
    print(
        f"RESULT: KUNDUR_DISTURBANCE_TYPE_default_config={cfg.KUNDUR_DISTURBANCE_TYPE} "
        f"valid={cfg.KUNDUR_DISTURBANCE_TYPES_VALID}"
    )

    steps_per_ep = int(cfg.T_EPISODE / cfg.DT)  # 50
    magnitude = +0.4  # sys-pu, well inside DIST_MIN/DIST_MAX = [0.1, 0.5]

    runs: list[dict] = []
    smoke_ok = True
    fail_reasons: list[str] = []

    # Episode-level run plan: (mode, expected_target_idx, label).
    # For random_bus we run multiple eps to see distribution; expected_target_idx
    # is None and we record both possibilities.
    plan: list[tuple[str, int | None, str]] = [
        ("pm_step_proxy_bus7", 0, "bus7"),
        ("pm_step_proxy_bus9", 3, "bus9"),
        ("pm_step_proxy_random_bus", None, "random_1"),
        ("pm_step_proxy_random_bus", None, "random_2"),
        ("pm_step_proxy_random_bus", None, "random_3"),
        ("pm_step_proxy_random_bus", None, "random_4"),
        ("pm_step_single_vsg", 0, "legacy_single_vsg"),
    ]

    for mode, expected_idx, label in plan:
        print(f"RESULT: --- run label={label} mode={mode} ---")
        env_t0 = time.time()
        try:
            env = KundurSimulinkEnv(training=True, disturbance_type=mode)
        except Exception as exc:
            print(f"RESULT: env construct FAILED for mode={mode}: {exc}")
            traceback.print_exc()
            smoke_ok = False
            fail_reasons.append(f"{label}:env_construct:{exc}")
            continue
        env_construct_s = time.time() - env_t0
        # Seed the np_random for reproducibility on random_bus draws.
        env.np_random  # ensure RNG initialized via reset(); done below.

        try:
            ep_t0 = time.time()
            rec = _run_one_episode(env, steps_per_ep, magnitude, mode)
            rec["label"] = label
            rec["expected_target_idx"] = expected_idx
            rec["env_construct_s"] = env_construct_s
            rec["episode_wall_s"] = time.time() - ep_t0

            # Validate the routing.
            post = rec["post_apply_amps_pu"]
            nonzero_idx = [i for i, v in enumerate(post) if abs(v) > 1e-9]
            zero_idx = [i for i, v in enumerate(post) if abs(v) <= 1e-9]
            rec["nonzero_post_idx"] = nonzero_idx
            rec["zero_post_idx"] = zero_idx

            if expected_idx is not None:
                if nonzero_idx != [expected_idx]:
                    smoke_ok = False
                    fail_reasons.append(
                        f"{label}:wrong_target nonzero={nonzero_idx} "
                        f"expected={[expected_idx]}"
                    )
            else:  # random_bus: expect exactly one of (0, 3)
                if len(nonzero_idx) != 1 or nonzero_idx[0] not in (0, 3):
                    smoke_ok = False
                    fail_reasons.append(
                        f"{label}:random_bus_not_in_{{0,3}} nonzero={nonzero_idx}"
                    )

            if rec["max_freq_dev_hz"] <= 0.0 or not np.isfinite(rec["max_freq_dev_hz"]):
                smoke_ok = False
                fail_reasons.append(
                    f"{label}:freq_dev_zero_or_nonfinite"
                    f"={rec['max_freq_dev_hz']}"
                )
            if rec["nan_inf_seen"]:
                smoke_ok = False
                fail_reasons.append(f"{label}:nan_inf_in_omega_or_pe")
            if rec["tds_failed"]:
                smoke_ok = False
                fail_reasons.append(f"{label}:tds_failed")

            print(
                f"RESULT: label={label} mode={mode} target={nonzero_idx} "
                f"max_dev_Hz={rec['max_freq_dev_hz']:.4f} "
                f"max_abs_omega_dev_pu={rec['max_abs_omega_dev_pu']:.6f} "
                f"nan_inf={rec['nan_inf_seen']} tds_failed={rec['tds_failed']} "
                f"steps={rec['n_steps_run']} wall={rec['episode_wall_s']:.1f}s"
            )
            runs.append(rec)
        except Exception as exc:
            print(f"RESULT: episode FAILED label={label} mode={mode}: {exc}")
            traceback.print_exc()
            smoke_ok = False
            fail_reasons.append(f"{label}:episode_exc:{exc}")
        finally:
            try:
                env.close()
            except Exception:
                pass

    # Random-bus distribution check: with 4 draws under default reset-seed
    # behavior, expect at least one bus7 (idx 0) and at least one bus9 (idx 3)
    # if the dispatch is actually stochastic. Tolerate worst-case 4-of-a-kind
    # under a fixed seed since reset uses time-based seeding only when the
    # caller does not pass seed= (here we don't): record observed counts.
    rand_records = [r for r in runs if r["mode"] == "pm_step_proxy_random_bus"]
    rand_target_counts = {0: 0, 3: 0}
    for r in rand_records:
        for i in r.get("nonzero_post_idx", []):
            if i in rand_target_counts:
                rand_target_counts[i] += 1
    print(
        f"RESULT: random_bus draws={len(rand_records)} bus7(idx0)="
        f"{rand_target_counts[0]} bus9(idx3)={rand_target_counts[3]}"
    )

    summary = {
        "smoke_ok": smoke_ok,
        "fail_reasons": fail_reasons,
        "n_runs": len(runs),
        "rand_target_counts": rand_target_counts,
        "magnitude_sys_pu": magnitude,
        "steps_per_ep": steps_per_ep,
        "T_WARMUP": cfg.T_WARMUP,
        "model_profile": cfg.KUNDUR_MODEL_PROFILE.model_name,
        "config_default_KUNDUR_DISTURBANCE_TYPE": cfg.KUNDUR_DISTURBANCE_TYPE,
        "runs": runs,
    }
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"RESULT: JSON written to {json_out}")
    print(f"RESULT: smoke_ok={smoke_ok}")
    if not smoke_ok:
        print(f"RESULT: fail_reasons={fail_reasons}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
