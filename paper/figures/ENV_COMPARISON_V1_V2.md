# V1 vs V2 ANDES env baseline 对比 (2026-05-06)

> ⚠ **2026-05-07 更新**: 本文件 cum_rf "完美匹配 103%" 声明被 6-axis 推翻.
> V2 env 仅 sync 积分量级匹配, max_df / final_df / settling / range / smoothness 5/6 axis 全 fail.
> 真实状态: `docs/paper/andes_replication_status_2026-05-07_6axis.md`
>
> ⚠ **2026-05-07 L4 重构**: 文中所有 `_eval_paper_specific.py` / `_v2_d0_sweep.py` /
> `_v2_linex_sweep.py` / `_run_v2_5seed.sh` 命令是 R0 期 (2026-04~05) 历史快照.
> 这些脚本现已归档至 `scenarios/kundur/_legacy_2026-04/`. **不要用作当前 eval 入口**;
> 当前 paper-spec eval 唯一脚本 = `scripts/research_loop/eval_paper_spec_v2.py`.

## TL;DR (旧 cum_rf 单维)

V2 默认 = `D₀=[20,16,4,8]` (2026-05-06 sweep verdict).

| 指标 | 论文 | V1 (D₀=4 uniform) | V2 final (D₀=[20,16,4,8]) | cum_rf 匹配度 |
|---|---|---|---|---|
| LS1 no-ctrl cum_rf | -1.61 | -0.95 (59%) | **-1.66 (103%)** | 几乎完美 |
| LS1 no-ctrl max_df | 0.12 Hz | 0.59 | 0.63 | ✗ 仍 5× |
| LS2 no-ctrl cum_rf | -0.80 | -0.80 (100%) | -0.72 (90%) | ✓ 90% |
| LS2 no-ctrl max_df | 0.08 Hz | 0.52 | 0.48 | ✗ 6× |
| 4-node Δf 分化 | 显著 | 弱 (过同步) | **强** | ✓ 论文 §IV-C 一致 |

## 改了什么 (V2 vs V1)

V2 在 V1 基础上做 4 处变更, **拓扑/PHI/reward/通信图全部不变**:

```python
# env/andes/andes_vsg_env_v2.py
class AndesMultiVSGEnvV2(AndesMultiVSGEnv):
    VSG_M0 = 30.0  # 1.5x V1
    VSG_D0 = 4.0   # 兜底; 实际用异质
    D0_HETEROGENEOUS = np.array([20.0, 16.0, 4.0, 8.0])  # 按电气距离反比
    DM_MIN, DM_MAX = -12.0, 40.0   # V1 [-10, 30]
    DD_MIN, DD_MAX = -15.0, 45.0   # V1 [-10, 30]
    NEW_LINE_X = 0.20              # V1 0.10 (拉长 ESS-bus 接入线)
```

异质 D₀ 设计原理: 4 ESS 在 Bus 12/14/15/16, LS1=Bus14 LS2=Bus15
- ES1@Bus12→Bus7  (远 LS1, D=20 强 damp)
- ES2@Bus16→Bus8  (远 LS1, D=16 强 damp)
- ES3@Bus14→Bus10 (在 LS1 disturbance bus, D=4 弱 damp)
- ES4@Bus15→Bus9  (在 LS2 disturbance bus, D=8 中等 damp)

## 切换方式

```bash
# V1 默认 (env var 不设)
python scenarios/kundur/_eval_paper_specific.py

# V2 (设环境变量)
EVAL_PAPER_SPEC_ENV=v2 \
EVAL_PAPER_SPEC_OUT_DIR=$ROOT/results/andes_eval_paper_specific_v2_envV2_hetero \
python scenarios/kundur/_eval_paper_specific.py
```

## D₀ Sweep 结果 (2026-05-06)

`scenarios/kundur/_v2_d0_sweep.py` 跑 4 组 D₀ × 4 场景:

| D₀ hetero | LS1 cum_rf | LS1 max_df | LS2 cum_rf | LS2 max_df |
|---|---|---|---|---|
| [10, 8, 2, 4]   | -2.22 (138%) | 0.69 | -1.12 (140%) | 0.53 |
| **[20, 16, 4, 8]** ← 默认 | **-1.66 (103%)** | 0.63 | **-0.72 (90%)** | 0.48 |
| [30, 24, 6, 12] | -1.31 (81%)  | 0.58 | -0.53 (66%)  | 0.44 |
| [40, 32, 8, 16] | -1.09 (68%)  | 0.53 | -0.41 (52%)  | 0.41 |

