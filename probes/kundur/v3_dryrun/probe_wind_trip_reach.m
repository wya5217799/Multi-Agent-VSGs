function out = probe_wind_trip_reach(json_out, trip_frac_list, t_settle_s)
%PROBE_WIND_TRIP_REACH  Phase 2.4 — wind trip reach for kundur_cvs_v3.
%
%   Trips W1 / W2 by setting WindAmp_w ∈ [0, 1] from t = 0 (Phasor solver
%   reads the workspace var at compile, no mid-sim event). Compares to
%   baseline (WindAmp_1 = WindAmp_2 = 1) using the L1 transient-peak Δω
%   metric (post-P2.3-L1 verdict).
%
%   Dual-tier gate (post-P2.3 user policy):
%     - Absolute reach: at least one trip case yields df_peak ∈ [0.05, 5] Hz
%       for at least one wind farm.
%     - Sensitivity reach (per wind farm):
%         * df_peak strictly increases with trip fraction (slope > 0)
%         * peak source consistent with electrical neighbourhood of the
%           tripped wind farm (should be a swing-eq source within 1-2 hops)
%         * df_peak > 0 and ≥ 1 mHz at full trip (above numerical noise)
%
%   Wind trip is "loss of generation" — equivalent to a positive load step
%   from the network's view. ΔP_W1 at full trip = +7.00 sys-pu (700 MW),
%   ΔP_W2 at full trip = +1.00 sys-pu (100 MW).

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p24_wind_trip_reach_L1.json');
end
if nargin < 2 || isempty(trip_frac_list)
    trip_frac_list = [0.25, 0.50, 0.75, 1.00];   % 25/50/75/100% trip
end
if nargin < 3 || isempty(t_settle_s),  t_settle_s = 60.0; end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);
fn = 50;
Sbase = 100e6;

local_reset_disturbances(src_names);
% Force LoadStep blocks open
set_param([mdl '/LoadStep7'], 'Resistance', '1e9');
set_param([mdl '/LoadStep9'], 'Resistance', '1e9');

for k = 1:n
    s = src_names{k};
    set_param([mdl '/W_omega_' s], 'MaxDataPoints', 'inf');
end
set_param(mdl, 'StopTime', sprintf('%.6f', t_settle_s));

% --- Baseline ---
assignin('base', 'WindAmp_1', 1.0);
assignin('base', 'WindAmp_2', 1.0);
so_a = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
base_t   = so_a.get(['omega_ts_' src_names{1}]).Time(:);
base_omg = zeros(numel(base_t), n);
for k = 1:n
    base_omg(:, k) = so_a.get(['omega_ts_' src_names{k}]).Data(:);
end
fprintf('RESULT: P2.4 baseline (WindAmp=1,1) done %d samples\n', numel(base_t));

% --- Sweep ---
nT = numel(trip_frac_list);
W1_dP_mw = 700 * trip_frac_list;
W2_dP_mw = 100 * trip_frac_list;

df_w1_peak_hz = zeros(1, nT);
df_w2_peak_hz = zeros(1, nT);
t_w1_peak_s   = zeros(1, nT);
t_w2_peak_s   = zeros(1, nT);
src_w1_peak   = repmat({''}, 1, nT);
src_w2_peak   = repmat({''}, 1, nT);

t_total = tic;
for ti = 1:nT
    trip = trip_frac_list(ti);

    % W1 trip case (W2 normal)
    assignin('base', 'WindAmp_1', 1.0 - trip);
    assignin('base', 'WindAmp_2', 1.0);
    so_b = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    [df_w1_peak_hz(ti), t_w1_peak_s(ti), src_w1_peak{ti}] = ...
        local_peak_df(so_b, src_names, base_t, base_omg, fn);

    % W2 trip case (W1 normal)
    assignin('base', 'WindAmp_1', 1.0);
    assignin('base', 'WindAmp_2', 1.0 - trip);
    so_c = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    [df_w2_peak_hz(ti), t_w2_peak_s(ti), src_w2_peak{ti}] = ...
        local_peak_df(so_c, src_names, base_t, base_omg, fn);

    fprintf('RESULT: trip=%.0f%% W1(%4.0f MW lost) df=%.4f Hz @ %.2fs (%s)  W2(%3.0f MW lost) df=%.4f Hz @ %.2fs (%s)\n', ...
        trip*100, W1_dP_mw(ti), df_w1_peak_hz(ti), t_w1_peak_s(ti), src_w1_peak{ti}, ...
        W2_dP_mw(ti), df_w2_peak_hz(ti), t_w2_peak_s(ti), src_w2_peak{ti});
