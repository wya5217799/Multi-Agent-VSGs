# Kundur SPS Phasor Migration V4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Kundur 主训练路径从 `ee_lib + SolverConfig` 迁移到 `SPS + powergui(Phasor)`，并在迁移前置建立 `JSON intent -> Simulink implementation -> semantic manifest` 三层边界，减少对反复 MCP/临时 MATLAB 查询的依赖。

**Architecture:** V4 先做结构治理，再做模型迁移。先定义 scenario-local JSON profile，只允许“已知结构上的参数化、模式切换、功能开关”；再从 Simulink 自动导出 semantic manifest，作为只读事实层；最后按 manifest-sized batches 迁移 shadow model `kundur_vsg_sps.slx`，每一批都过 `profile <-> manifest` 一致性 gate，再过物理和训练 gate。最终 cutover 保持 `ScenarioContract.model_name='kundur_vsg'` 稳定：先归档旧 `ee_lib` 模型，再把通过 gate 的 SPS 候选模型提升为 canonical `kundur_vsg.slx`。

**Tech Stack:** Python 3.11+ standard library (`json`, `dataclasses`, `pathlib`, `typing`), existing `engine/simulink_bridge.py`, MATLAB/Simulink R2025b, SPS `powergui` Phasor mode, repo MCP Simulink tools, harness artifacts under `results/harness/`.

---

**Supersedes:** `docs/superpowers/plans/2026-04-24-kundur-sps-phasor-migration-v3.md`

## Why V4 Exists

`v3` 的主轴是“影子模型先行，再 cutover 到 SPS/Phasor”。这个方向本身没问题，但它缺少一个前置结构层，导致两个风险：

1. 迁移过程中仍然要靠 MCP/临时脚本不断问 MATLAB，知识不会沉淀。
2. 调试时无法清楚地区分“配置漂移”和“模型结构漂移”。

`v4` 把这部分前移，并明确三层职责：

- `JSON intent`：只表达已知语义槽位上的参数、模式、功能开关。
- `Simulink implementation`：真实块、连线、初始化策略，由 `.slx` / builder 决定。
- `semantic manifest`：从 Simulink 自动导出的事实层；回答“模型现在实际长什么样”。

## Design Guardrails

- JSON profile 不允许描述任意 block path、端口连线、拓扑增删。
- semantic manifest 是只读导出物，不是反向建模 DSL。
- 不新增新的 harness task family；manifest 集成到现有 `model_inspect` / `model_report`。
- cutover 之前，`scenarios/contract.py` 中 Kundur 的 canonical `model_name` 保持不变。
- `ee_lib` 路线只允许被归档，不允许继续通过“加 warmup / 加 ramp / 加 IC patch”续命。
- 所有新 engine/helper 都必须服务于“纸面结果复现”或“重复 AI 操作标准化”；本计划里的新模块属于后者。

## MCP-First Execution Policy

All Simulink work in this plan follows `simulink-toolbox` MCP-first routing.

- Discovery defaults to:
  - `simulink_load_model`
  - `simulink_get_block_tree`
  - `simulink_explore_block`
  - `simulink_query_params`
  - `simulink_solver_audit`
- Construction and editing default to:
  - `simulink_library_lookup`
  - `simulink_create_model` / `simulink_add_block` / `simulink_add_subsystem`
  - `simulink_describe_block_ports`
  - `simulink_connect_ports`
  - `simulink_set_block_params` or `simulink_patch_and_verify`
- Verification defaults to:
  - `simulink_compile_diagnostics` after every batch of at most 3 structural edits
  - `simulink_query_params` / `simulink_trace_port_connections` for readback
  - `simulink_signal_snapshot` / `simulink_step_diagnostics` for short-window runtime checks
- Runtime reset and short-window checks default to:
  - `simulink_runtime_reset`
  - `simulink_run_window`
  - `simulink_signal_snapshot`
- `simulink_run_script` / `_async` are escape hatches only:
  - semantic manifest aggregation export
  - tightly coupled probe scripts
  - replayable builder batches after the MCP edit sequence is already validated

For every Simulink-facing step in Tasks 4-9, write the action in this shape:

```text
Step N: [goal]
  Tool: [preferred MCP tool(s)]
  Combine: [optional fallback or supporting step]
  Verify: [tool used to confirm completion]
```

Do not treat `matlab -batch` as the default path. Scripts are fallback only and never replace routine inspect / edit / verify.

## File Structure

### New files

- `docs/decisions/2026-04-24-kundur-intent-manifest-boundary.md`
  - 记录 JSON/profile 与 manifest 的稳定边界规则。
- `scenarios/kundur/model_profile.py`
  - 读取、解析、校验 Kundur JSON profile，向 Python runtime 暴露强类型对象。
- `scenarios/kundur/model_profiles/schema.json`
  - JSON profile 的机器约束；只允许已知语义槽位。
- `scenarios/kundur/model_profiles/kundur_ee_legacy.json`
  - 旧 `ee_lib` 主线的显式 profile。
- `scenarios/kundur/model_profiles/kundur_sps_candidate.json`
  - 新 `SPS/Phasor` 候选主线的显式 profile。
- `scenarios/kundur/manifest_contract.py`
  - Kundur 语义槽位定义与 `profile <-> manifest` 一致性规则。
- `engine/simulink_semantic_manifest.py`
  - 通用 manifest payload 类型、校验与 diff helper。
- `scenarios/kundur/simulink_models/export_kundur_semantic_manifest.m`
  - 直接从 Simulink 模型导出 Kundur semantic manifest。
- `tests/test_kundur_model_profile.py`
  - JSON profile 解析与禁用字段测试。
