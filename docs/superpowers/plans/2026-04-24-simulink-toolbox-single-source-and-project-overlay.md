# Simulink Toolbox Single-Source And Project Overlay Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate dual maintenance of the installed `simulink-toolbox` skill, keep the global skill strictly generic, fix hook/config drift, and move Yang/VSG model-specific routing into a dedicated repository folder.

**Architecture:** Use one canonical shared skill directory at `C:\Users\27443\.shared-skills\simulink-toolbox`, then make `C:\Users\27443\.codex\skills\simulink-toolbox` and `C:\Users\27443\.claude\skills\simulink-toolbox` junctions to it. Keep only generic Simulink content in that shared skill. Move repo/model-specific routing into `docs/agent_layer/simulink-project-routing/`, with a dedicated `models/` subfolder for Kundur and NE39 specifics.

**Tech Stack:** PowerShell, Python 3, junctions on Windows, Markdown skill files, repo pytest guards, local hook configuration in `C:\Users\27443\.codex\hooks.json` and `C:\Users\27443\.claude\settings.json`.

---

## Problem Statement

The current state has four maintenance problems:

1. The same skill exists as two independent directories:
   - `C:\Users\27443\.codex\skills\simulink-toolbox`
   - `C:\Users\27443\.claude\skills\simulink-toolbox`

2. The installed generic skill still contains project-specific/model-specific content, especially `training-smoke-debug.md` and prior Kundur/NE39 trigger logic.

3. The current consistency guard does not cover hook wiring, install layout, or encoding/layout drift.

4. Platform-specific and project-specific concerns are mixed together:
   - generic Simulink routing
   - Codex-only hook behavior
   - Claude-only hook behavior
   - Yang/VSG/Kundur/NE39 routing

The target state must fix all four at once. Partial cleanup is not acceptable.

---

## Target Layout

### Shared Installed Skill

```text
C:\Users\27443\.shared-skills\simulink-toolbox\
  SKILL.md
  map.md
  index.json
  INVARIANTS.md
  validate_consistency.py
  validate_layout.py
  hooks\
    README.md
    codex\
      codex_simulink_hook.py
    claude\
      pre-tool-use.sh
      user-prompt-submit.sh
  patterns\
    build-and-verify.md
    debug-existing-model.md
    param-sweep.md
    trace-connectivity.md
```

### Installed Entry Points

```text
C:\Users\27443\.codex\skills\simulink-toolbox   -> junction -> C:\Users\27443\.shared-skills\simulink-toolbox
C:\Users\27443\.claude\skills\simulink-toolbox  -> junction -> C:\Users\27443\.shared-skills\simulink-toolbox
```

### Repository Project Overlay

```text
docs\agent_layer\simulink-project-routing\
  README.md
  training-smoke-debug.md
  models\
    kundur.md
    ne39.md
```

Rules:

- The shared installed skill contains only generic Simulink routing.
- Platform-specific hook files live under `hooks\codex\` and `hooks\claude\`.
- Project/model-specific routing does not live in the shared installed skill.
- Kundur/NE39 details live under `docs\agent_layer\simulink-project-routing\models\`.

---

## File Responsibility Map

| Path | Responsibility |
| --- | --- |
| `C:\Users\27443\.shared-skills\simulink-toolbox\SKILL.md` | Generic entrypoint only; trigger conditions, not project workflow |
| `C:\Users\27443\.shared-skills\simulink-toolbox\map.md` | Generic intent-to-tool routing only |
| `C:\Users\27443\.shared-skills\simulink-toolbox\patterns\*.md` | Generic Simulink patterns only |
| `C:\Users\27443\.shared-skills\simulink-toolbox\hooks\codex\codex_simulink_hook.py` | Codex-only hook logic |
| `C:\Users\27443\.shared-skills\simulink-toolbox\hooks\claude\*.sh` | Claude-only hook logic |
| `C:\Users\27443\.shared-skills\simulink-toolbox\validate_consistency.py` | Generic skill doc/index consistency only |
| `C:\Users\27443\.shared-skills\simulink-toolbox\validate_layout.py` | Install layout, hook path, junction, and UTF-8 validation |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing\README.md` | Repo-only overlay boundary and routing entry |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing\training-smoke-debug.md` | Repo-only training/smoke workflow previously leaked into the generic skill |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing\models\kundur.md` | Kundur-only facts and routing |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing\models\ne39.md` | NE39-only facts and routing |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\scripts\regen_skill_index.py` | Generate one generic `index.json`; dedupe aliased install paths |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_simulink_toolbox_skill_boundary.py` | Guard generic skill boundary |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_regen_skill_index.py` | Guard generic index generation |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\tests\test_simulink_toolbox_shared_layout.py` | Guard single-source install layout |
| `C:\Users\27443\Desktop\Multi-Agent  VSGs\scripts\install_shared_simulink_toolbox.ps1` | Safe migration/reinstall for the shared skill junction layout |

---

## Task 1: Record The New Layout Decision

**Files:**
- Create: `docs/decisions/2026-04-24-simulink-toolbox-single-source-layout.md`
- Modify: `MEMORY.md`

- [ ] **Step 1: Write the decision record**

Create `docs/decisions/2026-04-24-simulink-toolbox-single-source-layout.md` with these sections:

```markdown
# 2026-04-24 Simulink Toolbox Single-Source Layout

