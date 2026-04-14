"""env/gym_adapter.py — Thin Gymnasium compatibility adapter.

Wraps old-spec envs (returning 4-tuple from step) to the Gymnasium 5-tuple spec:
    (obs, rewards, terminated, truncated, info)

Usage::

    from env.gym_adapter import GymAdapter
    env = GymAdapter(AndesMultiVSGEnv(...))
    obs, info = env.reset()
    obs, rew, terminated, truncated, info = env.step(actions)

Only wraps reset/step; all other attributes are passed through transparently.
"""

from __future__ import annotations

from typing import Any


class GymAdapter:
    """Wraps a 4-tuple (obs, rew, done, info) env to 5-tuple Gymnasium spec.

    - ``terminated`` = ``done`` from the wrapped env (episode reached a natural end)
    - ``truncated`` = False (time-limit truncation is handled inside the wrapped env)
    - ``reset()`` returns ``(obs, {})`` (Gymnasium expects obs + info dict)
    """

    def __init__(self, env: Any) -> None:
        self._env = env

    # ── attribute pass-through ──────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        return getattr(self._env, name)

    # ── Gymnasium-spec API ──────────────────────────────────────────────────

    def reset(self, **kwargs) -> tuple[Any, dict]:
        result = self._env.reset(**kwargs)
        # Guard against wrapped envs that have already been partially upgraded to
        # return (obs, info) from reset().  Unpack if tuple, keep info dict if present.
        if isinstance(result, tuple) and len(result) == 2:
            obs, info = result
            return obs, (info if isinstance(info, dict) else {})
        return result, {}

    def step(self, actions: Any) -> tuple[Any, Any, bool, bool, dict]:
        obs, rewards, done, info = self._env.step(actions)
        return obs, rewards, bool(done), False, info

    def close(self) -> None:
        if hasattr(self._env, "close"):
            self._env.close()

    def __repr__(self) -> str:
        return f"GymAdapter({self._env!r})"
