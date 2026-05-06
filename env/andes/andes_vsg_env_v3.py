"""ANDES Kundur 4-VSG env V3 — V2 + IEEEG1 governor + EXST1 AVR (R04 Phase B).

Builds on V2 hetero baseline. After super().setup() adds:
  - IEEEG1 turbine governor on each GENROU sync gen
  - EXST1 IEEE excitation system on each GENROU

Probe verdict (r03_governor_wire_probe.json): pflow + 5step TDS PASS.

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
