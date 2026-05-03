# Kundur CVS v3 — Phase 4 50-Episode Gate Plan (DRAFT)

> **Status:** DRAFT (planning only — no training, no SAC edits, no reward edits, no env edits beyond what Phase 3 already shipped).
> **Date:** 2026-04-26
> **Predecessor:** Phase 3 cleared at commit `a5bc173` (P3.4 5-ep smoke PASS).
> **Master plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`](2026-04-26_kundur_cvs_v3_plan.md)
> **Spec:** [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](2026-04-26_cvs_v3_topology_spec.md)

---

## 1. What Phase 4 IS and IS NOT

### Phase 4 IS
- A **50-episode RL gate run** against `kundur_cvs_v3` to confirm:
  1. r_f reward signal has measurable scale (paper §IV-B target: r_f% ≈ 3–8 % of total reward).
  2. SAC actor / critic updates are stable over 50 ep (no NaN, no monotone divergence).
  3. ω deviation per ep stays in [0.05, 0.5] Hz reach band.
  4. v3 wall time per episode stays under a budget compatible with later 2000-ep training.
- A **dual-PHI sweep** (paper-aligned): test ≥ 2 reward shaping configurations to confirm `(PHI_H, PHI_D)` selection has the predicted effect on r_f% balance.
- A documented **GO / NO-GO decision** for Phase 5 (2000-ep paper-baseline training).

### Phase 4 is NOT
- 2000-episode training run (that is **Phase 5**).
- Paper baseline comparison vs adaptive / DDIC / no-control (Phase 5).
- A reward-shaping research project — Phase 4 picks 2–3 PHI configs and reports r_f%, no full grid.
- A reason to touch v2 / NE39 / SAC architecture / bridge / helper.

---

## 2. Hard boundaries (locked)

Phase 4 may **only** edit / create:

```
ALLOW
  scenarios/kundur/config_simulink.py                 (PHI_H/PHI_D choice for v3 if needed; BATCH_SIZE / WARMUP_STEPS may be re-tuned for v3 vs v2)
  scenarios/kundur/train_simulink.py                  (only if a v3-specific CLI flag is required — prefer profile-driven dispatch)
  probes/kundur/v3_dryrun/probe_50ep_phi_gate.py      (NEW; orchestrator that runs train_simulink + collects metrics)
  results/harness/kundur/cvs_v3_phase4/               (NEW dir; per-PHI run dirs + per-PHI verdict + aggregate verdict)
  quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_plan.md   (this file)

ALLOW (consumption only — already wired in Phase 3)
  KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json           (env var dispatch)
  scenarios/kundur/model_profiles/kundur_cvs_v3.json  (read-only)
  env/simulink/kundur_simulink_env.py                 (no edits — already routes v3)
  engine/simulink_bridge.py                           (no edits — already supports cvs_signal)
  slx_helpers/vsg_bridge/{slx_step_and_read_cvs,
    slx_episode_warmup_cvs}.m                          (no edits — both v3-aware after P3.0b/P3.4 R-h1)
  scenarios/kundur/simulink_models/kundur_cvs_v3.slx  (no edits — locked at fix-A2)
  scenarios/kundur/kundur_ic_cvs_v3.json              (no edits — Phase 1)
```

Phase 4 may **NOT** edit:

```
DENY
  agents/                                              (SAC architecture / hyper)
  scenarios/contract.py                                (KUNDUR contract — N_AGENTS, OBS_DIM, ACT_DIM)
  scenarios/config_simulink_base.py                    (shared SAC base hyper)

  scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m  (Phase 1 locked)
  scenarios/kundur/kundur_ic_cvs_v3.json               (Phase 1 locked)
  scenarios/kundur/simulink_models/build_kundur_cvs_v3.m / .slx / .mat   (fix-A2 locked)

  v2 (kundur_cvs.*, kundur_ic_cvs.json, build_kundur_cvs.m, model_profiles/kundur_cvs.json)
  NE39 (scenarios/new_england/, env/simulink/ne39_simulink_env.py)
  Currently-running NE39 training session (PID 75660 / MATLAB PID 70996)
```

Any deviation = STOP and request user authorization.

---

## 3. Phase 4 sub-step cadence (mirrors Phase 3)

```
P4.0 read-only audit                  →  halt, present findings, request GO
  ↓
P4.1 select PHI_H / PHI_D candidates  →  halt, request GO
  ↓
P4.2 50-ep gate run, baseline PHI     →  halt with per-run verdict, request GO
  ↓
P4.3 50-ep gate run, alternate PHI(s) →  halt with per-run verdict, request GO
  ↓
