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


def test_runner_config_includes_scenario_provenance_when_provided() -> None:
    """P0a: runner_config carries scenario_provenance dict from caller."""
    env = _FakeEnv()
    dr = {"env_type": "", "cli_mode": None, "dispatch_path": "pm_step_proxy",
          "implicit_conflict_warned": False}
    prov = {"source": "manifest", "manifest_path": "/x.json",
            "manifest_sha256_16": "abc1234567890def", "n_scenarios": 50,
            "scenario_set": "test"}
    cfg = _build_runner_config(env, 0.005, 1.0, dr, scenario_provenance=prov)
    assert cfg["scenario_provenance"] == prov


def test_runner_config_scenario_provenance_default_empty_for_backward_compat() -> None:
    """Caller not passing scenario_provenance gets {} (additive evolution)."""
    env = _FakeEnv()
    dr = {"env_type": "", "cli_mode": None, "dispatch_path": "pm_step_proxy",
          "implicit_conflict_warned": False}
    cfg = _build_runner_config(env, 0.005, 1.0, dr)
    assert cfg["scenario_provenance"] == {}


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


def _make_minimal_result(schema_version: int = 3) -> EvalResult:
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


def test_result_to_dict_emits_schema_version() -> None:
    """Refactored evaluator stamps schema_version (was 1 pre-2026-05-03; bumped to
    2 by ab1d480 for runner_config; bumped to 3 by P3b for rh_abs_share rename)."""
    r = _make_minimal_result(schema_version=3)
    d = result_to_dict(r, runner_config={})
    assert d["schema_version"] == 3


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


def test_summary_rh_abs_share_pct_mean_field_present(tmp_path) -> None:
    """P3b: summary key is now ``rh_abs_share_pct_mean`` (NOT
    ``rh_share_pct_mean``). The field name reflects the |·| absolute-value
    step, which is a project-internal metric, not paper formula. Schema
    version >= 3 implies this rename.

    Smoke-checked via evaluate_policy with stub env in test_evaluate_policy.py;
    here we just confirm the rename via direct inspection of evaluate_policy
    source so consumers reading summary[rh_*_share_*] will fail loudly if
    field name reverts.
    """
    from evaluation import paper_eval as _pe
    src = open(_pe.__file__, encoding="utf-8").read()
    assert '"rh_abs_share_pct_mean":' in src, (
        "P3b rename lost: summary should emit 'rh_abs_share_pct_mean', not "
        "'rh_share_pct_mean'."
    )
    assert '"rh_share_pct_mean":' not in src, (
        "P3b rename incomplete: legacy 'rh_share_pct_mean' still in source."
    )


def test_result_to_dict_paper_comparison_lock_unchanged() -> None:
    """PAPER-ANCHOR LOCK still hardcoded False — runner_config doesn't unlock."""
    r = _make_minimal_result()
    d = result_to_dict(r, runner_config={"phi_f": 100.0})
    assert d["paper_comparison_enabled"] is False
    assert "INCONCLUSIVE_STOP_REQUIRED" in d["paper_comparison_lock_reason"]


# ---------------------------------------------------------------------------
# P0a (scenario provenance) — _compute_scenario_provenance
# ---------------------------------------------------------------------------


def test_scenario_provenance_inline_mode_returns_seed_and_n() -> None:
    """scenario_set='none' → inline mode; provenance has seed_base + n_scenarios."""
    from evaluation.runner_helpers import _compute_scenario_provenance
    prov = _compute_scenario_provenance(
        scenario_set="none", manifest_path=None, n_scenarios=50, seed_base=42,
    )
    assert prov["source"] == "inline_generator"
    assert prov["scenario_set"] == "none"
    assert prov["seed_base"] == 42
    assert prov["n_scenarios"] == 50
    # Manifest fields absent in inline mode.
    assert "manifest_path" not in prov
    assert "manifest_sha256_16" not in prov


def test_scenario_provenance_manifest_mode_returns_sha256(tmp_path) -> None:
    """scenario_set != 'none' + valid manifest → sha256 + path recorded."""
    from evaluation.runner_helpers import _compute_scenario_provenance
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"scenarios": [{"idx": 1}]}', encoding="utf-8")
    prov = _compute_scenario_provenance(
        scenario_set="test", manifest_path=manifest,
        n_scenarios=1, seed_base=42,
    )
    assert prov["source"] == "manifest"
    assert prov["scenario_set"] == "test"
    assert prov["manifest_path"] == str(manifest)
    assert "manifest_sha256_16" in prov
    assert len(prov["manifest_sha256_16"]) == 16
    # Sanity: re-hashing yields same value.
    import hashlib
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]
    assert prov["manifest_sha256_16"] == expected