- `tests/test_kundur_semantic_manifest.py`
  - semantic manifest 结构与 profile 一致性测试。

### Modified files

- `scenarios/kundur/config_simulink.py`
  - 从固定常量式配置切到“profile 驱动 + 派生 BridgeConfig”。
- `env/simulink/kundur_simulink_env.py`
  - 支持 profile 选择；默认保留 legacy profile。
- `engine/simulink_bridge.py`
  - 只在真正缺 generic capability 时补通用字段，不再塞 Kundur 特判语义。
- `engine/modeling_tasks.py`
  - `model_inspect` 附带导出 semantic manifest artifact。
- `engine/harness_reports.py`
  - `model_report` 汇总 profile/manifest drift。
- `probes/kundur/probe_sps_minimal.m`
  - 作为 `powergui(Phasor)` 最小可行性 probe 的唯一基线。
- `probes/kundur/validate_phase3_zero_action.py`
  - 从“长 warmup 也不炸”改为“无需结构性 warmup 补偿”。
- `scenarios/kundur/simulink_models/build_kundur_sps.m`
  - 新 shadow builder。
- `scenarios/kundur/simulink_models/build_powerlib_kundur.m`
  - 只做 legacy builder，禁止继续承担 candidate 路线。
- `scenarios/kundur/NOTES.md`
  - 记录迁移后有效规则和回归禁区。
- `tests/test_modeling_tasks.py`
  - 验证 `model_inspect` 的 manifest artifact 行为。
- `tests/test_harness_reports.py`
  - 验证 `model_report` 对 drift 的摘要。
- `tests/test_simulink_bridge.py`
  - 更新 Kundur runtime 契约测试。

## Acceptance Gates

### A0: Boundary Gate

- `docs/decisions/2026-04-24-kundur-intent-manifest-boundary.md` 落地。
- `kundur_ee_legacy.json` 和 `kundur_sps_candidate.json` 都能被 `model_profile.py` 解析。
- profile 中出现 `connections`、`block_paths`、`wires`、`topology` 这类字段必须硬失败。

### A1: Legacy Baseline Gate

- 对当前 `kundur_vsg.slx` 导出 legacy semantic manifest。
- 导出的 manifest 必须明确显示：
  - `solver.family = simscape_ee`
  - `initialization.uses_pref_ramp = true`
  - `initialization.warmup_mode = physics_compensation`
  - `measurement.mode = feedback`

### A2: Candidate Structural Gate

- 对 `kundur_vsg_sps.slx` 导出 candidate semantic manifest。
- candidate manifest 必须明确显示：
  - `solver.family = sps_phasor`
  - `solver.has_solver_config = false`
  - `initialization.uses_pref_ramp = false`
  - `measurement.mode = vi`
  - `phase_command_mode = absolute_with_loadflow`

### G0: SPS Feasibility Gate

- `probes/kundur/probe_sps_minimal.m` 通过。
- `powergui(Phasor)` 下 `t <= 1 ms` 时 `Pe / P_nominal` 进入 `[0.95, 1.05]`。

### G1: Zero-Action Physical Gate

- `validate_phase3_zero_action.py` 按新 invariants 通过。
- 不接受“`delta` 卡在 `-90 deg` 但 drift 很小”的假稳定。
- 不接受“只有长 warmup 才稳定”的结构性补偿。

### G2: Smoke Bridge Gate

- 在 candidate profile 下，`train_smoke_*` 给出 pass verdict。
- 不再依赖 `Pe_prev` / `delta_prev_deg` 补丁逻辑来掩盖结构问题。

### G3: Short Training Gate

- `python scenarios/kundur/train_simulink.py --mode simulink --episodes 20` 可以完整起跑。
- Episode 1 就能进入训练循环，无 `omega_saturated` 系统性爆炸，无 `Pe=0` 持续失败。

### G4: Cutover Gate

- A0-A2 + G0-G3 全部通过后，才允许将 `kundur_vsg_sps.slx` 提升为 canonical `kundur_vsg.slx`。

## Task 1: Lock The Stable Boundary Before Model Work

**Files:**
- Create: `docs/decisions/2026-04-24-kundur-intent-manifest-boundary.md`
- Modify: `scenarios/kundur/NOTES.md`

- [ ] **Step 1: Write the boundary decision record**

```md
# Kundur Intent vs Manifest Boundary

## Status
Accepted

## Context
Kundur SPS migration needs a durable external config layer and a durable
structure-fact layer. Repeated ad hoc MATLAB inspection is too expensive.

## Decision
- JSON profiles may configure only known semantic slots.
- JSON profiles may not declare arbitrary topology, wires, ports, or block paths.
- Semantic manifests are exported facts from Simulink and are read-only.
- Harness integrates manifests through existing tasks; no new task family is added.

## Consequences
- Config drift and structure drift become separately diagnosable.
- MCP/MATLAB inspection becomes baseline capture, not a repeated debugging loop.
```

- [ ] **Step 2: Add a short rule block to `scenarios/kundur/NOTES.md`**

```md
## Active migration rule

- JSON profile controls only known semantic slots.
- Semantic manifest is the exported fact layer.
- Reintroducing `PrefRamp_*` or long physical warmup on the SPS path is a regression.
```

- [ ] **Step 3: Commit**

```bash
git add docs/decisions/2026-04-24-kundur-intent-manifest-boundary.md scenarios/kundur/NOTES.md
git commit -m "docs: define kundur intent and semantic manifest boundary"
```

## Task 2: Add The JSON Intent Layer

