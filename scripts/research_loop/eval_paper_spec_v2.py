"""V2 eval driver — produces paper-spec eval JSON from a ckpt dir.

Replaces lost `scenarios/kundur/_eval_paper_specific.py` (stash-event 2026-05-07).
Output JSON schema matches `evaluation/paper_grade_axes.py` + `figs6_9_ls_traces.py`:
  {controller, scenario, cum_rf_total, max_df, osc, n_steps, traces[]}
  trace[i] = {step, t, freq_hz[N], f_bar, step_rf, delta_P_es[N], delta_f_es[N],
              M_es[N], D_es[N], delta_M[N], delta_D[N]}

Disturbances (from evaluate_andes.py legacy):
  load_step_1: delta_u={"PQ_Bus14": -2.48} (Bus 14 减载 248 MW)
  load_step_2: delta_u={"PQ_Bus15":  1.88} (Bus 15 增载 188 MW)

Usage:
  python scripts/research_loop/eval_paper_spec_v2.py \
      --ckpt-dir results/research_loop/r02_A_lam0p01_200ep_s42 \
      --suffix best \
      --label   ddic_r02_lam0p01_200ep_s42_best \
      --out-dir results/research_loop/eval_r02_paper_spec/

Also generates `no_control_<scenario>.json` (single eval, cached on first run).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.sac import SACAgent  # noqa: E402
from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2  # noqa: E402

# Paper-spec scenarios (legacy from evaluate_andes.py:455-462)
SCENARIOS = {
    "load_step_1": {"PQ_Bus14": -2.48},   # Bus 14 减载 248 MW
    "load_step_2": {"PQ_Bus15":  1.88},   # Bus 15 增载 188 MW
}

EVAL_SEED = 42  # single deterministic seed for fig (matches paper Fig.7/9)


def _load_actors(ckpt_dir: Path, suffix: str = "best", device: str = "cpu") -> list:
    """Load 4 SAC actors from ckpt dir (uses class-attr OBS_DIM since V2 = 7)."""
    from config import HIDDEN_SIZES
    obs_dim = AndesMultiVSGEnvV2.OBS_DIM
    action_dim = 2
    agents = []
    for i in range(AndesMultiVSGEnvV2.N_AGENTS):
        a = SACAgent(obs_dim=obs_dim, action_dim=action_dim,
                     hidden_sizes=HIDDEN_SIZES, device=device)
        ckpt_path = ckpt_dir / f"agent_{i}_{suffix}.pt"
        if not ckpt_path.exists():
            raise FileNotFoundError(ckpt_path)
        a.load(str(ckpt_path))
        agents.append(a)
    return agents


def _eval_one_scenario(scenario_name: str, delta_u: dict,
                        agents: list | None,
                        controller_label: str,
                        seed: int = EVAL_SEED) -> dict:
    """Run V2 env for STEPS_PER_EPISODE=50 with deterministic actor (or zero action).

    Returns paper-spec JSON dict.
    """
    env = AndesMultiVSGEnvV2(random_disturbance=False, comm_fail_prob=0.0)
    env.seed(seed)
    obs = env.reset(delta_u=delta_u)

    N = env.N_AGENTS
    F_NOM = env.FN
    M0 = env.M0.copy()
    D0 = env.D0.copy()

    traces = []
    cum_rf = 0.0
    max_df = 0.0
    osc_accum = 0.0  # cumulative |Δf - mean| sum (rough oscillation proxy)

    for step in range(env.STEPS_PER_EPISODE):
        if agents is not None:
            actions = {i: agents[i].select_action(obs[i], deterministic=True)
                       for i in range(N)}
        else:
            actions = {i: np.zeros(2, dtype=np.float32) for i in range(N)}

        obs, rewards, done, info = env.step(actions)
        if info.get("tds_failed", False):
            break

        freq_hz = info["freq_hz"].astype(float).tolist()
        delta_f = [(f - F_NOM) for f in freq_hz]
        f_bar = float(np.mean(freq_hz))
        step_rf = float(np.mean([(d - (f_bar - F_NOM)) ** 2 for d in delta_f]))
        cum_rf -= step_rf

        max_df = max(max_df, float(np.max(np.abs(delta_f))))
        osc_accum += float(np.std(delta_f))

        traces.append({
            "step":         step,
            "t":            float(info["time"]),
            "freq_hz":      freq_hz,
            "f_bar":        f_bar,
            "step_rf":      step_rf,
            "delta_P_es":   info["P_es"].astype(float).tolist(),
            "delta_f_es":   delta_f,
            "M_es":         info["M_es"].astype(float).tolist(),
            "D_es":         info["D_es"].astype(float).tolist(),
            "delta_M":      info["delta_M"].astype(float).tolist(),
            "delta_D":      info["delta_D"].astype(float).tolist(),
        })

        if done:
            break

    env.close()

    return {
        "controller":   controller_label,
        "scenario":     scenario_name,
        "cum_rf_total": cum_rf,
        "max_df":       max_df,
        "osc":          osc_accum,
        "n_steps":      len(traces),
        "traces":       traces,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt-dir", required=True, help="dir with agent_{0..3}_<suffix>.pt")
    p.add_argument("--suffix",   default="best", choices=["best", "final"])
    p.add_argument("--label",    required=True, help="DDIC label (used in JSON + filename)")
    p.add_argument("--out-dir",  required=True, help="eval output dir for *.json")
    p.add_argument("--seed",     type=int, default=EVAL_SEED)
    p.add_argument("--write-no-ctrl", action="store_true",
                   help="Also write no_control_<scenario>.json baseline")
    args = p.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Load actors
    ckpt_dir = Path(args.ckpt_dir)
    print(f"[eval] loading 4 actors from {ckpt_dir} (suffix={args.suffix})")
    agents = _load_actors(ckpt_dir, suffix=args.suffix)

    # 2. DDIC eval per scenario
    for scen_name, delta_u in SCENARIOS.items():
        print(f"[eval] DDIC {args.label} on {scen_name} (delta_u={delta_u})")
        rep = _eval_one_scenario(scen_name, delta_u, agents, args.label, seed=args.seed)
        out_path = out / f"{args.label}_{scen_name}.json"
        out_path.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"        n_steps={rep['n_steps']}  cum_rf={rep['cum_rf_total']:+.4f}  "
              f"max_df={rep['max_df']:.3f} Hz")

    # 3. no-control baseline (cached, written if missing or --write-no-ctrl)
    if args.write_no_ctrl:
        for scen_name, delta_u in SCENARIOS.items():
            out_path = out / f"no_control_{scen_name}.json"
            if out_path.exists() and not args.write_no_ctrl:
                continue
            print(f"[eval] no_control on {scen_name}")
            rep = _eval_one_scenario(scen_name, delta_u, None, "no_control",
                                      seed=args.seed)
            out_path.write_text(json.dumps(rep, indent=2), encoding="utf-8")
            print(f"        n_steps={rep['n_steps']}  cum_rf={rep['cum_rf_total']:+.4f}  "
                  f"max_df={rep['max_df']:.3f} Hz")

    print(f"[eval] done, output dir = {out}")


if __name__ == "__main__":
    main()
