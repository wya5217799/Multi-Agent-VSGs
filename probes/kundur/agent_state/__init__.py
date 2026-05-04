"""Agent state probe — runtime diagnostic for trained DDIC policies.

Sibling to probes/kundur/probe_state/ (model state). Same design principles:
discovery > declaration, single source of truth, versioned schema, fail-soft
per phase, read-only on production, probe measures don't interpret.

Phases:
- A1 specialization — is multi-agent framework producing diverse policies?
- A2 ablation — per-agent contribution by zero-action substitution
- A3 failure — worst-case forensics on max_df_max excursions

Verdicts: PASS / REJECT / PENDING / ERROR
"""
from probes.kundur.agent_state.probe_config import IMPLEMENTATION_VERSION

__version__ = IMPLEMENTATION_VERSION