**Files:**
- Create: `scenarios/kundur/model_profile.py`
- Create: `scenarios/kundur/model_profiles/schema.json`
- Create: `scenarios/kundur/model_profiles/kundur_ee_legacy.json`
- Create: `scenarios/kundur/model_profiles/kundur_sps_candidate.json`
- Create: `tests/test_kundur_model_profile.py`

- [ ] **Step 1: Write failing tests for allowed and forbidden profile fields**

```python
from pathlib import Path

import pytest

from scenarios.kundur.model_profile import (
    load_kundur_model_profile,
    parse_kundur_model_profile,
)


def test_legacy_profile_declares_feedback_and_physics_warmup():
    profile = load_kundur_model_profile(
        Path("scenarios/kundur/model_profiles/kundur_ee_legacy.json")
    )
    assert profile.solver_family == "simscape_ee"
    assert profile.pe_measurement == "feedback"
    assert profile.warmup_mode == "physics_compensation"


def test_candidate_profile_declares_vi_and_sps():
    profile = load_kundur_model_profile(
        Path("scenarios/kundur/model_profiles/kundur_sps_candidate.json")
    )
    assert profile.solver_family == "sps_phasor"
    assert profile.pe_measurement == "vi"
    assert profile.phase_command_mode == "absolute_with_loadflow"


def test_profile_rejects_topology_fields():
    with pytest.raises(ValueError, match="connections"):
        parse_kundur_model_profile(
            {
                "scenario_id": "kundur",
                "profile_id": "bad",
                "connections": [],
            }
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_kundur_model_profile.py -q`

Expected: `ModuleNotFoundError` or `ImportError` for `scenarios.kundur.model_profile`

- [ ] **Step 3: Write the schema file**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "KundurModelProfile",
  "type": "object",
  "required": [
    "scenario_id",
    "profile_id",
    "model_name",
    "solver_family",
    "pe_measurement",
    "phase_command_mode",
    "warmup_mode",
    "feature_flags"
  ],
  "additionalProperties": false,
  "properties": {
    "scenario_id": { "const": "kundur" },
    "profile_id": { "type": "string", "minLength": 1 },
    "model_name": { "type": "string", "minLength": 1 },
    "solver_family": { "enum": ["simscape_ee", "sps_phasor"] },
    "pe_measurement": { "enum": ["feedback", "vi"] },
    "phase_command_mode": { "enum": ["passthrough", "absolute_with_loadflow"] },
    "warmup_mode": { "enum": ["physics_compensation", "technical_reset_only"] },
    "feature_flags": {
      "type": "object",
      "required": [
        "allow_pref_ramp",
        "allow_simscape_solver_config",
        "allow_feedback_only_pe_chain"
      ],
      "additionalProperties": false,
      "properties": {
        "allow_pref_ramp": { "type": "boolean" },
        "allow_simscape_solver_config": { "type": "boolean" },
        "allow_feedback_only_pe_chain": { "type": "boolean" }
      }
    }
  }
}
```

- [ ] **Step 4: Write the two concrete profile files**

```json
{
  "scenario_id": "kundur",
  "profile_id": "kundur_ee_legacy",
  "model_name": "kundur_vsg",
  "solver_family": "simscape_ee",
  "pe_measurement": "feedback",
  "phase_command_mode": "passthrough",
  "warmup_mode": "physics_compensation",
  "feature_flags": {
    "allow_pref_ramp": true,
    "allow_simscape_solver_config": true,
    "allow_feedback_only_pe_chain": true
  }
}
```

```json
{
  "scenario_id": "kundur",
  "profile_id": "kundur_sps_candidate",
  "model_name": "kundur_vsg_sps",
  "solver_family": "sps_phasor",
  "pe_measurement": "vi",
  "phase_command_mode": "absolute_with_loadflow",
  "warmup_mode": "technical_reset_only",
  "feature_flags": {
    "allow_pref_ramp": false,
    "allow_simscape_solver_config": false,
    "allow_feedback_only_pe_chain": false
  }
}
```

- [ ] **Step 5: Implement the loader and validator**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FORBIDDEN_KEYS = {"connections", "block_paths", "wires", "topology"}


@dataclass(frozen=True)
class KundurFeatureFlags:
    allow_pref_ramp: bool
    allow_simscape_solver_config: bool
    allow_feedback_only_pe_chain: bool


@dataclass(frozen=True)
class KundurModelProfile:
    scenario_id: str
    profile_id: str
    model_name: str
    solver_family: str
    pe_measurement: str
    phase_command_mode: str
    warmup_mode: str
    feature_flags: KundurFeatureFlags


def parse_kundur_model_profile(payload: dict[str, Any]) -> KundurModelProfile:
    bad = _FORBIDDEN_KEYS.intersection(payload)
    if bad:
        raise ValueError(f"Profile may not declare topology keys: {sorted(bad)}")
    flags = payload["feature_flags"]
    return KundurModelProfile(
        scenario_id=payload["scenario_id"],
        profile_id=payload["profile_id"],
        model_name=payload["model_name"],
        solver_family=payload["solver_family"],
        pe_measurement=payload["pe_measurement"],
        phase_command_mode=payload["phase_command_mode"],
        warmup_mode=payload["warmup_mode"],
        feature_flags=KundurFeatureFlags(**flags),
    )


def load_kundur_model_profile(path: str | Path) -> KundurModelProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_kundur_model_profile(payload)
```

- [ ] **Step 6: Run tests and verify they pass**

Run: `pytest tests/test_kundur_model_profile.py -q`

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add scenarios/kundur/model_profile.py scenarios/kundur/model_profiles tests/test_kundur_model_profile.py
git commit -m "feat: add kundur model profile layer"
```

## Task 3: Define The Semantic Manifest Contract

**Files:**
- Create: `engine/simulink_semantic_manifest.py`
- Create: `scenarios/kundur/manifest_contract.py`
- Create: `tests/test_kundur_semantic_manifest.py`

- [ ] **Step 1: Write failing tests for manifest structure and drift detection**

```python
from scenarios.kundur.manifest_contract import validate_kundur_alignment
from scenarios.kundur.model_profile import load_kundur_model_profile


