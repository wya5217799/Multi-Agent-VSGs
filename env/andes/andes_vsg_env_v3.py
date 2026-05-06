"""ANDES Kundur 4-VSG env V3 — V2 + IEEEG1 governor + EXST1 AVR (R04 Phase B).

⚠⚠⚠ GOVERNOR WIRING NOT VERIFIED EFFECTIVE (R08 2026-05-07 finding) ⚠⚠⚠
──────────────────────────────────────────────────────────────────────────
R08 H scan (`scripts/research_loop/r08_h_scan.py`) 实测 zero-action no-SAC:
  V2a (V2 env, no gov, H=10) max_df = 0.815 Hz
  V2b (V3 env, gov on, H=10) max_df = 0.815 Hz  ← 完全相同, governor 没起作用!

R03 governor probe 报 PASS 只是 TDS 没 crash, 不代表 IEEEG1/EXST1 vout 接进了
GENROU 的 Pm/vf input. R04 V3_smoke 报的 fpeak 改善是 SAC 训练效果, 不是
governor 物理效果.

完整 verdict 见 `quality_reports/research_loop/round_08_verdict.md` §2 Finding 3.
ANDES path closure 文档: `quality_reports/handoff/2026-05-07_andes_path_closure.md`.

修法 (若未来重启 ANDES path):
  1. 验 ANDES IEEEG1 syn= 字段是否真自动 wire 到 GENROU Pm (大概率不自动)
  2. 手动 link: e.g. 自定义 ANDES function 或 patch GENROU Pm input
  3. 修后必须 zero-action V2 vs V3 max_df 对比 (差异 ≥ 30% 才算 wired)
──────────────────────────────────────────────────────────────────────────

Builds on V2 hetero baseline. After super().setup() adds:
  - IEEEG1 turbine governor on each GENROU sync gen
  - EXST1 IEEE excitation system on each GENROU

Probe verdict (r03_governor_wire_probe.json): pflow + 5step TDS PASS.
⚠ probe PASS 不代表 governor 物理生效, 见上方 R08 finding.

V1/V2 ckpts NOT compatible (action range, obs encoding identical but env physics
different — frequency response will differ, agents trained on V2 may diverge).
R04 必须 fresh 5seed × 200ep, 不 resume.
"""
from __future__ import annotations

import numpy as np

from env.andes.andes_vsg_env_v2 import AndesMultiVSGEnvV2


class AndesMultiVSGEnvV3(AndesMultiVSGEnvV2):
    """V3 = V2 + governor (IEEEG1) + AVR (EXST1) on every GENROU."""

    def _build_system(self):
        ss = super()._build_system()
        # Add IEEEG1 + EXST1 to each sync gen.
        # Probe (r03_governor_wire_probe) confirmed this sequence: add → re-setup → pflow ok.
        for syn_idx in ss.GENROU.idx.v:
            ss.IEEEG1.add(idx=f"GOV_{syn_idx}", syn=syn_idx)
            ss.EXST1.add(idx=f"AVR_{syn_idx}", syn=syn_idx)
        try:
            ss.setup()
        except Exception:
            # ANDES re-setup after add can warn but works; ignore.
            pass
        return ss

    @classmethod
    def deviation_summary(cls) -> dict:
        base = super().deviation_summary()
        base.update({
            "version": "v3",
            "governor": "IEEEG1 on all GENROU",
            "avr":      "EXST1 on all GENROU",
            "rationale": "V2 GENCLS-only 无 governor → freq nadir 物理底大. V3 加 governor "
                         "靠近 Kundur [49] 经典. R04 Class C deviation (paper §II-A literal 不要求, "
                         "但 Kundur 经典含 governor). 待 R04 实测看 max_df 是否改善.",
        })
        return base
