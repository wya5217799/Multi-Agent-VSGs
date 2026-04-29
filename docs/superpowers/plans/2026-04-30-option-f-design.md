# Option F Design: Multi-Point Pm-Step Disturbance Scheduling

**Date:** 2026-04-30
**Status:** DESIGN ONLY — no training, no checkpoint, no .slx/build/reward/obs/SAC changes
**Scope:** env disturbance scheduling layer only (`disturbance_protocols.py`, `_apply_disturbance_backend`, `scenario_loader.py`, `paper_eval.py`, `config_simulink.py`)
**Prerequisite:** Probe B-ESS verdict (`results/harness/kundur/cvs_v3_probe_b_ess/PROBE_B_ESS_VERDICT.md`) determines whether ES2 can be included
**Supersedes:** N/A (first Option F design iteration)

---

## 0. Pre-read (mandatory)

1. `results/harness/kundur/cvs_v3_probe_b/PROTOCOL_GRADIENT_DEGENERACY_STOP_VERDICT.md` — locks the constraint Option F is meant to break
2. `results/harness/kundur/cvs_v3_probe_b/PROBE_B_STOP_VERDICT.md` — per-agent response data from G1/G2/G3 sign-pairs (foundation for superposition reasoning below)
3. `results/harness/kundur/cvs_v3_probe_b_ess/PROBE_B_ESS_VERDICT.md` — ES2 swing-eq channel verdict; required input
4. `docs/paper/kundur-paper-project-terminology-dictionary.md` §3 row D-T6 — ES2 universally dead under SG-side
5. `docs/paper/disturbance-protocol-mismatch-fix-report.md` §2.4 (Option A multi-point Pm-step previous sketch)
6. `scenarios/kundur/disturbance_protocols.py::EssPmStepProxy` — current single-target adapter (Option F extends this without breaking it)

---

## 1. Goal

**Quantitative:** Every paper_eval scenario excites ≥ 2 ESS agents above
1e-3 Hz per-agent peak |Δf|. Aggregate target: average **≥ 3 / 4 agents
respond** (vs current 1.33 / 4 baseline measured 2026-04-30).

**Qualitative:** Provide ES2 with a non-zero r_f gradient in some
non-trivial fraction of scenarios — explicitly NOT 0 % as today.

**Non-goal:** Reproducing paper's `-8.04 / -15.20` cumulative reward
numerically. That requires either Q8 (paper unit ambiguity) resolution
or Option E (CCS at Bus 7/9 network LoadStep), neither in Option F scope.

---

## 2. Hard scope boundary

ALLOWED to modify:
- `scenarios/kundur/disturbance_protocols.py` — extend `EssPmStepProxy` and/or add new adapter classes for multi-point dispatch
- `scenarios/kundur/scenario_loader.py::scenario_to_disturbance_type` — add routes for new disturbance_type strings
- `scenarios/kundur/config_simulink.py::KUNDUR_DISTURBANCE_TYPES_VALID` — register new types
- `evaluation/paper_eval.py` — add `--disturbance-mode multi` CLI option, or recognize new `disturbance_kind` values in scenario manifests
- `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` — accept multi-point disturbance_type strings (delegation to adapter; no new logic in env itself)
- `scenarios/kundur/workspace_vars.py` — only if a new workspace var family is required (probably not — multi-point dispatch reuses existing `PM_STEP_AMP[1..4]` and `PM_STEP_T[1..4]`)

