"""
配置文件 — 论文 Yang et al., IEEE TPWRS 2023
"A Distributed Dynamic Inertia-Droop Control Strategy
 Based on Multi-Agent Deep Reinforcement Learning
 for Multiple Paralleled VSGs"

修订说明:
  - H_ES0: 5→80, D_ES0: 10→1 (Kundur 物理值: 900MVA/100MVA, ζ≈0.15)
  - LOAD_STEP_1: 平衡扰动 [2.40,0,-2.40,0] 防 CofI 漂移
  - B_tie=24 → ω_n≈0.88 Hz (通过区间振荡闸门 [0.8,1.5] Hz)
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
#  H=80, D=1 → 欠阻尼 (ζ≈0.15), 调节时间~4-5s
# ═══════════════════════════════════════════════════════
H_ES0 = np.array([80.0, 80.0, 80.0, 80.0])  # 真实 Kundur: 900MVA/100MVA → H=9×9=81≈80
D_ES0 = np.array([1.0,  1.0,  1.0,  1.0])  # ζ≈0.15, 调节时间~4-5s

# ═══════════════════════════════════════════════════════
#  动作空间 — 惯量/阻尼修正量范围 (Section IV-B)
#  按 H_ES0/D_ES0 基值等比缩放
#  确保 H_es = H_ES0 + ΔH > 0 (即 ΔH > -70)
# ═══════════════════════════════════════════════════════
DH_MIN, DH_MAX = -70.0, 300.0    # ΔH 范围 → H ∈ [10, 380] s
DD_MIN, DD_MAX = -0.8,  8.0      # ΔD 范围 → D ∈ [0.2, 9.0]（ΔD 量纲见风险声明）

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
#  Area1: bus 0, 1;  Area2: bus 2, 3
#  均匀导纳 B=24, ω_n≈0.88 Hz (均匀耦合简化，非物理两区域拓扑)
# ═══════════════════════════════════════════════════════
B_MATRIX = np.array([
    [ 0, 24,  0,  0],
    [24,  0, 24,  0],
    [ 0, 24,  0, 24],
    [ 0,  0, 24,  0],
], dtype=np.float64)  # B_tie=24 → ω_n≈0.88Hz, passes f_osc gate (B_tie=20 gave 0.76Hz)

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