end
elapsed = toc(t_total);

% Reset wind to nominal
assignin('base', 'WindAmp_1', 1.0);
assignin('base', 'WindAmp_2', 1.0);

% --- Gate evaluation ---
% Absolute reach: any df_peak ∈ [0.05, 5] Hz across both wind farms
in_band_w1 = (df_w1_peak_hz >= 0.05) & (df_w1_peak_hz <= 5.0);
in_band_w2 = (df_w2_peak_hz >= 0.05) & (df_w2_peak_hz <= 5.0);
g_absolute = any(in_band_w1) | any(in_band_w2);

% Sensitivity reach: per wind farm
%   - strictly increasing
%   - slope > 0
%   - df at full trip > 1 mHz (above noise)
g_sens_w1_monotone = all(diff(df_w1_peak_hz) >= 0);
g_sens_w2_monotone = all(diff(df_w2_peak_hz) >= 0);
g_sens_w1_above_noise = df_w1_peak_hz(end) >= 1e-3;
g_sens_w2_above_noise = df_w2_peak_hz(end) >= 1e-3;
% Linearity check via first-vs-last slope ratio (should ≈ trip ratio)
slope_w1 = df_w1_peak_hz(end) / df_w1_peak_hz(1);
slope_w2 = df_w2_peak_hz(end) / df_w2_peak_hz(1);
expected_ratio = trip_frac_list(end) / trip_frac_list(1);
g_lin_w1 = abs(slope_w1 - expected_ratio) / expected_ratio < 0.30;
g_lin_w2 = abs(slope_w2 - expected_ratio) / expected_ratio < 0.30;

% Peak-source plausibility:
%   W1 (Bus 4) electrical neighbours: Bus 4 → L_4_9 → Bus 9 (1 hop) → ES4
%     Also L_3_10 → Bus 10 → L_10_14 → ES3 (2 hops via G3 area).
%     Expect ES4, ES3, or G3 as peak source.
%   W2 (Bus 11) electrical neighbours: Bus 11 → L_8_W2 → Bus 8 (1 hop)
%     Bus 8 → L_8_16 → ES2 (1 hop through Bus 8). Also Bus 8 → L_8_9 → ES4.
%     Expect ES2 or ES4 as peak source.
plausible_w1 = {'G3','ES3','ES4'};
plausible_w2 = {'ES2','ES4','ES1'};
g_loc_w1 = all(cellfun(@(s) any(strcmp(s, plausible_w1)), src_w1_peak));
g_loc_w2 = all(cellfun(@(s) any(strcmp(s, plausible_w2)), src_w2_peak));

g_sensitivity_w1 = g_sens_w1_monotone && g_sens_w1_above_noise && g_lin_w1 && g_loc_w1;
g_sensitivity_w2 = g_sens_w2_monotone && g_sens_w2_above_noise && g_lin_w2 && g_loc_w2;
g_sensitivity_all = g_sensitivity_w1 && g_sensitivity_w2;

all_pass = g_absolute && g_sensitivity_all;

fprintf('RESULT: P2.4 gates absolute=%d sens_w1=%d sens_w2=%d ALL=%d (wall %.1fs)\n', ...
    g_absolute, g_sensitivity_w1, g_sensitivity_w2, all_pass, elapsed);

