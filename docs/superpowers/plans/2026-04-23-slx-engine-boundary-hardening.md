# SLX Engine Boundary Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the boundary between general Simulink MCP primitives, VSG bridge adapters, and Training Control Surface utilities without changing paper reproduction behavior.

**Architecture:** Keep the existing three-layer design: MATLAB helpers remain the lowest execution layer, `engine/mcp_simulink_tools.py` remains the public MCP facade, and `engine/simulink_bridge.py` remains the VSG/RL adapter used by `env/simulink`. This plan adds filesystem separation and tests for the helper boundary, fixes two small Training Control drift points, and keeps both installed `simulink-toolbox` skills in parity: `C:\Users\27443\.codex\skills\simulink-toolbox` and `C:\Users\27443\.claude\skills\simulink-toolbox`.

**Tech Stack:** Python 3, pytest, MATLAB Engine API, MATLAB `.m` helper files, FastMCP, existing `simulink-toolbox` skill validation script.

---

## Design Document Decision

Do not create a new design document for this work.

The design decision already exists in `docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md`. This implementation plan applies that decision. If the implementation changes the public MCP tool surface, the `AGENTS.md` control terminology, or the accepted `scenario_id` contract, update the existing decision file instead of creating a parallel design record.

Anti-drift justification: this work standardizes a repeated AI operation on the repository by making "general Simulink primitive" versus "VSG bridge adapter" mechanically visible and test-enforced.

## Design Principles Used

This plan follows patterns from well-maintained tool/plugin systems:

- Single source of truth for public inventory: `engine.mcp_server.PUBLIC_TOOLS` generates skill `index.json`.
- Thin routing docs: skill `map.md` routes intent to tools but does not own model, training, or paper logic.
- Compatibility adapters are isolated: VSG bridge helpers keep stable names but move out of the general helper root.
- Verification is automated across installs: both Codex and Claude skill copies must pass the same generated-index and map consistency checks.
- Public facade remains stable: no public `simulink_*`, `harness_*`, or `training_*` tool is renamed in this plan.

## File Structure

Files and responsibilities after this plan:

- `slx_helpers/`
  - Root contains general Simulink primitives only: block, line, port, parameter, workspace, runtime, signal, diagnostics, save/status, screenshot, and figure helpers.
- `slx_helpers/vsg_bridge/`
  - Contains VSG/RL compatibility adapters used by `engine/simulink_bridge.py`: episode warmup, step/read, state extraction, bridge config, FastRestart wrapper, and legacy VSG model validation.
- `engine/matlab_session.py`
  - Adds both helper paths to MATLAB explicitly. It does not use recursive `genpath`.
- `engine/mcp_simulink_tools.py`
  - Stays as the public `simulink_*` facade and must not directly call VSG bridge helper names.
- `engine/training_launch.py`
  - Derives model path and train entry from `scenarios/contract.py`, not duplicate local maps.
- `engine/training_tasks.py`
  - Keeps `scenario_id` docs aligned with the contract: only `kundur` or `ne39`.
- `tests/test_slx_helper_boundary.py`
  - New static boundary tests for helper placement and public MCP calls.
- Existing tests under `tests/test_mcp_simulink_tools.py`, `tests/test_training_launch.py`, and `tests/test_training_tasks.py`
  - Add focused regression tests for path injection and scenario-id drift.
- `scripts/regen_skill_index.py`
  - Already targets both Codex and Claude skill directories by default. This plan keeps that behavior and adds verification steps around it.
- `C:\Users\27443\.codex\skills\simulink-toolbox`
  - Codex-side routing skill. Its `index.json`, `map.md`, and patterns must remain consistent.
- `C:\Users\27443\.claude\skills\simulink-toolbox`
  - Claude-side routing skill. It must stay semantically aligned with the Codex copy for tool inventory and route boundaries.

## Task 1: Add Boundary Tests For MATLAB Helper Placement

**Files:**
- Create: `tests/test_slx_helper_boundary.py`