P4.4 aggregate Phase 4 verdict        →  halt with GO/NO-GO recommendation for Phase 5
```

Per-step rules:
- Each 50-ep run goes to its own `results/harness/kundur/cvs_v3_phase4/<run_id>/` dir.
- Per-run verdict file: `results/harness/kundur/cvs_v3_phase4/<run_tag>_verdict.md`.
- Each run is independent (no shared replay buffer across runs).
- All runs use `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json`.
- No 2000-ep training launched anywhere in Phase 4.

---

## 4. P4.0 — Read-only dependency audit (first step)

Before any code change, audit:

| File / dir | Question to answer |
|---|---|
| `scenarios/kundur/config_simulink.py` | Current `PHI_H / PHI_D / PHI_F / BATCH_SIZE / WARMUP_STEPS / DEFAULT_EPISODES` values, and whether they apply uniformly to v2 & v3 or branch on profile |
| `scenarios/kundur/train_simulink.py` | CLI flags — confirm `--episodes 50 --resume none --eval-interval N --save-interval N` cover the smoke-flavored 50-ep we want without a code change |
| `utils/run_protocol.py` + `engine/run_schema.py` | run_id format, training_status.json schema — confirm v3 will produce queryable runs without env edits |
| Currently-running NE39 training | Resource & filesystem footprint — confirm we can launch a v3 training in parallel without contention (MATLAB engine isolation, GPU allocation if any, output dir collisions) |
| `scenarios/kundur/config_simulink.py` PHI_H / PHI_D current values | They are 1e-4 / 1e-4 (B1 baseline). Decide whether v3 keeps that, or applies the asymmetric `PHI_H > PHI_D` recommendation from P2.5c (e.g. 1e-3 / 1e-4) |

P4.0 deliverable: `results/harness/kundur/cvs_v3_phase4/phase4_p40_audit_verdict.md` documenting findings + insertion points + risks.

---

## 5. P4.1 — PHI candidate selection (post-audit)

Recommended initial sweep (subject to user approval after P4.0):

| Run tag | PHI_H | PHI_D | Rationale |
|---|---|---|---|
| `phi_b1` | 1e-4 | 1e-4 | v2 B1 baseline (locked at commit `de5a11c`); reproduces v2 reward shape on v3 model — confirms r_f signal exists on the heavier 16-bus topology. |
| `phi_asym_a` | 1e-3 | 1e-4 | P2.5c-recommended asymmetric weighting — H is the primary RL action lever (4.86× ratio in P2.5a), D is secondary/marginal (P2.5c τ ratio 1.44× under coordinated sweep). 10× heavier H penalty matches the rough authority ratio. |
| `phi_asym_b` | 1e-2 | 1e-3 | (Optional, ONLY if `phi_asym_a` r_f% is too low) — same ratio, larger absolute weights to push reward sensitivity up. |

Stop after the first config that passes the 50-ep gate criteria (§ 6) **OR** after `phi_asym_b` if all three fail.

---

## 6. 50-ep gate criteria (per run)

A 50-ep run PASSES if **all** of:

1. **Completion:** all 50 episodes complete; no `tds_failed`, no `Simscape constraint violation`, no helper status fail, no Python exception.
2. **Numerical health:** zero NaN / Inf in (omega, Pe, action, reward) across 50 × 50 = 2500 step records.
3. **r_f signal scale:** `r_f% = mean(|r_f|) / mean(|total_reward|)` over the last 25 episodes ∈ [3 %, 30 %]. Below 3 % means H/D penalties are dominating (r_f drowned out); above 30 % means H/D are too weak to constrain the agent.
4. **Frequency reach:** per-ep `max_freq_dev_hz` ∈ [0.05, 1.5] Hz on at least 80 % of episodes (paper test envelope).
5. **Action-space health:** per-ep mean(M) ∈ [`M_LO`+ε, `M_HI`−ε] and mean(D) ∈ [`D_LO`+ε, `D_HI`−ε]. The agent should not pin to bounds (suggests reward saturation).
6. **Wall-time budget:** total wall time < 60 min for 50 ep (= 1.2 min/ep). Current MCP-side smoke achieves ~14 s/ep; allow 5× margin for SAC update overhead. Above 60 min → 2000-ep would take > 40 hr → blocker for Phase 5.
7. **Replay buffer / SAC sanity:** loss curves (actor, critic, alpha) finite throughout; no `requires_grad=False` on a tunable; `WARMUP_STEPS` (config_simulink.py) honored.

A run is CONDITIONAL PASS if criteria 1, 2, 4 pass but 3 / 5 / 6 are marginal — document and propose a refinement, do NOT auto-progress to Phase 5.

A run is FAIL if criterion 1 or 2 fails — diagnose, halt, do not retry without a documented fix.

---

## 7. Run management protocol

Each 50-ep run creates:

```
results/sim_kundur/runs/kundur_cvs_v3_<phi_tag>_50ep_<timestamp>/
  ├── checkpoints/             (SAC actor / critic snapshots)
  ├── logs/training_log.json   (per-ep summary)
  ├── training_status.json     (RunStatus schema)
  └── events.jsonl             (per-step disturbance / step metrics, if available)

