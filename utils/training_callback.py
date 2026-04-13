"""Training callback protocol for GridGym training loops.

Defines the minimal ABC that all training callbacks must implement.
Training scripts compose a list of callbacks at startup; the loop
calls each callback at episode end and stops if any returns True.

Reference: SB3's on_step → bool abort pattern.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class EpisodeResult:
    """Standardised episode data passed to every callback."""

    episode: int
    rewards: float
    reward_components: dict[str, float]
    actions: np.ndarray
    info: dict[str, Any]
    per_agent_rewards: dict[int, float] | None = None
    sac_losses: list[dict[str, float]] | None = None


class TrainingCallback(ABC):
    """Minimal callback interface for training loops.

    Each callback receives an EpisodeResult at the end of every episode.
    Return True from ``on_episode_end`` to request a hard stop; the loop
    stops after the first callback that returns True.

    Lifecycle:
        on_training_start() → [on_episode_end() × N] → on_training_end()
    """

    def on_training_start(self) -> None:
        """Called once before the first episode."""

    @abstractmethod
    def on_episode_end(self, result: EpisodeResult) -> bool:
        """Called at the end of each episode.

        Returns:
            True to stop training immediately, False to continue.
        """

    def on_training_end(self, stopped_early: bool) -> None:
        """Called once after the last episode (or after early stop).

        Args:
            stopped_early: True if a callback triggered a hard stop,
                           False if all scheduled episodes completed.
        """


class CallbackList:
    """Runs a list of callbacks in order; stops on the first True return.

    Usage::

        callbacks = CallbackList([monitor_cb, checkpoint_cb])
        callbacks.on_training_start()
        for ep in range(episodes):
            result = EpisodeResult(...)
            if callbacks.on_episode_end(result):
                break
        callbacks.on_training_end(stopped_early=...)
    """

    def __init__(self, callbacks: list[TrainingCallback]) -> None:
        self._callbacks = list(callbacks)

    def on_training_start(self) -> None:
        for cb in self._callbacks:
            cb.on_training_start()

    def on_episode_end(self, result: EpisodeResult) -> bool:
        """Return True if any callback requests a stop."""
        for cb in self._callbacks:
            if cb.on_episode_end(result):
                return True
        return False

    def on_training_end(self, stopped_early: bool) -> None:
        for cb in self._callbacks:
            cb.on_training_end(stopped_early)
