# FACT: this package's runtime behaviour is the contract; module docstrings
# are CLAIM. See probes/kundur/probe_state/README.md for usage.
"""Kundur model state probe — Phase A.

Captures runtime ground truth for the active Kundur CVS Simulink model:
static topology, NR/IC, open-loop dynamics, per-dispatch signal scan,
and falsification gates G1-G5.
"""
from __future__ import annotations

from probes.kundur.probe_state.probe_state import ModelStateProbe, SCHEMA_VERSION

__all__ = ["ModelStateProbe", "SCHEMA_VERSION"]
