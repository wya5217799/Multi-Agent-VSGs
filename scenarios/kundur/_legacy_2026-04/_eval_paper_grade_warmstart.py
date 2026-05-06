"""
Warmstart ckpt paper-grade evaluator — thin adapter over _eval_paper_grade_andes_one.py.

Loads agents from results/andes_warmstart_seed{SEED}/agent_{i}_final.pt
instead of the Phase 4 template.  All rollout/bootstrap/aggregation logic is
identical to the parent script (imported directly to avoid drift).

Usage:
    python3 scenarios/kundur/_eval_paper_grade_warmstart.py \
        --seed 42 \
        --out-json results/andes_warmstart_seed42/eval_paper_grade.json \
        [--n-eps 50]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

# Import shared helpers from the parent eval script
_parent_mod_path = str(Path(__file__).parent / "_eval_paper_grade_andes_one.py")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_eval_pg_one", _parent_mod_path)
_pg_one = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_pg_one)

# Re-use all constants
N_AGENTS     = _pg_one.N_AGENTS
OBS_DIM      = _pg_one.OBS_DIM
ACTION_DIM   = _pg_one.ACTION_DIM
HIDDEN_SIZES = _pg_one.HIDDEN_SIZES
F_NOM        = _pg_one.F_NOM
DT_S         = _pg_one.DT_S
N_STEPS      = _pg_one.N_STEPS
SEED_BASE    = _pg_one.SEED_BASE
TOL_HZ       = _pg_one.TOL_HZ
WINDOW_S     = _pg_one.WINDOW_S
BOOTSTRAP_N  = _pg_one.BOOTSTRAP_N
BOOTSTRAP_ALPHA = _pg_one.BOOTSTRAP_ALPHA
BOOTSTRAP_SEED  = _pg_one.BOOTSTRAP_SEED

# Warmstart ckpt template (different from Phase 4)
WARMSTART_CKPT_TEMPLATE = "results/andes_warmstart_seed{s}/agent_{i}_final.pt"

from agents.sac import SACAgent
from env.andes.andes_vsg_env import AndesMultiVSGEnv


def _load_warmstart_agents(seed: int) -> list[SACAgent]:
    """Load 4 SACAgents from warmstart seed directory."""
    agents = []
    for i in range(N_AGENTS):
        ckpt_path = _ROOT / WARMSTART_CKPT_TEMPLATE.format(s=seed, i=i)
        if not ckpt_path.exists():
            raise FileNotFoundError(f"Ckpt not found: {ckpt_path}")
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warmstart ckpt paper-grade evaluator"
    )
    parser.add_argument("--seed", type=int, required=True,
                        help="Warmstart seed (42/43/44)")
    parser.add_argument("--out-json", required=True,
                        help="Output JSON path")
    parser.add_argument("--n-eps", type=int,
                        default=int(os.environ.get("N_EPS_OVERRIDE", "50")),
                        help="Number of test episodes (default 50)")
    args = parser.parse_args()

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seed = args.seed
    n_test_eps = args.n_eps
    label = f"ddic_warmstart_seed{seed}_final"

    print(f"[warmstart:{seed}] Building ANDES env (comm_fail_prob=default 0.1)...")
    t0 = time.time()
    env = AndesMultiVSGEnv(random_disturbance=True)
    print(f"[warmstart:{seed}] env ready ({time.time()-t0:.1f}s)")

    print(f"[warmstart:{seed}] Loading warmstart ckpts...")
    agents = _load_warmstart_agents(seed)
    action_fn = _pg_one._action_ddic

    records = []
    for ep_idx in range(n_test_eps):
        ep_seed = SEED_BASE + ep_idx
        ep_t0 = time.time()
        rec = _pg_one._rollout(env, action_fn, agents, ep_seed)
        elapsed = time.time() - ep_t0
        status = "TDS_FAIL" if rec and rec["tds_failed"] else "ok"
        print(
            f"  [warmstart:{seed}] ep {ep_idx:3d} seed={ep_seed}  "
            f"cum_rf={rec['cum_rf']:+.4f}  "
            f"max_df={rec['max_df_hz']:.4f}Hz  "
            f"rocof={rec['rocof_max']:.3f}Hz/s  "
            f"settle={rec['settling_s']}s  "
            f"[{status}] ({elapsed:.1f}s)"
        )
        records.append(rec)

    env.close()

    summary = _pg_one._aggregate(records, label)

    output = {
        "controller": f"ddic_warmstart_seed{seed}",
        "label": label,
        "n_test_eps": n_test_eps,
        "seed_range": f"{SEED_BASE}..{SEED_BASE + n_test_eps - 1}",
        "eval_config": {
            "f_nom_hz": F_NOM,
            "dt_s": DT_S,
            "n_steps": N_STEPS,
            "tol_hz": TOL_HZ,
            "window_s": WINDOW_S,
            "comm_fail_prob": 0.1,
            "bootstrap": {
                "n_resample": BOOTSTRAP_N,
                "alpha": BOOTSTRAP_ALPHA,
                "seed": BOOTSTRAP_SEED,
            },
        },
        "episode_records": records,
        "summary": summary,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print(f"[warmstart:{seed}] written → {out_path}")


if __name__ == "__main__":
    main()
