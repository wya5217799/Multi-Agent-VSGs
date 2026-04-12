import json
from pathlib import Path


def _write_green_modeling_records(harness_reports, scenario_id: str, run_id: str) -> Path:
    run_dir = harness_reports.ensure_run_dir(scenario_id, run_id)
    harness_reports.write_task_record(
        run_dir,
        "scenario_status",
        {
            "task": "scenario_status",
            "scenario_id": scenario_id,
            "run_id": run_id,
            "status": "ok",
        },
    )
    harness_reports.write_task_record(
        run_dir,
        "model_report",
        {
            "task": "model_report",
            "scenario_id": scenario_id,
            "run_id": run_id,
            "status": "ok",
            "run_status": "ok",
        },
    )
    return run_dir


def test_scenario_status_resolves_registry_and_writes_manifest(tmp_path, monkeypatch):
    from engine import harness_reports, harness_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")

    result = harness_tasks.harness_scenario_status(
        scenario_id="kundur",
        run_id="run-001",
        goal="inspect active model",
        requested_tasks=["scenario_status", "model_report"],
    )

    manifest_path = tmp_path / "results" / "harness" / "kundur" / "run-001" / "manifest.json"
    assert result["status"] == "ok"
    assert result["resolved_model_name"] == "kundur_vsg"
    assert result["reference_manifest_path"].endswith("scenarios/kundur/harness_reference.json")
    assert "n_agents" in result["reference_summary"]["must_match_keys"]
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["requested_tasks"] == ["scenario_status", "model_report"]


def test_model_inspect_queries_underlying_tools(tmp_path, monkeypatch):
    from engine import harness_reports, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_load_model",
        lambda model_name: {"ok": True, "loaded_models": [model_name]},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_loaded_models",
        lambda: ["kundur_vsg"],
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_get_block_tree",
        lambda model_name, root_path=None, max_depth=3: {
            "path": root_path or model_name,
            "children": [],
        },
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_query_params",
        lambda model_name, block_paths, param_names=None: {"items": [{"block_path": block_paths[0], "params": {}}]},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_solver_audit",
        lambda model_name: {"ok": True, "solver_type": "Fixed-step"},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_check_params",
        lambda model_name, depth=5: {"passed": True, "suspects": []},
    )

    result = modeling_tasks.harness_model_inspect(
        scenario_id="kundur",
        run_id="run-001",
        focus_paths=["kundur_vsg/VSG_ES1"],
        query_params=["StopTime"],
    )

    assert result["status"] == "ok"
    assert result["model_loaded"] is True
    assert result["loaded_models"] == ["kundur_vsg"]
    assert result["reference_validation"]["has_warnings"] is False
    assert any(item["key"] == "n_agents" for item in result["reference_validation"]["checks"])
    assert result["recommended_next_task"] == "model_patch_verify"


def test_model_inspect_downgrades_to_warning_on_reference_mismatch(tmp_path, monkeypatch):
    from engine import harness_reports, modeling_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_load_model",
        lambda model_name: {"ok": True, "loaded_models": [model_name]},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_loaded_models",
        lambda: ["kundur_vsg"],
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_get_block_tree",
        lambda model_name, root_path=None, max_depth=3: {"path": root_path or model_name, "children": []},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_query_params",
        lambda model_name, block_paths, param_names=None: {"items": []},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_solver_audit",
        lambda model_name: {"ok": True, "solver_type": "Fixed-step"},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "simulink_check_params",
        lambda model_name, depth=5: {"passed": True, "suspects": []},
    )
    monkeypatch.setattr(
        modeling_tasks,
        "build_reference_context",
        lambda scenario_id, spec, load_result=None: {"n_agents": 99, "model_name": "kundur_vsg"},
    )

    result = modeling_tasks.harness_model_inspect(
        scenario_id="kundur",
        run_id="run-002",
    )

    assert result["status"] == "warning"
    assert result["reference_validation"]["has_warnings"] is True
    assert "n_agents" in result["reference_validation"]["mismatch_keys"]


