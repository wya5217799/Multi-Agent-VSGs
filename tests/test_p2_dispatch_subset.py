"""Unit tests for Module α dispatch-subset parsing (no MATLAB required).

Tests target ``_parse_subset_spec`` in ``probes.kundur.probe_state._subset``.
All tests are pure-Python; import of MATLAB-bound modules is avoided.
"""
from __future__ import annotations

import pytest

from probes.kundur.probe_state._subset import _parse_subset_spec


_VALID = ["a", "b", "c", "d"]


def test_parse_subset_int_indices():
    """Integer indices into valid_targets resolve to canonical names."""
    result = _parse_subset_spec("0,2", _VALID)
    assert result == ("a", "c")


def test_parse_subset_names():
    """Named tokens resolve to themselves when present in valid_targets."""
    result = _parse_subset_spec("b,d", _VALID)
    assert result == ("b", "d")


def test_parse_subset_mixed_int_and_name():
    """Mixed int index and name token both resolve correctly."""
    result = _parse_subset_spec("0,b", _VALID)
    assert result == ("a", "b")


def test_parse_subset_index_out_of_range():
    """Index beyond valid_targets length raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        _parse_subset_spec("9", _VALID)
    assert "out of range" in str(exc_info.value)


def test_parse_subset_invalid_name():
    """Unknown name not in valid_targets raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        _parse_subset_spec("zzz", _VALID)
    assert "zzz" in str(exc_info.value)


def test_parse_subset_single_index():
    """Single integer index works."""
    result = _parse_subset_spec("1", _VALID)
    assert result == ("b",)


def test_parse_subset_deduplicates():
    """Duplicate tokens collapse to unique names (order-preserved)."""
    result = _parse_subset_spec("0,a", _VALID)
    assert result == ("a",)


def test_parse_subset_empty_spec_raises():
    """Empty spec string raises SystemExit."""
    with pytest.raises(SystemExit):
        _parse_subset_spec("", _VALID)
