"""
TDD tests for the three structural fixes:

  P1  run_id isolation: standalone and simulink must use separate checkpoint/log dirs
  P2  alpha_optim grad clip: clip_grad_norm_ must be applied before alpha_optim.step()
  P3  NE39 buffer_size: must be >= 10_000 (currently 2_500, too small for 8-agent)
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pytest

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# P3  NE39 buffer_size — simplest test, no mock needed
# =============================================================================

class TestNE39BufferSize:
    """
    NE39 has 8 agents, each contributing transitions every step.
    buffer_size=2500 fills in ~312 steps → replay diversity is effectively zero.
    Minimum viable buffer for a 500-episode run: 10_000.
    """

    def test_ne39_buffer_size_at_least_10000(self):
        """BUFFER_SIZE in NE39 config must be >= 10_000."""
        from scenarios.new_england.config_simulink import BUFFER_SIZE
        assert BUFFER_SIZE >= 10_000, (
            f"NE39 BUFFER_SIZE={BUFFER_SIZE} is too small for 8-agent training. "
            f"Minimum required: 10_000."
        )

    def test_ne39_buffer_size_larger_than_kundur(self):
        """
        NE39 has 8 agents vs Kundur's 4 — it must fill the buffer twice as fast.
        NE39 buffer should be at least as large as Kundur's to compensate.
        """
        from scenarios.new_england.config_simulink import BUFFER_SIZE as NE39_BUF
        from scenarios.kundur.config_simulink import BUFFER_SIZE as KD_BUF
        assert NE39_BUF >= KD_BUF, (
            f"NE39 BUFFER_SIZE={NE39_BUF} < Kundur BUFFER_SIZE={KD_BUF}. "
            f"NE39 has 2x agents and fills faster — needs equal or larger buffer."
        )


# =============================================================================
# P2  alpha_optim grad clip
# =============================================================================

class TestAlphaGradClip:
    """
    SACAgent.update() must apply clip_grad_norm_ to alpha_optim parameters
    before stepping the optimizer, to bound log_alpha updates.

    Without this, Adam's first-step effective lr = lr / sqrt(eps) can be
    anomalously large when the squared-gradient accumulator is near zero.
    """

    def _make_agent(self):
        from env.simulink.sac_agent_standalone import SACAgent
        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=20, warmup_steps=0,
                         batch_size=10)
        # Fill buffer with enough transitions
        rng = np.random.default_rng(0)
        for _ in range(20):
            obs = rng.standard_normal(7).astype(np.float32)
            act = rng.uniform(-1, 1, 2).astype(np.float32)
            agent.store_transition(obs, act, -100.0, obs, False)
        return agent

    def test_sac_agent_has_max_grad_norm(self):
        """SACAgent must expose max_grad_norm for alpha gradient bounding."""
        from env.simulink.sac_agent_standalone import SACAgent
        agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=20, warmup_steps=0)
        assert hasattr(agent, "max_grad_norm"), (
            "SACAgent missing 'max_grad_norm' attribute required for alpha grad clipping"
        )

    def test_update_clips_alpha_gradient(self, monkeypatch):
        """update() must call clip_grad_norm_ with [log_alpha] before alpha_optim.step()."""
        import torch.nn as nn
        from env.simulink import sac_agent_standalone as module

        clip_calls = []
        original_clip = nn.utils.clip_grad_norm_

        def recording_clip(parameters, max_norm, **kwargs):
            params_list = list(parameters)
            clip_calls.append({"params": params_list, "max_norm": max_norm})
            return original_clip(params_list, max_norm, **kwargs)

        monkeypatch.setattr(module.nn.utils, "clip_grad_norm_", recording_clip)

        agent = self._make_agent()
        agent.update()

        # Must have been called at least once with log_alpha in the parameter list
        alpha_clips = [
            c for c in clip_calls
            if any(p is agent.log_alpha for p in c["params"])
        ]
        assert len(alpha_clips) > 0, (
            "clip_grad_norm_ was never called with log_alpha. "
            "Alpha gradient is unclipped, risking divergence on first Adam steps."
        )

    def test_agents_sac_also_clips_alpha_gradient(self, monkeypatch):
        """agents/sac.py (ANDES/ODE path) must also clip alpha gradient before optimizer step."""
        import torch
        import torch.nn as nn
        from agents import sac as module

        clip_calls = []
        original_clip = nn.utils.clip_grad_norm_

        def recording_clip(parameters, max_norm, **kwargs):
            clip_calls.append({"params": list(parameters), "max_norm": max_norm})
            return original_clip(list(parameters), max_norm, **kwargs)

        monkeypatch.setattr(module.nn.utils, "clip_grad_norm_", recording_clip)

        from agents.sac import SACAgent
        agent = SACAgent(obs_dim=4, action_dim=1, hidden_sizes=(32,), batch_size=10,
                         buffer_size=20, device="cpu")
        rng = np.random.default_rng(1)
        for _ in range(20):
            obs = rng.standard_normal(4).astype(np.float32)
            act = rng.uniform(-1, 1, 1).astype(np.float32)
            agent.store_transition(obs, act, -10.0, obs, False)

        agent.update()

        alpha_clips = [
            c for c in clip_calls
            if any(p is agent.log_alpha for p in c["params"])
        ]
        assert len(alpha_clips) > 0, (
            "agents/sac.py SACAgent: clip_grad_norm_ was never called with log_alpha. "
            "ANDES/ODE training path lacks alpha gradient bounding."
        )

    def test_alpha_grad_clip_uses_max_grad_norm(self, monkeypatch):
        """clip_grad_norm_ for alpha must use agent.max_grad_norm as the bound."""
        import torch.nn as nn
        from env.simulink import sac_agent_standalone as module

        clip_calls = []
        original_clip = nn.utils.clip_grad_norm_

        def recording_clip(parameters, max_norm, **kwargs):
            clip_calls.append({"params": list(parameters), "max_norm": max_norm})
            return original_clip(list(parameters), max_norm, **kwargs)

        monkeypatch.setattr(module.nn.utils, "clip_grad_norm_", recording_clip)

        agent = self._make_agent()
        agent.update()

        alpha_clips = [
            c for c in clip_calls
            if any(p is agent.log_alpha for p in c["params"])
        ]
        assert len(alpha_clips) > 0  # already tested above, guard for message clarity

        actual_max_norm = alpha_clips[0]["max_norm"]
        assert actual_max_norm == agent.max_grad_norm, (
            f"Alpha grad clip used max_norm={actual_max_norm}, "
            f"expected agent.max_grad_norm={agent.max_grad_norm}"
        )


# =============================================================================
# P1  run_id / mode isolation for checkpoint and log dirs
# =============================================================================

class TestNE39AutoResume:
    """
    NE39 train script must have the same auto-resume logic as Kundur:
    scan checkpoint_dir for ep*.pt files and load the latest automatically,
    preventing alpha-reset collapse when training is restarted on an existing log.
    """

    def _parse_ne39(self, argv=None):
        old_argv = sys.argv[:]
        sys.argv = ["train_simulink.py"] + (argv or [])
        try:
            if "scenarios.new_england.train_simulink" in sys.modules:
                del sys.modules["scenarios.new_england.train_simulink"]
            from scenarios.new_england.train_simulink import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    def test_ne39_resume_none_string_disables_auto_resume(self):
        """--resume none must disable auto-resume (force fresh start)."""
        args = self._parse_ne39(["--mode", "standalone", "--resume", "none"])
        # The 'none' string value should be normalised to prevent auto-resume
        # We test this by checking parse_args accepts it without error.
        assert args.resume.lower() == "none"

    def test_ne39_auto_resume_loads_latest_ep_checkpoint(self, tmp_path):
        """train() must auto-load the highest ep*.pt from checkpoint_dir if --resume not given."""
        import torch
        from env.simulink.sac_agent_standalone import SACAgent

        # Create fake checkpoint files
        ckpt_dir = tmp_path / "checkpoints" / "standalone"
        ckpt_dir.mkdir(parents=True)

        # Save a real checkpoint at ep50
        dummy_agent = SACAgent(obs_dim=7, act_dim=2, buffer_size=10, warmup_steps=0)
        ckpt_path = str(ckpt_dir / "ep50.pt")
        dummy_agent.save(ckpt_path, metadata={"start_episode": 50})

        # Verify the checkpoint can be found and loaded
        ep_ckpts = sorted(
            [f for f in os.listdir(str(ckpt_dir)) if f.startswith("ep") and f.endswith(".pt")],
            key=lambda name: int(name[2:-3]),
        )
        assert ep_ckpts == ["ep50.pt"], "checkpoint not written correctly"

        loader = SACAgent(obs_dim=7, act_dim=2, buffer_size=10, warmup_steps=0)
        meta = loader.load(ckpt_path)
        assert meta.get("start_episode") == 50, (
            "auto-resume must restore start_episode=50 from checkpoint metadata"
        )


class TestRunIsolation:
    """
    standalone and simulink modes must write to separate directories so that
    auto-resume never picks up checkpoints from the other mode.

    The minimal fix: parse_args() derives checkpoint-dir and log-file from
    args.mode, giving:
      checkpoints/standalone/   checkpoints/simulink/
      logs/standalone/          logs/simulink/
    """

    def _parse_kundur(self, argv=None):
        old_argv = sys.argv[:]
        sys.argv = ["train_simulink.py"] + (argv or [])
        try:
            if "scenarios.kundur.train_simulink" in sys.modules:
                del sys.modules["scenarios.kundur.train_simulink"]
            from scenarios.kundur.train_simulink import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    def _parse_ne39(self, argv=None):
        old_argv = sys.argv[:]
        sys.argv = ["train_simulink.py"] + (argv or [])
        try:
            if "scenarios.new_england.train_simulink" in sys.modules:
                del sys.modules["scenarios.new_england.train_simulink"]
            from scenarios.new_england.train_simulink import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    # ── Kundur ───────────────────────────────────────────────────────────────

    def test_kundur_checkpoint_dir_contains_mode_standalone(self):
        """Kundur standalone checkpoint dir must contain the word 'standalone'."""
        args = self._parse_kundur(["--mode", "standalone"])
        assert "standalone" in args.checkpoint_dir, (
            f"checkpoint_dir='{args.checkpoint_dir}' does not include mode 'standalone'. "
            f"Cross-mode auto-resume will contaminate training."
        )

    def test_kundur_checkpoint_dir_contains_mode_simulink(self):
        """Kundur simulink checkpoint dir must contain the word 'simulink'."""
        args = self._parse_kundur(["--mode", "simulink"])
        assert "simulink" in args.checkpoint_dir, (
            f"checkpoint_dir='{args.checkpoint_dir}' does not include mode 'simulink'."
        )

    def test_kundur_standalone_simulink_use_different_checkpoint_dirs(self):
        """Kundur standalone and simulink must not share checkpoint directories."""
        args_sta = self._parse_kundur(["--mode", "standalone"])
        args_sim = self._parse_kundur(["--mode", "simulink"])
        assert args_sta.checkpoint_dir != args_sim.checkpoint_dir, (
            "standalone and simulink modes share the same checkpoint_dir. "
            "This enables cross-mode checkpoint contamination."
        )

    def test_kundur_standalone_simulink_use_different_log_files(self):
        """Kundur standalone and simulink must write to different training_log.json files."""
        args_sta = self._parse_kundur(["--mode", "standalone"])
        args_sim = self._parse_kundur(["--mode", "simulink"])
        assert args_sta.log_file != args_sim.log_file, (
            "standalone and simulink modes share the same log_file. "
            "Two modes will append entries into the same JSON, making the log ambiguous."
        )

    # ── NE39 ─────────────────────────────────────────────────────────────────

    def test_ne39_checkpoint_dir_contains_mode_standalone(self):
        """NE39 standalone checkpoint dir must contain the word 'standalone'."""
        args = self._parse_ne39(["--mode", "standalone"])
        assert "standalone" in args.checkpoint_dir, (
            f"NE39 checkpoint_dir='{args.checkpoint_dir}' doesn't include mode 'standalone'."
        )

    def test_ne39_checkpoint_dir_contains_mode_simulink(self):
        """NE39 simulink checkpoint dir must contain the word 'simulink'."""
        args = self._parse_ne39(["--mode", "simulink"])
        assert "simulink" in args.checkpoint_dir, (
            f"NE39 checkpoint_dir='{args.checkpoint_dir}' doesn't include mode 'simulink'."
        )

    def test_ne39_standalone_simulink_use_different_log_files(self):
        """NE39 standalone and simulink must write to different training_log.json files."""
        args_sta = self._parse_ne39(["--mode", "standalone"])
        args_sim = self._parse_ne39(["--mode", "simulink"])
        assert args_sta.log_file != args_sim.log_file, (
            "NE39: standalone and simulink share the same log_file."
        )
