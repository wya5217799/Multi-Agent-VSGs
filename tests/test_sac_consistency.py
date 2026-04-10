"""Regression tests for known SAC consistency bugs.

These tests guard against re-introducing bugs that were fixed but had
no tests: alpha gradient clip sync, buffer size, save key set.
Both SAC implementations must pass all checks.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAC_MAIN = PROJECT_ROOT / "agents" / "sac.py"
SAC_STANDALONE = PROJECT_ROOT / "env" / "simulink" / "sac_agent_standalone.py"


# ---------- Alpha gradient clip ----------

def _has_alpha_clip(path: Path) -> bool:
    """Return True if file applies clip_grad_norm_ to the alpha/log_alpha param."""
    text = path.read_text(encoding="utf-8")
    return bool(re.search(r"clip_grad_norm_.*log_alpha", text))


def test_sac_main_has_alpha_clip():
    assert _has_alpha_clip(SAC_MAIN), (
        "agents/sac.py must apply clip_grad_norm_ to log_alpha. "
        "This was a known bug — see feedback_training_structural_fixes.md"
    )


def test_sac_standalone_has_alpha_clip():
    if not SAC_STANDALONE.exists():
        import pytest
        pytest.skip("sac_agent_standalone.py not found")
    assert _has_alpha_clip(SAC_STANDALONE), (
        "env/simulink/sac_agent_standalone.py must apply clip_grad_norm_ to log_alpha. "
        "Both SAC files must be kept in sync."
    )


# ---------- Save key set ----------

def _get_save_keys(path: Path) -> set[str]:
    """Extract keys passed to torch.save({...}) in the save() method."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"torch\.save\(\{([^}]+)\}", text, re.DOTALL)
    if not match:
        return set()
    block = match.group(1)
    return set(re.findall(r"['\"](\w+)['\"]", block))


def test_sac_main_save_has_required_keys():
    keys = _get_save_keys(SAC_MAIN)
    required = {"actor", "critic", "critic_target", "log_alpha",
                "actor_opt", "critic_opt", "alpha_opt"}
    missing = required - keys
    assert not missing, f"agents/sac.py save() missing keys: {missing}"


def test_sac_standalone_save_has_required_keys():
    if not SAC_STANDALONE.exists():
        import pytest
        pytest.skip("sac_agent_standalone.py not found")
    keys = _get_save_keys(SAC_STANDALONE)
    # Standalone uses different key names: policy (not actor), policy_optim, etc.
    required = {"policy", "critic", "log_alpha"}
    missing = required - keys
    assert not missing, f"sac_agent_standalone.py save() missing keys: {missing}"


# ---------- Buffer size not undersized ----------

def test_kundur_buffer_not_undersized():
    """Kundur config BUFFER_SIZE must be >= 10000 for 4-agent training."""
    from scenarios.kundur.config_simulink import BUFFER_SIZE
    assert BUFFER_SIZE >= 10000, (
        f"BUFFER_SIZE={BUFFER_SIZE} is too small for 4-agent Kundur training."
    )


def test_ne39_buffer_not_undersized():
    """NE39 config BUFFER_SIZE must be >= 50000 for 8-agent training."""
    from scenarios.new_england.config_simulink import BUFFER_SIZE
    assert BUFFER_SIZE >= 50000, (
        f"BUFFER_SIZE={BUFFER_SIZE} is too small for 8-agent NE39 training."
    )


# ---------- Reward formula: mean(a**2) not (mean(a))**2 ----------

def _uses_correct_reward_formula(path: Path) -> bool:
    """Check that action penalty uses np.mean(a**2) or similar, not np.mean(a)**2."""
    text = path.read_text(encoding="utf-8")
    bad = re.search(r"np\.mean\(.*action.*\)\s*\*\*\s*2", text)
    return bad is None


def test_kundur_env_reward_formula():
    env_file = PROJECT_ROOT / "env" / "simulink" / "kundur_simulink_env.py"
    if env_file.exists():
        assert _uses_correct_reward_formula(env_file), (
            "kundur_simulink_env.py contains (mean(action))**2 penalty — should be mean(action**2). "
            "This silently cancels symmetric actions."
        )


def test_ne39_env_reward_formula():
    env_file = PROJECT_ROOT / "env" / "simulink" / "ne39_simulink_env.py"
    if env_file.exists():
        assert _uses_correct_reward_formula(env_file), (
            "ne39_simulink_env.py contains (mean(action))**2 penalty — should be mean(action**2)."
        )


# ---------- Config base inheritance ----------

def test_kundur_config_uses_base_lr():
    from scenarios.kundur.config_simulink import LR
    from scenarios.config_simulink_base import LR as BASE_LR
    assert LR == BASE_LR, "Kundur LR diverged from base — edit config_simulink_base.py to change it"


def test_ne39_config_uses_base_lr():
    from scenarios.new_england.config_simulink import LR
    from scenarios.config_simulink_base import LR as BASE_LR
    assert LR == BASE_LR, "NE39 LR diverged from base — edit config_simulink_base.py to change it"
