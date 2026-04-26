function out = probe_30s_zero_action(stop_time_s, json_out, t_settle_s)
%PROBE_30S_ZERO_ACTION  Phase 2.1 — 30 s zero-action stability for kundur_cvs_v3.
%
%   No disturbance: all Pm_step_amp_<i> = 0, WindAmp = 1, LoadStep = 0.
%   ESS M/D held at workspace defaults (M_<i>=24, D_<i>=4.5).
%
%   Gate criteria (steady-region, evaluated over [t_settle_s, stop_time_s]):
%     - omega_pu_per_source ∈ [0.999, 1.001]
%     - |delta_rad_per_source| < π/2 − 0.05 (= 1.5208), full window
%     - |Pe_pu − Pm0_pu| < 0.05 · |Pm0_pu|   (5 % deviation per source)
%     - common-mode omega drift |⟨ω⟩(t_end) − ⟨ω⟩(t_settle)| < 2 e-4 pu
%
%   The first t_settle_s of the trajectory is treated as Phasor-solver
%   inductor warmup (zero-IC current loading) and recorded as `kick`
%   metrics, NOT used for gate evaluation. Default t_settle_s = 5 s.

if nargin < 1 || isempty(stop_time_s), stop_time_s = 30.0; end
if nargin < 3 || isempty(t_settle_s), t_settle_s = 5.0; end
if nargin < 2 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p21_zero_action.json');
end

repo_root = local_repo_root();
addpath(fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models'));

mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl)
    load_system(slx);
end

% Reset workspace knobs to "no disturbance"
src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
for k = 1:numel(src_names)
    s = src_names{k};
    if startsWith(s, 'G')
        assignin('base', sprintf('PmgStep_t_%d', sscanf(s, 'G%d')), 1e9);
        assignin('base', sprintf('PmgStep_amp_%d', sscanf(s, 'G%d')), 0.0);
    else
        assignin('base', sprintf('Pm_step_t_%d',   sscanf(s, 'ES%d')), 1e9);
        assignin('base', sprintf('Pm_step_amp_%d', sscanf(s, 'ES%d')), 0.0);
    end
end
for w = 1:2
    assignin('base', sprintf('WindAmp_%d', w), 1.0);
    assignin('base', sprintf('LoadStep_t_%d',   w), 1e9);
    assignin('base', sprintf('LoadStep_amp_%d', w), 0.0);
end

% Unbound the loggers — we want full 30 s trajectories
for k = 1:numel(src_names)
    s = src_names{k};
    set_param([mdl '/W_omega_' s], 'MaxDataPoints', 'inf');
    set_param([mdl '/W_delta_' s], 'MaxDataPoints', 'inf');
    set_param([mdl '/W_Pe_'    s], 'MaxDataPoints', 'inf');
end

set_param(mdl, 'StopTime', sprintf('%.6f', stop_time_s));

t_start = tic;
so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
elapsed = toc(t_start);

% Pull Pm0 from workspace for per-source Pe gate
Pm0_per_src = zeros(1, numel(src_names));
for k = 1:numel(src_names)
    s = src_names{k};
    if startsWith(s, 'G')
        Pm0_per_src(k) = evalin('base', sprintf('Pmg_%d', sscanf(s, 'G%d')));
    else
        Pm0_per_src(k) = evalin('base', sprintf('Pm_%d',  sscanf(s, 'ES%d')));
    end
end

% Per-source classification
out.src_names    = src_names;
out.stop_time_s  = stop_time_s;
out.wall_time_s  = elapsed;

omega_data = cell(numel(src_names), 1);
delta_data = cell(numel(src_names), 1);
pe_data    = cell(numel(src_names), 1);
t_data     = [];
for k = 1:numel(src_names)
    s = src_names{k};
    ow = so.get(['omega_ts_' s]);
    dw = so.get(['delta_ts_' s]);
    pw = so.get(['Pe_ts_' s]);
    omega_data{k} = ow.Data(:);
    delta_data{k} = dw.Data(:);
    pe_data{k}    = pw.Data(:);
    if isempty(t_data), t_data = ow.Time(:); end
end

n_t = numel(t_data);
out.n_samples_per_logger = n_t;

% Settle-window mask: gates evaluated over [t_settle_s, stop_time_s]
i_settle = find(t_data >= t_settle_s, 1, 'first');
if isempty(i_settle), i_settle = 1; end
mask_steady = i_settle:n_t;

% Per-source aggregate metrics — split into KICK (full window) and STEADY
omega_min        = zeros(1, numel(src_names));   % steady region only
omega_max        = zeros(1, numel(src_names));   % steady region only
omega_end        = zeros(1, numel(src_names));
delta_max_abs    = zeros(1, numel(src_names));   % full window (safety check)
pe_dev_max       = zeros(1, numel(src_names));   % steady region only
pe_dev_pct_max   = zeros(1, numel(src_names));   % steady region only
omega_kick_min   = zeros(1, numel(src_names));   % full window kick metric
omega_kick_max   = zeros(1, numel(src_names));
pe_dev_kick_max  = zeros(1, numel(src_names));
for k = 1:numel(src_names)
    omega_kick_min(k) = min(omega_data{k});
    omega_kick_max(k) = max(omega_data{k});
    omega_min(k) = min(omega_data{k}(mask_steady));
    omega_max(k) = max(omega_data{k}(mask_steady));
    omega_end(k) = omega_data{k}(end);
    delta_max_abs(k) = max(abs(delta_data{k}));      % full window
    pe_dev_full = abs(pe_data{k} - Pm0_per_src(k));
    pe_dev_kick_max(k) = max(pe_dev_full);
    pe_dev_max(k) = max(pe_dev_full(mask_steady));
    if abs(Pm0_per_src(k)) > 0
        pe_dev_pct_max(k) = pe_dev_max(k) / abs(Pm0_per_src(k));
    else
        pe_dev_pct_max(k) = NaN;
    end