- [ ] **Step 1: Write the failing boundary tests**

Create `tests/test_slx_helper_boundary.py` with this exact content:

```python
"""Static boundary tests for slx_helpers.

The repository has two MATLAB helper families:
- general Simulink primitives in slx_helpers/
- VSG/RL bridge adapters in slx_helpers/vsg_bridge/

These tests keep the directory boundary mechanical so the general MCP layer
does not drift back into VSG-specific helper calls.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "slx_helpers"
VSG_DIR = CORE_DIR / "vsg_bridge"

VSG_BRIDGE_HELPERS = {
    "slx_warmup.m",
    "slx_step_and_read.m",
    "slx_extract_state.m",
    "slx_build_bridge_config.m",
    "slx_validate_model.m",
    "slx_fastrestart_reset.m",
    "slx_episode_warmup.m",
}

CORE_HELPERS_REQUIRED = {
    "slx_add_block.m",
    "slx_add_subsystem.m",
    "slx_batch_query.m",
    "slx_compile_diagnostics.m",
    "slx_connect_blocks.m",
    "slx_delete_block.m",
    "slx_describe_block_ports.m",
    "slx_get_block_tree.m",
    "slx_patch_and_verify.m",
    "slx_run_window.m",
    "slx_signal_snapshot.m",
    "slx_workspace_set.m",
}


def test_vsg_bridge_helpers_live_in_vsg_bridge_subdir():
    assert VSG_DIR.is_dir(), f"missing VSG bridge helper dir: {VSG_DIR}"

    for helper_name in sorted(VSG_BRIDGE_HELPERS):
        root_path = CORE_DIR / helper_name
        bridge_path = VSG_DIR / helper_name
        assert not root_path.exists(), (
            f"legacy VSG helper still in slx_helpers root: {helper_name}"
        )
        assert bridge_path.exists(), (
            f"legacy VSG helper missing from vsg_bridge dir: {helper_name}"
        )


def test_core_helpers_remain_in_slx_helpers_root():
    for helper_name in sorted(CORE_HELPERS_REQUIRED):
        assert (CORE_DIR / helper_name).exists(), (
            f"general Simulink helper missing from slx_helpers root: {helper_name}"
        )


def test_public_mcp_tools_do_not_call_vsg_bridge_helpers_directly():
    tool_text = (ROOT / "engine" / "mcp_simulink_tools.py").read_text(
        encoding="utf-8"
    )

    for helper_name in sorted(VSG_BRIDGE_HELPERS):
        helper_stem = helper_name.removesuffix(".m")
        assert f'"{helper_stem}"' not in tool_text
        assert f"'{helper_stem}'" not in tool_text
```

- [ ] **Step 2: Run the new tests and confirm the expected failure**

Run:

```bash
python -m pytest tests/test_slx_helper_boundary.py -q
```

Expected result before moving files:

