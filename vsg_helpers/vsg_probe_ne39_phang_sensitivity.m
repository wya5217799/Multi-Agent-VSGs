%VSG_PROBE_NE39_PHANG_SENSITIVITY  Repeatable NE39 closed-loop health probe.
%
% Run through MCP:
%   simulink_run_script("vsg_probe_ne39_phang_sensitivity", timeout_sec=120)
%
% All diagnostic lines use RESULT: so vsg_run_quiet surfaces them.

model_name = 'NE39bus_v2';
agent_ids = 1:8;
sbase_va = 100e6;
init_phang = [-3.646, 0.0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181];
init_pe_vsg = 0.5;
t_warmup = 0.5;
dt_probe = 0.2;

repo_root = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(repo_root, 'vsg_helpers'));
model_dir = fullfile(repo_root, 'scenarios', 'new_england', 'simulink_models');
model_file = fullfile(model_dir, [model_name '.slx']);
workspace_file = fullfile(model_dir, 'NE39bus_workspace.mat');
data_file = fullfile(model_dir, 'NE39bus_data.m');
old_dir = pwd;
cleanup = onCleanup(@() local_cleanup(old_dir, model_name));
cd(model_dir);

try
    if exist(data_file, 'file') == 2
        local_run_file_in_base(data_file);
    end
    if exist(workspace_file, 'file') == 2
        local_load_mat_to_base(workspace_file);
    end

    if ~bdIsLoaded(model_name)
        load_system(model_file);
    end

    cfg = struct();
    cfg.omega_signal = 'omega_ES{idx}';
    cfg.vabc_signal = 'Vabc_ES{idx}';
    cfg.iabc_signal = 'Iabc_ES{idx}';
    cfg.delta_signal = 'delta_ES{idx}';
    cfg.pe_measurement = 'vi';

    phase_expr = local_get_param_or_empty([model_name '/VSrc_ES1'], 'PhaseAngle');
    phang_param_exists = contains(phase_expr, 'phAng_ES1');
    fprintf('RESULT: phAng param exists = %d, VSrc_ES1 PhaseAngle="%s"\n', ...
        phang_param_exists, phase_expr);

    baseline = local_reset_and_step(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        12.0 * ones(1, 8), 3.0 * ones(1, 8), true);
    fprintf('RESULT: baseline Pe/omega/phAngCmd = Pe[%s], omega[%s], phAngCmd[%s]\n', ...
        local_vec(baseline.Pe), local_vec(baseline.omega), ...
        local_vec(baseline.phAng_cmd_deg));

    shifted = local_reset_and_step_with_delta_offset(model_name, agent_ids, ...
        sbase_va, cfg, init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        12.0 * ones(1, 8), 3.0 * ones(1, 8), 1, 30.0);
    phang_pe_delta = max(abs(shifted.Pe - baseline.Pe));
    fprintf(['RESULT: phAng step +30deg Pe/omega = Pe[%s], omega[%s], ' ...
        'max_abs_dPe=%.6g, injected_delta_deg[%s], phAngCmd[%s]\n'], ...
        local_vec(shifted.Pe), local_vec(shifted.omega), phang_pe_delta, ...
        local_vec(shifted.injected_delta_deg), local_vec(shifted.phAng_cmd_deg));

    md_low = local_reset_and_step(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        6.0 * ones(1, 8), 1.5 * ones(1, 8), true);
    fprintf('RESULT: M/D low omega/delta/phAngCmd/Pe = omega[%s], delta_deg[%s], phAngCmd[%s], Pe[%s]\n', ...
        local_vec(md_low.omega), local_vec(md_low.delta_deg), ...
        local_vec(md_low.phAng_cmd_deg), local_vec(md_low.Pe));

    md_base = local_reset_and_step(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        12.0 * ones(1, 8), 3.0 * ones(1, 8), true);
    fprintf('RESULT: M/D base omega/delta/phAngCmd/Pe = omega[%s], delta_deg[%s], phAngCmd[%s], Pe[%s]\n', ...
        local_vec(md_base.omega), local_vec(md_base.delta_deg), ...
        local_vec(md_base.phAng_cmd_deg), local_vec(md_base.Pe));

    md_high = local_reset_and_step(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        30.0 * ones(1, 8), 7.5 * ones(1, 8), true);
    fprintf('RESULT: M/D high omega/delta/phAngCmd/Pe = omega[%s], delta_deg[%s], phAngCmd[%s], Pe[%s]\n', ...
        local_vec(md_high.omega), local_vec(md_high.delta_deg), ...
        local_vec(md_high.phAng_cmd_deg), local_vec(md_high.Pe));

    md_omega_span = max(abs(md_low.omega - md_high.omega));
    md_delta_span = max(abs(md_low.delta_deg - md_high.delta_deg));
    md_pe_span = max(abs(md_low.Pe - md_high.Pe));

    open_loop = local_reset_and_two_steps(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        12.0 * ones(1, 8), 3.0 * ones(1, 8), false);
    open_loop_pe_drift = max(abs(open_loop.second.Pe - open_loop.first.Pe));
    fprintf('RESULT: open-loop no-delta Pe drift = %.6g, first[%s], second[%s]\n', ...
        open_loop_pe_drift, local_vec(open_loop.first.Pe), local_vec(open_loop.second.Pe));

    closed_loop = local_reset_and_two_steps(model_name, agent_ids, sbase_va, cfg, ...
        init_phang, init_pe_vsg, t_warmup, dt_probe, ...
        12.0 * ones(1, 8), 3.0 * ones(1, 8), true);
    closed_loop_cmd_bounded = max(abs(closed_loop.second.phAng_cmd_deg)) < 180.0;
    closed_loop_finite = all(isfinite(closed_loop.second.Pe)) && ...
        all(isfinite(closed_loop.second.omega)) && ...
        all(isfinite(closed_loop.second.phAng_cmd_deg));
    fprintf(['RESULT: closed-loop two-step bounded = %d, finite = %d, ' ...
        'second_Pe[%s], second_omega[%s], second_phAngCmd[%s]\n'], ...
        closed_loop_cmd_bounded, closed_loop_finite, ...
        local_vec(closed_loop.second.Pe), local_vec(closed_loop.second.omega), ...
        local_vec(closed_loop.second.phAng_cmd_deg));

    max_abs_delta = max(abs(md_base.delta_deg));
    max_abs_phang_cmd = max(abs(md_base.phAng_cmd_deg));
    fprintf(['RESULT: delta range = max_abs_delta_deg %.6g, ' ...
        'max_abs_phAng_cmd_deg %.6g, baseline_delta_deg[%s], phAngCmd[%s]\n'], ...
        max_abs_delta, max_abs_phang_cmd, local_vec(md_base.delta_deg), ...
        local_vec(md_base.phAng_cmd_deg));

    warmup_delta_error = max(abs(baseline.warmup_delta_deg - init_phang));
    phang_cmd_error = max(abs(baseline.phAng_cmd_deg - init_phang));
    warmup_preserved = phang_cmd_error < 1e-6;
    fprintf(['RESULT: warmup init phAng preserved = %d, ' ...
        'max_abs_delta_error_deg=%.6g, max_abs_cmd_error_deg=%.6g, ' ...
        'warmup_delta_deg[%s], phAngCmd[%s], init_phAng[%s]\n'], ...
        warmup_preserved, warmup_delta_error, phang_cmd_error, ...
        local_vec(baseline.warmup_delta_deg), local_vec(baseline.phAng_cmd_deg), ...
        local_vec(init_phang));

    phang_affects_pe = phang_pe_delta > 1e-4;
    md_affects_state = (md_omega_span > 1e-6) || (md_delta_span > 1e-4) || (md_pe_span > 1e-4);
    delta_reasonable = max_abs_phang_cmd < 180.0;
    open_loop_frozen = open_loop_pe_drift < 1e-4;
    passed = phang_param_exists && phang_affects_pe && md_affects_state && ...
        delta_reasonable && warmup_preserved && closed_loop_cmd_bounded && ...
        closed_loop_finite;

    fprintf(['RESULT: classification = %s, phAng_affects_Pe=%d, ' ...
        'MD_affects_state=%d, open_loop_no_delta_frozen=%d, ' ...
        'delta_reasonable=%d, warmup_preserved=%d, ' ...
        'closed_loop_two_step_bounded=%d, closed_loop_two_step_finite=%d\n'], ...
        local_passfail(passed), phang_affects_pe, md_affects_state, ...
        open_loop_frozen, delta_reasonable, warmup_preserved, ...
        closed_loop_cmd_bounded, closed_loop_finite);