def test_model_report_summarizes_prior_task_records(tmp_path, monkeypatch):
    from engine import harness_reports, harness_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = _write_green_modeling_records(harness_reports, "kundur", "run-001")

    result = harness_tasks.harness_model_report(
        scenario_id="kundur",
        run_id="run-001",
        include_summary_md=True,
    )

    assert result["status"] == "ok"
    assert result["run_status"] == "ok"
    assert "scenario_status" in result["completed_tasks"]
    assert result["memory_hints"] == {
        "should_write_devlog": False,
        "should_write_decision": False,
        "reason": [],
    }
    assert (run_dir / "summary.md").exists()


def test_model_report_adds_memory_hints_for_new_root_cause(tmp_path, monkeypatch):
    from engine import harness_reports, harness_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    run_dir = _write_green_modeling_records(harness_reports, "kundur", "run-003")
    harness_reports.write_task_record(
        run_dir,
        "model_diagnose",
        {
            "task": "model_diagnose",
            "scenario_id": "kundur",
            "run_id": "run-003",
            "status": "failed",
            "suspected_root_causes": ["breaker timing mismatch"],
            "failures": [
                {
                    "failure_class": "model_error",
                    "message": "Diagnostics found compile or simulation issues",
                }
            ],
        },
    )

    result = harness_tasks.harness_model_report(
        scenario_id="kundur",
        run_id="run-003",
        include_summary_md=True,
    )

    assert result["memory_hints"]["should_write_devlog"] is True
    assert result["memory_hints"]["should_write_decision"] is False
    assert "new_root_cause_identified" in result["memory_hints"]["reason"]
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "Memory follow-up:" in summary
    assert "- Add a devlog entry for this run." in summary


def test_train_smoke_is_deprecated_and_fails_fast(tmp_path, monkeypatch):
    """harness_train_smoke (sync) must fail immediately with contract_error.

    The synchronous version blocks the MCP server for the full training
    duration and will time out.  It should never reach subprocess.run.
    """
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    harness_reports.ensure_run_dir("kundur", "run-001")

    called = False

    def _never_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess should not run for deprecated sync train_smoke")

    monkeypatch.setattr(smoke_tasks.subprocess, "run", _never_run)

    result = smoke_tasks.harness_train_smoke(
        scenario_id="kundur",
        run_id="run-001",
        episodes=1,
        mode="simulink",
    )

    assert result["status"] == "failed"
    assert result["smoke_passed"] is False
    assert result["failures"][0]["failure_class"] == "contract_error"
    assert "harness_train_smoke_start" in result["failures"][0]["message"]
    assert called is False


def test_train_smoke_is_deprecated_even_with_green_preconditions(tmp_path, monkeypatch):
    """sync harness_train_smoke must fail with contract_error even when preconditions are green."""
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(smoke_tasks, "_PROJECT_ROOT", tmp_path)
    run_dir = _write_green_modeling_records(harness_reports, "kundur", "run-002")

    called = False

    def _never_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess should not run for deprecated sync train_smoke")

    monkeypatch.setattr(smoke_tasks.subprocess, "run", _never_run)

    result = smoke_tasks.harness_train_smoke(
        scenario_id="kundur",
        run_id="run-002",
        episodes=1,
        mode="simulink",
    )

    assert result["status"] == "failed"
    assert result["smoke_passed"] is False
    assert result["failures"][0]["failure_class"] == "contract_error"
    assert "harness_train_smoke_start" in result["failures"][0]["message"]
    assert called is False
    train_smoke_path = run_dir / "train_smoke.json"
    assert train_smoke_path.exists()


