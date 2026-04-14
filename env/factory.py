"""env/factory.py — Unified environment factory.

Creates the correct multi-agent VSG environment for a given scenario + backend,
wrapping legacy envs in GymAdapter so all callers receive the 5-tuple Gymnasium
step signature: (obs, rewards, terminated, truncated, info).

Supported scenario × backend combinations
-----------------------------------------
scenario   backend      class
--------   -------      -----
kundur     andes        AndesMultiVSGEnv
kundur     ode          MultiVSGEnv (Kundur config)
kundur     simulink     KundurSimulinkEnv
ne39       andes        AndesNEEnv
ne39       ode          MultiVSGEnv (NE39 config)
ne39       simulink     NE39SimulinkEnv

Usage::

    env = make_env("kundur", "simulink")
    obs, info = env.reset()
    obs, rew, terminated, truncated, info = env.step(actions)
"""

from __future__ import annotations

from typing import Any

from env.gym_adapter import GymAdapter

# ── lazy imports — keep expensive deps (ANDES, MATLAB) out of module scope ──


def _make_kundur_andes(**kwargs: Any) -> GymAdapter:
    from env.andes.andes_vsg_env import AndesMultiVSGEnv  # type: ignore
    return GymAdapter(AndesMultiVSGEnv(**kwargs))


def _make_kundur_ode(**kwargs: Any) -> GymAdapter:
    from env.ode.multi_vsg_env import MultiVSGEnv  # type: ignore
    import scenarios.kundur.config as cfg
    return GymAdapter(MultiVSGEnv(cfg, **kwargs))


def _make_kundur_simulink(**kwargs: Any) -> Any:
    # KundurSimulinkEnv already returns 5-tuple (Gymnasium spec) — no adapter needed.
    from env.simulink.kundur_simulink_env import KundurSimulinkEnv  # type: ignore
    return KundurSimulinkEnv(**kwargs)


def _make_ne39_andes(**kwargs: Any) -> GymAdapter:
    from env.andes.andes_ne_env import AndesNEEnv  # type: ignore
    return GymAdapter(AndesNEEnv(**kwargs))


def _make_ne39_ode(**kwargs: Any) -> GymAdapter:
    from env.ode.multi_vsg_env import MultiVSGEnv  # type: ignore
    import scenarios.new_england.config as cfg
    return GymAdapter(MultiVSGEnv(cfg, **kwargs))


def _make_ne39_simulink(**kwargs: Any) -> Any:
    # NE39SimulinkEnv already returns 5-tuple — no adapter needed.
    from env.simulink.ne39_simulink_env import NE39SimulinkEnv  # type: ignore
    return NE39SimulinkEnv(**kwargs)


_REGISTRY: dict[tuple[str, str], Any] = {
    ("kundur", "andes"):    _make_kundur_andes,
    ("kundur", "ode"):      _make_kundur_ode,
    ("kundur", "simulink"): _make_kundur_simulink,
    ("ne39",   "andes"):    _make_ne39_andes,
    ("ne39",   "ode"):      _make_ne39_ode,
    ("ne39",   "simulink"): _make_ne39_simulink,
}


def make_env(scenario: str, backend: str, **kwargs: Any) -> Any:
    """Create a VSG environment.

    Parameters
    ----------
    scenario:
        ``"kundur"`` or ``"ne39"``
    backend:
        ``"andes"``, ``"ode"``, or ``"simulink"``
    **kwargs:
        Forwarded to the environment constructor.

    Returns
    -------
    An environment with the 5-tuple Gymnasium step interface:
    ``(obs, rewards, terminated, truncated, info)``

    Raises
    ------
    ValueError
        If the scenario/backend combination is not supported.
    """
    key = (scenario.lower(), backend.lower())
    factory = _REGISTRY.get(key)
    if factory is None:
        supported = ", ".join(f"{s}/{b}" for s, b in sorted(_REGISTRY))
        raise ValueError(
            f"Unknown scenario/backend '{scenario}/{backend}'. "
            f"Supported: {supported}"
        )
    return factory(**kwargs)


__all__ = ["make_env"]
