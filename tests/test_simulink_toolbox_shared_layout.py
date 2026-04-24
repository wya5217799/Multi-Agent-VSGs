"""Guard tests for the shared simulink-toolbox skill install layout.

Verifies that:
- Both install directories exist
- Their resolved canonical paths are identical (both are junctions to the shared root)
- Required shared hook subfolders exist
- Generic patterns do not include training-smoke-debug.md
- Repo overlay folder exists
- Repo model overlay folder exists
"""

from __future__ import annotations

from pathlib import Path

import pytest

CODEX_INSTALL = Path.home() / ".codex" / "skills" / "simulink-toolbox"
CLAUDE_INSTALL = Path.home() / ".claude" / "skills" / "simulink-toolbox"

_REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_OVERLAY = _REPO_ROOT / "docs" / "agent_layer" / "simulink-project-routing"
REPO_MODELS = REPO_OVERLAY / "models"


def _resolve_path(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


@pytest.mark.offline
def test_both_install_directories_exist() -> None:
    if not CODEX_INSTALL.exists():
        pytest.skip("CODEX install not present.")
    if not CLAUDE_INSTALL.exists():
        pytest.skip("CLAUDE install not present.")
    assert CODEX_INSTALL.exists(), f"CODEX install missing: {CODEX_INSTALL}"
    assert CLAUDE_INSTALL.exists(), f"CLAUDE install missing: {CLAUDE_INSTALL}"


@pytest.mark.offline
def test_both_installs_resolve_to_same_canonical_path() -> None:
    if not CODEX_INSTALL.exists() or not CLAUDE_INSTALL.exists():
        pytest.skip("One or both install paths do not exist.")
    codex_real = _resolve_path(CODEX_INSTALL)
    claude_real = _resolve_path(CLAUDE_INSTALL)
    assert str(codex_real).lower() == str(claude_real).lower(), (
        f"Install paths resolve to different directories:\n"
        f"  CODEX  -> {codex_real}\n"
        f"  CLAUDE -> {claude_real}\n"
        f"Both should be junctions to the shared root."
    )


@pytest.mark.offline
def test_shared_hook_subfolders_exist() -> None:
    if not CODEX_INSTALL.exists():
        pytest.skip("CODEX install not present.")
    shared_root = _resolve_path(CODEX_INSTALL)
    assert (shared_root / "hooks" / "codex" / "codex_simulink_hook.py").exists(), \
        "hooks/codex/codex_simulink_hook.py missing from shared skill"
    assert (shared_root / "hooks" / "claude" / "pre-tool-use.sh").exists(), \
        "hooks/claude/pre-tool-use.sh missing from shared skill"
    assert (shared_root / "hooks" / "claude" / "user-prompt-submit.sh").exists(), \
        "hooks/claude/user-prompt-submit.sh missing from shared skill"


@pytest.mark.offline
def test_generic_patterns_do_not_include_training_smoke_debug() -> None:
    if not CODEX_INSTALL.exists():
        pytest.skip("CODEX install not present.")
    shared_root = _resolve_path(CODEX_INSTALL)
    assert not (shared_root / "patterns" / "training-smoke-debug.md").exists(), (
        "patterns/training-smoke-debug.md must not exist in the generic shared skill. "
        "It belongs in docs/agent_layer/simulink-project-routing/."
    )


@pytest.mark.offline
def test_repo_overlay_folder_exists() -> None:
    assert REPO_OVERLAY.exists(), (
        f"Repository Simulink project routing overlay missing: {REPO_OVERLAY}\n"
        f"Expected at: docs/agent_layer/simulink-project-routing/"
    )
    assert (REPO_OVERLAY / "README.md").exists(), \
        "docs/agent_layer/simulink-project-routing/README.md missing"
    assert (REPO_OVERLAY / "training-smoke-debug.md").exists(), \
        "docs/agent_layer/simulink-project-routing/training-smoke-debug.md missing"


@pytest.mark.offline
def test_repo_model_overlay_folder_exists() -> None:
    assert REPO_MODELS.exists(), (
        f"Repository model overlay folder missing: {REPO_MODELS}\n"
        f"Expected at: docs/agent_layer/simulink-project-routing/models/"
    )
    assert (REPO_MODELS / "kundur.md").exists(), \
        "docs/agent_layer/simulink-project-routing/models/kundur.md missing"
    assert (REPO_MODELS / "ne39.md").exists(), \
        "docs/agent_layer/simulink-project-routing/models/ne39.md missing"