def test_scenario_provenance_manifest_missing_raises(tmp_path) -> None:
    """Missing manifest path → FileNotFoundError."""
    from evaluation.runner_helpers import _compute_scenario_provenance
    with pytest.raises(FileNotFoundError):
        _compute_scenario_provenance(
            scenario_set="test", manifest_path=tmp_path / "nope.json",
            n_scenarios=1, seed_base=42,
        )


def test_scenario_provenance_manifest_path_none_falls_to_inline() -> None:
    """If scenario_set != 'none' but manifest_path is None → inline (defensive)."""
    from evaluation.runner_helpers import _compute_scenario_provenance
    prov = _compute_scenario_provenance(
        scenario_set="test", manifest_path=None, n_scenarios=10, seed_base=99,
    )
    assert prov["source"] == "inline_generator"


def test_scenario_provenance_sha256_changes_when_content_changes(tmp_path) -> None:
    """Different manifest content → different sha256 (collision check)."""
    from evaluation.runner_helpers import _compute_scenario_provenance
    m1 = tmp_path / "a.json"
    m1.write_text('{"a": 1}', encoding="utf-8")
    m2 = tmp_path / "b.json"
    m2.write_text('{"a": 2}', encoding="utf-8")
    p1 = _compute_scenario_provenance(
        scenario_set="test", manifest_path=m1, n_scenarios=1, seed_base=42,
    )
    p2 = _compute_scenario_provenance(
        scenario_set="test", manifest_path=m2, n_scenarios=1, seed_base=42,
    )
    assert p1["manifest_sha256_16"] != p2["manifest_sha256_16"]


# ---------------------------------------------------------------------------
# P1a (batch) — spec validation
# ---------------------------------------------------------------------------


