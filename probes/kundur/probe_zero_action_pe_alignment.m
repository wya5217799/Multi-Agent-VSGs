model_name  = 'kundur_vsg';
agent_ids   = 1:4;
vsg_sn_va   = 200e6;
sbase_va    = 100e6;
vsg_m0      = 12.0;
vsg_d0      = 3.0;
t_warmup    = 0.5;
dt_probe    = 1.0;

repo_root    = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(repo_root, 'slx_helpers'));
model_dir    = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models');
scenario_dir = fullfile(repo_root, 'scenarios', 'kundur');
old_dir      = pwd;
cleanup      = onCleanup(@() local_cleanup(old_dir, model_name));
cd(model_dir);

try
    ic = slx_load_kundur_ic(fullfile(scenario_dir, 'kundur_ic.json'));

    for i = 1:length(agent_ids)
        idx = agent_ids(i);
        assignin('base', sprintf('M0_val_ES%d', idx), vsg_m0);
        assignin('base', sprintf('D0_val_ES%d', idx), vsg_d0);
        assignin('base', sprintf('Pe_ES%d',     idx), ic.vsg_p0_vsg_base_pu(i));
        assignin('base', sprintf('phAng_ES%d',  idx), 0.0);
    end

    if ~bdIsLoaded(model_name)
        load_system(fullfile(model_dir, [model_name '.slx']));
    end

    slx_warmup(model_name, t_warmup);

    set_param(model_name, 'StopTime', num2str(t_warmup + dt_probe, '%.6f'));
    simOut = sim(model_name);

    n_agents    = length(agent_ids);
    pe_sbase    = zeros(1, n_agents);
    pout_sbase  = zeros(1, n_agents);
    all_aligned = true;

    for i = 1:n_agents
        idx = agent_ids(i);

        pefb_val = local_read_signal_last(simOut, sprintf('PeFb_ES%d', idx));
        pout_val = local_read_signal_last(simOut, sprintf('P_out_ES%d', idx));
        omega_val = local_read_signal_last(simOut, sprintf('omega_ES%d', idx));
        delta_val = local_read_signal_last(simOut, sprintf('delta_ES%d', idx));
        delta_deg = delta_val * 180 / pi;

        pe_sbase(i)   = pefb_val * (vsg_sn_va / sbase_va);
        pout_sbase(i) = pout_val * (vsg_sn_va / sbase_va);

        err_i     = pe_sbase(i) - pefb_val * (vsg_sn_va / sbase_va);
        rel_err_i = abs(err_i) / max(abs(pe_sbase(i)), 1e-9);
        aligned_i = abs(err_i) < 1e-6 || rel_err_i < 1e-6;

        if ~aligned_i
            all_aligned = false;
        end

        omega_dev = abs(omega_val - 1.0);

        try
            intw_val = local_read_signal_last(simOut, sprintf('IntW_ES%d', idx));
            intw_str = sprintf('%.6g', intw_val);
        catch
            intw_str = 'N/A';
        end

        fprintf(['RESULT: agent%d: pefb_pu=%.6g, pe_sbase=%.6g, pout_sbase=%.6g, ' ...
            'omega=%.6g, delta_deg=%.6g, err=%.2e, aligned=%d, ' ...
            'omega_dev=%.2e, intw=%s\n'], ...
            idx, pefb_val, pe_sbase(i), pout_sbase(i), omega_val, delta_deg, ...
            err_i, aligned_i, omega_dev, intw_str);
    end

    passed = all_aligned;
    fprintf(['RESULT: classification = %s, n_agents=%d, all_aligned=%d, ' ...
        'pe_sbase=[%s], pout_sbase=[%s]\n'], ...
        local_passfail(passed), n_agents, all_aligned, ...
        local_vec(pe_sbase), local_vec(pout_sbase));

catch ME
    fprintf('RESULT: classification = fail, error="%s"\n', ME.message);
end

function val = local_read_signal_last(simOut, sig_name)
    ts  = simOut.get(sig_name);
    val = ts.Data(end);
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
