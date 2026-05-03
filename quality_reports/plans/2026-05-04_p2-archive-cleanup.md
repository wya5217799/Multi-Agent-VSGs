<!--
USAGE:
  - Copy to quality_reports/plans/YYYY-MM-DD_<short-name>.md before starting.
  - Use for 1-3 hr cross-file tasks. For >3 hr / paper-anchor / multi-phase work,
    use the fuller spec template at quality_reports/specs/ instead.
  - Status keyword on line 1 enables: grep "^\*\*Status\*\*" quality_reports/plans/*.md
-->

# Plan: P2 cleanup — archive superseded plans and gate verdicts

**Status**: DONE
**Estimated**: 0.5 hr | **Actual**: ~0.25 hr
**Trigger**: retro §3.5.5 + §3.5.7 — 27+ plans / 26+ gates littering active dirs, confusing new AI agents
**Supersedes**: none

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | `quality_reports/plans/` has < 32 active .md files after cleanup | `ls quality_reports/plans/*.md \| wc -l` | PASS (24) |
| G2 | All retain-list files still in `plans/` (not archived) | manual check | PASS |
| G3 | `plans/_archive/` holds 8 moved files; `gates/_archive/` holds 13 | `ls _archive/*.md \| wc -l` | PASS |
| G4 | 16/16 tests pass | `pytest tests/test_archive_script.py -v` | PASS |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| Write `scripts/archive_superseded_plans.py` | §3.1 |
| Dry-run and verify retain list safe | §3.2 |
| Run `--apply --verbose` | §3.3 |
| Write `tests/test_archive_script.py` | §3.4 |
| Write this plan doc | §3.5 |

## §3 Steps (atomic, file-level)

1. Script implementation
   - 1.1 Write `scripts/archive_superseded_plans.py` with Rule 1 (status marker) + Rule 3 (hardcoded globs) + retain set + date-based retain
   - 1.2 Dry-run with verbose to confirm retain list safety

2. Apply
   - 2.1 `python scripts/archive_superseded_plans.py --apply --verbose 2>&1 | tee scripts/archive_run_2026-05-04.log`

3. Tests
   - 3.1 Write `tests/test_archive_script.py` covering all 5 spec scenarios
   - 3.2 `pytest tests/test_archive_script.py -v` → 16 PASS

## §4 Risks (skip if trivial)

- Retain list miss: mitigated by dry-run verification and explicit + date-based dual retain logic

## §5 Out of scope (skip if low creep risk)

- Rule 2 (date-heuristic against SoT registry) — too risky, deferred per spec
- `docs/decisions/`, `quality_reports/reviews/`, `quality_reports/specs/`, `quality_reports/session_logs/` — not touched
- Committing — not done per task constraints

## §6 References

- retro §3.5.5 + §3.5.7: superseded plan accumulation over 5 weeks
- `scripts/archive_run_2026-05-04.log` — full apply log

---

# §Done Summary (append-only, post-execution)

**Commit**: (not committed per task constraints)
**Gate verdicts**: G1 PASS, G2 PASS, G3 PASS, G4 PASS

**Archive count by category**:
- `quality_reports/plans/_archive/`: 8 files moved
  - 5 × `2026-04-26_*.md` (v3 topology spec, phase3, phase4+5 roadmap, phase4, kundur cvs v3 plan)
  - 3 × `2026-04-28-task-{1,2,3}-*.md` (execution plans for w2-to-bus8, bus14-preengage, action-range-doc)
- `quality_reports/gates/_archive/`: 13 files moved
  - All 13 × `2026-04-26_kundur_cvs_g3prep_*.md` (A/B/C/D/DE/E/F variants, superseded by P2 phase 4 oracle)

**Retain list verified**: all 7 required files confirmed present in `plans/` after apply.

**Estimate vs actual**: 0.5 hr est / ~0.25 hr actual
**Surprises**: `phase_b_findings_cvs_discrete_unlock.md` and `phase_b_extended_module_selection.md` already had `2026-05-03_` prefix on disk (renamed since retro), so they were retained by date-based logic rather than needing hardcoded exclusion.
