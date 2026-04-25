# Stage 2 D4.2 — Read-only Audit of Gate 2 FAIL Root Causes

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` (HEAD `307952e` after D3 commit)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** READ-ONLY AUDIT — no code, model, parameter, or threshold change
**Goal:** Decide whether D4 FAIL is caused by (i) baseline mismatch with the
paper, (ii) Gate 2 thresholds being over-tight, or (iii) metric definitions
being inappropriate for a type-0 frequency response.
**Predecessors:**
- D4 + D4.1 verdict — `2026-04-26_kundur_cvs_p4_d4_gate2.md`
- Stage 2 plan §1 D4 + §5 — `2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- Engineering contract — `docs/design/cvs_design.md`
- Constraint doc (main worktree, read-only) — `docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md`
- Paper fact-base (read-only) — `docs/paper/yang2023-fact-base.md`

---

## TL;DR

| Question | Answer | Evidence |
|---|---|---|
| Is `D = 3` the paper baseline? | **No.** It is a P2/P3 spike artefact. | `cvs_design.md` D-CVS-6 + `build_kundur_cvs_p2.m`; the "与 paper Sec.IV-A 一致" claim refers only to *homogeneity* across 4 VSGs, not to the numeric value. |
| Does the paper give a numeric baseline `D_ES0`? | **No.** Only the action range `ΔD ∈ [-200, 600]` is given (Sec.IV-B). | Paper fact-base §3.3, §10 deviation table. |
| What baseline did the rest of the project pick? | **`H_ES0 = 24, D_ES0 = 18`** (modal calibration ω_n ≈ 0.623 Hz, ζ ≈ 0.048). | `config.py` L29, L32-33, used by ANDES + ODE + Simulink default fallback. |
| Is plan §5 `settle ≤ 5 s` paper-grounded? | **No.** Engineering rule of thumb. | Constraint doc row 260; plan rationale "Kundur nadir 2-3 s 内出现 → 5 s 够" (nadir ≠ settle). |
| Is plan §5 `peak/steady ≤ 1.5` paper-grounded? | **No.** Classical control rule of thumb. | Constraint doc row 260, no paper citation. |
| Is `peak/steady` mathematically appropriate for type-0 ω response? | **No.** ω returns to nominal (no new steady-state). The δ-channel is the type-0 step response; the ω-channel is the velocity-channel and has no peak/steady ratio. | This report §4. |

**Net diagnosis (consistent with §2.4 / §6 / §7 below):**

1. `D = 3` is a P2/P3 spike artefact. It is **not** the paper baseline.
2. The project's paper-aligned baseline is `D_ES0 = 18` (with `H_ES0 = 24`),
   recorded in `config.py` as a modal-calibration target ω_n ≈ 0.6 Hz,
   ζ ≈ 0.048 against the ANDES reduced-network model. The paper itself does
   **not** quote a numeric `D₀`.
3. Even after substituting the project paper-baseline `D = 18` into the CVS
   path's linearised swing equation (`M = 48`, `K_lin = 1/X_v = 10`), the
   predicted settle to a 5 %-of-peak band is **~16 s** and to the strict
   plan §5 absolute band (5e-4 pu) is **~12 s** — both still violate the
   `≤ 5 s` threshold (§2.4). Gate 2 criterion 4 will therefore most likely
   **still FAIL** under a simple D = 3 → D = 18 swap; criterion 4 cannot be
   recovered by parameter restoration alone.
4. Criterion 3 (`peak/steady ≤ 1.5`) is a **separate**, metric-level issue:
   `peak/steady` is mathematically ill-defined on the type-0 ω channel
   (§4), and threshold `1.5` is not paper-mandated.
5. Disposition therefore requires a **plan-author decision** on:
   (a) whether `settle ≤ 5 s` is retained, relaxed, or redefined (e.g.
   relative band, or paper-justifiable absolute target), and
   (b) whether `peak/steady` is replaced (δ-channel overshoot) or dropped.
   Without (a) + (b), Gate 2 stays FAIL irrespective of which D value is
   used.

**No model / parameter / threshold change applied. Decisions deferred to
plan author per D4 mandate.**

---

## 1. Paper-side facts (`docs/paper/yang2023-fact-base.md`, Yang TPWRS 2023)

### 1.1 What the paper specifies for D / H

