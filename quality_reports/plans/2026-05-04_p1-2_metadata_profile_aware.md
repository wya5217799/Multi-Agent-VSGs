**Status**: DONE
**Estimated**: 1 hr | **Actual**: ~15 min
**Trigger**: Retro §3.5 + P2 ADR D2 follow-up — false-alarm `below_expected_floor` on
  `pm_step_hybrid_sg_es` every Phase 4 run at probe mag=0.5 sys-pu
**Supersedes**: none

# Plan: P1-2 — dispatch_metadata per-sys-pu linear floor scaling

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | `DispatchMetadata` accepts `expected_df_hz_per_sys_pu` field | schema constructible | PASS |
| G2 | `pm_step_hybrid_sg_es` uses per-sys-pu floor; no false-alarm at mag=0.5 | effective_floor=0.21 Hz ≤ observed 0.21 Hz | PASS |
| G3 | All other dispatches unaffected (backward compat) | pytest test_all_non_hybrid_dispatches_have_none_per_sys_pu | PASS |
| G4 | All existing + new tests pass | 67 tests total (18 new) | PASS |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| Add `expected_df_hz_per_sys_pu` field to `DispatchMetadata` | §3.1 |
| Update `get_metadata()` to expose new field | §3.2 |
| Recalibrate `pm_step_hybrid_sg_es` entry | §3.3 |
| Update floor check in `_dynamics.py` | §3.4 |
| Write test file | §3.5 |
| Write plan doc | §3.6 |

## §3 Steps (atomic, file-level)

1. Schema + registry
   - 1.1 `dispatch_metadata.py`: add `expected_df_hz_per_sys_pu: float | None = None` field to `DispatchMetadata` dataclass
   - 1.2 `dispatch_metadata.py`: update `get_metadata()` missing-branch and hit-branch to include new field
   - 1.3 `dispatch_metadata.py`: recalibrate `pm_step_hybrid_sg_es` — set `expected_df_hz_per_sys_pu=0.42`, null `expected_min_df_hz=None`

2. Consumer
   - 2.1 `_dynamics.py:359`: replace static floor lookup with per-sys-pu precedence check:
     `if per_sys_pu is not None: effective_floor = per_sys_pu * abs(mag) else: effective_floor = md.get("expected_min_df_hz")`

3. Tests
   - 3.1 Create `tests/test_p1_metadata_profile_aware.py` with 4 test classes (schema, per-sys-pu math, backward compat, hybrid recalibration)
   - 3.2 Run: `pytest tests/test_p1_metadata_profile_aware.py tests/test_disturbance_protocols.py -x -v` → 67 PASS

## §4 Risks (skip if trivial)

- Unit ambiguity (`MW` vs `sys-pu`): **resolved** — codebase uses `sys-pu` throughout
  (`applied_magnitude_sys_pu`, `mag_unit="sys-pu (total budget)"`). Field named
  `expected_df_hz_per_sys_pu` to be explicit.

## §5 Out of scope

- Other dispatches' floor recalibration (future cycles one-by-one)
- `expected_max_df_hz` ceiling logic (P1-3 territory)
- `_verdict.py` G4 changes (P1-1 territory)

## §6 References

- Retro: `quality_reports/reviews/2026-05-04_engineering_retro_long_cycle.md` §3.5
- Historical data: `F4_V3_RETRAIN_FINAL_VERDICT.md` — mean Δf=0.65 Hz at mag≈1.55 sys-pu
- Derivation: 0.65 / 1.55 = 0.419 ≈ 0.42 Hz/sys-pu
- Probe pain: at mag=0.5 → old static floor 0.30 Hz, observed 0.18-0.21 Hz → false alarm
- After fix: effective_floor = 0.42 * 0.5 = 0.21 Hz ≈ observed → floor_status="ok"

---

# §Done Summary (append-only, post-execution)

**Commit**: (not committed per spec)
**Gate verdicts**: G1 PASS, G2 PASS, G3 PASS, G4 PASS
**Estimate vs actual**: 1 hr est / ~15 min actual
**Surprises**: Unit was already `sys-pu` (not MW) — field renamed to `expected_df_hz_per_sys_pu`
  for clarity. The result dict stores the *effective* computed floor under the existing
  `"expected_min_df_hz"` key so downstream consumers (_report.py, _verdict.py) need no changes.
