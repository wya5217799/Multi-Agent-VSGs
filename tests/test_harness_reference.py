def test_load_scenario_reference_reads_manifest_for_supported_scenario():
    from engine.harness_reference import load_scenario_reference

    kundur = load_scenario_reference("kundur")
    ne39 = load_scenario_reference("ne39")

    assert kundur["scenario_id"] == "kundur"
    assert ne39["scenario_id"] == "ne39"
    assert any(item["key"] == "n_agents" for item in kundur["reference_items"])
    assert any(item["key"] == "comm_adj" for item in ne39["reference_items"])


def test_validate_reference_items_reports_match_mismatch_and_missing():
    from engine.harness_reference import validate_reference_items

    validation = validate_reference_items(
        reference_items=[
            {"key": "model_name", "value": "kundur_vsg", "check_mode": "must_match"},
            {"key": "dt", "value": 0.2, "check_mode": "must_match"},
            {"key": "act_dim", "value": 2, "check_mode": "warn_if_missing"},
            {"key": "paper_note", "value": "ring", "check_mode": "informational"},
        ],
        actual_values={
            "model_name": "kundur_vsg",
            "dt": 0.1,
        },
    )

    statuses = {item["key"]: item["status"] for item in validation["checks"]}

    assert statuses["model_name"] == "match"
    assert statuses["dt"] == "mismatch"
    assert statuses["act_dim"] == "missing"
    assert statuses["paper_note"] == "informational"
    assert validation["has_warnings"] is True
