function [state, status] = vsg_step_and_read( ...
    model_name, agent_ids, M_values, D_values, ...
    t_stop, sbase_va, cfg, Pe_prev, delta_prev_deg)
%VSG_STEP_AND_READ  Set workspace vars + advance FastRestart sim + read state.
%
%   [state, status] = vsg_step_and_read(model_name, agent_ids,
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
    vsg_sn   = 200e6;
    pe_scale = sbase_va / vsg_sn;  % 0.5 for 100e6/200e6

    phAng_cmd_deg = nan(1, N);

    % --- Phase 1: Update workspace variables ---
    for i = 1:N
        idx = agent_ids(i);

        % Inertia and damping
        assignin('base', sprintf('M0_val_ES%d', idx), M_values(i));
        assignin('base', sprintf('D0_val_ES%d', idx), D_values(i));

        % Phase angle feedback (degrees)
        if ~isempty(delta_prev_deg)
            phAng_cmd_deg(i) = step_phase_command_deg(model_name, idx, delta_prev_deg(i));
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
    [state, meas_failures] = step_extract_state(simOut, agent_ids, cfg, sbase_va);
    state.phAng_cmd_deg = phAng_cmd_deg;

    % Structured measurement failure reporting (consumed by Python bridge)
    status.measurement_failures = meas_failures;
    status.elapsed_ms = toc * 1000;
end


% -----------------------------------------------------------------------
% Private helpers (must NOT start with underscore in MATLAB)
% -----------------------------------------------------------------------

function [state, meas_failures] = step_extract_state(simOut, agent_ids, cfg, sbase_va)
    N = length(agent_ids);
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);

    % Structured failure tracking: cell array of strings, one per failure.
    % Python receives this as a list and can decide severity.
    meas_failures = {};

    for i = 1:N
        idx = agent_ids(i);

        omega_name = strrep(cfg.omega_signal, '{idx}', num2str(idx));
        vabc_name  = strrep(cfg.vabc_signal,  '{idx}', num2str(idx));
        iabc_name  = strrep(cfg.iabc_signal,  '{idx}', num2str(idx));

        try
            omega_ts = simOut.get(omega_name);
            state.omega(i) = omega_ts.Data(end);
            if length(omega_ts.Data) >= 2
                dt = omega_ts.Time(end) - omega_ts.Time(end-1);
                if dt > 0
                    state.rocof(i) = (omega_ts.Data(end) - omega_ts.Data(end-1)) / dt;
                end
            end
        catch ME
            meas_failures{end+1} = sprintf('omega:agent%d:%s', idx, ME.message); %#ok<AGROW>
        end

        % Pe: dispatch on cfg.pe_measurement contract.
        %   'vi'             — V×I only (NE39)
        %   'pout'           — p_out_signal only (Kundur)
        %   'vi_then_pout'   — try V×I, fall back to p_out (legacy)
        pe_read = false;
        pe_error = '';
        pe_mode = cfg.pe_measurement;

        % --- V×I path ---
        if ~pe_read && (strcmp(pe_mode, 'vi') || strcmp(pe_mode, 'vi_then_pout'))
            try
                Vabc = simOut.get(vabc_name);
                Iabc = simOut.get(iabc_name);
                state.Pe(i) = real(sum(Vabc.Data(end,:) .* conj(Iabc.Data(end,:)))) / sbase_va;
                pe_read = true;
            catch ME
                pe_error = ME.message;
            end
        end

        % --- P_out path ---
        if ~pe_read && (strcmp(pe_mode, 'pout') || strcmp(pe_mode, 'vi_then_pout'))
            if isfield(cfg, 'p_out_signal') && ~isempty(cfg.p_out_signal)
                try
                    p_out_name = strrep(cfg.p_out_signal, '{idx}', num2str(idx));
                    p_out_ts = simOut.get(p_out_name);
                    % P_out is p.u. on VSG base; convert to sbase p.u.
                    state.Pe(i) = p_out_ts.Data(end) * (cfg.vsg_sn / sbase_va);
                    pe_read = true;
                catch ME
                    if isempty(pe_error)
                        pe_error = ME.message;
                    else
                        pe_error = sprintf('%s | fallback: %s', pe_error, ME.message);
                    end
                end
            end
        end

        if ~pe_read
            meas_failures{end+1} = sprintf('Pe:agent%d:%s:%s', idx, pe_mode, pe_error); %#ok<AGROW>
            warning('vsg_step_and_read:PeReadFailed', ...
                'Failed to read Pe for agent %d (mode=%s). state.Pe remains %.6g. %s', ...
                idx, pe_mode, state.Pe(i), pe_error);
        end

        try
            delta_name     = strrep(cfg.delta_signal, '{idx}', num2str(idx));
            delta_ts       = simOut.get(delta_name);
            state.delta(i)     = delta_ts.Data(end);
            state.delta_deg(i) = delta_ts.Data(end) * (180 / pi);
        catch ME
            meas_failures{end+1} = sprintf('delta:agent%d:%s', idx, ME.message); %#ok<AGROW>
        end
    end
end


function state = step_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
    state.phAng_cmd_deg = nan(1, N);
end


function ph = step_phase_command_deg(model_name, idx, delta_deg)
% Convert VSG internal angle to the absolute VSrc PhaseAngle command.
%
% Feedback gain < 1.0 for NE39bus_v2:
%   A gain of 1.0 causes delay-induced oscillations at the 0.2 s control
%   sampling rate.  With X_line=0.10 p.u. and V=1 p.u., a 10-degree phAng
%   jump produces ΔPe ≈ 1.7 p.u. (170 MW) per step, far above the system's
%   damping capacity.  Reducing the gain to 0.3 limits ΔPe to ~30 MW/step
%   while still coupling the mechanical rotor angle to the VSrc angle,
%   preserving the VSG synchronisation behaviour.
    if strcmp(model_name, 'NE39bus_v2')
        init_phAng = [-3.646, 0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181];
        gain = 0.3;
        ph = step_wrap_to_180(init_phAng(idx) + gain * step_wrap_to_180(delta_deg));
    else
        ph = delta_deg;
    end
end


function wrapped = step_wrap_to_180(angle_deg)
% Toolbox-free equivalent of wrapTo180.
    wrapped = mod(angle_deg + 180.0, 360.0) - 180.0;
end
