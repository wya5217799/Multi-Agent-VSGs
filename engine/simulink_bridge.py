# engine/simulink_bridge.py
"""Layer 3a: SimulinkBridge — RL training co-simulation interface.

Wraps slx_step_and_read.m into a clean step()/reset()/close() API
for use by KundurSimulinkEnv and NE39BusSimulinkEnv.

⚠️ 修改前先读 env/simulink/COMMON_NOTES.md + scenarios/{kundur,new_england}/NOTES.md
   （Bridge 是共享层，改动同时影响两个场景）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence

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


# Valid Pe measurement strategies:
#   "vi"             — V×I from Vabc/Iabc ToWorkspace (NE39)
#   "pout"           — P_out from swing equation ToWorkspace (debug only)
#   "vi_then_pout"   — try V×I first, fall back to P_out (legacy/transition)
#   "feedback"       — PeGain_ES{idx} ToWorkspace, true electrical Pe (Kundur main)
PE_MEASUREMENT_MODES = ("vi", "pout", "vi_then_pout", "feedback")


def _normalize_per_agent_vector(
    name: str, value: "float | Sequence[float]", n_agents: int
) -> np.ndarray:
    """Validate scalar or sequence; broadcast to shape (n_agents,)."""
    arr = np.atleast_1d(np.asarray(value, dtype=np.float64))
    if arr.size == 1:
        arr = np.full(n_agents, arr.item())
    if arr.shape != (n_agents,):
        raise ValueError(
            f"{name}: expected scalar or length-{n_agents} sequence, got {arr.shape}"
        )
    return arr


@dataclass(frozen=True)
class BridgeConfig:
    """Scenario-specific Simulink bridge configuration.

    Template strings use {model} and {idx} placeholders that get
    substituted by slx_step_and_read.m at runtime.
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
    p_out_signal: str = ''          # 'P_out_ES{idx}' — swing eq output ToWorkspace (debug only)
    pe_measurement: str = 'vi_then_pout'  # Pe strategy: "vi", "pout", "vi_then_pout", or "feedback"
    pe0_default_vsg: float | tuple = 0.5  # nominal Pe seed (VSG-base pu); scalar or per-agent sequence
    pe_feedback_signal: str = ''    # 'PeFb_ES{idx}' — PeGain_ES ToWorkspace (feedback mode only)
    # Phase-angle feedback (NE39 only)
    phase_command_mode: str = 'passthrough'  # 'passthrough' (Kundur) or 'absolute_with_loadflow' (NE39)
    init_phang: tuple[float, ...] = ()       # load-flow initial phase angles (deg); NE39: 8-element vector
    phase_feedback_gain: float = 1.0         # feedback gain; NE39 uses 0.3 to avoid step-induced oscillations
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

    def __post_init__(self) -> None:
        """Validate configuration at construction time.

        Catches missing/inconsistent fields that would otherwise cause
        silent measurement failures at runtime.
        """
        errors: list[str] = []

        # Pe measurement contract validation
        has_vi = bool(self.vabc_signal) and bool(self.iabc_signal)
        has_pout = bool(self.p_out_signal)

        if self.pe_measurement not in PE_MEASUREMENT_MODES:
            errors.append(
                f"pe_measurement={self.pe_measurement!r} not in "
                f"{PE_MEASUREMENT_MODES}"
            )
        elif self.pe_measurement == "vi" and not has_vi:
            errors.append(
                "pe_measurement='vi' but vabc_signal/iabc_signal not both set"
            )
        elif self.pe_measurement == "pout" and not has_pout:
            errors.append(
                "pe_measurement='pout' but p_out_signal is empty"
            )
        elif self.pe_measurement == "vi_then_pout" and not has_vi and not has_pout:
            errors.append(
                "pe_measurement='vi_then_pout' but neither V×I nor p_out_signal configured"
            )
        elif self.pe_measurement == "feedback" and not self.pe_feedback_signal:
            errors.append(
                "pe_measurement='feedback' but pe_feedback_signal is empty"
            )

        # Template placeholders must be present
        for field_name in ("omega_signal", "delta_signal", "m_var_template", "d_var_template"):
            val = getattr(self, field_name)
            if val and "{idx}" not in val:
                errors.append(f"{field_name}={val!r} missing '{{idx}}' placeholder")

        if self.n_agents < 1:
            errors.append(f"n_agents must be >= 1, got {self.n_agents}")

        if self.dt_control <= 0:
            errors.append(f"dt_control must be > 0, got {self.dt_control}")

        if errors:
            raise ValueError(
                f"BridgeConfig({self.model_name!r}) validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


class MeasurementFailureError(SimulinkError):
    """Raised when measurement signals are unavailable or stuck at zero.

    Carries structured failure details from slx_step_and_read.m so callers
    can distinguish transient glitches from persistent feedback chain breaks.
    """

    def __init__(self, message: str, failures: list[str]):
        super().__init__(message)
        self.failures = failures


# Maximum consecutive steps with all-zero Pe before raising.
# 3 steps = 0.6s at dt=0.2s — long enough to skip a transient glitch,
# short enough to catch a broken feedback chain within one episode.
_PE_ZERO_TOLERANCE_STEPS: int = 3

# Per-step wall-clock threshold (seconds).  If a single step exceeds this,
# log a warning.  Normal Kundur steps take ~5s; NE39 ~15s.  25s indicates
# solver struggling or model thrashing.
_STEP_SLOW_THRESHOLD_S: float = 25.0


class SimulinkBridge:
    """High-level interface for RL training with Simulink models.

    Wraps slx_step_and_read.m to provide step()/reset()/close():
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
        # Measurement health tracking
        self._pe_zero_count: int = 0
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
        """Build a MATLAB struct from BridgeConfig via slx_build_bridge_config.

        Replaces the fragile string-eval pattern with a typed MATLAB function
        call.  Field name mismatches cause an immediate MATLAB error instead of
        silently using wrong defaults.
        """
        mdbl = self._matlab_double
        return self.session.call(
            "slx_build_bridge_config",
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
            self.cfg.pe_measurement,
            self.cfg.phase_command_mode,
            mdbl(list(self.cfg.init_phang)),
            float(self.cfg.phase_feedback_gain),
            self.cfg.pe_feedback_signal,
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
        wall_t0 = time.perf_counter()
        state, status = self.session.call(
            "slx_step_and_read",
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
        wall_elapsed = time.perf_counter() - wall_t0

        if wall_elapsed > _STEP_SLOW_THRESHOLD_S:
            logger.warning(
                "Slow step at t=%.3f: %.1fs (threshold %.1fs). "
                "Solver may be struggling.",
                t_stop, wall_elapsed, _STEP_SLOW_THRESHOLD_S,
            )

        if not status["success"]:
            t_start = self.t_current
            # FastRestart solver state is corrupted after a sim() crash.
            # Force full recompile on the next episode reset so the corrupted
            # state is cleared (set_param FastRestart off→on).  Without this,
            # every subsequent warmup uses the fast path and all future steps
            # fail permanently — killing the training run.
            self._fr_compiled = False
            raise SimulinkError(
                f"Simulation failed at t={t_start:.3f}: {status['error']}"
            )

        # Surface measurement failures from MATLAB as structured data.
        meas_failures_raw = status.get("measurement_failures", [])
        # MATLAB returns cell array as list of strings (or empty list).
        meas_failures: list[str] = []
        if meas_failures_raw:
            if isinstance(meas_failures_raw, str):
                meas_failures = [meas_failures_raw]
            else:
                meas_failures = [str(f) for f in meas_failures_raw]
        if meas_failures:
            logger.warning(
                "Measurement failures at t=%.3f: %s",
                t_stop, "; ".join(meas_failures),
            )

        self.t_current = t_stop

        result = {
            "omega":     np.array(state["omega"]).flatten(),
            "Pe":        np.array(state["Pe"]).flatten(),
            "rocof":     np.array(state["rocof"]).flatten(),
            "delta":     np.array(state["delta"]).flatten(),
            "delta_deg": np.array(state["delta_deg"]).flatten(),
        }

        # --- Pe sanity check: detect broken feedback chain early ---
        # If ALL agents report Pe=0 for _PE_ZERO_TOLERANCE_STEPS consecutive
        # steps, the feedback chain is almost certainly broken (missing
        # ToWorkspace signal, wrong p_out_signal, etc.).
        if np.all(result["Pe"] == 0.0):
            self._pe_zero_count += 1
            if self._pe_zero_count >= _PE_ZERO_TOLERANCE_STEPS:
                # Note: sim() completed successfully (status["success"]=True above),
                # so the FastRestart compiled state is NOT corrupted — _fr_compiled
                # is intentionally left True here.  This contrasts with the sim-crash
                # path (status["success"]=False) where _fr_compiled is reset to False.
                raise MeasurementFailureError(
                    f"Pe=0 for all agents for {self._pe_zero_count} consecutive "
                    f"steps (t={self.t_current:.3f}s). Feedback chain is likely "
                    f"broken. Check p_out_signal config or ToWorkspace blocks.",
                    failures=meas_failures,
                )
        else:
            self._pe_zero_count = 0

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
        per-step values are overridden by setVariable inside slx_step_and_read.

        Also initialises Pe/phAng/wref feedback variables and seeds
        ``_Pe_prev`` / ``_delta_prev_deg`` so the first RL step sends valid
        feedback to slx_step_and_read.m (fixes max_power_swing=0 symptom).
        """
        # Constant blocks reference workspace variables by name (e.g. 'M0_val_ES1').
        # These must exist in the base workspace before the model is first compiled.
        #
        # Pe/phAng/wref feedback vars: without these, slx_step_and_read skips
        # the Pe writeback (``if ~isempty(Pe_prev)`` → false) and the electrical
        # power never responds to M/D changes.  NE39's 5-arg warmup sets these
        # in MATLAB; the Kundur 3-arg path must do it here in Python.
        pe_nominal_vsg_arr = _normalize_per_agent_vector(
            'pe0_default_vsg', self.cfg.pe0_default_vsg, self.cfg.n_agents
        )
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
                f"assignin('base', 'Pe_ES{i}', {pe_nominal_vsg_arr[i - 1]})", nargout=0
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
        self.session.call("slx_warmup", self.cfg.model_name, duration, do_recompile, nargout=0)
        self._fr_compiled = True
        self.t_current = duration

        # Seed feedback state so the first RL step has valid Pe/delta args.
        # pe_scale = sbase/vsg_sn = 0.5 for Kundur; dividing VSG-base by it gives sbase.
        pe_scale = self.cfg.sbase_va / self.cfg.vsg_sn_va
        self._Pe_prev = pe_nominal_vsg_arr / pe_scale
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
        which runs slx_warmup with StartTime=0 — FastRestart detects the
        time discontinuity and resets Simscape state to model initial conditions.
        """
        self.t_current       = 0.0
        self._Pe_prev        = None
        self._delta_prev_deg = None
        self._pe_zero_count  = 0

    def close(self) -> None:
        """Close the Simulink model (keep MATLAB engine alive).

        Resets _model_loaded and _fr_compiled so that if this instance is
        reused after close() (e.g. eval loops, error recovery), the next
        warmup() correctly triggers a full recompile on an uncompiled model.
        """
        try:
            self.session.call("slx_close_model", self.cfg.model_name, nargout=0)
        except MatlabCallError as exc:
            logger.warning(
                "Failed to close Simulink model %s cleanly: %s",
                self.cfg.model_name,
                exc,
            )
        self._model_loaded = False
        self._fr_compiled  = False