results/harness/kundur/cvs_v3_phase4/
  ├── <phi_tag>_50ep_summary.json   (machine-readable gate evaluation)
  ├── <phi_tag>_50ep_verdict.md     (human-readable per-run verdict)
  └── phase4_aggregate_verdict.md   (final, after all runs done)
```

`probe_50ep_phi_gate.py` orchestrates:
1. Set env vars (`KUNDUR_MODEL_PROFILE`, `PHI_H`, `PHI_D` overrides via env or config-side patch)
2. Launch `python -m scenarios.kundur.train_simulink --mode simulink --episodes 50 --resume none --output <run_dir>` as subprocess
3. Poll `<run_dir>/training_status.json` until status ∈ {`done`, `failed`}
4. Read training log + ev journal, evaluate criteria
5. Emit `<phi_tag>_50ep_summary.json` + `<phi_tag>_50ep_verdict.md`

NE39 training (PID 75660) keeps running — Phase 4 v3 runs use a separate MATLAB engine started by their own `train_simulink.py` Python session.

---

## 8. Risks (Phase 4-specific)

| ID | Risk | Mitigation |
|---|---|---|
| R-P4-1 | v3 ESS Pm0 = −0.369 sys-pu (absorbing baseline) is a very different operating point from v2 Pm0 = +0.2. SAC initialization may take more episodes to find usable policies. | First 50-ep run uses `--warmup-steps` raised if needed (config-side knob; v2 default 2000). If learning is dead at 50 ep, raise to 5000 and re-run. |
| R-P4-2 | Concurrent NE39 training contention on MATLAB license / shared cache | Each v3 train_simulink launches its own engine; observed 5 concurrent MATLAB.exe processes already coexisting OK. If license blocks v3 launch → halt and ask. |
| R-P4-3 | T_WARMUP=10s smoke value may be too short for stable 50-ep training (P3.3b explicitly flagged this as smoke-stage, not permanent) | Phase 4 keeps T_WARMUP=10s and watches for residual transient bleed into r_f signal. If r_f% noise floor is high, raise to 20-30s. |
| R-P4-4 | r_f signal could be ~0 if agent learns to clamp δ = 0 (no actual swing) under reward shaping that rewards low ω deviation more than the disturbance allows | Gate criterion 3 (r_f% ∈ [3, 30 %]) catches this. Diagnose: lower PHI_H / PHI_D, OR raise disturbance magnitude. |
| R-P4-5 | Memory leak in 16-bus Phasor sim — Phase 2 probes ran ≤ 30 s sims; 50 ep × 50 step × 0.2 s = 500 s sim time per ep × 50 ep = 25 000 s cumulative sim, possible engine-side memory growth | Probe orchestrator restarts the train_simulink subprocess between runs. If MATLAB engine grows above 4 GB → halt and ask. |
| R-P4-6 | NE39 training crashes during Phase 4 due to shared resource | Out of v3 scope; if it happens, document and continue. NE39 user owns the recovery decision. |

---

## 9. Decision points for user

1. **Approve this Phase 4 plan as written?**
2. **Ready to start P4.0 (read-only audit) immediately, or stage for a later session?**
3. **Any adjustments to the dual-PHI candidate list** (§5: `phi_b1` / `phi_asym_a` / `phi_asym_b` ratios)?
4. **Concurrency policy:** OK to launch v3 50-ep run alongside the still-running NE39 500-ep training, or wait for NE39 to finish first?

**No code or training launched until user approves.**

---

## 10. What this plan does NOT decide

- 2000-episode hyperparameter set (Phase 5)
- Paper baseline implementations (adaptive / DDIC / no-control — Phase 5)
- Test-set evaluation protocol (Phase 5)
- Communication delay / failure tests (paper §IV-D, IV-E — separate phase)

These are intentionally deferred to keep Phase 4 minimal.

---

## 11. Files emitted in this draft

```
quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_plan.md   (this file)
```

That's the only Phase 4 file written in this turn. No code, no model, no training.
