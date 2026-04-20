# ODE Model Notes

> 修 ODE 模型前必读。与 `docs/paper/yang2023-fact-base.md` 一致。

## 能力开关（config.py）

| 开关 | 默认 | 作用 | 成本 |
|---|---|---|---|
| `ODE_HETEROGENEOUS` | False | 按 `ODE_H_SPREAD` 生成 per-node H/D | 无性能影响 |
| `ODE_NETWORK_MODE` | 'linear' | 'nonlinear' 时用 `Σ B_ij sin(θ_i-θ_j)` | +~30 % step 时间 |
| `ODE_GOVERNOR_ENABLED` | False | 加一阶 droop + τ_G 汽轮机滞后；状态 2N→3N | +~10 % step 时间 |
| (事件 API) | — | `EventSchedule` 传入 `reset(event_schedule=...)` | 对齐 step 边界 |

## 默认 = 论文 Eq.4 对齐

所有开关默认 off 时，`PowerSystem` / `MultiVSGEnv` 行为 baseline-preserving（兼容性门控验证）。
可用 `tests/test_ode_physics_gates.py` 验证。

## 事件 API

`utils/ode_events.py` 提供：
- `DisturbanceEvent(t, delta_u)` — 将当前 Δu 全量替换为新值（所有母线）
- `LineTripEvent(t, bus_i, bus_j)` — 将 B[i,j]=B[j,i]=0 并重建 L
- `EventSchedule(events=(...))` — 冻结的事件序列；必须按 t 单调不减

事件在 step 边界生效（step-boundary 语义）：t=0 事件在 `reset()` 内立即应用；t>0 事件用 `max(0, round(t/dt) - 1) == step_idx` 匹配，已知存在一步提前偏差。亚步精度不支持——若需要，把 dt 调小。

## 已知限制

1. **事件只对齐 step 边界**（<0.2 s 误差）。
2. **governor R / τ_G 全节点共享**——若需要异构 governor，仿 heterogeneity helper 扩展即可。
3. **nonlinear 的 `_coupling` 是 O(N²)**。N=4/10 没问题，N>>100 需要向量化/稀疏化。
4. **governor 不参与 RL 动作空间**——RL agent 只调 H, D；governor 作为背景一次调频动力学。

## 已核实事实

- 与论文一致：Eq.1/4 的 H·Δω̇ 系数约定已统一为 2H（见 power_system 注释）。
- ODE 现有状态：`[Δθ, Δω]` (2N)，governor 开启后扩为 `[Δθ, Δω, P_gov]` (3N)。
- Gate 目标：`ω_n ≈ 0.6 Hz, ζ ≈ 0.05, Δf_peak ≈ 0.4 Hz`（H=24, D=18, B_tie=4）。

## 试过没用的

- （待填）
