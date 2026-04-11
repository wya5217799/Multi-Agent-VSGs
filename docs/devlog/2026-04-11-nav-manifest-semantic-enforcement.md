---
note_id: devlog-2026-04-11-nav-manifest-semantic-enforcement
scenario_id: kundur
related_run_id: none
related_commit: pending
status: closed
tags: [navigation, docs, tests]
---

# Context

`docs/navigation_manifest.toml` was introduced as the single source of truth
for Start Here entries, but the initial test only enforced the ordered path
list. Review feedback correctly pointed out that `purpose` and `trigger`
remained hand-maintained prose in `AGENTS.md`, so the semantic contract was
still able to drift while tests stayed green.

# Evidence

- Review finding: manifest metadata was declared authoritative but only `path`
  was machine-checked.
- Prior implementation in `tests/test_nav_manifest.py` extracted only
  backtick-quoted paths from `AGENTS.md`.

# What Changed

- Tightened `tests/test_nav_manifest.py` so it now compares `path`, `purpose`,
  and `trigger` for every Start Here entry.
- Rewrote the Start Here list in `AGENTS.md` to render the full manifest
  contract explicitly, including re-evaluation triggers.
- Normalized `docs/navigation_manifest.toml` wording to ASCII-safe prose so the
  rendered text and test parsing do not depend on ambiguous punctuation.

# Outcome

- Start Here is no longer only a path checklist; its rendered semantics are now
  covered by pytest.
- A future edit that changes manifest metadata without updating `AGENTS.md`
  will fail `tests/test_nav_manifest.py`.

# Next

- If Start Here prose changes more often, generate the AGENTS section directly
  from the manifest instead of validating a hand-rendered copy.
