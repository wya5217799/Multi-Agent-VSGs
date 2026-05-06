"""check_state.py 单测."""
import json
from pathlib import Path
import pytest

from scripts.research_loop.check_state import (
    check_state_dict,
    StateSchemaError,
    SUPPORTED_VERSIONS,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_legal_state_passes():
    state = _load("state_v1_legal.json")
    assert check_state_dict(state) is None


def test_missing_field_raises():
    state = _load("state_missing_field.json")
    with pytest.raises(StateSchemaError, match="budget"):
        check_state_dict(state)


def test_old_version_raises():
    state = _load("state_old_version.json")
    with pytest.raises(StateSchemaError, match="version"):
        check_state_dict(state)


def test_supported_versions_set_contains_v1():
    """常量级 sanity."""
    assert "1.0" in SUPPORTED_VERSIONS


def test_version_with_trailing_space_raises():
    """行为级: 严格匹配, 不容忍空白."""
    state = _load("state_v1_legal.json")
    state["version"] = "1.0 "
    with pytest.raises(StateSchemaError, match="version"):
        check_state_dict(state)


def test_non_dict_input_raises():
    """覆盖 isinstance(state, dict) guard."""
    with pytest.raises(StateSchemaError, match="must be dict"):
        check_state_dict([])  # type: ignore[arg-type]
    with pytest.raises(StateSchemaError, match="must be dict"):
        check_state_dict(None)  # type: ignore[arg-type]


def test_check_state_file_handles_cjk_utf8(tmp_path):
    """check_state_file 用 utf-8 显式打开 (Windows cp1252 默认会乱)."""
    from scripts.research_loop.check_state import check_state_file
    state = _load("state_v1_legal.json")
    state["ai_session_log"] = [{"wake_at_utc": "2026-05-07T00:00:00Z",
                                "context_used_tok": 1000,
                                "wrote": ["看图分析.md"],
                                "session_id": "测试中文"}]
    target = tmp_path / "state.json"
    target.write_text(json.dumps(state, ensure_ascii=False),
                      encoding="utf-8")
    check_state_file(target)  # 不应 raise UnicodeDecodeError
