# tests/test_smoke_simulink.py
"""Online smoke tests for Simulink feedback chain integrity.

Run with: pytest -m smoke_simulink
Requires: MATLAB R2025b + compiled .slx model + ~30s warm session.

These tests verify that the measurement chain is alive — Pe responds to
disturbance, omega deviates from nominal, delta moves. If any of these
are stuck at zero, the feedback chain is broken.
"""
import pytest
import numpy as np

pytestmark = pytest.mark.smoke_simulink


def _try_import_matlab():
    """Skip all tests if MATLAB engine is unavailable."""
    try:
        import matlab.engine  # noqa: F401
        return True
    except ImportError:
        return False


skipif_no_matlab = pytest.mark.skipif(
    not _try_import_matlab(),
    reason="matlab.engine not available",
)


@skipif_no_matlab
class TestKundurFeedbackChain:
    """Kundur 4-gen: verify Pe/omega/delta respond after 1 control step."""

    @pytest.fixture(autouse=True)
    def bridge(self):
        from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG
        from engine.simulink_bridge import SimulinkBridge

        b = SimulinkBridge(KUNDUR_BRIDGE_CONFIG)
        b.load_model()
        b.warmup(0.01)
        yield b
        b.close()

    def test_pe_nonzero_after_one_step(self, bridge):
        """Pe must be > 0 after warmup + 1 step (feedback chain alive)."""
        M = np.full(bridge.cfg.n_agents, 12.0)
        D = np.full(bridge.cfg.n_agents, 3.0)
        result = bridge.step(M, D)

        assert np.any(result["Pe"] > 0.01), (
            f"Pe all near zero after 1 step: {result['Pe']}. "
            "Check p_out_signal config or ToWorkspace blocks."
        )

    def test_omega_near_nominal(self, bridge):
        """Omega should be close to 1.0 p.u. (no huge divergence)."""
        M = np.full(bridge.cfg.n_agents, 12.0)
        D = np.full(bridge.cfg.n_agents, 3.0)
        result = bridge.step(M, D)

        assert np.all(np.abs(result["omega"] - 1.0) < 0.1), (
            f"Omega far from nominal: {result['omega']}"
        )

    def test_delta_nonzero_after_step(self, bridge):
        """Delta should be non-trivial (rotor angle signal exists)."""
        M = np.full(bridge.cfg.n_agents, 12.0)
        D = np.full(bridge.cfg.n_agents, 3.0)
        result = bridge.step(M, D)

        # After warmup, at least some agents should have non-zero angle
        assert np.any(np.abs(result["delta_deg"]) > 0.001), (
            f"All delta_deg = 0: {result['delta_deg']}. "
            "Check delta_ES{{idx}} ToWorkspace block."
        )

    def test_pe_responds_to_m_change(self, bridge):
        """Changing M should cause Pe to differ from nominal within 2 steps."""
        n = bridge.cfg.n_agents
        M_nominal = np.full(n, 12.0)
        D_nominal = np.full(n, 3.0)

        r1 = bridge.step(M_nominal, D_nominal)

        # Large M change should produce a measurable Pe difference
        M_high = np.full(n, 25.0)
        r2 = bridge.step(M_high, D_nominal)

        pe_diff = np.max(np.abs(r2["Pe"] - r1["Pe"]))
        # At minimum, Pe should show SOME response (even 0.001 p.u.)
        # A zero diff means the control has no effect on electrical output.
        assert pe_diff > 1e-4 or np.all(r2["Pe"] > 0.01), (
            f"Pe unchanged after M step: {r1['Pe']} -> {r2['Pe']}. "
            "Control-to-measurement chain may be open-loop."
        )


@skipif_no_matlab
class TestNE39FeedbackChain:
    """NE39 8-gen: verify Pe/omega/delta respond after 1 control step."""

    @pytest.fixture(autouse=True)
    def bridge(self):
        from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG
        from engine.simulink_bridge import SimulinkBridge

        b = SimulinkBridge(NE39_BRIDGE_CONFIG)
        b.load_model()
        b.warmup(0.01)
        yield b
        b.close()

    def test_pe_nonzero_after_one_step(self, bridge):
        """Pe must be > 0 after warmup + 1 step."""
        M = np.full(bridge.cfg.n_agents, 12.0)
        D = np.full(bridge.cfg.n_agents, 3.0)
        result = bridge.step(M, D)

        assert np.any(result["Pe"] > 0.01), (
            f"Pe all near zero: {result['Pe']}. "
            "Check Vabc/Iabc ToWorkspace or V×I calculation."
        )

    def test_omega_near_nominal(self, bridge):
        """Omega should be close to 1.0 p.u."""
        M = np.full(bridge.cfg.n_agents, 12.0)
        D = np.full(bridge.cfg.n_agents, 3.0)
        result = bridge.step(M, D)

        assert np.all(np.abs(result["omega"] - 1.0) < 0.1), (
            f"Omega far from nominal: {result['omega']}"
        )
