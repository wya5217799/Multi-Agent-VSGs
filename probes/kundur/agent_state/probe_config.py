"""Agent state probe — config & thresholds.

Bump IMPLEMENTATION_VERSION when verdict logic / thresholds change.
"""
from __future__ import annotations

from dataclasses import dataclass

# Schema = snapshot data shape (additive only; bump on rename/drop)
SCHEMA_VERSION = 1

# Implementation = verdict logic + thresholds (bump on any algo change)
IMPLEMENTATION_VERSION = "0.1.0"

# CHANGELOG (rolling, last 5):
#   0.1.0  initial — A1 (specialization), A2 (ablation), A3 (failure)


@dataclass(frozen=True)
class ProbeThresholds:
    # A1: pairwise cosine similarity matrix off-diagonal mean
    a1_specialized_max_cos: float = 0.60   # if mean off-diag cos < 0.60 → SPECIALIZED
    a1_homogeneous_min_cos: float = 0.90   # if mean off-diag cos > 0.90 → HOMOGENEOUS
    a1_n_obs_samples: int = 200            # synthetic obs sample size

    # A2: agent contribution share (delta cum_rf when ablated, normalized)
    a2_freerider_max_share: float = 0.05   # contribution < 5% of mean → FREERIDER
    a2_n_eval_eps: int = 20                # episodes per ablation run (subset of fixed test set)

    # A3: failure forensics — worst-K episodes
    a3_worst_k: int = 5                    # top-K worst episodes by max_df_max
    a3_n_total_eps: int = 50               # full fixed test set
    a3_max_df_threshold_hz: float = 0.40   # episodes with max_df > 0.40 Hz are flagged