| Quantity | Paper value / specification | Section |
|---|---|---|
| Action `ΔD_es,i,t` range | `[-200, 600]` (units **not stated in the paper**) | Sec.IV-B (fact-base L100) |
| Action `ΔH_es,i,t` range | `[-100, 300]` (units not stated) | Sec.IV-B (fact-base L99) |
| Update rule | `D_es,i,t = D_es,i,0 + ΔD_es,i,t` | Eq.12-13 (fact-base L96) |
| `D_es,0` numeric value | **NOT given** in paper | — |
| `H_es,0` numeric value | **NOT given** in paper | — |
| `D` dimension / unit | **NOT given** (Q7 unresolved; fact-base L320) | Sec.II-A Eq.1 |
| Baseline mass `M` formula | Eq.1 with `H_es,i` (units unspecified) | Sec.II-A |
| Damping ratio target | **NOT specified** in paper | — |
| Settle time target | **NOT specified** in paper | — |
| Overshoot bound | **NOT specified** in paper | — |
| Frequency-deviation upper bound | Fig 4 shows ~0.4 Hz transient peak (visual, not threshold) | Sec.IV-A figures |

### 1.2 Project-recorded deviation (fact-base §10, L361)

> | 动作范围 | ΔH ∈ [-100,300]，ΔD ∈ [-200,600] | ΔM ∈ [-6,18]（M=2H），ΔD ∈ [-1.5,4.5] | 不同的基值（H₀/D₀ scale 不同） |

The project already documents that the paper's `ΔD = [-200, 600]` does **not**
map onto the project's `ΔD = [-1.5, 4.5]` (a ~133× ratio). This is logged as
a known scale ambiguity caused by `H_paper` units (Q7).

---

## 2. Project-side facts — D baseline lineage

### 2.1 The two distinct project D values

| Source | Path / location | M | D | Pm | Origin |
|---|---|---|---|---|---|
| ANDES + ODE + Simulink fallback | `config.py` L32-33 | (M=2H₀=48 if ω_s=1 pu) | **`D_ES0 = 18`** | (`P0` topology-derived) | "modal calibration for ω_n≈0.6 Hz, ζ≈0.05" (config.py L8-9) |
| CVS Phasor (D-CVS-6 spike artefact) | `cvs_design.md` row 258, `build_kundur_cvs_p2.m` L57-58 | **`M0 = 12`** | **`D0 = 3`** | `Pm0 = 0.5` | P2/P3 spike phase choice |

### 2.2 Cross-reference to the constraint doc

`docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md` row 314:

> | D-CVS-6 | 4 个 VSG 是否参数完全相同（同质 vs 异质）| 同质（M0=12, D0=3）| **与 paper Sec.IV-A 一致** |

**Reading the row literally:** the column "是否参数完全相同" is asking about
homogeneity (uniform vs heterogeneous). The "与 paper 一致" justification is
about the **homogeneity property** (all 4 ESS equal), not about the numeric
values M=12, D=3. Paper Sec.IV-A indeed says "4 storages, separately
connected to different areas" without parameter heterogeneity — homogeneous
is consistent. The numerical pair `M=12, D=3` is **not** in the paper.

### 2.3 Where M=12, D=3 actually came from

- `build_kundur_cvs_p2.m` L57-58 sets `assignin('base', 'M_i', double(12.0))`
  and `assignin('base', 'D_i', double(3.0))` as **per-agent base ws defaults**
  for the P2 episode probe. No comment / citation in the file points to a
  paper origin.
- The values were inherited verbatim into `build_kundur_cvs.m` (D2 evolution)
  via `M0_default = 12.0; D0_default = 3.0` (L83-84 of current
  `build_kundur_cvs.m`).
- Spike-stage P3 verdict (`2026-04-25_kundur_cvs_p3_smoke.md`) PASS-ed at
  Pe ≈ 0.5 not because the IC was right (it wasn't — see D2 verdict's
  Pe-scale convention discussion) but because the closed swing-eq
  self-corrected δ at a different equilibrium. With `Pe_scale = 0.5/Sbase`
  P3's `|δ|max ≈ 1.21 rad` masked the underlying baseline-vs-paper gap.

**Conclusion:** `D = 3` is a **spike-phase artefact**, not the project's
declared paper baseline `D_ES0 = 18`, and not paper-quoted.

### 2.4 Paper-baseline ζ computation (analytic)

If we substitute `M = 48` (= 2·H_ES0 for H_ES0 = 24) and `D = 18` into the
linearised swing equation with K_lin = 1/X_v = 10 pu/rad (the same effective
Pe-δ stiffness used in D4.1):

