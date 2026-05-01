# FACT: this package's runtime behaviour is the contract; module docstrings
# are CLAIM. See probes/kundur/probe_state/README.md for usage.
"""Kundur model state probe — Evidence Pack Generator.

Captures runtime ground truth for the active Kundur CVS Simulink model:
static topology, NR/IC, open-loop dynamics, per-dispatch signal scan,
trained-policy ablation, causality short-train, and falsification gates
G1-G6 with verdicts in {PASS, REJECT, PENDING, ERROR} + reason_codes.

Out of scope: root-cause inference, paper-alignment judgment, anchor-
unlock recipes. The probe collects facts; consumers interpret them.
"""
from __future__ import annotations

from probes.kundur.probe_state.probe_config import (
    IMPLEMENTATION_VERSION as __version__,
)
from probes.kundur.probe_state.probe_state import ModelStateProbe, SCHEMA_VERSION

__all__ = ["ModelStateProbe", "SCHEMA_VERSION", "__version__"]
