# agent_state — Trained DDIC Policy Diagnostic Probe

Sibling to `probes/kundur/probe_state/` (model state). Operates on **trained
SAC policies**, not the SLX model.

## Identity

```
purpose:  diagnose a trained DDIC policy beyond cum_rf summary
mode:     read-only — loads ckpts, runs rollouts on AndesMultiVSGEnv
output:   agent_state_<TS>.json + AGENT_STATE_REPORT_<TS>.md
gates:    A1 (specialization), A2 (ablation), A3 (failure forensics)
```

Default output: `results/harness/kundur/agent_state/`.

## Phases

| Phase | Module | Question | Method |
|---|---|---|---|
| A1 | `_specialization.py` | Do the 4 SAC agents converge to distinct policies? | Synthetic-obs cosine similarity matrix + per-agent action stats |
| A2 | `_ablation.py` | Which agents are pulling weight? | Replace agent_i with zero action; measure cum_rf delta |
| A3 | `_failure.py` | Where does max_df_max excursion come from? | Sort 50 fixed-test eps by max_df, inspect worst-K + cluster detection |

## Falsification gates (verdict ∈ {PASS, REJECT, PENDING, ERROR})

| Gate | Meaning | PASS condition |
|---|---|---|
| A1 | Multi-agent framework producing diverse policies | offdiag pairwise cosine mean < `a1_specialized_max_cos` (default 0.60) |
| A2 | All agents contributing | min agent contribution share ≥ `a2_freerider_max_share` (default 5%) AND max/min ratio ≤ 4× |
| A3 | Failures scattered (no actionable cluster) | no clustering by bus / sign / magnitude in worst-K |

A3 inverts the usual "PASS = good" — A3 PASS means **no specific failure pattern** (failures look random). A3 REJECT means **a pattern was detected** that's actionable (e.g., always Bus 14, always large magnitude).

## Usage

```bash
# All phases
python -m probes.kundur.agent_state \
  --ckpt-dir results/andes_phase4_noPHIabs_seed42 \
  --ckpt-kind final

# Subset
python -m probes.kundur.agent_state \
  --ckpt-dir results/andes_phase4_noPHIabs_seed42 \
  --phases A1,A2

# Older PHI_ABS=50 policy (compare)
python -m probes.kundur.agent_state \
  --ckpt-dir results/andes_phase3_seed42 \
  --ckpt-kind best
```

Wall time: A1 ~30s, A2 ~3-5min (5 rollouts × 20 ep), A3 ~4-6min (50 ep). Total ~10min.

## Module layout

```
agent_state.py        AgentStateProbe orchestrator + ALL_PHASES tuple
__main__.py           CLI
probe_config.py       ProbeThresholds + IMPLEMENTATION_VERSION
_loader.py            policy loader (discovery from env class + ckpt dir)
_specialization.py    Phase A1
_ablation.py          Phase A2
_failure.py           Phase A3
_verdict.py           A1-A3 verdict logic
_report.py            JSON + Markdown render
```

## Design principles (mirrored from probe_state)

1. discovery > declaration (N_AGENTS / OBS_DIM from `AndesMultiVSGEnv`, not hardcoded)
2. single source of truth (`FIXED_TEST_SEEDS` from `_ablation.py`, used by A3 too)
3. versioned schema (`SCHEMA_VERSION` + `IMPLEMENTATION_VERSION`)
4. fail-soft per phase (one phase exception → `phase.error`, others continue)
5. read-only on production (no edits to env / agents / config / training scripts)
6. probe measures, does not interpret (verdicts are facts; "policy is bad" is for the consuming agent)

## Versioning

Same convention as probe_state — bump `IMPLEMENTATION_VERSION` on threshold or verdict-logic change. Bump `SCHEMA_VERSION` on snapshot field rename/drop.

## Boundaries

- Reads `agents/sac.py::SACAgent` for ctor signature + `select_action(obs, deterministic)`
- Reads `env/andes/andes_vsg_env.py::AndesMultiVSGEnv` for env interface + class attributes
- Reads `config.py` for SAC hyperparams matching training time
- Writes only under `results/harness/kundur/agent_state/`

If the upstream env / SAC API changes (e.g., `select_action` signature), this probe must be updated. Same boundary as probe_state.
