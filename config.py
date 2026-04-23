"""
配置文件 — 论文 Yang et al., IEEE TPWRS 2023
"A Distributed Dynamic Inertia-Droop Control Strategy
 Based on Multi-Agent Deep Reinforcement Learning
 for Multiple Paralleled VSGs"

修订说明:
  - H_ES0=24, D_ES0=18: modal calibration for ω_n≈0.6 Hz, ζ≈0.05
  - H_ES0=24, D_ES0=18, B_tie=4 → ω_n=0.623 Hz, ζ=0.048, Δf_peak≈0.39 Hz
  - LOAD_STEP_1: 平衡扰动 [2.40,0,-2.40,0] 防 CofI 漂移
  - 采用固定训练集 (100 场景) + 固定测试集 (50 场景)
"""

import numpy as np

from scenarios.contract import KUNDUR as _CONTRACT

# ═══════════════════════════════════════════════════════
#  系统参数 (Section IV-A) — from contract
# ═══════════════════════════════════════════════════════
N_AGENTS = _CONTRACT.n_agents
DT = _CONTRACT.dt                 # 控制步长 0.2s
T_EPISODE = 10.0                  # episode 总时长 10s
STEPS_PER_EPISODE = int(T_EPISODE / DT)  # M = 50
OMEGA_N = 2 * np.pi * _CONTRACT.fn  # 额定角频率 (rad/s)

# ═══════════════════════════════════════════════════════
#  VSG 基础参数
#  H=24, D=18 → ω_n=0.623 Hz, ζ=0.048, Δf_peak≈0.385 Hz
#  与论文 Fig 4 频率偏差量级吻合 (target ~0.4 Hz)
# ═══════════════════════════════════════════════════════
H_ES0 = np.array([24.0, 24.0, 24.0, 24.0])
D_ES0 = np.array([18.0, 18.0, 18.0, 18.0])

# ═══════════════════════════════════════════════════════
#  动作空间 — 惯量/阻尼修正量范围 (Section IV-B)
#  DH: H_min = H_ES0 + DH_MIN = 24 - 16.1 = 7.9 (env floor clamp → H ≥ 8)
#  DH_MAX = 3 × H_ES0 = 72 (允许 H 最大 96)
#  DD: D_min = 18 - 14 = 4; D_max = 18 + 54 = 72
#
#  [M4 A 版口径核查] 论文 Sec.IV-B: ΔH∈[-100,300], ΔD∈[-200,600] (无基准 H_es,0 数值).
#  论文 Eq.(1) H 量纲未明示 (2026-04-21 核查 high_accuracy_transcription_cn.md).
#  项目工作假设 H_paper = 2·H_code (电机学 2H/ω_s 折算, 非论文事实, 见 env/ode/NOTES.md M1).
#  在该假设下换算: ΔH_code=[-16.1,72] → ΔH_paper=[-32.2,144] vs 论文 [-100,300]
#                  ΔD_code=[-14,54]   → ΔD_paper=[-14,54]    vs 论文 [-200,600]
#  结论: 工程基值差 ΔH~2-3×、ΔD~4-11×, 属经验值 (非小信号推导); 量纲等价性依赖工作假设.
#  B 版升级 (改回论文值) 须再训练 + 验证, 见计划 N2.
# ═══════════════════════════════════════════════════════
DH_MIN, DH_MAX = -16.1, 72.0     # ΔH 范围 → H ∈ [7.9, 96.1] s; floor clamp in env enforces H ≥ 8
DD_MIN, DD_MAX = -14.0, 54.0     # ΔD 范围 → D ∈ [4, 72]

# ═══════════════════════════════════════════════════════
#  奖励权重 (Section IV-B: φ_f=100, φ_h=1, φ_d=1)
# ═══════════════════════════════════════════════════════
PHI_F = 100.0
PHI_H = 1.0
PHI_D = 1.0

# ═══════════════════════════════════════════════════════
#  神经网络 (Section IV-A: 4层全连接, 每层128单元)
# ═══════════════════════════════════════════════════════
HIDDEN_SIZES = [128, 128, 128, 128]

