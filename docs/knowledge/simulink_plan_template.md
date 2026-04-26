# Simulink 计划模板 — 标准 MCP 工具序列

> 计划作者抄这一页：写涉及 Simulink 的步骤时，按下方模板组合 MCP 工具。
> 引入：[`quality_reports/plans/2026-04-27_simulink_tools_mcp_optimization_plan.md`](../../quality_reports/plans/2026-04-27_simulink_tools_mcp_optimization_plan.md) Phase A.5。

---

## 决策树

```
     Simulink 涉及任务？
            │
       ┌────┴────┐
       │         │
    探索/查参   修改/构建/仿真
       │         │
   library_     │
   lookup       │
   query_      ┌┴────────────────────┐
   params      │                     │
              < 60 s 且确定          > 60 s 或不确定
               │                     │
           run_script              run_script_async
              │                     │
           直接拿结果              poll_script (循环)
                                    │
                                   done
```

---

## 模板 1 — 单个建模/构建步骤

```
对每一步 Simulink 修改：
1. simulink_library_lookup(...)              # 放置前确认参数名 (~ 1 s)
2. simulink_run_script_async(build_*.m)      # 后台跑 build (60+ s)
3. simulink_poll_script(...)                 # 轮询直至 status='done'
4. simulink_compile_diagnostics(mode='update')  # 5 s 编译 sanity
5. （如需）simulink_step_diagnostics(...)    # 短窗口仿真验证
```

**何时跳步：**
- step 1 跳过：你已知该 block 的参数名（罕见，多数时候省 1 次 trial-and-error）
- step 2 用 sync `simulink_run_script` 替代：build 确定 < 60 s 且不阻塞别的工作
- step 5 跳过：编辑无可能改动 sim 行为（如纯命名调整）

---

## 模板 2 — 模型诊断 / debug

```
1. simulink_describe_block_ports(block)             # 拿端口元信息
2. simulink_trace_port_connections(block, port,     # 追踪连接，max_depth=10 默认
                                    max_depth=10)
3. simulink_signal_snapshot(...)                    # 在某时间点读信号
4. simulink_step_diagnostics(...)                   # 短窗口跑，看 warning/error
```

powerlib 物理网（LConn/RConn）不可内省 — 详见 [`docs/knowledge/simulink_debug.md`](simulink_debug.md)。

---

## 模板 3 — 长跑训练 / sweep（不在 MCP 工具范围内）

训练用 `engine/training_launch.py` + `scripts/launch_training.ps1`，不走 simulink-tools MCP。
poll 走 `mcp__simulink-tools__training_status`（**不**走 `simulink_poll_script`）。
详见 [`docs/knowledge/training_management.md`](training_management.md)。

---

## 边界提醒

- **不绕道 shell matlab**：`Bash matlab -batch ...` / 直接 `python -c "import matlab.engine"` 路径会冷启 MATLAB engine（24 min hang 风险），用 long-lived MCP engine
- **timeout 默认 600 s**（sync `simulink_run_script`）/ **300 s**（async）— 长 build 显式传 `timeout_sec=N` 或走 async
- **stdout 编码**：MATLAB 端 UTF-8（已强制）；中文报错可直接显示
- **MCP server 重启**：仅影响工具入口，不影响进程外训练（训练有独立 matlab.engine）

---

## 引用

- [simulink-tools MCP 优化计划](../../quality_reports/plans/2026-04-27_simulink_tools_mcp_optimization_plan.md) — 工具能力路线图
- [simulink_base.md](simulink_base.md) — Simulink 建模基础
- [simulink_debug.md](simulink_debug.md) — 物理网内省限制 + diagnose 模式
- [simulink_rules.md](simulink_rules.md) — 建模规则约束
- [training_management.md](training_management.md) — 训练角色分层
