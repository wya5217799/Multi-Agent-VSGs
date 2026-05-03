"""Module δ — snapshot merge unit tests (no MATLAB, no subprocess)."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from probes.kundur.probe_state._merge import (
    MergeError,
    load_worker_snapshot,
    merge_snapshots,
)


def _mk_snapshot(dispatch_dicts: dict) -> dict:
    return {
        "schema_version": 1,
        "phase4_per_dispatch": {
            "probe_default_magnitude_sys_pu": 0.5,
            "probe_default_sim_duration_s": 3.0,
            "settle_window_s": 2.0,
            "skipped_unrecognised": [],
            "dispatches": dispatch_dicts,
            "metadata_warnings": [],
        },
    }


class TestMergeDisjoint:
    def test_two_workers_disjoint(self):
        parent = {"phase1_topology": {"n_ess": 4}, "errors": [], "schema_version": 1}
        w0 = _mk_snapshot({"a": {"max_abs_f_dev_hz_global": 0.3}})
        w1 = _mk_snapshot({"b": {"max_abs_f_dev_hz_global": 0.4}})
        w0["phase2_nr_ic"] = {"foo": 1}
        w0["phase3_open_loop"] = {"bar": 2}
        meta = [
            {"idx": 0, "exit_code": 0, "wall_s": 100.0, "subset": ["a"]},
            {"idx": 1, "exit_code": 0, "wall_s": 110.0, "subset": ["b"]},
        ]
        result = merge_snapshots(parent, [w0, w1], meta, [["a"], ["b"]])
        dispatches = result["phase4_per_dispatch"]["dispatches"]
        assert "a" in dispatches
        assert "b" in dispatches
        assert dispatches["a"]["worker_id"] == 0
        assert dispatches["b"]["worker_id"] == 1
        assert result["phase4_per_dispatch"]["parallel_metadata"]["n_workers"] == 2
        # Phase 2/3 from worker 0
        assert result["phase2_nr_ic"] == {"foo": 1}
        assert result["phase3_open_loop"] == {"bar": 2}
        # Phase 1 from parent
        assert result["phase1_topology"] == {"n_ess": 4}
        # schema_version unchanged (M5)
        assert result["schema_version"] == 1

    def test_single_worker(self):
        parent = {"errors": [], "schema_version": 1}
        w0 = _mk_snapshot({"h1": {"max_abs_f_dev_hz_global": 0.1}})
        w0["phase2_nr_ic"] = {"ok": True}
        w0["phase3_open_loop"] = {"ok": True}
        meta = [{"idx": 0, "exit_code": 0, "wall_s": 50.0, "subset": ["h1"]}]
        result = merge_snapshots(parent, [w0], meta, [["h1"]])
        assert "h1" in result["phase4_per_dispatch"]["dispatches"]
        assert result["phase4_per_dispatch"]["dispatches"]["h1"]["worker_id"] == 0

    def test_three_workers_disjoint(self):
        parent = {"errors": [], "schema_version": 1}
        w0 = _mk_snapshot({"a": {"x": 1}})
        w1 = _mk_snapshot({"b": {"x": 2}})
        w2 = _mk_snapshot({"c": {"x": 3}})
        w0["phase2_nr_ic"] = {"nr": True}
        w0["phase3_open_loop"] = {"ol": True}
        meta = [
            {"idx": 0, "exit_code": 0, "wall_s": 90.0, "subset": ["a"]},
            {"idx": 1, "exit_code": 0, "wall_s": 95.0, "subset": ["b"]},
            {"idx": 2, "exit_code": 0, "wall_s": 85.0, "subset": ["c"]},
        ]
        result = merge_snapshots(parent, [w0, w1, w2], meta, [["a"], ["b"], ["c"]])
        dispatches = result["phase4_per_dispatch"]["dispatches"]
        assert set(dispatches.keys()) == {"a", "b", "c"}
        assert dispatches["c"]["worker_id"] == 2
        pm = result["phase4_per_dispatch"]["parallel_metadata"]
        assert pm["n_workers"] == 3

    def test_parallel_metadata_structure(self):
        parent = {"errors": [], "schema_version": 1}
        w0 = _mk_snapshot({"a": {"v": 1}})
        meta = [{"idx": 0, "exit_code": 0, "wall_s": 10.0, "subset": ["a"]}]
        result = merge_snapshots(parent, [w0], meta, [["a"]])
        pm = result["phase4_per_dispatch"]["parallel_metadata"]
        assert "n_workers" in pm
        assert "worker_subsets" in pm
        assert "worker_meta" in pm
        assert "dropped_dispatches" in pm
        assert pm["worker_subsets"] == [["a"]]
        assert pm["dropped_dispatches"] == []


class TestMergeOverlap:
    def test_overlap_raises(self):
        parent = {"errors": []}
        w0 = _mk_snapshot({"a": {"x": 1}})
        w1 = _mk_snapshot({"a": {"x": 2}})  # collision!
        meta = [
            {"idx": 0, "exit_code": 0, "wall_s": 1, "subset": ["a"]},
            {"idx": 1, "exit_code": 0, "wall_s": 1, "subset": ["a"]},
        ]
        with pytest.raises(MergeError, match="multiple workers"):
            merge_snapshots(parent, [w0, w1], meta, [["a"], ["a"]])


class TestMergeNonZeroExit:
    def test_nonzero_exit_surfaced(self):
        parent = {"errors": []}
        w0 = _mk_snapshot({"a": {"x": 1}})
        meta = [
            {"idx": 0, "exit_code": 2, "wall_s": 5, "subset": ["a"]},
        ]
        result = merge_snapshots(parent, [w0], meta, [["a"]])
        assert any(
            "p2_workers" in e.get("phase", "")
            for e in result["errors"]
        )

    def test_zero_exit_no_error_for_workers(self):
        parent = {"errors": []}
        w0 = _mk_snapshot({"a": {"x": 1}})
        meta = [{"idx": 0, "exit_code": 0, "wall_s": 5, "subset": ["a"]}]
        result = merge_snapshots(parent, [w0], meta, [["a"]])
        assert not any(
            "p2_workers" in e.get("phase", "")
            for e in result.get("errors", [])
        )


class TestMergeDropped:
    def test_dropped_dispatches_surfaced(self):
        parent = {"errors": []}
        w0 = _mk_snapshot({"a": {"x": 1}})  # only a; expected a + b
        meta = [
            {"idx": 0, "exit_code": 0, "wall_s": 5, "subset": ["a", "b"]},
        ]
        result = merge_snapshots(parent, [w0], meta, [["a", "b"]])
        # b should be in dropped list
        pm = result["phase4_per_dispatch"]["parallel_metadata"]
        assert "b" in pm["dropped_dispatches"]
        assert any(
            "dropped" in e.get("error", "")
            for e in result["errors"]
        )

    def test_no_dropped_when_all_present(self):
        parent = {"errors": []}
        w0 = _mk_snapshot({"a": {"x": 1}, "b": {"x": 2}})
        meta = [{"idx": 0, "exit_code": 0, "wall_s": 5, "subset": ["a", "b"]}]
        result = merge_snapshots(parent, [w0], meta, [["a", "b"]])
        pm = result["phase4_per_dispatch"]["parallel_metadata"]
        assert pm["dropped_dispatches"] == []
        assert not any(
            "dropped" in e.get("error", "")
            for e in result.get("errors", [])
        )


class TestMergeEmptyRaises:
    def test_zero_workers_raises(self):
        with pytest.raises(MergeError, match="zero workers"):
            merge_snapshots({}, [], [], [])

    def test_meta_count_mismatch(self):
        with pytest.raises(MergeError, match="len.*"):
            merge_snapshots({}, [{}], [], [["a"]])


def test_load_worker_snapshot_missing(tmp_path):
    with pytest.raises(MergeError, match="missing"):
        load_worker_snapshot(tmp_path)


def test_load_worker_snapshot_ok(tmp_path):
    p = tmp_path / "state_snapshot_latest.json"
    p.write_text(json.dumps({"schema_version": 1, "test": True}), encoding="utf-8")
    result = load_worker_snapshot(tmp_path)
    assert result == {"schema_version": 1, "test": True}


def test_worker_errors_forwarded():
    """Worker-side errors[] entries are forwarded into the merged snapshot."""
    parent = {"errors": [], "schema_version": 1}
    w0 = _mk_snapshot({"a": {"x": 1}})
    w0["errors"] = [{"phase": "phase3_open_loop", "error": "timeout"}]
    meta = [{"idx": 0, "exit_code": 0, "wall_s": 5.0, "subset": ["a"]}]
    result = merge_snapshots(parent, [w0], meta, [["a"]])
    phases_in_errors = [e.get("phase") for e in result["errors"]]
    assert "phase3_open_loop" in phases_in_errors


def test_skipped_unrecognised_deduplicated():
    """skipped_unrecognised from multiple workers is deduplicated."""
    parent = {"errors": [], "schema_version": 1}
    w0 = _mk_snapshot({"a": {"x": 1}})
    w0["phase4_per_dispatch"]["skipped_unrecognised"] = ["foo", "bar"]
    w1 = _mk_snapshot({"b": {"x": 2}})
    w1["phase4_per_dispatch"]["skipped_unrecognised"] = ["bar", "baz"]
    meta = [
        {"idx": 0, "exit_code": 0, "wall_s": 5.0, "subset": ["a"]},
        {"idx": 1, "exit_code": 0, "wall_s": 5.0, "subset": ["b"]},
    ]
    result = merge_snapshots(parent, [w0, w1], meta, [["a"], ["b"]])
    skipped = result["phase4_per_dispatch"]["skipped_unrecognised"]
    assert sorted(skipped) == ["bar", "baz", "foo"]
    # No duplicates.
    assert len(skipped) == len(set(skipped))


def test_phase4_scalar_defaults_from_first_nonempty_worker():
    """Top-level phase4 scalars come from worker 0's phase4 block."""
    parent = {"errors": [], "schema_version": 1}
    w0 = _mk_snapshot({"a": {"x": 1}})
    w0["phase4_per_dispatch"]["probe_default_magnitude_sys_pu"] = 0.7
    w0["phase4_per_dispatch"]["settle_window_s"] = 1.5
    w1 = _mk_snapshot({"b": {"x": 2}})
    meta = [
        {"idx": 0, "exit_code": 0, "wall_s": 5.0, "subset": ["a"]},
        {"idx": 1, "exit_code": 0, "wall_s": 5.0, "subset": ["b"]},
    ]
    result = merge_snapshots(parent, [w0, w1], meta, [["a"], ["b"]])
    p4 = result["phase4_per_dispatch"]
    assert p4["probe_default_magnitude_sys_pu"] == 0.7
    assert p4["settle_window_s"] == 1.5


def test_diff_handles_merged_snapshot():
    """R_P8: _diff.py must consume merged snapshots transparently.

    diff_snapshots(merged_path, merged_path) must return 0 (no diff).
    """
    from probes.kundur.probe_state._diff import diff_snapshots

    parent = {"phase1_topology": {"n_ess": 4}, "errors": [], "schema_version": 1}
    w0 = _mk_snapshot({"a": {"x": 1}})
    w0["phase2_nr_ic"] = {"foo": 1}
    w0["phase3_open_loop"] = {"bar": 2}
    meta = [{"idx": 0, "exit_code": 0, "wall_s": 1.0, "subset": ["a"]}]
    merged = merge_snapshots(parent, [w0], meta, [["a"]])

    # diff_snapshots takes Path objects; write to temp file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(merged, f)
        tmp_path = f.name

    try:
        from pathlib import Path
        rc = diff_snapshots(Path(tmp_path), Path(tmp_path))
        assert rc == 0, f"merged vs merged should produce zero diff, got {rc}"
    finally:
        os.unlink(tmp_path)
