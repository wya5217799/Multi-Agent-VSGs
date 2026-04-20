# Agent Control Layer Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the repo's Agent layer as a dual-control system (`Model Control` + `Training Control`) with one authoritative manifest and test-enforced navigation, without turning training into a heavyweight parallel harness or overstating the current runtime surface.

**Architecture:** Keep the current Simulink harness as the model-side quality gate, formally acknowledge the existing training protocol/artifact stack as the training-side control line, and place one manifest-driven navigation layer above both. Do not introduce a second authoritative Python reference file for training; use one TOML manifest as the registration source, point shared code-backed reference state at `engine/harness_reference.py`, and keep graph support optional and read-only.

**Tech Stack:** Markdown, TOML, Python, pytest, existing MCP/FastMCP surface, existing training artifact protocol, optional graphify output

---

## Scope

This plan intentionally does **not**:

- redesign RL algorithms
- build a heavyweight training orchestration framework
- turn graph output into a source of truth
- merge model repair and training run control into one task family
- block Agent-layer cleanup on training status bug fixes

This plan **does**:

- fix the Agent-layer narrative mismatch
- create one authoritative control manifest
- make navigation freshness mechanically testable
- acknowledge training as a first-class control line
- defer training runtime bug fixes to a separate follow-up line

## Target State

After this plan lands, the repo should communicate this clearly:

```text
Model Control
  - inspect / patch / diagnose / report / smoke gate

Training Control
  - run lifecycle / verdict / comparison

Navigation
  - one manifest-backed, test-enforced entry layer

Graph
  - optional navigation aid and drift detector only
```

## File Structure

### Core control and navigation

- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\AGENTS.md`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\CLAUDE.md`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\MEMORY.md`
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_control_manifest.toml`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\navigation_manifest.toml`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\scripts\lint_nav.py`
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_agent_control_manifest.py`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_nav_manifest.py`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_nav_integrity.py`

### Optional thin training control surface

- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\mcp_server.py`
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\training_tasks.py`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_mcp_server.py`

### Explicitly deferred follow-up

- Modify later in a separate line:
  - `C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\train_simulink.py`
  - `C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\new_england\train_simulink.py`
  - `C:\Users\27443\Desktop\Multi-Agent  VSGs\utils\evaluate_run.py`
  - training-status related tests

### Optional graph support

- Create later: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\graph-policy.md`

## Recommended PR Split

1. PR 1: Agent-layer narrative rewrite
2. PR 2: Authoritative control manifest + nav lint/tests
3. PR 3: Thin training control surfacing if still needed after tool audit
4. PR 4: Training status semantics bug fix (separate)

### Task 1: Rewrite the Agent-Layer Narrative

**Files:**
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\AGENTS.md`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\CLAUDE.md`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\MEMORY.md`

- [ ] **Step 1: Rewrite `AGENTS.md` scope around two control lines**

Replace the current single-line framing with this structure:

```md
## Scope

- Repo control model: dual control lines
- Model Control governs model correctness, diagnosis, repair, and smoke readiness
- Training Control governs run lifecycle, verdicts, and comparison of training outputs
- Current project phase: model issues still exist, but training is no longer described as a permanent afterthought
```

Expected: `AGENTS.md` stops implying that "mainline = model building only forever".

Constraint: this rewrite must not claim that training already has a full MCP control plane. Current runtime truth is still:
- model-side harness is the strongest agent-facing control surface
- training-side MCP surface is thin and currently centered on smoke bridge behavior plus artifact-side utilities outside MCP

- [ ] **Step 2: Rewrite the default workflow section**

Use wording like:

```md
## Default Working Mode

1. Use Model Control when the question is about model validity, closed-loop semantics, or patching
2. Use Training Control when the question is about run quality, verdicts, comparison, or artifact interpretation
3. Route from training back to model work when training evidence indicates model-side physical or semantic faults
```

Expected: the file reflects the current ambiguous-but-real project phase instead of a false single-mainline story.

Risk note: wording changes in `## Scope` do **not** directly break `tests/test_nav_manifest.py`; that test only checks the `## Start Here` list against `docs/navigation_manifest.toml`. The real risk in Phase 1 is narrative drift from the actual runtime contract.

- [ ] **Step 3: Trim `CLAUDE.md` down to reference use**

Edit `CLAUDE.md` so it:
- points readers back to `AGENTS.md` and manifests
- does not present itself as a parallel control plane
- removes or rewrites statements that frame training as only `train_smoke` in perpetuity

