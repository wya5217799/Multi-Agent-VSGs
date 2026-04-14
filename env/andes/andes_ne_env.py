"""
ANDES 版 New England (IEEE 39-bus) 多智能体 VSG 环境
====================================================

在 ANDES IEEE 39-bus 系统上:
  - G1-G8 (Bus 30-37): M=0.1, D=0, R=999 模拟风电场 (近零惯量)
  - G9-G10 (Bus 38-39): 保留为同步发电机
  - 新增 Bus 40-47 (通过短线路连接 Bus 30-37)
  - 8 台 GENCLS VSG 挂在 Bus 40-47
  - RL agent 实时调节 VSG 的 M(=2H) 和 D

论文对应: Yang et al., IEEE TPWRS 2023, Section IV-G, Fig 17-21
"""

import numpy as np
import andes
import warnings

from env.andes.base_env import AndesBaseEnv
from scenarios.contract import NE39 as _CONTRACT

warnings.filterwarnings("ignore")


class AndesNEEnv(AndesBaseEnv):
    """基于 ANDES 的 New England 39-bus VSG 控制环境.

    系统拓扑: IEEE 39-bus (10 GENROU + 8 VSG GENCLS)
      - G1-G8 (Bus 30-37): 风电场 (M=0.1, D=0, R=999)
      - G9 (Bus 38), G10 (Bus 39): 同步发电机
      - ES1-ES8: GENCLS VSG, 挂在新建 Bus 40-47
    """

    N_AGENTS = _CONTRACT.n_agents
    FN = _CONTRACT.fn                # New England 标称频率 60 Hz

    # NE 系统需要高惯量 VSG, 否则 TDS 发散 (M0<20 → divergence)
    # BackendProfile: ANDES-specific calibration. VSG_M0=20.0 (H0=10s) differs intentionally
    # from Simulink side (VSG_M0=12.0, H0=6s). Both are backend-specific calibrations, not errors.
    # Also note: root config.py still contains old H_ES0=3/D_ES0=2 (v0 system, to be retired).
    VSG_M0 = 20.0
    VSG_D0 = 4.0
    # 动作范围 — see docs/decisions/2026-04-14-action-bounds-audit.md
    # DM: BackendProfile — M0 ratio (20/12=5/3) explains difference vs Simulink. OK.
    DM_MIN = -10.0
    DM_MAX = 30.0
    # DD: PENDING AUDIT — v1 legacy. Proportional target: [-2, 6]. Do not change until
    # ANDES training is complete (risk of breaking trained policies).
    DD_MIN = -10.0
    DD_MAX = 30.0

    # G1-G8 风电场参数
    WIND_FARM_M = 0.1
    WIND_FARM_D = 0.0
    WIND_FARM_GOV_R = 999.0

    # VSG 新母线和连接
    VSG_BUSES = [40, 41, 42, 43, 44, 45, 46, 47]
    PARENT_BUSES = [30, 31, 32, 33, 34, 35, 36, 37]
    VSG_BUS_VN = 22.0        # kV

    # GENROU idx for G1-G8 and their controllers
    GENROU_WIND_IDX = [f"GENROU_{i}" for i in range(1, 9)]
    TGOV_WIND_IDX = [f"TGOV1_{i}" for i in range(1, 9)]

    # 通信拓扑: 8-node ring
    COMM_ADJ = {
        0: [1, 7], 1: [0, 2], 2: [1, 3], 3: [2, 4],
        4: [3, 5], 5: [4, 6], 6: [5, 7], 7: [6, 0],
    }

    # 扰动范围
    DIST_MIN = 1.0
    DIST_MAX = 3.0

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None,
                 x_line=None):
        super().__init__(random_disturbance=random_disturbance,
                         comm_fail_prob=comm_fail_prob,
                         comm_delay_steps=comm_delay_steps,
                         forced_link_failures=forced_link_failures)
        self.x_line = x_line or self.NEW_LINE_X
        self.case_path = andes.get_case("ieee39/ieee39_full.xlsx")
        self._gen_trip = None

    def _pre_build(self, gen_trip=None, **kwargs):
        """存储 gen_trip 以便 _build_system 添加 Toggler."""
        if gen_trip is not None:
            self._gen_trip = gen_trip

    def _build_system(self):
        """加载 IEEE 39-bus, 添加 Bus 40-47 + 8 VSG, 修改 G1-G8 为风电场."""
        ss = andes.load(self.case_path, default_config=True, setup=False)

        # Toggler: 发电机跳闸 (必须 setup 前添加)
        if self._gen_trip is not None:
            ss.add("Toggler", {
                "idx": "Trip_Gen", "model": "GENROU",
                "dev": self._gen_trip, "t": 0.5,
            })

        # 新建 Bus 40-47 + 传输线路
        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            parent_bus = self.PARENT_BUSES[i]

            ss.add("Bus", {
                "idx": new_bus, "name": f"BusVSG{i+1}",
                "Vn": self.VSG_BUS_VN, "v0": 1.0, "a0": 0.0,
            })
            ss.add("Line", {
                "idx": f"Line_VSG_{i+1}",
                "bus1": parent_bus, "bus2": new_bus,
                "Vn1": self.VSG_BUS_VN, "Vn2": self.VSG_BUS_VN,
                "r": self.NEW_LINE_R, "x": self.x_line, "b": self.NEW_LINE_B,
            })

        # 添加 8 台 VSG (GENCLS)
        self.vsg_idx = []
        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            vsg_id = f"VSG_{i+1}"
            gen_id = f"SG_VSG_{i+1}"
            ss.add("PV", {
                "idx": gen_id, "name": f"VSG{i+1}", "bus": new_bus,
                "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                "p0": 0.5, "q0": 0.0,
                "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0,
            })
            ss.add("GENCLS", {
                "idx": vsg_id, "bus": new_bus, "gen": gen_id,
                "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                "M": self.M0[i], "D": self.D0[i],
                "ra": 0.001, "xd1": 0.15,
            })
            self.vsg_idx.append(vsg_id)

        ss.setup()

        # G1-G8: 近零惯量 + 禁用调速器
        for idx in self.GENROU_WIND_IDX:
            if idx in list(ss.GENROU.idx.v):
                ss.GENROU.set("M", idx, self.WIND_FARM_M, attr='v')
                ss.GENROU.set("D", idx, self.WIND_FARM_D, attr='v')
        for idx in self.TGOV_WIND_IDX:
            if idx in list(ss.TGOV1N.idx.v):
                ss.TGOV1N.set("R", idx, self.WIND_FARM_GOV_R, attr='v')

        ss.TDS.config.criteria = 0
        return ss

    def _apply_disturbance(self, delta_u=None, **kwargs):
        """施加 PQ 负荷扰动 (随机 PQ 母线).

        使用 Ppf (常功率模式) 而非 p0, 确保 TDS 期间负荷变化生效.
        """
        if delta_u is not None:
            for pq_idx, dp in delta_u.items():
                all_pq_idx = list(self.ss.PQ.idx.v)
                if pq_idx in all_pq_idx:
                    pq_pos = all_pq_idx.index(pq_idx)
                    self.ss.PQ.Ppf.v[pq_pos] += dp
                    self.ss.TDS.custom_event = True
        elif self.random_disturbance:
            all_pq_idx = list(self.ss.PQ.idx.v)
            pq_idx = self.rng.choice(all_pq_idx)
            pq_pos = all_pq_idx.index(pq_idx)
            magnitude = self.rng.uniform(self.DIST_MIN, self.DIST_MAX)
            sign = self.rng.choice([-1, 1])
            self.ss.PQ.Ppf.v[pq_pos] += sign * magnitude
            self.ss.TDS.custom_event = True
