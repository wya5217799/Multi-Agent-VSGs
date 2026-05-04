"""
Paper §IV-C grade evaluator for ANDES Kundur DDIC policy.

Evaluates 5 controllers × 50 fixed test episodes; records ROCoF, settling time,
and bootstrap 95% CI per metric.  Output: JSON + markdown report.

Run:
    wsl bash -c 'source ~/andes_venv/bin/activate && \\
        cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs" && \\
        python3 scenarios/kundur/_eval_paper_grade_andes.py'

Read-only on env / agents / config / evaluation module.
New output lands in results/andes_eval_paper_grade/.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# ── project root on sys.path ──────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

import torch
from agents.sac import SACAgent
from agents.networks import GaussianActor
from env.andes.andes_vsg_env import AndesMultiVSGEnv
from evaluation.metrics import (
    _compute_global_rf_unnorm,
    _compute_per_agent_max_abs_df,
    _rocof_max,
    _settling_time_s,
    _bootstrap_ci,
)

# ── constants ─────────────────────────────────────────────────────────────────
N_AGENTS = AndesMultiVSGEnv.N_AGENTS          # 4
OBS_DIM = AndesMultiVSGEnv.OBS_DIM            # 7
ACTION_DIM = 2
HIDDEN_SIZES = [128, 128, 128, 128]

F_NOM = 50.0       # Hz — Kundur system
DT_S = 0.2         # control step (s)
N_STEPS = 50       # steps per episode
N_TEST_EPS = 50
SEED_BASE = 20000  # seeds 20000..20049

TOL_HZ = 0.005     # settling tolerance (paper-style, README default)
WINDOW_S = 1.0     # settling window (README default)

# Adaptive controller gains (K_H=10, K_D=400)
K_H = 10.0
K_D = 400.0

# Action-range denominators (from base_env, used for adaptive normalisation)
DD_MAX = AndesMultiVSGEnv.DD_MAX   # 30.0
DM_MAX = AndesMultiVSGEnv.DM_MAX   # 30.0

# Normalisation factors from base_env._build_obs
# obs[i][1] = d_omega[i] / 3.0  → d_omega (rad/s dev) = obs[i][1] * 3
# obs[i][2] = omega_dot[i] * _omega_scale / 5.0  → omega_dot_rad = obs[i][2] * 5
_OMEGA_SCALE = F_NOM * 2 * np.pi   # ≈ 314.16 rad/s

OUTPUT_DIR = _ROOT / "results" / "andes_eval_paper_grade"
CKPT_SEEDS = [42, 43, 44]
CKPT_TEMPLATE = "results/andes_phase4_noPHIabs_seed{s}/agent_{i}_final.pt"

BOOTSTRAP_N = 1000
BOOTSTRAP_ALPHA = 0.05
BOOTSTRAP_SEED = 7919


# ── agent loading ─────────────────────────────────────────────────────────────

def _load_agents(seed: int) -> list[SACAgent]:
    """Load 4 SACAgents from a phase4 seed directory."""
    agents = []
    for i in range(N_AGENTS):
        ckpt_path = _ROOT / CKPT_TEMPLATE.format(s=seed, i=i)
        agent = SACAgent(
            obs_dim=OBS_DIM,
            action_dim=ACTION_DIM,
            hidden_sizes=HIDDEN_SIZES,
            device="cpu",
        )
        state = torch.load(str(ckpt_path), map_location="cpu")
        agent.actor.load_state_dict(state["actor"])
        agent.actor.eval()
        agents.append(agent)
    return agents


# ── controller action selectors ───────────────────────────────────────────────

def _action_ddic(agents: list[SACAgent], obs: dict) -> dict:
    """DDIC policy: deterministic action from each SAC actor."""
    return {i: agents[i].select_action(obs[i], deterministic=True)
            for i in range(N_AGENTS)}


def _action_no_control(_agents, _obs: dict) -> dict:
    """No-control baseline: zero actions for all agents."""
    return {i: np.zeros(ACTION_DIM, dtype=np.float32) for i in range(N_AGENTS)}


def _action_adaptive(_agents, obs: dict) -> dict:
    """Best-adaptive controller: K_H * |dω̇|, K_D * |Δω|.

    obs[i][1] = d_omega[i] / 3  (normalised rad/s deviation)
    obs[i][2] = omega_dot[i] * _OMEGA_SCALE / 5  (normalised rad/s² deviation)

    Map to ΔM_norm, ΔD_norm in [-1, 1]:
      ΔM ∝ K_H * |omega_dot_rad|, clamp to [-1, 1]
      ΔD ∝ K_D * |d_omega_rad|,   clamp to [-1, 1]
    """
    actions = {}
    for i in range(N_AGENTS):
        o = obs[i]
        d_omega_rad = float(o[1]) * 3.0          # rad/s deviation
        omega_dot_rad = float(o[2]) * 5.0        # rad/s² (still includes _OMEGA_SCALE in obs)
        delta_m_norm = float(min(K_H * abs(omega_dot_rad) / DM_MAX, 1.0))
        delta_d_norm = float(min(K_D * abs(d_omega_rad)   / DD_MAX, 1.0))
        actions[i] = np.array([delta_m_norm, delta_d_norm], dtype=np.float32)
    return actions


# ── per-episode rollout ───────────────────────────────────────────────────────

def _rollout(
    env: AndesMultiVSGEnv,
    action_fn,
    agents,
    seed: int,
) -> Optional[dict]:
    """Run one episode; return metrics dict or None if TDS failed immediately."""
    env.seed(seed)
    obs = env.reset()

    omega_trace = np.zeros((N_STEPS, N_AGENTS), dtype=np.float64)
    tds_failed = False

    for t in range(N_STEPS):
        actions = action_fn(agents, obs)
        obs, _rewards, done, info = env.step(actions)

        omega_step = np.asarray(info["omega"], dtype=np.float64)  # shape (4,) p.u.
        omega_trace[t] = omega_step

        if info.get("tds_failed", False):
            tds_failed = True
            # fill remaining rows with last known omega
            if t + 1 < N_STEPS:
                omega_trace[t + 1:] = omega_step
            break

        if done:
            break

    # Compute per-episode metrics via evaluation.metrics helpers
    cum_rf = _compute_global_rf_unnorm(omega_trace, f_nom=F_NOM)
    rocof = _rocof_max(omega_trace, dt_s=DT_S, f_nom=F_NOM)
    settling = _settling_time_s(omega_trace, dt_s=DT_S, f_nom=F_NOM,
                                tol_hz=TOL_HZ, window_s=WINDOW_S)
    per_agent_df = _compute_per_agent_max_abs_df(omega_trace, f_nom=F_NOM)
    max_df = float(max(per_agent_df))

    return {
        "seed_ep": seed,
        "cum_rf": float(cum_rf),
        "rocof_max": float(rocof),
        "settling_s": float(settling) if settling is not None else None,
        "max_df_hz": max_df,
        "tds_failed": tds_failed,
    }


# ── aggregate helper ──────────────────────────────────────────────────────────

def _aggregate(ep_records: list[dict], label: str) -> dict:
    """Aggregate 50-ep records into bootstrap-CI summary."""
    n = len(ep_records)
    cum_rf_vals = [r["cum_rf"] for r in ep_records]
    max_df_vals = [r["max_df_hz"] for r in ep_records]
    rocof_vals = [r["rocof_max"] for r in ep_records]
    settling_vals = [r["settling_s"] for r in ep_records if r["settling_s"] is not None]
    n_settled = len(settling_vals)
    n_unsettled = n - n_settled

    # cum_rf is a scalar per episode; report total + CI
    cum_rf_total = float(sum(cum_rf_vals))

    settling_for_ci = settling_vals if settling_vals else [0.0]

    return {
        "label": label,
        "n_scenarios": n,
        "cum_rf_total": cum_rf_total,
        "cum_rf_ci": _bootstrap_ci(cum_rf_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "max_df_hz": _bootstrap_ci(max_df_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "rocof_max": _bootstrap_ci(rocof_vals, n_resample=BOOTSTRAP_N,
                                   alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
        "settling_time_s": {
            **_bootstrap_ci(settling_for_ci, n_resample=BOOTSTRAP_N,
                            alpha=BOOTSTRAP_ALPHA, seed=BOOTSTRAP_SEED),
            "n_settled": n_settled,
            "n_unsettled": n_unsettled,
        },
    }


# ── CI overlap helper ─────────────────────────────────────────────────────────

def _ci_overlap(ci_a: dict, ci_b: dict) -> bool:
    """True if the 95% CIs overlap (not disjoint)."""
    lo_a, hi_a = ci_a["ci_lo"], ci_a["ci_hi"]
    lo_b, hi_b = ci_b["ci_lo"], ci_b["ci_hi"]
    return not (hi_a < lo_b or hi_b < lo_a)


# ── markdown report ───────────────────────────────────────────────────────────

def _write_markdown(summaries: dict, out_path: Path) -> None:
    ctrl_keys = list(summaries["controllers"].keys())
    ctrls = summaries["controllers"]

    lines = [
        "# ANDES Kundur Paper §IV-C Grade Evaluation",
        "",
        "**Metric helpers provenance**: `evaluation/metrics.py`  ",
        f"**N test episodes per controller**: 50 (seeds 20000–20049)  ",
        f"**Settling tolerance**: {TOL_HZ} Hz, window {WINDOW_S}s  ",
        f"**Bootstrap**: n_resample={BOOTSTRAP_N}, alpha={BOOTSTRAP_ALPHA}, seed={BOOTSTRAP_SEED}",
        "",
        "---",
        "",
        "## Table 1 — Cumulative r_f with Bootstrap CI",
        "",
        "| Controller | cum_rf total | mean/ep | ci_lo | ci_hi |",
        "|---|---:|---:|---:|---:|",
    ]
    for k in ctrl_keys:
        c = ctrls[k]
        ci = c["cum_rf_ci"]
        lines.append(
            f"| {k} | {c['cum_rf_total']:.4f} | {ci['mean']:.4f} | "
            f"{ci['ci_lo']:.4f} | {ci['ci_hi']:.4f} |"
        )

    lines += [
        "",
        "## Table 2 — max |Δf|, ROCoF, Settling Time with Bootstrap CI",
        "",
        "| Controller | max_df mean (Hz) | ci_lo | ci_hi |"
        " ROCoF mean (Hz/s) | ci_lo | ci_hi |"
        " settling mean (s) | ci_lo | ci_hi | n_settled/50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k in ctrl_keys:
        c = ctrls[k]
        df = c["max_df_hz"]
        ro = c["rocof_max"]
        st = c["settling_time_s"]
        lines.append(
            f"| {k} | {df['mean']:.4f} | {df['ci_lo']:.4f} | {df['ci_hi']:.4f} |"
            f" {ro['mean']:.4f} | {ro['ci_lo']:.4f} | {ro['ci_hi']:.4f} |"
            f" {st['mean']:.3f} | {st['ci_lo']:.3f} | {st['ci_hi']:.3f} |"
            f" {st['n_settled']}/50 |"
        )

    # Comparison statements
    ddic_key = "ddic_phase4_3seed_mean"
    adaptive_key = "adaptive_K10_K400"
    no_ctrl_key = "no_control"

    if ddic_key in ctrls and adaptive_key in ctrls:
        d_rf = ctrls[ddic_key]["cum_rf_ci"]
        a_rf = ctrls[adaptive_key]["cum_rf_ci"]
        overlap_rf = _ci_overlap(d_rf, a_rf)

        d_df = ctrls[ddic_key]["max_df_hz"]
        a_df = ctrls[adaptive_key]["max_df_hz"]
        overlap_df = _ci_overlap(d_df, a_df)

        d_ro = ctrls[ddic_key]["rocof_max"]
        a_ro = ctrls[adaptive_key]["rocof_max"]
        overlap_ro = _ci_overlap(d_ro, a_ro)

        d_st = ctrls[ddic_key]["settling_time_s"]
        a_st = ctrls[adaptive_key]["settling_time_s"]
        overlap_st = _ci_overlap(d_st, a_st)

    if no_ctrl_key in ctrls and ddic_key in ctrls:
        nc_rf = ctrls[no_ctrl_key]["cum_rf_ci"]
        d_rf2 = ctrls[ddic_key]["cum_rf_ci"]
        improvement_rf = (nc_rf["mean"] - d_rf2["mean"]) / (abs(nc_rf["mean"]) + 1e-12) * 100

    lines += [
        "",
        "## Table 3 — Comparison Statements",
        "",
        "| Comparison | Metric | DDIC mean | Adaptive mean | CI overlap | Interpretation |",
        "|---|---|---:|---:|---|---|",
    ]

    if ddic_key in ctrls and adaptive_key in ctrls:
        def _overlap_str(b: bool) -> str:
            return "OVERLAP → not statistically significant" if b else "NO OVERLAP → significant"

        lines.append(
            f"| DDIC vs adaptive | cum_rf/ep |"
            f" {d_rf['mean']:.4f} | {a_rf['mean']:.4f} |"
            f" CI overlap = {'YES' if overlap_rf else 'NO'} | {_overlap_str(overlap_rf)} |"
        )
        lines.append(
            f"| DDIC vs adaptive | max_df (Hz) |"
            f" {d_df['mean']:.4f} | {a_df['mean']:.4f} |"
            f" CI overlap = {'YES' if overlap_df else 'NO'} | {_overlap_str(overlap_df)} |"
        )
        lines.append(
            f"| DDIC vs adaptive | ROCoF (Hz/s) |"
            f" {d_ro['mean']:.4f} | {a_ro['mean']:.4f} |"
            f" CI overlap = {'YES' if overlap_ro else 'NO'} | {_overlap_str(overlap_ro)} |"
        )
        lines.append(
            f"| DDIC vs adaptive | settling (s) |"
            f" {d_st['mean']:.3f} | {a_st['mean']:.3f} |"
            f" CI overlap = {'YES' if overlap_st else 'NO'} | {_overlap_str(overlap_st)} |"
        )

    if no_ctrl_key in ctrls and ddic_key in ctrls:
        lines.append(
            f"| DDIC vs no-control | cum_rf/ep |"
            f" {d_rf2['mean']:.4f} | {nc_rf['mean']:.4f} |"
            f" — | DDIC improvement: {improvement_rf:+.1f}% |"
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scenarios/kundur/_eval_paper_grade_andes.py`*",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] written → {out_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Define controllers: (label, action_fn, agents_or_None)
    # Build env once; seed per episode
    print("[init] Building ANDES env...")
    t0 = time.time()
    env = AndesMultiVSGEnv(random_disturbance=True)
    print(f"[init] env ready ({time.time()-t0:.1f}s)")

    # Load DDIC agents for each seed
    ddic_agents: dict[int, list[SACAgent]] = {}
    for s in CKPT_SEEDS:
        print(f"[load] Loading DDIC seed {s} agents...")
        ddic_agents[s] = _load_agents(s)

    # Controller specs: (label, action_fn, agents)
    controller_specs: list[tuple[str, object, object]] = [
        ("no_control", _action_no_control, None),
        ("adaptive_K10_K400", _action_adaptive, None),
    ]
    for s in CKPT_SEEDS:
        lbl = f"ddic_phase4_seed{s}_final"
        controller_specs.append((lbl, _action_ddic, ddic_agents[s]))

    # Run evaluations
    all_records: dict[str, list[dict]] = {}

    for label, action_fn, agents in controller_specs:
        print(f"\n[eval] Controller: {label}")
        records = []
        for ep_idx in range(N_TEST_EPS):
            seed = SEED_BASE + ep_idx
            ep_t0 = time.time()
            rec = _rollout(env, action_fn, agents, seed)
            elapsed = time.time() - ep_t0
            status = "TDS_FAIL" if rec and rec["tds_failed"] else "ok"
            print(f"  ep {ep_idx:3d} seed={seed}  "
                  f"cum_rf={rec['cum_rf']:+.4f}  "
                  f"max_df={rec['max_df_hz']:.4f}Hz  "
                  f"rocof={rec['rocof_max']:.3f}Hz/s  "
                  f"settle={rec['settling_s']}s  "
                  f"[{status}] ({elapsed:.1f}s)")
            records.append(rec)
        all_records[label] = records

    env.close()

    # Build 3-seed mean aggregate (150 eps total)
    three_seed_records: list[dict] = []
    for s in CKPT_SEEDS:
        three_seed_records.extend(all_records[f"ddic_phase4_seed{s}_final"])

    # Aggregate summaries
    controllers_summary: dict[str, dict] = {}
    for label, records in all_records.items():
        controllers_summary[label] = _aggregate(records, label)
    controllers_summary["ddic_phase4_3seed_mean"] = _aggregate(
        three_seed_records, "ddic_phase4_3seed_mean")

    output = {
        "metric_helpers_provenance": "evaluation/metrics.py",
        "eval_config": {
            "n_test_eps": N_TEST_EPS,
            "seed_range": f"{SEED_BASE}..{SEED_BASE + N_TEST_EPS - 1}",
            "f_nom_hz": F_NOM,
            "dt_s": DT_S,
            "n_steps": N_STEPS,
            "tol_hz": TOL_HZ,
            "window_s": WINDOW_S,
            "bootstrap": {
                "n_resample": BOOTSTRAP_N,
                "alpha": BOOTSTRAP_ALPHA,
                "seed": BOOTSTRAP_SEED,
            },
            "adaptive_gains": {"K_H": K_H, "K_D": K_D},
        },
        "controllers": controllers_summary,
    }

    json_path = OUTPUT_DIR / "per_seed_summary.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print(f"\n[output] JSON → {json_path}")

    md_path = OUTPUT_DIR / "summary.md"
    _write_markdown(output, md_path)

    print("\n[done] Evaluation complete.")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
