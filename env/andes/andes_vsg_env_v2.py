"""ANDES Kundur 4-VSG env V2 — paper-alignment 改进实验.

V2 vs V1 (`andes_vsg_env.py`):
  - 拓扑: 完全相同 (Kundur full + 4 ESS @ Bus 12/14/15/16 + W2)
  - VSG_M0: 20 → 30 (1.5× V1, H₀=10→15s)
  - VSG_D0 同质 → 异质 [20, 16, 4, 8] (制造 sync 失同步)
      ES1@Bus12→Bus7  : 远 LS1 (D=20 强 damp)
      ES2@Bus16→Bus8  : 远 LS1 (D=16 强 damp)
      ES3@Bus14→Bus10 : 在 LS1 disturbance bus (D=4 弱 damp)
      ES4@Bus15→Bus9  : 在 LS2 disturbance bus (D=8 中等 damp)
  - DM/DD ranges: [-10,30] / [-10,30] → [-12,40] / [-15,45] (适度扩 1.3-1.5×)
  - NEW_LINE_X: 0.10 → 0.20 (拉长 ESS-bus 接入线)
  - 通信拓扑、PHI 权重、reward 公式: 不动

ANDES_V2_D0 / ANDES_V2_LINE_X env vars 可覆盖默认.

V2 sweep verdict (2026-05-06):
  - D₀ sweep: [10,8,2,4]/[20,16,4,8]/[30,24,6,12]/[40,32,8,16] → [20,16,4,8] 是 sync 量级最优 (LS1 cum_rf -1.66 vs paper -1.61)
  - NEW_LINE_X sweep: 0.10/0.20/0.30/0.40/0.60 → 0.20 是 sweet spot, 0.60 power flow 发散

V1 完全保留, V2 是独立子类, V2 训练需新 actor.

⚠ 6-axis 真实评估 (2026-05-07): 即使 V2 hetero env, 6-axis overall 仍 < 0.04.
   sync 偏差量级匹配是单维 cherry-pick, 物理动态 5/6 axis 仍 fail.
   见 docs/paper/andes_replication_status_2026-05-07_6axis.md.
"""
from __future__ import annotations

import os as _os

import numpy as np

from env.andes.andes_vsg_env import AndesMultiVSGEnv


class AndesMultiVSGEnvV2(AndesMultiVSGEnv):
    """V2: D₀ 异质 + 适度 baseline 提高 + 网络距离拉长, V1 完整不动."""

    # ─── Baseline overrides ───
    VSG_M0 = 30.0   # 1.5× V1, H₀=15s
    VSG_D0 = 4.0    # 兜底; 实际用 D0_HETEROGENEOUS

    # 默认 [20, 16, 4, 8] — 2026-05-06 sweep verdict: LS1 cum_rf=-1.66 (paper -1.61, 103%).
    # ANDES_V2_D0="x,y,z,w" 可覆盖.
    _D0_OVERRIDE = _os.environ.get("ANDES_V2_D0", "")
    if _D0_OVERRIDE:
        D0_HETEROGENEOUS = np.array([float(x) for x in _D0_OVERRIDE.split(",")])
    else:
        D0_HETEROGENEOUS = np.array([20.0, 16.0, 4.0, 8.0])

    # ─── Action range (适度扩, 不进 Phase C 不可行区) ───
    DM_MIN = -12.0
    DM_MAX = 40.0
    DD_MIN = -15.0
    DD_MAX = 45.0

    # ─── 网络拉长 (增大 ESS 电气距离, 制造频率失同步) ───
    # ANDES_V2_LINE_X env var 可覆盖默认 0.20.
    _LINE_X_OVERRIDE = _os.environ.get("ANDES_V2_LINE_X", "")
    NEW_LINE_X = float(_LINE_X_OVERRIDE) if _LINE_X_OVERRIDE else 0.20
    NEW_LINE_R = 0.002
    NEW_LINE_B = 0.0175

    def _build_system(self):
        """父类 _build_system + 应用 D₀ 异质."""
        ss = super()._build_system()
        for i, vsg_id in enumerate(self.vsg_idx):
            ss.GENCLS.set("D", vsg_id, self.D0_HETEROGENEOUS[i], attr="v")
        return ss

    def reset(self, *args, **kwargs):
        obs = super().reset(*args, **kwargs)
        # base_env.reset → _init_baselines 走父类时 self.D0 被覆盖为 full(VSG_D0).
        # 这里再覆盖确保 D0 异质.
        self.D0 = self.D0_HETEROGENEOUS.copy()
        return obs

    @classmethod
    def deviation_summary(cls) -> dict:
        return {
            "version": "v2",
            "vsg_m0": cls.VSG_M0,
            "vsg_d0_heterogeneous": cls.D0_HETEROGENEOUS.tolist(),
            "dm_range": [cls.DM_MIN, cls.DM_MAX],
            "dd_range": [cls.DD_MIN, cls.DD_MAX],
            "new_line_x": cls.NEW_LINE_X,
            "v1_baseline": {
                "vsg_m0": 20.0, "vsg_d0_uniform": 4.0,
                "dm_range": [-10.0, 30.0], "dd_range": [-10.0, 30.0],
                "new_line_x": 0.10,
            },
            "rationale": (
                "D₀ 异质 [20,16,4,8] 制造 sync 失同步, NEW_LINE_X 拉长增大电气距离. "
                "Sweep verdict: LS1 no-ctrl cum_rf -1.66 vs paper -1.61 (103%). "
                "但 6-axis 评估 (max_df / final_df / settling / range / smoothness) 仍 fail."
            ),
        }
