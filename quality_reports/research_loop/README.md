# Research Loop Workspace

Auto research loop runtime artifacts. 见 spec
`quality_reports/specs/2026-05-07_research_loop_design.md`.

## 文件

- `state.json` — daemon + AI 共用运行时状态 (schema § spec §4)
- `round_NN_plan.md` / `round_NN_verdict.md` — caveman 计划+判决
- `handoffs/` + `INDEX.md` — 跨会话续命
- `incidents/` — OOM/NaN/发散 复盘
- `audits/` — 跨 round 现象审计
- `pivots/` — 方向转换提案

## Daemon 启停

启:
```bash
nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &
echo $! > /tmp/rloop_daemon.pid
```

停: `kill $(cat /tmp/rloop_daemon.pid)`

## AI 会话进入

新会话第一句:
> 续 research-loop, 读 quality_reports/research_loop/handoffs/<最新>

或老会话:
> 进 research-loop
