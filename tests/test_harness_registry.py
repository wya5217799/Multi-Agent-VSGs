from pathlib import Path


def test_resolve_scenario_returns_supported_specs():
    from engine.harness_registry import resolve_scenario

    kundur = resolve_scenario("kundur")
    ne39 = resolve_scenario("ne39")

    assert kundur.scenario_id == "kundur"
    assert kundur.model_name == "kundur_vsg"
    assert kundur.model_dir == Path("scenarios/kundur/simulink_models")
    assert kundur.train_entry == Path("scenarios/kundur/train_simulink.py")

    assert ne39.scenario_id == "ne39"
    assert ne39.model_name == "NE39bus_v2"
    assert ne39.model_dir == Path("scenarios/new_england/simulink_models")
    assert ne39.train_entry == Path("scenarios/new_england/train_simulink.py")


def test_resolve_scenario_rejects_unknown_id():
    from engine.harness_registry import resolve_scenario

    try:
        resolve_scenario("andes")
    except ValueError as exc:
        assert "kundur" in str(exc)
        assert "ne39" in str(exc)
    else:
        raise AssertionError("resolve_scenario should reject unsupported scenarios")


def test_resolve_scenario_guides_ne39_v2_alias_to_ne39():
    from engine.harness_registry import resolve_scenario

    try:
        resolve_scenario("ne39_v2")
    except ValueError as exc:
        message = str(exc)
        assert "scenario_id='ne39'" in message
        assert "model_name='NE39bus_v2'" in message
    else:
        raise AssertionError("resolve_scenario should reject model-name aliases")