## Status

Adopted.

## Context

The installed `simulink-toolbox` skill is currently duplicated under both
`~/.codex/skills/` and `~/.claude/skills/`. This causes content drift, hook
drift, and repeated manual edits.

The same skill also mixes three concerns:

- generic Simulink routing
- platform-specific hook implementation
- Yang/VSG/Kundur/NE39 project routing

## Decision

Use one canonical installed skill directory:

- `C:\Users\27443\.shared-skills\simulink-toolbox`

Use directory junctions for:

- `C:\Users\27443\.codex\skills\simulink-toolbox`
- `C:\Users\27443\.claude\skills\simulink-toolbox`

Keep generic Simulink content in the shared installed skill.

Move project/model-specific routing to:

- `docs/agent_layer/simulink-project-routing/`
- `docs/agent_layer/simulink-project-routing/models/`

## Consequences

- Future edits happen in one place only.
- Platform-specific hooks remain supported via subfolders under one shared tree.
- Generic skill validation and project overlay validation become separable.
```

- [ ] **Step 2: Add the decision to `MEMORY.md`**

Add a new bullet under **Decisions**:

```markdown
- [2026-04-24 Simulink toolbox single-source layout](docs/decisions/2026-04-24-simulink-toolbox-single-source-layout.md)
```

- [ ] **Step 3: Verify the index entry**

Run:

```powershell
Select-String -Path 'C:\Users\27443\Desktop\Multi-Agent  VSGs\MEMORY.md' -Pattern 'single-source layout'
```

Expected: one match.

- [ ] **Step 4: Commit**

```powershell
git add docs/decisions/2026-04-24-simulink-toolbox-single-source-layout.md MEMORY.md
git commit -m "docs: define shared Simulink skill install layout"
```

---

## Task 2: Add A Safe Installer For The Shared Skill Layout

**Files:**
- Create: `scripts/install_shared_simulink_toolbox.ps1`

- [ ] **Step 1: Write the installer script**

Create `scripts/install_shared_simulink_toolbox.ps1` with these parameters:

```powershell
param(
  [string]$SharedRoot = 'C:\Users\27443\.shared-skills\simulink-toolbox',
  [string]$CodexPath = 'C:\Users\27443\.codex\skills\simulink-toolbox',
  [string]$ClaudePath = 'C:\Users\27443\.claude\skills\simulink-toolbox',
  [string]$BackupRoot = 'C:\Users\27443\.shared-skills\backups',
  [switch]$DryRun
)
```

The script must do this in order:

1. Resolve absolute paths.
2. Create `BackupRoot\<timestamp>\`.
3. If `SharedRoot` does not exist:
   - copy the current Codex skill tree into `SharedRoot`
   - if Codex copy is missing, use Claude copy instead
4. Back up both install trees before replacing them.
5. Remove the current install directories only after backup succeeds.
6. Create junctions from `CodexPath` and `ClaudePath` to `SharedRoot`.
7. Verify that both install paths resolve to the same canonical path.
8. Exit nonzero on any mismatch.

Required verification block:

```powershell
$codexResolved = (Get-Item -LiteralPath $CodexPath).Target
$claudeResolved = (Get-Item -LiteralPath $ClaudePath).Target
if (-not $codexResolved -or -not $claudeResolved) {
  throw 'Expected both install paths to be junctions.'
}
```

The script must also print:

```text
BACKUP: <path>
SHARED: <path>
CODEX:  ok
CLAUDE: ok
```

- [ ] **Step 2: Dry-run the installer**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_shared_simulink_toolbox.ps1 -DryRun
```