catch ME
    fprintf('RESULT: classification = fail, error="%s"\n', ME.message);
end

function probe = local_reset_and_step(model_name, agent_ids, sbase_va, cfg, ...
    init_phang, init_pe_vsg, t_warmup, dt_probe, M_values, D_values, use_delta)

    [warmup_state, warmup_status] = local_warmup(model_name, agent_ids, ...
        sbase_va, cfg, init_phang, init_pe_vsg, t_warmup);
    if ~warmup_status.success
        error('Warmup failed: %s', warmup_status.error);
    end

    pe_prev = warmup_state.Pe;
    if use_delta
        delta_prev = warmup_state.delta_deg;
    else
        delta_prev = [];
    end

    [state, status] = vsg_step_and_read(model_name, agent_ids, M_values, ...
        D_values, t_warmup + dt_probe, sbase_va, cfg, pe_prev, delta_prev);
    if ~status.success
        error('Step failed: %s', status.error);
    end

    probe = state;
    probe.warmup_delta_deg = warmup_state.delta_deg;
end

function probe = local_reset_and_step_with_delta_offset(model_name, agent_ids, ...
    sbase_va, cfg, init_phang, init_pe_vsg, t_warmup, dt_probe, ...
    M_values, D_values, offset_idx, offset_deg)

    [warmup_state, warmup_status] = local_warmup(model_name, agent_ids, ...
        sbase_va, cfg, init_phang, init_pe_vsg, t_warmup);
    if ~warmup_status.success
        error('Warmup failed: %s', warmup_status.error);
    end

    delta_prev = warmup_state.delta_deg;
    delta_prev(offset_idx) = delta_prev(offset_idx) + offset_deg;

    [state, status] = vsg_step_and_read(model_name, agent_ids, M_values, ...
        D_values, t_warmup + dt_probe, sbase_va, cfg, warmup_state.Pe, delta_prev);
    if ~status.success
        error('Step failed: %s', status.error);
    end

    probe = state;
    probe.warmup_delta_deg = warmup_state.delta_deg;
    probe.injected_delta_deg = delta_prev;
