# 论文复现报告

## 论文信息

**Yang et al.**, "A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs", *IEEE Transactions on Power Systems*, Vol.38, No.6, Nov 2023.

## 复现范围

完整复现论文 Fig 4-21 的全部实验, 包括:
- ODE 简化模型 (4 母线两区域系统)
- ANDES 完整电磁暂态仿真 (Kundur 两区域系统)
- 可扩展性实验 (N=2, 4, 8)
- New England 10 机 39 节点系统 (8 VSG)

## 方法

### 算法
- **Multi-Agent SAC** (Soft Actor-Critic): 独立学习者, 分布式架构
- 每个 agent 网络: 4 层 x 128 隐藏单元
- 超参数: LR=3e-4, gamma=0.99, tau=0.005, buffer=10000, batch=256

### 系统模型
- **ODE 简化模型**: Kron 约化摇摆方程, H=3s, D=2 p.u.
- **ANDES 模型**: 修改版 Kundur 10 母线 + 4 台 GENCLS (VSG) + 4 台 GENROU

### 对比基线
- 无控制 (固定 H, D 参数)
- 自适应惯量-阻尼控制 (论文 ref [25])
- 集中式 DRL (可扩展性对比)

## 主要结果

### 1. 训练收敛 (Fig 4, 17)

| 系统 | Episodes | 初始奖励 | 最终奖励 |
|------|----------|---------|---------|
| ODE 4-bus | 2000 | -1513 | -840 |
| New England 8-bus | 2000 | -1017 | -544 |
| ANDES Kundur | 2000 | -1067 | -645 |

### 2. 控制性能对比 (Fig 5, 19)

| 方法 | ODE 4-bus | New England 8-bus |
|------|----------|------------------|
| Proposed MADRL | best | -0.10 |
| Adaptive inertia [25] | middle | -0.50 |
| Without control | worst | -1.03 |

MADRL 在所有场景下均优于传统方法.

### 3. 可扩展性 (Fig 14-16)

| N agents | Distributed MADRL | Centralized DRL | 评价 |
|----------|------------------|-----------------|------|
| 2 | -748 | -681 | 两者接近 |
| 4 | -583 | -475 | 集中式略优 |
| 8 | **-551** | **-2929** | 集中式崩溃 |

**核心结论完全复现**: 集中式 DRL 在 N=8 时训练发散 (从 ep800 的 -1595 恶化到 -4386), 而分布式 MADRL 保持稳定收敛.

### 4. 通信鲁棒性 (Fig 10-13)

| 场景 | ODE 版 | ANDES 版 |
|------|--------|---------|
| 正常通信 | baseline | -0.077 |
| 30% 链路故障 | 轻微降低 | -0.084 (8.6% 降) |
| 0.2s 通信延迟 | 轻微降低 | -0.079 (2.3% 降) |

模型在通信故障和延迟下表现鲁棒.

## 与论文的差距

### 模型简化
- 论文: MATLAB/Simulink 含完整 VSG 控制环路 (电压环, 电流环, PLL)
- 本项目: ODE 摇摆方程近似 / ANDES GENCLS 经典模型
- 影响: 时域波形的振幅和阻尼特征有差异, 但定性趋势一致

### 可扩展性 N=2/4
- 论文: 分布式在所有规模下均可比或优于集中式
- 本项目: N=2/4 时集中式略优, N=8 时分布式显著优势
- 原因: 小规模下集中式全局信息优势尚在, 维度不足以导致崩溃

### ANDES 训练效果
- MADRL vs 无控制差距为 2x, 论文可能为 5-10x
- 原因: GENCLS 近似 VSG 的精度有限; 分批训练可能不如连续训练

## 项目结构

```
train.py                  -- ODE 主训练 (Fig 4)
evaluate.py               -- ODE 评估 (Fig 4-13)
train_scalability.py      -- 可扩展性实验 (Fig 14-15)
train_new_england.py      -- New England 系统 (Fig 17-21)
generate_fig16.py         -- Fig 16 可扩展性分析图
train_andes.py            -- ANDES 训练 (WSL)
evaluate_andes.py         -- ANDES 评估 (Fig 4-13 ANDES)
run_all.py                -- 一键运行全部实验
generate_summary.py       -- 生成结果汇总表格
config.py                 -- 全局配置
env/                      -- 环境 (ODE + ANDES)
agents/                   -- SAC agent + 多agent管理
results/figures/          -- 所有图表 (29 张 PNG)
results/summary.md        -- 结果汇总表格
```

## 运行方式

```bash
# 完整运行 (约 4-5 小时)
python run_all.py

# 快速验证 (约 10 分钟)
python run_all.py --quick

# 包含 ANDES (需 WSL + andes_venv)
python run_all.py --andes

# 仅评估 (已有训练模型)
python run_all.py --skip-train
```
