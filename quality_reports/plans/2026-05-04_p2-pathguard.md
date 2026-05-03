**Status**: DONE
**Estimated**: 1.5 hr | **Actual**: ~10 min
**Trigger**: Engineering retro §3.5.3 — cross-worktree shadowing upgraded to P0-shadow priority
**Supersedes**: none

# Plan: P2-cleanup-pathguard — Python-side worktree assert guard

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | All `tests/test_path_guard.py` tests pass | `pytest tests/test_path_guard.py -x -v` → 15 passed | PASS |
| G2 | `--help` still works from correct worktree | `python -m probes.kundur.probe_state --help` exits 0 | PASS |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| Create engine/path_guard.py | §3.1 |
| Wire probe entrypoint __main__.py | §3.2 |
| Create tests/test_path_guard.py | §3.3 |
| Run pytest + --help smoke | §3.4 |
| Write this plan | §3.5 |

## §3 Steps (atomic, file-level)

1. New module
   - 1.1 Create `engine/path_guard.py` — `assert_active_worktree`, `WrongWorktreeError`, constants

2. Wire probe entrypoint
   - 2.1 Edit `probes/kundur/probe_state/__main__.py` — add import + call after `parse_args`, before heavy work

3. Tests
   - 3.1 Create `tests/test_path_guard.py` — 15 tests covering pass/fail/env-override/custom-basename

4. Verification
   - 4.1 `pytest tests/test_path_guard.py -x -v` → 15 passed
   - 4.2 `python -m probes.kundur.probe_state --help` → exits 0 (guard fires after parse_args)

5. Doc
   - 5.1 Write this plan

## §4 Risks (skip if trivial)

- None: pure Python, no MATLAB, no existing tests broken.

## §5 Out of scope

- Training scripts, paper_eval, other probe entrypoints: defer to next cycle referencing this module.
- MATLAB-side guard (already exists at `build_kundur_cvs_v3_discrete.m:61-79`, commit c400cbd).
- `_verdict.py` / `dispatch_metadata.py` (P1-1 / P1-2 territory).

## §6 References

- Retro §3.5.3 — cross-worktree shadowing as P0-shadow
- MATLAB analog: `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m:61-79` (commit c400cbd)
- Env var name: `MAVSGS_DISABLE_WORKTREE_ASSERT` — shared with MATLAB side for consistency

---

# §Done Summary (append-only, post-execution)

**Commit**: not committed per spec
**Gate verdicts**: G1 PASS (15/15), G2 PASS
**Estimate vs actual**: 1.5 hr est / ~10 min actual
**Surprises**: none — implementation straightforward; `--help` correctly bypasses guard because argparse handles it before returning from `parse_args`, so the guard never fires for `--help` invocations
