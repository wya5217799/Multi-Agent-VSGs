function out = probe_logger_readout_sanity(json_out)
%PROBE_LOGGER_READOUT_SANITY  P3.0c — verify v3 .slx logger names match
%   the slx_step_and_read_cvs.m helper contract AND that the bridge dispatch
%   path returns non-empty finite omega/Pe/delta for all 4 ESS agents.
%
%   READ-ONLY against helper / bridge / env / SAC / training. Only this probe
%   file and a JSON output are written.
%
%   Pass criteria:
%     1. simOut.get('omega_ts_<int>') for int in 1..4 returns non-empty Timeseries.
%     2. simOut.get('delta_ts_<int>') / 'Pe_ts_<int>' likewise.
%     3. SG diagnostic loggers omega_ts_G1..G3 (etc.) also non-empty.
%     4. Direct call to slx_step_and_read_cvs(...) returns
%        state.omega(1..4) finite + non-zero (zero indicates the empty-key
%        path that motivated this fix).

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase3', 'p30c_logger_readout_sanity.json');
end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

% Reset disturbances so simOut state matches NR steady (ω near 1)
src_names_all = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
for k = 1:numel(src_names_all)
    s = src_names_all{k};
    if startsWith(s, 'G')
        assignin('base', sprintf('PmgStep_t_%d',   sscanf(s, 'G%d')), 1e9);
        assignin('base', sprintf('PmgStep_amp_%d', sscanf(s, 'G%d')), 0.0);
    else
        assignin('base', sprintf('Pm_step_t_%d',   sscanf(s, 'ES%d')), 1e9);
        assignin('base', sprintf('Pm_step_amp_%d', sscanf(s, 'ES%d')), 0.0);
    end
end
for w = 1:2, assignin('base', sprintf('WindAmp_%d', w), 1.0); end
set_param([mdl '/LoadStep7'], 'Resistance', '1e9');
set_param([mdl '/LoadStep9'], 'Resistance', '1e9');

set_param(mdl, 'StopTime', '0.5');

t_start = tic;
so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
elapsed_sim = toc(t_start);

% Tier 1: ESS integer-suffix loggers (helper contract)
ess_int_names = {{'omega_ts_1','delta_ts_1','Pe_ts_1'}, ...
                 {'omega_ts_2','delta_ts_2','Pe_ts_2'}, ...
                 {'omega_ts_3','delta_ts_3','Pe_ts_3'}, ...
                 {'omega_ts_4','delta_ts_4','Pe_ts_4'}};
ess_present = true(4, 3);
ess_finite  = true(4, 3);
ess_values  = nan(4, 3);
for i = 1:4
    for ch = 1:3
        nm = ess_int_names{i}{ch};
        ts = so.get(nm);
        if isempty(ts)
            ess_present(i, ch) = false;
            ess_finite(i, ch)  = false;
        else
            v = double(ts.Data(end));
            ess_values(i, ch) = v;
            if ~isfinite(v)
                ess_finite(i, ch) = false;
            end
        end
    end
end

% Tier 2: SG diagnostic loggers (string suffix preserved)
sg_str_names = {{'omega_ts_G1','delta_ts_G1','Pe_ts_G1'}, ...
                {'omega_ts_G2','delta_ts_G2','Pe_ts_G2'}, ...
                {'omega_ts_G3','delta_ts_G3','Pe_ts_G3'}};
sg_present = true(3, 3);
sg_finite  = true(3, 3);
sg_values  = nan(3, 3);
for g = 1:3
    for ch = 1:3
        nm = sg_str_names{g}{ch};
        ts = so.get(nm);
        if isempty(ts)
            sg_present(g, ch) = false;
            sg_finite(g, ch)  = false;
        else
            v = double(ts.Data(end));
            sg_values(g, ch) = v;
            if ~isfinite(v)
                sg_finite(g, ch) = false;
            end
        end
    end
end

% Tier 3: legacy ES-suffix loggers MUST be ABSENT (proves rename worked).
% simOut.get() throws on unknown field in this Simulink version; treat
% the throw as "absent", and a successful get with non-empty data as "present".
legacy_es_names = {'omega_ts_ES1','omega_ts_ES2','omega_ts_ES3','omega_ts_ES4'};
legacy_present = false(1, 4);
for i = 1:4
    try
        ts = so.get(legacy_es_names{i});
        legacy_present(i) = ~isempty(ts);
    catch
        legacy_present(i) = false;   % field not in simOut → rename worked
    end
end

% Tier 4: helper round-trip — call slx_step_and_read_cvs with agent_ids 1:4
% This is the actual bridge dispatch call. Build a minimal cfg struct
% matching what BridgeConfig populates (m_var_template, d_var_template).
cfg = struct();
cfg.m_var_template = 'M_{idx}';
cfg.d_var_template = 'D_{idx}';
agent_ids = 1:4;
M_values = [24 24 24 24];
D_values = [4.5 4.5 4.5 4.5];
sbase_va = 100e6;
t_step  = 1.0;
Pe_prev = zeros(1, 4);
delta_prev_deg = zeros(1, 4);