def test_train_smoke_start_launches_and_poll_collects(tmp_path, monkeypatch):
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(smoke_tasks, "_PROJECT_ROOT", tmp_path)
    _write_green_modeling_records(harness_reports, "kundur", "run-async")

    # Create a fake training script that writes expected artifacts.
    train_script = tmp_path / "scenarios" / "kundur" / "train_simulink.py"
    train_script.parent.mkdir(parents=True, exist_ok=True)
    train_script.write_text(
        "import argparse, pathlib, json, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--mode')\n"
        "p.add_argument('--episodes', type=int)\n"
        "p.add_argument('--checkpoint-dir')\n"
        "p.add_argument('--log-file')\n"
        "args = p.parse_args()\n"
        "pathlib.Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)\n"
        "(pathlib.Path(args.checkpoint_dir) / 'final.pt').write_text('ckpt')\n"
        "pathlib.Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)\n"
        "pathlib.Path(args.log_file).write_text(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )

    # Start
    start_result = smoke_tasks.harness_train_smoke_start(
        scenario_id="kundur",
        run_id="run-async",
        episodes=1,
        mode="simulink",
    )
    assert start_result["status"] == "running"
    assert start_result["smoke_started"] is True
    assert start_result["pid"] is not None

    # Wait for process to finish (it's a tiny script).
    import time
    for _ in range(60):
        poll_result = smoke_tasks.harness_train_smoke_poll(
            scenario_id="kundur",
            run_id="run-async",
        )
        if poll_result["process_status"] != "running":
            break
        time.sleep(0.5)

    assert poll_result["process_status"] == "finished"
    assert poll_result["smoke_passed"] is True
    assert poll_result["exit_code"] == 0
    assert len(poll_result["native_checkpoint_paths"]) >= 1
    # Fake script wrote {"ok": True} — no training keys, so summary is present but empty
    assert poll_result["training_summary"] is not None
    assert poll_result["training_summary"]["episodes_completed"] == 0
    assert poll_result["training_summary"]["last_10_reward_mean"] is None


def test_train_smoke_start_rejects_without_preconditions(tmp_path, monkeypatch):
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    harness_reports.ensure_run_dir("kundur", "run-fail")

    result = smoke_tasks.harness_train_smoke_start(
        scenario_id="kundur",
        run_id="run-fail",
    )
    assert result["status"] == "failed"
    assert result["smoke_started"] is False


def test_train_smoke_poll_not_found(tmp_path, monkeypatch):
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    harness_reports.ensure_run_dir("kundur", "run-ghost")

    result = smoke_tasks.harness_train_smoke_poll(
        scenario_id="kundur",
        run_id="run-ghost",
    )
    assert result["status"] == "failed"
    assert result["process_status"] == "not_found"


def test_poll_training_summary_populated_from_complete_log(tmp_path, monkeypatch):
    """training_summary is parsed from training_log.json after successful training."""
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(smoke_tasks, "_PROJECT_ROOT", tmp_path)
    _write_green_modeling_records(harness_reports, "kundur", "run-tsum")

    # 11 episodes, last-10 mean = (-80-60-50-40-35-30-25-20-15-10)/10 = -36.5
    log_content = json.dumps({
        "episode_rewards": [-100.0, -80.0, -60.0, -50.0, -40.0,
                            -35.0, -30.0, -25.0, -20.0, -15.0, -10.0],
        "eval_rewards": [
            {"episode": 5, "reward": -55.0},
            {"episode": 10, "reward": -12.0},
        ],
        "critic_losses": [0.5, 0.4, 0.3],
        "policy_losses": [0.2, 0.1, 0.08],
        "alphas": [0.2, 0.18, 0.15],
        "physics_summary": [
            {"max_freq_dev_hz": 0.5, "mean_freq_dev_hz": 0.2, "settled": False, "max_power_swing": 0.1},
            {"max_freq_dev_hz": 0.3, "mean_freq_dev_hz": 0.1, "settled": True,  "max_power_swing": 0.05},
        ],
    })

    train_script = tmp_path / "scenarios" / "kundur" / "train_simulink.py"
    train_script.parent.mkdir(parents=True, exist_ok=True)
    train_script.write_text(
        "import argparse, pathlib, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--mode'); p.add_argument('--episodes', type=int)\n"
        "p.add_argument('--checkpoint-dir'); p.add_argument('--log-file')\n"
        "args = p.parse_args()\n"
        "pathlib.Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)\n"
        "(pathlib.Path(args.checkpoint_dir) / 'final.pt').write_text('ckpt')\n"
        "pathlib.Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)\n"
        f"pathlib.Path(args.log_file).write_text({repr(log_content)})\n",
        encoding="utf-8",
    )

    start_result = smoke_tasks.harness_train_smoke_start(
        scenario_id="kundur", run_id="run-tsum", episodes=1, mode="simulink",
    )
    assert start_result["smoke_started"] is True

    import time
    for _ in range(60):
        poll_result = smoke_tasks.harness_train_smoke_poll(
            scenario_id="kundur", run_id="run-tsum",
        )
        if poll_result["process_status"] != "running":
            break
        time.sleep(0.5)

    assert poll_result["smoke_passed"] is True

    ts = poll_result["training_summary"]
    assert ts is not None
    assert ts["episodes_completed"] == 11
    assert ts["last_10_reward_mean"] == -36.5
    assert ts["best_eval_reward"] == -12.0
    assert ts["last_eval_reward"] == -12.0
    assert ts["last_alpha"] == 0.15
    assert ts["physics_settled_rate_last10"] == 0.5   # 1 settled out of 2
    assert ts["last_max_freq_dev_hz"] == 0.3

    # Existing fields must be unaffected
    assert poll_result["process_status"] == "finished"
    assert poll_result["exit_code"] == 0
    assert len(poll_result["native_checkpoint_paths"]) >= 1


def test_parse_training_summary_returns_none_for_absent_and_invalid(tmp_path):
    """_parse_training_summary is None for missing file or malformed JSON."""
    from engine.smoke_tasks import _parse_training_summary

    # File does not exist
    assert _parse_training_summary(tmp_path / "no_such_file.json") is None

    # Malformed JSON (truncated write)
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert _parse_training_summary(bad) is None

    # Valid JSON but no training keys → episodes_completed=0, all others None
    empty_log = tmp_path / "empty.json"
    empty_log.write_text("{}", encoding="utf-8")
    result = _parse_training_summary(empty_log)
    assert result is not None
    assert result["episodes_completed"] == 0
    assert result["last_10_reward_mean"] is None
    assert result["best_eval_reward"] is None


def test_train_smoke_poll_recovers_pid_from_disk_after_restart(tmp_path, monkeypatch):
    """Simulate MCP restart: clear in-memory dict, poll should recover PID from disk."""
    from engine import harness_reports, smoke_tasks

    monkeypatch.setattr(harness_reports, "HARNESS_ROOT", tmp_path / "results" / "harness")
    monkeypatch.setattr(smoke_tasks, "_PROJECT_ROOT", tmp_path)
    run_dir = _write_green_modeling_records(harness_reports, "kundur", "run-recover")

    # Create a fake train_script that exits quickly.
    train_script = tmp_path / "scenarios" / "kundur" / "train_simulink.py"
    train_script.parent.mkdir(parents=True, exist_ok=True)
    train_script.write_text(
        "import argparse, pathlib, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--mode')\n"
        "p.add_argument('--episodes', type=int)\n"
        "p.add_argument('--checkpoint-dir')\n"
        "p.add_argument('--log-file')\n"
        "args = p.parse_args()\n"
        "pathlib.Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)\n"
        "(pathlib.Path(args.checkpoint_dir) / 'final.pt').write_text('ckpt')\n"
        "pathlib.Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)\n"
        "pathlib.Path(args.log_file).write_text(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )

    # Start normally.
    start_result = smoke_tasks.harness_train_smoke_start(
        scenario_id="kundur", run_id="run-recover", episodes=1, mode="simulink",
    )
    assert start_result["smoke_started"] is True
    pid = start_result["pid"]

    # Wait for process to finish.
    import time
    for _ in range(60):
        if smoke_tasks._SMOKE_PROCESSES.get(("kundur", "run-recover"), None) is None:
            break
        if smoke_tasks._SMOKE_PROCESSES[("kundur", "run-recover")].poll() is not None:
            break
        time.sleep(0.2)

    # Simulate MCP restart: clear in-memory state.
    smoke_tasks._SMOKE_PROCESSES.clear()
    smoke_tasks._SMOKE_LOG_HANDLES.clear()

    # Poll should recover from disk. Process is dead, so it collects results.
    poll_result = smoke_tasks.harness_train_smoke_poll(
        scenario_id="kundur", run_id="run-recover",
    )
    assert poll_result["process_status"] == "finished"
    assert poll_result["pid"] == pid
    # exit_code is None because we lost the handle, but smoke_passed inferred from artifacts.
    assert poll_result["exit_code"] is None
    assert poll_result["smoke_passed"] is True
