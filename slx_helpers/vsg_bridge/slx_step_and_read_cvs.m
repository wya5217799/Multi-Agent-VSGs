function [state, status] = slx_step_and_read_cvs( ...
    model_name, agent_ids, M_values, D_values, ...
    t_stop, sbase_va, cfg, Pe_prev, delta_prev_deg) %#ok<INUSD>
%SLX_STEP_AND_READ_CVS  Set M/D + advance sim + read state for the CVS Phasor path.
%
%   Same Python-facing signature as slx_step_and_read.m, but tailored to the
%   Kundur CVS Phasor model (build_kundur_cvs.m → kundur_cvs.slx). Two key
%   differences vs the NE39/legacy path:
%
%     1. The CVS swing equation is closed *inside* the .slx (cosD/sinD/RI2C
%        feeding driven Controlled Voltage Sources — see cvs_design.md H1-H6).
%        Therefore Pe_prev and delta_prev_deg are IGNORED; there is no phAng
%        feedback path to drive.
%     2. The .slx logs omega_ts_<i> / delta_ts_<i> / Pe_ts_<i> as Timeseries
%        via "To Workspace" blocks. NE39/legacy's slx_extract_state reads
%        omega_ES_<i> / Vabc_ES_<i> / Iabc_ES_<i> and would not work here.
%
%   This function is dispatched ONLY when BridgeConfig.step_strategy ==
%   "cvs_signal" (G3-prep-B). The default "phang_feedback" path keeps using
%   slx_step_and_read.m verbatim. Do NOT call from NE39 or legacy Kundur.
%
%   Variable names hard-coded for the CVS .slx (NOT NE39/legacy compatible):
%     M_<i>, D_<i> are addressed via cfg.m_var_template / cfg.d_var_template
%     so that profile-driven naming stays consistent with the bridge config.
%
%   Arguments (signature match with slx_step_and_read.m):
%     model_name        - 'kundur_cvs' (CVS .slx model name)
%     agent_ids         - Vector of VSG indices, e.g. 1:4
%     M_values(N)       - Per-VSG inertia (s)
%     D_values(N)       - Per-VSG damping
%     t_stop            - Absolute stop time for this step (s)
%     sbase_va          - System base power (VA) — informational only here
%     cfg               - Bridge config struct (uses .m_var_template,
%                         .d_var_template; other fields ignored)
%     Pe_prev(N)        - IGNORED (CVS has no Pe writeback path)
%     delta_prev_deg(N) - IGNORED (CVS has no phAng feedback)
%
%   Returns (schema bit-compatible with slx_step_and_read):
%     state.omega(N)     - per-agent ω at t_stop (pu)
%     state.Pe(N)        - per-agent Pe at t_stop (pu, system base)
%     state.rocof(N)     - per-agent ROCOF at t_stop (pu/s)
%     state.delta(N)     - per-agent rotor angle at t_stop (rad)
%     state.delta_deg(N) - per-agent rotor angle at t_stop (deg)
%     status.success     - boolean
%     status.error       - error string (empty if success)
%     status.elapsed_ms  - wall clock (ms)

    status.success = true;
    status.error   = '';
    status.measurement_failures = {};
    tic;
    N = length(agent_ids);

    % --- Phase 1: Update per-VSG M, D workspace variables ---
    %
    % Pe_prev and delta_prev_deg are intentionally NOT consumed (no phAng
    % feedback in the CVS path; swing-eq is closed inside the .slx).
    vars = struct();
    for i = 1:N
        idx = agent_ids(i);
        m_var = strrep(cfg.m_var_template, '{idx}', num2str(idx));
        d_var = strrep(cfg.d_var_template, '{idx}', num2str(idx));
        vars.(m_var) = double(M_values(i));
        vars.(d_var) = double(D_values(i));
    end
    ws_result = slx_workspace_set(vars);
    if ~ws_result.ok
        status.success    = false;
        status.error      = ['Workspace write failed: ' ws_result.error_message];
        state             = step_cvs_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % --- Phase 2: Advance sim ---
    try
        set_param(model_name, 'StopTime', num2str(t_stop, '%.6f'));
        simOut = sim(model_name);
    catch ME
        status.success    = false;
        status.error      = ME.message;
        state             = step_cvs_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % --- Phase 3: Read CVS Timeseries loggers ---
    state = step_cvs_extract_state(simOut, agent_ids);
    status.elapsed_ms = toc * 1000;
end


% -----------------------------------------------------------------------
% Private helpers (must NOT start with underscore in MATLAB)
% -----------------------------------------------------------------------

function state = step_cvs_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
end


function state = step_cvs_extract_state(simOut, agent_ids)
    N = length(agent_ids);
    state = step_cvs_empty_state(N);
    for i = 1:N
        idx = agent_ids(i);
        omega_ts = simOut.get(sprintf('omega_ts_%d', idx));
        delta_ts = simOut.get(sprintf('delta_ts_%d', idx));
        pe_ts    = simOut.get(sprintf('Pe_ts_%d',    idx));
        if isempty(omega_ts) || isempty(delta_ts) || isempty(pe_ts)
            continue;
        end
        omega_data = double(omega_ts.Data);
        delta_data = double(delta_ts.Data);
        pe_data    = double(pe_ts.Data);
        omega_t    = double(omega_ts.Time);
        state.omega(i)     = omega_data(end);
        state.delta(i)     = delta_data(end);
        state.delta_deg(i) = delta_data(end) * 180 / pi;
        state.Pe(i)        = pe_data(end);
        if numel(omega_t) >= 2
            dt = omega_t(end) - omega_t(end-1);
            if dt > 0
                state.rocof(i) = (omega_data(end) - omega_data(end-1)) / dt;
            end
        end
    end
end
