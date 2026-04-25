function [state, status] = slx_episode_warmup_cvs( ...
    model_name, agent_ids, sbase_va, cfg, init_params, do_recompile)
%SLX_EPISODE_WARMUP_CVS  Episode reset + warmup for the Kundur CVS Phasor path.
%
%   [state, status] = slx_episode_warmup_cvs(model_name, agent_ids,
%       sbase_va, cfg, init_params)
%   [state, status] = slx_episode_warmup_cvs(model_name, agent_ids,
%       sbase_va, cfg, init_params, do_recompile)
%
%   Same Python-facing signature as slx_episode_warmup.m, but the init_params
%   schema is **CVS-specific** (no phAng feedback, no Pe seed; the swing
%   equation is closed inside the .slx via cosD/sinD/RI2C — see
%   docs/design/cvs_design.md and build_kundur_cvs.m).
%
%   This file is dispatched ONLY when BridgeConfig.step_strategy == "cvs_signal"
%   (G3-prep-B). The default "phang_feedback" path keeps using
%   slx_episode_warmup.m verbatim. Do NOT call this function from the NE39
%   or legacy Kundur path.
%
%   init_params fields (CVS semantics):
%     .M0          - scalar or N-vector (s)        — VSG inertia
%     .D0          - scalar or N-vector            — VSG damping
%     .Pm0_pu      - scalar or N-vector (pu, sys)  — mechanical power set-point
%     .delta0_rad  - N-vector (rad)                — initial rotor angle (NR IC)
%     .Vmag_volts  - (OPTIONAL) scalar or N-vector — terminal voltage magnitude
%                                                   in Volts (already scaled by
%                                                   Vbase). Omit to keep the
%                                                   build-time Vmag_<i> values.
%     .Pm_step_t   - scalar (s, default 5.0)       — disturbance step time
%     .Pm_step_amp - scalar or N-vector (pu, default 0)  — disturbance amplitude
%                                                   per VSG (0 = no step)
%     .t_warmup    - scalar (s, default 0.5)       — sim duration
%
%   cfg fields read (CVS path, all already on BridgeConfig):
%     .m_var_template  - 'M_{idx}'   (CVS profile sets this)
%     .d_var_template  - 'D_{idx}'
%     .n_agents (implicit via length(agent_ids))
%
%   Variable names hard-coded for the CVS .slx (NOT NE39/legacy compatible):
%     Pm_<i>, delta0_<i>, Vmag_<i>, Pm_step_t_<i>, Pm_step_amp_<i>
%
%   Returns (schema bit-compatible with slx_episode_warmup):
%     state.omega(N), state.Pe(N), state.rocof(N), state.delta(N), state.delta_deg(N)
%     status.success, status.error, status.elapsed_ms

    if nargin < 6, do_recompile = true; end %#ok<NASGU>  % CVS path: no FastRestart cache to flip

    status.success = true;
    status.error   = '';
    tic;
    model_name = char(model_name);
    N = length(agent_ids);

    if ~isfield(init_params, 't_warmup'),    init_params.t_warmup    = 0.5; end
    if ~isfield(init_params, 'Pm_step_t'),   init_params.Pm_step_t   = 5.0; end
    if ~isfield(init_params, 'Pm_step_amp'), init_params.Pm_step_amp = 0.0; end
    if isscalar(init_params.M0),          init_params.M0          = repmat(init_params.M0,          1, N); end
    if isscalar(init_params.D0),          init_params.D0          = repmat(init_params.D0,          1, N); end
    if isscalar(init_params.Pm0_pu),      init_params.Pm0_pu      = repmat(init_params.Pm0_pu,      1, N); end
    if isscalar(init_params.Pm_step_amp), init_params.Pm_step_amp = repmat(init_params.Pm_step_amp, 1, N); end
    has_vmag_override = isfield(init_params, 'Vmag_volts');
    if has_vmag_override && isscalar(init_params.Vmag_volts)
        init_params.Vmag_volts = repmat(init_params.Vmag_volts, 1, N);
    end

    % --- Phase 1: Reset workspace state for the CVS .slx ---
    %
    % cfg.m_var_template / cfg.d_var_template come from the CVS profile
    % (BridgeConfig fields already exist). The remaining CVS variable names
    % are hard-coded here (Pm_<i>, delta0_<i>, Vmag_<i>, Pm_step_t_<i>,
    % Pm_step_amp_<i>) because adding cfg fields was forbidden by the
    % G3-prep-C scope decision.
    % build_kundur_cvs.m wrote per-VSG Vmag_<i> (Volts), wn_const, Vbase_const,
    % Sbase_const, Pe_scale, L_v_H / L_tie_H / L_inf_H, R_loadA / R_loadB to
    % the base workspace at build time. We do NOT rewrite those here — the
    % build-time values are authoritative and bridge.warmup() must not depend
    % on them being re-pushed every episode.
    vars = struct();
    for i = 1:N
        idx = agent_ids(i);
        m_var = strrep(cfg.m_var_template, '{idx}', num2str(idx));
        d_var = strrep(cfg.d_var_template, '{idx}', num2str(idx));
        vars.(m_var) = double(init_params.M0(i));
        vars.(d_var) = double(init_params.D0(i));
        vars.(sprintf('Pm_%d',          idx)) = double(init_params.Pm0_pu(i));
        vars.(sprintf('delta0_%d',      idx)) = double(init_params.delta0_rad(i));
        vars.(sprintf('Pm_step_t_%d',   idx)) = double(init_params.Pm_step_t);
        vars.(sprintf('Pm_step_amp_%d', idx)) = double(init_params.Pm_step_amp(i));
        if has_vmag_override
            vars.(sprintf('Vmag_%d',    idx)) = double(init_params.Vmag_volts(i));
        end
    end

    ws_result = slx_workspace_set(vars);
    if ~ws_result.ok
        status.success    = false;
        status.error      = ['Workspace write failed: ' ws_result.error_message];
        state             = warmup_cvs_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % --- Phase 2: Run warmup sim ---
    %
    % CVS path uses powergui Phasor mode; no FastRestart cache flip needed.
    % build_kundur_cvs.m sets the model's StopTime to '0.5' at build time;
    % we override it here to t_warmup.
    try
        set_param(model_name, 'StopTime', num2str(init_params.t_warmup, '%.6f'));
        simOut = sim(model_name);
    catch ME
        status.success    = false;
        status.error      = ['Warmup sim failed: ' ME.message];
        state             = warmup_cvs_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % --- Phase 3: Extract state from CVS Timeseries loggers ---
    %
    % CVS .slx logs omega_ts_<i> / delta_ts_<i> / Pe_ts_<i> as Timeseries
    % via "To Workspace" blocks (see build_kundur_cvs.m). slx_extract_state
    % is NE39/legacy-specific (reads omega_ES_<i> / Vabc_ES_<i> / Iabc_ES_<i>)
    % and would not work here, so we read Timeseries directly.
    state = warmup_cvs_extract_state(simOut, agent_ids, sbase_va);
    status.measurement_failures = {};
    status.elapsed_ms = toc * 1000;