Expected: planned paths printed, no filesystem mutation.

- [ ] **Step 3: Commit**

```powershell
git add scripts/install_shared_simulink_toolbox.ps1
git commit -m "chore: add shared Simulink skill installer"
```

---

## Task 3: Migrate To One Shared Skill Tree

**Files:**
- Modify or create: `C:\Users\27443\.shared-skills\simulink-toolbox\*`
- Replace with junctions:
  - `C:\Users\27443\.codex\skills\simulink-toolbox`
  - `C:\Users\27443\.claude\skills\simulink-toolbox`

- [ ] **Step 1: Create the shared source from the richer current copy**

Use the current Codex skill directory as the initial source because it already
contains `codex_simulink_hook.py`.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_shared_simulink_toolbox.ps1
```

Expected: backups created and both install paths replaced by junctions.

- [ ] **Step 2: Verify both paths resolve to one canonical source**

Run:

```powershell
Get-Item 'C:\Users\27443\.codex\skills\simulink-toolbox' | Format-List FullName,LinkType,Target
Get-Item 'C:\Users\27443\.claude\skills\simulink-toolbox' | Format-List FullName,LinkType,Target
```

Expected:

- `LinkType` is `Junction` for both
- `Target` is `C:\Users\27443\.shared-skills\simulink-toolbox`

- [ ] **Step 3: Remove stale duplicate-only artifacts**

Delete these if they still exist inside the shared tree:

```text
hooks\__pycache__\
*.pyc
```

Run:

```powershell
Get-ChildItem 'C:\Users\27443\.shared-skills\simulink-toolbox' -Recurse -Force |
  Where-Object { $_.FullName -match '__pycache__|\.pyc$' }
```

Expected after cleanup: no output.

---

## Task 4: Restructure The Shared Skill Into Generic Core + Platform Hook Folders

**Files:**
- Modify: `C:\Users\27443\.shared-skills\simulink-toolbox\SKILL.md`
- Modify: `C:\Users\27443\.shared-skills\simulink-toolbox\map.md`
- Modify: `C:\Users\27443\.shared-skills\simulink-toolbox\INVARIANTS.md`
- Modify: `C:\Users\27443\.shared-skills\simulink-toolbox\hooks\README.md`
- Move:
  - `hooks\codex_simulink_hook.py` -> `hooks\codex\codex_simulink_hook.py`
  - `hooks\pre-tool-use.sh` -> `hooks\claude\pre-tool-use.sh`
  - `hooks\user-prompt-submit.sh` -> `hooks\claude\user-prompt-submit.sh`
- Remove from generic patterns:
  - `patterns\training-smoke-debug.md`

- [ ] **Step 1: Normalize the shared skill file encoding**

Every file under the shared tree must be UTF-8. Re-save these as UTF-8:

- `SKILL.md`
- `map.md`
- `INVARIANTS.md`
- `hooks\README.md`
- `patterns\*.md`
- `validate_consistency.py`

Required result: no mojibake when opened via Python `encoding="utf-8"`.

- [ ] **Step 2: Fix `SKILL.md` frontmatter and scope**

Replace the description with a trigger-only description:

```yaml
description: Use when any Simulink, Simscape, Stateflow, .slx, or simulink-tools task begins
```

Do not mention workflow details in the description.

Inside the body:

- keep generic MCP-first guidance
- keep generic patterns only
- remove any mention of Kundur, NE39, Yang, VSG, harness, training, agent, episode, reward

- [ ] **Step 3: Fix the generic hook trigger policy**

In `hooks\codex\codex_simulink_hook.py`:

- remove `kundur` and `ne39` from `SIMULINK_PROMPT_RE`
- keep only generic Simulink/Simscape/Stateflow/`.slx`/`simulink-tools` triggers
- keep `[force_sl]`

In the Claude shell hook:

- keep the generic Simulink trigger only
- do not add project/model names

- [ ] **Step 4: Reorganize hook folders**

Target tree:

```text
hooks\
  README.md
  codex\
    codex_simulink_hook.py
  claude\
    pre-tool-use.sh
    user-prompt-submit.sh
