import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.workspace_clean import (
    HygieneConfig,
    apply_clean,
    load_config,
    scan_workspace,
)


def make_config(tmp_path):
    return HygieneConfig(
        quarantine_root=tmp_path / "quarantine",
        movable_patterns=("paper_draft.tex", "论文/**", "__pycache__/**"),
        report_only_patterns=("MEMORY.md",),
        protected_patterns=("AGENTS.md", "docs/**"),
    )


def test_scan_reports_movable_and_report_only_pollution(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "paper_draft.tex").write_text("draft")
    (workspace / "MEMORY.md").write_text("memory")
    (workspace / "src").mkdir()
    (workspace / "src" / "model.py").write_text("print('ok')")

    findings = scan_workspace(workspace, make_config(tmp_path), tracked_paths=set())

    assert [(f.relative_path, f.action) for f in findings] == [
        ("MEMORY.md", "report"),
        ("paper_draft.tex", "move"),
    ]


def test_scan_never_moves_tracked_or_protected_paths(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "paper_draft.tex").write_text("tracked draft")
    (workspace / "AGENTS.md").write_text("instructions")

    config = HygieneConfig(
        quarantine_root=tmp_path / "quarantine",
        movable_patterns=("*.md", "paper_draft.tex"),
        report_only_patterns=(),
        protected_patterns=("AGENTS.md",),
    )
    findings = scan_workspace(
        workspace,
        config,
        tracked_paths={"paper_draft.tex", "AGENTS.md"},
    )

    assert [(f.relative_path, f.action, f.reason) for f in findings] == [
        ("AGENTS.md", "report", "protected"),
        ("paper_draft.tex", "report", "tracked"),
    ]


def test_scan_does_not_move_directory_containing_tracked_files(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    figure_dir = workspace / "Figure.paper"
    figure_dir.mkdir()
    (figure_dir / "4.png").write_bytes(b"tracked")

    config = HygieneConfig(
        quarantine_root=tmp_path / "quarantine",
        movable_patterns=("Figure.paper", "Figure.paper/**"),
        report_only_patterns=(),
        protected_patterns=(),
    )

    findings = scan_workspace(workspace, config, tracked_paths={"Figure.paper/4.png"})

    assert len(findings) == 1
    assert findings[0].relative_path == "Figure.paper"
    assert findings[0].action == "report"
    assert findings[0].reason == "contains_tracked"


def test_scan_does_not_report_clean_protected_paths(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "docs" / "decision.md").write_text("keep")

    config = HygieneConfig(
        quarantine_root=tmp_path / "quarantine",
        movable_patterns=("paper_draft.tex",),
        report_only_patterns=(),
        protected_patterns=("docs/**",),
    )

    assert scan_workspace(workspace, config, tracked_paths=set()) == []


def test_apply_clean_moves_only_movable_findings_and_writes_manifest(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "论文").mkdir()
    (workspace / "论文" / "paper.pdf").write_text("pdf")
    (workspace / "MEMORY.md").write_text("memory")
    cache_dir = workspace / "pkg" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (cache_dir / "module.pyc").write_bytes(b"cache")

    config = make_config(tmp_path)
    findings = scan_workspace(workspace, config, tracked_paths=set())
    manifest_path = apply_clean(workspace, config, findings, dry_run=False, timestamp="20260411_120000")

    assert not (workspace / "论文" / "paper.pdf").exists()
    assert not (workspace / "pkg" / "__pycache__" / "module.pyc").exists()
    assert (workspace / "MEMORY.md").exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    moved = {entry["relative_path"] for entry in manifest["moved"]}
    reported = {entry["relative_path"] for entry in manifest["reported"]}
    assert moved == {"pkg/__pycache__/module.pyc", "论文/paper.pdf"}
    assert reported == {"MEMORY.md"}
    for entry in manifest["moved"]:
        assert Path(entry["destination"]).exists()


def test_apply_clean_dry_run_does_not_move_or_write_manifest(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "paper_draft.tex").write_text("draft")
    config = make_config(tmp_path)

    findings = scan_workspace(workspace, config, tracked_paths=set())
    manifest_path = apply_clean(workspace, config, findings, dry_run=True, timestamp="20260411_120000")

    assert manifest_path is None
    assert (workspace / "paper_draft.tex").exists()
    assert not config.quarantine_root.exists()


def test_default_config_classifies_pollution_correctly():
    config = load_config()

    # MEMORY.md is a tracked navigation file, must NOT be movable
    assert "MEMORY.md" not in config.movable_patterns

    # Local-only artifacts should be movable
    assert ".claude" in config.movable_patterns
    assert ".worktrees" in config.movable_patterns
    assert "results/sim_kundur" in config.movable_patterns
    assert "results/sim_ne39" in config.movable_patterns