end


% -----------------------------------------------------------------------
% Private helpers (must NOT start with underscore in MATLAB)
% -----------------------------------------------------------------------

function state = warmup_cvs_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
end


function state = warmup_cvs_extract_state(simOut, agent_ids, sbase_va) %#ok<INUSD>
    N = length(agent_ids);
    state = warmup_cvs_empty_state(N);
    for i = 1:N
        idx = agent_ids(i);
        omega_ts = simOut.get(sprintf('omega_ts_%d', idx));
        delta_ts = simOut.get(sprintf('delta_ts_%d', idx));
        pe_ts    = simOut.get(sprintf('Pe_ts_%d',    idx));
        if isempty(omega_ts) || isempty(delta_ts) || isempty(pe_ts)
            continue;  % leave zeros, caller may treat as failure
        end
        omega_data = double(omega_ts.Data);
        delta_data = double(delta_ts.Data);
        pe_data    = double(pe_ts.Data);
        omega_t    = double(omega_ts.Time);
        % Last-sample values
        state.omega(i)     = omega_data(end);
        state.delta(i)     = delta_data(end);
        state.delta_deg(i) = delta_data(end) * 180 / pi;
        state.Pe(i)        = pe_data(end);
        % Backward-difference rocof on omega (per second)
        if numel(omega_t) >= 2
            dt = omega_t(end) - omega_t(end-1);
            if dt > 0
                state.rocof(i) = (omega_data(end) - omega_data(end-1)) / dt;
            end
        end
    end
end
