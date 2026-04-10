function [state, status] = vsg_warmup(model_name, agent_ids_or_duration, sbase_va, cfg, init_params)
%VSG_WARMUP  Episode reset helper -- shared by Kundur and NE39 scenarios.
%
% Kundur (2-arg) mode:
%   vsg_warmup(model_name, duration)
%   Stops any running FastRestart session, re-enables it, and runs a brief
%   warmup sim.  Python (bridge.warmup) pre-initialises workspace vars first.
%   Returns [] for both outputs; call with nargout=0.
%
% NE39 (5-arg) mode:
%   [state, status] = vsg_warmup(model_name, agent_ids, sbase_va, cfg, init_params)
%   Full episode reset for NE39bus_v2.slx:
%     1. Stop FastRestart (set_param off)
%     2. Write all workspace vars (M0, D0, phAng, Pe, wref)
%     3. Re-enable FastRestart (set_param on)
%     4. Run warmup sim for init_params.t_warmup seconds
%     5. Read initial state and update phAng/Pe workspace vars
%
%   init_params fields:
%     .M0       - scalar or N-vector, inertia (s)
%     .D0       - scalar or N-vector, damping
%     .phAng    - N-vector, initial phase angles (degrees)
%     .Pe0      - scalar or N-vector, initial Pe (p.u. VSG base, 200 MVA)
%     .t_warmup - warmup duration (s), default 0.5
%
%   state fields: omega(N), Pe(N), rocof(N), delta(N), delta_deg(N)
%   status fields: success, error, elapsed_ms

    % ------------------------------------------------------------------
    % Dispatch by nargin
    % ------------------------------------------------------------------
    if nargin == 2
        % Kundur / generic mode (legacy: always recompile)
        duration = agent_ids_or_duration;
        warmup_fastrestart_reset(model_name, duration, true);
        state  = [];
        status = [];
        return;
    end

    if nargin == 3
        % Kundur / generic mode with recompile flag (FR optimisation).
        %   do_recompile=true: first episode, FastRestart off then on
        %       (full compile, ~10s)
        %   do_recompile=false: subsequent episodes, skip recompile (~1s)
        %
        % NOTE: The 3rd positional arg maps to the parameter named `sbase_va`
        % in the function signature (which is shared with the 5-arg NE39 path).
        % It carries the do_recompile flag here, not a power base.  See the
        % nargin dispatch logic at the top of this function.
        duration     = agent_ids_or_duration;
        do_recompile = logical(sbase_va);   % sbase_va carries do_recompile for this path
        warmup_fastrestart_reset(model_name, duration, do_recompile);
        state  = [];
        status = [];
        return;
    end

    % NE39 full mode
    status.success = true;
    status.error   = '';
    tic;
    agent_ids = agent_ids_or_duration;
    N = length(agent_ids);

    % Defaults
    if ~isfield(init_params, 't_warmup'), init_params.t_warmup = 0.5; end
    if isscalar(init_params.M0),  init_params.M0  = repmat(init_params.M0,  1, N); end
    if isscalar(init_params.D0),  init_params.D0  = repmat(init_params.D0,  1, N); end
    if isscalar(init_params.Pe0), init_params.Pe0 = repmat(init_params.Pe0, 1, N); end

    % Step 0: Clear accumulated SDI / workspace data from previous episode.
    %   - Simulink.sdi.clear: evicts Signal Data Inspector internal log that
    %     accumulates across FastRestart sim() calls (main cause of linear
    %     warmup slowdown).
    %   - clearvars: removes ToWorkspace signal variables from base workspace.
    try
        Simulink.sdi.clear;
    catch
    end
    try
        evalin('base', 'clearvars -regexp ''^(omega|delta|Vabc|Iabc)_ES\d+$''');
    catch
    end

    % Step 1: Stop any running FastRestart session
    try
        set_param(model_name, 'FastRestart', 'off');
    catch
    end

    % Step 2: Write all workspace variables
    for i = 1:N
        idx = agent_ids(i);
        assignin('base', sprintf('M0_val_ES%d', idx), init_params.M0(i));
        assignin('base', sprintf('D0_val_ES%d', idx), init_params.D0(i));
        assignin('base', sprintf('phAng_ES%d',  idx), init_params.phAng(i));
        assignin('base', sprintf('Pe_ES%d',     idx), init_params.Pe0(i));
        assignin('base', sprintf('wref_%d',     idx), 1.0);
    end

    % Step 3: Enable FastRestart
    try
        set_param(model_name, 'FastRestart', 'on');
    catch ME
        status.success = false;
        status.error   = ['FastRestart enable failed: ' ME.message];
        state = warmup_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % Step 4: Run warmup simulation
    try
        set_param(model_name, 'StopTime', num2str(init_params.t_warmup, '%.6f'));
        simOut = sim(model_name);
    catch ME
        status.success = false;
        status.error   = ['Warmup sim failed: ' ME.message];
        state = warmup_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % Step 5: Extract initial state
    state = warmup_extract_state(simOut, agent_ids, cfg, sbase_va);

    % Step 6: Feed warmup delta/Pe back into workspace vars so the first
    %         RL step starts from the correct phase angle and Pe.
    %
    %   phAng_ES{k} is an ABSOLUTE VSrc phase-angle command (degrees).
    %   It must be computed the same way vsg_step_and_read.m does:
    %       phAngCmd = wrapTo180(init_loadflow_phAng(k) + wrapTo180(delta_deg(k)))
    %   Writing raw delta_deg here would set the wrong initial phAng and is
    %   inconsistent with what vsg_step_and_read.m will apply on the first step.
    vsg_sn = 200e6;
    init_phAng_ne39 = [-3.646, 0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181];
    for i = 1:N
        idx = agent_ids(i);
        % --- Phase angle: use corrected absolute command (matches step_phase_command_deg) ---
        if state.delta(i) ~= 0
            delta_clipped = max(-90.0, min(90.0, state.delta_deg(i)));
            if strcmp(model_name, 'NE39bus_v2')
                ph = mod(init_phAng_ne39(idx) + mod(delta_clipped + 180.0, 360.0) - 180.0 + 180.0, 360.0) - 180.0;
            else
                ph = delta_clipped;
            end
            assignin('base', sprintf('phAng_ES%d', idx), ph);
        end
        if state.Pe(i) ~= 0
            pe_vsg = state.Pe(i) * (sbase_va / vsg_sn);
            assignin('base', sprintf('Pe_ES%d', idx), pe_vsg);
        end
    end

    status.elapsed_ms = toc * 1000;
    fprintf('RESULT: vsg_warmup (NE39) done in %.0f ms, omega=[%s]\n', ...
            status.elapsed_ms, num2str(state.omega, '%.4f '));
