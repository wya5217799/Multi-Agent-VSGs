"""Static boundary tests for slx_helpers.

The repository has two MATLAB helper families:
- general Simulink primitives in slx_helpers/
- VSG/RL bridge adapters in slx_helpers/vsg_bridge/

These tests keep the directory boundary mechanical so the general MCP layer
does not drift back into VSG-specific helper calls.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "slx_helpers"
VSG_DIR = CORE_DIR / "vsg_bridge"

VSG_BRIDGE_HELPERS = {
    "slx_warmup.m",
    "slx_step_and_read.m",
    "slx_extract_state.m",
    "slx_build_bridge_config.m",
    "slx_validate_model.m",
    "slx_fastrestart_reset.m",
    "slx_episode_warmup.m",
}

CORE_HELPERS_REQUIRED = {
    "slx_add_block.m",
    "slx_add_subsystem.m",
    "slx_batch_query.m",
    "slx_compile_diagnostics.m",
    "slx_connect_blocks.m",
    "slx_delete_block.m",
    "slx_describe_block_ports.m",
    "slx_get_block_tree.m",
    "slx_patch_and_verify.m",
    "slx_run_window.m",
    "slx_signal_snapshot.m",
    "slx_workspace_set.m",
}


def test_vsg_bridge_helpers_live_in_vsg_bridge_subdir():
    assert VSG_DIR.is_dir(), f"missing VSG bridge helper dir: {VSG_DIR}"

    for helper_name in sorted(VSG_BRIDGE_HELPERS):
        root_path = CORE_DIR / helper_name
        bridge_path = VSG_DIR / helper_name
        assert not root_path.exists(), (
            f"legacy VSG helper still in slx_helpers root: {helper_name}"
        )
        assert bridge_path.exists(), (
            f"legacy VSG helper missing from vsg_bridge dir: {helper_name}"
        )


def test_core_helpers_remain_in_slx_helpers_root():
    for helper_name in sorted(CORE_HELPERS_REQUIRED):
        assert (CORE_DIR / helper_name).exists(), (
            f"general Simulink helper missing from slx_helpers root: {helper_name}"
        )


def test_public_mcp_tools_do_not_call_vsg_bridge_helpers_directly():
    tool_text = (ROOT / "engine" / "mcp_simulink_tools.py").read_text(
        encoding="utf-8"
    )

    for helper_name in sorted(VSG_BRIDGE_HELPERS):
        helper_stem = helper_name.removesuffix(".m")
        assert f'"{helper_stem}"' not in tool_text
        assert f"'{helper_stem}'" not in tool_text