```

`hooks\README.md` must document both paths and must not say Codex-only files are
"legacy Claude hooks" anymore. It must describe:

- shared root
- Codex hook subfolder
- Claude hook subfolder
- expected external config files

- [ ] **Step 5: Remove the project-specific pattern from the generic skill**

Delete:

```text
C:\Users\27443\.shared-skills\simulink-toolbox\patterns\training-smoke-debug.md
```

After deletion, `SKILL.md` must reference only:

- `patterns/build-and-verify.md`
- `patterns/debug-existing-model.md`
- `patterns/trace-connectivity.md`
- `patterns/param-sweep.md`

- [ ] **Step 6: Tighten `map.md` language**

`map.md` must explicitly say:

```markdown
This file routes generic Simulink user intent only.
Project-specific harness, training, paper-reproduction, and model-specific workflows belong to repository instructions or project overlays.
```

Do not mention or route to:

- `harness_*`
- `training_*`
- `simulink_bridge_status`
- Kundur
- NE39

---

## Task 5: Move Project-Specific And Model-Specific Routing Into A Repository Folder

**Files:**
- Create: `docs/agent_layer/simulink-project-routing/README.md`
- Create: `docs/agent_layer/simulink-project-routing/training-smoke-debug.md`
- Create: `docs/agent_layer/simulink-project-routing/models/kundur.md`
- Create: `docs/agent_layer/simulink-project-routing/models/ne39.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Create the overlay README**

Create `docs/agent_layer/simulink-project-routing/README.md` with:

```markdown
# Simulink Project Routing Overlay

This folder contains repository-specific routing that must not live in the
installed global `simulink-toolbox` skill.

Use this folder for:

- Yang/VSG project routing
- harness/training/smoke workflows
- Kundur-specific notes
- NE39-specific notes
- model-specific operational caveats

Do not copy these rules back into the shared installed skill.
```

- [ ] **Step 2: Move the training/smoke workflow here**

Create `docs/agent_layer/simulink-project-routing/training-smoke-debug.md` by
refactoring the current generic-skill version:

- keep only repository-specific tool names
- keep `harness_*` and `training_*` workflows
- remove any generic-skill framing

- [ ] **Step 3: Put model-specific routing into a dedicated subfolder**

Create:

- `docs/agent_layer/simulink-project-routing/models/kundur.md`
- `docs/agent_layer/simulink-project-routing/models/ne39.md`

Each file must contain:

- supported `scenario_id`
- actual `model_name`
- train entry path
- cold-start or smoke caveats
- known model-specific routing notes

`kundur.md` must mention:

- `scenario_id = kundur`
- `model_name = kundur_vsg`
- `scenarios/kundur/train_simulink.py`

`ne39.md` must mention:

- `scenario_id = ne39`
- `model_name = NE39bus_v2`
- `scenarios/new_england/train_simulink.py`

- [ ] **Step 4: Link the overlay from `AGENTS.md`**

Add one explicit line under the Simulink/project routing area:

```markdown
Repository-specific Simulink routing overlays live in `docs/agent_layer/simulink-project-routing/`; Kundur/NE39 model-specific notes live under `docs/agent_layer/simulink-project-routing/models/`.
```

- [ ] **Step 5: Verify the generic skill no longer carries project docs**

Run:

```powershell
Test-Path 'C:\Users\27443\.shared-skills\simulink-toolbox\patterns\training-smoke-debug.md'
Test-Path 'C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing\training-smoke-debug.md'
```

Expected:

- first command returns `False`
- second command returns `True`

- [ ] **Step 6: Commit the repository overlay**

```powershell
git add AGENTS.md docs/agent_layer/simulink-project-routing
git commit -m "docs: move Simulink project routing into overlay folder"
```

---

## Task 6: Fix External Hook Wiring And Matcher Drift

**Files:**
- Modify: `C:\Users\27443\.codex\hooks.json`
- Modify: `C:\Users\27443\.claude\settings.json`

- [ ] **Step 1: Point Codex to the new shared hook path**

Update:

```text
C:\Users\27443\.codex\skills\simulink-toolbox\hooks\codex\codex_simulink_hook.py
```

Required command strings:

```json
"command": "C:\\Users\\27443\\AppData\\Local\\Programs\\Python\\Python314\\python.exe C:\\Users\\27443\\.codex\\skills\\simulink-toolbox\\hooks\\codex\\codex_simulink_hook.py user-prompt-submit"
```

and

```json
"command": "C:\\Users\\27443\\AppData\\Local\\Programs\\Python\\Python314\\python.exe C:\\Users\\27443\\.codex\\skills\\simulink-toolbox\\hooks\\codex\\codex_simulink_hook.py pre-tool-use"
```

- [ ] **Step 2: Fix the Codex run-script matcher**