DO NOT modify:
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`
- `scenarios/kundur/simulink_models/kundur_cvs_v3.slx`
- `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat`
- `scenarios/kundur/kundur_ic_cvs_v3.json`
- `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m`
- `engine/simulink_bridge.py`, `engine/matlab_session.py`, `slx_helpers/**`
- `env/simulink/_base.py` (reward formula)
- `env/simulink/sac_agent_standalone.py`, `agents/multi_agent_sac_manager.py`
- `evaluation/paper_eval.py` reward computation (only CLI / dispatch routing added)

---

## 3. Multi-point dispatch candidates

All candidates use the existing `EssPmStepProxy` workspace-var path
(`PM_STEP_AMP[i]` Constant blocks proven LIVE per Probe B G1/G2/G3 +
the existing `pm_step_proxy_bus7/9` runs). The only change is **how
many `i` get a non-zero amp simultaneously, and how the magnitude is
distributed**.

### 3.1 Candidate F1 — All-4 simultaneous, equal magnitude

```python
EssPmStepProxy(target_indices=(0, 1, 2, 3))
# amp_per_vsg = magnitude_sys_pu / 4
```

- **Predicted response (superposition under linearization assumption):**
  ES1 + ES3 + ES4 each get ~25 % of paper-magnitude direct injection
  (each agent's own swing-eq Pm input). **ES2 contribution depends on
  Probe B-ESS verdict.**
- **Pros:** Simplest possible Option F. Paper-magnitude conserved
  (sum = magnitude_sys_pu).
- **Cons:** Single mode-shape excitation (in-phase, 4 agents fire same
  direction same time). Network mode-shape pattern that paper's RL is
  supposed to learn won't appear — all 4 agents see identical "uniform
  Pm bump" rather than differential disturbance.
- **Falsifiable expected outcome:** all 4 ES respond at ~25 % of
  per-agent paper-magnitude single-target response; cum_unnorm should
  be similar magnitude to G1+G2+G3 random average; per-agent r_f
  contribution roughly equal across 4 (no agent dominates).

### 3.2 Candidate F2 — Multi-point asynchronous (paper's mode-shape mimic)

```python
class MultiPointPmStepProxy:
    def __init__(self, target_indices, amp_weights, time_offsets):
        # e.g. target_indices=(0, 3), amp_weights=(0.6, 0.4),
        #      time_offsets=(0.0, 0.4)  # ES4 fires 400 ms after ES1
        ...

    def apply(...):
        for i, w, dt in zip(target_indices, amp_weights, time_offsets):
            bridge.apply_workspace_var(PM_STEP_AMP[i], magnitude_sys_pu * w)
            bridge.apply_workspace_var(PM_STEP_T[i], t_now + dt)
```

- **Predicted response:** ES1 fires first → ES1 / network ringing →
  ES4 fires 400 ms later → 4-agent system never settles to single
  mode-shape. Closer to paper LoadStep's mode-shape signature where
  4 agents have non-coincident peak times.
- **Pros:** Closest mimic to paper's "true 4-agent desync" without
  network-side disturbance. Known to be the workaround approach
  outlined in `disturbance-protocol-mismatch-fix-report.md` §2.4.
- **Cons:** Magnitude/timing parameters are project-fabricated. RL
  may overfit to the specific (amp_weights, time_offsets) pattern
  rather than learning generalizable coordination.

### 3.3 Candidate F3 — Random multi-point (paper-random + multi-target)

```python
EssPmStepProxy(target_indices="random_2_of_4")
# or "random_3_of_4"
# Each call: rng picks 2 (or 3) of 4 indices to receive non-zero amp.
# Magnitude split equally.
```

- **Predicted response:** Per scenario, 2 (or 3) random ES respond.
  Across 50-scenario eval, every ES gets signal in ~50% (or 75%) of
  scenarios.
- **Pros:** Maintains paper's "randomized scenarios" structure.
  Statistically, every ES (including ES2 if Probe B-ESS PASS) gets a
  non-trivial fraction of scenarios with learning signal.
- **Cons:** Per-scenario excitation count is variable. Eval variance
  may increase (different runs get different per-agent gradient
  fractions if seed differs).

### 3.4 Candidate F4 — Hybrid SG-side + multi-point ESS (Option B + Option A)

```python
class HybridSgEssMultiPoint:
    def apply(...):
        # SG-side hit on random G ∈ {1,2,3} with primary magnitude
        # AND
        # ESS-direct multi-point on the ES NOT excited by that G
        ...
```

- **Predicted response:** G1 fires + ES2/ES3/ES4 each get small direct
  Pm step. ES1 sees both network propagation from G1 AND its own
  direct contribution. Roughly 4/4 agents respond.
- **Pros:** Combines paper-faithful "SG-side electrical-direction"
  with multi-target gradient coverage. Actively compensates for
  topology asymmetry (ES2 always added back).
- **Cons:** Even less paper-faithful (mixes mechanical + network
  pathways simultaneously). Reward landscape is composite.

---

## 4. Predicted per-agent response (superposition table)

Based on Probe B G1+G2+G3 measured per-agent response data at mag=±0.5
sys-pu, and assuming approximate linearization (small-signal regime):

### Single-target reference (measured 2026-04-30, mag=±0.5)

`|nadir_diff| + |peak_diff|` per agent in Hz. Source:
`results/harness/kundur/cvs_v3_probe_b{,_ess}/`. ~0 = below 1e-3 Hz noise floor.

| target | ES1 | ES2 | ES3 | ES4 |
|---|---:|---:|---:|---:|
| G1 (Bus 1)        | **0.062** | ~0     | ~0     | ~0     |
| G2 (Bus 2)        | **0.097** | ~0     | ~0     | ~0     |
| G3 (Bus 3)        | ~0        | ~0     | **0.021** | **0.017** |
| ES1 (direct)      | **0.113** | 0.000  | 0.000  | 0.000  |
| ES2 (direct)      | 0.000     | **0.038** | 0.000  | 0.000  |
| ES3 (direct)      | 0.000     | 0.000  | **0.043** | 0.002  |
| ES4 (direct)      | 0.000     | 0.000  | 0.006  | **0.038** |

**Topology takeaway:** ES1 and ES2 are *both* electrical islands at
the ESS layer — direct injection at one does not propagate to the
other. ES3 and ES4 are weakly coupled (~5-15 % cross-leak).
**ES2 has zero coupling to anything except itself.** Any Option F
candidate that does not write `PM_STEP_AMP[2]` directly cannot give
ES2 a learning signal.

### Predicted F1 response (all-4 equal split, mag=±0.5 split 4 ways → 0.125 each)

Linear superposition: each ES{i} sees its `direct(0.125)` ≈
`direct(0.5) × 0.25` = direct response ÷ 4. Cross-agent leakage is
small enough to ignore.

| Candidate F1 prediction | ES1 | ES2 | ES3 | ES4 |
|---|---:|---:|---:|---:|
| direct (mag=0.125) ≈ direct(0.5)/4 | 0.028 | 0.0094 | 0.011 | 0.0096 |
| F1 expected (incl. weak ES3↔ES4 leak) | 0.028 | 0.0094 | 0.011 | 0.0096 |

**All 4 above 1e-3 threshold ✓**, but ES2/ES3/ES4 are within an order
of magnitude of the 1e-3 cutoff. Suggest using **mag = 1.0 sys-pu**
for F1 (each ES gets 0.25 amp) → all per-agent diffs ~ 2×, comfortably
above noise.

**Critical caveat:** F1 is in-phase (all 4 agents fire same direction
same time). The reward `r_f_i = -(Δω_i - mean_j Δω_j)²` *vanishes* when
all agents have identical Δω. F1 may produce **near-zero r_f gradient
despite per-agent response > 0** because the differential vanishes.
This must be verified by sign-pair Probe before any training under F1.

### Predicted F3 ("random_2_of_4") response (per-scenario)

Each call selects 2 random ES, magnitude split 50/50. Per scenario:
2 of 4 agents respond at ~direct(0.25) ≈ direct(0.5)/2 ≈ 0.057-0.022 Hz.

| F3 ES coverage over 50 scenarios | ES1 | ES2 | ES3 | ES4 |
|---|---:|---:|---:|---:|
| Probability of being target | 50% | 50% | 50% | 50% |
| Expected per-scenario diff when targeted | ~0.057 | ~0.019 | ~0.022 | ~0.019 |
| Expected mean per-agent diff over 50 ep | ~0.029 | ~0.0095 | ~0.011 | ~0.0095 |

Compared to F1: same per-agent average gradient magnitude, but **per
scenario only 2 ES respond** → r_f_i ≠ 0 for those 2 (they differ from
the 2 silent ES). Differential signal preserved. **Recommended over F1.**

### Predicted F4 (G_random + ES_compensate) response

Per scenario: pick random G ∈ {G1, G2, G3}, fire at 0.7 × magnitude;
simultaneously fire ES_NOT_excited at 0.3 × magnitude.

For random G1 (only ES1 in network response), compensate via ES2/3/4:
- ES1: 0.062 × (0.7/0.5) = 0.087 (network from G1)
- ES2: direct(0.3 × 1/3) = 0.038 × (0.1/0.5) = 0.0076 (direct from compensate)
- ES3: direct(0.1/0.5) = 0.0086
- ES4: direct(0.1/0.5) = 0.0077

For random G3 (ES3+ES4 in network response), compensate via ES1+ES2:
- ES1: direct(0.15/0.5) = 0.034
- ES2: direct(0.15/0.5) = 0.011
- ES3: 0.021 × (0.7/0.5) = 0.029
- ES4: 0.017 × (0.7/0.5) = 0.024

**All 4 above 1e-3 in both branches ✓**, mode-shape pattern preserved
(network-side does not produce in-phase response). F4 is most
paper-faithful and most robust to ES2 isolation.

**Recommended for actual training:** F4 (or F3 + ES2-bias if F4 design
proves too complex).

---

## 5. Branch-on-ES2 decision matrix

This is the key conditional point of the design. Probe B-ESS verdict
fills in the missing data:

### Branch A: Probe B-ESS confirms ES2 swing-eq is LIVE

ES2 silence under SG-side is purely electrical-area mismatch (ES2 not in
G1/G2/G3's electrical neighborhood, despite project assumption it was
in area 1 with G1/G2). All 4 ES Pm channels work.

**Recommended candidate:** **F3 with `random_2_of_4`** OR **F4 hybrid**.
- F3 is simpler (single new adapter class, no new physics).
- F4 is more paper-faithful (preserves SG-side electrical direction).
- Both deliver ES2 a non-zero learning signal in a non-trivial fraction
  of scenarios.

### Branch B: Probe B-ESS shows ES2 swing-eq is DEAD

ES2 silence is a build-script bug — `PM_STEP_AMP[2]` workspace var is
not actually wired to the ES2 IntW Pm input in `build_kundur_cvs_v3.m`.

**Action:** Pause Option F design and spawn a build-script audit:
- File: `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`
- Search for: `Pm_step_amp_2`, `ES2`, `IntW_ES2`, `Pm_2`
- Verify: the Pm-step gate Constant block for ES2 actually feeds into
  ES2's swing-eq Pm summer
- This is a Tier A physical-layer fix; breaks credibility close lock.

**Fallback Option F (3-agent only):** If build-script fix is deferred,
Option F design accepts ES2 as structural dead agent and targets only
{ES1, ES3, ES4} via `EssPmStepProxy(target_indices=(0, 2, 3))`.
Trained policy will NOT actuate ES2 effectively.

---

## 6. Acceptance criteria for any Option F candidate

Before training under any candidate, run a Probe-B-style sign-pair
verification under the new dispatch:

1. **Per-agent response coverage:** ≥ 3 of 4 ES show |Δf| > 1e-3 Hz
   in at least 50 % of 50 random-seed scenarios. (Branch A target.)
   For Branch B: ≥ 3 of 4 from {ES1, ES3, ES4} show response in
   ≥ 90 % of scenarios.

2. **Per-agent r_f contribution:** No single agent contributes > 70 %
   of total r_f_global magnitude on average across scenarios.
   (Current single-point: ES1 alone is ~70 % of cum_unnorm under G2.)

3. **Numerical stability:** 0 NaN, 0 tds_failed across 50 scenarios.

4. **cum_unnorm magnitude band:** per_M ∈ [-25, -10] (loose; Option F
   does not need to land in paper-class band — that's Option E's job).

5. **Sign asymmetry preserved:** for all candidate types, mag=+0.5 vs
   mag=-0.5 must produce different per-agent peak times / signs (not
   collapsed). Verifies Option F dispatch isn't accidentally bypassing
   the paper Eq.15 sign convention.

If any criterion fails → fix design, re-validate, do not train.

---

## 7. Implementation outline (NOT TO EXECUTE THIS ITERATION)

If Option F is approved later, the implementation order would be:

### Step 1: Add `MultiPointPmStepProxy` to `disturbance_protocols.py`

```python
@dataclass(frozen=True)
class MultiPointPmStepProxy:
    target_indices: tuple[int, ...] | str  # supports "random_2_of_4", etc.
    amp_weights: tuple[float, ...] | None = None   # default: equal split
    time_offsets: tuple[float, ...] | None = None  # default: all 0.0

    def apply(self, bridge, magnitude_sys_pu, rng, t_now, cfg):
        # Resolve sentinels (random_2_of_4, random_3_of_4)
        # Compute per-target (amp, t)
        # Write to PM_STEP_AMP[i] and PM_STEP_T[i] via _ws()
        # Silence SG Pmg
        # Return DisturbanceTrace
        ...
```

### Step 2: Register dispatch_type strings

```python
_DISPATCH_TABLE.update({
    "pm_step_multi_4_equal":
        lambda: MultiPointPmStepProxy(target_indices=(0,1,2,3)),
    "pm_step_multi_random_2":
        lambda: MultiPointPmStepProxy(target_indices="random_2_of_4"),
    "pm_step_multi_random_3":
        lambda: MultiPointPmStepProxy(target_indices="random_3_of_4"),
    # F4 hybrid would need a new adapter class
})
```

### Step 3: Extend `scenario_to_disturbance_type` to recognize new `disturbance_kind` values

```python
if scenario.disturbance_kind == "multi":
    if scenario.target == 4:
        return "pm_step_multi_4_equal"
    if scenario.target in (2, 3):
        return f"pm_step_multi_random_{scenario.target}"
    raise ValueError(...)
```

### Step 4: `paper_eval.py` accept `--disturbance-mode multi` + map manifest bus to new disturbance_type strings

### Step 5: Validation Probe-B-style sign-pair under new dispatch (10-15 min wall per candidate)

### Step 6: If validation passes, retrain anchor under selected Option F candidate, 200-500 ep (5-8 h wall)

### Step 7: Compare retrained policy vs no_control under same Option F protocol; judge improvement

---

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Multi-point superposition is non-linear in the Phasor solver; predicted per-agent response may not match measured | Run sign-pair Probe under each F candidate before training (Step 5); if response distribution is bipolar or saturated like P1b, redesign F before training |
| R2 | F1/F3 with all 4 in-phase produces single mode-shape, no actual 4-agent desync | F2/F4 explicitly add time_offsets / hybrid pathways to break in-phase; choose F2 or F4 if F1/F3 sign-pair verification shows degenerate mode-shape |
| R3 | Option F gives RL signal but does not change reward landscape topology — RL might still converge to "ES1 dominant" policy because ES1 has best learnable response curve | Per-agent action ablation post-training: zero out ES{i}'s actions in eval, measure cum_unnorm degradation. If only ES1's policy matters, Option F has not solved the underlying paper-faithfulness problem |
| R4 | ES2 dead even under direct Pm injection (Branch B) — Option F structurally cannot include ES2 | Documented above. Option F must be marked as "3-agent best achievable" until physical-layer ES2 fix |
| R5 | Hybrid F4 (SG + ESS) double-counts magnitude — total disturbance > paper magnitude | F4 design must split magnitude budget: e.g. 70 % SG + 30 % ESS-compensate |
| R6 | New disturbance types pollute the legacy `pm_step_proxy_*` namespace; future agents may pick wrong default | Update `kundur-paper-project-terminology-dictionary.md` §2.2 row to register all new types + mark which is production default |

---

## 9. What this design does NOT solve

- **Paper unit comparability (Q8):** Even if Option F gives 4/4 agent
  excitation, the project's per_M scale vs paper -15.20 is still
  Q8-ambiguous. Option F is necessary but not sufficient for paper
  numerical comparison.
- **Network electrical disturbance (Option E):** Option F is mechanical
  (Pm-side); paper's LoadStep is electrical (network admittance side).
  Option F approximates the *gradient distribution* of the paper
  protocol but not the *physical mechanism*.
- **Action range Q7:** Q7 ambiguity is orthogonal to disturbance
  scheduling; Option F leaves DM_MIN/DM_MAX untouched.
- **Single-point legacy protocols:** All current
  `pm_step_proxy_random_bus` / `pm_step_proxy_random_gen` runs remain
  diagnostic tools, not deprecated. Option F adds choices, doesn't
  remove existing ones.

---

## 10. Status

- **Probe B-ESS:** ✅ COMPLETED 2026-04-30 03:00 (job `blixryfo7` rerun
  after `args.disturbance_mode` NameError fix)
- **Branch decision:** ✅ Branch A locked (all 4 ES swing-eq LIVE)
- **Candidate ranking:** F4 > F3 > F2 > F1 (F1 rejected for in-phase
  collapse risk)
- **Surprise finding:** ES1 and ES2 are ESS-layer electrical islands;
  any Option F variant must write `PM_STEP_AMP[2]` directly to give
  ES2 a learning signal. No network-mediated path reaches ES2.
- **Recommended next step (NOT executed in this iteration):** if user
  approves F4 (or F3) implementation, the implementation outline in §7
  applies. Sign-pair Probe under the chosen candidate is the gate
  before any training.
- **This document:** complete; ready for user decision on which
  candidate to actually implement, or to defer Option F entirely in
  favor of Option E (CCS at Bus 7/9, breaks credibility close lock,
  more paper-faithful).