```text
FAILED tests/test_slx_helper_boundary.py::test_vsg_bridge_helpers_live_in_vsg_bridge_subdir
AssertionError: legacy VSG helper still in slx_helpers root: slx_build_bridge_config.m
```

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_slx_helper_boundary.py
git commit -m "test: lock slx helper boundary"
```

## Task 2: Move VSG Bridge MATLAB Helpers Into A Subdirectory

**Files:**
- Move: `slx_helpers/slx_warmup.m` -> `slx_helpers/vsg_bridge/slx_warmup.m`
- Move: `slx_helpers/slx_step_and_read.m` -> `slx_helpers/vsg_bridge/slx_step_and_read.m`
- Move: `slx_helpers/slx_extract_state.m` -> `slx_helpers/vsg_bridge/slx_extract_state.m`
- Move: `slx_helpers/slx_build_bridge_config.m` -> `slx_helpers/vsg_bridge/slx_build_bridge_config.m`
- Move: `slx_helpers/slx_validate_model.m` -> `slx_helpers/vsg_bridge/slx_validate_model.m`
- Move: `slx_helpers/slx_fastrestart_reset.m` -> `slx_helpers/vsg_bridge/slx_fastrestart_reset.m`
- Move: `slx_helpers/slx_episode_warmup.m` -> `slx_helpers/vsg_bridge/slx_episode_warmup.m`
- Modify: `slx_helpers/README.md`

- [ ] **Step 1: Move helper files with git**

Run:

```bash
New-Item -ItemType Directory -Force slx_helpers/vsg_bridge
git mv slx_helpers/slx_warmup.m slx_helpers/vsg_bridge/slx_warmup.m
git mv slx_helpers/slx_step_and_read.m slx_helpers/vsg_bridge/slx_step_and_read.m
git mv slx_helpers/slx_extract_state.m slx_helpers/vsg_bridge/slx_extract_state.m
git mv slx_helpers/slx_build_bridge_config.m slx_helpers/vsg_bridge/slx_build_bridge_config.m
git mv slx_helpers/slx_validate_model.m slx_helpers/vsg_bridge/slx_validate_model.m
git mv slx_helpers/slx_fastrestart_reset.m slx_helpers/vsg_bridge/slx_fastrestart_reset.m
git mv slx_helpers/slx_episode_warmup.m slx_helpers/vsg_bridge/slx_episode_warmup.m
```

Expected result:

```text
slx_helpers/vsg_bridge contains the seven moved .m files
slx_helpers root no longer contains those seven .m files
```

- [ ] **Step 2: Update the helper README**

Replace `slx_helpers/README.md` with:

```markdown
# slx_helpers - General Simulink Operation Core

Root-level helpers in this directory are general Simulink primitives. They
operate on model, block, line, port, parameter, workspace variable,
SimulationInput, SimulationOutput, timeseries, solver, FastRestart,
diagnostics, screenshot, and figure concepts.

Root-level helpers must not introduce new APIs whose primary contract is
expressed in VSG/RL terms: agent, episode, reward, M/D action, Pe, omega,
rocof, delta, Kundur, or NE39.

Model-specific logic belongs in Python project adapters:

- `engine/simulink_bridge.py`
- `env/simulink/`
- `scenarios/*/config_simulink.py`

Reusable one-scenario diagnostics belong under:

- `probes/kundur/`
- `probes/ne39/`

## Directory Boundary

```text
slx_helpers/
  *.m
    General Simulink primitives only.

slx_helpers/vsg_bridge/
  *.m
    VSG/RL bridge compatibility adapters used by engine/simulink_bridge.py.
```

## VSG Bridge Compatibility Adapters

The following helpers are retained for the active Yang 2023 reproduction path
and are not general Simulink primitives:

- `vsg_bridge/slx_warmup.m`
- `vsg_bridge/slx_step_and_read.m`
- `vsg_bridge/slx_extract_state.m`
- `vsg_bridge/slx_build_bridge_config.m`
- `vsg_bridge/slx_validate_model.m`
- `vsg_bridge/slx_fastrestart_reset.m`
- `vsg_bridge/slx_episode_warmup.m`

Status: retained for VSG bridge compatibility. New generic MCP tools must not
call these helpers directly.
```

- [ ] **Step 3: Run the boundary tests**

Run:

```bash
python -m pytest tests/test_slx_helper_boundary.py -q
```

Expected result:

```text
3 passed
```

- [ ] **Step 4: Commit the helper move**

```bash
git add slx_helpers tests/test_slx_helper_boundary.py
git commit -m "refactor: separate vsg bridge slx helpers"
```

## Task 3: Add Both Helper Paths To MATLAB Sessions

**Files:**
- Modify: `engine/matlab_session.py`
- Modify: `tests/test_mcp_simulink_tools.py`

- [ ] **Step 1: Add a failing test for MATLAB path setup**

Append this test class near the existing MCP tool tests in `tests/test_mcp_simulink_tools.py`:

```python
class TestMatlabSessionHelperPaths:
    def setup_method(self):
        from engine.matlab_session import MatlabSession
        MatlabSession._instances.clear()

    @patch("engine.matlab_session.matlab_engine", create=True)
    def test_connect_adds_core_and_vsg_bridge_helper_paths(self, mock_me):
        from engine.matlab_session import MatlabSession

        mock_eng = MagicMock()
        mock_eng.sqrt = MagicMock(return_value=2.0)
        mock_me.start_matlab.return_value = mock_eng

        session = MatlabSession.get()
        assert session.call("sqrt", 4.0) == 2.0

        repo_root = Path(__file__).resolve().parents[1]
        addpath_paths = [call.args[0] for call in mock_eng.addpath.call_args_list]
        assert str(repo_root / "slx_helpers") in addpath_paths
        assert str(repo_root / "slx_helpers" / "vsg_bridge") in addpath_paths