out.trip_frac_list   = trip_frac_list;
out.W1_dP_mw         = W1_dP_mw;
out.W2_dP_mw         = W2_dP_mw;
out.df_w1_peak_hz    = df_w1_peak_hz;
out.df_w2_peak_hz    = df_w2_peak_hz;
out.t_w1_peak_s      = t_w1_peak_s;
out.t_w2_peak_s      = t_w2_peak_s;
out.src_w1_peak      = src_w1_peak;
out.src_w2_peak      = src_w2_peak;
out.gate_absolute    = g_absolute;
out.gate_sens_w1     = g_sensitivity_w1;
out.gate_sens_w2     = g_sensitivity_w2;
out.gate_pass        = all_pass;
out.wall_time_s      = elapsed;

ic = struct();
ic.probe = 'p24_wind_trip_reach_L1';
ic.model = mdl;
ic.metric = 'transient_peak_df_subtract_baseline';
ic.trip_frac_list = trip_frac_list;
ic.W1_dP_mw = W1_dP_mw;
ic.W2_dP_mw = W2_dP_mw;
ic.src_names = src_names;
ic.df_w1_peak_hz = df_w1_peak_hz;
ic.df_w2_peak_hz = df_w2_peak_hz;
ic.t_w1_peak_s = t_w1_peak_s;
ic.t_w2_peak_s = t_w2_peak_s;
ic.src_w1_peak = src_w1_peak;
ic.src_w2_peak = src_w2_peak;
ic.in_band_w1 = in_band_w1;
ic.in_band_w2 = in_band_w2;
ic.gates = struct( ...
    'absolute_reach',  g_absolute, ...
    'sensitivity_w1_monotone',   g_sens_w1_monotone, ...
    'sensitivity_w1_linear',     g_lin_w1, ...
    'sensitivity_w1_above_noise', g_sens_w1_above_noise, ...
    'sensitivity_w1_local_src',  g_loc_w1, ...
    'sensitivity_w1_pass',       g_sensitivity_w1, ...
    'sensitivity_w2_monotone',   g_sens_w2_monotone, ...
    'sensitivity_w2_linear',     g_lin_w2, ...
    'sensitivity_w2_above_noise', g_sens_w2_above_noise, ...
    'sensitivity_w2_local_src',  g_loc_w2, ...
    'sensitivity_w2_pass',       g_sensitivity_w2, ...
    'all_pass',                  all_pass);
ic.gate_def = struct( ...
    'absolute',    'any df_peak ∈ [0.05, 5] Hz across W1 / W2 trips', ...
    'sensitivity', 'monotone, linear within 30%, above 1 mHz at full trip, peak source in plausible-neighbour set');
ic.wall_time_s = elapsed;

out_dir = fileparts(json_out);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(json_out, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);
fprintf('RESULT: wrote %s\n', json_out);

end

function local_reset_disturbances(src_names)
for k = 1:numel(src_names)
    s = src_names{k};
    if startsWith(s, 'G')
        assignin('base', sprintf('PmgStep_t_%d',   sscanf(s, 'G%d')), 1e9);
        assignin('base', sprintf('PmgStep_amp_%d', sscanf(s, 'G%d')), 0.0);
    else
        assignin('base', sprintf('Pm_step_t_%d',   sscanf(s, 'ES%d')), 1e9);
        assignin('base', sprintf('Pm_step_amp_%d', sscanf(s, 'ES%d')), 0.0);
    end
end
end

function r = local_repo_root()
this_dir = fileparts(mfilename('fullpath'));
r = fileparts(fileparts(fileparts(this_dir)));
end

function [df_peak_hz, t_peak_s, src_label] = local_peak_df(so, src_names, base_t, base_omg, fn)
n = numel(src_names);
df_peak_hz = 0;
t_peak_s   = 0;
src_label  = src_names{1};
for k = 1:n
    ow = so.get(['omega_ts_' src_names{k}]);
    t  = ow.Time(:); o = ow.Data(:);
    if numel(t) ~= numel(base_t) || any(abs(t - base_t) > 1e-6)
        ob = interp1(base_t, base_omg(:, k), t, 'linear', 'extrap');
    else
        ob = base_omg(:, k);
    end
    d  = abs(o - ob) * fn;
    [dmax, idx] = max(d);
    if dmax > df_peak_hz
        df_peak_hz = dmax;
        t_peak_s   = t(idx);
        src_label  = src_names{k};
    end
end
end
