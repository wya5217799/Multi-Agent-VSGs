"""
Single-controller worker for the parallel ANDES paper-grade evaluator.

Runs one controller × N test episodes; writes per-controller JSON to --out-json.
Called as a subprocess by _eval_paper_grade_andes_parallel.py.

Usage:
    python3 scenarios/kundur/_eval_paper_grade_andes_one.py \\
        --controller no_control \\
        --out-json results/andes_eval_paper_grade/no_control.json \\
        [--n-eps 50]

Controllers:
    no_control         zero action baseline
    adaptive           K_H=10 / K_D=400 adaptive controller
    ddic_seed42        DDIC phase4 seed 42
    ddic_seed43        DDIC phase4 seed 43
    ddic_seed44        DDIC phase4 seed 44
    ddic_seed45        DDIC phase4 seed 45 (Tier A n=5 extension)
    ddic_seed46        DDIC phase4 seed 46 (Tier A n=5 extension)

Pure-Python; no subprocess calls.  Read-only on env / agents / config /
evaluation module.
"""
from __future__ import annotations

import argparse
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
from env.andes.andes_vsg_env import AndesMultiVSGEnv
from evaluation.metrics import (
    _compute_global_rf_unnorm,
    _compute_per_agent_max_abs_df,
    _rocof_max,
    _settling_time_s,
    _bootstrap_ci,
)

# ── constants (identical to serial version) ───────────────────────────────────
N_AGENTS = AndesMultiVSGEnv.N_AGENTS          # 4
OBS_DIM = AndesMultiVSGEnv.OBS_DIM            # 7
ACTION_DIM = 2
HIDDEN_SIZES = [128, 128, 128, 128]

F_NOM = 50.0       # Hz — Kundur system
DT_S = 0.2         # control step (s)
N_STEPS = 50       # steps per episode
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

CKPT_TEMPLATE = "results/andes_phase4_noPHIabs_seed{s}/agent_{i}_final.pt"

BOOTSTRAP_N = 1000
BOOTSTRAP_ALPHA = 0.05
BOOTSTRAP_SEED = 7919

# Map CLI controller names to (ckpt_seed_or_None)
_CONTROLLER_NAMES = {
    "no_control",
    "adaptive",
    "ddic_seed42",
    "ddic_seed43",
    "ddic_seed44",
    "ddic_seed45",
    "ddic_seed46",
    # 2026-05-04 hparam sweep: arbitrary checkpoint dir via --ckpt-dir
    "ddic_custom",
}