end

function probe = local_reset_and_two_steps(model_name, agent_ids, sbase_va, cfg, ...
    init_phang, init_pe_vsg, t_warmup, dt_probe, M_values, D_values, use_delta)

    [warmup_state, warmup_status] = local_warmup(model_name, agent_ids, ...
        sbase_va, cfg, init_phang, init_pe_vsg, t_warmup);
    if ~warmup_status.success
        error('Warmup failed: %s', warmup_status.error);
    end

    pe_prev = warmup_state.Pe;
    if use_delta
        delta_prev = warmup_state.delta_deg;
    else
        delta_prev = [];
    end

    [first, status1] = vsg_step_and_read(model_name, agent_ids, M_values, ...
        D_values, t_warmup + dt_probe, sbase_va, cfg, pe_prev, delta_prev);
    if ~status1.success
        error('First step failed: %s', status1.error);
    end

    if use_delta
        second_delta_prev = first.delta_deg;
    else
        second_delta_prev = [];
    end

    [second, status2] = vsg_step_and_read(model_name, agent_ids, M_values, ...
        D_values, t_warmup + 2 * dt_probe, sbase_va, cfg, first.Pe, second_delta_prev);
    if ~status2.success
        error('Second step failed: %s', status2.error);
    end

    probe = struct('first', first, 'second', second);
end

function [state, status] = local_warmup(model_name, agent_ids, sbase_va, cfg, ...
    init_phang, init_pe_vsg, t_warmup)

    init_params = struct();
    init_params.M0 = 12.0 * ones(1, length(agent_ids));
    init_params.D0 = 3.0 * ones(1, length(agent_ids));
    init_params.phAng = init_phang;
    init_params.Pe0 = init_pe_vsg * ones(1, length(agent_ids));
    init_params.t_warmup = t_warmup;
    [state, status] = vsg_warmup(model_name, agent_ids, sbase_va, cfg, init_params);
end

function value = local_get_param_or_empty(block_path, param_name)
    try
        value = char(get_param(block_path, param_name));
    catch
        value = '';
    end
end

function local_load_mat_to_base(mat_file)
    vars = load(mat_file);
    names = fieldnames(vars);
    for k = 1:numel(names)
        assignin('base', names{k}, vars.(names{k}));
    end
end

function local_run_file_in_base(script_file)
    escaped = strrep(script_file, '''', '''''');
    evalin('base', sprintf('run(''%s'');', escaped));
end

function text = local_vec(values)
    text = strtrim(num2str(values, '%.6g '));
end

function text = local_passfail(ok)
    if ok
        text = 'pass';
    else
        text = 'fail';
    end
end

function local_cleanup(old_dir, model_name)
    try
        if bdIsLoaded(model_name)
            set_param(model_name, 'FastRestart', 'off');
        end
    catch
    end
    cd(old_dir);
end
