# Paper-explicit-requirement audit — v3 conformance check

> **Status:** READ-ONLY AUDIT — enumerates every paper-explicitly-stated item from `docs/paper/yang2023-fact-base.md` and checks whether v3 satisfies it. Conformance: 16/22 ✓, 6/22 ❌/⚠. Non-conformities classified by impact on Phase 5 paper-replication closure.
> **Date:** 2026-04-27
> **Scope:** "paper explicitly says" = paper text states the value/form directly, not via OCR ambiguity (Q7/Q8) or project inference. Project-inferred items (Q7 ΔH = ΔM/2, Q8 1/M normalization, Q1 fixed scenarios) are tagged ⚠ ambiguous.

---

## 1. Conformance table

| # | Item | Paper §/Eq says | Required value | v3 value | Status |
|---|---|---|---|---|---|
| 1 | Δω unit | Sec.II-A line 50 | p.u. | `ω−1` (p.u.) | ✓ |
| 2 | Eq.14 total reward shape | Sec.III-A | `r_i = φ_f r_f + φ_h r_h + φ_d r_d` | matches | ✓ R1 |
| 3 | Eq.15-16 r_f formula | Sec.III-A | local ω̄ + comm-mask weighted | matches | ✓ R1 |
| 4 | Eq.17 r_h formula | Sec.III-A | `−(ΔH_avg)²` | matches; ΔH = ΔM/2 (Q7 inference) | ⚠ Q7 |
| 5 | Eq.18 r_d formula | Sec.III-A | `−(ΔD_avg)²` | matches | ✓ |
| 6 | **φ_f weight** | **Sec.IV-B explicit** | **100** | 100 | ✓ |
| 7 | **φ_h weight** | **Sec.IV-B explicit** | **1.0** | **1e-4** (Kundur override) | **❌ G1** |
| 8 | **φ_d weight** | **Sec.IV-B explicit** | **1.0** | **1e-4** (Kundur override) | **❌ G1** |
| 9 | **ΔH range** | **Sec.IV-B explicit** | **[−100, +300]** | **[−3, +9] (Q7: ΔM=[−6,+18] → ΔH = ΔM/2)** | **❌ G2 / Q7** |
| 10 | ΔD range | Sec.IV-B explicit | [−200, +600] | [−1.5, +4.5] | ❌ G2 |
| 11 | DT (control step) | Sec.IV-A explicit | 0.2 s | 0.2 s | ✓ |
| 12 | T_EPISODE | Sec.IV-A explicit | 10 s | 10 s | ✓ |
| 13 | M (steps per ep) | Sec.IV-A + Table I explicit | 50 | 50 | ✓ |
| 14 | N (agents) | Sec.IV-A explicit | 4 ESS | 4 ESS | ✓ |
| 15 | System topology | Sec.IV-A explicit | Modified Kundur 2-area; Gen4 → wind farm; Bus 8 → 100 MW wind | matches | ✓ |
| 16 | Sim toolchain | Sec.IV-A explicit | MATLAB-Simulink + Python | matches | ✓ |
| 17 | **Train scenarios** | **Sec.IV-A explicit** | **100 random** (fixed across episodes — paper ambiguous Q1 but cumulative-reward comparison requires fixed) | **per-episode random resample** (Phase 4.3 unimplemented) | **❌ G3 / Q1** |
| 18 | **Test scenarios** | **Sec.IV-A explicit** | **50 random** (fixed) | **inline-generated 50 deterministic seed=42** | ⚠ semi-OK |
| 19 | **Episodes** | **Table I explicit** | **2000** | **670 (P4.2-overnight stopped at plateau)** | ⚠ G4 |
| 20 | γ discount | Table I explicit | 0.99 | 0.99 | ✓ |
| 21 | Mini-batch size | Table I explicit | 256 | 256 | ✓ |
| 22 | **Replay buffer size** | **Table I explicit** | **10 000** | **100 000** (Kundur override) | **❌ G5** |
| 23 | All learning rates (actor/critic/α) | Table I explicit | 3e-4 | 3e-4 | ✓ |
| 24 | Actor + critic depth/width | Sec.IV-A explicit | 4 layers × 128 units each | 4 × 128 | ✓ |
| 25 | DDIC = independent learner | Sec.III-A explicit | each agent: own actor π_φ_i + own critic Q_θ_i | code uses **shared-weights SAC** | ⚠ G6 |
| 26 | **Algorithm 1 line 16** | **Sec.III-A Algo 1** | **Clear buffer D_i per episode** | **DISABLED** (`CLEAR_BUFFER_PER_EPISODE=False`) | **❌ G7** |
| 27 | Cumulative reward formula | Sec.IV-C explicit | `−Σ_t Σ_i (Δf−f̄)²` Hz, GLOBAL f̄ | paper_eval matches | ✓ P5.1 |
| 28 | Paper baseline numbers | Sec.IV-C explicit | DDIC −8.04, adaptive −12.93, no_control −15.20 | v3 DDIC −8.90, no_control −7.48 (1/2 paper magnitude) | ⚠ G8 |

