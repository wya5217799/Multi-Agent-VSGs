# Project Memory Index

This file is the navigation layer for repo-native project memory. Keep entries
short and link to the source record instead of duplicating document bodies.

## Navigation

Agent entry points are defined in `AGENTS.md` (governed by `docs/control_manifest.toml`).
This file is an index only — do not maintain a parallel Start Here list here.

## Decisions

- [2026-04-05 Harness architecture](docs/decisions/2026-04-05-harness-architecture.md)
- [2026-04-06 Project memory system](docs/decisions/2026-04-06-project-memory-system.md)
- [2026-04-07 Harness repair hints and sync deprecation](docs/decisions/2026-04-07-harness-repair-hints-and-sync-deprecation.md)
- [2026-04-09 Harness boundary convention](docs/decisions/2026-04-09-harness-boundary-convention.md)
- [2026-04-10 Paper baseline contract](docs/decisions/2026-04-10-paper-baseline-contract.md)
- [2026-04-11 Workspace hygiene](docs/decisions/2026-04-11-workspace-hygiene.md)
- [2026-04-11 Nav freshness system](docs/decisions/2026-04-11-nav-freshness-system.md)
- [MCP/Simulink 系统演进计划（跨会话进度追踪）](docs/decisions/evolution-plan.md) — B/C/D/E1-E2/F/H + ACL + Z1 全部完成；E3/G directional
- [2026-04-17 Control Surface Convention](docs/decisions/2026-04-17-control-surface-convention.md) — harness=quality gate / smoke=bridge / training=control surface；control_manifest.toml 合并两旧 manifest

- [2026-04-22 Simulink MCP generalization boundary](docs/decisions/2026-04-22-simulink-mcp-generalization-boundary.md) - general `simulink_*` tools use Simulink vocabulary; VSG/RL semantics stay in project adapters

## Plans (Pending)

- [2026-04-22 Simulink MCP generalization implementation plan](docs/superpowers/plans/2026-04-22-simulink-mcp-generalization-plan.md) - staged plan for general runtime/signal/workspace tools, skill routing, and VSG bridge compatibility

## Plans (Executed)

- [2026-04-12 Agent Control Layer Restructure](docs/history/superpowers/plans/2026-04-12-agent-control-layer-restructure.md) — 双控制线(Model+Training)+单 TOML manifest+导航可测性；Task 1-4 + Z1 全部完成(95bbca7)
- [2026-04-12 Harness Type Contracts & Decomposition](docs/history/superpowers/plans/2026-04-12-harness-type-contracts-and-decomposition.md) — dataclass 合约/modeling+smoke 拆分/显式 flow gate/TrainingCallback E1-E2；Phase 1-3 + E1-E2 完成
- [2026-04-14 Code Understanding Toolchain](docs/history/superpowers/plans/2026-04-14-code-understanding-toolchain.md) — pydeps + import-linter(架构边界 CI) + ast-grep(pattern 库)；全部完成(eb52937)

## Devlog

- [2026-04-10 NE39 phang feedback probe](docs/devlog/2026-04-10-ne39-phang-feedback-probe.md)
- [2026-04-10 Phase 1 artifact contract fixes](docs/devlog/2026-04-10-phase1-artifact-contract-fixes.md)
- [2026-04-10 Test contract alignment](docs/devlog/2026-04-10-test-contract-alignment.md)
- [2026-04-11 Nav manifest semantic enforcement](docs/devlog/2026-04-11-nav-manifest-semantic-enforcement.md)
- [2026-04-11 Simulink run artifact locality](docs/devlog/2026-04-11-simulink-run-artifact-locality.md)
- [2026-04-11 Python runtime alignment and optional ANDES skip](docs/devlog/2026-04-11-python-runtime-alignment-and-optional-andes-skip.md)
- 2026-04-13 MCP Phase B/C/D — B1a 审计+视觉捕获暴露(893c784) + D1 async脚本(5a4a8e5) + D2 RESULT进度标记(bf7bb43)
- 2026-04-14 Phase F — harness flow contract 测试 + 5处 summary overwrite 修复(46c0518)
- 2026-04-14 Phase H — MATLAB stdout 与 MCP JSON-RPC 传输隔离(d6dc3e3); eval()首次输出日志(75fe8b2)
- 2026-04-14 P1-P5 harness 改进 — t_episode/扰动一致性测试 + smoke wrapper + ee_lib_paths 发现分离(752c980)
