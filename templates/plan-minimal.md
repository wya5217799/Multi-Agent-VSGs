<!--
USAGE:
  - Copy to quality_reports/plans/YYYY-MM-DD_<short-name>.md before starting.
  - Use for 1-3 hr cross-file tasks. For >3 hr / paper-anchor / multi-phase work,
    use the fuller spec template at quality_reports/specs/ instead.
  - Status keyword on line 1 enables: grep "^\*\*Status\*\*" quality_reports/plans/*.md
-->

# Plan: [one-line goal]

**Status**: DRAFT
**Estimated**: X hr | **Actual**: TBD
**Trigger**: [condition / task ID / issue reference]
**Supersedes**: none

## §1 Acceptance Gates (PRE-REGISTERED, IMMUTABLE)

| ID | Threshold | Measurement | Verdict |
|---|---|---|---|
| G1 | [threshold] | [how measured] | TBD |
| G2 | [threshold] | [how measured] | TBD |

## §2 TodoWrite Mapping (1:1)

| Todo content | Step |
|---|---|
| [line 1 of todo] | §3.X |
| [line 2 of todo] | §3.Y |

## §3 Steps (atomic, file-level)

1. [module / phase]
   - 1.1 Edit `path/to/file.py:LINE` — A → B
   - 1.2 Edit `path/to/file.py:LINES` — X → Y
   - 1.3 Run `pytest -k test_name` → expect PASS

2. [next module]
   - 2.1 Modify `another/file.py` — change Z
   - 2.2 Verify via [command] → expect [output]

## §4 Risks (skip if trivial)

- [risk]: [mitigation]

## §5 Out of scope (skip if low creep risk)

- [explicitly NOT doing]: [why]

## §6 References

- [commit hash or link]
- [related doc or spec]

---

# §Done Summary (append-only, post-execution)

**Commit**: `[hash]`
**Gate verdicts**: G1 PASS, G2 PASS, ...
**Estimate vs actual**: X hr est / Y hr actual (±Z%)
**Surprises**: [what was unexpected]