Expected: `CLAUDE.md` becomes a secondary orientation doc, not a competing authority.

- [ ] **Step 4: Keep `MEMORY.md` as an index only**

Remove duplicated routing or default workflow claims. Keep only:
- where key docs live
- where control manifests live
- where history/decisions/devlogs live

- [ ] **Step 5: Review for contradiction**

Read:
- `C:\Users\27443\Desktop\Multi-Agent  VSGs\AGENTS.md`
- `C:\Users\27443\Desktop\Multi-Agent  VSGs\CLAUDE.md`
- `C:\Users\27443\Desktop\Multi-Agent  VSGs\MEMORY.md`

Check that none of them now says:
- training is permanently only smoke
- model work is the only repo mainline
- graph output is authoritative

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md CLAUDE.md MEMORY.md
git commit -m "docs: rewrite agent layer around model and training control"
```

### Task 2: Create One Authoritative Agent Control Manifest

**Files:**
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_control_manifest.toml`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\navigation_manifest.toml`
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_agent_control_manifest.py`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\scripts\lint_nav.py`
- Modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_nav_manifest.py`

- [ ] **Step 1: Add `docs/agent_control_manifest.toml`**

Create one registration source for the two control lines:

```toml
version = 1
reference_py = "engine/harness_reference.py"

[model_control]
entry_doc = "AGENTS.md"
artifact_root = "results/harness"
reference_paths = [
  "docs/harness/2026-04-05-simulink-harness-v1.md",
]
task_family = [
  "scenario_status",
  "model_inspect",
  "model_patch_verify",
  "model_diagnose",
  "model_report",
  "train_smoke_start",
  "train_smoke_poll",
]

[training_control]
entry_doc = "AGENTS.md"
artifact_root = "results/sim_*"
reference_paths = [
  "utils/run_protocol.py",
  "utils/artifact_writer.py",
  "utils/monitor.py",
  "utils/evaluate_run.py",
  "scenarios/kundur/train_simulink.py",
  "scenarios/new_england/train_simulink.py",
]
task_family = [
  "run_lifecycle",
  "run_polling",
  "run_verdict",
  "run_compare",
]
```

Important:
- do **not** create `training_reference.py`
- `reference_py` must point only to `engine/harness_reference.py`
- both control lines share that single code-backed reference anchor
- training-specific entrypoints and artifact paths belong in TOML, not in a second Python reference module

- [ ] **Step 2: Teach navigation manifest about the new control manifest**

Extend `docs/navigation_manifest.toml` with a separate control-layer section such as:

```toml
[agent_control]
manifest = "docs/agent_control_manifest.toml"
reference_py = "engine/harness_reference.py"
```

Do **not** mutate the existing `[[start_here]]` list in this step unless there is a deliberate decision to also update `AGENTS.md` Start Here rendering and its exact-match tests.

Expected: agent navigation now has an explicit place to discover both control lines.

- [ ] **Step 3: Add manifest tests**

Write tests like:

```python
from pathlib import Path
import tomllib

def test_agent_control_manifest_exists():
    assert Path("docs/agent_control_manifest.toml").exists()

def test_agent_control_manifest_reference_py_exists():
    data = tomllib.loads(Path("docs/agent_control_manifest.toml").read_text(encoding="utf-8"))
    assert Path(data["reference_py"]).exists()

def test_agent_control_manifest_reference_paths_exist():
    data = tomllib.loads(Path("docs/agent_control_manifest.toml").read_text(encoding="utf-8"))
    for section in ("model_control", "training_control"):
        for rel in data[section]["reference_paths"]:
            assert Path(rel).exists()

def test_agent_control_manifest_declares_two_control_lines():
    data = tomllib.loads(Path("docs/agent_control_manifest.toml").read_text(encoding="utf-8"))
    assert "model_control" in data
    assert "training_control" in data
```

- [ ] **Step 4: Extend nav lint only where it matters**

Add checks to `scripts/lint_nav.py` for:
- existence of `docs/agent_control_manifest.toml`
- existence of `reference_py` declared by the manifest
- all manifest-declared paths exist
- `AGENTS.md` mentions both `Model Control` and `Training Control`
- `CLAUDE.md` does not claim to override manifests or `AGENTS.md`

