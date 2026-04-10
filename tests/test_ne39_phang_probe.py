from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE = PROJECT_ROOT / "vsg_helpers" / "vsg_probe_ne39_phang_sensitivity.m"


def test_ne39_phang_probe_script_has_stable_result_fields():
    text = PROBE.read_text(encoding="utf-8")

    expected_fields = [
        "RESULT: phAng param exists",
        "RESULT: baseline Pe/omega/phAngCmd",
        "RESULT: phAng step +30deg Pe/omega",
        "RESULT: M/D low omega/delta/phAngCmd/Pe",
        "RESULT: M/D base omega/delta/phAngCmd/Pe",
        "RESULT: M/D high omega/delta/phAngCmd/Pe",
        "RESULT: open-loop no-delta Pe drift",
        "RESULT: closed-loop two-step bounded",
        "RESULT: delta range",
        "RESULT: warmup init phAng preserved",
        "RESULT: classification",
    ]
    for field in expected_fields:
        assert field in text


def test_known_mojibake_markers_are_absent_from_touched_sources():
    paths = [
        PROJECT_ROOT / "engine" / "mcp_server.py",
        PROJECT_ROOT / "vsg_helpers" / "vsg_warmup.m",
        PROBE,
    ]
    mojibake_markers = [
        "\u9205\u9225",
        "\ufffd",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for marker in mojibake_markers:
            assert marker not in text
