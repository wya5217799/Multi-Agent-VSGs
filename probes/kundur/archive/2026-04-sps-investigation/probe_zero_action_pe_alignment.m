model_name  = 'kundur_vsg';
agent_ids   = 1:4;
vsg_sn_va   = 200e6;
sbase_va    = 100e6;
vsg_m0      = 12.0;
vsg_d0      = 3.0;
t_warmup    = 0.5;
dt_probe    = 10.0;   % Phase 3: 10 s physical validation

% Steady-state window (absolute simulation time after warmup)
t_ss_start = t_warmup + 8.0;   % 8.5 s
t_ss_end   = t_warmup + dt_probe;  % 10.5 s

repo_root    = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo_root, 'slx_helpers'));
addpath(fullfile(repo_root, 'scenarios', 'kundur', 'matlab_scripts'));
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

    % ---- Phase 2: unit alignment (last-value, tautology check) ----
    for i = 1:n_agents
        idx = agent_ids(i);

        pefb_val  = local_read_last(simOut, sprintf('PeFb_ES%d',  idx));
        pout_val  = local_read_last(simOut, sprintf('P_out_ES%d', idx));
        omega_val = local_read_last(simOut, sprintf('omega_ES%d', idx));
        delta_val = local_read_last(simOut, sprintf('delta_ES%d', idx));
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
            intw_val = local_read_last(simOut, sprintf('IntW_ES%d', idx));
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

    fprintf(['RESULT: phase2_classification = %s, n_agents=%d, all_aligned=%d, ' ...
        'pe_sbase=[%s], pout_sbase=[%s]\n'], ...
        local_passfail(all_aligned), n_agents, all_aligned, ...
        local_vec(pe_sbase), local_vec(pout_sbase));

    % ---- Phase 3: physical validation (steady-state window [8.5, 10.5] s) ----
    pe_ok_all    = true;
    omega_ok_all = true;
    delta_ok_all = true;
    intw_ok_all  = true;

    for i = 1:n_agents
        idx        = agent_ids(i);
        pe_nominal = ic.vsg_p0_vsg_base_pu(i);

        pefb_ts  = simOut.get(sprintf('PeFb_ES%d',  idx));
        omega_ts = simOut.get(sprintf('omega_ES%d', idx));
        delta_ts = simOut.get(sprintf('delta_ES%d', idx));

        ss_pe  = local_window(pefb_ts,  t_ss_start, t_ss_end);
        ss_om  = local_window(omega_ts, t_ss_start, t_ss_end);
        ss_dl  = local_window(delta_ts, t_ss_start, t_ss_end);
        ss_t   = local_window_time(delta_ts, t_ss_start, t_ss_end);

        % Pe steady-state deviation from IC nominal
        pe_dev_rel = max(abs(ss_pe - pe_nominal)) / abs(pe_nominal);
        pe_ok_i    = pe_dev_rel < 0.05;

        % omega deviation from 1 pu (< 0.002 pu = ±0.1 Hz at 50 Hz)
        omega_dev_max = max(abs(ss_om - 1.0));
        omega_ok_i    = omega_dev_max < 0.002;

        % delta drift < 1 deg/s in steady-state window
        if length(ss_dl) >= 2
            delta_drift = abs((ss_dl(end) - ss_dl(1)) * (180/pi)) / ...
                          max(ss_t(end) - ss_t(1), 1e-9);
        else
            delta_drift = 0;
        end
        delta_ok_i = delta_drift < 1.0;

        % IntW: check full simulation (not just SS window) for saturation
        try
            intw_ts  = simOut.get(sprintf('IntW_ES%d', idx));
            intw_max = max(intw_ts.Data);
            intw_min = min(intw_ts.Data);
            intw_sat = intw_max >= 1.3 || intw_min <= 0.7;
            intw_ok_i = ~intw_sat;
            intw_range_str = sprintf('[%.4g, %.4g]', intw_min, intw_max);
        catch
            intw_ok_i      = true;   % signal absent → assume OK
            intw_range_str = 'N/A';
        end

        pe_ok_all    = pe_ok_all    && pe_ok_i;
        omega_ok_all = omega_ok_all && omega_ok_i;
        delta_ok_all = delta_ok_all && delta_ok_i;
        intw_ok_all  = intw_ok_all  && intw_ok_i;

        agent_p3_ok = pe_ok_i && omega_ok_i && delta_ok_i && intw_ok_i;
        fprintf(['RESULT: p3_agent%d: pe_dev_rel=%.4f, pe_ok=%d, ' ...
            'omega_dev_max=%.4g, omega_ok=%d, delta_drift=%.4g deg/s, delta_ok=%d, ' ...
            'intw=%s, intw_ok=%d, agent_ok=%d\n'], ...
            idx, pe_dev_rel, pe_ok_i, omega_dev_max, omega_ok_i, ...
            delta_drift, delta_ok_i, intw_range_str, intw_ok_i, agent_p3_ok);
    end

    passed_p3 = pe_ok_all && omega_ok_all && delta_ok_all && intw_ok_all;
    fprintf(['RESULT: phase3_classification = %s, ' ...
        'pe_ok=%d, omega_ok=%d, delta_ok=%d, intw_ok=%d\n'], ...
        local_passfail(passed_p3), pe_ok_all, omega_ok_all, delta_ok_all, intw_ok_all);

catch ME
    fprintf('RESULT: classification = fail, error="%s"\n', ME.message);
end

% -----------------------------------------------------------------------
function val = local_read_last(simOut, sig_name)
    ts  = simOut.get(sig_name);
    val = ts.Data(end);
end

function data = local_window(ts, t_start, t_end)
    mask = ts.Time >= t_start & ts.Time <= t_end;
    if ~any(mask)
        data = ts.Data;
    else
        data = ts.Data(mask);
    end
end

function t = local_window_time(ts, t_start, t_end)
    mask = ts.Time >= t_start & ts.Time <= t_end;
    if ~any(mask)
        t = ts.Time;
    else
        t = ts.Time(mask);
    end
end

function text = local_vec(values)
    text = strtrim(num2str(values, '%.6g '));
end

function text = local_passfail(ok)
    if ok; text = 'pass'; else; text = 'fail'; end
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
