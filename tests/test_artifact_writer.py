"""Tests for ArtifactWriter — JSONL append + atomic latest_state."""
import json
import os
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.artifact_writer import ArtifactWriter


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_metrics_jsonl_created(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {"reward": -1000.0, "alpha": 0.5})
    path = Path(tmp_dir) / "metrics.jsonl"
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["episode"] == 0
    assert record["reward"] == pytest.approx(-1000.0)
    assert record["alpha"] == pytest.approx(0.5)
    assert "ts" in record


def test_metrics_jsonl_appends(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {"reward": -1000.0})
    w.log_metric(1, {"reward": -900.0})
    lines = (Path(tmp_dir) / "metrics.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[1])["episode"] == 1


def test_events_jsonl_created(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_event(5, "alert", {"check": "freq_out_of_range", "message": "test"})
    path = Path(tmp_dir) / "events.jsonl"
    assert path.exists()
    record = json.loads(path.read_text().strip())
    assert record["episode"] == 5
    assert record["type"] == "alert"
    assert record["check"] == "freq_out_of_range"
    assert "ts" in record


def test_update_state_writes_json(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.update_state({"episode": 50, "reward_mean": -5000.0, "alpha": 0.3})
    path = Path(tmp_dir) / "latest_state.json"
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["episode"] == 50
    assert state["reward_mean"] == pytest.approx(-5000.0)
    assert "ts" in state


def test_update_state_overwrites_previous(tmp_dir):
    """Verify each update_state call fully replaces the prior snapshot."""
    w = ArtifactWriter(tmp_dir)
    w.update_state({"episode": 10})
    w.update_state({"episode": 20, "extra": "field"})
    path = Path(tmp_dir) / "latest_state.json"
    state = json.loads(path.read_text())
    assert state["episode"] == 20   # second write replaced first


def test_log_dir_created_if_missing(tmp_dir):
    nested = os.path.join(tmp_dir, "deep", "nested")
    w = ArtifactWriter(nested)
    w.log_metric(0, {"reward": 0.0})
    assert (Path(nested) / "metrics.jsonl").exists()


def test_log_metric_raises_on_reserved_key(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    with pytest.raises(ValueError, match="reserved keys"):
        w.log_metric(0, {"episode": 99, "reward": -100.0})


def test_log_event_raises_on_reserved_key(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    with pytest.raises(ValueError, match="reserved keys"):
        w.log_event(0, "alert", {"type": "bad", "check": "x"})


def test_log_metric_handles_numpy_scalars(tmp_dir):
    """numpy scalars from training must serialize without TypeError."""
    import numpy as np
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {
        "reward": np.float64(-1234.5),
        "alpha": np.float32(0.1),
        "episode_count": np.int64(42),
    })
    path = Path(tmp_dir) / "metrics.jsonl"
    record = json.loads(path.read_text().strip())
    assert record["reward"] == pytest.approx(-1234.5)
    assert record["episode_count"] == 42


def test_reset_existing_clears_previous_run_files(tmp_dir):
    w = ArtifactWriter(tmp_dir)
    w.log_metric(0, {"reward": -1000.0})
    w.log_event(0, "training_start", {"mode": "standalone"})
    w.update_state({"episode": 0})

    ArtifactWriter(tmp_dir, reset_existing=True)

    assert not (Path(tmp_dir) / "metrics.jsonl").exists()
    assert not (Path(tmp_dir) / "events.jsonl").exists()
    assert not (Path(tmp_dir) / "latest_state.json").exists()