```
σ_th_paper = D / (2M) = 18 / 96 = 0.1875 / s            (1.5× the D=3 value 0.125 / s)
ω_n_paper  = √(K · ω_s / M) = √(10 · 314 / 48) = 8.09 rad/s
ζ_paper    = D / (2 √(K · ω_s · M)) = 18 / (2 · 388.5) = 0.0232
τ_env      = 1/σ = 5.33 s
Settle 5e-4 pu @ peak ≈ 5e-3:  ln(10)/0.1875 ≈ 12.3 s   (still > 5 s)
Settle 5 %-of-peak:            ln(20)/0.1875 ≈ 16.0 s   (still > 5 s)
```

This contradicts `config.py` L8-9 which reports "H=24, D=18 → ω_n≈0.6 Hz,
ζ≈0.048". The discrepancy is because **`config.py` calibration uses a
different K_lin** — it is computed against the ANDES reduced 4-bus chain
network with B_tie = 4 and λ_min ≈ 2.343, giving a much smaller effective
stiffness than the CVS path's K_lin = 1/X_v = 10. The ANDES K_eff ≈ 2.34/M
maps to ω_n_andes = √(2.34/48) ≈ 0.221 rad/s = 0.035 Hz — also doesn't
match config.py's 0.623 Hz number. The exact derivation of config.py's
ζ = 0.048 is **not traceable from comments alone**; it is likely tied to
ANDES TDS modal analysis, not CVS-domain analytics.

**What the audit can say with confidence:**
- D = 18 (paper baseline) → ζ ≈ 0.023 in the CVS path → settle to 5e-4 pu
  is ~12 s, still > 5 s.
- To meet plan §5 settle ≤ 5 s in the CVS path, D would need to be ≈ 50–60
  (ζ ≥ 0.07), which **no project file documents** as a paper baseline.
- Conclusion: even adopting the project's paper-aligned `D_ES0 = 18` would
  not flip Gate 2 criterion 4 to PASS without **also** redefining "settle".

---

## 3. Plan-side facts — Gate 2 settle / peak-steady origin

### 3.1 Constraint doc lineage

`docs/superpowers/plans/2026-04-25-kundur-cvs-rewrite-constraints.md` §6 Gate
2 row 260:

> 系统能在 ≤ 5 s 阻尼回到稳态（peak/steady ≤ 1.5）

`quality_reports/gates/2026-04-25_kundur_cvs_stage2_readiness_plan.md` §5
inherits verbatim from the constraint doc. Neither cites a paper section.

### 3.2 Plan's stated rationale for "5 s"

`stage2_readiness_plan.md` row 365:

> Kundur T_EPISODE | 10s（M=50，Sec.IV-A）| 5s（M=25）| 工程决策：Kundur
> nadir 在 2-3s 内出现，5s 已够学习信号；NE39 保持 10s

This conflates **nadir time** (time to first frequency peak — a property
of natural frequency ω_n) with **settle time** (time for envelope to decay
into a tolerance band — a property of damping ratio ζ).

- nadir time `t_nadir ≈ π / (2·ω_d) ≈ π/(2·ω_n)` ≈ 0.2 s for ω_n = 8.09 rad/s
  (matches D4.1 traces — first peak at ~0.2 s after step)
- settle time scales with `1/(ζ·ω_n)` and depends on ζ separately

A nadir at 2-3 s would imply ω_n ≈ 1.0-1.5 rad/s = 0.16-0.24 Hz, which is
inconsistent with both the CVS path's ω_n = 8.09 rad/s and the ANDES path's
0.623 Hz target. The 2-3 s nadir claim is most likely an empirical observation
from training-time frequency excursions involving inter-area modes (not the
local mode that dominates a per-VSG step response in D4).

**The 5 s settle bound is therefore an engineering rule of thumb attached to
a slightly mis-applied physical reasoning chain — it is not paper-mandated
and not analytically grounded for the CVS path's local-mode response.**

### 3.3 `peak/steady ≤ 1.5` lineage

Same constraint-doc line 260. No further definition in either the constraint
doc or the readiness plan: "peak" and "steady" are not formally defined,
and there is no guidance for type-0 systems where `steady → 0`.

