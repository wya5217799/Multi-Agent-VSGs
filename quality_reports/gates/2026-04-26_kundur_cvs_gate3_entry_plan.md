# Stage 2 Gate 3 — Entry Plan (RL/SAC pre-flight, no training yet)

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` (HEAD `74428d7` after D4-rev-B Gate 2 PASS)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** PLAN — design-only, no code change. **Does NOT start training.**
**Predecessors:**
- D4-rev-B Gate 2 PASS — `2026-04-26_kundur_cvs_p4_d4_rev_gate2.md`
- D3 Gate 1 PASS — `2026-04-26_kundur_cvs_p4_d3_gate1.md`
- Stage 2 readiness plan §1 D5 — `2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- Engineering contract — `docs/design/cvs_design.md`
- Constraint doc (read-only, main worktree) — `docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md`

---

## TL;DR

Gate 3 (RL/SAC baseline) is **still locked**. This plan does three things:

1. Lists the **engineering prerequisites** that must be in place before any
   RL command runs (model profile JSON, `bridge.py` `step_strategy` field,
   new step/warmup `.m` files, NE39 snapshot). All of these are currently
   **not done** and are explicitly carved out of the locked-down areas
   (`engine/simulink_bridge.py`, `slx_helpers/vsg_bridge/*`, NE39).
2. Defines a **first-smoke** of 5–10 episodes — not the 50-ep "baseline"
   from readiness plan §1 D5 — to detect integration / wiring errors before
   any quantitative learning claim is made.
3. Locks the metric inheritance map: which Gate 2 (D4-rev-B) hard criteria
   carry over verbatim, which become RL-time constraints, and which are
   genuinely new RL-only signals.

Until **all prerequisites pass and the user authorises the smoke command**,
no SAC / replay-buffer / training entry is invoked.

---

## 0. Strict scope (carries over from D4-rev-B)

| Item | Status | Notes |
|---|---|---|
| `engine/simulink_bridge.py` | UNCHANGED through this plan | Will need a NEW `step_strategy` field at G3-prep time (see §3) — additive only, no original-field mutation; that step is itself gated by user authorisation |
| `slx_helpers/vsg_bridge/*` | UNCHANGED | NE39 共享层；G3-prep will add NEW files `*_cvs.m`, NOT edit shared ones |
| `scenarios/contract.py::KUNDUR` | UNCHANGED | single source of truth |
| `scenarios/new_england/*`, `env/simulink/ne39_*.py` | UNCHANGED | NE39 isolation |
| legacy ee / SPS .slx, `kundur_ic.json`, legacy NR | UNCHANGED | |
| `agents/`, `config.py`, `env/simulink/_base.py`, reward / observation / action | UNCHANGED | paper-fidelity contract |
| `Pm0`, `X_v`, `X_tie`, `X_inf`, `Pe_scale` | UNCHANGED | |
| `M0_default = 24, D0_default = 18` | LOCKED at D4-rev-B paper-baseline | further D mutation needs another explicit user authorisation, NOT in this plan |
| Hard criteria of Gate 2 | LOCKED (5 items, see §4) | inherited verbatim during RL |
| δ_overshoot diagnostic | LOCKED at "diagnostic-only, not gating" | recorded but never blocks training |
| D1 / D2 / D3 / D4 / D4.1 / D4.2 / D4-rev-B verdict reports | UNCHANGED on disk | historical record |

---

## 1. Why a separate G3-prep stage is required

Stage 2 readiness plan §1 D5 lists the entry conditions:

> ✅ Gate 1 (D3) PASS — DONE (`307952e`)
> ✅ Gate 2 (D4) PASS — DONE (`74428d7`, D4-rev-B)
> ✅ NE39 baseline 快照已记录 — **NOT DONE**
> ✅ `scenarios/kundur/model_profiles/kundur_cvs.json` 写完 — **NOT DONE**
> ✅ `bridge.py` `step_strategy` 字段加好 — **NOT DONE**
> ✅ 新 step/warmup `.m`: `slx_step_and_read_cvs.m`, `slx_episode_warmup_cvs.m` — **NOT DONE**
> ✅ 50 ep baseline 命令已固定 + 显式日志路径 — **NOT DONE**
> ✅ 用户显式授权启动训练 — **NOT GIVEN**

The first two PASS ✅. The next five are engineering prerequisites; the
last is the user-authorisation gate. **None of the five engineering items
exists yet.** Each one touches a file inside the strict-scope list (above)
and must therefore be its own narrow, user-authorised step. Lumping them
into a single "G3 prep" commit would violate the worktree's commit-layering
discipline.

