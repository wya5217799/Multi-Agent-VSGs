"""Check and clean non-project workspace artifacts.

The tool is intentionally conservative:
- tracked files are reported, never moved
- protected paths are reported, never moved
- dry-run is the default CLI mode
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable

import tomllib


DEFAULT_CONFIG = Path(__file__).with_name("workspace_hygiene.toml")


@dataclass(frozen=True)
class HygieneConfig:
    quarantine_root: Path
    movable_patterns: tuple[str, ...]
    report_only_patterns: tuple[str, ...]
    protected_patterns: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    relative_path: str
    action: str
    reason: str
    pattern: str


def load_config(path: Path = DEFAULT_CONFIG) -> HygieneConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return HygieneConfig(
        quarantine_root=Path(data["quarantine_root"]),
        movable_patterns=tuple(data.get("movable_patterns", ())),
        report_only_patterns=tuple(data.get("report_only_patterns", ())),
        protected_patterns=tuple(data.get("protected_patterns", ())),
    )


def get_tracked_paths(workspace: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def scan_workspace(
    workspace: Path,
    config: HygieneConfig,
    tracked_paths: set[str] | None = None,
) -> list[Finding]:
    workspace = workspace.resolve()
    tracked = tracked_paths if tracked_paths is not None else get_tracked_paths(workspace)
    candidates = _iter_candidates(workspace)
    findings: list[Finding] = []
    claimed: list[str] = []

    for rel in candidates:
        if any(_is_inside(rel, parent) for parent in claimed):
            continue
        report_pattern = _first_match(rel, config.report_only_patterns)
        move_pattern = _first_match(rel, config.movable_patterns)
        pollution_pattern = report_pattern or move_pattern
        if not pollution_pattern:
            continue

        if pattern := _first_match(rel, config.protected_patterns):
            findings.append(Finding(rel, "report", "protected", pattern))
            claimed.append(rel)
        elif rel in tracked:
            pattern = pollution_pattern or "tracked"
            findings.append(Finding(rel, "report", "tracked", pattern))
            claimed.append(rel)
        elif move_pattern and _contains_tracked(rel, tracked):
            findings.append(Finding(rel, "report", "contains_tracked", move_pattern))
            claimed.append(rel)
        elif report_pattern:
            findings.append(Finding(rel, "report", "report_only", report_pattern))
            claimed.append(rel)
        elif move_pattern:
            findings.append(Finding(rel, "move", "movable", move_pattern))
            claimed.append(rel)

    return findings


def apply_clean(
    workspace: Path,
    config: HygieneConfig,
    findings: Iterable[Finding],
    *,
    dry_run: bool = True,
    timestamp: str | None = None,
) -> Path | None:
    findings = list(findings)
    if dry_run:
        return None

    workspace = workspace.resolve()
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    destination_root = config.quarantine_root / f"Multi-Agent VSGs_cleanup_{stamp}"
    moved = []
    reported = []

    for finding in findings:
        record = {
            "relative_path": finding.relative_path,
            "action": finding.action,
            "reason": finding.reason,
            "pattern": finding.pattern,
        }
        source = workspace / Path(finding.relative_path)
        if finding.action != "move":
            reported.append(record)
            continue
        if not source.exists():
            reported.append({**record, "action": "report", "reason": "missing"})
            continue

        destination = _unique_destination(destination_root / Path(finding.relative_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append({**record, "destination": str(destination)})
        _remove_empty_parents(source.parent, workspace)

    destination_root.mkdir(parents=True, exist_ok=True)
    manifest_path = destination_root / "manifest.json"
    manifest = {
        "workspace": str(workspace),
        "quarantine_root": str(destination_root),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "moved": moved,
        "reported": reported,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or clean workspace pollution.")
    parser.add_argument("command", choices=("check", "clean"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", help="Move matched files. Default is dry-run.")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    findings = scan_workspace(args.workspace, config)
    _print_findings(findings)

    if args.command == "check":
        return 1 if any(finding.action == "move" for finding in findings) else 0

    manifest = apply_clean(args.workspace, config, findings, dry_run=not args.apply)
    if manifest:
        print(f"manifest: {manifest}")
    else:
        print("dry-run: no files moved")
    return 0


def _iter_candidates(workspace: Path) -> list[str]:
    paths = []
    for path in workspace.rglob("*"):
        rel = path.relative_to(workspace).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        paths.append(rel)
    return sorted(paths, key=lambda item: (item.count("/"), item))


def _first_match(relative_path: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        normalized = pattern.strip().replace("\\", "/").rstrip("/")
        expanded = [normalized]
        if "/" in normalized and not normalized.startswith("**/"):
            expanded.append(f"**/{normalized}")
            expanded.append(f"*/{normalized}")
        if any(fnmatchcase(relative_path, candidate) for candidate in expanded):
            return pattern
    return None


def _is_inside(relative_path: str, parent: str) -> bool:
    return relative_path != parent and relative_path.startswith(parent.rstrip("/") + "/")


def _contains_tracked(relative_path: str, tracked_paths: Iterable[str]) -> bool:
    return any(_is_inside(tracked_path, relative_path) for tracked_path in tracked_paths)


def _unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    counter = 1
    while True:
        candidate = destination.with_name(f"{destination.name}.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def _remove_empty_parents(start: Path, stop: Path) -> None:
    current = start
    stop = stop.resolve()
    while current.resolve() != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _print_findings(findings: Iterable[Finding]) -> None:
    for finding in findings:
        print(f"{finding.action}\t{finding.reason}\t{finding.relative_path}\t{finding.pattern}")


if __name__ == "__main__":
    sys.exit(main())