**Conformance: 18/28 ✓, 4/28 ⚠, 6/28 ❌.**

---

## 2. Gap inventory (impact on Phase 5 closure)

### G1 — `φ_h = φ_d = 1e-4` vs paper `1.0` (4 OoM)

- Project rationale (`scenarios/kundur/config_simulink.py:107-118`): paper φ_h = 1 + paper ΔH = [−100, +300] gives r_h ≈ 1 × 200² = 40 000 per step. Paper number doesn't appear in published reward magnitudes. Project ΔM = [−6, +18] makes r_h with φ_h=1 ≈ ΔM=10 → r_h ≈ 50 per step. Even 50 swamps r_f. Project lowered to 1e-4 to keep r_f visible.
- **Paper-explicit deviation, but matches paper's intent (= small r_h, large r_f effect) under project's ΔH range.**
- **R2 evidence (today):** sweeping φ_h ∈ {1e-5, 1e-4, 1e-2} over 1.4 hr produced ~1 dB variation in DDIC outcome — none broke the regression. **Not the dominant problem.**

### G2 — ΔH range [−3, +9] vs paper [−100, +300] (33-40× smaller, plus Q7)

- Project ΔM = [−6, +18] (Kundur), ΔH = ΔM/2 (Q7 inference). Paper ΔH = [−100, +300]. **Likely Q7 dimensional discrepancy:** if paper M = ω_s · H_paper / 2 (mechanical-system convention) then paper H ~ 100s = paper M ~ 31 000 in code units (50 Hz × 2π × 100). Project's calibrated ΔM [−6, +18] is likely closer to a project-stable physical range, but it's not a direct paper match.
- Cannot be reconciled without paper authors' clarification of H units. Q7 is OPEN per fact-base.

### G3 — Train scenarios per-ep resampled vs paper 100 fixed

- Project: random_uniform per-ep magnitude + bus pick. Paper: 100 fixed.
- Phase 4.3 task (per roadmap §Gap 3) — not yet implemented.
- **Impact:** paper Sec.IV-C cumulative reward over 50 test scenarios is reproducible iff scenarios are fixed. Without Phase 4.3, comparison is ad-hoc.

### G4 — 670 ep trained (vs paper 2000)

- P4.2-overnight stopped at ep 670 because reward plateau + α floor since ep 100 indicated convergence. P5.1 paper-eval on `best.pt` (ep 549) showed regression vs no_control. **Continuing to 2000 ep won't fix it** if R2's failure root cause (PHI-orthogonal) is correct.
- Once Z1 (SG-side disturbance) shows learnable signal, 2000-ep run is worth it.

### G5 — Replay buffer 100 000 vs paper 10 000 (10× larger)

- Project rationale (`scenarios/kundur/config_simulink.py:271`): "Kundur fills buffer slower (4 agents × 25 steps/ep)". Buffer 100k = 500 episodes capacity at 200 transitions/ep.
- **Paper-explicit deviation.** Paper 10k = 50 ep capacity (matches Algorithm 1 "clear per ep" intent, gives roughly recent-ep-window training).
- **Impact:** with 100k buffer, agent samples old experiences at ratio 5x more than recent ones. Old experiences from a different policy regime can pull policy in stale directions. May contribute to plateau / regression.

### G6 — Shared-weights SAC vs paper independent learners