This entry plan therefore proposes a 5-step **G3-prep ladder** before any
training command is issued.

---

## 2. G3-prep ladder (5 steps, design-only here)

Each step is a separate authorisation gate and a separate commit. None of
them is approved by this plan — only described.

### G3-prep-A — Kundur CVS model profile JSON

**Adds:** `scenarios/kundur/model_profiles/kundur_cvs.json`
(NEW file; sibling of `kundur_ee_legacy.json` and `kundur_sps_candidate.json`)

**Schema:** matches the existing `model_profiles/schema.json`. Key fields:
`model_name = "kundur_cvs"`, `phase_command_mode`, `pe_measurement = "vi"`,
`pe_vi_scale = 0.5` (note: this is the **bridge-side** Pe scaling for ω
observation in the env, distinct from the **build-side** `Pe_scale =
1.0/Sbase` that closes the swing-eq loop — see D2 verdict).

**Does NOT touch:** `kundur_ee_legacy.json`, `kundur_sps_candidate.json`,
`schema.json`, `model_profile.py`, `config_simulink.py`. The new profile
must be selectable via the existing `KUNDUR_MODEL_PROFILE` env var; no
fallback or default change.

**Verification:** `load_kundur_model_profile('kundur_cvs.json')` returns
without error and yields the same fields the bridge already reads. Read-only
test, no sim.

---

### G3-prep-B — Bridge `step_strategy` field

**Adds:** in `engine/simulink_bridge.py`, a new optional config field
`step_strategy: str = "phang_feedback"` (default = current behaviour).

**Used by:** the env factory to dispatch to either the existing phang_feedback
step (NE39 + legacy Kundur) or the new `cvs_signal` step (Kundur CVS).

**Constraint:** ADD-ONLY. No existing field renamed, no existing default
changed, no existing branch deleted. NE39 path must remain bit-exact.

**Verification:** NE39 short run (3 ep) before/after the field is added —
reward / max_freq_dev / settled_rate stay within `<30 %` of the §3 baseline.

---

### G3-prep-C — New CVS step / warmup `.m` files

**Adds:** `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` and
`slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m`.

**Constraint:** **NEW files only.** Neither `slx_step_and_read.m` nor
`slx_episode_warmup.m` may be edited (NE39 共享层; cvs_design.md H3).

**Internals:** the CVS step must drive `Pm_step_t_<i>` / `Pm_step_amp_<i>`
disturbance inputs (already in the model from D4) and per-VSG action
mapping `M_i, D_i ← H_ES0[i] + ΔH_i, D_ES0[i] + ΔD_i` (per-paper Eq.12-13).
Pe / ω readout follows the existing `slx_step_and_read.m` shape so the
bridge can swap with a one-line dispatch.

**Verification:** unit test against the D3-style zero-action 30 s sim —
all 5 D3 PASS criteria must still hold.

---

### G3-prep-D — NE39 baseline snapshot (read-only)

**Adds:** `quality_reports/gates/2026-04-26_ne39_baseline_snapshot.md`
(NEW file, content per readiness plan §2).

**Does:** runs `python scenarios/new_england/train_simulink.py --mode
simulink --episodes 3 --resume none` against the **un**modified NE39 path
(before G3-prep-B/C land), records reward / max_freq_dev / settled_rate.

**Does NOT touch:** any NE39 file. After the 3-ep run completes the
snapshot script restores `FastRestart=off` and base ws defaults.

**Used as:** the contamination tripwire for G3-prep-B and G3-prep-C —
any post-prep NE39 short run that deviates `>30 %` from this snapshot
triggers an immediate roll-back of B/C.

---

### G3-prep-E — Smoke command spec + reproducibility lock

**Adds:** a small spec file pinning:
- random seed = 42
- model file SHA-256, IC JSON SHA-256
- exact command line + env activation
- result destination `results/sim_kundur/runs/cvs_smoke_<timestamp>/`
- `pip freeze` snapshot path

**Authorisation:** the user must explicitly issue the run command. The spec
file does not invoke training.

---

## 3. First smoke — 5–10 episodes, not 50

Readiness plan §1 D5 calls 50 ep a "baseline". **This entry plan inserts
a smaller smoke step ahead of it** to catch integration errors cheaply.

### 3.1 Why 5–10 ep first

