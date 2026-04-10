"""
ANDES 版 New England (IEEE 39-bus) 多智能体 VSG 环境 — REGCA1 风电场版
=====================================================================

与 andes_ne_env.py 的区别:
  - G1-G8 使用 REGCA1+REECA1 (WECC Type-4 电流源风机), 非 GENROU M=0.1
  - 通过修改 xlsx 彻底移除 GENROU G1-G8 及其控制器
  - Toggler 直接作用于 REGCA1 模型

论文对应: Yang et al., IEEE TPWRS 2023, Section IV-G
"""

import os
import shutil
import tempfile

import numpy as np
import andes
import openpyxl
import warnings

from env.andes.base_env import AndesBaseEnv

warnings.filterwarnings("ignore")


class AndesNERegca1Env(AndesBaseEnv):
    """基于 ANDES + REGCA1 风电场的 New England 39-bus VSG 控制环境."""

    N_AGENTS = 8

    # VSG 新母线和连接
    VSG_BUSES = [40, 41, 42, 43, 44, 45, 46, 47]
    PARENT_BUSES = [30, 31, 32, 33, 34, 35, 36, 37]
    VSG_BUS_VN = 22.0

    # REGCA1 风电场 idx
    REGCA1_WIND_IDX = [f"WF_REG_{i}" for i in range(1, 9)]

    # 通信拓扑: 8-node ring
    COMM_ADJ = {
        0: [1, 7], 1: [0, 2], 2: [1, 3], 3: [2, 4],
        4: [3, 5], 5: [4, 6], 6: [5, 7], 7: [6, 0],
    }

    # 类级别共享: 干净 case 文件
    _shared_clean_case_path = None
    _shared_clean_case_dir = None

    def __init__(self, random_disturbance=True, comm_fail_prob=None,
                 comm_delay_steps=0, forced_link_failures=None,
                 x_line=None):
        super().__init__(random_disturbance=random_disturbance,
                         comm_fail_prob=comm_fail_prob,
                         comm_delay_steps=comm_delay_steps,
                         forced_link_failures=forced_link_failures)
        self.x_line = x_line or self.NEW_LINE_X
        self.case_path = andes.get_case("ieee39/ieee39_full.xlsx")

        # 创建干净 case (类级别, 仅首次创建)
        if AndesNERegca1Env._shared_clean_case_path is None:
            AndesNERegca1Env._shared_clean_case_dir = tempfile.mkdtemp(prefix="andes_regca1_")
            AndesNERegca1Env._shared_clean_case_path = self._create_clean_case()
        self._clean_case_path = AndesNERegca1Env._shared_clean_case_path

        self._gen_trip = None

    @classmethod
    def cleanup(cls):
        """清理共享临时文件 (训练结束后调用)."""
        if cls._shared_clean_case_dir is not None:
            shutil.rmtree(cls._shared_clean_case_dir, ignore_errors=True)
            cls._shared_clean_case_path = None
            cls._shared_clean_case_dir = None

    def _create_clean_case(self):
        """创建去除 G1-G8 GENROU 及控制器的 xlsx 文件."""
        tmp_path = os.path.join(self._shared_clean_case_dir, "ieee39_regca1.xlsx")
        shutil.copy2(self.case_path, tmp_path)

        wb = openpyxl.load_workbook(tmp_path)
        remove_uids = set(range(8))  # uid 0..7 = G1..G8

        for sheet_name in ["GENROU", "TGOV1N", "IEEEX1", "IEEEST"]:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows_to_delete = []
            for row in range(2, ws.max_row + 1):
                uid = ws.cell(row=row, column=1).value
                if uid in remove_uids:
                    rows_to_delete.append(row)
            for row in reversed(rows_to_delete):
                ws.delete_rows(row)

        # 删除原始 Toggler (引用已删除的 GENROU)
        if "Toggler" in wb.sheetnames:
            ws = wb["Toggler"]
            header = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
            model_col = header.index("model") + 1 if "model" in header else 5
            rows_to_delete = []
            for row in range(2, ws.max_row + 1):
                if ws.cell(row=row, column=model_col).value == "GENROU":
                    rows_to_delete.append(row)
            for row in reversed(rows_to_delete):
                ws.delete_rows(row)

        wb.save(tmp_path)
        wb.close()
        return tmp_path

    # 扰动范围 (PQ 负荷扰动, 与 AndesNEEnv 一致)
    DIST_MIN = 1.0
    DIST_MAX = 3.0

    def _pre_build(self, gen_trip=None, **kwargs):
        """预处理: 不再使用 Toggler (分段 TDS 不兼容), 改用 PQ 扰动."""
        self._gen_trip = None

    def _build_system(self):
        """加载干净 case, 添加 REGCA1 风电场 + Bus 40-47 + 8 VSG."""
        ss = andes.load(self._clean_case_path, default_config=True, setup=False)

        # 添加 REGCA1+REECA1 风电场
        for i in range(8):
            bus = self.PARENT_BUSES[i]
            existing_pv = i + 1
            wf_reg = f"WF_REG_{i+1}"
            wf_ree = f"WF_REE_{i+1}"

            ss.add("REGCA1", {
                "idx": wf_reg, "bus": bus, "gen": existing_pv, "Sn": 200.0,
                "Tg": 0.1, "Rrpwr": 999, "Brkpt": 0.8, "Zerox": 0.5,
                "Lvplsw": 1, "Lvpl1": 1.0, "Volim": 1.2,
                "Lvpnt1": 1.0, "Lvpnt0": 0.4, "Iolim": -1.5,
                "Tfltr": 0.1, "Khv": 0.0,
                "Iqrmax": 999, "Iqrmin": -999,
                "gammap": 1.0, "gammaq": 1.0, "xs": 0.25,
            })
            ss.add("REECA1", {
                "idx": wf_ree, "reg": wf_reg,
                "PFFLAG": 1, "VFLAG": 0, "QFLAG": 0, "PFLAG": 0, "PQFLAG": 1,
                "Vdip": 0.5, "Vup": 1.5, "Trv": 0.02,
                "dbd1": -0.05, "dbd2": 0.05, "Kqv": 0.0,
                "Iqh1": 999, "Iql1": -999, "Vref0": 0,
                "Tp": 0.02, "Tiq": 0.02,
                "dPmax": 999, "dPmin": -999,
                "PMAX": 999, "PMIN": 0, "Imax": 999, "Tpord": 0.02,
                "Kqp": 0, "Kqi": 0, "Kvp": 0, "Kvi": 0,
                "QMax": 999, "QMin": -999, "VMAX": 999, "VMIN": -999,
            })

        # Toggler: 风电场跳闸 (作用于 REGCA1)
        if self._gen_trip is not None:
            ss.add("Toggler", {
                "idx": "Trip_Gen", "model": "REGCA1",
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
        ss.TDS.config.criteria = 0
        return ss

    def _apply_disturbance(self, delta_u=None, **kwargs):
        """施加 PQ 负荷扰动 (随机 PQ 母线).

        使用 Ppf (常功率模式) 而非 p0, 确保 TDS 期间负荷变化生效.
        与 AndesNEEnv 使用相同的扰动机制, 区别仅在风电场建模方式.
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
