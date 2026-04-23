from scenarios.kundur.manifest_contract import validate_kundur_alignment
from scenarios.kundur.model_profile import load_kundur_model_profile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_candidate_manifest_requires_vi_and_no_solverconfig():
    profile = load_kundur_model_profile(
        _REPO_ROOT / "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )
    manifest = {
        "scenario_id": "kundur",
        "model_name": "kundur_vsg_sps",
        "solver": {"family": "sps_phasor", "has_solver_config": False},
        "initialization": {"uses_pref_ramp": False, "warmup_mode": "technical_reset_only"},
        "measurement": {"mode": "vi"},
    }
    issues = validate_kundur_alignment(profile, manifest)
    assert issues == []


def test_candidate_manifest_rejects_pref_ramp():
    profile = load_kundur_model_profile(
        _REPO_ROOT / "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )
    manifest = {
        "scenario_id": "kundur",
        "model_name": "kundur_vsg_sps",
        "solver": {"family": "sps_phasor", "has_solver_config": False},
        "initialization": {"uses_pref_ramp": True, "warmup_mode": "technical_reset_only"},
        "measurement": {"mode": "vi"},
    }
    issues = validate_kundur_alignment(profile, manifest)
    assert "pref_ramp" in " ".join(issues)
