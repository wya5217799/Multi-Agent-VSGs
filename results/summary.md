# 实验结果汇总 — Yang et al. TPWRS 2023 论文复现

## 1. ODE 简化模型训练 (Fig 4)
- Episodes: 2000
- 初始奖励 (前100ep avg): -1513.3
- 最终奖励 (末100ep avg): -840.4

## 2. 可扩展性实验 (Fig 14-16)

| N | 分布式 MADRL | 集中式 DRL | 差距 |
|---|-------------|-----------|------|
| 2 | -747.7 | -680.9 | 0.91x |
| 4 | -583.4 | -475.0 | 0.81x |
| 8 | -551.1 | -2928.5 | 5.31x |

## 3. New England 系统 (Fig 17-21)
- Episodes: 2000
- 初始奖励 (前100ep avg): -1017.4
- 最终奖励 (末100ep avg): -544.3

### Fig 19 三方对比 (50 test episodes)

| 方法 | 平均频率同步奖励 |
|------|-----------------|
| Proposed MADRL | -0.10 |
| Adaptive inertia [25] | -0.50 |
| Without control | -1.03 |

## 4. ANDES 完整系统

- 总训练 Episodes: 2000 (4轮累计)
- 初始奖励 (前50ep avg): -1066.6
- 最终奖励 (末100ep avg): -644.9

### ANDES 评估结果

| 测试 | MADRL avg | No Control avg | 差距 |
|------|----------|---------------|------|
| Fig 5 累积奖励 | -0.08 | -0.16 | 2.0x |
| Fig 10 通信故障 (30%) | -0.084 | — | 8.6% 降幅 |
| Fig 12 通信延迟 (0.2s) | -0.079 | — | 2.3% 降幅 |

## 5. 图表清单

共 29 张图:

| 图号 | 文件名 | 大小 |
|------|--------|------|
| ANDES Fig 10 | andes_fig10_comm_failure_reward.png | 92KB |
| ANDES Fig 11 | andes_fig11_comm_failure_td.png | 99KB |
| ANDES Fig 12 | andes_fig12_comm_delay_reward.png | 89KB |
| ANDES Fig 13 | andes_fig13_comm_delay_td.png | 104KB |
| ANDES Fig 4 | andes_fig4_training.png | 176KB |
| ANDES Fig 5 | andes_fig5_cumulative.png | 71KB |
| ANDES Fig 6 | andes_fig6_ls1_no_ctrl.png | 102KB |
| ANDES Fig 7 | andes_fig7_ls1_ctrl.png | 94KB |
| ANDES Fig 8 | andes_fig8_ls2_no_ctrl.png | 103KB |
| ANDES Fig 9 | andes_fig9_ls2_ctrl.png | 94KB |
| 附加 | andes_training_curves.png | 255KB |
| Fig 10 | fig10_comm_failure_reward.png | 68KB |
| Fig 11 | fig11_comm_failure_td.png | 276KB |
| Fig 12 | fig12_comm_delay_reward.png | 67KB |
| Fig 13 | fig13_comm_delay_td.png | 277KB |
| Fig 14 | fig14_scalability_training.png | 108KB |
| Fig 15 | fig15_scalability_cumulative.png | 138KB |
| Fig 16 | fig16_scalability_analysis.png | 103KB |
| Fig 17 | fig17_ne_training.png | 64KB |
| Fig 18 | fig18_ne_no_ctrl.png | 137KB |
| Fig 19 | fig19_ne_adaptive.png | 72KB |
| Fig 20 | fig20_ne_rl_ctrl.png | 425KB |
| Fig 21 | fig21_ne_short_circuit.png | 58KB |
| Fig 4 | fig4_training_curves.png | 454KB |
| Fig 5 | fig5_cumulative_reward.png | 67KB |
| Fig 6 | fig6_load_step1_no_ctrl.png | 156KB |
| Fig 7 | fig7_load_step1_rl.png | 272KB |
| Fig 8 | fig8_load_step2_no_ctrl.png | 161KB |
| Fig 9 | fig9_load_step2_rl.png | 293KB |

## 6. 核心结论复现情况

| 论文核心结论 | 复现状态 | 证据 |
|------------|---------|------|
| 分布式 MADRL 优于集中式 DRL (大规模) | [OK] 完全复现 | N=8: -551 vs -2929 |
| MADRL 优于自适应惯量方法 | [OK] 复现 | -0.10 vs -0.50 (Fig 19) |
| 通信故障下鲁棒 | [OK] 复现 | 30%故障仅 8.6% 性能降 |
| 通信延迟下鲁棒 | [OK] 复现 | 0.2s延迟仅 2.3% 性能降 |
| 集中式 DRL 大规模训练不稳定 | [OK] 完全复现 | N=8 集中式后期发散 |
