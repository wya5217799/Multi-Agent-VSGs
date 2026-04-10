# engine/simulink_bridge.py
"""Layer 3a: SimulinkBridge — RL training co-simulation interface.

Wraps vsg_step_and_read.m into a clean step()/reset()/close() API
for use by KundurSimulinkEnv and NE39BusSimulinkEnv.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from engine.exceptions import MatlabCallError, SimulinkError
from engine.matlab_session import MatlabSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level bridge registry — lets MCP tools observe active training state
# without coupling the MCP server to the env object.
# ---------------------------------------------------------------------------
_bridge_registry: dict[str, "SimulinkBridge"] = {}


def register_bridge(bridge: "SimulinkBridge") -> None:
    """Register a bridge so MCP tools can query its runtime state."""
    _bridge_registry[bridge.cfg.model_name] = bridge


def get_active_bridge(model_name: str) -> "SimulinkBridge | None":
    """Return the most-recently-constructed bridge for model_name, or None."""
    return _bridge_registry.get(model_name)


def list_active_bridges() -> list[str]:
    """Return all model names with a registered bridge."""
    return list(_bridge_registry.keys())


@dataclass(frozen=True)
class BridgeConfig:
    """Scenario-specific Simulink bridge configuration.

    Template strings use {model} and {idx} placeholders that get
    substituted by vsg_step_and_read.m at runtime.
    """

    model_name: str        # 'kundur_vsg' or 'NE39bus_v2'
    model_dir: str         # absolute path to directory containing .slx
    n_agents: int          # 4 (Kundur) or 8 (NE39)
    dt_control: float      # 0.2s
    sbase_va: float        # 100e6 (system base in VA)
    m_path_template: str   # '{model}/VSG_ES{idx}/M0'
    d_path_template: str   # '{model}/VSG_ES{idx}/D0'
    omega_signal: str      # 'omega_ES{idx}'
    vabc_signal: str       # 'Vabc_ES{idx}'
    iabc_signal: str       # 'Iabc_ES{idx}'
    pe_path_template: str = ''      # '{model}/Pe_{idx}' — P_e feedback constant (optional, leave empty if model is direct-wired)
    src_path_template: str = ''     # '{model}/VSrc_ES{idx}' — source block (optional)
    vsg_sn_va: float = 200e6        # VSG rated power in VA for Pe base conversion
    delta_signal: str = 'delta_ES{idx}'  # rotor angle ToWorkspace signal template
    p_out_signal: str = ''          # 'P_out_ES{idx}' — Power Sensor ToWorkspace (W); if set, Pe read from here instead of V×I
    # Workspace variable names referenced by M0/D0 Constant blocks (setVariable approach)
    m_var_template: str = 'M0_val_ES{idx}'   # must match Constant block Value field in .slx
    d_var_template: str = 'D0_val_ES{idx}'
    m0_default: float = 12.0                  # nominal M (used to init workspace before first compile)
    d0_default: float = 3.0                   # nominal D
    # Workspace variable names for disturbance loads (no topology change)
    tripload1_p_var: str = 'TripLoad1_P'     # TripLoad_1 rated power (W), Bus14, default=248 MW
    tripload2_p_var: str = 'TripLoad2_P'     # TripLoad_2 rated power (W), Bus15
    tripload1_p_default: float = 248e6       # initial load (W) — Bus14 248 MW (breaker closed)
    tripload2_p_default: float = 1.0         # initial load (W) — Bus15 default; scenario may override to rated MW
    breaker_step_block_template: str = ''    # '{model}/BrkCtrl_{idx}' (optional Step block path)
    breaker_count: int = 0                   # number of disturbance breaker controls


class SimulinkBridge:
    """High-level interface for RL training with Simulink models.

    Wraps vsg_step_and_read.m to provide step()/reset()/close():
    - One IPC call per control step (batches N-agent param sets)
    - Manages simulation time and final state across steps
    - Handles numpy <-> matlab.double conversion
    """

    def __init__(self, config: BridgeConfig, session_id: str = "default"):
        self.cfg = config
        self.session = MatlabSession.get(session_id)
        self.t_current: float = 0.0
        self._matlab_cfg: Any = None
        self.__mdbl = None
        self._model_loaded: bool = False  # guard: load_model() runs only once
        # Per-step feedback state (NE39 phase-angle + Pe loop)
        self._delta_prev_deg: np.ndarray | None = None  # degrees
        self._Pe_prev: np.ndarray | None = None         # p.u. on sbase
        # Disturbance load state (workspace variables, no topology change)
        self._tripload_state: dict = {
            config.tripload1_p_var: config.tripload1_p_default,
            config.tripload2_p_var: config.tripload2_p_default,
        }
        self._breaker_events: dict[int, dict[str, float]] = {}
        for idx in range(1, config.breaker_count + 1):
            # Default all breakers to open (before=0, after=0).
            # Scene-specific initial states must be set by the env via
            # configure_breaker_event() before the first warmup().
            self._breaker_events[idx] = {"time_s": 100.0, "before": 0.0, "after": 0.0}

        # FR optimisation: track whether the model has been compiled at least once.
        # warmup() passes do_recompile=True on the first call (FastRestart off→on),
        # and do_recompile=False on all subsequent calls — skipping the ~10-12 s
        # Simscape recompile that was previously paid on every episode reset.
        self._fr_compiled: bool = False

        # Register so MCP tools (simulink_bridge_status) can observe training state.
        register_bridge(self)

    @property
    def _matlab_double(self):
        """Lazy import of matlab.double (avoids importing matlab at module load)."""
        if self.__mdbl is None:
            import matlab  # type: ignore
            self.__mdbl = matlab.double
        return self.__mdbl

    def load_model(self) -> None:
        """Load .slx model and build MATLAB-side config struct.

        Idempotent: subsequent calls are no-ops once the model is loaded.
        This avoids repeated load_system + cfg rebuild overhead each episode.
        """
        if self._model_loaded:
            return
        self.session.call("cd", self.cfg.model_dir, nargout=0)
        self.session.call("load_system", self.cfg.model_name, nargout=0)
        self._matlab_cfg = self._build_matlab_cfg()
        self._model_loaded = True
        logger.info("Loaded Simulink model: %s", self.cfg.model_name)

    def _build_matlab_cfg(self) -> Any:
        """Build a MATLAB struct from BridgeConfig via vsg_build_bridge_config.

        Replaces the fragile string-eval pattern with a typed MATLAB function
        call.  Field name mismatches cause an immediate MATLAB error instead of
        silently using wrong defaults.
        """
        return self.session.call(
            "vsg_build_bridge_config",
            self.cfg.m_path_template,
            self.cfg.d_path_template,
            self.cfg.omega_signal,
            self.cfg.vabc_signal,
            self.cfg.iabc_signal,
            self.cfg.pe_path_template,
            self.cfg.src_path_template,
            float(self.cfg.vsg_sn_va),
            self.cfg.delta_signal,
            self.cfg.p_out_signal,
            self.cfg.m_var_template,
            self.cfg.d_var_template,
            nargout=1,
        )

    def step(self, M: np.ndarray, D: np.ndarray) -> dict:
        """One control step: set params -> simulate -> read state.

        Args:
            M: shape (n_agents,) — target inertia values (physical units)
            D: shape (n_agents,) — target damping values (physical units)

        Returns:
            {'omega': np.ndarray, 'Pe': np.ndarray, 'rocof': np.ndarray,
             'delta': np.ndarray}
            Each array has shape (n_agents,).

        Raises:
            SimulinkError: if simulation diverges or fails.
        """
        mdbl = self._matlab_double  # lazy import

        t_stop = self.t_current + self.cfg.dt_control
        agent_ids = mdbl(list(range(1, self.cfg.n_agents + 1)))

        pe_arg    = mdbl(self._Pe_prev.tolist()) if self._Pe_prev is not None else mdbl([])
        delta_arg = mdbl(self._delta_prev_deg.tolist()) if self._delta_prev_deg is not None else mdbl([])

        # New 2-return signature: (model, agent_ids, M, D, t_stop, sbase, cfg, Pe_prev, delta_prev_deg)
        state, status = self.session.call(
            "vsg_step_and_read",
            self.cfg.model_name,
            agent_ids,
            mdbl(M.tolist()),
            mdbl(D.tolist()),
            float(t_stop),
            float(self.cfg.sbase_va),
            self._matlab_cfg,
            pe_arg,
            delta_arg,
            nargout=2,
        )

        if not status["success"]:
            t_start = self.t_current
            raise SimulinkError(
                f"Simulation failed at t={t_start:.3f}: {status['error']}"
            )

        self.t_current = t_stop

        result = {
            "omega":     np.array(state["omega"]).flatten(),
            "Pe":        np.array(state["Pe"]).flatten(),
            "rocof":     np.array(state["rocof"]).flatten(),
            "delta":     np.array(state["delta"]).flatten(),
            "delta_deg": np.array(state["delta_deg"]).flatten(),
        }

        # Store for next step's feedback.
        # Clip delta_deg to ±90°: VSG synchronisation limit; beyond that the
        # machine has slipped a pole and raw delta would drive phAng into a
        # nonphysical regime.
        # Clip Pe to [0, 5] p.u. on sbase: prevents transient measurement
        # artefacts from being fed back as extreme torque.  Kundur generators
        # run at ~3.75 sbase p.u. each (375 MW / 100 MVA), so the old 2.0
        # ceiling truncated valid readings.
        self._Pe_prev        = np.clip(result["Pe"].copy(), 0.0, 5.0)
        self._delta_prev_deg = np.clip(result["delta_deg"].copy(), -90.0, 90.0)

        return result

    def warmup(self, duration: float = 0.01) -> None:
        """Compile model (if needed) and run a brief FastRestart warmup.

        FastRestart keeps the compiled model and Simscape physical state in
        MATLAB memory.  Calling warmup again at the start of each episode
        resets state to model initial conditions (because StartTime=0 differs
        from the last stop time).

        Workspace variables for M/D Constant blocks are initialised here so
        the model can compile without "Undefined variable" errors.  Actual
        per-step values are overridden by setVariable inside vsg_step_and_read.

        Also initialises Pe/phAng/wref feedback variables and seeds
        ``_Pe_prev`` / ``_delta_prev_deg`` so the first RL step sends valid
        feedback to vsg_step_and_read.m (fixes max_power_swing=0 symptom).
        """
        # Constant blocks reference workspace variables by name (e.g. 'M0_val_ES1').
        # These must exist in the base workspace before the model is first compiled.
        #
        # Pe/phAng/wref feedback vars: without these, vsg_step_and_read skips
        # the Pe writeback (``if ~isempty(Pe_prev)`` → false) and the electrical
        # power never responds to M/D changes.  NE39's 5-arg warmup sets these
        # in MATLAB; the Kundur 3-arg path must do it here in Python.
        pe_nominal_vsg = 0.5   # VSG base p.u. — safe initial for any scenario
        for i in range(1, self.cfg.n_agents + 1):
            m_var = self.cfg.m_var_template.replace('{idx}', str(i))
            d_var = self.cfg.d_var_template.replace('{idx}', str(i))
            self.session.eval(
                f"assignin('base', '{m_var}', {self.cfg.m0_default})", nargout=0
            )
            self.session.eval(
                f"assignin('base', '{d_var}', {self.cfg.d0_default})", nargout=0
            )
            self.session.eval(
                f"assignin('base', 'Pe_ES{i}', {pe_nominal_vsg})", nargout=0
            )
            self.session.eval(
                f"assignin('base', 'phAng_ES{i}', 0.0)", nargout=0
            )
            self.session.eval(
                f"assignin('base', 'wref_{i}', 1.0)", nargout=0
            )
        # Disturbance loads: use CURRENT _tripload_state (set by caller before warmup).
        # TripLoad_1/2 P values are Simscape physical params — only tunable at compile time.
        # Caller (e.g. KundurSimulinkEnv._reset_backend) must set _tripload_state BEFORE
        # calling warmup(), so the values are baked in when FastRestart recompiles.
        for var, val in self._tripload_state.items():
            self.session.eval(f"assignin('base', '{var}', {val})", nargout=0)
        self._apply_breaker_events()
        do_recompile = not self._fr_compiled
        self.session.call("vsg_warmup", self.cfg.model_name, duration, do_recompile, nargout=0)
        self._fr_compiled = True
        self.t_current = duration

        # Seed feedback state so the first RL step has valid Pe/delta args.
        # pe_scale converts sbase p.u. → VSG base p.u.; invert to get sbase.
        pe_scale = self.cfg.sbase_va / self.cfg.vsg_sn_va
        self._Pe_prev = np.full(self.cfg.n_agents, pe_nominal_vsg / pe_scale)
        self._delta_prev_deg = np.zeros(self.cfg.n_agents)

        logger.debug("Warmup complete: t=%.4f s (recompile=%s)", duration, do_recompile)

    def _apply_breaker_events(self) -> None:
        if not self.cfg.breaker_step_block_template:
            return
        for idx, evt in self._breaker_events.items():
            block_path = self.cfg.breaker_step_block_template.format(
                model=self.cfg.model_name,
                idx=idx,
            )
            self.session.eval(
                "set_param('{block}', 'Time', '{time:.6f}', 'Before', '{before:.6f}', 'After', '{after:.6f}')".format(
                    block=block_path,
                    time=evt["time_s"],
                    before=evt["before"],
                    after=evt["after"],
                ),
                nargout=0,
            )

    def configure_breaker_event(
        self,
        breaker_idx: int,
        *,
        time_s: float,
        before: float,
        after: float,
    ) -> None:
        """Configure a disturbance breaker Step block for the next warmup/reset."""
        self._breaker_events[breaker_idx] = {
            "time_s": float(time_s),
            "before": float(before),
            "after": float(after),
        }

    def set_disturbance_load(self, var_name: str, value_w: float) -> None:
        """Set a TripLoad workspace variable (W).  Takes effect on next step().

        Args:
            var_name:  e.g. cfg.tripload1_p_var ('TripLoad1_P')
            value_w:   power in Watts (0 = load disconnected)
        """
        self._tripload_state[var_name] = value_w

    def apply_disturbance_load(self, var_name: str, value_w: float) -> None:
        """Immediately push load workspace variable to MATLAB base workspace.

        Unlike set_disturbance_load (which only updates the Python dict),
        this also calls assignin so the value is visible to Simulink on the
        very next FastRestart sim() call — enabling mid-episode disturbances
        without any topology change.

        Args:
            var_name:  e.g. cfg.tripload1_p_var ('TripLoad1_P')
            value_w:   per-phase power in Watts (0 = load off)
        """
        self._tripload_state[var_name] = value_w
        self.session.eval(
            f"assignin('base', '{var_name}', {value_w:.6g})", nargout=0
        )

    def reset_episode(self, duration: float = 0.01) -> None:
        """Reset Python counters and run FastRestart warmup in one atomic call.

        Replaces the reset() + warmup(duration) two-step pattern that callers
        must invoke in the correct order.  Use this in env._reset_backend().
        """
        self.reset()
        self.warmup(duration)

    def reset(self) -> None:
        """Reset Python-side counters.  Physical state is reset by warmup()
        which runs vsg_warmup with StartTime=0 — FastRestart detects the
        time discontinuity and resets Simscape state to model initial conditions.
        """
        self.t_current       = 0.0
        self._Pe_prev        = None
        self._delta_prev_deg = None

    def close(self) -> None:
        """Close the Simulink model (keep MATLAB engine alive).

        Resets _model_loaded and _fr_compiled so that if this instance is
        reused after close() (e.g. eval loops, error recovery), the next
        warmup() correctly triggers a full recompile on an uncompiled model.
        """
        try:
            self.session.call("vsg_close_model", self.cfg.model_name, nargout=0)
        except MatlabCallError:
            pass  # model may already be closed
        self._model_loaded = False
        self._fr_compiled  = False