```

- [ ] **Step 2: Run the path test and confirm the expected failure**

Run:

```bash
python -m pytest tests/test_mcp_simulink_tools.py::TestMatlabSessionHelperPaths::test_connect_adds_core_and_vsg_bridge_helper_paths -q
```

Expected result before implementation:

```text
FAILED ... AssertionError: '.../slx_helpers/vsg_bridge' not in addpath_paths
```

- [ ] **Step 3: Update `MatlabSession` path injection**

In `engine/matlab_session.py`, replace the single `_helpers_path` field with an explicit list.

Use this implementation inside `MatlabSession.__init__`:

```python
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._helper_paths: list[str] = [
            os.path.join(project_root, "slx_helpers"),
            os.path.join(project_root, "slx_helpers", "vsg_bridge"),
        ]
```

Then replace the current "Auto-addpath for slx_helpers" block in `_connect()` with:

```python
        # Auto-addpath for MATLAB helper layers. Keep these explicit instead
        # of using genpath so cache/build folders are not added accidentally.
        for helper_path in self._helper_paths:
            if os.path.isdir(helper_path):
                self._eng.addpath(helper_path, nargout=0)
                logger.debug("Added to MATLAB path: %s", helper_path)
            else:
                logger.warning("MATLAB helper dir not found: %s", helper_path)
```

Also update the module docstring bullet from:

```python
- Auto addpath for slx_helpers/ on first connect
```

to:

```python
- Auto addpath for slx_helpers/ and slx_helpers/vsg_bridge/ on first connect
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_mcp_simulink_tools.py::TestMatlabSessionHelperPaths tests/test_slx_helper_boundary.py -q
```

Expected result:

```text
4 passed
```

- [ ] **Step 5: Commit the MATLAB path update**

```bash
git add engine/matlab_session.py tests/test_mcp_simulink_tools.py
git commit -m "fix: add vsg bridge helpers to matlab path"
```

## Task 4: Derive Training Launch Paths From ScenarioContract

**Files:**
- Modify: `engine/training_launch.py`
- Modify: `tests/test_training_launch.py`

- [ ] **Step 1: Add failing tests against duplicate launch maps**

In `tests/test_training_launch.py`, add this test under `TestGetTrainingLaunchStatus`:

```python
    def test_training_launch_uses_scenario_contract_instead_of_duplicate_maps(self):
        import engine.training_launch as tl

        assert not hasattr(tl, "_TRAIN_ENTRIES")
        assert not hasattr(tl, "_MODEL_PATHS")
```

Replace `test_fallback_train_entry_from_builtin_map` with:

```python
    def test_fallback_train_entry_from_scenario_contract(self, monkeypatch, tmp_path):
        """When harness ref has no training_entry key, use scenarios.contract."""
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference", lambda sid: _fake_ref(sid))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("kundur")
        assert result["train_entry"] == "scenarios/kundur/train_simulink.py"
        assert result["model_name"] == "kundur_vsg"
        assert result["launch"]["script"] == "scenarios/kundur/train_simulink.py"