def test_batch_spec_missing_required_keys_raises(tmp_path) -> None:
    """Batch spec without 'checkpoints' / 'ablations' / 'output_dir' → ValueError."""
    from evaluation.paper_eval import _load_batch_spec
    bad = tmp_path / "bad.json"
    bad.write_text('{"checkpoints": ["a.pt"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required key 'ablations'"):
        _load_batch_spec(bad)


def test_batch_spec_empty_checkpoints_raises(tmp_path) -> None:
    """Empty 'checkpoints' list → ValueError."""
    from evaluation.paper_eval import _load_batch_spec
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"checkpoints": [], "ablations": [{"label":"x","zero_agent_idx":null}], '
        '"output_dir": "/tmp"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty list"):
        _load_batch_spec(bad)


def test_batch_spec_ablation_missing_label_raises(tmp_path) -> None:
    """Ablation entry without 'label' → ValueError."""
    from evaluation.paper_eval import _load_batch_spec
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"checkpoints": ["a.pt"], "ablations": [{"zero_agent_idx":null}], '
        '"output_dir": "/tmp"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty 'label' string"):
        _load_batch_spec(bad)


def test_batch_spec_ablation_zero_agent_idx_must_be_int_or_null(tmp_path) -> None:
    """zero_agent_idx must be int or null (not str)."""
    from evaluation.paper_eval import _load_batch_spec
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"checkpoints": ["a.pt"], '
        '"ablations": [{"label":"x","zero_agent_idx":"1"}], '
        '"output_dir": "/tmp"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be int or null"):
        _load_batch_spec(bad)


def test_batch_spec_minimal_valid_applies_defaults(tmp_path) -> None:
    """Minimal valid spec — optional keys get sensible defaults."""
    from evaluation.paper_eval import _load_batch_spec
    good = tmp_path / "good.json"
    good.write_text(
        '{"checkpoints": ["a.pt", "b.pt"], '
        '"ablations": [{"label":"full","zero_agent_idx":null}, '
        '              {"label":"ab1","zero_agent_idx":0}], '
        '"output_dir": "/tmp/batch1"}',
        encoding="utf-8",
    )
    spec = _load_batch_spec(good)
    assert spec["checkpoints"] == ["a.pt", "b.pt"]
    assert len(spec["ablations"]) == 2
    assert spec["ablations"][1]["zero_agent_idx"] == 0
    # Defaults applied:
    assert spec["scenario_set"] == "none"
    assert spec["scenario_set_path"] is None
    assert spec["disturbance_mode"] is None
    assert spec["settle_tol_hz"] == SETTLE_TOL_HZ
    assert spec["n_scenarios"] == 50
    assert spec["seed_base"] == 42


def test_batch_spec_optional_overrides_preserved(tmp_path) -> None:
    """User-supplied optional keys override defaults."""
    from evaluation.paper_eval import _load_batch_spec
    good = tmp_path / "good.json"
    good.write_text(
        '{"checkpoints": ["a.pt"], '
        '"ablations": [{"label":"x","zero_agent_idx":null}], '
        '"output_dir": "/tmp/x", '
        '"scenario_set": "test", "settle_tol_hz": 0.001, '
        '"n_scenarios": 10, "seed_base": 7, "disturbance_mode": "gen"}',
        encoding="utf-8",
    )
    spec = _load_batch_spec(good)
    assert spec["scenario_set"] == "test"
    assert spec["settle_tol_hz"] == 0.001
    assert spec["n_scenarios"] == 10
    assert spec["seed_base"] == 7
    assert spec["disturbance_mode"] == "gen"


def test_batch_spec_path_does_not_exist_raises(tmp_path) -> None:
    """Missing spec file → FileNotFoundError."""
    from evaluation.paper_eval import _load_batch_spec
    with pytest.raises(FileNotFoundError):
        _load_batch_spec(tmp_path / "no_such_file.json")


def test_batch_spec_not_object_raises(tmp_path) -> None:
    """Spec must be JSON object, not list/scalar."""
    from evaluation.paper_eval import _load_batch_spec
    bad = tmp_path / "bad.json"
    bad.write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        _load_batch_spec(bad)


# ---------------------------------------------------------------------------
# P1a (CLI) — mutual exclusion + output-json optionality in batch mode
# ---------------------------------------------------------------------------


def test_argparse_checkpoint_and_batch_spec_mutually_exclusive() -> None:
    """argparse rejects both --checkpoint and --batch-spec."""
    p = _build_arg_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--checkpoint", "a.pt", "--batch-spec", "b.json"])


def test_argparse_batch_mode_does_not_require_output_json() -> None:
    """In batch mode, --output-json is optional (per-cell paths from spec)."""
    p = _build_arg_parser()
    ns = p.parse_args(["--batch-spec", "b.json"])
    assert ns.batch_spec == "b.json"
    assert ns.output_json is None
    assert ns.checkpoint is None


def test_argparse_single_mode_output_json_optional_at_parse_time() -> None:
    """argparse no longer marks --output-json as required (main() enforces)."""
    p = _build_arg_parser()
    # Parses without --output-json; main() will return 2 with stderr error.
    ns = p.parse_args(["--checkpoint", "a.pt"])
    assert ns.checkpoint == "a.pt"
    assert ns.output_json is None  # main() will reject this combo


# ---------------------------------------------------------------------------
# P1a — _resolve_bus_choices pure dispatch
# ---------------------------------------------------------------------------


def test_resolve_bus_choices_all_modes() -> None:
    """Each mode maps to its documented bus_choices tuple."""
    from evaluation.paper_eval import _resolve_bus_choices
    assert _resolve_bus_choices("bus") == (7, 9)
    assert _resolve_bus_choices("gen") == (1, 2, 3)
    assert _resolve_bus_choices("vsg") == (1, 2, 3, 4)
    assert _resolve_bus_choices("hybrid") == (0,)
    assert _resolve_bus_choices("ccs_load") == (7, 9)


def test_resolve_bus_choices_unknown_falls_back_to_bus() -> None:
    """Unknown mode → defensive (7, 9) fallback (matches original behavior)."""
    from evaluation.paper_eval import _resolve_bus_choices
    assert _resolve_bus_choices("nonexistent_mode") == (7, 9)


# ---------------------------------------------------------------------------
# P1a — _wrap_with_zero_agent_ablation
# ---------------------------------------------------------------------------


def test_wrap_with_zero_agent_ablation_zeros_target_row() -> None:
    """Wrapping forces row[zero_agent_idx] = 0 in returned action."""
    import numpy as np
    from evaluation.paper_eval import _wrap_with_zero_agent_ablation
    base_action = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
    base_select = lambda obs: base_action  # noqa: E731 — trivial test stub
    wrapped = _wrap_with_zero_agent_ablation(base_select, zero_agent_idx=2)
    out = wrapped(obs=None)
    assert out.shape == (4, 2)
    # Row 2 zeroed; other rows untouched.
    assert (out[2] == 0.0).all()
    assert (out[0] == [1.0, 2.0]).all()
    assert (out[1] == [3.0, 4.0]).all()
    assert (out[3] == [7.0, 8.0]).all()
    # Source array NOT mutated (we copy).
    assert (base_action[2] == [5.0, 6.0]).all()


# ---------------------------------------------------------------------------
# P1a — run_batch with stub env (no MATLAB) — verifies orchestration shape
# ---------------------------------------------------------------------------


class _StubBatchEnv:
    """Minimal env stub: just enough for run_single_eval to fail predictably
    on missing checkpoints, exercising the per-cell fail-continue path.
    """
    def __init__(self) -> None:
        self.N_ESS = 4
        self._F_NOM = 50.0
        self.DT = 0.04
        self.T_EPISODE = 2.0
        self._PHI_F = 100.0
        self._PHI_H = 5e-4
        self._PHI_D = 5e-4
        self._PHI_H_PER_AGENT = None
        self._PHI_D_PER_AGENT = None


def test_run_batch_all_missing_ckpts_records_failures(tmp_path, monkeypatch) -> None:
    """All ckpts missing → run_batch returns n_fail=n_cells, no JSONs written.

    Verifies the fail-continue contract: a missing-ckpt cell does not abort
    the batch; subsequent cells still get attempted; summary is written.
    """
    from evaluation.paper_eval import run_batch
    # Avoid requiring KUNDUR_DISTURBANCE_TYPE side-effects:
    monkeypatch.setenv("KUNDUR_DISTURBANCE_TYPE", "pm_step_proxy_random_gen")

    spec = {
        "checkpoints": [str(tmp_path / "missing_a.pt"),
                        str(tmp_path / "missing_b.pt")],
        "ablations": [
            {"label": "full", "zero_agent_idx": None},
            {"label": "ab1", "zero_agent_idx": 0},
        ],
        "output_dir": str(tmp_path / "out"),
        "scenario_set": "none",
        "scenario_set_path": None,
        "disturbance_mode": None,
        "settle_tol_hz": 0.005,
        "n_scenarios": 1,
        "seed_base": 42,
    }
    env = _StubBatchEnv()
    summary = run_batch(env=env, batch_spec=spec)
    assert summary["n_cells"] == 4  # 2 ckpt × 2 ablation
    assert summary["n_fail"] == 4
    assert summary["n_pass"] == 0
    assert all(r["status"] == "FAIL" for r in summary["results"])
    assert all("FileNotFoundError" in r["error"] for r in summary["results"])
    # Summary JSON written even when all fail.
    assert (tmp_path / "out" / "_batch_summary.json").exists()


def test_run_batch_summary_records_per_cell_paths_and_labels(tmp_path, monkeypatch) -> None:
    """Summary records ckpt+ablation+status+output_path for each cell."""
    from evaluation.paper_eval import run_batch
    monkeypatch.setenv("KUNDUR_DISTURBANCE_TYPE", "pm_step_proxy_random_gen")
    spec = {
        "checkpoints": [str(tmp_path / "a.pt"), str(tmp_path / "b.pt")],
        "ablations": [{"label": "full", "zero_agent_idx": None}],
        "output_dir": str(tmp_path / "out"),
        "scenario_set": "none",
        "scenario_set_path": None,
        "disturbance_mode": None,
        "settle_tol_hz": 0.005,
        "n_scenarios": 1,
        "seed_base": 42,
    }
    env = _StubBatchEnv()
    summary = run_batch(env=env, batch_spec=spec)
    assert len(summary["results"]) == 2
    # Cell 0: ckpt a, ablation full
    assert summary["results"][0]["ckpt"].endswith("a.pt")
    assert summary["results"][0]["ablation"] == "full"
    # Cell 1: ckpt b, ablation full
    assert summary["results"][1]["ckpt"].endswith("b.pt")
    # output_path is None on FAIL (no JSON written for failed cell).
    for r in summary["results"]:
        assert r["status"] == "FAIL"
        assert r["output_path"] is None
    # total_time_s present and non-negative.
    assert summary["total_time_s"] >= 0.0
