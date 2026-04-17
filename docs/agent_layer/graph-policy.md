# Graph Policy

- Graph output may be used for navigation and drift discovery.
- Graph output is **not** the authoritative control contract.
- If graph output conflicts with `AGENTS.md`, manifests, or code-backed references, the graph loses.
- Rebuild graph outputs after control-manifest or MCP-surface changes if graph navigation is in active use.

## Authority Hierarchy

```
AGENTS.md + docs/control_manifest.toml   ← authoritative
engine/harness_reference.py              ← code-backed reference
graph output (graphify-out/)             ← secondary navigation aid only
```

## When to Use Graph Output

- Discovering unknown cross-file dependencies during unfamiliar code exploration.
- Detecting drift between expected and actual module relationships.
- Navigating large refactors where the textual index is insufficient.

## When NOT to Use Graph Output

- As the primary definition of which tools exist (use `mcp_server.PUBLIC_TOOLS`).
- As the primary definition of harness task sequence (use harness task contracts).
- To override decisions already recorded in `docs/decisions/`.