```

Replace `test_launch_is_none_when_no_train_entry` with:

```python
    def test_known_contract_scenario_has_launch_when_ref_lacks_train_entry(
        self, monkeypatch, tmp_path
    ):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference", lambda sid: _fake_ref(sid))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("ne39")
        assert result["launch"] is not None
        assert result["launch"]["script"] == "scenarios/new_england/train_simulink.py"
```

- [ ] **Step 2: Run the launch tests and confirm the expected failure**

Run:

```bash
python -m pytest tests/test_training_launch.py::TestGetTrainingLaunchStatus::test_training_launch_uses_scenario_contract_instead_of_duplicate_maps -q
```

Expected result before implementation:

```text
FAILED ... assert not hasattr(tl, "_TRAIN_ENTRIES")
```

- [ ] **Step 3: Replace local maps with contract-derived paths**

In `engine/training_launch.py`, remove `_TRAIN_ENTRIES` and `_MODEL_PATHS`.

Add this import:

```python
from scenarios.contract import get_contract
```

Add this helper near `_PYTHON_EXE`:

```python
def _scenario_launch_facts(scenario_id: str) -> tuple[str, str, Path]:
    """Return contract-derived train entry, model name, and model file path."""
    contract = get_contract(scenario_id)
    train_entry = contract.train_entry.as_posix()
    model_name = contract.model_name
    model_file = contract.model_dir / f"{contract.model_name}.slx"
    return train_entry, model_name, model_file
```

Inside `get_training_launch_status()`, replace the `facts`, `train_entry`, `model_name`, and model path block with:

```python
    try:
        contract_train_entry, contract_model_name, contract_model_file = (
            _scenario_launch_facts(scenario_id)
        )
    except ValueError:
        return {
            "supported": False,
            "scenario_id": scenario_id,
            "error": "unknown scenario_id",
        }

    facts = {item["key"]: item["value"] for item in ref.get("reference_items", [])}

    train_entry = facts.get("training_entry", contract_train_entry)
    model_name = facts.get("model_name", contract_model_name)

    slx_abs = _PROJECT_ROOT / contract_model_file
    model_exists = slx_abs.exists()
```

- [ ] **Step 4: Run launch tests**

Run:

```bash
python -m pytest tests/test_training_launch.py -q
```

Expected result:

```text
all tests in tests/test_training_launch.py pass
```

- [ ] **Step 5: Commit the launch cleanup**

```bash
git add engine/training_launch.py tests/test_training_launch.py
git commit -m "refactor: derive training launch facts from scenario contract"
```

## Task 5: Fix Training Control Scenario-ID Documentation Drift

**Files:**
- Modify: `engine/training_tasks.py`
- Modify: `tests/test_training_tasks.py`

- [ ] **Step 1: Add a doc drift regression test**

Append this test near the top of `tests/test_training_tasks.py` after the fixtures:

```python
def test_training_compare_runs_doc_uses_contract_scenario_ids():
    from engine.training_tasks import training_compare_runs

    doc = training_compare_runs.__doc__ or ""
    assert '"kundur" or "ne39"' in doc
    assert 'e.g. "sim_kundur"' not in doc
```

Also add this functional guard:

```python
def test_training_compare_runs_passes_canonical_scenario_id(monkeypatch):
    import engine.training_tasks as tt

    calls = []

    def fake_evaluate_run(scenario_id, run_id):
        calls.append((scenario_id, run_id))
        return {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "verdict": "PASS",
            "episode_count": 10,
            "metrics": {"reward_mean_recent": -10.0},
            "reasons": [],
        }

    monkeypatch.setattr(tt, "training_evaluate_run", fake_evaluate_run)

    result = tt.training_compare_runs("kundur", ["run_a", "run_b"])

    assert calls == [("kundur", "run_a"), ("kundur", "run_b")]
    assert result["scenario_id"] == "kundur"
    assert result["best_run"] == "run_a"