Do **not** add an authority-marker metadata system.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_agent_control_manifest.py tests/test_nav_manifest.py tests/test_nav_integrity.py -q
```

Expected: pass

- [ ] **Step 6: Commit**

```bash
git add docs/agent_control_manifest.toml docs/navigation_manifest.toml scripts/lint_nav.py tests/test_agent_control_manifest.py tests/test_nav_manifest.py
git commit -m "test: add single manifest for dual-line agent control"
```

### Task 3: Audit Before Expanding the MCP Tool Surface

**Files:**
- Review: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\mcp_server.py`
- Review: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\harness_tasks.py`
- Review: `C:\Users\27443\Desktop\Multi-Agent  VSGs\utils\run_protocol.py`
- Review: `C:\Users\27443\Desktop\Multi-Agent  VSGs\utils\evaluate_run.py`
- Review: `C:\Users\27443\Desktop\Multi-Agent  VSGs\utils\sidecar.py`
- Modify only if justified: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\mcp_server.py`
- Create only if justified: `C:\Users\27443\Desktop\Multi-Agent  VSGs\engine\training_tasks.py`

- [ ] **Step 1: List current public tools and classify them**

Create a short audit note that answers:
- how many current public MCP tools exist in total
- which current public tools are model-side only
- which are smoke bridge only
- which training-side capabilities already exist outside MCP
- which training-side gaps actually block agent work today

This audit must explicitly inspect whether the existing public surface already covers:
- training launch via `harness_train_smoke_start`
- training polling via `harness_train_smoke_poll`

This audit must specifically evaluate whether adding new MCP tools would reduce confusion or increase it.

- [ ] **Step 2: Decide whether new training tasks are needed**

Only if the audit shows a real gap, add the minimum possible surface.

Allowed first additions:

```text
train_run_evaluate
train_run_compare
```

Do **not** add `train_run_start` or `train_run_poll` unless the audit shows current smoke/start/poll paths are genuinely insufficient.

If `utils/evaluate_run.py` is only used as a CLI and agent work would benefit from structured access, an MCP adapter is reasonable. If agent workflows do not actually need MCP access to it yet, do not wrap it preemptively.

- [ ] **Step 3: If implementing, keep `training_tasks.py` thin**

If created, `engine/training_tasks.py` may only:
- read training artifacts
- call existing helpers such as `evaluate_run.py`
- summarize comparisons across run directories

It must not:
- import model repair code
- mutate Simulink models
- become a second orchestration framework

- [ ] **Step 4: Update MCP tests only if tool surface changes**

Run:

```bash
pytest tests/test_mcp_server.py -q
```

Expected:
- unchanged if no tools were added
- updated and passing if the audited minimum additions were made

- [ ] **Step 5: Commit**

If no tool changes:

```bash
git add docs
git commit -m "docs: record training control tool-surface audit"
```

If thin tool changes were added:

```bash
git add engine/mcp_server.py engine/training_tasks.py tests/test_mcp_server.py
git commit -m "feat: add minimal training control tasks for agents"
```

### Task 4: Optional Graph Integration as Navigation Aid Only

**Files:**
- Create: `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\graph-policy.md`
- Optionally modify: `C:\Users\27443\Desktop\Multi-Agent  VSGs\AGENTS.md`

- [ ] **Step 1: Add a short graph policy**

Create:

```md
# Graph Policy

- Graph output may be used for navigation and drift discovery.
- Graph output is not the authoritative control contract.
- If graph output conflicts with AGENTS.md, manifests, or code-backed references, the graph loses.
- Rebuild graph outputs after control-manifest or MCP-surface changes if graph navigation is in active use.
```

- [ ] **Step 2: Add one pointer from `AGENTS.md`**

Add a one-line note:

```md
For relational navigation and drift discovery, graph output may be consulted as a secondary aid.
```

- [ ] **Step 3: Commit**

```bash
git add docs/agent_layer/graph-policy.md AGENTS.md
git commit -m "docs: define graph as optional navigation aid"
```

## Deferred Follow-Up Plan

This restructure intentionally does **not** block on the following training bug line:

- `monitor_stop` should not end as `completed`
- `training_status.json` semantics should distinguish full completion vs interruption
- `evaluate_run.py` and training status should align on interrupted runs

That follow-up should be handled as a separate plan or PR after the Agent-layer control rewrite lands.

It may land before, after, or in parallel with Phase 1-3 work because it is a training-runtime correctness fix, not an Agent-layer dependency.

## Review Checklist

- There is only one new authoritative registration source: `docs/agent_control_manifest.toml`
- The plan does not require full model stabilization before Agent-layer cleanup
- The plan does not create a heavyweight parallel training harness
- The plan does not add a doc-marker maintenance regime
- Graph stays optional and non-authoritative
- Training status bug fixes are decoupled from Agent-layer restructure

## Recommended Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