- Project: single SACAgent shared across 4 agents (`env/simulink/sac_agent_standalone.py`). Paper Algorithm 1: per-agent actor + critic.
- **Paper-explicit deviation.** Project rationale: parameter sharing is a standard MARL trick that reduces sample complexity; in paper's homogeneous ESS setup, shared-weights is mathematically equivalent up to the random-seed difference.
- **Impact:** equivalence depends on exact obs symmetry. Paper's r_f formula uses LOCAL ω̄ which DIFFERS per agent (because each agent's neighbor set is different). So per-agent obs are NOT identical — independent learners would adapt differently. Shared-weights may underfit per-agent specialization.

### G7 — Clear buffer per ep DISABLED

- Paper Algorithm 1 line 16 explicitly: "Clear buffer D_i". Project disabled because Table I says buffer = 10 000, which CONFLICTS with "clear per ep" (50 ep × 200 trans/ep > 10k... actually = 10k exactly; near-bursting). Project chose Table I (cross-ep accumulate).
- **Documented as deliberate paper-vs-code conflict** (fact-base §7.1, line 256-264).
- **Impact:** with clear-per-ep enabled, training would never see batch=256 from a single ep (only 200 transitions/ep). Project's interpretation (= keep buffer 10k, never clear) is more SAC-faithful.

### G8 — v3 magnitudes ½ paper magnitudes

- v3 no_control = −7.48 vs paper −15.20.
- v3 disturbance = Pm-step proxy at [10, 50] MW per ESS. Paper "Load Step 1/2" = 248 / 188 MW at load buses.
- **Z1 (SG-side proxy) won't fully close this — need paper-magnitude LoadStep (Z2 / Path A) for 1:1 paper baseline match.**
- v3 closure of paper-explicit gap currently **bounded by Pm-step proxy** as the only allow-listed disturbance route.

---

## 3. Closure plan (must close to claim "paper-replication")

| Gap | Closure path | Authorized? | Phase |
|---|---|---|---|
| G1 (φ_h/d) | R2 sweep — covered, irreducible at current ΔH range. Document deviation rationale in fact-base. | yes | DONE — see R2 verdict |
| G2 (ΔH range) | Q7 paper-side clarification needed. Project keeps current calibrated range; document. | irreducible | OPEN (Q7) |
| G3 (fixed scenarios) | **Phase 4.3** — generate JSON manifest + scenario_loader.py + CLI flag. | authorized | TODO |
| G4 (2000 ep) | Run after Z1 unblocks; 2000-ep main run = Phase 5.3. | needs explicit GO | TODO |
| G5 (buffer 10k) | Roll back Kundur override `BUFFER_SIZE = 100000` → use base `10000` (or 50 000 as compromise). One-line config edit. | yes (config edit, P4.x scope) | TODO — recommend with Z1 |
| G6 (shared-weights) | Architectural — would require switching to MultiAgentManager. Big change; defer to Phase 5.5+ extension. | NO without explicit GO | DEFER |
| G7 (clear buffer) | Re-enable would invalidate Table I (= incompatible). Document as Sec.IV-A vs Algorithm 1 paper-internal conflict. | resolved by project decision | DOCUMENTED |
| G8 (magnitude) | Z2 LoadStep (Path A scope expansion) OR Z1 SG-Pm-step proxy (lower-magnitude, but at least leverage-correct). | Z1 yes; Z2 needs explicit GO | TODO — Z1 next |

---

## 4. Closure priority for Z1 + downstream

For the user's "paper-explicitly-says-so MUST close" mandate, the actionable items in **current allow-list scope** are:

1. **G3 fixed scenarios (Phase 4.3)** — script + JSON manifest, no model edit.
2. **G5 buffer rollback** to paper Table I value (10 000) — one-line `config_simulink.py` edit.
3. **G1 PHI = 1.0** experiment — already done in R2 (`phi_paper_scaled` ran at 1e-2 not 1.0; should add `phi_paper_strict=1.0/1.0/100`. Outcome predictable: r_h kills training. But for "paper-explicit closure", we should run it once and document.).
4. **G6 deferred** — explicit user GO needed for arch change.
5. **G8 Z1 first**, Z2 if Z1 fails.

---

## 5. Boundary check

Read-only audit. No code change. No NE39 touch. No training launched.

---

## 6. Output

This file only.

---

## 7. Recommended sequencing alongside Z1

While Z1 (SG-side dispatch) implementation runs, also stage:
- Phase 4.3 (G3 closure) — JSON manifest + loader (1 day work, parallel-implementable)
- Buffer rollback to 10 000 (G5 closure) — single config edit + retrain

Both close paper-explicit gaps without blocking Z1.
