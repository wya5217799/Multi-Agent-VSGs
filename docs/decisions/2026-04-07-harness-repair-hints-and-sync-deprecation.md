# Decision: repair_hints field and harness_train_smoke deprecation

Date: 2026-04-07
Related commits: (this commit)

## repair_hints — diagnostic output extension

### Decision

`model_diagnose` now returns a `repair_hints` field alongside `suspected_root_causes`.
`repair_hints` is always present (list, may be empty).

### Rationale

`suspected_root_causes` contained raw MATLAB error text.
An agent consuming the record still had to manually map error text to a concrete fix.
`repair_hints` closes that gap with a lightweight keyword-matching layer
(`engine/harness_repair.py`, rules D1–D6) that outputs structured suggestions
an agent can pass directly to `model_patch_verify`.

### Constraints (stable rules)

- `repair_hints` is **heuristic only** — not guaranteed correct. Confidence field
  (`"high"` / `"low"`) signals match strength.
- Returns `[]` on no match — never blocks the existing diagnose → patch_verify chain.
- Rules are hard-coded in `engine/harness_repair.py`; no external knowledge file.
- New root causes still go to `docs/devlog/` + `docs/decisions/` via the normal
  memory workflow. `harness_repair.py` is not a substitute for that.

### Workflow after this change

```
model_diagnose
  → suspected_root_causes  (raw MATLAB text, unchanged)
  → repair_hints           (structured suggestions, new)
        ↓
  agent judgment
        ↓
  model_patch_verify(edits=[...])
```

No new harness task. No new MCP tool. `model_diagnose` contract extended only.

---

## harness_train_smoke — synchronous version deprecated

### Decision

`harness_train_smoke` (sync) now returns `contract_error` immediately without
launching a subprocess. Use `harness_train_smoke_start` +
`harness_train_smoke_poll` instead.

### Rationale

The synchronous version blocks the MCP server for the full training duration
and reliably times out. It was never successfully executed in production.
The async start/poll pair was introduced in commit c920f9a as the correct path.

### Stable rule

The tool name `harness_train_smoke` is preserved in PUBLIC_TOOLS so agent prompts
and the test contract (`test_mcp_server.py`) remain valid. The function body
fails fast with a clear migration message rather than silently disappearing.
If the project later moves to async-only, a separate API-change commit should
update docs, tests, and all dependent prompts together.
