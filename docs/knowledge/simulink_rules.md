# Simulink 建模与调试规则

> 所有 Simulink 工作均适用。环境：MATLAB R2025b。
> 本文件从 CLAUDE.md 抽出，保持 CLAUDE.md 精简；任何 Simulink/MATLAB 工作开始前必读。

## Bug 处理流程

- **严禁**诊断代码
- 本地明确错误（拼写/路径/参数值）直接修复
- 其他失败 → 先读错误输出：
  - 有错误信息 → 查 `docs/knowledge/simulink_debug.md` → 未命中再 WebSearch
  - 无错误信息（超时/崩溃无输出） → 可分段定位后再查
- **不得未查库/搜索直接换 API 重试**
- WebSearch 最多 3 轮（1 轮 = 1 搜索 + 1 修复），不确定或未解决 → 汇总给用户
- 版本相关带版本号

## 批判性审查

用户反馈**或自己搜到的方案**有疑点/矛盾/版本不匹配 → 指出问题，不盲目采纳。

## 知识库使用

- 改 `.slx` 或 build 脚本前 → 读 `docs/knowledge/simulink_base.md`
- 任何 Simulink/MATLAB 报错（含 `matlab_session` / `simulink_bridge` / `slx_helpers` 冒泡的错误）→ 先查 `docs/knowledge/simulink_debug.md`
  - 命中则照做
  - 未命中 → 走上述 Bug 处理流程
- 只存**可复现的 Simulink 行为问题**（非一次性拼写/路径错误），存回库后展示用户确认

## 有界性检查（debug 分流门控）

进入假设测试前先问：能否列出 ≤5 个具体原因？

- **能** → 正常 systematic-debug
- **不能**（API 行为未知 / 无 error / 首次遇到该 block）→ 这是**无界问题**，**禁止盲试**
  - 改走发现流程：WebSearch 1 轮定位 → 未解决则给用户具体关键词停手

## 新 block 预飞行发现

知识库未覆盖的 block 类型，建模前必须：

1. 用 `connectionPortProperties` + `isfield` 逐一查端口和参数名
2. 将结果存入 `docs/knowledge/simulink_base.md`
3. 再开始建模

一次发现成本 1-2k token，后续使用零探索成本。

## 建模后验证

目前无自动参数审计工具。build 脚本写完后，参数合法性请手动用 `simulink_query_params` 查询关键 block 参数，确认物理量纲和范围正确。

## 基础设施约束

- 遇到工具超时 / MCP 限制等非 Simulink 问题：确认根因后立即停下，告知用户并列出可选方案，**不得持续擅自尝试**
- Build 脚本超时默认方案：
  1. 先用 `simulink_run_script_async` 提交后台执行
  2. 再用 `simulink_poll_script(job_id)` 轮询结果
  3. 若仍超时，交付脚本让用户在 MATLAB 命令行手动运行

## Windows 进程启动（强制）

- 从 Claude Code (Git Bash) 启动独立训练窗口，**必须用** `powershell -Command "Start-Process powershell ..."`
- **禁止**用 bash `start`（exit code 0 但静默失败）
- 启动后必须查 PID 验证进程存在
- 推荐入口：`scripts/launch_training.ps1 both`

## 建模操作模式（强制）

- 所有 `add_block` / `set_param` / `addConnection` 必须先用 Write 工具写成 `.m` 脚本
- 再用 `mcp__matlab__evaluate_matlab_code("slx_run_quiet('脚本名')")` 一次执行
- **禁止**逐行 `evaluate_matlab_code` 做建模操作
- 单次 `get_param` 查询仍可直接调用，无需脚本化

## 批量查询（强制）

查询多个 block 参数用 `slx_batch_query`，不循环调用 `get_param`。

## 建模辅助工具清单（`slx_helpers/`）

| 工具 | 用途 |
|---|---|
| `slx_run_quiet(code)` | 吞输出噪声，只返回关键行 |
| `slx_batch_query(model, blocks)` | 批量参数查询 |
