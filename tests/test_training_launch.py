"""Unit tests for engine.training_launch.

Covers:
  - get_training_launch_status: unknown / known scenarios, return shape
  - structured launch field: python_executable is absolute, script + args present
  - recommended_command derives from same fields (not a separate string)
  - _inspect_latest_run: missing dir, empty dir, status.json, ep checkpoints,
    final.pt fallback, corrupt json
  - _find_active_pid: empty entry guard, pattern derivation, subprocess timeout,
    valid PID return
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _fake_ref(scenario_id: str, train_entry: str = "", model_name: str = "") -> dict:
    """Minimal harness reference dict for a known scenario."""
    items = []
    if train_entry:
        items.append({"key": "training_entry", "value": train_entry})
    if model_name:
        items.append({"key": "model_name", "value": model_name})
    return {"scenario_id": scenario_id, "reference_items": items}


# ── get_training_launch_status ─────────────────────────────────────────────────

class TestGetTrainingLaunchStatus:
    def test_unknown_scenario_returns_not_supported(self, monkeypatch):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: (_ for _ in ()).throw(ValueError("unknown")))
        result = tl.get_training_launch_status("bogus")
        assert result["supported"] is False
        assert result["scenario_id"] == "bogus"
        assert "error" in result

    def test_file_not_found_also_returns_not_supported(self, monkeypatch):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: (_ for _ in ()).throw(FileNotFoundError()))
        result = tl.get_training_launch_status("ne39")
        assert result["supported"] is False

    def test_known_scenario_returns_supported_true(self, monkeypatch, tmp_path):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid, "scenarios/kundur/train_simulink.py"))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("kundur")
        assert result["supported"] is True
        assert result["scenario_id"] == "kundur"

    def test_result_contains_all_required_keys(self, monkeypatch, tmp_path):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid, "scenarios/kundur/train_simulink.py",
                                                  "kundur_vsg"))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("kundur")
        for key in ("supported", "scenario_id", "train_entry", "model_name",
                    "model_file_exists", "latest_run_id", "latest_run_status",
                    "latest_run_checkpoint_count", "active_pid", "resume_candidate",
                    "launch", "recommended_command"):
            assert key in result, f"missing key: {key}"

    def test_model_name_from_harness_reference(self, monkeypatch, tmp_path):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid,
                                                  "scenarios/kundur/train_simulink.py",
                                                  "my_model"))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("kundur")
        assert result["model_name"] == "my_model"

    def test_training_launch_uses_scenario_contract_instead_of_duplicate_maps(self):
        import engine.training_launch as tl

        assert not hasattr(tl, "_TRAIN_ENTRIES")
        assert not hasattr(tl, "_MODEL_PATHS")

    def test_fallback_train_entry_from_scenario_contract(self, monkeypatch, tmp_path):
        """When harness ref has no training_entry key, use scenarios.contract."""
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference", lambda sid: _fake_ref(sid))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("kundur")
        assert result["train_entry"] == "scenarios/kundur/train_simulink.py"
        assert result["model_name"] == "kundur_vsg"
        assert result["launch"]["script"] == "scenarios/kundur/train_simulink.py"

    def test_active_pid_surfaced_when_kundur_process_running(self, monkeypatch, tmp_path):
        """active_pid from _find_active_pid is included in the result for kundur."""
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid, "scenarios/kundur/train_simulink.py"))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: 12345)

        result = tl.get_training_launch_status("kundur")
        assert result["active_pid"] == 12345

    def test_active_pid_surfaced_when_ne39_process_running(self, monkeypatch, tmp_path):
        """active_pid from _find_active_pid is included in the result for ne39."""
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid, "scenarios/new_england/train_simulink.py"))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: 99999)

        result = tl.get_training_launch_status("ne39")
        assert result["active_pid"] == 99999


# ── structured launch field ────────────────────────────────────────────────────

class TestLaunchField:
    def _status(self, monkeypatch, tmp_path, scenario="kundur",
                train_entry="scenarios/kundur/train_simulink.py"):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference",
                            lambda sid: _fake_ref(sid, train_entry))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)
        return tl.get_training_launch_status(scenario)

    def test_launch_has_required_keys(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        assert result["launch"] is not None
        for key in ("python_executable", "script", "args"):
            assert key in result["launch"], f"missing launch key: {key}"

    def test_python_executable_is_absolute_path(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        exe = Path(result["launch"]["python_executable"])
        assert exe.is_absolute(), f"python_executable not absolute: {exe}"

    def test_launch_script_matches_train_entry(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        assert result["launch"]["script"] == "scenarios/kundur/train_simulink.py"

    def test_launch_args_is_list(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        assert isinstance(result["launch"]["args"], list)
        assert len(result["launch"]["args"]) > 0

    def test_known_contract_scenario_has_launch_when_ref_lacks_train_entry(
        self, monkeypatch, tmp_path
    ):
        import engine.training_launch as tl
        monkeypatch.setattr(tl, "load_scenario_reference", lambda sid: _fake_ref(sid))
        monkeypatch.setattr(tl, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(tl, "_find_active_pid", lambda _: None)

        result = tl.get_training_launch_status("ne39")
        assert result["launch"] is not None
        assert result["launch"]["script"] == "scenarios/new_england/train_simulink.py"

    def test_recommended_command_contains_python_executable(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        exe = result["launch"]["python_executable"]
        assert exe in result["recommended_command"]

    def test_recommended_command_contains_script(self, monkeypatch, tmp_path):
        result = self._status(monkeypatch, tmp_path)
        assert result["launch"]["script"] in result["recommended_command"]


# ── _inspect_latest_run ────────────────────────────────────────────────────────

class TestInspectLatestRun:
    def _call(self, runs_root):
        from engine.training_launch import _inspect_latest_run
        return _inspect_latest_run(runs_root)

    def test_nonexistent_dir_returns_nones(self, tmp_path):
        run_id, status, count, candidate = self._call(tmp_path / "no_such_dir")
        assert run_id is None
        assert status is None
        assert count == 0
        assert candidate is None

    def test_empty_runs_dir_returns_nones(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        run_id, status, count, candidate = self._call(runs)
        assert run_id is None

    def test_returns_name_of_latest_run_dir(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        (runs / "run_old").mkdir()
        import time; time.sleep(0.01)
        (runs / "run_new").mkdir()
        run_id, *_ = self._call(runs)
        assert run_id == "run_new"

    def test_reads_status_from_json(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        run_dir = runs / "run1"
        run_dir.mkdir()
        (run_dir / "training_status.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8"
        )
        _, status, *_ = self._call(runs)
        assert status == "completed"

    def test_status_none_when_json_missing(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        (runs / "run1").mkdir()
        _, status, *_ = self._call(runs)
        assert status is None

    def test_status_none_on_corrupt_json(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        run_dir = runs / "run1"
        run_dir.mkdir()
        (run_dir / "training_status.json").write_text("NOT_JSON", encoding="utf-8")
        _, status, *_ = self._call(runs)
        assert status is None

    def test_ep_checkpoint_count(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        run_dir = runs / "run1"
        ckpt = run_dir / "checkpoints"
        ckpt.mkdir(parents=True)
        for ep in (10, 20, 30):
            (ckpt / f"ep{ep}.pt").write_text("")
        _, _, count, candidate = self._call(runs)
        assert count == 3
        assert "ep30.pt" in candidate

    def test_no_ep_ckpts_falls_back_to_final_pt(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        run_dir = runs / "run1"
        ckpt = run_dir / "checkpoints"
        ckpt.mkdir(parents=True)
        (ckpt / "final.pt").write_text("")
        _, _, count, candidate = self._call(runs)
        assert count == 0
        assert "final.pt" in candidate

    def test_no_checkpoints_at_all_candidate_is_none(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        (runs / "run1").mkdir()
        _, _, count, candidate = self._call(runs)
        assert count == 0
        assert candidate is None


# ── _find_active_pid ───────────────────────────────────────────────────────────

class TestFindActivePid:
    def _call(self, train_entry):
        from engine.training_launch import _find_active_pid
        return _find_active_pid(train_entry)

    def test_empty_entry_returns_none_without_subprocess(self):
        # Must not call subprocess at all for empty entry.
        with patch("engine.training_launch.subprocess.run") as mock_run:
            result = self._call("")
        assert result is None
        mock_run.assert_not_called()

    def test_valid_pid_returned_as_int(self):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.stdout = "12345\n"
            return m
        with patch("engine.training_launch.subprocess.run", side_effect=fake_run):
            result = self._call("scenarios/kundur/train_simulink.py")
        assert result == 12345

    def test_non_numeric_output_returns_none(self):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.stdout = "not_a_pid"
            return m
        with patch("engine.training_launch.subprocess.run", side_effect=fake_run):
            result = self._call("scenarios/kundur/train_simulink.py")
        assert result is None

    def test_subprocess_exception_returns_none(self):
        with patch("engine.training_launch.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="ps", timeout=10)):
            result = self._call("scenarios/kundur/train_simulink.py")
        assert result is None

    def test_backslash_path_normalized_to_forward_slash(self):
        """Windows paths with backslashes must still produce correct patterns."""
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            m = MagicMock()
            m.stdout = ""
            return m
        with patch("engine.training_launch.subprocess.run", side_effect=fake_run):
            self._call(r"scenarios\kundur\train_simulink.py")
        assert "kundur/train_simulink.py" in " ".join(captured["cmd"])


# ── _resolve_python_exe ────────────────────────────────────────────────────────

class TestResolvePythonExe:
    """Tests for the andes_env interpreter detection logic."""

    def _call(self, monkeypatch, conda_prefix: str | None, existing_paths: list[str]):
        """Invoke _resolve_python_exe with controlled env and filesystem."""
        import engine.training_launch as tl

        if conda_prefix is None:
            monkeypatch.delenv("CONDA_PREFIX", raising=False)
        else:
            monkeypatch.setenv("CONDA_PREFIX", conda_prefix)

        existing = {Path(p) for p in existing_paths}
        monkeypatch.setattr(Path, "exists", lambda self: self in existing)
        return tl._resolve_python_exe()

    def test_conda_prefix_andes_env_returns_prefix_python(self, monkeypatch, tmp_path):
        prefix = str(tmp_path / "envs" / "andes_env")
        python = str(Path(prefix) / "python.exe")
        result = self._call(monkeypatch, prefix, [python])
        assert result == Path(python)

    def test_conda_prefix_wrong_env_skips_to_search(self, monkeypatch, tmp_path):
        """CONDA_PREFIX pointing to a different env must not short-circuit."""
        prefix = str(tmp_path / "envs" / "other_env")
        # Only andes_env path exists in the search list
        import engine.training_launch as tl
        search_andes = str(Path.home() / "miniconda3" / "envs" / "andes_env" / "python.exe")
        result = self._call(monkeypatch, prefix, [search_andes])
        assert result == Path(search_andes)

    def test_no_conda_prefix_searches_miniconda(self, monkeypatch):
        miniconda_python = str(Path.home() / "miniconda3" / "envs" / "andes_env" / "python.exe")
        result = self._call(monkeypatch, None, [miniconda_python])
        assert result == Path(miniconda_python)

    def test_falls_back_to_sys_executable_when_nothing_found(self, monkeypatch):
        import sys
        result = self._call(monkeypatch, None, [])   # no paths exist
        assert result == Path(sys.executable)

    def test_miniconda_searched_before_anaconda(self, monkeypatch):
        """When both miniconda and anaconda andes_env exist, miniconda wins."""
        miniconda = str(Path.home() / "miniconda3" / "envs" / "andes_env" / "python.exe")
        anaconda  = str(Path.home() / "anaconda3"  / "envs" / "andes_env" / "python.exe")
        result = self._call(monkeypatch, None, [miniconda, anaconda])
        assert result == Path(miniconda)
