# FACT: 这是合约本身（搬自 paper_eval.py:1-4，2026-05-03 抽离自 Phase A commit ab1d480）。
# 本模块所有 helper 输出在 PAPER-ANCHOR LOCK 解锁前 INVALID per LOCK，不得作为 paper
# claim 引用。runner_config metadata 让 cross-run 对账成为可能，但**不解锁** paper 数字
# 引用——后者仍由 Signal/Measurement/Causality G1-G6 verdict 把关。
# 详见 paper_eval.py:1-4 + docs/paper/archive/yang2023-fact-base.md §10.

"""Runner-level helpers for paper_eval — pure functions, env-shape-only deps.

Extracted from paper_eval.py 2026-05-03 (after Phase A commit ab1d480) for
the same reason as evaluation/metrics.py: the helpers are Ousterhout-deep
(small interface, substantive resolution logic) but were trapped in a
1000+ line god-script. Splitting them improves locality and lets the
runner-level test suite (tests/test_paper_eval_runner.py) import directly
without pulling the full CLI / env-construction surface.

Contents:

- ``_LOADSTEP_ENV_PREFIXES`` — single source of truth for which
  KUNDUR_DISTURBANCE_TYPE prefixes force LoadStep dispatch
- ``_resolve_disturbance_dispatch`` — A3+ semantics for
  --disturbance-mode CLI vs KUNDUR_DISTURBANCE_TYPE env-var conflict
  (explicit conflict → SystemExit; implicit → stderr WARN + flag)
- ``_build_runner_config`` — snapshot of PHI weights + settle config +
  dispatch resolution into the top-level runner_config JSON block

These are runner-level (depend on env attribute shape `_PHI_*` and on
sys.stderr) — NOT pure metric primitives. They live separate from
evaluation/metrics.py for that reason: metrics.py is reusable across
NE39/Kundur, runner_helpers.py is Kundur-runner-shape-specific.
"""
from __future__ import annotations

import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Loadstep prefix sentinel (single source of truth)
# ---------------------------------------------------------------------------

# Loadstep env-var prefixes that force LoadStep dispatch path inside
# evaluate_policy (paper_eval.py per-episode dispatch branch). Used by
# both the CLI conflict resolver and the per-episode dispatch branch.
_LOADSTEP_ENV_PREFIXES: tuple[str, ...] = ("loadstep_paper_", "loadstep_ptdf_")


# ---------------------------------------------------------------------------
# Dispatch resolver (P0c, 2026-05-03)
# ---------------------------------------------------------------------------


def _resolve_disturbance_dispatch(
    cli_mode: Optional[str],
    env_type: str,
) -> dict:
    """Resolve --disturbance-mode (CLI) vs KUNDUR_DISTURBANCE_TYPE (env-var).

    Three-zone semantics (P0c, 2026-05-03):

    - CLI explicit (non-None) + env startswith loadstep_*  → SystemExit
      (operator must pick one; loadstep dispatch ignores CLI mode silently
      otherwise — refuse to run rather than produce mis-labeled JSON).
    - CLI None (default) + env startswith loadstep_*  → stderr WARN,
      use env-var precedence, record `implicit_conflict_warned=True` in
      the returned dispatch_resolution (so JSON consumer can audit).
    - Otherwise (no env, or non-loadstep env) → resolve cli_mode to its
      default "bus" if None, return clean resolution.

    Returns a dict with keys ``env_type``, ``cli_mode``, ``dispatch_path``
    (one of "loadstep_paper" / "loadstep_ptdf" / "pm_step_proxy"), and
    ``implicit_conflict_warned``. Pure function (no side effects beyond
    stderr in the implicit-conflict branch); raises SystemExit on the
    explicit-conflict branch.
    """
    is_loadstep = env_type.startswith(_LOADSTEP_ENV_PREFIXES)
    if cli_mode is not None and is_loadstep:
        raise SystemExit(
            f"paper_eval: explicit --disturbance-mode={cli_mode!r} conflicts "
            f"with KUNDUR_DISTURBANCE_TYPE={env_type!r} (loadstep dispatch "
            f"ignores CLI mode). Either unset the env-var or omit "
            f"--disturbance-mode."
        )
    implicit_conflict = (cli_mode is None and is_loadstep)
    if implicit_conflict:
        print(
            f"[paper_eval] WARNING: --disturbance-mode unspecified but "
            f"KUNDUR_DISTURBANCE_TYPE={env_type!r} forces loadstep dispatch. "
            f"Using env-var; CLI mode is ignored.",
            file=sys.stderr,
        )
    if env_type.startswith("loadstep_paper_"):
        dispatch_path = "loadstep_paper"
    elif env_type.startswith("loadstep_ptdf_"):
        dispatch_path = "loadstep_ptdf"
    else:
        dispatch_path = "pm_step_proxy"
    return {
        "env_type": env_type,
        "cli_mode": cli_mode,  # None if user did not specify
        "dispatch_path": dispatch_path,
        "implicit_conflict_warned": implicit_conflict,
    }


# ---------------------------------------------------------------------------
# Runner config snapshot builder (P0b, 2026-05-03)
# ---------------------------------------------------------------------------


def _build_runner_config(
    env,
    settle_tol_hz: float,
    settle_window_s: float,
    dispatch_resolution: dict,
) -> dict:
    """Snapshot all runner-level params that affect JSON interpretation.

    Anything that doesn't change RL/env behavior but affects how downstream
    consumers interpret the metric numbers belongs here (P0b, 2026-05-03).
    Reads PHI_* directly from env attributes so that any future env-var
    override applied at env-construction time is captured (single source
    of truth: ``env._PHI_F`` etc., set in kundur_simulink_env.py:148-154).
    """
    cfg: dict = {
        "phi_f": float(getattr(env, "_PHI_F")),
        "phi_h": float(getattr(env, "_PHI_H")),
        "phi_d": float(getattr(env, "_PHI_D")),
        "phi_h_per_agent": getattr(env, "_PHI_H_PER_AGENT", None),
        "phi_d_per_agent": getattr(env, "_PHI_D_PER_AGENT", None),
        "settle_tol_hz": float(settle_tol_hz),
        "settle_window_s": float(settle_window_s),
        "dispatch_resolution": dispatch_resolution,
    }
    # Per-agent overrides: convert numpy / list to plain JSON-friendly form.
    for k in ("phi_h_per_agent", "phi_d_per_agent"):
        v = cfg[k]
        if v is not None:
            try:
                cfg[k] = [float(x) for x in v]
            except TypeError:
                cfg[k] = None  # not iterable / scalar None
    return cfg
