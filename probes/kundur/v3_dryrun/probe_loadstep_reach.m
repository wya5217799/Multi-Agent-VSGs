function out = probe_loadstep_reach(json_out, dP_step_list_sys_pu, t_settle_s)
%PROBE_LOADSTEP_REACH  Phase 2.3 (L1 reformulation) — LoadStep reach at
%Bus 7 / Bus 9 via transient-peak Δω metric.
%
%   The L0 (steady-state) form of this probe found df_steady ≈ 0 because
%   the swing-eq δ-integrator drives ω → 1 at steady regardless of load.
%   See phase2_p23_verdict.md §3.1 for the structural derivation.
%
%   L1 reformulation (probe-only, no model edit):
%     - Run a baseline sim (case A) with both LoadStep blocks open (R=1e9).
%     - For each ΔP_step in dP_step_list_sys_pu and each load bus (7 or 9):
%         change LoadStepN R to V²/ΔP_W from t=0, run sim.
%     - Reach metric:
%         df_peak(t) = max_{src} |omega_src_step(t) − omega_src_base(t)| · fn
%         df_peak    = max_t df_peak(t)
%         t_peak     = argmax_t df_peak(t)
%       This subtracts the common inductor-IC kick (present in both
%       baseline and step) and captures only the load-step-induced excursion.
%     - Gate: df_peak ∈ [0.05, 5] Hz (paper reach band) for at least one
%       ΔP in the list, for each load bus.

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p23_loadstep_reach_L1.json');
end
if nargin < 2 || isempty(dP_step_list_sys_pu)
    dP_step_list_sys_pu = [1.0, 2.0, 5.0, 9.67];     % 100, 200, 500, 967 MW
end
if nargin < 3 || isempty(t_settle_s),     t_settle_s = 60.0; end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);
fn   = 50;
Sbase = 100e6;
Vbase = 230e3;
stop_time_s = t_settle_s;             % full window

R_open = 1e9;

local_reset_disturbances(src_names);

for k = 1:n
    s = src_names{k};
    set_param([mdl '/W_omega_' s], 'MaxDataPoints', 'inf');
end
set_param(mdl, 'StopTime', sprintf('%.6f', stop_time_s));

% --- Run baseline (case A) once ---
set_param([mdl '/LoadStep7'], 'Resistance', sprintf('%.10g', R_open));
set_param([mdl '/LoadStep9'], 'Resistance', sprintf('%.10g', R_open));
so_a = sim(mdl, 'ReturnWorkspaceOutputs', 'on');

base_t   = so_a.get(['omega_ts_' src_names{1}]).Time(:);
base_omg = zeros(numel(base_t), n);
for k = 1:n
    base_omg(:, k) = so_a.get(['omega_ts_' src_names{k}]).Data(:);
end
fprintf('RESULT: P2.3-L1 baseline (R7=R9=open) done, %d samples over %.1fs\n', ...
    numel(base_t), stop_time_s);

% --- Per-bus, per-ΔP sweep ---
nDP   = numel(dP_step_list_sys_pu);
df_b7_peak_hz = zeros(1, nDP);
df_b9_peak_hz = zeros(1, nDP);
t_b7_peak_s   = zeros(1, nDP);
t_b9_peak_s   = zeros(1, nDP);
src_at_b7_peak = repmat({''}, 1, nDP);
src_at_b9_peak = repmat({''}, 1, nDP);
dP_mw_list = dP_step_list_sys_pu * Sbase / 1e6;

