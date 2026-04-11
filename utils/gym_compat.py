"""Minimal gymnasium compatibility for optional-dependency workspaces.

The standalone/Simulink environments only require a small subset of the
gymnasium API during unit tests: an ``Env`` base class and ``spaces.Box``
containers for metadata.  When gymnasium is unavailable, provide a tiny local
fallback so import-time contracts and pure-Python tests still run.
"""

from __future__ import annotations

from types import SimpleNamespace

try:
    import gymnasium as gym  # type: ignore
    from gymnasium import spaces  # type: ignore
except ImportError:  # pragma: no cover - exercised in dependency-light envs
    class _Env:
        metadata: dict = {}

        def reset(self, *args, **kwargs):
            raise NotImplementedError

        def step(self, *args, **kwargs):
            raise NotImplementedError

        def close(self) -> None:
            pass

    class _Box:
        def __init__(self, low, high, shape=None, dtype=None):
            self.low = low
            self.high = high
            self.shape = shape
            self.dtype = dtype

        def sample(self):
            raise NotImplementedError("spaces.Box.sample() requires gymnasium")

    gym = SimpleNamespace(Env=_Env)
    spaces = SimpleNamespace(Box=_Box)

__all__ = ["gym", "spaces"]