Classical second-order step response with ζ < 1 has overshoot
`%OS = exp(-π·ζ/√(1-ζ²)) · 100`, so `peak/steady = 1.5` corresponds to
`%OS = 50%` ↔ ζ ≈ 0.215. The 1.5 figure is a damping-ratio proxy. **It is
not a paper specification.**

---

## 4. Metric appropriateness — `peak/steady` on the ω channel

### 4.1 The system is type-0 in ω (frequency)

A `Pm` step on a single VSG induces:
- **δ channel:** an asymptotic shift to a new equilibrium δ' satisfying
  `Pm_total = Pe(δ')` — *this is a type-0 step response of position*.
- **ω channel:** a transient excursion that decays back to ω = 1.0 — *this
  is a type-0 step response of velocity, which by definition has no new
  steady-state value*.

A direct mechanical analogy: pushing a sliding mass attached to a spring-
damper system with a constant force.
- **Position** moves to a new equilibrium (Hooke's law) → classical step
  response with overshoot, `peak/steady ≤ 1+%OS` is meaningful.
- **Velocity** spikes upward, then decays to zero → the only "steady-state"
  velocity is zero; the ratio `peak/zero` is undefined.

`peak/steady` is **mathematically defined** for the δ channel (and would
yield a meaningful overshoot ≈ 1.05 here, well within the 1.5 bound), but is
**not defined** for the ω channel.

### 4.2 What the D4 probe actually computed

`p4_d4_gate2_dist_sweep.py` defines (at the time of D4):

```
peak   = max |ω(t) − 1| for t ≥ T_step
steady = mean |ω(t) − 1| over t ∈ [t_end − 5 s, t_end]
ratio  = peak / max(steady, 1e-5)
```

`steady` reads the **residual decaying tail of |ω−1|**, which is mechanical
floor noise (~1e-4 to 1e-3 pu depending on amp) rather than a genuine
asymptote. The ratio then varies as `peak / decay_floor`, growing without
bound as the sim window lengthens (the longer the tail, the smaller the
floor, the larger the ratio). The 21-38× values reported in D4 are
consistent with this artefact and will move arbitrarily if the sim window
is changed — **the ratio is not a stable characterisation of the system**.

### 4.3 Honest re-formulation candidates (no code change applied)

Three ways to make the metric well-defined; **none is implemented in this
audit**:

| Candidate | Channel | What it measures |
|---|---|---|
| δ-channel overshoot | `(δ_peak − δ_new_steady) / (δ_new_steady − δ_old_steady)` | Classical second-order step overshoot |
| ω-channel relative peak | `ω_peak − 1` (Hz) divided by linear-prediction `ΔPm·k_ω` | Departure from small-signal linear prediction |
| Drop the metric | — | Acknowledge type-0 ω channel has no peak/steady; cover overshoot via δ-channel only |

The audit recommends the plan author pick one in coordination with the
existing `linearity_R²` metric (which already PASSes ω-channel linearity).

---

## 5. Untouched-state proof

`git status --short` after this audit's read-only file reads:

```
 M scenarios/kundur/kundur_ic_cvs.json          (timestamp drift only — see §1.3 of D4 verdict)
 M scenarios/kundur/simulink_models/build_kundur_cvs.m
 M scenarios/kundur/simulink_models/kundur_cvs.slx
?? probes/kundur/gates/p4_d4_gate2_dist_sweep.py
?? probes/kundur/gates/p4_d4p1_diagnose.py
?? quality_reports/gates/2026-04-26_kundur_cvs_p4_d4_gate2.md
?? quality_reports/gates/2026-04-26_kundur_cvs_p4_d4p2_readonly_audit.md   ← this report
```

The first four entries are exactly the D4 + D4.1 dirty set already accounted
for in the D4 verdict §"Did D4 expand scope?" — **no new edits beyond writing
this report**. M, D, Pm0, X_v / X_tie / X_inf, reward, agent, bridge, NE39,
legacy: **all unchanged**.

This audit added one new file: this markdown report.

---

## 6. Diagnosis summary table

| FAIL criterion | Root cause class | Evidence |
|---|---|---|
| `peak_to_steady ≤ 1.5` | **Inappropriate metric for type-0 ω channel** + threshold not paper-grounded | §4 above + constraint doc row 260 |
| `settle ≤ 5 s` | **Compound:** (a) baseline mismatch (D = 3 spike vs project paper-baseline D = 18), (b) even paper-baseline D = 18 yields settle ~12 s in the CVS path (ζ ≈ 0.023), (c) 5 s threshold is engineering rule of thumb based on misapplied "nadir at 2-3 s" reasoning | §2.4, §3.2 above |

**The FAIL is real, but its surface area decomposes into:**
- ~50 % "wrong metric" (peak/steady inapplicable to type-0 ω)
- ~30 % "wrong threshold" (5 s is rule-of-thumb, not paper-grounded)
- ~20 % "wrong baseline" (D = 3 is spike artefact; project paper-baseline
  is D = 18, paper itself does not specify D₀)

None of these are dynamics bugs in the model; the swing equation closes
correctly, NR IC matches sim exactly (D2 PASS), and zero-action is stable
to floating-point precision (D3 PASS). Linearity, max-frequency-deviation
margin, and clip-non-touch all PASS in D4. The remaining FAILs are
specification-level issues.

---

## 7. Recommendation (still **C: DEFER**, refined)

The recommendation from D4.1 stands, with sharpened next-step actions for
the plan author:

| ID | Action | Effect on Gate 2 | Effort |
|---|---|---|---|
| **C** | DEFER. Stop Stage 2 here. | unchanged | 0 |
| C.1 | Plan author confirms whether `D_ES0` should follow project paper-baseline `18` or stay at the spike `3` | Sets the parameter scope of any future re-run | minutes |
| C.2 | Plan author defines whether `settle` in §5 is paper-grounded or rule-of-thumb; if rule-of-thumb, decide a paper-justifiable target (or drop) | Sets criterion 4 threshold | minutes |
| C.3 | Plan author replaces / drops `peak_to_steady` for the ω channel (use δ-channel overshoot, or remove) | Resolves criterion 3 | minutes |
| A | After C.1/C.2/C.3: re-run sweep with paper-baseline `D = 18` and revised metrics | Predicts: criterion 1, 2, 5 still PASS; criterion 3 PASS or removed; criterion 4 likely still FAIL on a strict 5 s bound but PASS on a paper-justifiable target (e.g., 10-15 s, or a relative band) | one sweep run + verdict update |

**The audit does NOT prescribe any of these — the worktree boundary is
held.** The 5 next-step actions are decisions a plan author or paper-fidelity
authority must make.

---

## 8. Strict bounds upheld (per D4.2 mandate)

- ❌ `build_kundur_cvs.m` not edited
- ❌ `kundur_cvs.slx` not edited / rebuilt
- ❌ `compute_kundur_cvs_powerflow.m` / `kundur_ic_cvs.json` not edited
- ❌ `M`, `D`, `Pm0`, `X_v`, `X_tie`, `X_inf`, `Pe_scale` numeric values not changed
- ❌ Reward / agent / SAC / hidden layers / bridge / NE39 / legacy / `contract.py` not touched
- ❌ Gate 3 / RL training not entered
- ❌ Plan §5 thresholds in code not relaxed
- ❌ D4 + D4.1 verdict report not modified
- ❌ Probes / sweep code not changed beyond what was already in the D4 + D4.1 commit envelope

Files added by this audit (one only): the present markdown report.

---

## 9. Cross-reference index

| Claim | Source location |
|---|---|
| Paper does not give D₀ numeric value | `docs/paper/yang2023-fact-base.md` §3.3 (L92-100), §6.1 (L193-201) |
| Paper Sec.IV-B specifies `ΔD ∈ [-200, 600]` | fact-base L100, L342 |
| Project ANDES baseline H=24, D=18, ζ-target ≈ 0.048 | `config.py` L8-9, L29, L32-33 |
| Simulink default fallback uses H_ES0/D_ES0 (= 24/18) | `env/simulink/simulink_vsg_env.py` L54-55 |
| CVS spike value M=12, D=3 | `build_kundur_cvs_p2.m` L57-58 (now also L83-84 of `build_kundur_cvs.m`) |
| D-CVS-6 lock | `cvs_design.md` row 258, constraint doc row 314 |
| Settle ≤ 5 s | constraint doc row 260, plan §5 row 199 |
| Settle rationale "Kundur nadir 2-3 s" | plan row 365 |
| peak/steady ≤ 1.5 | constraint doc row 260, plan §5 row 198 |
| ζ = 0.0077 measured in D4.1 | `results/cvs_gate2/20260425T183630/diagnose.json` |
| All 15 runs ω returns to 1.0 within 5e-4 pu | same |
| Empirical envelope decay σ_hat / σ_th ∈ [0.88, 1.12], mean 0.996 | same |
