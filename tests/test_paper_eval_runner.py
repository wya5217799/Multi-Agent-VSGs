"""Tests for paper_eval runner-level helpers (P0b/P0c/P3a, 2026-05-03).

Covers:
- ``_resolve_disturbance_dispatch``: A3+ semantics (explicit conflict → SystemExit;
  implicit conflict → stderr warn + flag; clean cases → silent)
- ``_build_runner_config``: shape contract for the runner_config JSON block
- ``_build_arg_parser``: --disturbance-mode default None + --settle-tol-hz flag
- ``result_to_dict``: schema_version=2 emitted + runner_config block included

Pure unit tests; no MATLAB engine, no env construction.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr
from typing import Optional

import pytest

from evaluation.metrics import EvalResult

# Runner-level helpers were extracted from paper_eval.py to
# evaluation/runner_helpers.py 2026-05-03. Tests import them directly.
# paper_eval.py also re-exports for backward-compat (verified separately
# by test_dispatch_helpers_re_exported_from_paper_eval below).
from evaluation.runner_helpers import (
    _LOADSTEP_ENV_PREFIXES,
    _build_runner_config,
    _resolve_disturbance_dispatch,
)
from evaluation.paper_eval import (
    SETTLE_TOL_HZ,
    SETTLE_WINDOW_S,
    _build_arg_parser,
    result_to_dict,
)

pytestmark = pytest.mark.offline


# ---------------------------------------------------------------------------
# Fake env stand-in (we only need PHI / per-agent attrs accessible)
# ---------------------------------------------------------------------------


class _FakeEnv:
    """Minimal env stub exposing the attrs _build_runner_config reads."""

    def __init__(
        self,
        phi_f: float = 100.0,
        phi_h: float = 5e-4,
        phi_d: float = 5e-4,
        phi_h_per_agent: Optional[list[float]] = None,
        phi_d_per_agent: Optional[list[float]] = None,
    ) -> None:
        self._PHI_F = phi_f
        self._PHI_H = phi_h
        self._PHI_D = phi_d
        self._PHI_H_PER_AGENT = phi_h_per_agent
        self._PHI_D_PER_AGENT = phi_d_per_agent


# ---------------------------------------------------------------------------
# _resolve_disturbance_dispatch — A3+ semantics
# ---------------------------------------------------------------------------


def test_dispatch_no_env_no_cli_returns_pm_step_proxy() -> None:
    """Default-default case: no env-var, no CLI → pm_step_proxy, no warning."""
    r = _resolve_disturbance_dispatch(cli_mode=None, env_type="")
    assert r["dispatch_path"] == "pm_step_proxy"
    assert r["cli_mode"] is None
    assert r["env_type"] == ""
    assert r["implicit_conflict_warned"] is False


def test_dispatch_non_loadstep_env_with_cli_resolves_cleanly() -> None:
    """Non-loadstep env (pm_step_*) + explicit CLI → both recorded, no warning."""
    r = _resolve_disturbance_dispatch(
        cli_mode="gen", env_type="pm_step_proxy_random_gen"
    )
    assert r["dispatch_path"] == "pm_step_proxy"
    assert r["cli_mode"] == "gen"
    assert r["env_type"] == "pm_step_proxy_random_gen"
    assert r["implicit_conflict_warned"] is False


def test_dispatch_implicit_conflict_warns_to_stderr_and_uses_loadstep() -> None:
    """CLI default (None) + loadstep_* env → stderr WARN + dispatch=loadstep + flag."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        r = _resolve_disturbance_dispatch(
            cli_mode=None, env_type="loadstep_ptdf_random_load"
        )
    assert r["dispatch_path"] == "loadstep_ptdf"
    assert r["implicit_conflict_warned"] is True
    stderr_text = buf.getvalue()
    assert "WARNING" in stderr_text
    assert "loadstep_ptdf_random_load" in stderr_text


