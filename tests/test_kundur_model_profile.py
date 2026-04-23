from pathlib import Path

import pytest

from scenarios.kundur.model_profile import (
    load_kundur_model_profile,
    parse_kundur_model_profile,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_legacy_profile_declares_feedback_and_physics_warmup():
    profile = load_kundur_model_profile(
        _REPO_ROOT / "scenarios/kundur/model_profiles/kundur_ee_legacy.json"
    )
    assert profile.solver_family == "simscape_ee"
    assert profile.pe_measurement == "feedback"
    assert profile.warmup_mode == "physics_compensation"


def test_candidate_profile_declares_vi_and_sps():
    profile = load_kundur_model_profile(
        _REPO_ROOT / "scenarios/kundur/model_profiles/kundur_sps_candidate.json"
    )
    assert profile.solver_family == "sps_phasor"
    assert profile.pe_measurement == "vi"
    assert profile.phase_command_mode == "absolute_with_loadflow"


def test_profile_rejects_topology_fields():
    with pytest.raises(ValueError, match="connections"):
        parse_kundur_model_profile(
            {
                "scenario_id": "kundur",
                "profile_id": "bad",
                "connections": [],
            }
        )