Do not guess. Verify the actual tool name first by using one of:

- a real denied hook event from Codex
- the tool list shown in the Codex environment

If the actual tool name is:

```text
mcp__simulink_tools__.simulink_run_script
```

then the matcher must escape the dot:

```json
"matcher": "Bash|shell_command|functions\\.shell_command|mcp__simulink_tools__\\.simulink_run_script(_async)?"
```

If the actual tool name differs, match the verified emitted name, not an inferred one.

- [ ] **Step 3: Point Claude to the new shared hook subfolder**

Update:

```json
"command": "bash \"$HOME/.claude/skills/simulink-toolbox/hooks/claude/pre-tool-use.sh\""
```

and

```json
"command": "bash \"$HOME/.claude/skills/simulink-toolbox/hooks/claude/user-prompt-submit.sh\""
```

- [ ] **Step 4: Keep Claude matcher naming only if verified**

The current Claude matcher uses:

```text
mcp__simulink-tools__simulink_run_script
```

Keep this only if the live Claude tool name actually uses that form.
If not, update it to the live emitted name.

- [ ] **Step 5: Run manual smoke tests for both platforms**

Codex hook smoke:

```powershell
$p = 'C:\Users\27443\AppData\Local\Programs\Python\Python314\python.exe'
$s = 'C:\Users\27443\.codex\skills\simulink-toolbox\hooks\codex\codex_simulink_hook.py'
@{ prompt = 'inspect this Simulink .slx model' } | ConvertTo-Json -Compress | & $p $s user-prompt-submit
@{ tool_name = 'functions.shell_command'; tool_input = @{ command = 'matlab -batch "disp(1)"' } } | ConvertTo-Json -Compress | & $p $s pre-tool-use
```

Claude hook smoke:

```powershell
echo '{"prompt":"inspect this Simulink .slx model"}' | bash "$HOME/.claude/skills/simulink-toolbox/hooks/claude/user-prompt-submit.sh"
echo '{"tool_name":"Bash","tool_input":{"command":"matlab -batch \"disp(1)\""}}' | bash "$HOME/.claude/skills/simulink-toolbox/hooks/claude/pre-tool-use.sh"
```

Expected:

- prompt hook emits generic Simulink guidance
- shell MATLAB escape is denied

---

## Task 7: Upgrade Validation To Cover Shared Layout, Hooks, And UTF-8

**Files:**
- Create: `C:\Users\27443\.shared-skills\simulink-toolbox\validate_layout.py`
- Modify: `C:\Users\27443\.shared-skills\simulink-toolbox\validate_consistency.py`
- Create: `tests/test_simulink_toolbox_shared_layout.py`
- Modify: `tests/test_simulink_toolbox_skill_boundary.py`
- Modify: `tests/test_regen_skill_index.py`
- Modify: `scripts/regen_skill_index.py`

- [ ] **Step 1: Make the index generator dedupe aliased install targets**

In `scripts/regen_skill_index.py`, dedupe target directories by canonical resolved path before writing.

Required behavior:

- if `.codex` and `.claude` are separate real directories, write both
- if they are junctions to the same real path, write only once

Implementation rule:

```python
unique_dirs = []
seen = set()
for path in _get_skill_dirs():
    key = str(path.resolve()).lower()
    if key in seen:
        continue
    seen.add(key)
    unique_dirs.append(path)
```

- [ ] **Step 2: Add `validate_layout.py` to the shared skill**

This script must verify:

1. `C:\Users\27443\.codex\skills\simulink-toolbox` exists
2. `C:\Users\27443\.claude\skills\simulink-toolbox` exists
3. both resolve to the same canonical directory
4. required files exist in the shared tree
5. `patterns\training-smoke-debug.md` is absent
6. all shared files can be opened as UTF-8
7. `C:\Users\27443\.codex\hooks.json` points to `hooks\codex\codex_simulink_hook.py`
8. `C:\Users\27443\.claude\settings.json` points to `hooks\claude\*.sh`

Exit code:

- `0` for pass
- `1` for any drift

- [ ] **Step 3: Extend the repo layout guard**

Create `tests/test_simulink_toolbox_shared_layout.py` with tests for:

- installed directories exist
- their resolved canonical paths are identical
- required shared hook subfolders exist
- generic patterns do not include `training-smoke-debug.md`
- repo overlay folder exists
- repo model folder exists

- [ ] **Step 4: Update the boundary test to use canonical paths**

