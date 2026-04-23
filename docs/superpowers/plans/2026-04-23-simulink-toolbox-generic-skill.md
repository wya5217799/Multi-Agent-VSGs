# Simulink Toolbox Generic Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the installed `simulink-toolbox` skill a single generic Simulink skill that works across projects, with project-specific Yang/VSG harness and training rules kept in this repository's AGENTS/docs layer.

**Architecture:** Keep one `simulink-toolbox` skill name in both installed locations: `C:\Users\27443\.codex\skills\simulink-toolbox` and `C:\Users\27443\.claude\skills\simulink-toolbox`. Filter the skill inventory and routing docs to general Simulink `simulink_*` primitives only, excluding `harness_*`, `training_*`, VSG bridge status, Kundur, NE39, Yang, agent, episode, reward, and paper-reproduction language. Keep project-specific routing in `AGENTS.md`, `docs/decisions/`, and the repository control surface docs.

**Tech Stack:** Markdown skill files, Python index generator, pytest offline static tests, PowerShell for local file inspection and command execution.

---

## File Structure

- Modify: `scripts/regen_skill_index.py`
  - Generate the installed skill `index.json` as a generic Simulink inventory by default.
  - Keep both target skill directories in one generator path.
  - Exclude project-only public tools from the generic skill inventory.

- Modify: `tests/test_regen_skill_index.py`
  - Verify generated skill indexes are generic by default.
  - Verify project-only tools are not emitted into the generic skill inventory.

- Create: `tests/test_simulink_toolbox_skill_boundary.py`
  - Static guard that checks installed `.codex` and `.claude` `simulink-toolbox` skill files, when present.
  - Fails if project-specific terms return to `SKILL.md`, `map.md`, or `index.json`.

- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md`
  - Remove harness/training/VSG/Yang project-specific routing.
  - Keep generic MCP-first Simulink workflow.

- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
  - Remove `harness`, `training`, `training_bridge`, and project-specific entry point sections.
  - Remove `simulink_bridge_status` from generic routing.
  - Replace VSG-specific NOT statements with generic "domain interpretation belongs to project adapters" wording.

- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\index.json`
  - Regenerate from `scripts/regen_skill_index.py`.
  - Contains generic Simulink tools only.

- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md`
  - Same content contract as Codex installation.

- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`
  - Same content contract as Codex installation.

- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\index.json`
  - Same generated inventory as Codex installation.

- Create: `docs/decisions/2026-04-23-simulink-toolbox-generic-boundary.md`
  - Record the stable rule: skills may specialize by domain, not by individual project.
  - State that this repository's Yang/VSG rules live in AGENTS/docs, not in the global skill.

---

### Task 1: Add The Boundary Decision

**Files:**
- Create: `docs/decisions/2026-04-23-simulink-toolbox-generic-boundary.md`

- [ ] **Step 1: Create the decision record**

Create `docs/decisions/2026-04-23-simulink-toolbox-generic-boundary.md` with:

```markdown
# 2026-04-23 Simulink Toolbox Generic Skill Boundary

## Status

Adopted.

## Context

The installed `simulink-toolbox` skill is intended to be reused across multiple
Simulink projects. It currently includes project-specific Yang 2023 VSG
reproduction routing such as `harness_*`, `training_*`, Kundur/NE39, VSG bridge,
agent, episode, and paper reproduction language.

That makes the global skill too specific. A second similar VSG-specific skill
would also be harmful because two near-duplicate Simulink skills can compete for
the same user prompts and make tool routing less predictable.

## Decision

Keep exactly one installed skill named `simulink-toolbox`.

The skill may specialize in the Simulink domain, but it must not specialize in
this repository's Yang/VSG project. Its routing docs and generated inventory
must cover only general Simulink concepts:

- model lifecycle
- block and subsystem structure
- lines and ports
- block and model parameters
- workspace variables
- controlled simulation windows
- logged signals and `SimulationOutput`
- solver configuration and diagnostics
- screenshots and MATLAB figures
- script execution as an escape hatch

The following project-specific concepts must stay out of the installed generic
skill:

- Yang 2023
- Kundur
- NE39
- VSG
- `harness_*`
- `training_*`
- `simulink_bridge_status`
- agent
- episode
- reward
- Pe/omega/delta interpretation
- paper reproduction workflow

Project-specific routing belongs in this repository's `AGENTS.md`, scenario
contracts, harness docs, training docs, and decisions.

## Consequences

The same `simulink-toolbox` skill can be reused safely in unrelated Simulink
projects.

This repository still keeps its paper-reproduction routing, but those rules are
provided by repository context rather than the global skill.

The index generator must emit a generic skill inventory by default for both:

- `C:\Users\27443\.codex\skills\simulink-toolbox`
- `C:\Users\27443\.claude\skills\simulink-toolbox`
```

- [ ] **Step 2: Review for project rule placement**

Run:

```powershell
Select-String -Path 'docs/decisions/2026-04-23-simulink-toolbox-generic-boundary.md' -Pattern 'Project-specific routing belongs'
```

Expected: one match confirming that Yang/VSG routing is assigned to repository context, not to the skill.

- [ ] **Step 3: Commit**

```powershell
git add docs/decisions/2026-04-23-simulink-toolbox-generic-boundary.md
git commit -m "docs: define generic Simulink skill boundary"
```

---

### Task 2: Add Static Skill Boundary Tests

**Files:**
- Create: `tests/test_simulink_toolbox_skill_boundary.py`

- [ ] **Step 1: Write the failing boundary test**

Create `tests/test_simulink_toolbox_skill_boundary.py` with:

```python
"""Static boundary tests for installed simulink-toolbox skill copies.

The global skill is shared across Simulink projects. It must stay generic and
must not contain this repository's Yang/VSG harness or training routing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


SKILL_DIRS = [
    Path.home() / ".codex" / "skills" / "simulink-toolbox",
    Path.home() / ".claude" / "skills" / "simulink-toolbox",
]

PROJECT_ONLY_PATTERNS = [
    r"\bYang\b",
    r"\bKundur\b",
    r"\bNE39\b",
    r"\bVSG\b",
    r"\bharness_",
    r"\btraining_",
    r"\bsimulink_bridge_status\b",
    r"\bSimulinkBridge\b",
    r"\bagent\b",
    r"\bagents\b",
    r"\bepisode\b",
    r"\breward\b",
    r"\bPe\b",
    r"\bomega\b",
    r"\bdelta\b",
    r"\bget_training_launch_status\b",
]

GENERIC_ALLOWED_TOOL_PREFIX = "simulink_"
PROJECT_ONLY_SIMULINK_TOOLS = {"simulink_bridge_status"}


def _existing_skill_dirs() -> list[Path]:
    return [path for path in SKILL_DIRS if path.exists()]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.offline
def test_installed_simulink_toolbox_skill_copies_exist_when_checked() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")
    for skill_dir in _existing_skill_dirs():
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "map.md").exists()
        assert (skill_dir / "index.json").exists()


@pytest.mark.offline
def test_installed_simulink_toolbox_docs_are_project_neutral() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")

    for skill_dir in _existing_skill_dirs():
        for filename in ("SKILL.md", "map.md"):
            text = _read_text(skill_dir / filename)
            for pattern in PROJECT_ONLY_PATTERNS:
                assert not re.search(pattern, text), (
                    f"{skill_dir / filename} contains project-only pattern {pattern!r}"
                )


@pytest.mark.offline
def test_installed_simulink_toolbox_index_is_generic_only() -> None:
    if not _existing_skill_dirs():
        pytest.skip("No installed simulink-toolbox skill directories found.")

    for skill_dir in _existing_skill_dirs():
        payload = json.loads((skill_dir / "index.json").read_text(encoding="utf-8"))
        assert "harness_tools" not in payload
        assert "training_tools" not in payload

        tools = payload.get("simulink_tools", [])
        assert tools, f"{skill_dir / 'index.json'} has no simulink_tools"
        for tool in tools:
            name = tool["name"]
            assert name.startswith(GENERIC_ALLOWED_TOOL_PREFIX)
            assert name not in PROJECT_ONLY_SIMULINK_TOOLS
            assert tool.get("group") != "training_bridge"
```

- [ ] **Step 2: Run the new test and verify it fails before cleanup**

Run:

```powershell
python -m pytest tests/test_simulink_toolbox_skill_boundary.py -q
```

Expected before implementation: FAIL because at least one installed skill file still contains project-specific terms such as `harness_`, `training_`, `VSG`, or `simulink_bridge_status`.

- [ ] **Step 3: Commit the failing guard**

```powershell
git add tests/test_simulink_toolbox_skill_boundary.py
git commit -m "test: guard generic Simulink skill boundary"
```

---

### Task 3: Make Skill Index Generation Generic By Default

**Files:**
- Modify: `scripts/regen_skill_index.py`
- Modify: `tests/test_regen_skill_index.py`

- [ ] **Step 1: Add project-only filtering to the generator**

In `scripts/regen_skill_index.py`, add this constant below `_SIMULINK_META`:

```python
_PROJECT_ONLY_TOOLS: set[str] = {
    "simulink_bridge_status",
}
```

Then replace `_build_index` with:

```python
def _build_index(tool_names: list[str]) -> dict:
    """Build the generic simulink-toolbox index from public tool names.

    The installed skill is shared across projects, so the generated inventory
    intentionally excludes this repository's harness, training, and VSG bridge
    tools even though those tools remain public in this MCP server.
    """
    simulink_tools = []
    skipped_project_tools = []

    for name in tool_names:
        if name in _PROJECT_ONLY_TOOLS:
            skipped_project_tools.append(name)
            continue
        if name.startswith(("harness_", "training_")):
            skipped_project_tools.append(name)
            continue
        if name.startswith("simulink_"):
            meta = _SIMULINK_META.get(name, {})
            entry: dict[str, str] = {"name": name}
            if "group" in meta:
                entry["group"] = meta["group"]
            entry["description"] = meta.get("description", "")
            simulink_tools.append(entry)
        else:
            print(f"WARNING: unclassified tool skipped: {name}", file=sys.stderr)

    return {
        "meta": {
            "source": "generated from mcp_server.PUBLIC_TOOLS filtered for generic simulink-toolbox use",
            "note": (
                "This file is the L0 authority for the generic installed skill inventory. "
                "It intentionally excludes project-specific harness, training, and VSG bridge tools. "
                "Regenerate with: python scripts/regen_skill_index.py"
            ),
            "excluded_project_tools": skipped_project_tools,
        },
        "simulink_tools": simulink_tools,
        "summary": {
            "simulink_count": len(simulink_tools),
            "total": len(simulink_tools),
        },
    }
```

- [ ] **Step 2: Update the generator CLI description**

In `scripts/regen_skill_index.py`, replace the parser description with:

```python
description="Regenerate generic simulink-toolbox index.json files from PUBLIC_TOOLS."
```

Keep `_get_skill_dirs()` unchanged because it already targets both installed copies by default.

- [ ] **Step 3: Extend the regen test with generic-only assertions**

In `tests/test_regen_skill_index.py`, add this helper after `_SCRIPT`:

```python
def _load_generated_index(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
```

Add `import json` at the top of the file.

Then add this test after `test_skill_index_consistent_with_public_tools`:

```python
@pytest.mark.offline
def test_generated_skill_index_is_generic_only(tmp_path: Path) -> None:
    env = {**os.environ, "SKILL_DIR": str(tmp_path)}

    gen = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert gen.returncode == 0, f"regen failed:\n{gen.stdout}\n{gen.stderr}"

    payload = _load_generated_index(tmp_path)
    assert "harness_tools" not in payload
    assert "training_tools" not in payload

    names = {tool["name"] for tool in payload["simulink_tools"]}
    assert "simulink_bridge_status" not in names
    assert all(name.startswith("simulink_") for name in names)

    excluded = set(payload["meta"]["excluded_project_tools"])
    assert "simulink_bridge_status" in excluded
    assert any(name.startswith("harness_") for name in excluded)
    assert any(name.startswith("training_") for name in excluded)
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_regen_skill_index.py -q
```

Expected after implementation: PASS.

- [ ] **Step 5: Regenerate both installed indexes**

Run:

```powershell
python scripts/regen_skill_index.py
```

Expected output includes both installed paths:

```text
Written C:\Users\27443\.codex\skills\simulink-toolbox\index.json
Written C:\Users\27443\.claude\skills\simulink-toolbox\index.json
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/regen_skill_index.py tests/test_regen_skill_index.py
git commit -m "refactor: generate generic Simulink skill index"
```

Do not commit installed skill files unless they are intentionally tracked in a separate repository. They live outside this repo.

---

### Task 4: Rewrite The Generic Skill Entry File In Both Installs

**Files:**
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md`

- [ ] **Step 1: Replace Codex `SKILL.md` with generic content**

Replace `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md` with:

```markdown
---
name: simulink-toolbox
description: Use when any Simulink, Simscape, Stateflow, .slx, or simulink-tools task begins. Provides a generic MCP-first routing guide for model inspection, editing, wiring, parameter reads/writes, diagnostics, controlled simulation, signal snapshots, screenshots, and MATLAB script execution when no dedicated tool exists.
---

## Work Mode

Prefer MCP tools over direct MATLAB shell commands.

Use `map.md` to select a tool by user intent. Public routing is generic
Simulink routing only; project-specific workflows belong to the active
repository instructions.

For multi-step work, write each step with this shape:

```text
Step N: [goal]
  Tool: [preferred MCP tool]
  Combine: [pre/post tool, if needed]
  Verify: [tool used to confirm completion]
```

Use `simulink_run_script` or `simulink_run_script_async` only when a dedicated
MCP tool cannot do the job or when a tightly coupled multi-step MATLAB operation
is safer as one script.

## References

| When to read | File |
|---|---|
| Any Simulink task | `map.md` |
| New model or compile timing | `patterns/build-and-verify.md` |
| Debug or repair existing model | `patterns/debug-existing-model.md` |
| Trace lines, ports, or connectivity | `patterns/trace-connectivity.md` |
| Parameter sweeps or long simulations | `patterns/param-sweep.md` |

## Self-Check

| Symptom | Response |
|---|---|
| You want to parse `.slx` XML manually | Use `simulink_get_block_tree`, `simulink_explore_block`, or `simulink_trace_port_connections` |
| You want to call `find_system` directly | Check `map.md` first and use the closest MCP discovery tool |
| You do not know which block parameters exist | Use `simulink_library_lookup` before placement, or `simulink_query_params` for model blocks |
| You changed parameters | Verify with `simulink_patch_and_verify` or `simulink_query_params` |
| You need a short runtime check | Use `simulink_compile_diagnostics` or `simulink_step_diagnostics` before long simulation |
| You need logged values at a time point | Use `simulink_signal_snapshot` |
| No dedicated MCP tool matches | Use `simulink_run_script` for short work and `_async` plus `simulink_poll_script` for long work |
```

- [ ] **Step 2: Copy the same content to Claude install**

Run:

```powershell
Copy-Item -LiteralPath 'C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md' -Destination 'C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md'
```

- [ ] **Step 3: Verify both files match**

Run:

```powershell
Compare-Object `
  (Get-Content -LiteralPath 'C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md') `
  (Get-Content -LiteralPath 'C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md')
```

Expected: no output.

---

### Task 5: Rewrite The Generic Tool Map In Both Installs

**Files:**
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`

- [ ] **Step 1: Replace Codex `map.md` with generic routing**

Replace `C:\Users\27443\.codex\skills\simulink-toolbox\map.md` with:

```markdown
# simulink-toolbox: Intent -> Tool Map

Tool inventory source: `index.json`. This file routes generic Simulink user
intent to public MCP tools. It intentionally excludes repository-specific
harness, training, paper-reproduction, and domain-adapter workflows.

---

## Frequent Tools

| Tool | Use For | Not For | Verify? |
|---|---|---|---|
| `simulink_load_model` | Open an existing `.slx` into MATLAB | Creating a new model | No |
| `simulink_get_block_tree` | Browse model hierarchy | Reading parameter values | No |
| `simulink_explore_block` | Inspect one block's type, params, ports, and nearby connections | Full-model traversal | No |
| `simulink_library_lookup` | Discover library block parameters/defaults before placement | Model-level verification | No |
| `simulink_query_params` | Read current block parameters | Writing parameters | No |
| `simulink_patch_and_verify` | Write parameters and immediately verify readback/update | Initial compile diagnosis | Yes |
| `simulink_compile_diagnostics` | Compile/update and report errors or warnings | Modifying the model | Yes |
| `simulink_step_diagnostics` | Short controlled runtime diagnosis | Full long simulation | Yes |
| `simulink_signal_snapshot` | Read logged, ToWorkspace, or temporary block-output values | Domain-specific interpretation | No |
| `simulink_run_script` / `_async` | Escape hatch for unsupported or tightly coupled MATLAB operations | Default model inspection or patching | No |

---

## discover - Model Structure And Paths

- `simulink_loaded_models` - list models loaded in the MATLAB session. NOT: list files on disk.
- `simulink_model_status` - inspect loaded, dirty, file, solver, StopTime, and FastRestart state.
- `simulink_get_block_tree` - get model or subsystem hierarchy. NOT: read parameter values.
- `simulink_explore_block` - inspect one block deeply. NOT: replace full-model traversal.

## construct - Models, Subsystems, Blocks

- `simulink_create_model` - create a new empty model. NOT: open an existing `.slx`.
- `simulink_load_model` - load an existing model. NOT: create a model.
- `simulink_close_model` - close a loaded model. NOT: delete the file.
- `simulink_save_model` - save a loaded model or save to a target path.
- `simulink_add_block` - add one library block to a model. Confirm library paths first.
- `simulink_add_subsystem` - add a subsystem container. NOT: add a normal block.

## wire - Lines, Ports, Connectivity

- `simulink_describe_block_ports` - list block port names, directions, and connection metadata.
- `simulink_trace_port_connections` - trace one port's upstream/downstream signal chain.
- `simulink_connect_ports` - connect ports by name addressing. Port numbering is 1-based.

## modify - Parameters And Deletion

- `simulink_set_block_params` - set block parameters. Verify with `simulink_query_params` or `simulink_patch_and_verify`.
- `simulink_delete_block` - delete a block, optionally with attached lines. Confirm the path first.

## query - Parameters And Values

- `simulink_query_params` - read one or many blocks' parameters. Use `param_names` to validate expected names.
- `simulink_signal_snapshot` - read logged, ToWorkspace, or temporary block-output values at one time point.

## verify - Compile And Configuration

- `simulink_compile_diagnostics` - update/compile and return structured diagnostics.
- `simulink_solver_audit` - inspect solver configuration and related suspects.
- `simulink_patch_and_verify` - write parameter edits, read them back, and optionally run update/smoke simulation.

## diagnose - Runtime And Connectivity Faults

- `simulink_step_diagnostics` - run a short window and classify warnings/errors.
- `simulink_compile_diagnostics` - use for compile-time failures.
- `simulink_trace_port_connections` - use for missing, wrong, or ambiguous wiring.

## workspace - Base Workspace Variables

- `simulink_workspace_set` - set MATLAB base-workspace variables in one structured call. NOT: set block mask parameters.

## runtime - Controlled Simulation

- `simulink_runtime_reset` - reset FastRestart/runtime state without project semantics.
- `simulink_run_window` - run a model over a StartTime/StopTime window.

## capture - Images

- `simulink_screenshot` - capture a Simulink canvas. NOT: capture MATLAB figures.
- `simulink_capture_figure` - capture MATLAB figure windows. NOT: capture Simulink diagrams.

## execute - MATLAB Script Escape Hatch

- `simulink_run_script` - run a short MATLAB script synchronously.
- `simulink_run_script_async` - run a long MATLAB script asynchronously.
- `simulink_poll_script` - poll an async script job.

Use script execution only when at least one condition is true:

1. No dedicated MCP tool covers the operation.
2. The operation is a tightly coupled multi-step MATLAB workflow.
3. A Simulink API is required and the public MCP surface does not expose it.

Do not use script execution for routine model discovery, parameter reads,
parameter writes, compile diagnostics, screenshots, or signal snapshots.

---

## Pitfalls

1. Do not parse `.slx` XML for routine structure or connectivity; use discovery and trace tools.
2. Do not guess block type names; use `simulink_library_lookup` first.
3. Do not assume port numbering starts at 0; Simulink port addressing here is 1-based.
4. Do not run long simulations synchronously; use `_async` and poll.
5. Do not set parameters without readback when correctness matters.
6. Do not leave many models open in one MATLAB session; close models when done.
```

- [ ] **Step 2: Copy the same map to Claude install**

Run:

```powershell
Copy-Item -LiteralPath 'C:\Users\27443\.codex\skills\simulink-toolbox\map.md' -Destination 'C:\Users\27443\.claude\skills\simulink-toolbox\map.md'
```

- [ ] **Step 3: Verify both maps match**

Run:

```powershell
Compare-Object `
  (Get-Content -LiteralPath 'C:\Users\27443\.codex\skills\simulink-toolbox\map.md') `
  (Get-Content -LiteralPath 'C:\Users\27443\.claude\skills\simulink-toolbox\map.md')
```

Expected: no output.

---

### Task 6: Regenerate And Verify Installed Generic Skill Inventories

**Files:**
- Modify: `C:\Users\27443\.codex\skills\simulink-toolbox\index.json`
- Modify: `C:\Users\27443\.claude\skills\simulink-toolbox\index.json`

- [ ] **Step 1: Regenerate both indexes**

Run:

```powershell
python scripts/regen_skill_index.py
```

Expected: writes both installed `index.json` files.

- [ ] **Step 2: Verify generated indexes are current**

Run:

```powershell
python scripts/regen_skill_index.py --check
```

Expected: both installed skill indexes are consistent with generated generic output.

- [ ] **Step 3: Inspect that project-only groups are absent**

Run:

```powershell
Select-String -Path `
  'C:\Users\27443\.codex\skills\simulink-toolbox\index.json',`
  'C:\Users\27443\.claude\skills\simulink-toolbox\index.json' `
  -Pattern 'harness_tools|training_tools|training_bridge|simulink_bridge_status'
```

Expected: no output.

---

### Task 7: Run Full Offline Verification

**Files:**
- Test only.

- [ ] **Step 1: Run focused offline tests**

Run:

```powershell
python -m pytest `
  tests/test_regen_skill_index.py `
  tests/test_simulink_toolbox_skill_boundary.py `
  tests/test_slx_helper_boundary.py `
  tests/test_mcp_tool_helper_coverage.py::test_public_tools_list_nonempty `
  tests/test_mcp_tool_helper_coverage.py::test_all_slx_helpers_exist `
  tests/test_mcp_tool_helper_coverage.py::test_build_chain_not_in_public_tools `
  -q
```

Expected: PASS.

- [ ] **Step 2: Manually confirm repository-specific routing still exists outside the skill**

Run:

```powershell
Select-String -Path 'AGENTS.md' -Pattern 'Model Harness|Smoke Bridge|Training Control Surface|kundur|ne39'
```

Expected: matches confirming project routing remains in repository instructions.

- [ ] **Step 3: Confirm installed skill docs are project-neutral**

Run:

```powershell
python -m pytest tests/test_simulink_toolbox_skill_boundary.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit repo changes**

```powershell
git add `
  scripts/regen_skill_index.py `
  tests/test_regen_skill_index.py `
  tests/test_simulink_toolbox_skill_boundary.py
git commit -m "refactor: keep Simulink toolbox skill generic"
```

Installed skill files under `C:\Users\27443\.codex` and `C:\Users\27443\.claude` are outside this repo. Do not add them to this repo commit.

---

## Self-Review Checklist

- [ ] The plan keeps one skill named `simulink-toolbox`; it does not create a second similar skill.
- [ ] Both installed locations are covered: `.codex` and `.claude`.
- [ ] The generic skill excludes `harness_*`, `training_*`, and `simulink_bridge_status`.
- [ ] Project-specific Yang/VSG routing remains in repository context.
- [ ] The generator remains the single path for both installed `index.json` files.
- [ ] Tests fail before cleanup and pass after cleanup.
- [ ] No MATLAB runtime or Simulink model execution is required for verification.

## Execution Handoff

Plan complete. Recommended execution mode is subagent-driven only if the worker is allowed to modify installed skill directories outside the repository; otherwise execute inline in this session so local paths can be verified directly.