end
omega_avg_t = zeros(n_t, 1);
for ti = 1:n_t
    s = 0;
    for k = 1:numel(src_names), s = s + omega_data{k}(ti); end
    omega_avg_t(ti) = s / numel(src_names);
end
common_mode_drift_pu = omega_avg_t(end) - omega_avg_t(i_settle);

% Gate evaluation
g_omega_band = all(omega_min >= 0.999) && all(omega_max <= 1.001);
g_delta_safe = all(delta_max_abs < (pi/2 - 0.05));
g_pe_5pct    = all(pe_dev_pct_max < 0.05);
g_drift      = abs(common_mode_drift_pu) < 2e-4;
all_pass     = g_omega_band && g_delta_safe && g_pe_5pct && g_drift;

out.t_settle_s        = t_settle_s;
out.Pm0_per_src       = Pm0_per_src;
out.omega_min         = omega_min;
out.omega_max         = omega_max;
out.omega_end         = omega_end;
out.delta_max_abs     = delta_max_abs;
out.pe_dev_max_pu     = pe_dev_max;
out.pe_dev_pct_max    = pe_dev_pct_max;
out.omega_kick_min    = omega_kick_min;
out.omega_kick_max    = omega_kick_max;
out.pe_dev_kick_max   = pe_dev_kick_max;
out.common_mode_drift_pu = common_mode_drift_pu;
out.gates = struct( ...
    'omega_in_band',      g_omega_band, ...
    'delta_safe',         g_delta_safe, ...
    'pe_within_5pct',     g_pe_5pct, ...
    'common_mode_drift_ok', g_drift, ...
    'all_pass',           all_pass);

% Pretty print
fprintf('RESULT: P2.1 stop=%.1fs settle=%.1fs wall=%.2fs n_samples=%d\n', ...
    stop_time_s, t_settle_s, elapsed, n_t);
fprintf('RESULT: --- KICK METRICS (t<%.1fs, observation-only) ---\n', t_settle_s);
for k = 1:numel(src_names)
    fprintf('RESULT: %-3s kick omega=[%.6f, %.6f] Pe_dev=%.4f\n', ...
        src_names{k}, omega_kick_min(k), omega_kick_max(k), pe_dev_kick_max(k));
end
fprintf('RESULT: --- STEADY METRICS (t>=%.1fs, gate-evaluated) ---\n', t_settle_s);
for k = 1:numel(src_names)
    fprintf('RESULT: %-3s steady omega=[%.6f, %.6f] |delta|max=%.4f Pe_dev=%.4f (%.2f%%)\n', ...
        src_names{k}, omega_min(k), omega_max(k), delta_max_abs(k), ...
        pe_dev_max(k), 100*pe_dev_pct_max(k));
end
fprintf('RESULT: common_mode_drift_pu=%+.3e (gate < 2e-4)\n', common_mode_drift_pu);
fprintf('RESULT: gates  omega_band=%d delta_safe=%d pe_5pct=%d drift_ok=%d ALL=%d\n', ...
    g_omega_band, g_delta_safe, g_pe_5pct, g_drift, all_pass);

% Write JSON
out_dir = fileparts(json_out);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end

ic = struct();
ic.probe = 'p21_zero_action';
ic.model = mdl;
ic.stop_time_s = stop_time_s;
ic.t_settle_s = t_settle_s;
ic.wall_time_s = elapsed;
ic.n_samples_per_logger = n_t;
ic.Pm0_per_src_sys_pu = Pm0_per_src;
ic.src_names = src_names;
ic.omega_min_steady = omega_min;
ic.omega_max_steady = omega_max;
ic.omega_end = omega_end;
ic.delta_max_abs_rad_full = delta_max_abs;
ic.pe_dev_max_steady_pu = pe_dev_max;
ic.pe_dev_pct_max_steady = pe_dev_pct_max;
ic.kick_omega_min_full = omega_kick_min;
ic.kick_omega_max_full = omega_kick_max;
ic.kick_pe_dev_max_full = pe_dev_kick_max;
ic.common_mode_drift_pu = common_mode_drift_pu;
ic.gates = out.gates;
ic.gate_def = struct( ...
    'omega_band',      '[0.999, 1.001] over [t_settle, t_end]', ...
    'delta_safe',      '|delta| < pi/2 - 0.05 = 1.5208 rad full window', ...
    'pe_within_5pct',  '|Pe - Pm0| / |Pm0| < 0.05 over [t_settle, t_end]', ...
    'common_mode_drift', '|<omega>(t_end) - <omega>(t_settle)| < 2e-4 pu');

fid = fopen(json_out, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);

fprintf('RESULT: wrote %s\n', json_out);

end

function r = local_repo_root()
this_dir = fileparts(mfilename('fullpath'));
% probes/kundur/v3_dryrun → repo root is up 3
r = fileparts(fileparts(fileparts(this_dir)));
end
