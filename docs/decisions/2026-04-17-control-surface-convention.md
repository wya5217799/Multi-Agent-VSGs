# Control Surface Convention — 2026-04-17

## 三个控制层的术语定义

| 术语 | 含义 | 代码入口 |
|------|------|---------|
| **Model Harness** | 建模质量门（modeling quality gate）：scenario_status / model_inspect / model_patch_verify / model_diagnose / model_report | `engine/mcp_simulink_tools.py` |
| **Smoke Bridge** | 入口验证桥（entry verification bridge）：连接 Model Harness 与 Training Control Surface；train_smoke_* 工具 | `engine/mcp_simulink_tools.py` |
| **Training Control Surface** | 训练观察/诊断/评估面（NOT a harness）：get_training_launch_status / training_status / training_diagnose / training_evaluate_run / training_compare_runs | `engine/training_launch.py` + `engine/mcp_simulink_tools.py` |

## 命名规则

- `harness` 一词**仅指** Model Harness（建模正确性门），不泛指训练流程。
- "训练 harness" 是旧叙事，已废弃；统一改为 **Training Control Surface**。
- MCP 工具名 `harness_train_smoke_*` 暂保留（改名见后置 D-3）。

## 机读注册表

`docs/control_manifest.toml` — 合并自原 `navigation_manifest.toml` + `agent_control_manifest.toml`，是唯一 TOML 注册源。