def test_candidate_manifest_requires_vi_and_no_solverconfig():
    profile = load_kundur_model_profile(
        "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )
    manifest = {
        "scenario_id": "kundur",
        "model_name": "kundur_vsg_sps",
        "solver": {"family": "sps_phasor", "has_solver_config": False},
        "initialization": {"uses_pref_ramp": False, "warmup_mode": "technical_reset_only"},
        "measurement": {"mode": "vi"},
    }
    issues = validate_kundur_alignment(profile, manifest)
    assert issues == []


def test_candidate_manifest_rejects_pref_ramp():
    profile = load_kundur_model_profile(
        "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )
    manifest = {
        "scenario_id": "kundur",
        "model_name": "kundur_vsg_sps",
        "solver": {"family": "sps_phasor", "has_solver_config": False},
        "initialization": {"uses_pref_ramp": True, "warmup_mode": "technical_reset_only"},
        "measurement": {"mode": "vi"},
    }
    issues = validate_kundur_alignment(profile, manifest)
    assert "pref_ramp" in " ".join(issues)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_kundur_semantic_manifest.py -q`

Expected: `ModuleNotFoundError` for `scenarios.kundur.manifest_contract`

- [ ] **Step 3: Implement the generic manifest payload types**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticManifest:
    scenario_id: str
    model_name: str
    solver: dict[str, Any]
    initialization: dict[str, Any]
    measurement: dict[str, Any]
    units: list[dict[str, Any]]
    disturbances: list[dict[str, Any]]
```

- [ ] **Step 4: Implement Kundur-specific alignment rules**

```python
from __future__ import annotations

from scenarios.kundur.model_profile import KundurModelProfile


def validate_kundur_alignment(profile: KundurModelProfile, manifest: dict) -> list[str]:
    issues: list[str] = []
    if manifest["solver"]["family"] != profile.solver_family:
        issues.append("solver_family mismatch")
    if manifest["measurement"]["mode"] != profile.pe_measurement:
        issues.append("pe_measurement mismatch")
    if manifest["initialization"]["warmup_mode"] != profile.warmup_mode:
        issues.append("warmup_mode mismatch")
    if not profile.feature_flags.allow_pref_ramp and manifest["initialization"]["uses_pref_ramp"]:
        issues.append("pref_ramp present while profile forbids it")
    if not profile.feature_flags.allow_simscape_solver_config and manifest["solver"]["has_solver_config"]:
        issues.append("solver_config present while profile forbids it")
    return issues
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `pytest tests/test_kundur_semantic_manifest.py -q`

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add engine/simulink_semantic_manifest.py scenarios/kundur/manifest_contract.py tests/test_kundur_semantic_manifest.py
git commit -m "feat: add kundur semantic manifest contract"
```

## Task 4: Export Semantic Manifest From Simulink And Wire It Into Harness Inspection

**Files:**
- Create: `scenarios/kundur/simulink_models/export_kundur_semantic_manifest.m`
- Modify: `engine/modeling_tasks.py`
- Modify: `engine/harness_reports.py`
- Modify: `tests/test_modeling_tasks.py`
- Modify: `tests/test_harness_reports.py`

Execution shape for this task:

```text
Step A: capture raw structure facts
  Tool: simulink_load_model, simulink_get_block_tree, simulink_solver_audit, simulink_query_params
  Combine: model_inspect stores raw MCP artifacts under results/harness/.../attachments/
  Verify: raw artifacts exist before semantic export runs

Step B: aggregate semantic facts
  Tool: simulink_run_script
  Combine: export_kundur_semantic_manifest.m reads the already-loaded model and writes one JSON file
  Verify: validate_kundur_alignment + model_report summary
```

- [ ] **Step 1: Write failing tests for manifest artifact emission**

```python
def test_model_inspect_adds_semantic_manifest_artifact(tmp_path):
    result = {
        "semantic_manifest_artifact": str(tmp_path / "semantic_manifest.json"),
        "semantic_alignment": [],
    }
    assert result["semantic_manifest_artifact"].endswith("semantic_manifest.json")
    assert result["semantic_alignment"] == []
```

```python
def test_model_report_surfaces_alignment_warnings():
    payload = {
        "semantic_alignment": ["pref_ramp present while profile forbids it"]
    }
    assert payload["semantic_alignment"][0].startswith("pref_ramp")
```

- [ ] **Step 2: Implement the MATLAB exporter**

```matlab
function payload = export_kundur_semantic_manifest(model_name, out_path)
load_system(model_name);

payload.schema_version = 1;
payload.scenario_id = 'kundur';
payload.model_name = model_name;
has_powergui = ~isempty(find_system(model_name, 'SearchDepth', 1, 'Name', 'powergui'));
if has_powergui
    payload.solver.family = 'sps_phasor';
else
    payload.solver.family = 'simscape_ee';
end
payload.solver.has_solver_config = ~isempty(find_system(model_name, 'SearchDepth', 1, 'Name', 'SolverConfig'));
payload.initialization.uses_pref_ramp = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', 'PrefRamp_.*'));
if payload.initialization.uses_pref_ramp
    payload.initialization.warmup_mode = 'physics_compensation';
else
    payload.initialization.warmup_mode = 'technical_reset_only';
end
has_vi = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', '.*VIMeas.*'));
has_pefb = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', 'Log_PeFb_.*'));
if has_vi
    payload.measurement.mode = 'vi';
elseif has_pefb
    payload.measurement.mode = 'feedback';
else
    payload.measurement.mode = 'unknown';
end
payload.units = struct([]);
payload.disturbances = struct([]);

txt = jsonencode(payload);
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', txt);
fclose(fid);
end
```

- [ ] **Step 3: Extend `model_inspect` to attach semantic manifest and alignment**

```python
semantic_manifest_path = run_dir / "attachments" / "semantic_manifest.json"
alignment_issues = validate_kundur_alignment(profile, manifest_payload)
summary.append(f"semantic_alignment={len(alignment_issues)}")
artifacts.append(str(semantic_manifest_path))
```

- [ ] **Step 4: Extend `model_report` to summarize drift**

```python
if semantic_alignment:
    key_findings.extend(semantic_alignment)
    run_status = "warning"
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `pytest tests/test_modeling_tasks.py tests/test_harness_reports.py -q`

Expected: all selected tests pass

- [ ] **Step 6: Capture the legacy baseline with an MCP-first sequence**

```text
Step 6A: inspect the legacy model before semantic aggregation
  Tool: simulink_load_model, simulink_get_block_tree, simulink_solver_audit, simulink_query_params
  Combine: save raw hierarchy / solver / parameter facts to results/harness/kundur/20260424-legacy-baseline/attachments/
  Verify: tree and query output show SolverConfig and PrefRamp_* on the legacy path

Step 6B: export the semantic manifest only after raw MCP capture
  Tool: simulink_run_script
  Combine: call export_kundur_semantic_manifest('kundur_vsg', out_path)
  Verify: results/harness/kundur/20260424-legacy-baseline/attachments/semantic_manifest.json exists and reports solver.family=simscape_ee
```

- [ ] **Step 7: Commit**

```bash
git add scenarios/kundur/simulink_models/export_kundur_semantic_manifest.m engine/modeling_tasks.py engine/harness_reports.py tests/test_modeling_tasks.py tests/test_harness_reports.py
git commit -m "feat: export kundur semantic manifest during harness inspection"
```

## Task 5: Make Kundur Runtime Profile-Driven Without Changing The Default Path

**Files:**
- Modify: `scenarios/kundur/config_simulink.py`
- Modify: `env/simulink/kundur_simulink_env.py`
- Modify: `tests/test_simulink_bridge.py`

- [ ] **Step 1: Write failing tests for default legacy profile and candidate override**

```python
def test_kundur_default_profile_is_legacy():
    from scenarios.kundur.config_simulink import KUNDUR_MODEL_PROFILE
    assert KUNDUR_MODEL_PROFILE.profile_id == "kundur_ee_legacy"


def test_kundur_candidate_profile_can_be_selected(monkeypatch):
    monkeypatch.setenv(
        "KUNDUR_MODEL_PROFILE",
        "scenarios/kundur/model_profiles/kundur_sps_candidate.json",
    )
    from scenarios.kundur.config_simulink import load_runtime_kundur_profile
    profile = load_runtime_kundur_profile()
    assert profile.profile_id == "kundur_sps_candidate"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_simulink_bridge.py -q -k "default_profile or candidate_profile"`

Expected: failing import or missing symbol assertions

- [ ] **Step 3: Implement runtime profile selection**

```python
DEFAULT_KUNDUR_MODEL_PROFILE = (
    Path(__file__).resolve().parent / "model_profiles" / "kundur_ee_legacy.json"
)


def load_runtime_kundur_profile():
    path = os.getenv("KUNDUR_MODEL_PROFILE", str(DEFAULT_KUNDUR_MODEL_PROFILE))
    return load_kundur_model_profile(path)


KUNDUR_MODEL_PROFILE = load_runtime_kundur_profile()
```

- [ ] **Step 4: Derive `BridgeConfig` from the selected profile**

```python
pe_measurement = KUNDUR_MODEL_PROFILE.pe_measurement
phase_command_mode = KUNDUR_MODEL_PROFILE.phase_command_mode
model_name = KUNDUR_MODEL_PROFILE.model_name
```

- [ ] **Step 5: Let the env accept an explicit profile path while keeping the default stable**

```python
class KundurSimulinkEnv(_KundurBaseEnv):
    def __init__(self, model_profile_path: str | None = None, **kwargs):
        selected_path = model_profile_path or os.getenv(
            "KUNDUR_MODEL_PROFILE",
            str(DEFAULT_KUNDUR_MODEL_PROFILE),
        )
        self._runtime_profile = load_kundur_model_profile(selected_path)
        super().__init__(**kwargs)
```

- [ ] **Step 6: Run tests and verify they pass**

Run: `pytest tests/test_simulink_bridge.py -q`

Expected: all selected Kundur bridge profile tests pass

- [ ] **Step 7: Commit**

```bash
git add scenarios/kundur/config_simulink.py env/simulink/kundur_simulink_env.py tests/test_simulink_bridge.py
git commit -m "feat: make kundur simulink runtime profile driven"
```

## Task 6: Build The SPS Shadow Skeleton And Prove G0 Early

**Files:**
- Create: `scenarios/kundur/simulink_models/build_kundur_sps.m`
- Modify: `probes/kundur/probe_sps_minimal.m`
- Generated: `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`

Execution shape for every build batch in this task:

```text
Step N: [build batch]
  Tool: simulink_library_lookup, simulink_create_model / simulink_add_block, simulink_describe_block_ports, simulink_connect_ports, simulink_set_block_params
  Combine: simulink_compile_diagnostics after every <=3 structural edits; simulink_save_model after every green batch
  Verify: simulink_get_block_tree, simulink_query_params, simulink_trace_port_connections
```

- [ ] **Step 1: Preflight the exact SPS library blocks before placing anything**

```text
Step 1A: verify root solver and minimal-probe libraries
  Tool: simulink_library_lookup
  Combine: none
  Verify: exact library paths are recorded for powergui, Three-Phase Source, Three-Phase V-I Measurement, and Three-Phase Parallel RLC Load
```

- [ ] **Step 2: Create the minimal SPS skeleton through MCP tools first**

```matlab
mdl = 'kundur_vsg_sps';
% This file is the rebuild artifact generated after the MCP-first skeleton
% is proven green. Do not use this script as the first implementation path.
new_system(mdl);
load_system('powerlib');
add_block('powerlib/powergui', [mdl '/powergui']);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
save_system(mdl, fullfile(fileparts(mfilename('fullpath')), [mdl '.slx']));
```

- [ ] **Step 3: Compile and save the skeleton immediately after the root batch**

```text
Step 3A: build the root solver layer
  Tool: simulink_create_model, simulink_add_block, simulink_set_block_params, simulink_save_model
  Combine: none
  Verify: simulink_get_block_tree shows powergui at root and no SolverConfig

Step 3B: compile after the first structural batch
  Tool: simulink_compile_diagnostics
  Combine: none
  Verify: model reaches compile/update success or a concrete missing-network error; no library-missing error is allowed
```

- [ ] **Step 4: Encode the proven skeleton into `build_kundur_sps.m` as a rebuild artifact**

```text
Step 4A: mirror the verified MCP edit sequence into build_kundur_sps.m
  Tool: none (file edit)
  Combine: if the public MCP surface cannot express a tightly coupled save/replay detail, use simulink_run_script only after the MCP sequence is already validated
  Verify: rerunning the builder produces the same root tree as the MCP-built model
```

- [ ] **Step 5: Align `probe_sps_minimal.m` with the exact block names installed in R2025b**

Expected checks:

- `powerlib/powergui`
- `powerlib/Electrical Sources/Three-Phase Source`
- `powerlib/Measurements/Three-Phase V-I Measurement`
- `powerlib/Elements/Three-Phase Parallel RLC Load`

- [ ] **Step 6: Run G0 before any large-scale surgery**

```text
Step 6A: validate the minimal SPS direction with discovery-first setup
  Tool: simulink_library_lookup, simulink_load_model
  Combine: simulink_run_script executes probe_sps_minimal.m only after exact block paths are confirmed
  Verify: probe output contains RESULT: probe_sps_minimal PASS
```

- [ ] **Step 7: Capture the candidate skeleton manifest with MCP-first discovery**

```text
Step 7A: inspect the skeleton model
  Tool: simulink_load_model, simulink_get_block_tree, simulink_solver_audit, simulink_query_params
  Combine: persist raw facts under results/harness/kundur/20260424-sps-skeleton/attachments/
  Verify: root facts show powergui and no SolverConfig

Step 7B: aggregate semantic manifest
  Tool: simulink_run_script
  Combine: call export_kundur_semantic_manifest('kundur_vsg_sps', out_path)
  Verify: semantic manifest reports solver.family=sps_phasor and solver.has_solver_config=false
```

- [ ] **Step 8: Commit**

```bash
git add scenarios/kundur/simulink_models/build_kundur_sps.m probes/kundur/probe_sps_minimal.m
git commit -m "feat: add kundur sps shadow skeleton"
```

## Task 7: Port The Electrical Layer In Manifest-Sized Batches

**Files:**
- Modify: `scenarios/kundur/simulink_models/build_kundur_sps.m`
- Read: `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`
- Modify: `scenarios/kundur/simulink_models/export_kundur_semantic_manifest.m`

Execution shape for every migration batch in this task:

```text
Step N: [migration batch]
  Tool: simulink_library_lookup, simulink_add_block / simulink_delete_block, simulink_describe_block_ports, simulink_connect_ports, simulink_set_block_params
  Combine: simulink_query_params preflight; simulink_compile_diagnostics after each <=3 structural edits; simulink_run_script only for tightly coupled power-flow or manifest aggregation
  Verify: simulink_get_block_tree, simulink_query_params, simulink_trace_port_connections, validate_kundur_alignment
```

- [ ] **Step 1: Port source blocks first and keep them explicit**

Required batch:

- `CVS_G*` / `CVS_ES*` families migrate to SPS source equivalents
- every source has explicit phase angle and internal impedance
- no external “startup crutch” RLC network added just to fake initialization

```text
Step 1A: preflight source libraries and parameters
  Tool: simulink_library_lookup
  Combine: none
  Verify: exact source block paths and parameter names are known before placement

Step 1B: place and wire source blocks in batches of at most 3 structural edits
  Tool: simulink_add_block, simulink_describe_block_ports, simulink_connect_ports, simulink_set_block_params
  Combine: simulink_compile_diagnostics after each batch
  Verify: simulink_get_block_tree, simulink_trace_port_connections, simulink_query_params
```

- [ ] **Step 2: Export manifest after the source batch and validate it**

Expected manifest facts:

- each `ES*` unit exists
- source type is SPS
- `phase_command_mode = absolute_with_loadflow` for candidate profile

```text
Step 2A: capture source-batch structure facts
  Tool: simulink_get_block_tree, simulink_query_params
  Combine: simulink_solver_audit for root solver confirmation
  Verify: raw facts show the expected source family

Step 2B: aggregate semantic manifest only after raw MCP capture
  Tool: simulink_run_script
  Combine: export_kundur_semantic_manifest.m
  Verify: validate_kundur_alignment returns [] for the source-related fields
```

- [ ] **Step 3: Port measurement chains second**

Required batch:

- `PeGain_*` feedback path is replaced by `V-I Measurement` + explicit `Pe` reconstruction
- `ToWorkspace` signals needed by Python remain until bridge reads are updated

```text
Step 3A: preflight V-I measurement blocks and ports
  Tool: simulink_library_lookup, simulink_describe_block_ports
  Combine: none
  Verify: port naming and parameter names are confirmed before wiring

Step 3B: migrate the measurement chain in small verified batches
  Tool: simulink_add_block, simulink_connect_ports, simulink_set_block_params, simulink_delete_block
  Combine: simulink_compile_diagnostics after each batch
  Verify: simulink_trace_port_connections, simulink_query_params
```

- [ ] **Step 4: Export manifest after the measurement batch and validate it**

Expected manifest facts:

- `measurement.mode = vi`
- no unit still depends on feedback-only `PeFb_*`

```text
Step 4A: inspect measurement-chain facts
  Tool: simulink_get_block_tree, simulink_query_params, simulink_trace_port_connections
  Combine: none
  Verify: no active path still routes through feedback-only Pe blocks

Step 4B: aggregate semantic manifest
  Tool: simulink_run_script
  Combine: export_kundur_semantic_manifest.m
  Verify: measurement.mode=vi and alignment stays green
```

- [ ] **Step 5: Port lines, loads, and disturbance banks third**

Required batch:

- transmission lines and loads use SPS equivalents
- disturbance remains amplitude-controlled
- disturbance no longer relies on Simscape warm-start behavior

```text
Step 5A: preflight line/load/disturbance libraries
  Tool: simulink_library_lookup
  Combine: none
  Verify: exact SPS element paths are known

Step 5B: migrate electrical network batches with compile after each batch
  Tool: simulink_add_block, simulink_delete_block, simulink_connect_ports, simulink_set_block_params
  Combine: simulink_compile_diagnostics after each batch
  Verify: simulink_get_block_tree, simulink_trace_port_connections, simulink_query_params
```

- [ ] **Step 6: Remove startup-only crutches as a dedicated batch**

Remove:

- `PrefRamp_*`
- `PrefSat_*`
- any comment or block whose only role is “wait for ramp / warmup to finish”

```text
Step 6A: delete startup-only blocks explicitly
  Tool: simulink_get_block_tree, simulink_delete_block
  Combine: none
  Verify: get_block_tree no longer finds PrefRamp_* or PrefSat_*

Step 6B: compile immediately after crutch removal
  Tool: simulink_compile_diagnostics
  Combine: none
  Verify: no new compile failure is introduced by the cleanup batch
```

- [ ] **Step 7: Export manifest after every batch and fail fast on drift**

Pass criteria:

- candidate profile alignment returns `[]`
- no manifest reintroduces `SolverConfig`, `PrefRamp_*`, or `feedback` measurement mode

```text
Step 7A: do not aggregate semantic facts blindly
  Tool: simulink_get_block_tree, simulink_solver_audit, simulink_query_params
  Combine: export_kundur_semantic_manifest.m via simulink_run_script only after raw facts are green
  Verify: validate_kundur_alignment returns [] after every batch
```

- [ ] **Step 8: Commit after each successful batch**

Recommended commit subjects:

```bash
git commit -m "feat: port kundur sps source layer"
git commit -m "feat: port kundur sps measurement chain"
git commit -m "feat: port kundur sps lines loads and disturbances"
git commit -m "fix: remove startup crutches from kundur sps candidate"
```

## Task 8: Rewrite Probes, Tests, And Harness Gates Around The New Invariants

**Files:**
- Modify: `probes/kundur/validate_phase3_zero_action.py`
- Create: `probes/kundur/probe_warmup_trajectory.m`
- Modify: `tests/test_simulink_bridge.py`
- Modify: `tests/test_modeling_tasks.py`
- Modify: `scenarios/kundur/NOTES.md`

Execution shape for runtime validation in this task:

```text
Step N: [runtime check]
  Tool: simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot, simulink_step_diagnostics
  Combine: use probe scripts only when a multi-signal or multi-episode capture cannot be expressed cleanly through the public MCP surface
  Verify: probe output and MCP snapshots agree on the same invariant
```

- [ ] **Step 1: Rewrite zero-action around the new physical invariant**

Old invariant:

- “warmup long enough and drift small”

New invariant:

- “no structural warmup compensation is needed”
- “`Pe` is near nominal immediately”
- “no hidden clamp masquerades as stability”

```text
Step 1A: express the routine zero-action check in MCP terms first
  Tool: simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot, simulink_step_diagnostics
  Combine: validate_phase3_zero_action.py wraps these checks into a reusable regression helper
  Verify: snapshots show immediate Pe alignment without long physical warmup
```

- [ ] **Step 2: Add a dedicated warmup/reset probe**

`probe_warmup_trajectory.m` must answer:

- episode 2 reset state matches episode 1 reset state
- reset time is technical, not physical
- `omega`, `Pe`, and source phase are already aligned without a long settling stage

```text
Step 2A: prefer MCP runtime tools for reset trajectory capture
  Tool: simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot
  Combine: use probe_warmup_trajectory.m only if the required multi-episode capture is too tightly coupled for the current public surface
  Verify: episode-1 and episode-2 reset snapshots match
```

- [ ] **Step 3: Add or update bridge tests**

Required assertions:

- candidate profile implies `pe_measurement='vi'`
- candidate profile implies `phase_command_mode='absolute_with_loadflow'`
- candidate manifest forbids `feedback`-only measurement chain on the SPS route

- [ ] **Step 4: Make harness output the drift clearly**

Expected `model_report` key finding examples:

- `pref_ramp present while profile forbids it`
- `solver_config present while profile forbids it`
- `measurement mode feedback mismatches profile vi`

- [ ] **Step 5: Run the updated tests**

Run:

```bash
pytest tests/test_simulink_bridge.py tests/test_modeling_tasks.py -q
```

Expected: all selected tests pass

- [ ] **Step 6: Commit**

```bash
git add probes/kundur/validate_phase3_zero_action.py probes/kundur/probe_warmup_trajectory.m tests/test_simulink_bridge.py tests/test_modeling_tasks.py scenarios/kundur/NOTES.md
git commit -m "feat: gate kundur sps migration with profile and manifest invariants"
```

## Task 9: Run Full Gates And Perform The Final Cutover

**Files:**
- Generated: `results/harness/kundur/20260424-candidate-gates/manifest.json`
- Generated: `results/harness/kundur/20260424-candidate-gates/model_inspect.json`
- Generated: `results/harness/kundur/20260424-candidate-gates/model_report.json`
- Modify: `scenarios/kundur/simulink_models/kundur_vsg.slx`
- Modify: `scenarios/kundur/simulink_models/kundur_vsg_sps.slx`
- Update: `docs/paper/experiment-index.md`

- [ ] **Step 1: Run the candidate through A2 and G1**

Required order:

1. export candidate semantic manifest
2. run `validate_phase3_zero_action.py`
3. confirm no profile/manifest drift

```text
Step 1A: use harness + MCP discovery as the default gate path
  Tool: scenario_status, model_inspect, model_diagnose
  Combine: model_inspect performs MCP discovery first; semantic manifest export remains a run_script aggregation step
  Verify: model_report contains no profile/manifest drift and no compile/runtime anomaly requiring model-side repair

Step 1B: run the zero-action physical gate
  Tool: simulink_runtime_reset, simulink_run_window, simulink_signal_snapshot, simulink_step_diagnostics
  Combine: validate_phase3_zero_action.py as reusable wrapper
  Verify: G1 passes without long warmup or false stability
```

- [ ] **Step 2: Run the Smoke Bridge**

```text
Step 2A: launch smoke through the registered control-surface tools
  Tool: train_smoke_start, train_smoke_poll
  Combine: inspect the produced train_smoke_start.json / train_smoke_poll.json records
  Verify: smoke_passed=true and no repeated FastRestart corruption
```

- [ ] **Step 3: Run short training**

Run:

```bash
python scenarios/kundur/train_simulink.py --mode simulink --episodes 20
```

Expected:

- backend boot succeeds at episode 1
- no structural warmup failure
- no systemic `omega_saturated` / `Pe=0` failure mode

```text
Step 3A: consult the launch entry before invoking training
  Tool: get_training_launch_status
  Combine: launch the returned command exactly once
  Verify: training_status can observe the active run and the run starts cleanly at episode 1
```

- [ ] **Step 4: Compare against the old failure modes explicitly**

Answer these in `docs/paper/experiment-index.md`:

- Is `T_WARMUP` still needed for physics, or only for technical reset?
- Is any `P_ref` ramp still present in the active path?
- Did `delta = -90 deg` false stability reappear?
- Did `omega_saturated` disappear or become rare under zero action?

- [ ] **Step 5: Cut over without changing the canonical scenario name**

Do:

1. archive current legacy file as `scenarios/kundur/simulink_models/kundur_vsg_ee_legacy.slx`
2. save the passing candidate model as `scenarios/kundur/simulink_models/kundur_vsg.slx`
3. keep `kundur_vsg_sps.slx` only if it is still useful as a build-side shadow; otherwise remove it after verifying the canonical file is correct

```text
Step 5A: save and close models through Simulink tools before filesystem renames
  Tool: simulink_save_model, simulink_close_model
  Combine: archive/rename the .slx files only after the canonical save succeeds
  Verify: scenario registry still resolves kundur -> kundur_vsg.slx and the canonical file reloads cleanly
```

- [ ] **Step 6: Record the cutover outcome**

Update:

- `scenarios/kundur/NOTES.md`
- `docs/paper/experiment-index.md`

- [ ] **Step 7: Commit**

```bash
git add scenarios/kundur/simulink_models/kundur_vsg.slx scenarios/kundur/simulink_models/kundur_vsg_ee_legacy.slx docs/paper/experiment-index.md scenarios/kundur/NOTES.md
git commit -m "feat: cut over kundur training path to sps phasor"
```

## Definition Of Done

- Kundur active training path is `SPS + powergui(Phasor)`, not `ee_lib + SolverConfig`.
- JSON profile exists and only controls known semantic slots.
- semantic manifest can be exported on demand and is attached to harness inspection output.
- `profile <-> manifest` drift is machine-detectable.
- active SPS route has no `PrefRamp_*`, no `feedback`-only measurement dependency, and no long physical warmup dependency.
- `probe_sps_minimal`, zero-action, smoke, and short training all pass.
- old `ee_lib` path is archived for regression archaeology, not retained as the active route.

## Risks To Watch

- MATLAB library lookup drift: SPS block names can vary by release; fix `probe_sps_minimal.m` before mass model edits.
- Manifest underspecification: if the exporter only emits block names but not semantic roles, it will not help debugging.
- Runtime drift: if `config_simulink.py` still hardcodes values that disagree with the selected JSON profile, the intent layer is fake.
- Harness drift: if `model_inspect` exports a manifest but `model_report` does not surface mismatches, engineers will ignore the new gate.
- Cutover drift: if the candidate is promoted under a new canonical name too early, scenario registry churn will hide model regressions instead of isolating them.