`tests/test_simulink_toolbox_skill_boundary.py` must not scan the same shared
tree twice when both install paths are junctions. Use resolved unique paths.

Add one more assertion:

```python
assert not (skill_dir / "patterns" / "training-smoke-debug.md").exists()
```

- [ ] **Step 5: Keep `validate_consistency.py` focused**

Do not make `validate_consistency.py` parse external configs. It should remain a
generic doc/index checker for:

- `index.json`
- `map.md`
- `patterns/*.md`

External layout and hook config checks belong in `validate_layout.py`.

- [ ] **Step 6: Run verification**

Run:

```powershell
python scripts/regen_skill_index.py --check
python -m pytest tests/test_regen_skill_index.py tests/test_simulink_toolbox_skill_boundary.py tests/test_simulink_toolbox_shared_layout.py -q
python C:\Users\27443\.shared-skills\simulink-toolbox\validate_consistency.py
python C:\Users\27443\.shared-skills\simulink-toolbox\validate_layout.py
```

Expected: all commands exit `0`.

- [ ] **Step 7: Commit**

```powershell
git add scripts/regen_skill_index.py tests/test_regen_skill_index.py tests/test_simulink_toolbox_skill_boundary.py tests/test_simulink_toolbox_shared_layout.py
git commit -m "test: guard shared Simulink skill layout"
```

---

## Task 8: Final Verification And Cleanup

**Files:**
- Modify if needed: `docs/devlog/*`

- [ ] **Step 1: Verify the shared skill tree manually**

Run:

```powershell
Get-ChildItem 'C:\Users\27443\.shared-skills\simulink-toolbox' -Recurse |
  Select-Object FullName | Format-Table -AutoSize
```

Expected:

- only one `SKILL.md`
- only one `map.md`
- `hooks\codex\codex_simulink_hook.py`
- `hooks\claude\pre-tool-use.sh`
- `hooks\claude\user-prompt-submit.sh`
- no `patterns\training-smoke-debug.md`

- [ ] **Step 2: Verify model-specific files are in the repo overlay**

Run:

```powershell
Get-ChildItem 'C:\Users\27443\Desktop\Multi-Agent  VSGs\docs\agent_layer\simulink-project-routing' -Recurse |
  Select-Object FullName | Format-Table -AutoSize
```

Expected:

- `README.md`
- `training-smoke-debug.md`
- `models\kundur.md`
- `models\ne39.md`

- [ ] **Step 3: Verify generic prompt neutrality**

Run:

```powershell
Select-String -Path `
  'C:\Users\27443\.shared-skills\simulink-toolbox\SKILL.md',`
  'C:\Users\27443\.shared-skills\simulink-toolbox\map.md' `
  -Pattern 'Kundur|NE39|Yang|VSG|harness_|training_|reward|episode|agent'
```

Expected: no output.

- [ ] **Step 4: Record a devlog only if a new durable migration fact was discovered**

Write a devlog only if one of these happened:

- junction creation hit a Windows-specific edge case
- matcher names differed from expected live tool names
- UTF-8 normalization exposed hidden file corruption
- repo overlay boundaries required a non-obvious rule

If none of those occurred, skip the devlog.

---

## Acceptance Criteria

- Exactly one real installed skill tree exists at `C:\Users\27443\.shared-skills\simulink-toolbox`.
- `C:\Users\27443\.codex\skills\simulink-toolbox` and `C:\Users\27443\.claude\skills\simulink-toolbox` are junctions to that tree.
- The shared installed skill contains only generic Simulink routing.
- `training-smoke-debug.md` no longer exists under generic skill `patterns\`.
- Repo/model-specific routing exists under `docs/agent_layer/simulink-project-routing/`.
- Kundur and NE39 notes exist under `docs/agent_layer/simulink-project-routing/models/`.
- Codex and Claude configs point to the shared hook subfolders and match live tool names.
- `validate_consistency.py`, `validate_layout.py`, and repo pytest guards all pass.

## Rollback

If the migration breaks either install:

1. Remove both junctions.
2. Restore the latest backup from `C:\Users\27443\.shared-skills\backups\<timestamp>\`.
3. Restore `C:\Users\27443\.codex\hooks.json` and `C:\Users\27443\.claude\settings.json`.
4. Re-run the validation scripts before retrying.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-simulink-toolbox-single-source-and-project-overlay.md`. Recommended execution mode is **Inline Execution** rather than subagent-driven, because this work touches both repository files and live home-directory config/install paths and benefits from one continuous verification thread.