end


% -----------------------------------------------------------------------
% Private helpers (names must NOT start with underscore in MATLAB)
% -----------------------------------------------------------------------

function warmup_fastrestart_reset(model_name, duration, do_recompile)
% Generic Kundur-mode reset.
%
%   do_recompile=true  (first episode):
%     FastRestart off then on forces Simscape recompile and IC resolution.
%     Required once per training run to compile the model.
%
%   do_recompile=false (subsequent episodes):
%     Keep FastRestart on.  Setting StopTime to a value lower than the
%     current simulation time causes Simulink to restart from t=0 and
%     re-solve Simscape initial conditions from the .slx model parameters.
%     Skips the ~10-12 s recompile cost paid on every episode reset.
%
    if nargin < 3, do_recompile = true; end

    if do_recompile
        % Full recompile path (used once per training run).
        try
            set_param(model_name, 'FastRestart', 'off');
        catch
        end
        try
            set_param(model_name, 'FastRestart', 'on');
        catch ME
            error('vsg_warmup: FastRestart enable failed: %s', ME.message);
        end
    else
        % Fast path: model already compiled, just clear accumulated SDI data.
        % FastRestart stays on; sim() below restarts from t=0 automatically
        % because StopTime < current simulation time.
        try
            Simulink.sdi.clear;
        catch
        end
        try
            evalin('base', 'clearvars -regexp ''^(omega|delta|Vabc|Iabc)_ES\d+$''');
        catch
        end
    end

    set_param(model_name, 'StopTime', num2str(duration, '%.6f'));
    sim(model_name);
    fprintf('RESULT: vsg_warmup (Kundur) done, t_warmup=%.3f s, recompile=%d\n', ...
            duration, do_recompile);
end


function state = warmup_extract_state(simOut, agent_ids, cfg, sbase_va)
    N = length(agent_ids);
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);

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
        catch
        end

        % Pe: prefer V×I (NE39 has Vabc/Iabc ToWorkspace), fall back to
        % p_out_signal (Kundur logs P_out directly from swing equation).
        pe_read = false;
        try
            Vabc = simOut.get(vabc_name);
            Iabc = simOut.get(iabc_name);
            state.Pe(i) = real(sum(Vabc.Data(end,:) .* conj(Iabc.Data(end,:)))) / sbase_va;
            pe_read = true;
        catch
        end
        if ~pe_read && isfield(cfg, 'p_out_signal') && ~isempty(cfg.p_out_signal)
            try
                p_out_name = strrep(cfg.p_out_signal, '{idx}', num2str(idx));
                p_out_ts = simOut.get(p_out_name);
                % P_out is p.u. on VSG base; convert to sbase p.u.
                state.Pe(i) = p_out_ts.Data(end) * (cfg.vsg_sn / sbase_va);
            catch
            end
        end

        try
            delta_name     = strrep('delta_ES{idx}', '{idx}', num2str(idx));
            delta_ts       = simOut.get(delta_name);
            state.delta(i)     = delta_ts.Data(end);
            state.delta_deg(i) = delta_ts.Data(end) * (180 / pi);
        catch
        end
    end
end


function state = warmup_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
end
