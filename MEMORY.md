# Project Memory Index

This file is the navigation layer for repo-native project memory. Keep entries
short and link to the source record instead of duplicating document bodies.

## Navigation

Agent entry points are defined in `AGENTS.md` (governed by `docs/control_manifest.toml`).
This file is an index only — do not maintain a parallel Start Here list here.

- **`quality_reports/specs/2026-05-07_research_loop_design.md`** — 自动研究循环 spec (3 层架构, daemon + state.json + AI 会话, 跨会话续命, caveman 文档). Skill: `.claude/skills/research-loop/`. Daemon: `scripts/research_loop_daemon.sh`.

## 🎯 Active Work (2026-05-06): ANDES Kundur Paper Reproduction

**Frontier**: ANDES path 已多处达 paper-level (LS1+LS2 cum_rf < 5% diff).

| Status | Item |
|---|---|
| ✓ DONE | dt bug fix (0.6s → 0.2s in `env/andes/base_env.py`) |
| ✓ DONE | V2 hetero env D₀=[20,16,4,8] → no-ctrl LS1 = 103% paper match |
| ✓ DONE | PHI_D=0.05 (balanced) → LS2 DDIC = 5.4% diff (paper-level, n=1) |
| ✓ DONE | Best vs Final ckpt audit → 多 model 论文 5% 内 (top: warmstart_seed42 final = LS1 4.5% / LS2 1.8%) |
| TODO | V2 env + PHI_D=0.05 + best ckpt 三合一重训 5 seed (P0) |
| TODO | PHI_D 0.10/0.20/0.50 sweep (P0) |
| TODO | Sec.IV-D 通信失败 / Sec.IV-E 通信延迟 eval (P1) |
| ✗ 不可消 | max_df 5× (动作范围 + GENROU D=0 + 扰动相对幅值) |

**Key files for new conversations** (按读序):
1. `scenarios/kundur/NOTES_ANDES.md` — 修代码必读 (V1/V2 env, results 目录, verdicts, 失败模式)
2. `docs/paper/andes_replication_status_2026-05-06.md` — 论文复现量级对账表
3. `paper/figures/ENV_COMPARISON_V1_V2.md` — V2 hetero env 设计 + sweep 结果
4. `docs/paper/kd_4agent_paper_facts.md` — 论文事实唯一规范
5. `CLAUDE.md` §当前活跃路径 = ANDES Kundur

**Key data dirs** (2026-05-06):
- `results/andes_eval_bestckpt_re_eval_2026-05-06/` — best vs final 全扫
- `results/andes_eval_paper_specific_v2/` — V1 paper-aligned LS traces
- `results/andes_eval_specific_v2_d0_20_16_4_8/` — V2 final hetero env
- `results/andes_postfix_balanced_seed{42,43,44}/` — PHI_D=0.05 训过的 3 seed

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
- [2026-04-24 Simulink toolbox single-source layout](docs/decisions/2026-04-24-simulink-toolbox-single-source-layout.md) - one canonical shared skill at ~/.shared-skills, junctions from .codex/.claude; project-specific routing in docs/agent_layer/simulink-project-routing/

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
