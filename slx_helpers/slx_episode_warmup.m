function [state, status] = slx_episode_warmup(model_name, agent_ids, sbase_va, cfg, init_params, do_recompile)
%SLX_EPISODE_WARMUP  Full episode reset and warmup for NE39 / Kundur scenarios.
%
%   [state, status] = slx_episode_warmup(model_name, agent_ids, sbase_va, cfg, init_params)
%   [state, status] = slx_episode_warmup(model_name, agent_ids, sbase_va, cfg, init_params, do_recompile)
%
%   Replaces the NE39 5/6-arg path of slx_warmup with general primitives:
%     1. Reset FastRestart state via slx_runtime_reset
%     2. Write all workspace vars (M0, D0, phAng, Pe, wref) via slx_workspace_set
%     3. Re-enable FastRestart (if do_recompile=true)
%     4. Run warmup sim for init_params.t_warmup seconds
%     5. Extract initial state via slx_extract_state
%     6. Feed warmup delta/Pe back into workspace vars via slx_workspace_set
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

    if nargin < 6, do_recompile = true; end

    status.success = true;
    status.error   = '';
    tic;
    model_name = char(model_name);
    N = length(agent_ids);

    if ~isfield(init_params, 't_warmup'), init_params.t_warmup = 0.5; end
    if isscalar(init_params.M0),  init_params.M0  = repmat(init_params.M0,  1, N); end
    if isscalar(init_params.D0),  init_params.D0  = repmat(init_params.D0,  1, N); end
    if isscalar(init_params.Pe0), init_params.Pe0 = repmat(init_params.Pe0, 1, N); end

    % Step 1: Reset FastRestart state
    if logical(do_recompile)
        slx_runtime_reset(model_name, 'off', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
    else
        slx_runtime_reset(model_name, '', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
    end

    % Step 2: Write all workspace variables
    vars = struct();
    for i = 1:N
        idx = agent_ids(i);
        vars.(sprintf('M0_val_ES%d', idx)) = init_params.M0(i);
        vars.(sprintf('D0_val_ES%d', idx)) = init_params.D0(i);
        vars.(sprintf('phAng_ES%d',  idx)) = init_params.phAng(i);
        vars.(sprintf('Pe_ES%d',     idx)) = init_params.Pe0(i);
        vars.(sprintf('wref_%d',     idx)) = 1.0;
    end
    slx_workspace_set(vars);

    % Step 3: Enable FastRestart (skip when do_recompile=false)
    if logical(do_recompile)
        reset_result = slx_runtime_reset(model_name, 'on', false, '');
        if ~reset_result.ok
            status.success = false;
            status.error   = ['FastRestart enable failed: ' reset_result.error_message];
            state = episode_warmup_empty_state(N);
            status.elapsed_ms = toc * 1000;
            return;
        end
    end

    % Step 4: Run warmup simulation (keep direct sim() to capture simOut for extract_state)
    try
        set_param(model_name, 'StopTime', num2str(init_params.t_warmup, '%.6f'));
        simOut = sim(model_name);
    catch ME
        status.success = false;
        status.error   = ['Warmup sim failed: ' ME.message];
        state = episode_warmup_empty_state(N);
        status.elapsed_ms = toc * 1000;
        return;
    end

    % Step 5: Extract initial state
    [state, ~] = slx_extract_state(simOut, agent_ids, cfg, sbase_va);

    % Step 6: Feed warmup delta/Pe back into workspace vars
    post_vars = struct();
    for i = 1:N
        idx = agent_ids(i);
        if state.delta(i) ~= 0
            delta_clipped = max(-90.0, min(90.0, state.delta_deg(i)));
            if isfield(cfg, 'phase_command_mode') && ...
                    strcmp(cfg.phase_command_mode, 'absolute_with_loadflow')
                gain = cfg.phase_feedback_gain;
                ph   = mod(cfg.init_phang(idx) + ...
                    mod(gain * delta_clipped + 180.0, 360.0) - 180.0 + 180.0, 360.0) - 180.0;
            else
                ph = delta_clipped;
            end
            post_vars.(sprintf('phAng_ES%d', idx)) = ph;
        end
        if state.Pe(i) ~= 0
            pe_vsg = state.Pe(i) * (sbase_va / cfg.vsg_sn);
            post_vars.(sprintf('Pe_ES%d', idx)) = pe_vsg;
        end
    end
    if ~isempty(fieldnames(post_vars))
        slx_workspace_set(post_vars);
    end

    status.elapsed_ms = toc * 1000;
    fprintf('RESULT: slx_episode_warmup done in %.0f ms, omega=[%s]\n', ...
            status.elapsed_ms, num2str(state.omega, '%.4f '));
end


function state = episode_warmup_empty_state(N)
    state.omega     = zeros(1, N);
    state.Pe        = zeros(1, N);
    state.rocof     = zeros(1, N);
    state.delta     = zeros(1, N);
    state.delta_deg = zeros(1, N);
end