addpath(fullfile(repo_root, 'slx_helpers', 'vsg_bridge'));
addpath(fullfile(repo_root, 'slx_helpers'));

helper_state = struct();
helper_status = struct();
helper_omega_finite = false(1, 4);
helper_omega_nonzero = false(1, 4);
try
    [helper_state, helper_status] = slx_step_and_read_cvs( ...
        mdl, agent_ids, M_values, D_values, t_step, sbase_va, cfg, ...
        Pe_prev, delta_prev_deg);
    for i = 1:4
        helper_omega_finite(i) = isfinite(helper_state.omega(i));
        helper_omega_nonzero(i) = abs(helper_state.omega(i)) > 1e-12;
    end
catch ME
    helper_status.success = false;
    helper_status.error   = ME.message;
end

% Pass criteria
g_ess_all_present = all(ess_present(:));
g_ess_all_finite  = all(ess_finite(:));
g_sg_all_present  = all(sg_present(:));
g_sg_all_finite   = all(sg_finite(:));
g_legacy_absent   = ~any(legacy_present);
g_helper_ok       = isfield(helper_status, 'success') && helper_status.success && ...
                    all(helper_omega_finite) && all(helper_omega_nonzero);
all_pass = g_ess_all_present && g_ess_all_finite && g_sg_all_present && ...
           g_sg_all_finite && g_legacy_absent && g_helper_ok;

% Report
fprintf('RESULT: P3.0c logger readout sanity (sim wall %.2fs)\n', elapsed_sim);
fprintf('RESULT: ESS integer loggers present=%d finite=%d (4 sources x 3 channels)\n', ...
    g_ess_all_present, g_ess_all_finite);
fprintf('RESULT: SG  string  loggers present=%d finite=%d (3 sources x 3 channels)\n', ...
    g_sg_all_present, g_sg_all_finite);
fprintf('RESULT: Legacy ES-suffix loggers absent=%d (rename verified)\n', g_legacy_absent);
fprintf('RESULT: Helper round-trip slx_step_and_read_cvs success=%d omega_finite_all=%d omega_nonzero_all=%d\n', ...
    isfield(helper_status, 'success') && helper_status.success, ...
    all(helper_omega_finite), all(helper_omega_nonzero));
if isfield(helper_state, 'omega')
    fprintf('RESULT: helper omega = [%+.6f %+.6f %+.6f %+.6f]\n', helper_state.omega(:)');
    fprintf('RESULT: helper Pe    = [%+.6f %+.6f %+.6f %+.6f]\n', helper_state.Pe(:)');
    fprintf('RESULT: helper delta = [%+.6f %+.6f %+.6f %+.6f] rad\n', helper_state.delta(:)');
end
fprintf('RESULT: ALL_PASS=%d\n', all_pass);

out.elapsed_sim_s = elapsed_sim;
out.ess_present = ess_present;
out.ess_finite  = ess_finite;
out.ess_values  = ess_values;
out.sg_present  = sg_present;
out.sg_finite   = sg_finite;
out.sg_values   = sg_values;
out.legacy_present = legacy_present;
out.helper_state = helper_state;
out.helper_status = helper_status;
out.helper_omega_finite = helper_omega_finite;
out.helper_omega_nonzero = helper_omega_nonzero;
out.all_pass = all_pass;

ic = struct();
ic.probe = 'p30c_logger_readout_sanity';
ic.model = mdl;
ic.elapsed_sim_s = elapsed_sim;
ic.ess_int_names_checked = {ess_int_names{:}};
ic.ess_present = ess_present;
ic.ess_finite  = ess_finite;
ic.ess_values_at_t_end = ess_values;
ic.sg_str_names_checked = {sg_str_names{:}};
ic.sg_present  = sg_present;
ic.sg_finite   = sg_finite;
ic.sg_values_at_t_end = sg_values;
ic.legacy_es_names_must_be_absent = legacy_es_names;
ic.legacy_present = legacy_present;
ic.helper_omega = helper_state.omega(:)';
ic.helper_Pe    = helper_state.Pe(:)';
ic.helper_delta_rad = helper_state.delta(:)';
ic.helper_status_success = helper_status.success;
ic.gates = struct( ...
    'ess_all_present',  g_ess_all_present, ...
    'ess_all_finite',   g_ess_all_finite, ...
    'sg_all_present',   g_sg_all_present, ...
    'sg_all_finite',    g_sg_all_finite, ...
    'legacy_absent',    g_legacy_absent, ...
    'helper_round_trip_ok', g_helper_ok, ...
    'all_pass',         all_pass);

out_dir = fileparts(json_out);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(json_out, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);
fprintf('RESULT: wrote %s\n', json_out);

end

function r = local_repo_root()
this_dir = fileparts(mfilename('fullpath'));
r = fileparts(fileparts(fileparts(this_dir)));
end
