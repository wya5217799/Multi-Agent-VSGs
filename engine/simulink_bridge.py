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

# step_strategy: how a single RL control step drives the .slx model.
#   "phang_feedback" — current default for all in-tree callers (NE39 +
#                      legacy Kundur). step() writes M_i / D_i workspace
#                      values, calls slx_step_and_read.m, optionally
#                      injects phAng feedback (NE39 only).
#   "cvs_signal"     — reserved for the Kundur CVS path (G3-prep-C). The
#                      CVS model has no phAng feedback; the swing-eq is
#                      already closed inside the .slx via cosD/sinD/RI2C.
#                      This value is currently ACCEPTED at construction
#                      time and stored on the config but NOT yet dispatched
#                      by step() — actual dispatch is added in G3-prep-C.
STEP_STRATEGY_MODES = ("phang_feedback", "cvs_signal")


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
    pe_vi_scale: float = 1.0        # V×I Pe scaling: 1.0 for RMS phasors, 0.5 for SPS peak phasors
    # Phase-angle feedback (NE39 only)
    phase_command_mode: str = 'passthrough'  # 'passthrough' (Kundur) or 'absolute_with_loadflow' (NE39)
    init_phang: tuple[float, ...] = ()       # load-flow initial phase angles (deg); NE39: 8-element vector
    # Rotor angle ICs for 5/6-arg warmup seeding (Kundur only)
    # Empty tuple → 3-arg warmup (phAng=0); non-empty → 6-arg warmup seeded with delta0_deg
    delta0_deg: tuple[float, ...] = ()
    phase_feedback_gain: float = 1.0         # feedback gain; NE39 uses 0.3 to avoid step-induced oscillations
    # Workspace variable names referenced by Constant blocks (assignin approach)
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
    # G3-prep-B (additive): how a single step drives the .slx.
    #   Default "phang_feedback" reproduces the pre-B behaviour for every
    #   existing caller (NE39, legacy Kundur). "cvs_signal" is reserved
    #   for the Kundur CVS profile; dispatch wiring lands in G3-prep-C.
    step_strategy: str = "phang_feedback"
    # FastRestart opt-in flag.
    #   When True, the bridge calls set_param(<model>, 'FastRestart', 'on')
    #   on the loaded model after load_system so all subsequent warmup()
    #   calls skip the model-init phase.  Validated for v3 Discrete
    #   (microtest 2026-05-03, physics rel err 2.46e-08, 35% wall savings);
    #   not yet validated for v3 Phasor or v2.  Production training paths
    #   inherit the safe default (False).
    fast_restart: bool = False

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

        # G3-prep-B: validate step_strategy enum
        if self.step_strategy not in STEP_STRATEGY_MODES:
            errors.append(
                f"step_strategy={self.step_strategy!r} not in "
                f"{STEP_STRATEGY_MODES}"
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

        # delta0_deg: when non-empty must match n_agents and be all-finite
        if self.delta0_deg:
            if len(self.delta0_deg) != self.n_agents:
                errors.append(
                    f"delta0_deg: expected length {self.n_agents} (n_agents), "
                    f"got {len(self.delta0_deg)}"
                )
            else:
                arr = np.asarray(self.delta0_deg, dtype=np.float64)
                if not np.isfinite(arr).all():
                    errors.append(
                        f"delta0_deg: all values must be finite, got {list(self.delta0_deg)}"
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
        self.session.add_vsg_bridge_path()
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
        # FR integration disabled 2026-05-03 EOD: probe Phase 4 with cfg.fast_restart=True
        # measured 28% wall regression (alpha 36 min vs FR run 46 min). Microtest's
        # 35% per-sim speedup did not translate to integrated env.reset+warmup loop.
        # Suspected interaction with the existing _fr_compiled / slx_episode_warmup_cvs
        # FR cycling state machine — proper integration deferred to Option C refactor
        # (single source of truth for FR state). cfg.fast_restart kept as opt-in flag
        # but currently a no-op; CLI / env / probe wiring kept for future.
        # self._apply_fast_restart()  # ← reverted; Option A per debugger 2026-05-03
        self._matlab_cfg = self._build_matlab_cfg()
        self._model_loaded = True
        logger.info("Loaded Simulink model: %s", self.cfg.model_name)

    def _apply_fast_restart(self) -> None:
        """Set FastRestart='on' on the loaded model if cfg.fast_restart is True.

        No-op when cfg.fast_restart is False (production default).  Must be
        called after load_system and before the first sim() / warmup().

        STATUS 2026-05-03 EOD: this method is currently UNUSED — the call site
        in load_model() was reverted after measuring a 28% wall regression in
        integrated probe Phase 4 (alpha 36 min vs FR run 46 min). The microtest
        passed (1e-9 physics rel err, 35% per-sim speedup) but the speedup did
        not translate to the env.reset → warmup → multi-dispatch loop. Proper
        re-integration (Option C refactor) requires unifying this with the
        pre-existing _fr_compiled / slx_episode_warmup_cvs FR state machine.
        Method body kept for future use; do NOT remove.
        """
        if not self.cfg.fast_restart:
            return
        self.session.eval(
            f"set_param('{self.cfg.model_name}', 'FastRestart', 'on')",
            nargout=0,
        )
        logger.info(
            "FastRestart=on applied to %s (opt-in, v3 Discrete validated)",
            self.cfg.model_name,
        )

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
            float(self.cfg.pe_vi_scale),
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
        # G3-prep-C dispatch: cvs_signal routes to slx_step_and_read_cvs.m
        # (same Python-facing signature; CVS .m ignores Pe_prev/delta_prev_deg).
        # phang_feedback default keeps NE39 + legacy Kundur path bit-for-bit.
        step_fn = (
            "slx_step_and_read_cvs"
            if self.cfg.step_strategy == "cvs_signal"
            else "slx_step_and_read"
        )
        wall_t0 = time.perf_counter()
        state, status = self.session.call(
            step_fn,
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
        # G3-prep-C dispatch: cvs_signal takes a separate path that does NOT
        # touch the NE39/legacy 5/6-arg or 3-arg branches below. The CVS .slx
        # has its own base-ws variable scheme (M_<i>, D_<i>, Pm_<i>,
        # delta0_<i>, Vmag_<i>, Pm_step_*_<i>) and Timeseries loggers
        # (omega_ts_<i>, delta_ts_<i>, Pe_ts_<i>); slx_episode_warmup_cvs.m
        # handles all of it. The default phang_feedback path is unchanged.
        if self.cfg.step_strategy == "cvs_signal":
            self._warmup_cvs(duration)
            return

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
        do_recompile = not self._fr_compiled
        pe_scale = self.cfg.sbase_va / self.cfg.vsg_sn_va

        if self.cfg.delta0_deg:
            # 5/6-arg path: seeded warmup matching NE39 _reset_backend pattern.
            # slx_warmup sets M/D/phAng/Pe/wref workspace vars internally from kundur_ip.
            # Tripload and breaker vars still need Python-side setup before calling.
            delta0 = np.asarray(self.cfg.delta0_deg, dtype=np.float64)
            phang_str = ", ".join(f"{v:.4f}" for v in delta0)
            pe0_str = ", ".join(f"{v:.6f}" for v in pe_nominal_vsg_arr)
            mdbl = self._matlab_double
            agent_ids = mdbl(list(range(1, self.cfg.n_agents + 1)))

            for var, val in self._tripload_state.items():
                self.session.eval(f"assignin('base', '{var}', {val})", nargout=0)
            self._apply_breaker_events()

            self.session.eval(
                f"kundur_ip.M0 = {self.cfg.m0_default}; "
                f"kundur_ip.D0 = {self.cfg.d0_default}; "
                f"kundur_ip.phAng = [{phang_str}]; "
                f"kundur_ip.Pe0 = [{pe0_str}]; "
                f"kundur_ip.t_warmup = {duration};",
                nargout=0,
            )
            warmup_state, warmup_status = self.session.call(
                "slx_episode_warmup",
                self.cfg.model_name,
                agent_ids,
                float(self.cfg.sbase_va),
                self._matlab_cfg,
                self.session.eval("kundur_ip", nargout=1),
                bool(do_recompile),
                nargout=2,
            )
            if warmup_status is not None and not warmup_status.get("success", True):
                raise RuntimeError(
                    f"slx_episode_warmup failed: {warmup_status.get('error', 'unknown')}"
                )
            self._fr_compiled = True
            self.t_current = duration

            # Pe stays at nominal: warmup_extract_state lacks a feedback branch
            # and would read diverged Pe for the Kundur model.
            self._Pe_prev = pe_nominal_vsg_arr / pe_scale
            if warmup_state:
                raw_delta = np.array(
                    warmup_state.get("delta_deg", list(delta0))
                ).flatten()
                raw_omega = np.array(warmup_state.get("omega", [])).flatten()
                logger.debug(
                    "DIAG warmup_state raw delta_deg=%s omega=%s", raw_delta, raw_omega
                )
                self._delta_prev_deg = np.clip(raw_delta, -90.0, 90.0)
            else:
                raw_delta = np.asarray(delta0, dtype=np.float64)
                self._delta_prev_deg = np.clip(raw_delta, -90.0, 90.0)
        else:
            # 3-arg path (original): Python pre-initialises all workspace vars.
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
            self.session.call("slx_fastrestart_reset", self.cfg.model_name, duration, do_recompile, nargout=0)
            self._fr_compiled = True
            self.t_current = duration
            self._Pe_prev = pe_nominal_vsg_arr / pe_scale
            self._delta_prev_deg = np.zeros(self.cfg.n_agents)

        logger.debug(
            "Warmup complete: t=%.4f s (recompile=%s, delta_seeded=%s)",
            duration, do_recompile, bool(self.cfg.delta0_deg),
        )

    def _warmup_cvs(self, duration: float) -> None:
        """G3-prep-C: CVS-only warmup path. NE39 / legacy paths are NOT touched.

        Reads NR initial condition (delta0_rad, Pm0_pu) from
        ``cfg.pe0_default_vsg`` and ``cfg.delta0_deg``, which the active
        model profile populates at ``scenarios/kundur/config_simulink.py``
        from the profile-matching IC JSON (``kundur_ic_cvs.json`` for v2,
        ``kundur_ic_cvs_v3.json`` for v3 — see the if/elif/else block at
        lines 145-177 of that file). Profile dispatch is the single
        source-of-truth; this method MUST NOT re-read any IC JSON. Vmag
        is NOT pushed (build-time values in the .slx remain authoritative
        — see _cvs.m header note).

        Only invoked when ``cfg.step_strategy == "cvs_signal"``.
        """
        if not self.cfg.pe0_default_vsg or not self.cfg.delta0_deg:
            raise SimulinkError(
                "CVS warmup requires cfg.pe0_default_vsg and cfg.delta0_deg "
                "to be populated by the active model profile "
                "(see scenarios/kundur/config_simulink.py)"
            )
        if (
            len(self.cfg.pe0_default_vsg) != self.cfg.n_agents
            or len(self.cfg.delta0_deg) != self.cfg.n_agents
        ):
            raise SimulinkError(
                f"CVS IC has Pm0={len(self.cfg.pe0_default_vsg)} agents, "
                f"delta0={len(self.cfg.delta0_deg)} agents; bridge expects "
                f"{self.cfg.n_agents}"
            )
        pm0_pu     = list(self.cfg.pe0_default_vsg)
        delta0_rad = [float(d) * np.pi / 180.0 for d in self.cfg.delta0_deg]

        mdbl = self._matlab_double
        agent_ids = mdbl(list(range(1, self.cfg.n_agents + 1)))

        # Push tripload vars and breaker events for parity with phang_feedback
        # path's pre-warmup workspace setup, even if the CVS .slx ignores them.
        for var, val in self._tripload_state.items():
            self.session.eval(f"assignin('base', '{var}', {val})", nargout=0)
        self._apply_breaker_events()

        # init_params struct (CVS schema; see slx_episode_warmup_cvs.m header)
        delta_str = ", ".join(f"{v:.10f}" for v in delta0_rad)
        pm_str    = ", ".join(f"{v:.10f}" for v in pm0_pu)
        self.session.eval(
            f"kundur_cvs_ip.M0          = {self.cfg.m0_default}; "
            f"kundur_cvs_ip.D0          = {self.cfg.d0_default}; "
            f"kundur_cvs_ip.Pm0_pu      = [{pm_str}]; "
            f"kundur_cvs_ip.delta0_rad  = [{delta_str}]; "
            f"kundur_cvs_ip.Pm_step_t   = 5.0; "
            f"kundur_cvs_ip.Pm_step_amp = 0.0; "
            f"kundur_cvs_ip.t_warmup    = {duration};",
            nargout=0,
        )
        do_recompile = not self._fr_compiled
        warmup_state, warmup_status = self.session.call(
            "slx_episode_warmup_cvs",
            self.cfg.model_name,
            agent_ids,
            float(self.cfg.sbase_va),
            self._matlab_cfg,
            self.session.eval("kundur_cvs_ip", nargout=1),
            bool(do_recompile),
            nargout=2,
        )
        if warmup_status is not None and not warmup_status.get("success", True):
            raise SimulinkError(
                f"slx_episode_warmup_cvs failed: "
                f"{warmup_status.get('error', 'unknown')}"
            )

        self._fr_compiled = True
        self.t_current = duration

        # Seed feedback caches so step() has valid Pe_prev / delta_prev_deg
        # arrays even though the CVS .m ignores them. Use NR IC for delta and
        # the warmup-extracted Pe (or fall back to NR Pm if extraction failed).
        self._delta_prev_deg = np.asarray(
            [d * 180.0 / np.pi for d in delta0_rad], dtype=np.float64
        )
        if warmup_state and "Pe" in warmup_state:
            pe_arr = np.array(warmup_state["Pe"]).flatten()
            if pe_arr.size == self.cfg.n_agents:
                self._Pe_prev = pe_arr
        if self._Pe_prev is None:
            # M1 fix: Pm0 can be negative for absorbing-mode profiles
            # (v3 ESS group absorbs +185 MW surplus). _Pe_prev contract
            # is non-negative pu; clip to [0, 5] and warn if any entry
            # was negative so a contract violation surfaces rather than
            # silently propagating into downstream callers.
            pm0_arr = np.asarray(pm0_pu, dtype=np.float64)
            if np.any(pm0_arr < 0.0):
                logger.warning(
                    "_Pe_prev fallback: clipping negative Pm0 entries to 0 "
                    "(raw=%s)", pm0_arr.tolist()
                )
            self._Pe_prev = np.clip(pm0_arr, 0.0, 5.0)

        logger.debug(
            "CVS warmup complete: t=%.4f s (recompile=%s, Pe=%s, delta_deg=%s)",
            duration, do_recompile, self._Pe_prev, self._delta_prev_deg,
        )

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

    def apply_workspace_var(self, var_name: str, value: float) -> None:
        """Push a single scalar workspace variable to MATLAB base ws.

        Like apply_disturbance_load, but does NOT touch self._tripload_state
        (which is reserved for the SPS TripLoad batch-write semantics in
        warmup). Use for mid-episode disturbance vars referenced by .slx
        Constant blocks (e.g. CVS Pm_step_amp_<i>, Pm_step_t_<i>) that
        the warmup re-population loop must not own.

        Args:
            var_name: workspace variable name (no path qualifier)
            value:    scalar value, written as a double precision literal
        """
        self.session.eval(
            f"assignin('base', '{var_name}', {float(value):.6g})", nargout=0
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