```

- [ ] **Step 2: Run the doc drift test and confirm the expected failure**

Run:

```bash
python -m pytest tests/test_training_tasks.py::test_training_compare_runs_doc_uses_contract_scenario_ids -q
```

Expected result before implementation:

```text
FAILED ... assert 'e.g. "sim_kundur"' not in doc
```

- [ ] **Step 3: Fix the docstring**

In `engine/training_tasks.py`, change the `training_compare_runs()` docstring argument section from:

```python
    Args:
        scenario_id: e.g. "sim_kundur"
        run_ids: list of run directory names to compare
```

to:

```python
    Args:
        scenario_id: "kundur" or "ne39"
        run_ids: list of run directory names to compare
```

- [ ] **Step 4: Run training task tests**

Run:

```bash
python -m pytest tests/test_training_tasks.py -q
```

Expected result:

```text
all tests in tests/test_training_tasks.py pass
```

- [ ] **Step 5: Commit the doc drift fix**

```bash
git add engine/training_tasks.py tests/test_training_tasks.py
git commit -m "fix: align training scenario id docs"
```

## Task 6: Verify Codex And Claude Skill Parity

**Files:**
- Modify only if verification fails: `C:\Users\27443\.codex\skills\simulink-toolbox\index.json`
- Modify only if verification fails: `C:\Users\27443\.claude\skills\simulink-toolbox\index.json`
- Modify only if routing prose is out of sync: `C:\Users\27443\.codex\skills\simulink-toolbox\map.md`
- Modify only if routing prose is out of sync: `C:\Users\27443\.claude\skills\simulink-toolbox\map.md`
- Modify only if routing prose is out of sync: `C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md`
- Modify only if routing prose is out of sync: `C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md`

- [ ] **Step 1: Check generated tool inventory for both skill installs**

Run:

```bash
python scripts/regen_skill_index.py --check
```

Expected result:

```text
OK: C:\Users\27443\.codex\skills\simulink-toolbox\index.json is consistent with PUBLIC_TOOLS.
OK: C:\Users\27443\.claude\skills\simulink-toolbox\index.json is consistent with PUBLIC_TOOLS.
```

If the command reports a diff, regenerate both indexes:

```bash
python scripts/regen_skill_index.py
```

Expected regeneration result:

```text
Written C:\Users\27443\.codex\skills\simulink-toolbox\index.json (43 tools total).
Written C:\Users\27443\.claude\skills\simulink-toolbox\index.json (43 tools total).
```

- [ ] **Step 2: Check route consistency for Codex skill**

Run:

```bash
python C:\Users\27443\.codex\skills\simulink-toolbox\validate_consistency.py
```

Expected result:

```text
All checks passed. 43 tools, 5 patterns, 43 map entries consistent.
```

- [ ] **Step 3: Check route consistency for Claude skill**

Run:

```bash
python C:\Users\27443\.claude\skills\simulink-toolbox\validate_consistency.py
```

Expected result:

```text
All checks passed. 43 tools, 5 patterns, 43 map entries consistent.
```

- [ ] **Step 4: Ensure both skill entry docs preserve the project boundary rule**

Run:

```bash
Select-String -Path C:\Users\27443\.codex\skills\simulink-toolbox\SKILL.md,C:\Users\27443\.claude\skills\simulink-toolbox\SKILL.md -Pattern "General Simulink tasks use"
Select-String -Path C:\Users\27443\.codex\skills\simulink-toolbox\map.md,C:\Users\27443\.claude\skills\simulink-toolbox\map.md -Pattern "Project-specific entry points"
```

Expected result:

```text
Both SKILL.md files include the "General Simulink tasks use simulink_* tools only" boundary rule.
Both map.md files include the "Project-specific entry points" section.
```

- [ ] **Step 5: Commit repo-side skill verification changes only if repo files changed**

If only files under `C:\Users\27443\.codex\skills\...` or `C:\Users\27443\.claude\skills\...` changed, do not create a repository commit for those external skill files. If `scripts/regen_skill_index.py` or repo tests changed, commit them:

```bash
git add scripts/regen_skill_index.py tests/test_regen_skill_index.py
git commit -m "test: verify simulink skill index parity"
```

## Task 7: Update Existing Boundary Decision And Run Full Verification

**Files:**
- Modify: `docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md`

- [ ] **Step 1: Update the existing decision document**

In `docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md`, change:

```markdown
Adopted. General MCP primitives are implemented; VSG helpers remain as project
adapter compatibility wrappers.
```

to:

```markdown
Adopted. General MCP primitives are implemented; VSG helpers remain as project
adapter compatibility wrappers under `slx_helpers/vsg_bridge/`.
```

Then replace this paragraph:

```markdown
Existing VSG/RL helpers may remain temporarily as compatibility wrappers, but
new general MCP tools must expose general Simulink concepts first.
```

with:

```markdown
Existing VSG/RL helpers may remain as compatibility wrappers under
`slx_helpers/vsg_bridge/`, but new general MCP tools must expose general
Simulink concepts first and must not call those adapter helpers directly.
```

- [ ] **Step 2: Run static and unit verification**

Run:

```bash
python -m pytest tests/test_slx_helper_boundary.py tests/test_mcp_simulink_tools.py tests/test_simulink_bridge.py tests/test_training_launch.py tests/test_training_tasks.py tests/test_agent_control_manifest.py tests/test_nav_manifest.py tests/test_regen_skill_index.py -m "not slow" -q
```

Expected result:

```text
all selected non-slow tests pass
```

- [ ] **Step 3: Run simulink-toolbox consistency verification for both installs**

Run:

```bash
python scripts/regen_skill_index.py --check
python C:\Users\27443\.codex\skills\simulink-toolbox\validate_consistency.py
python C:\Users\27443\.claude\skills\simulink-toolbox\validate_consistency.py
```

Expected result:

```text
Both installed index.json files are consistent with PUBLIC_TOOLS.
All checks passed. 43 tools, 5 patterns, 43 map entries consistent.
All checks passed. 43 tools, 5 patterns, 43 map entries consistent.
```

- [ ] **Step 4: Run a clean git status check**

Run:

```bash
git status --short
```

Expected result:

```text
Only the files changed by this plan are listed.
```

- [ ] **Step 5: Commit the decision update and final verification notes**

```bash
git add docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md
git commit -m "docs: record slx helper boundary implementation"
```

## Final Verification Commands

Run these before declaring the implementation complete:

```bash
python -m pytest tests/test_slx_helper_boundary.py tests/test_mcp_simulink_tools.py tests/test_simulink_bridge.py tests/test_training_launch.py tests/test_training_tasks.py tests/test_agent_control_manifest.py tests/test_nav_manifest.py tests/test_regen_skill_index.py -m "not slow" -q
python scripts/regen_skill_index.py --check
python C:\Users\27443\.codex\skills\simulink-toolbox\validate_consistency.py
python C:\Users\27443\.claude\skills\simulink-toolbox\validate_consistency.py
git status --short
```

Expected evidence:

```text
pytest exits 0
both installed skill indexes are consistent with PUBLIC_TOOLS
both simulink-toolbox consistency checks exit 0
git status lists only intentional changed files before final commit, or is clean after final commit
```

## Self-Review

Spec coverage:

- General Simulink versus VSG adapter boundary is covered by Tasks 1, 2, and 3.
- Training Control Surface path drift is covered by Task 4.
- Training Control Surface `scenario_id` wording drift is covered by Task 5.
- Codex and Claude skill parity is covered by Task 6.
- Existing design-document policy is covered by Task 7 without creating a duplicate design document.

Placeholder scan:

- The plan contains no open implementation placeholders.
- Each code change step includes exact target files and concrete code.
- Each verification step includes exact commands and expected outcomes.

Type and naming consistency:

- `scenario_id` remains `kundur` or `ne39`.
- VSG bridge MATLAB helpers keep their original function names, so `engine/simulink_bridge.py` does not need call-site changes after MATLAB path injection is updated.
- Public MCP tool names remain unchanged.
