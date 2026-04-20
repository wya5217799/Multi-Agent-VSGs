function [state, status] = slx_step_and_read( ...
    model_name, agent_ids, M_values, D_values, ...
    t_stop, sbase_va, cfg, Pe_prev, delta_prev_deg)
%SLX_STEP_AND_READ  Set workspace vars + advance FastRestart sim + read state.
%
%   [state, status] = slx_step_and_read(model_name, agent_ids,
%       M_values, D_values, t_stop, sbase_va, cfg, Pe_prev, delta_prev_deg)
%
%   FastRestart mode:
%     - Model state is held in memory between calls (no xFinal transfer).
%     - Only StopTime can be changed; StartTime is fixed at 0 from warmup.
%     - Workspace variables (M0_val_ES{k}, D0_val_ES{k}, phAng_ES{k},
%       Pe_ES{k}) are updated via assignin before each sim step.
%     - For NE39bus_v2, phAng_ES{k} is a VSrc absolute phase-angle command.
%       The VSG delta output is a raw internal angle, so convert it to
%       load-flow initial phase + wrapped relative delta before writing.
%     - No set_param on mask Value -- avoids checksum invalidation.
%
%   Arguments:
%     model_name        - Simulink model name, e.g. 'NE39bus_v2'
%     agent_ids         - Vector of agent indices, e.g. 1:8
%     M_values(N)       - Inertia values (s) for each agent
%     D_values(N)       - Damping values for each agent
%     t_stop            - Absolute stop time for this step (s)
%     sbase_va          - System base power (VA), e.g. 100e6
%     cfg               - Bridge config struct (omega_signal, vabc_signal, iabc_signal)
%     Pe_prev(N)        - Previous step Pe (p.u. on sbase). Pass [] first call.
%     delta_prev_deg(N) - Previous step delta (degrees). Pass [] first call.
%
%   Returns:
%     state.omega(N)     - per-agent frequency (p.u.)
%     state.Pe(N)        - per-agent electrical power (p.u. on sbase)
%     state.rocof(N)     - per-agent ROCOF (p.u./s)
%     state.delta(N)     - per-agent rotor angle (rad)
%     state.delta_deg(N) - per-agent rotor angle (degrees), for next call
%     status.success     - boolean
%     status.error       - error string (empty if success)
%     status.elapsed_ms

    if nargin < 8, Pe_prev = []; end
    if nargin < 9, delta_prev_deg = []; end

    status.success = true;
    status.error   = '';
    tic;
    N = length(agent_ids);
    vsg_sn   = cfg.vsg_sn;          % from BridgeConfig.vsg_sn_va (e.g. 200e6)
    pe_scale = sbase_va / vsg_sn;

    phAng_cmd_deg = nan(1, N);

    % --- Phase 1: Update workspace variables ---
    for i = 1:N
        idx = agent_ids(i);

        % Inertia and damping
        assignin('base', sprintf('M0_val_ES%d', idx), M_values(i));
        assignin('base', sprintf('D0_val_ES%d', idx), D_values(i));

        % Phase angle feedback (degrees)
        if ~isempty(delta_prev_deg)
            phAng_cmd_deg(i) = step_phase_command_deg(cfg, idx, delta_prev_deg(i));
            assignin('base', sprintf('phAng_ES%d', idx), phAng_cmd_deg(i));
        end

        % Pe feedback (convert sbase p.u. to VSG base p.u.)
        if ~isempty(Pe_prev)
            pe_vsg = Pe_prev(i) * pe_scale;
            assignin('base', sprintf('Pe_ES%d', idx), pe_vsg);
        end
    end

    % --- Phase 2: Advance simulation ---
    try
        set_param(model_name, 'StopTime', num2str(t_stop, '%.6f'));
        simOut = sim(model_name);
    catch ME
        status.success    = false;
        status.error      = ME.message;
        state             = step_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % --- Phase 3: Extract state ---
    [state, meas_failures] = slx_extract_state(simOut, agent_ids, cfg, sbase_va);
    state.phAng_cmd_deg = phAng_cmd_deg;

    % Structured measurement failure reporting (consumed by Python bridge)
    status.measurement_failures = meas_failures;
    status.elapsed_ms = toc * 1000;
end


% -----------------------------------------------------------------------
% Private helpers (must NOT start with underscore in MATLAB)
% -----------------------------------------------------------------------

function state = step_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
    state.phAng_cmd_deg = nan(1, N);
end


function ph = step_phase_command_deg(cfg, idx, delta_deg)
% Convert VSG internal angle to the absolute VSrc PhaseAngle command.
%
% cfg.phase_command_mode controls behaviour:
%   'passthrough'            — ph = delta_deg (Kundur: rotor angle direct command)
%   'absolute_with_loadflow' — ph = wrap(init_phang(idx) + gain*wrap(delta_deg))
%       Feedback gain < 1.0 needed for NE39bus_v2: a gain of 1.0 causes
%       delay-induced oscillations at 0.2 s control rate (X_line=0.10 p.u.,
%       V=1 p.u. → ΔPe≈1.7 p.u./step at gain=1.0; 0.3 limits to ~30 MW/step).
%
% cfg fields used:
%   phase_command_mode  — 'passthrough' | 'absolute_with_loadflow'
%   init_phang          — row vector of load-flow angles (deg); indexed by idx
%   phase_feedback_gain — scalar gain applied to wrapped delta
    if strcmp(cfg.phase_command_mode, 'absolute_with_loadflow')
        gain = cfg.phase_feedback_gain;
        ph   = step_wrap_to_180(cfg.init_phang(idx) + gain * step_wrap_to_180(delta_deg));
    else
        ph = delta_deg;
    end
end


function wrapped = step_wrap_to_180(angle_deg)
% Toolbox-free equivalent of wrapTo180.
    wrapped = mod(angle_deg + 180.0, 360.0) - 180.0;
end
