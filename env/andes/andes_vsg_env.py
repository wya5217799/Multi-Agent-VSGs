"""
ANDES 版多智能体 VSG 环境 — Kundur 两区域系统
=============================================

在 ANDES Kundur 两区域系统上:
  - 保留 4 台 GENROU 同步发电机
  - 额外添加 4 台 GENCLS 作为 VSG 储能 (经典摇摆方程 ≈ VSG)
  - RL agent 实时调节 VSG 的 M(=2H) 和 D
  - 通过 TDS 暂停-修改-恢复 实现 RL 控制循环

运行环境: WSL + Python 3.12 + ANDES 2.0.0

论文对应: Yang et al., IEEE TPWRS 2023
"""

import numpy as np
import andes
import warnings

from env.andes.base_env import AndesBaseEnv
from scenarios.contract import KUNDUR as _CONTRACT

warnings.filterwarnings("ignore")


class AndesMultiVSGEnv(AndesBaseEnv):
    """基于 ANDES 的 Kundur 两区域 VSG 控制环境.

    系统拓扑: 修改版 Kundur 两区域系统
      - Area 1: Gen1 (bus1), Gen2 (bus2), VSG1 (bus5), VSG2 (bus6)
      - Area 2: Gen3 (bus3), Gen4 (bus4), VSG3 (bus9), VSG4 (bus10)
      - 4 台 GENCLS 模拟 VSG 储能
    """

    N_AGENTS = _CONTRACT.n_agents

    # VSG 接入母线 (论文扩展拓扑 Fig. 3)
    VSG_BUSES = [12, 16, 14, 15]

    # 新增母线 → 连接到的已有母线
    NEW_BUS_CONNECTIONS = {
        12: 7,    # ES1: Bus12 → Bus7
        16: 8,    # ES2: Bus16 → Bus8
        14: 10,   # ES3: Bus14 → Bus10
        15: 9,    # ES4: Bus15 → Bus9
    }

    # Bus 8 附加 100MW 风电场 (论文: "a 100MW wind farm is connected to bus 8")
    # 直接挂在 Bus 8 上, 无需新增母线
    WF2_BUS = 8
    WF2_SN = 100.0                   # MVA
    WF2_P0 = 1.0                     # p.u. on WF2_SN base

    NEW_BUS_VN = 230.0     # kV (与原系统一致)

    # 新增负荷 (论文测试场景中扰动的负荷点)
    NEW_LOADS = {
        14: {"p0": 2.48, "q0": 0.0},  # Bus 14 稳态负荷 (减载测试前)
        15: {"p0": 0.0, "q0": 0.0},   # Bus 15 稳态负荷 (增载测试前为 0)
    }

    # 通信拓扑: 4-node ring
    COMM_ADJ = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}

    # 扰动范围 (p.u. on 100MVA base)
    DIST_MIN = 0.5                   # 最小扰动
    DIST_MAX = 2.0                   # 最大扰动

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None):
        super().__init__(random_disturbance=random_disturbance,
                         comm_fail_prob=comm_fail_prob,
                         comm_delay_steps=comm_delay_steps,
                         forced_link_failures=forced_link_failures)
        self.case_path = andes.get_case("kundur/kundur_full.xlsx")

    def _build_system(self):
        """加载 Kundur 系统, 扩展拓扑 (Fig.3), 添加 4 台 VSG + Bus8 风电场."""
        ss = andes.load(self.case_path, default_config=True, setup=False)

        # G4 替换为风电场 (setup 后修改惯量)
        self._g4_genrou_idx = 4

        # 添加新母线 (VSG 接入点, Bus 8 已存在无需新增)
        for new_bus in self.VSG_BUSES:
            if new_bus not in list(ss.Bus.idx.v):
                ss.add("Bus", {
                    "idx": new_bus,
                    "name": f"Bus{new_bus}",
                    "Vn": self.NEW_BUS_VN,
                    "v0": 1.0, "a0": 0.0,
                    "area": 1 if new_bus in (12, 16) else 2,
                })

        # 添加传输线路
        for new_bus, parent_bus in self.NEW_BUS_CONNECTIONS.items():
            ss.add("Line", {
                "idx": f"Line_{parent_bus}_{new_bus}",
                "bus1": parent_bus, "bus2": new_bus,
                "Vn1": self.NEW_BUS_VN, "Vn2": self.NEW_BUS_VN,
                "r": self.NEW_LINE_R, "x": self.NEW_LINE_X, "b": self.NEW_LINE_B,
            })

        # 添加负荷 (Bus 14, Bus 15)
        for load_bus, load_params in self.NEW_LOADS.items():
            ss.add("PQ", {
                "idx": f"PQ_Bus{load_bus}", "bus": load_bus,
                "Vn": self.NEW_BUS_VN,
                "p0": load_params["p0"], "q0": load_params["q0"],
            })

        # 添加 4 台 VSG (GENCLS)
        self.vsg_idx = []
        for i, bus in enumerate(self.VSG_BUSES):
            vsg_id = f"VSG_{i+1}"
            gen_id = f"SG_VSG_{i+1}"
            ss.add("PV", {
                "idx": gen_id, "name": f"VSG{i+1}", "bus": bus,
                "Vn": self.NEW_BUS_VN, "Sn": self.VSG_SN,
                "p0": 0.5, "q0": 0.0,
                "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0,
            })
            ss.add("GENCLS", {
                "idx": vsg_id, "bus": bus, "gen": gen_id,
                "Vn": self.NEW_BUS_VN, "Sn": self.VSG_SN,
                "M": self.M0[i], "D": self.D0[i],
                "ra": 0.001, "xd1": 0.15,
            })
            self.vsg_idx.append(vsg_id)

        # Bus 8 附加 100MW 风电场 (低惯量 GENCLS, 与 G4 处理方式一致)
        ss.add("PV", {
            "idx": "SG_WF2", "name": "WF2_Bus8", "bus": self.WF2_BUS,
            "Vn": self.NEW_BUS_VN, "Sn": self.WF2_SN,
            "p0": self.WF2_P0, "q0": 0.0,
            "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0,
        })
        ss.add("GENCLS", {
            "idx": "WF2", "bus": self.WF2_BUS, "gen": "SG_WF2",
            "Vn": self.NEW_BUS_VN, "Sn": self.WF2_SN,
            "M": 0.1, "D": 0.0,       # 近零惯量, 模拟风电场
            "ra": 0.001, "xd1": 0.15,
        })

        ss.setup()

        # G4 惯量降至近零 (模拟风电场)
        if hasattr(self, '_g4_genrou_idx'):
            genrou_idx_list = list(ss.GENROU.idx.v)
            if self._g4_genrou_idx in genrou_idx_list:
                ss.GENROU.set("M", self._g4_genrou_idx, 0.1, attr='v')
                ss.GENROU.set("D", self._g4_genrou_idx, 0.0, attr='v')

        # 保持默认 criteria=1, TDS 频率越界时报失败
        # → tds_failed=True → -50 惩罚 + 提前终止 → 给 agent 强学习信号
        return ss

    def _apply_disturbance(self, delta_u=None, **kwargs):
        """施加 PQ 负荷扰动 (随机选择任意 PQ 母线).

        使用 Ppf (常功率模式) 而非 p0, 确保 TDS 期间负荷变化生效.
        """
        if delta_u is not None:
            for pq_idx, dp in delta_u.items():
                pq_pos = list(self.ss.PQ.idx.v).index(pq_idx)
                self.ss.PQ.Ppf.v[pq_pos] += dp
        elif self.random_disturbance:
            n_pq = self.ss.PQ.n
            if n_pq > 0:
                pq_pos = self.rng.integers(0, n_pq)
                magnitude = self.rng.uniform(self.DIST_MIN, self.DIST_MAX)
                sign = self.rng.choice([-1, 1])
                self.ss.PQ.Ppf.v[pq_pos] += sign * magnitude

        # 无条件设置, ANDES TDS 需要此标志来检测参数变化
        self.ss.TDS.custom_event = True
