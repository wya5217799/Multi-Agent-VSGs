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

    if nargin < 6, do_recompile = true; end

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

    % --- Phase 0 (G3-prep-E A3): Load build-time runtime constants from sidecar ---
    %
    % build_kundur_cvs.m saves non-tunable scalars (wn_const, Vbase_const,
    % Sbase_const, Pe_scale, L_v_H / L_tie_H / L_inf_H, R_loadA / R_loadB,
    % Vmag_<i>) to kundur_cvs_runtime.mat alongside the .slx. These are
    % referenced by the .slx Constant blocks and Inductance / Resistance
    % parameters and consumed at compile-time. They do not change between
    % episodes, so we only need to (re)load on do_recompile=true (cold start
    % or after a sim crash forced a recompile).
    if logical(do_recompile)
        runtime_mat = fullfile(fileparts(which(model_name)), 'kundur_cvs_runtime.mat');
        if exist(runtime_mat, 'file') == 2
            consts = load(runtime_mat);
            const_fns = fieldnames(consts);
            for k = 1:numel(const_fns)
                assignin('base', const_fns{k}, consts.(const_fns{k}));
            end
        else
            status.success    = false;
            status.error      = sprintf( ...
                ['CVS runtime sidecar missing at %s. ' ...
                 'Run build_kundur_cvs.m to regenerate.'], runtime_mat);
            state             = warmup_cvs_empty_state(N);
            status.elapsed_ms = toc * 1000;
            return;
        end
    end

    % --- Phase 1a: FastRestart-aware runtime reset ---
    %
    % Pattern matches slx_episode_warmup.m (legacy/NE39 path). The CVS .slx
    % logs Timeseries via "To Workspace" blocks named omega_ts_<i> /
    % delta_ts_<i> / Pe_ts_<i>; these accumulate base-ws variables across
    % episodes and must be cleared between resets.
    %
    %   do_recompile=true  (first episode, or after a sim crash):
    %     Force FR off (clear SDI + ts vars), then re-enable FR before sim.
    %     This pays the one-time compile + Phasor steady-state init.
    %
    %   do_recompile=false (subsequent episodes):
    %     Keep FR on; only clear SDI + ts vars. The warmup sim() below
    %     restarts from t=0 automatically because the new StopTime
    %     (= t_warmup) is < the previous final sim time. No recompile.
    if logical(do_recompile)
        slx_runtime_reset(model_name, 'off', true, '^(omega|delta|Pe)_ts_\d+$');
        % --- Phase 1a-bis: idempotent ToWorkspace cap patch ---
        %
        % Newer build_kundur_cvs.m sets LimitDataPoints='on' / MaxDataPoints='2'
        % on the W_omega_<i> / W_delta_<i> / W_Pe_<i> blocks at build time so
        % the Timeseries IPC return stays O(1) regardless of t_stop. For .slx
        % files built before that change, patch them here under FR=off so the
        % structural change is safe. set_param is no-op if the value already
        % matches, so this is idempotent and cheap.
        for k = 1:N
            idx = agent_ids(k);
            for prefix = {'W_omega_', 'W_delta_', 'W_Pe_'}
                blk = [model_name '/' prefix{1} num2str(idx)];
                try
                    set_param(blk, 'LimitDataPoints', 'on', 'MaxDataPoints', '2');
                catch
                    % Block missing or model doesn't expose params: skip silently.
                    % Failure here means an old or non-CVS .slx; warmup will
                    % then surface that via the Phase 2 sim() error path.
                end
            end
        end
    else
        slx_runtime_reset(model_name, '',    true, '^(omega|delta|Pe)_ts_\d+$');
    end

    % --- Phase 1b: Reset workspace state for the CVS .slx ---
    %
    % cfg.m_var_template / cfg.d_var_template come from the CVS profile
    % (BridgeConfig fields already exist). The remaining per-VSG CVS variable
    % names are hard-coded here (Pm_<i>, delta0_<i>, Pm_step_t_<i>,
    % Pm_step_amp_<i>, optional Vmag_<i> override). Build-time scalars are
    % loaded by Phase 0 above; do not duplicate them here.
    %
    % All these vars feed Constant blocks (and one Integrator IC for
    % delta0_<i>); under FastRestart, Constant Value and Integrator IC are
    % both tunable parameters, so changes here propagate to the next sim()
    % without recompile.
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

    % --- Phase 1c: Enable FastRestart (only on do_recompile path) ---
    if logical(do_recompile)
        reset_result = slx_runtime_reset(model_name, 'on', false, '');
        if ~reset_result.ok
            status.success    = false;
            status.error      = ['FastRestart enable failed: ' reset_result.error_message];
            state             = warmup_cvs_empty_state(N);
            status.elapsed_ms = toc * 1000;
            return;
        end
    end

    % --- Phase 2: Run warmup sim ---
    %
    % build_kundur_cvs.m sets the model's StopTime to '0.5' at build time;
    % we override it here to t_warmup. With FR on, this restarts from t=0
    % automatically when StopTime < prev final sim time (subsequent eps).
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
