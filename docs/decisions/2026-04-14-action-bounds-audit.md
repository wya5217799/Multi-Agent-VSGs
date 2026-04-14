# Action Bounds Audit — ANDES vs Simulink (2026-04-14)

## Status: PENDING — DD bounds not unified; DM bounds confirmed consistent

---

## Context

During Phase 3 constant consolidation (commit e54d1fc), `PENDING AUDIT` annotations were added
to ANDES action bounds because they differ from the Simulink side:

| Param | ANDES | Simulink | Ratio |
|-------|-------|----------|-------|
| DM_MIN | −10.0 | −6.0 | 1.67× |
| DM_MAX | 30.0 | 18.0 | 1.67× |
| DD_MIN | −10.0 | −1.5 | 6.67× |
| DD_MAX | 30.0 | 4.5 | 6.67× |

---

## Findings

### DM bounds — consistent (BackendProfile, intentionally different)

ANDES VSG_M0 = 20.0 (H0 = 10 s); Simulink VSG_M0 = 12.0 (H0 = 6 s).

Ratio = 20/12 = 1.667 — exactly matches the DM bound ratio.

**Conclusion:** ANDES DM bounds are Simulink bounds scaled by M0 ratio.
This is a calibrated BackendProfile difference, NOT an error.

### DD bounds — suspect (v1 legacy artefact)

ANDES VSG_D0 = 4.0; Simulink VSG_D0 = 3.0. D0 ratio = 4/3 = 1.333.

If DD bounds were similarly proportional to D0, ANDES should use ≈ [−2.0, 6.0].
Instead ANDES has [−10.0, 30.0] — **5× wider than expected**.

The comment in `env/andes/base_env.py` confirms this is a "v1 config" artefact:
```python
DD_MIN = -10.0   # = DD_MIN (v1 config)
DD_MAX = 30.0    # = DD_MAX (v1 config)
```

**Conclusion:** ANDES DD bounds are NOT intentionally calibrated — they are an
unchanged legacy value from an early version. The physically consistent range
(proportional to D0) would be ≈ [−2.0, 6.0].

### Paper bounds — cannot resolve (Q7 unresolved)

Paper Sec.IV-B: ΔH ∈ [−100, 300], ΔD ∈ [−200, 600].

These ranges are far outside both ANDES and Simulink values. The discrepancy
is documented as Q7 in `yang2023-fact-base.md`: the paper's H_es,i may not be
in the same units as project H (seconds), so direct comparison is not possible.

---

## Decision

**DM bounds:** Keep as BackendProfile (intentionally different, justified by M0 ratio).
Remove `PENDING AUDIT` from DM lines once this document is verified.

**DD bounds:** Keep ANDES DD bounds at [−10, 30] for now to avoid breaking
existing trained checkpoints. Add a TODO to harmonize after:
1. Any in-progress ANDES training completes (no active runs as of 2026-04-14).
2. Action bounds change is tested for training stability impact.
3. Physical correctness of [−2, 6] is verified (D0-proportional assumption checked
   against ANDES small-signal stability analysis).

**Unification into ScenarioContract:** NOT appropriate yet.
DM: confirmed different by design → BackendProfile.
DD: suspected legacy error → fix ANDES DD to [−2, 6] in a dedicated PR after
validation; only then can both sides be unified into ScenarioContract if equal.

---

## What a "Correct" ANDES DD range looks like

Two scaling principles produce different targets; we need to pick one:

**Principle A — D0-proportional (same relative range as Simulink):**
```
Simulink: DD_MIN/D0 = −1.5/3.0 = −0.50,  DD_MAX/D0 = 4.5/3.0 = 1.50
ANDES D0 = 4.0 → DD_MIN = −0.50 × 4.0 = −2.0,  DD_MAX = 1.50 × 4.0 = 6.0
```

**Principle B — DM/DD ratio-proportional (same M:D ratio as Simulink):**
```
Simulink: DM_MAX/DD_MAX = 18/4.5 = 4.0
ANDES DM_MAX = 30 → DD_MAX = 30/4.0 = 7.5,  DD_MIN = −10/4.0 = −2.5
```

**Adopted decision: Principle A (D0-proportional), target [-2.0, 6.0].**

Rationale: The DM bounds were established via `DM = 2 × DH`, where `DH` was
calibrated per-backend as a fraction of H₀ (`DH_MAX = 1.5 × H₀`). The analogous
D-based scaling is D-proportional (Principle A), not derived from DM. Principle B
conflates the M-scale calibration with D-scale and yields an ad-hoc ratio.

This decision is adopted as the specification target for the corrective PR.
Changing DD bounds in a future PR requires:
1. Verifying no ANDES training is running.
2. Confirming D0-proportional bounds do not violate small-signal stability margins.
3. Running a short training run to check for learning regression.

---

## Files affected

- `env/andes/base_env.py` — ANDES Kundur action bounds (lines 56–59)
- `env/andes/andes_ne_env.py` — ANDES NE39 action bounds (lines 47–50)
- `scenarios/config_simulink_base.py` — Simulink shared bounds (lines 37–38)

---

*Date: 2026-04-14*
