"""Read-only diagnostic — explain why r_f ≈ 0 (i.e. why Δω_i - ω̄_i ≈ 0).

Hypotheses to discriminate (acceptance criteria from spec):
  A. measurement artifact — omega_ts_1..4 share a single source block
  B. disturbance routing artifact — Pm-step lands on shared/wrong target
  C. true physical strong synchronization
  D. reward ω̄ / adjacency computation artifact

Probe procedure (NO model edits, NO reward edits, NO config edits, NO
training, NO commit until verdict-only):

  1. Cold-start KundurSimulinkEnv (locked v3 profile + env-var Pm-step proxy).
  2. Use env.bridge.session.eval to inspect omega_ts_1..4 ToWorkspace block
     paths and trace to source block (verify per-ESS identity).
  3. Run zero-action episode targeting ES1 with amp=+0.5 sys-pu.
     Verify only Pm_step_amp_1 nonzero; other amps zero.
  4. Capture per-env-step ω_1..4 via env.step()'s info['omega'].
  5. Optionally re-run at amp=+1.0 sys-pu for sensitivity.
  6. Compute differential vs common-mode metrics + raw r_f with training ω̄.
  7. Classify root cause and write JSON + Markdown verdict.

NOTE: this probe touches NO mutable state of the canonical model. ω
values come straight out of the env's normal step() info dict; block-
path inspection is read-only get_param. Pm_step_amp writes are exactly
what env.apply_disturbance does — same as any normal training episode.
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

# Lock pre-flight env-vars BEFORE importing config.
for k in ("KUNDUR_PHI_H", "KUNDUR_PHI_D", "KUNDUR_ALLOW_LEGACY_PROFILE"):
    os.environ.pop(k, None)
os.environ["KUNDUR_MODEL_PROFILE"] = str(
    REPO_ROOT / "scenarios" / "kundur" / "model_profiles" / "kundur_cvs_v3.json"
)
os.environ.setdefault("KUNDUR_DISTURBANCE_TYPE", "pm_step_proxy_random_bus")

import numpy as np
from env.simulink.kundur_simulink_env import KundurSimulinkEnv
from scenarios.kundur.config_simulink import (
    N_AGENTS,
    STEPS_PER_EPISODE,
    PHI_F, PHI_H, PHI_D,
)
from scenarios.contract import KUNDUR as _CONTRACT
F_NOM = _CONTRACT.fn  # 50 Hz

OUT_DIR = REPO_ROOT / "results" / "harness" / "kundur" / "cvs_v3_phi_root_cause"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_omega_logger_identity(env: KundurSimulinkEnv) -> list[dict]:
    """Verify omega_ts_1..4 ToWorkspace blocks come from 4 distinct sources."""
    sess = env.bridge.session
    mdl = env.bridge.cfg.model_name
    code = f"""
    out = struct('var', {{'omega_ts_1','omega_ts_2','omega_ts_3','omega_ts_4'}}, ...
                 'tw_block', {{'','','',''}}, ...
                 'src_block', {{'','','',''}}, ...
                 'src_port', {{0,0,0,0}});
    tw_blocks = find_system('{mdl}', 'BlockType', 'ToWorkspace');
    for ti = 1:length(tw_blocks)
      vn = get_param(tw_blocks{{ti}}, 'VariableName');
      for k = 1:4
        if strcmp(vn, out(k).var)
          out(k).tw_block = tw_blocks{{ti}};
          ph = get_param(tw_blocks{{ti}}, 'PortHandles');
          ln = get_param(ph.Inport(1), 'Line');
          if ln ~= -1
            sp = get_param(ln, 'SrcPortHandle');
            if sp ~= -1
              out(k).src_block = get_param(sp, 'Parent');
              out(k).src_port  = get_param(sp, 'PortNumber');
            end
          end
        end
      end
    end
    json_out = jsonencode(out);
    """
    sess.eval(code, nargout=0)
    json_out = sess.eval("json_out", nargout=1)
    rows = json.loads(json_out)
    return rows


def read_pm_step_amps(env: KundurSimulinkEnv) -> dict:
    """Read all Pm_step_amp_<i> + PmgStep_amp_<g> + LoadStep_amp_busXX."""
    sess = env.bridge.session
    out = {}
    for i in range(1, N_AGENTS + 1):
        out[f"Pm_step_amp_{i}"] = float(sess.eval(f"Pm_step_amp_{i}", nargout=1))
    for g in range(1, 4):
        try:
            out[f"PmgStep_amp_{g}"] = float(sess.eval(f"PmgStep_amp_{g}", nargout=1))
        except Exception:
            out[f"PmgStep_amp_{g}"] = None
    for lb in ("bus14", "bus15"):
        try:
            out[f"LoadStep_amp_{lb}"] = float(sess.eval(f"LoadStep_amp_{lb}", nargout=1))
        except Exception:
            out[f"LoadStep_amp_{lb}"] = None
    return out


def _local_average_omega_dev(om_dev: np.ndarray, comm_adj: dict) -> np.ndarray:
    """Compute ω̄_i per training logic (η_j=1 for all neighbors, no comm fail)."""
    n = len(om_dev)
    out = np.zeros(n)
    for i in range(n):
        nbrs = comm_adj.get(i, [])
        s = om_dev[i] + sum(om_dev[j] for j in nbrs)
        out[i] = s / (1 + len(nbrs))
    return out


def run_amp_cell(env: KundurSimulinkEnv, amp_pu: float, target_idx: int = 0) -> dict:
    """Run one zero-action episode targeting ES1 with given Pm-step magnitude."""
    print(f"\n--- amp = {amp_pu:+.3f} sys-pu, target_idx = {target_idx} (ES{target_idx+1}) ---")
    # Force the disturbance type on the env to single-VSG so target index is honored.
    env._disturbance_type = "pm_step_single_vsg"
    env.DISTURBANCE_VSG_INDICES = (target_idx,)
    obs, _ = env.reset(seed=4242)
    env.apply_disturbance(bus_idx=target_idx, magnitude=amp_pu)

    pm_step_state = read_pm_step_amps(env)
    print(f"  workspace post apply_disturbance:")
    for k, v in pm_step_state.items():
        if v is not None:
            print(f"    {k:25s} = {v:+.4g}")

    # Run STEPS_PER_EPISODE zero-action steps. info['omega'] is per-agent ω at end of chunk.
    omega_history = []  # list of (4,) arrays, length = STEPS_PER_EPISODE
    pe_history = []
    zero_action = np.zeros((N_AGENTS, 2), dtype=np.float32)
    sim_ok = True
    for step in range(STEPS_PER_EPISODE):
        next_obs, rewards, term, trunc, info = env.step(zero_action)
        omega_history.append(np.array(info["omega"], dtype=np.float64).copy())
        pe_history.append(np.array(info["P_es"], dtype=np.float64).copy())
        if not info.get("sim_ok", True):
            sim_ok = False
            break
        obs = next_obs
        if term or trunc:
            break

    omega_arr = np.array(omega_history)  # (T, 4)
    pe_arr = np.array(pe_history)
    df_arr = (omega_arr - 1.0) * F_NOM  # (T, 4) in Hz

    # Per-agent metrics
    max_abs_df = np.max(np.abs(df_arr), axis=0)
    pairwise_max = np.zeros((N_AGENTS, N_AGENTS))
    for i in range(N_AGENTS):
        for j in range(N_AGENTS):
            pairwise_max[i, j] = np.max(np.abs(df_arr[:, i] - df_arr[:, j]))

    # Common-mode + differential decomposition
    common_mode = df_arr.mean(axis=1)  # (T,)
    differential = df_arr - common_mode[:, None]  # (T, 4)
    diff_max = np.max(np.abs(differential), axis=0)  # per-agent
    common_max = np.max(np.abs(common_mode))
    diff_to_common_ratio = diff_max / max(common_max, 1e-12)

    # Reward r_f using training-time logic with η_j=1 (all comms up — paper_eval mode)
    omega_dev_pu = (omega_arr - 1.0)  # in pu
    comm_adj = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}  # 4-ring
    r_f_per_step = np.zeros((omega_arr.shape[0], N_AGENTS))
    for t in range(omega_arr.shape[0]):
        om_dev_t = omega_dev_pu[t]
        omega_bar = _local_average_omega_dev(om_dev_t, comm_adj)
        for i in range(N_AGENTS):
            local = (om_dev_t[i] - omega_bar[i]) ** 2
            nbrs = comm_adj.get(i, [])
            nbr = sum((om_dev_t[j] - omega_bar[i]) ** 2 for j in nbrs)
            r_f_per_step[t, i] = -(local + nbr)

    r_f_total_per_agent = r_f_per_step.sum(axis=0)
    r_f_total_global = (r_f_per_step.sum(axis=1)).sum()  # cum across t and agents

    # Save raw arrays
    cell = {
        "amp_pu": amp_pu,
        "target_idx": target_idx,
        "sim_ok": sim_ok,
        "n_steps": int(omega_arr.shape[0]),
        "pm_step_workspace_state": pm_step_state,
        "max_abs_df_per_agent_hz": max_abs_df.tolist(),
        "pairwise_max_df_hz": pairwise_max.tolist(),
        "common_mode_max_hz": float(common_max),
        "differential_max_per_agent_hz": diff_max.tolist(),
        "differential_to_common_ratio": diff_to_common_ratio.tolist(),
        "r_f_total_per_agent": r_f_total_per_agent.tolist(),
        "r_f_total_global_unscaled": float(r_f_total_global),
        "r_f_total_global_scaled_phi_f": float(PHI_F * r_f_total_global),
        "omega_history": omega_arr.tolist(),
        "pe_history": pe_arr.tolist(),
    }

    print(f"  max|df|_i (Hz) per agent : {max_abs_df.tolist()}")
    print(f"  common_mode_max_hz       : {common_max:.6f}")
    print(f"  differential_max_per_agent: {diff_max.tolist()}")
    print(f"  diff/common ratio         : {diff_to_common_ratio.tolist()}")
    print(f"  pairwise_max max overall  : {pairwise_max.max():.6f} Hz")
    print(f"  r_f total per-agent       : {r_f_total_per_agent.tolist()}")
    print(f"  r_f total scaled (PHI_F)  : {PHI_F * r_f_total_global:+.6f}")

    return cell


def classify_root_cause(
    logger_rows: list[dict],
    cell_05: dict,
    cell_10: dict | None,
) -> dict:
    """Classify per spec acceptance gates A/B/C/D."""
    # ---- A: measurement artifact ----
    src_blocks = [r["src_block"] for r in logger_rows]
    distinct_sources = len(set(src_blocks))
    measurement_ok = (distinct_sources == 4) and all(s != "" for s in src_blocks)
    a_evidence = {
        "distinct_omega_sources": distinct_sources,
        "expected": 4,
        "logger_rows": logger_rows,
    }

    # ---- B: disturbance routing ----
    pm = cell_05["pm_step_workspace_state"]
    target_amp = pm.get("Pm_step_amp_1", 0.0)
    other_amps = [pm.get(f"Pm_step_amp_{i}", 0.0) for i in (2, 3, 4)]
    routing_ok = (
        abs(target_amp) > 1e-6
        and all(abs(a) < 1e-6 for a in other_amps)
        and pm.get("LoadStep_amp_bus14", 0.0) == 248e6  # IC retained
        and pm.get("LoadStep_amp_bus15", 0.0) == 0.0
    )
    b_evidence = {
        "target_amp_pu": target_amp,
        "other_amps_pu": other_amps,
        "loadstep_state_bus14": pm.get("LoadStep_amp_bus14"),
        "loadstep_state_bus15": pm.get("LoadStep_amp_bus15"),
        "routing_clean": routing_ok,
    }

    # ---- C vs D: physical sync vs reward formulation ----
    # If raw differential meaningfully nonzero (i.e. >1% of max|df|) and r_f is
    # still tiny (<1e-3 scaled), then D (reward formula). Else C.
    diff_max = max(cell_05["differential_max_per_agent_hz"])
    common_max = cell_05["common_mode_max_hz"]
    raw_diff_meaningful = (
        common_max > 1e-6 and diff_max / max(common_max, 1e-12) > 0.01
    )
    r_f_scaled = abs(cell_05["r_f_total_global_scaled_phi_f"])
    r_f_meaningful = r_f_scaled > 1e-3

    if raw_diff_meaningful and not r_f_meaningful:
        cause = "D"
        cause_label = "reward omega_bar / adjacency computation artifact"
    elif raw_diff_meaningful and r_f_meaningful:
        cause = "C-partial"
        cause_label = "physical differential exists and r_f reflects it (problem may be magnitude scaling)"
    elif not raw_diff_meaningful and r_f_meaningful:
        cause = "anomaly"
        cause_label = "raw differential ~0 but r_f nonzero — investigate logging / calculation"
    else:
        cause = "C"
        cause_label = "true physical strong synchronization (network coupling pulls ESS together)"

    if not measurement_ok:
        cause = "A"
        cause_label = "measurement artifact — omega loggers may share a source"
    if not routing_ok:
        cause = "B"
        cause_label = "disturbance routing artifact — Pm-step did not land cleanly on target"

    return {
        "primary_classification": cause,
        "label": cause_label,
        "raw_diff_meaningful": raw_diff_meaningful,
        "r_f_scaled_meaningful": r_f_meaningful,
        "evidence_A_measurement": a_evidence,
        "evidence_B_routing": b_evidence,
        "evidence_C_D_diff_max_hz": diff_max,
        "evidence_C_D_common_max_hz": common_max,
        "evidence_C_D_diff_to_common_ratio": diff_max / max(common_max, 1e-12),
        "evidence_C_D_r_f_scaled": r_f_scaled,
    }


def main() -> int:
    print("=" * 72)
    print("PHI root-cause diagnostic - explain why d_omega_i - omega_bar_i ~ 0")
    print(f"Locked PHI: PHI_F={PHI_F} PHI_H={PHI_H} PHI_D={PHI_D}")
    print(f"Disturbance type env: {os.environ['KUNDUR_DISTURBANCE_TYPE']}")
    print("=" * 72)

    print("\n[1] Constructing KundurSimulinkEnv (cold start) ...")
    t0 = time.time()
    env = KundurSimulinkEnv()
    env.reset(seed=4242)  # warmup once so .slx is loaded + warmup-cvs done
    print(f"    env constructed and warmed in {time.time()-t0:.1f}s")

    print("\n[2] Inspecting omega_ts_1..4 logger source identity ...")
    logger_rows = inspect_omega_logger_identity(env)
    for r in logger_rows:
        print(f"    {r['var']:12s}  TW={r['tw_block']}")
        print(f"    {'':12s}  ← src={r['src_block']} (port={r['src_port']})")

    print("\n[3] Running cell @ amp=+0.5 sys-pu, target=ES1 ...")
    cell_05 = run_amp_cell(env, amp_pu=+0.5, target_idx=0)

    print("\n[4] Running sensitivity cell @ amp=+1.0 sys-pu, target=ES1 ...")
    cell_10 = run_amp_cell(env, amp_pu=+1.0, target_idx=0)

    print("\n[5] Classifying root cause ...")
    cls = classify_root_cause(logger_rows, cell_05, cell_10)
    print(f"    PRIMARY: {cls['primary_classification']} — {cls['label']}")

    out = {
        "schema_version": 1,
        "logger_identity": logger_rows,
        "cell_amp_05": cell_05,
        "cell_amp_10": cell_10,
        "classification": cls,
        "config": {
            "PHI_F": PHI_F,
            "PHI_H": PHI_H,
            "PHI_D": PHI_D,
            "STEPS_PER_EPISODE": STEPS_PER_EPISODE,
            "F_NOM": F_NOM,
            "n_agents": N_AGENTS,
            "comm_adj": {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]},
        },
    }
    out_path = OUT_DIR / "diagnostic_raw.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")

    try:
        env.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