t_start_total = tic;
for di = 1:nDP
    dP_pu = dP_step_list_sys_pu(di);
    dP_W  = dP_pu * Sbase;
    R_tgt = Vbase^2 / dP_W;

    % Bus 7 case
    set_param([mdl '/LoadStep7'], 'Resistance', sprintf('%.10g', R_tgt));
    set_param([mdl '/LoadStep9'], 'Resistance', sprintf('%.10g', R_open));
    so_b = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    [df_b7_peak_hz(di), t_b7_peak_s(di), src_at_b7_peak{di}] = ...
        local_peak_df(so_b, src_names, base_t, base_omg, fn);

    % Bus 9 case
    set_param([mdl '/LoadStep7'], 'Resistance', sprintf('%.10g', R_open));
    set_param([mdl '/LoadStep9'], 'Resistance', sprintf('%.10g', R_tgt));
    so_c = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    [df_b9_peak_hz(di), t_b9_peak_s(di), src_at_b9_peak{di}] = ...
        local_peak_df(so_c, src_names, base_t, base_omg, fn);

    fprintf('RESULT: dP=%5.2f sys-pu (%4.0f MW)  bus7 df_peak=%.4f Hz @ t=%.2fs (src %s)  bus9 df_peak=%.4f Hz @ t=%.2fs (src %s)\n', ...
        dP_pu, dP_mw_list(di), df_b7_peak_hz(di), t_b7_peak_s(di), src_at_b7_peak{di}, ...
        df_b9_peak_hz(di), t_b9_peak_s(di), src_at_b9_peak{di});
end
elapsed = toc(t_start_total);

% Reset to open
set_param([mdl '/LoadStep7'], 'Resistance', sprintf('%.10g', R_open));
set_param([mdl '/LoadStep9'], 'Resistance', sprintf('%.10g', R_open));

% Gate: at least one ΔP in list yields df_peak ∈ [0.05, 5] Hz, per bus
in_band_b7 = (df_b7_peak_hz >= 0.05) & (df_b7_peak_hz <= 5.0);
in_band_b9 = (df_b9_peak_hz >= 0.05) & (df_b9_peak_hz <= 5.0);
g_b7 = any(in_band_b7);
g_b9 = any(in_band_b9);
all_pass = g_b7 && g_b9;

fprintf('RESULT: P2.3-L1 gates  bus7_in_band=%d  bus9_in_band=%d  ALL=%d\n', g_b7, g_b9, all_pass);

out.dP_list_sys_pu = dP_step_list_sys_pu;
out.dP_list_mw     = dP_mw_list;
out.df_b7_peak_hz  = df_b7_peak_hz;
out.df_b9_peak_hz  = df_b9_peak_hz;
out.t_b7_peak_s    = t_b7_peak_s;
out.t_b9_peak_s    = t_b9_peak_s;
out.src_at_b7_peak = src_at_b7_peak;
out.src_at_b9_peak = src_at_b9_peak;
out.in_band_b7     = in_band_b7;
out.in_band_b9     = in_band_b9;
out.gates_pass     = all_pass;
out.wall_time_s    = elapsed;

ic = struct();
ic.probe = 'p23_loadstep_reach_L1';
ic.model = mdl;
ic.metric = 'transient_peak_df';
ic.dP_list_sys_pu = dP_step_list_sys_pu;
ic.dP_list_mw     = dP_mw_list;
ic.stop_time_s    = stop_time_s;
ic.src_names      = src_names;
ic.df_b7_peak_hz  = df_b7_peak_hz;
ic.df_b9_peak_hz  = df_b9_peak_hz;
ic.t_b7_peak_s    = t_b7_peak_s;
ic.t_b9_peak_s    = t_b9_peak_s;
ic.src_at_b7_peak = src_at_b7_peak;
ic.src_at_b9_peak = src_at_b9_peak;
ic.in_band_b7     = in_band_b7;
ic.in_band_b9     = in_band_b9;
ic.gate_pass      = all_pass;
ic.gate_def       = 'df_peak = max_t max_src |ω_step(t) − ω_baseline(t)| · fn ∈ [0.05, 5] Hz for at least one ΔP in list';
ic.wall_time_s    = elapsed;

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
for w = 1:2
    assignin('base', sprintf('WindAmp_%d', w), 1.0);
    assignin('base', sprintf('LoadStep_t_%d',   w), 1e9);
    assignin('base', sprintf('LoadStep_amp_%d', w), 0.0);
end
end

function r = local_repo_root()
this_dir = fileparts(mfilename('fullpath'));
r = fileparts(fileparts(fileparts(this_dir)));
end

function [df_peak_hz, t_peak_s, src_label] = local_peak_df(so, src_names, base_t, base_omg, fn)
% Pull omega for each source, interpolate baseline to step's time grid, take
% per-time per-source max-abs-difference, return the global peak.
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
