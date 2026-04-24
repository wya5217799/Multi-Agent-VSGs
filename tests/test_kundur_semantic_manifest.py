from scenarios.kundur.manifest_contract import validate_kundur_alignment
from scenarios.kundur.model_profile import load_kundur_model_profile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _candidate_profile():
    return load_kundur_model_profile(
        _REPO_ROOT / "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )


def _base_candidate_manifest(**overrides):
    m = {
        "scenario_id": "kundur",
        "model_name": "kundur_vsg_sps",
        "solver": {"family": "sps_phasor", "has_solver_config": False, "powergui_mode": "Phasor"},
        "initialization": {"uses_pref_ramp": False, "warmup_mode": "technical_reset_only"},
        "measurement": {"mode": "vi"},
        "phase_command_mode": "absolute_with_loadflow",
    }
    m.update(overrides)
    return m


def test_candidate_manifest_requires_vi_and_no_solverconfig():
    issues = validate_kundur_alignment(_candidate_profile(), _base_candidate_manifest())
    assert issues == []


def test_candidate_manifest_rejects_pref_ramp():
    m = _base_candidate_manifest()
    m["initialization"] = {"uses_pref_ramp": True, "warmup_mode": "technical_reset_only"}
    issues = validate_kundur_alignment(_candidate_profile(), m)
    assert "pref_ramp" in " ".join(issues)


def test_candidate_manifest_rejects_wrong_powergui_mode():
    m = _base_candidate_manifest()
    m["solver"] = {"family": "sps_phasor", "has_solver_config": False, "powergui_mode": "Continuous"}
    issues = validate_kundur_alignment(_candidate_profile(), m)
    assert any("powergui_mode" in i for i in issues)


def test_candidate_manifest_rejects_wrong_phase_command_mode():
    m = _base_candidate_manifest()
    m["phase_command_mode"] = "passthrough"
    issues = validate_kundur_alignment(_candidate_profile(), m)
    assert any("phase_command_mode" in i for i in issues)


def test_alignment_passes_without_optional_phase_command_mode():
    m = _base_candidate_manifest()
    del m["phase_command_mode"]
    issues = validate_kundur_alignment(_candidate_profile(), m)
    assert issues == []
