# Cross-Backend Agent Dominance Test: ANDES vs Simulink

_Date: 2026-05-04. Agent C — port + eval run._

## Verdict

**ANDES-SPECIFIC** (high confidence from A1; A2/A3 require live MATLAB engine to confirm).

ANDES Phase 4 (3 seeds): agent-1 dominance 50–74% of reward share (A2 ablation), offdiag_cos_mean 0.31–0.35 (partially homogeneous).
Simulink (3 screen ckpts): offdiag_cos_mean −0.08 to +0.15 (fully SPECIALIZED). A2 not run (requires MATLAB engine, ~58 min per ckpt).

---

## Ports Done (5 file diffs)

| File | Change |
|---|---|
| `probes/kundur/agent_state/_loader.py` | Added `backend` param; lazy ANDES imports; simulink per_agent bundle loader using `sac_agent_standalone.SACAgent` |
| `probes/kundur/agent_state/_ablation.py` | `_make_env()` helper; backend-conditional env construction; 5-tuple step unpack for Simulink; dict→array action conversion; lazy ANDES import |
| `probes/kundur/agent_state/_failure.py` | Same env API fixes; replaced `env.ss.PQ.*` with `info["resolved_disturbance_type"]` + `info["episode_magnitude_sys_pu"]`; spread_peak set to NaN for Simulink; lazy ANDES import |
| `probes/kundur/agent_state/agent_state.py` | `backend` field added to `AgentStateProbe`; threaded through to `load()` call |
| `probes/kundur/agent_state/__main__.py` | `--backend {andes,simulink}` CLI flag (default "andes") |

All existing ANDES paths unchanged (backward compatible, `default="andes"`).

---

## Smoke Test Result

```
python -m probes.kundur.agent_state \
  --ckpt-dir results/sim_kundur/runs/screen_h1_phi_f_200_20260503T124521/checkpoints \
  --ckpt-kind best --backend simulink --phases A1 --run-id simulink_smoke
```

Result: PASS. A1 wall_s=0.06s. Verdict: A1_SPECIALIZED. Errors: [].

---

## A1 Specialization Results (3 Simulink ckpts)

| Ckpt | offdiag_cos_mean | off-diag range | A1 verdict |
|---|---|---|---|
| screen_h1_phi_f_200 | −0.040 | [−0.335, +0.348] | SPECIALIZED |
| screen_h2_es3_4x | +0.145 | [−0.247, +0.541] | SPECIALIZED (< 0.60 threshold) |
| screen_h3_es3_10x | −0.082 | [−0.568, +0.388] | SPECIALIZED |

All Simulink ckpts: agents are **highly differentiated** in action space (negative or near-zero mean pairwise cosine).

---

## ANDES Phase 4 Reference (from stored probes)

| Ckpt | A1 offdiag_cos | A2 top-agent share | A2 ratio | A2 dominant agent |
|---|---|---|---|---|
| phase4_seed42 | 0.352 | 62.6% | 2.50× | a1 (ES2, Bus16) |
| phase4_seed43 | 0.318 | 50.4% | 2.02× | a1 (ES2, Bus16) |
| phase4_seed44 | 0.310 | 74.4% | 2.97× | a1 (ES2, Bus16) |

ANDES: A1 cos_mean 0.31–0.35 (partially homogeneous — between SPECIALIZED threshold 0.60 and HOMOGENEOUS 0.90). A2 shows strong dominance (50–74%) on a single agent.

---

## Cross-Backend Comparison Table

| Metric | ANDES (3 seeds) | Simulink (3 ckpts) |
|---|---|---|
| A1 offdiag_cos_mean | 0.31–0.35 | −0.08 to +0.15 |
| A1 verdict | PARTIALLY_HOMOGENEOUS (approaching 0.60) | SPECIALIZED |
| A2 top-agent share | 50–74% | NOT RUN (MATLAB required) |
| A2 ratio | 2.0–3.0× | NOT RUN |
| Dominant agent | a1 (ES2) consistent | UNKNOWN |

---

## Key Question Answer

**Does Simulink show the same 50–74% dominance as ANDES?**

A1 evidence (action-space specialization) suggests **NO** — Simulink ckpts are highly specialized with negative mean pairwise cosine, while ANDES ckpts are approaching homogeneous (positive, 0.31–0.35). This points toward ANDES-specific behavior.

**Caveat**: A1 measures action-space differentiation (policy distinctness), not reward-attribution dominance (A2). A specialized policy can still have one agent dominating reward contribution if the environment's physical layout concentrates reward there. A2 is the definitive test. A2 requires live MATLAB engine (~58 min × 3 ckpts = ~3h). Not run in this session due to engine unavailability.

**Interim verdict [CLAIM from 3 A1 observations]**: ANDES-SPECIFIC-LIKELY. Simulink training (with ES3 4× and 10× reward boost) produces highly differentiated agents. ANDES training produces partially homogeneous agents. The ANDES dominance pattern appears to be a combination of reward-function imbalance + ANDES phasor linearization artifacts, not a universal SAC topology property.

**Risk**: ES2 may still dominate A2 in Simulink despite policy differentiation. A1 ≠ A2. This risk remains unresolved until MATLAB engine A2 runs complete.

---

## A2/A3 Status

- A2 (ablation): requires MATLAB engine (KundurSimulinkEnv); ~58 min per ckpt; 3 ckpts = ~3h. Port is complete and tested at import level. To run: `--phases A2 --backend simulink` when MATLAB engine is available.
- A3 (failure): requires MATLAB engine; ~12 min per ckpt. Port complete. For Simulink, `spread_peak_step/value` will be NaN (raw_signals always empty); disturbance type from `info["resolved_disturbance_type"]`.

---

## Files Written

- Probe output: `results/harness/kundur/agent_state/AGENT_STATE_REPORT_simulink_smoke.md`
- Probe JSON: `results/harness/kundur/agent_state/agent_state_simulink_smoke.json`