| Risk caught at smoke | Risk requires 50 ep | Risk requires 2000 ep |
|---|---|---|
| sim / matlab.engine wiring crash | reward-shape regression vs paper | convergence quality |
| step_strategy dispatch error | ε-greedy / replay buffer fill | learning saturation |
| Pe / ω scale-factor mismatch | settle / nadir distribution at varied dist | SAC entropy collapse |
| NaN / Inf from new `.m` files | ep-level wall-clock budget | inter-area mode coupling |
| action mapping (ΔH / ΔD encoding) sanity | r_h / r_f / r_d share at noisy SAC | optimal policy quality |
| baseline `M, D` change downstream impact | episode-to-episode reproducibility | — |

The **first 5–10 ep** are dominated by random actions (replay buffer is
warming, SAC actor is near initial entropy), so they exercise the env-bridge
plumbing without yet asserting anything about learning. A failure here is
almost certainly an integration bug, not a method bug.

### 3.2 Smoke episode count

| Setting | Value | Source |
|---|---|---|
| `--episodes` | **5** for the *first* smoke; **10** if the 5-ep smoke is clean and the user wants a slightly stronger sanity | this plan |
| `--resume` | `none` | clean run |
| seed | `42` | reproducibility |
| `T_EPISODE` | 10 s (M=50) | `config_simulink.py` L56 — UNCHANGED |
| `DT` | 0.2 s | `_CONTRACT.dt` — UNCHANGED |
| `WARMUP_STEPS` | 2000 | `config_simulink.py` L151 — UNCHANGED |
| `BUFFER_SIZE` | 10000 | `config.py` — UNCHANGED |
| Reward weights | `φ_f=100, φ_h=1, φ_d=1` | `config.py` — UNCHANGED |
| Network | 4 × 128 fully connected | `config.py` — UNCHANGED |

**Note on warmup vs smoke**: `WARMUP_STEPS = 2000` against a 50-step
episode means the buffer needs ~40 episodes before SAC updates begin. So
in a 5–10 ep smoke, **no SAC update** will fire — actions stay random.
This is intentional: the smoke is plumbing, not learning. A 50 ep "baseline"
(readiness plan §1 D5) is the next, separately-authorised step.

### 3.3 Smoke pass / abort criteria

PASS (5–10 ep all green):
- 0 sim / matlab.engine errors
- 0 NaN / Inf in any per-ep ω, δ, Pe trace
- ω never enters [0.7, 1.3] hard clip in any ep
- `max_freq_dev` < 12 Hz in every ep (= readiness plan §1 D5 abort threshold,
  also recorded as a *budget*, not a *gate*, here)
- IntD never touches ±π/2 in any ep
- per-ep wall-clock ≤ 5 min (50-step ep × ~0.5 s/step + reset overhead)

ABORT (any one triggers a hard stop, no retry on the same model):
- ω clip touch (any ep, any step)
- NaN / Inf
- sim crash
- per-ep wall-clock > 10 min (suggests cache or compile pathology)
- reward goes non-finite (`-inf` / `nan`) at any step

DIAGNOSTIC ONLY (recorded, not gating, in the smoke):
- per-ep δ-channel overshoot ratio (carried over from D4-rev-B)
- r_h / r_f / r_d shares (cannot make a paper claim with random actions)
- ep_reward magnitude (random actions give noisy ep_reward; useless until
  warmup completes)

---

## 4. Metric inheritance map

| Metric | Source | Gate 2 status | First-smoke role | 50-ep baseline role | 2000-ep paper-replication role |
|---|---|---|---|---|---|
| `linearity_R²` | D4-rev-B | hard PASS (1.0) | not measured (no swept dist) | not measured | not measured |
| `max_freq_dev` margin (Hz) | D4-rev-B | hard PASS (0.15 / 5) | **hard abort if > 12 Hz any ep** | hard abort if > 12 Hz any ep | quantitative claim per ep |
| `settle_relative_5%-of-peak ≤ 15 s` | D4-rev-B | hard PASS (8.5) | not measured (no isolated step) | quality signal at low-noise eps | post-hoc analysis on policy |
| `no_omega_clip_touch` | D4-rev-B | hard PASS | **hard abort if any clip touch** | hard abort | hard abort (any ep) |
| `simulation_health` (no NaN/Inf, no sim error) | D4-rev-B | hard PASS | **hard abort if violated** | hard abort | hard abort |
| δ-channel overshoot | D4-rev-B | diagnostic-only | diagnostic-only (logged) | diagnostic-only | diagnostic-only |
| ep_reward, r_f / r_h / r_d shares | new | n/a | logged but no claim (random) | learning-signal claim (after warmup) | quantitative claim |
| settled_rate (last 10 step within ±0.1 Hz) | new (readiness plan §1 D5) | n/a | logged | hard PASS criterion ≥ 60 % | quantitative claim |
| IntD clip touches | new | n/a | hard abort | hard abort | hard abort |
| `r_h share of \|reward\|` | new (batch 22 lesson) | n/a | logged (random action noise) | hard abort if > 60 % | quantitative claim |
| per-ep wall-clock | new | n/a | hard abort if > 10 min | budget cap (4 h cumulative) | budget cap |

