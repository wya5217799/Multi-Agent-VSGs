from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SLX_HELPERS = REPO_ROOT / "slx_helpers"

LEGACY_PROJECT_ADAPTERS = {
    "slx_warmup.m",
    "slx_fastrestart_reset.m",
    "slx_episode_warmup.m",
    "slx_step_and_read.m",
    "slx_extract_state.m",
    "slx_build_bridge_config.m",
    "slx_validate_model.m",
}

FORBIDDEN_GENERAL_TOKENS = {
    "agent_ids",
    "m_values",
    "d_values",
    "reward",
    "episode",
    "kundur",
    "ne39",
    "vsg",
    "vsg-base",
    "system-base",
}


def test_general_slx_helpers_do_not_add_project_terms():
    offenders = {}
    for path in sorted(SLX_HELPERS.glob("slx_*.m")):
        if path.name in LEGACY_PROJECT_ADAPTERS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits = sorted(token for token in FORBIDDEN_GENERAL_TOKENS if token in text)
        if hits:
            offenders[path.name] = hits
    assert not offenders, offenders