# ═══════════════════════════════════════════════════════
#  SAC 超参数 (Table I — 标准默认值)
# ═══════════════════════════════════════════════════════
LR = 3e-4
GAMMA = 0.99
TAU_SOFT = 0.005
BUFFER_SIZE = 10000                # Table I: 10 000 (跨 episode 积累)
BATCH_SIZE = 256                   # Table I: 256
N_EPISODES = 2000
WARMUP_STEPS = 1000                # 积累 ~20 ep (1000 transitions) 后开始更新

# ═══════════════════════════════════════════════════════
#  通信拓扑 — 环形: 0↔1↔2↔3↔0
#  每个 agent 有 2 个邻居 (Section IV-G)
# ═══════════════════════════════════════════════════════
COMM_ADJACENCY = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
MAX_NEIGHBORS = _CONTRACT.max_neighbors
OBS_DIM = 3 + 2 * MAX_NEIGHBORS   # = 7
ACTION_DIM = _CONTRACT.act_dim
COMM_FAIL_PROB = 0.1               # 每条链路每 episode 故障概率

# ═══════════════════════════════════════════════════════
#  电气网络 — 4 母线两区域系统 (Kundur 修改版)
#  均匀链形拓扑 B_tie=4 → ω_n=0.623 Hz, ζ=0.048
#  λ_min = 2×4×(1-cos(π/4)) = 2.343
# ═══════════════════════════════════════════════════════
B_MATRIX = np.array([
    [0, 4,  0,  0],
    [4, 0,  4,  0],
    [0, 4,  0,  4],
    [0, 0,  4,  0],
], dtype=np.float64)

S_BASE = 100.0  # MVA，用于 MW 换算

V_BUS = np.array([1.0, 1.0, 1.0, 1.0])  # 标幺值电压

# ═══════════════════════════════════════════════════════
#  扰动参数 — 产生 0.3~0.6 Hz 频率偏差 (匹配论文)
# ═══════════════════════════════════════════════════════
DISTURBANCE_MIN = 0.5    # 最小扰动功率 (p.u.)
DISTURBANCE_MAX = 3.0    # 最大扰动功率 (p.u.)

# ═══════════════════════════════════════════════════════
#  固定训练集/测试集 (论文 Sec IV-A)
#  "100 randomly generated dataset as training set"
#  "50 randomly generated data set as test set"
# ═══════════════════════════════════════════════════════
N_TRAIN_SCENARIOS = 100
N_TEST_SCENARIOS = 50

# ═══════════════════════════════════════════════════════
#  测试场景 (论文 Sec IV-C)
#  Load Step 1: 248MW 负荷突减 at bus 14 → bus 2 减载
#  Load Step 2: 188MW 负荷突增 at bus 15 → bus 3 增载
# ═══════════════════════════════════════════════════════
LOAD_STEP_1 = np.array([2.40, 0.0, -2.40, 0.0])   # 240MW balanced: gen↑ area1, load↑ area2 — prevents CofI drift; tuned for gate
LOAD_STEP_2 = np.array([0.0, 0.0,  0.0,  1.88])  # 188MW/100MVA (Fig8)

# ═══════════════════════════════════════════════════════
#  训练策略 (Algorithm 1 line 16)
# ═══════════════════════════════════════════════════════
CLEAR_BUFFER_PER_EPISODE = False   # 标准 off-policy SAC，跨 episode 积累经验

# ═══════════════════════════════════════════════════════
#  ODE Fidelity Toggles (default = paper baseline)
# ═══════════════════════════════════════════════════════
ODE_HETEROGENEOUS = False          # True → per-node H/D differ
ODE_H_SPREAD = 0.30                # +/-30 % around each H_ES0[i]
ODE_D_SPREAD = 0.30
ODE_HETEROGENEITY_SEED = 2023      # deterministic spread
ODE_NETWORK_MODE = 'linear'        # 'linear' | 'nonlinear'
ODE_GOVERNOR_ENABLED = False
ODE_GOVERNOR_R = 0.05              # p.u. droop (5 %)
ODE_GOVERNOR_TAU_G = 0.5           # turbine lag (s)