**Inherited verbatim** (D4-rev-B → smoke / 50 ep): `no_omega_clip_touch`,
`simulation_health`, `max_freq_dev` (margin tightened from `≤ 5 Hz @ 0.5 pu`
to `< 12 Hz any time` per readiness plan §1 D5 batch 22 lesson), δ_overshoot
diagnostic recording.

**Genuinely new at RL time** (not in any pre-RL gate): `ep_reward`, `r_f /
r_h / r_d shares`, `settled_rate`, `IntD clip touches per ep`, `wall-clock
per ep`. These cannot be measured pre-RL because they need an action sequence
and the env time-evolution at varied disturbances — exactly the work SAC does.

---

## 5. Open decisions (not made by this plan)

| ID | Decision | Default if user is silent | Why |
|---|---|---|---|
| G3-EP-1 | Run G3-prep-A (model profile JSON) yes/no/when | hold until user says go | touches a new file but conventionally low-risk; still want explicit go |
| G3-EP-2 | Order of B vs C (bridge field vs new `.m` files) | B first (additive Python field is reversible faster than `.m` file reviews) | discussion |
| G3-EP-3 | NE39 baseline snapshot timing — before B/C, between B and C, or after both | **before B** (must be a clean baseline) | otherwise NE39 short run picks up new bridge code |
| G3-EP-4 | First-smoke ep count: 5 or 10 | **5** | enough for plumbing, not enough to fight the warmup |
| G3-EP-5 | Acceptable per-ep wall-clock | **5 min nominal, 10 min hard abort** | based on D4-rev-B sweep timing × M=50 step |
| G3-EP-6 | Whether `IntD ±π/2` aborts within an ep or end-of-ep | abort the ep (mark FAIL), continue smoke | retains useful failure data without nuking the run |
| G3-EP-7 | What happens if smoke PASSes but δ_overshoot diagnostic shows new behaviour vs D4-rev-B (1.7-1.75) | log only, do not gate | δ_overshoot is diagnostic per D4-rev-B disposition |
| G3-EP-8 | Whether to attempt 50 ep automatically after a clean 5-ep smoke | **NO** — 50 ep is a separate user authorisation | discipline |

---

## 6. What this plan does NOT authorise

- 任何 RL / SAC / replay-buffer 启动
- 任何 `bridge.py` / `slx_helpers/vsg_bridge/*` / NE39 文件改动
- reward / agent / network / hyper-parameter mutation
- model parameter mutation (`M`, `D`, `Pm0`, X-values, `Pe_scale`, IC schema)
- 50 ep baseline / 2000 ep paper-replication run
- main worktree (`fix/governance-review-followups`) anything

If the user wants to advance, the next message must explicitly name a
specific G3-prep step (A, B, C, D, or E) or the smoke step.

---

## 7. Cross-references

| Decision | Source location |
|---|---|
| Gate 2 PASS verdict | `2026-04-26_kundur_cvs_p4_d4_rev_gate2.md` (commit `74428d7`) |
| 50-ep baseline scope (post-smoke) | readiness plan §1 D5 |
| NE39 contamination protocol | readiness plan §2 |
| Bridge dispatch (`step_strategy`) | cvs_design.md §4 |
| Reward / network / hyperparams (paper-fidelity) | `config.py`, fact-base §3-§5 |
| Action mapping ΔH ∈ [-16.1, 72], ΔD ∈ [-14, 54] | `config.py` L49-50 (project deviation from paper §10) |
| Yang Sec.IV-B action range `ΔD ∈ [-200, 600]` | fact-base L100; project deviation noted at config.py L41-46 |

---

## 8. Status when reviewing this plan

```
HEAD:    74428d7 feat(cvs-d4-rev): pass Gate 2 with paper-baseline damping metrics
Gate 1:  PASS  (commit 307952e)
Gate 2:  PASS  (commit 74428d7, D4-rev-B; 5/5 hard criteria, δ_overshoot diagnostic)
Gate 3:  LOCKED — awaits all G3-prep-A/B/C/D/E + user authorisation
SAC entry: NEVER attempted in this branch yet
```

Plan stops here. Awaiting the user's pick of the next step (or hold).