def _load_agents_from_dir(ckpt_dir: Path) -> list[SACAgent]:
    """Load 4 SACAgents from any directory containing agent_{0..3}_final.pt."""
    agents = []
    for i in range(N_AGENTS):
        ckpt_path = ckpt_dir / f"agent_{i}_final.pt"
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
    """
    actions = {}
    for i in range(N_AGENTS):
        o = obs[i]
        d_omega_rad = float(o[1]) * 3.0
        omega_dot_rad = float(o[2]) * 5.0
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
            if t + 1 < N_STEPS:
                omega_trace[t + 1:] = omega_step
            break

        if done:
            break

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
    """Aggregate episode records into bootstrap-CI summary."""
    n = len(ep_records)
    cum_rf_vals = [r["cum_rf"] for r in ep_records]
    max_df_vals = [r["max_df_hz"] for r in ep_records]
    rocof_vals = [r["rocof_max"] for r in ep_records]
    settling_vals = [r["settling_s"] for r in ep_records if r["settling_s"] is not None]
    n_settled = len(settling_vals)
    n_unsettled = n - n_settled

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


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single-controller ANDES paper-grade evaluator worker"
    )
    parser.add_argument(
        "--controller",
        required=True,
        choices=sorted(_CONTROLLER_NAMES),
        help="Which controller to evaluate",
    )
    parser.add_argument(
        "--out-json",
        required=True,
        help="Path to write per-controller JSON output",
    )
    parser.add_argument(
        "--n-eps",
        type=int,
        default=int(os.environ.get("N_EPS_OVERRIDE", "50")),
        help="Number of test episodes (default 50; override for smoke tests)",
    )
    parser.add_argument(
        "--ckpt-dir",
        type=str,
        default=None,
        help="Custom checkpoint directory (required for ddic_custom). "
             "If sibling training_log.json contains hparam_effective, those "
             "are monkey-patched to AndesMultiVSGEnv class attrs BEFORE env "
             "construction (action range must match training).",
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="Override output label (default: derived from controller name)",
    )
    args = parser.parse_args()

    n_test_eps: int = args.n_eps
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ctrl_name: str = args.controller

    # 2026-05-04 hparam sweep: monkey-patch hparam_effective from training_log
    # BEFORE env construction so action range / phi values match training.
    # Only relevant for ddic_custom controllers; baseline controllers ignore it.
    if ctrl_name == "ddic_custom":
        if args.ckpt_dir is None:
            raise SystemExit("ddic_custom requires --ckpt-dir")
        ckpt_dir = Path(args.ckpt_dir)
        tl_path = ckpt_dir / "training_log.json"
        if tl_path.exists():
            tl = json.load(open(tl_path))
            eff = tl.get("hparam_effective", {})
            if eff:
                print(f"[worker:{ctrl_name}] applying hparam_effective from {tl_path}:")
                for attr in ("PHI_F", "PHI_D", "DM_MIN", "DM_MAX", "DD_MIN", "DD_MAX"):
                    if attr in eff:
                        old = getattr(AndesMultiVSGEnv, attr)
                        setattr(AndesMultiVSGEnv, attr, float(eff[attr]))
                        print(f"   {attr}: {old} -> {eff[attr]}")

    print(f"[worker:{ctrl_name}] Building ANDES env...")
    t0 = time.time()
    env = AndesMultiVSGEnv(random_disturbance=True)
    print(f"[worker:{ctrl_name}] env ready ({time.time()-t0:.1f}s)")

    # Resolve action_fn and agents
    if ctrl_name == "no_control":
        action_fn = _action_no_control
        agents = None
        label = "no_control"
    elif ctrl_name == "adaptive":
        action_fn = _action_adaptive
        agents = None
        label = "adaptive_K10_K400"
    elif ctrl_name == "ddic_custom":
        ckpt_dir = Path(args.ckpt_dir)
        print(f"[worker:{ctrl_name}] Loading DDIC custom from {ckpt_dir}...")
        agents = _load_agents_from_dir(ckpt_dir)
        action_fn = _action_ddic
        label = args.label or f"ddic_custom_{ckpt_dir.name}"
    else:
        # ddic_seedXX
        seed_str = ctrl_name.split("ddic_seed")[1]
        ckpt_seed = int(seed_str)
        print(f"[worker:{ctrl_name}] Loading DDIC seed {ckpt_seed} agents...")
        agents = _load_agents(ckpt_seed)
        action_fn = _action_ddic
        label = f"ddic_phase4_seed{ckpt_seed}_final"

    records = []
    for ep_idx in range(n_test_eps):
        seed = SEED_BASE + ep_idx
        ep_t0 = time.time()
        rec = _rollout(env, action_fn, agents, seed)
        elapsed = time.time() - ep_t0
        status = "TDS_FAIL" if rec and rec["tds_failed"] else "ok"
        print(
            f"  [worker:{ctrl_name}] ep {ep_idx:3d} seed={seed}  "
            f"cum_rf={rec['cum_rf']:+.4f}  "
            f"max_df={rec['max_df_hz']:.4f}Hz  "
            f"rocof={rec['rocof_max']:.3f}Hz/s  "
            f"settle={rec['settling_s']}s  "
            f"[{status}] ({elapsed:.1f}s)"
        )
        records.append(rec)

    env.close()

    summary = _aggregate(records, label)

    output = {
        "controller": ctrl_name,
        "label": label,
        "n_test_eps": n_test_eps,
        "seed_range": f"{SEED_BASE}..{SEED_BASE + n_test_eps - 1}",
        "eval_config": {
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
        "episode_records": records,
        "summary": summary,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print(f"[worker:{ctrl_name}] written → {out_path}")


if __name__ == "__main__":
    main()
