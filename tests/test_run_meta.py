"""Tests for utils/run_meta.py — experiment metadata recording.

TDD RED phase: all tests must fail before implementation exists.
"""
import json
import os
import types
import argparse
import datetime
import pytest


# ── helpers ────────────────────────────────────────────────────────────────

def _make_args(**kwargs) -> argparse.Namespace:
    """Build a minimal argparse Namespace like train_simulink.py produces."""
    defaults = dict(
        checkpoint_dir="results/sim_kundur/checkpoints",
        n_episodes=500,
        eval_interval=50,
        resume=None,
        mode="simulink",
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_config_module(**extras) -> types.ModuleType:
    """Build a fake config module with scalar fields only."""
    mod = types.ModuleType("fake_config")
    mod.N_AGENTS = 4
    mod.BATCH_SIZE = 256
    mod.LR = 3e-4
    mod.GAMMA = 0.99
    mod.BUFFER_SIZE = 100_000
    mod.N_EPISODES = 500
    mod.DIST_MIN = 1.0
    mod.DIST_MAX = 3.0
    mod._private = "should_be_excluded"
    mod.complex_obj = object()           # non-serialisable → should be excluded
    for k, v in extras.items():
        setattr(mod, k, v)
    return mod


# ── import guard ────────────────────────────────────────────────────────────

from utils.run_meta import save_run_meta, update_run_meta  # noqa: E402


# ── save_run_meta ───────────────────────────────────────────────────────────

class TestSaveRunMeta:
    def test_creates_run_meta_json(self, tmp_path):
        """run_meta.json must be created in the given output directory."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        assert (tmp_path / "run_meta.json").exists()

    def test_contains_git_hash(self, tmp_path):
        """git_hash must be a non-empty string."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert isinstance(meta["git_hash"], str)
        assert len(meta["git_hash"]) > 0

    def test_contains_git_dirty_flag(self, tmp_path):
        """git_dirty must be a boolean."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert isinstance(meta["git_dirty"], bool)

    def test_contains_started_at_iso(self, tmp_path):
        """started_at must be a valid ISO-format timestamp."""
        before = datetime.datetime.now()
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        after = datetime.datetime.now()
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        ts = datetime.datetime.fromisoformat(meta["started_at"])  # raises if bad format
        assert before <= ts <= after

    def test_contains_args_dict(self, tmp_path):
        """args must be the CLI namespace serialised as a dict."""
        args = _make_args(n_episodes=999, mode="standalone")
        save_run_meta(str(tmp_path), args, _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert meta["args"]["n_episodes"] == 999
        assert meta["args"]["mode"] == "standalone"

    def test_contains_config_scalars(self, tmp_path):
        """config must include scalar fields from the config module."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert meta["config"]["N_AGENTS"] == 4
        assert meta["config"]["BATCH_SIZE"] == 256
        assert abs(meta["config"]["LR"] - 3e-4) < 1e-10

    def test_excludes_private_config_fields(self, tmp_path):
        """Fields starting with _ must be excluded from config snapshot."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert "_private" not in meta["config"]

    def test_excludes_non_serialisable_config_fields(self, tmp_path):
        """Non-serialisable fields (objects) must be silently excluded."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert "complex_obj" not in meta["config"]

    def test_output_dir_created_if_missing(self, tmp_path):
        """save_run_meta must create output_dir if it does not exist."""
        nested = tmp_path / "deep" / "nested"
        save_run_meta(str(nested), _make_args(), _make_config_module())
        assert (nested / "run_meta.json").exists()

    def test_valid_json_file(self, tmp_path):
        """run_meta.json must be valid JSON."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        content = (tmp_path / "run_meta.json").read_text(encoding="utf-8")
        data = json.loads(content)  # raises if invalid
        assert isinstance(data, dict)

    def test_resume_preserves_original_started_at(self, tmp_path):
        """Second call (resume) must not overwrite started_at from first call."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta1 = json.loads((tmp_path / "run_meta.json").read_text())

        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta2 = json.loads((tmp_path / "run_meta.json").read_text())

        assert meta2["started_at"] == meta1["started_at"]

    def test_resume_adds_resumed_at(self, tmp_path):
        """Second call (resume) must add a resumed_at field."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert "resumed_at" in meta


# ── update_run_meta ─────────────────────────────────────────────────────────

class TestUpdateRunMeta:
    def test_appends_finished_at(self, tmp_path):
        """update_run_meta must add finished_at without losing existing keys."""
        save_run_meta(str(tmp_path), _make_args(), _make_config_module())
        update_run_meta(str(tmp_path), {"finished_at": "2026-04-10T05:00:00", "total_episodes": 500})
        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert meta["finished_at"] == "2026-04-10T05:00:00"
        assert meta["total_episodes"] == 500
        # original fields preserved
        assert "git_hash" in meta
        assert "started_at" in meta

    def test_no_file_raises(self, tmp_path):
        """update_run_meta on a directory without run_meta.json must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            update_run_meta(str(tmp_path), {"finished_at": "2026-04-10T05:00:00"})
