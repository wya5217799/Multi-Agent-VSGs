"""Shared training log I/O for all Simulink training scripts."""

import json
import os
from typing import Any


EMPTY_LOG: dict[str, list[Any]] = {
    "episode_rewards": [],
    "eval_rewards": [],
    "critic_losses": [],
    "policy_losses": [],
    "alphas": [],
    "physics_summary": [],
}


def load_or_create_log(path: str, fresh: bool = False) -> dict[str, list[Any]]:
    """Load an existing training log or return a fresh empty one.

    On resume this lets new episodes extend the existing lists instead of
    overwriting them.  Handles truncated JSON (e.g. interrupted mid-write)
    by falling back to a fresh log with a warning.
    """
    if not fresh and os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
            return {k: existing.get(k, list(v)) for k, v in EMPTY_LOG.items()}
        except json.JSONDecodeError:
            print(f"[train] WARNING: {path} is not valid JSON (truncated?). Starting fresh log.")
    return {k: list(v) for k, v in EMPTY_LOG.items()}