def test_dispatch_implicit_conflict_loadstep_paper_distinguished() -> None:
    """loadstep_paper_* env yields dispatch_path 'loadstep_paper' (not 'loadstep_ptdf')."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        r = _resolve_disturbance_dispatch(
            cli_mode=None, env_type="loadstep_paper_random_bus"
        )
    assert r["dispatch_path"] == "loadstep_paper"
    assert r["implicit_conflict_warned"] is True


def test_dispatch_explicit_conflict_raises_systemexit() -> None:
    """Explicit CLI mode + loadstep_* env → SystemExit (refuse mis-labeled run)."""
    with pytest.raises(SystemExit) as exc_info:
        _resolve_disturbance_dispatch(
            cli_mode="bus", env_type="loadstep_paper_random_bus"
        )
    msg = str(exc_info.value)
    assert "explicit --disturbance-mode" in msg
    assert "'bus'" in msg
    assert "loadstep_paper_random_bus" in msg


def test_dispatch_explicit_conflict_with_other_modes_also_raises() -> None:
    """Sanity: any explicit non-None mode + loadstep env raises (not just bus)."""
    for mode in ("gen", "vsg", "ccs_load", "hybrid"):
        with pytest.raises(SystemExit):
            _resolve_disturbance_dispatch(
                cli_mode=mode, env_type="loadstep_ptdf_random_load"
            )


def test_dispatch_helpers_re_exported_from_paper_eval() -> None:
    """paper_eval.py re-export must resolve to the same objects as direct
    runner_helpers import (backward-compat for any external caller that
    historically imported these from evaluation.paper_eval).
    """
    from evaluation import paper_eval as _pe
    from evaluation import runner_helpers as _rh
    assert _pe._resolve_disturbance_dispatch is _rh._resolve_disturbance_dispatch
    assert _pe._build_runner_config is _rh._build_runner_config
    assert _pe._LOADSTEP_ENV_PREFIXES is _rh._LOADSTEP_ENV_PREFIXES


def test_dispatch_loadstep_prefixes_constant_matches_implementation() -> None:
    """_LOADSTEP_ENV_PREFIXES is the single source of truth for resolver."""
    # Strings starting with these prefixes must trigger loadstep behavior.
    for prefix in _LOADSTEP_ENV_PREFIXES:
        env_t = prefix + "anything"
        r = _resolve_disturbance_dispatch(cli_mode=None, env_type=env_t)
        assert r["dispatch_path"].startswith("loadstep")
        assert r["implicit_conflict_warned"] is True
    # Strings NOT starting with them must NOT trigger.
    for env_t in ("", "pm_step_proxy_random_gen", "ccs_load_b7"):
        r = _resolve_disturbance_dispatch(cli_mode=None, env_type=env_t)
        assert r["dispatch_path"] == "pm_step_proxy"
        assert r["implicit_conflict_warned"] is False


# ---------------------------------------------------------------------------
# _build_runner_config — shape contract
# ---------------------------------------------------------------------------


def test_runner_config_basic_shape() -> None:
    """All required keys present; PHI values from env attributes."""
    env = _FakeEnv(phi_f=100.0, phi_h=5e-4, phi_d=5e-4)
    dr = {"env_type": "", "cli_mode": "gen", "dispatch_path": "pm_step_proxy",
          "implicit_conflict_warned": False}
    cfg = _build_runner_config(env, settle_tol_hz=0.005, settle_window_s=1.0,
                               dispatch_resolution=dr)
    assert cfg["phi_f"] == 100.0
    assert cfg["phi_h"] == 5e-4
    assert cfg["phi_d"] == 5e-4
    assert cfg["phi_h_per_agent"] is None
    assert cfg["phi_d_per_agent"] is None
    assert cfg["settle_tol_hz"] == 0.005
    assert cfg["settle_window_s"] == 1.0
    assert cfg["dispatch_resolution"] is dr


def test_runner_config_per_agent_overrides_serialized() -> None:
    """Per-agent PHI overrides are converted to plain list[float] for JSON."""
    env = _FakeEnv(
        phi_h_per_agent=[5e-4, 5e-4, 2e-3, 5e-4],
        phi_d_per_agent=[1e-3, 1e-3, 1e-3, 1e-3],
    )
    dr = {"env_type": "", "cli_mode": None, "dispatch_path": "pm_step_proxy",
          "implicit_conflict_warned": False}
    cfg = _build_runner_config(env, 0.005, 1.0, dr)
    assert cfg["phi_h_per_agent"] == [5e-4, 5e-4, 2e-3, 5e-4]
    assert cfg["phi_d_per_agent"] == [1e-3, 1e-3, 1e-3, 1e-3]
    assert all(isinstance(x, float) for x in cfg["phi_h_per_agent"])


def test_runner_config_settle_tol_override_captured() -> None:
    """CLI --settle-tol-hz override flows into runner_config (not just default)."""
    env = _FakeEnv()
    dr = {"env_type": "", "cli_mode": "bus", "dispatch_path": "pm_step_proxy",
          "implicit_conflict_warned": False}
    cfg = _build_runner_config(env, settle_tol_hz=0.001, settle_window_s=2.0,
                               dispatch_resolution=dr)
    assert cfg["settle_tol_hz"] == 0.001
    assert cfg["settle_window_s"] == 2.0


# ---------------------------------------------------------------------------
# _build_arg_parser — defaults
# ---------------------------------------------------------------------------


def test_argparse_disturbance_mode_default_is_none() -> None:
    """Default must be None (not 'bus') so explicit-vs-default is distinguishable."""
    p = _build_arg_parser()
    ns = p.parse_args(["--output-json", "/tmp/x.json"])
    assert ns.disturbance_mode is None


def test_argparse_settle_tol_hz_default_matches_module_constant() -> None:
    """--settle-tol-hz default == SETTLE_TOL_HZ (0.005)."""
    p = _build_arg_parser()
    ns = p.parse_args(["--output-json", "/tmp/x.json"])
    assert ns.settle_tol_hz == SETTLE_TOL_HZ
    assert SETTLE_TOL_HZ == 0.005


def test_argparse_settle_tol_hz_override_parsed() -> None:
    """User-supplied --settle-tol-hz is parsed as float."""
    p = _build_arg_parser()
    ns = p.parse_args([
        "--output-json", "/tmp/x.json",
        "--settle-tol-hz", "0.001",
    ])
    assert ns.settle_tol_hz == 0.001


def test_argparse_disturbance_mode_explicit_recorded() -> None:
    """Explicit --disturbance-mode value is recorded (not coerced to default)."""
    p = _build_arg_parser()
    ns = p.parse_args([
        "--output-json", "/tmp/x.json",
        "--disturbance-mode", "gen",
    ])
    assert ns.disturbance_mode == "gen"


# ---------------------------------------------------------------------------
# result_to_dict — schema_version=2 + runner_config block
# ---------------------------------------------------------------------------


def _make_minimal_result(schema_version: int = 2) -> EvalResult:
    return EvalResult(
        schema_version=schema_version,
        checkpoint_path="",
        policy_label="zero_action_no_control",
        n_scenarios=0,
        seed_base=42,
        cumulative_reward_global_rf={"unnormalized": 0.0, "per_M": 0.0,
                                     "per_M_per_N": 0.0,
                                     "paper_target_unnormalized": -8.04,
                                     "paper_no_control_unnormalized": -15.20,
                                     "deltas_vs_paper": {}},
        per_episode_metrics=[],
        summary={"n_scenarios": 0},
    )


def test_result_to_dict_emits_schema_version_2() -> None:
    """Refactored evaluator stamps schema_version=2 (was 1 pre-2026-05-03)."""
    r = _make_minimal_result(schema_version=2)
    d = result_to_dict(r, runner_config={})
    assert d["schema_version"] == 2


def test_result_to_dict_includes_runner_config_block() -> None:
    """runner_config block flows through result_to_dict to output JSON."""
    r = _make_minimal_result()
    cfg = {
        "phi_f": 100.0, "phi_h": 5e-4, "phi_d": 5e-4,
        "phi_h_per_agent": None, "phi_d_per_agent": None,
        "settle_tol_hz": 0.005, "settle_window_s": 1.0,
        "dispatch_resolution": {"env_type": "", "cli_mode": "gen",
                                "dispatch_path": "pm_step_proxy",
                                "implicit_conflict_warned": False},
    }
    d = result_to_dict(r, runner_config=cfg)
    assert d["runner_config"] == cfg
    assert d["runner_config"]["phi_f"] == 100.0
    assert d["runner_config"]["dispatch_resolution"]["dispatch_path"] == "pm_step_proxy"


def test_result_to_dict_runner_config_default_empty_for_backward_compat() -> None:
    """Old caller passing only `result` gets {} runner_config (not error)."""
    r = _make_minimal_result()
    d = result_to_dict(r)  # no runner_config arg
    assert d["runner_config"] == {}


def test_result_to_dict_paper_comparison_lock_unchanged() -> None:
    """PAPER-ANCHOR LOCK still hardcoded False — runner_config doesn't unlock."""
    r = _make_minimal_result()
    d = result_to_dict(r, runner_config={"phi_f": 100.0})
    assert d["paper_comparison_enabled"] is False
    assert "INCONCLUSIVE_STOP_REQUIRED" in d["paper_comparison_lock_reason"]
