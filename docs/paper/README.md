# Paper Notes

This directory stores paper-facing summaries extracted from the project memory system.

It is not the primary record of debugging or development. Instead, it points back to:

- `results/harness/` for run evidence
- `docs/devlog/` for process reasoning
- `docs/decisions/` for stable rules

Use this directory to keep paper drafting lightweight and traceable.

## Suggested Files

- `method-evolution.md`: major method changes and why they happened
- `experiment-index.md`: run and evidence index for experiments worth citing

## Method Evolution Template

```md
# Method Evolution

## <topic>

- Time: 2026-04-06
- Claim: what changed in the method
- Evidence:
  - Run: `results/harness/kundur/20260406-140000-kundur-<goal>/`
  - Devlog: `docs/devlog/2026-04-06-<topic>.md`
  - Decision: `docs/decisions/2026-04-06-<topic>.md`
  - Commit: `<git-sha>`
- Relevance to paper:
  - method
  - experiment
  - ablation
```

## Experiment Index Template

```md
# Experiment Index

## <run-or-series>

- Scenario: kundur
- Run: `20260406-140000-kundur-<goal>`
- Question: what this run series was testing
- Outcome: short result summary
- Evidence:
  - Harness: `results/harness/kundur/20260406-140000-kundur-<goal>/`
  - Native artifacts: `<path-or-none>`
- Notes:
  - why this run matters for the paper
```
