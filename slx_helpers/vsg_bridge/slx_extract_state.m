function [state, meas_failures] = slx_extract_state(simOut, agent_ids, cfg, sbase_va)
%SLX_EXTRACT_STATE  Shared state-extraction helper for slx_step_and_read / slx_warmup.
%
%   [state, meas_failures] = slx_extract_state(simOut, agent_ids, cfg, sbase_va)
%
%   Reads omega / rocof / delta / Pe from a Simulink simOut object for every
%   agent listed in agent_ids.  Pe measurement mode is selected via
%   cfg.pe_measurement:
%
%     'vi'           -- V×I only (NE39)
%     'pout'         -- p_out_signal only (Kundur)
%     'vi_then_pout' -- try V×I, fall back to p_out (legacy)
%     'feedback'     -- PeGain_ES{idx} ToWorkspace (true electrical Pe)
%
%   Inputs:
%     simOut     - Simulink.SimulationOutput from sim()
%     agent_ids  - row/col vector of agent indices (e.g. 1:8)
%     cfg        - bridge config struct; required fields:
%                    omega_signal, vabc_signal, iabc_signal, delta_signal,
%                    pe_measurement, vsg_sn
%                  optional fields (depending on pe_measurement):
%                    p_out_signal, pe_feedback_signal
%     sbase_va   - system base power (VA), e.g. 100e6
%
%   Outputs:
%     state.omega(N)     - per-agent frequency (p.u.)
%     state.Pe(N)        - per-agent electrical power (p.u. on sbase_va)
%     state.rocof(N)     - per-agent ROCOF (p.u./s)
%     state.delta(N)     - per-agent rotor angle (rad)
%     state.delta_deg(N) - per-agent rotor angle (degrees)
%     meas_failures      - cell array of strings, one entry per failure
%                          (empty when everything succeeds)

    N = length(agent_ids);
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);

    % Structured failure tracking: consumed by Python bridge (and ignored in warmup).
    meas_failures = {};

    pe_mode = cfg.pe_measurement;

    for i = 1:N
        idx = agent_ids(i);

        omega_name = strrep(cfg.omega_signal, '{idx}', num2str(idx));
        vabc_name  = strrep(cfg.vabc_signal,  '{idx}', num2str(idx));
        iabc_name  = strrep(cfg.iabc_signal,  '{idx}', num2str(idx));

        % --- omega + rocof ---
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

        % --- Pe: dispatch on cfg.pe_measurement ---
        pe_read  = false;
        pe_error = '';

        % V×I path
        if ~pe_read && (strcmp(pe_mode, 'vi') || strcmp(pe_mode, 'vi_then_pout'))
            try
                Vabc = simOut.get(vabc_name);
                Iabc = simOut.get(iabc_name);
                vi_scale = 1.0;
                if isfield(cfg, 'pe_vi_scale')
                    vi_scale = cfg.pe_vi_scale;
                end
                state.Pe(i) = vi_scale * real(sum(Vabc.Data(end,:) .* conj(Iabc.Data(end,:)))) / sbase_va;
                pe_read = true;
            catch ME
                pe_error = ME.message;
            end
        end

        % P_out path
        if ~pe_read && (strcmp(pe_mode, 'pout') || strcmp(pe_mode, 'vi_then_pout'))
            if isfield(cfg, 'p_out_signal') && ~isempty(cfg.p_out_signal)
                try
                    p_out_name = strrep(cfg.p_out_signal, '{idx}', num2str(idx));
                    p_out_ts   = simOut.get(p_out_name);
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

        % feedback path (PeGain_ES{idx} ToWorkspace — true electrical Pe)
        if ~pe_read && strcmp(pe_mode, 'feedback')
            if isfield(cfg, 'pe_feedback_signal') && ~isempty(cfg.pe_feedback_signal)
                try
                    pefb_name = strrep(cfg.pe_feedback_signal, '{idx}', num2str(idx));
                    pefb_ts   = simOut.get(pefb_name);
                    % PeFb is VSG-base pu; single conversion point → system-base pu
                    state.Pe(i) = pefb_ts.Data(end) * (cfg.vsg_sn / sbase_va);
                    pe_read = true;
                catch ME
                    pe_error = ME.message;
                end
            end
        end

        if ~pe_read
            meas_failures{end+1} = sprintf('Pe:agent%d:%s:%s', idx, pe_mode, pe_error); %#ok<AGROW>
            warning('slx_extract_state:PeReadFailed', ...
                'Failed to read Pe for agent %d (mode=%s). state.Pe remains %.6g. %s', ...
                idx, pe_mode, state.Pe(i), pe_error);
        end

        % --- delta ---
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