## NEW_LINE_X Sweep 结果 (2026-05-06, D₀ 锁 [20,16,4,8])

`scenarios/kundur/_v2_linex_sweep.py` 跑 5 组 NEW_LINE_X × 2 场景:

| LINE_X | LS1 cum_rf | LS1 max_df | LS2 cum_rf | LS2 max_df |
|---|---|---|---|---|
| 0.10 (V1) | -0.95 (59%) | 0.59 | -0.80 (100%) | 0.52 |
| **0.20 (V2 default)** | **-1.66 (103%)** | 0.63 | **-0.72 (90%)** | 0.48 |
| 0.30 | -2.82 (175%) ↑超调 | 0.65 | -1.09 (136%) | 0.48 |
| 0.40 | -2.37 (147%) | 0.81 | -1.30 (163%) | 0.53 |
| 0.60 | DIVERGE | - | - | - |

**洞察**:
- LINE_X 0.10→0.20 让 cum_rf 量级从 59% 跃到 103%
- LINE_X > 0.20 cum_rf 超调论文; max_df 无显著改善
- LINE_X = 0.60 power flow 不收敛
- **max_df 与拓扑参数解耦**, 残差不在 NEW_LINE_X / D₀ 能解决的范围

锁 V2 默认: **D₀=[20,16,4,8] + NEW_LINE_X=0.20**.

## 关键洞察 (2026-05-07 6-axis 修正)

### V2 解决了 cum_rf 量级问题 (sync 积分匹配)
V1 cum_rf 量级偏小是 4 ESS 同质 D₀ 的对称性退化. V2 异质 D₀ 制造 sync 失同步 →
cum_rf 量级正确, 甚至略超调论文 (138-140%).

### 但 6-axis 仍 fail
V2 仅在 cum_rf 单维匹配, **physical 动态 5 axis 仍 0 分**:
- max_df 仍 5× 论文
- final_df 仍 4× 论文
- settling 仍 ∞
- ΔH/ΔD range 仍 70/45× 偏小

要 6-axis paper-aligned 需要:
- Phase A: action smoothing penalty (smoothness axis)
- Phase B: 启 IEEEG1 governor (max_df / final_df / settling)
- Phase C: H₀=50 + ΔH=[-50,150] (range axis)

详见 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

## V1 model checkpoint 兼容性

V1 SAC actor 在 V2 env 下 zero-shot 表现见 6-axis ranking. V2-trained actor 由于 V2 env 训练
数值不稳 (TDS fails 7%) 反而不如 V1 actor.

## 已落数据

| 路径 | 内容 |
|---|---|
| `results/andes_eval_paper_specific/` | V1 legacy (dt=0.6/30s) |
| `results/andes_eval_paper_specific_v2/` | V1 paper-aligned (dt=0.2/10s) |
| `results/andes_eval_paper_specific_v2_envV2_hetero/` | **V2 final (D 异质) - 主要数据源** |
| `results/andes_eval_specific_v2_d0_*` | V2 D₀ sweep (4 配置) |
| `results/andes_eval_specific_v2_linex_*` | V2 NEW_LINE_X sweep (5 配置) |
| `results/andes_v2_d0_sweep_summary.json` | D₀ sweep summary |
| `results/andes_v2_linex_sweep_summary.json` | LINE_X sweep summary |

## 文件

```
env/andes/andes_vsg_env_v2.py                                          — V2 子类
scenarios/kundur/_legacy_2026-04/_eval_paper_specific.py               — [archived] 历史 EVAL_PAPER_SPEC_ENV 切换 (2026-05-07 stash 事故丢的脚本; 现 eval = scripts/research_loop/eval_paper_spec_v2.py)
scenarios/kundur/_legacy_2026-04/_v2_d0_sweep.py                       — [archived] D₀ sweep 工具
scenarios/kundur/_legacy_2026-04/_v2_linex_sweep.py                    — [archived] LINE_X sweep 工具
scenarios/kundur/train_andes_v2.py                                     — V2 train 包装
scenarios/kundur/_legacy_2026-04/_run_v2_5seed.sh                      — [archived] V2 5-seed 启动
```
