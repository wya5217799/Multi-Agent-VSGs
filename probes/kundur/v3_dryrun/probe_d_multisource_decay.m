function out = probe_d_multisource_decay(json_out)
%PROBE_D_MULTISOURCE_DECAY  P2.5c — coordinated multi-source D sensitivity.
%
%   Companion to probe_d_sensitivity_decay.m (single-source ES1 D sweep,
%   τ ratio = 1.44 due to network coupling). Here all 4 ESS D values move
%   together to test whether coordinated modal damping recovers the
%   simple-oscillator τ(D=1.5)/τ(D=7.5) ≈ 5 prediction.
%
%   Method: same +0.2 sys-pu Pm-step on ES1 at t=35 s. M_<i>=24 fixed for
%   all 4 ESS. Sweep D_1=D_2=D_3=D_4 ∈ {1.5, 7.5}. Measure decay-envelope
%   τ on ES1 ω trajectory via log-linear fit on cycle-peaks.
%
%   Pass band on τ ratio: [3, 10].

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p25c_d_multisource_decay.json');
end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);

% Reset disturbances + neutral wind + load steps off
for k = 1:n
    s = src_names{k};
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

set_param([mdl '/W_omega_ES1'], 'MaxDataPoints', 'inf');

M_orig = zeros(1,4); D_orig = zeros(1,4);
for i = 1:4
    M_orig(i) = evalin('base', sprintf('M_%d', i));
    D_orig(i) = evalin('base', sprintf('D_%d', i));
end

t_step = 35.0;
t_post = 15.0;
amp_step = 0.2;
stop_time_s = t_step + t_post;
set_param(mdl, 'StopTime', sprintf('%.6f', stop_time_s));

assignin('base', 'Pm_step_t_1',   t_step);
assignin('base', 'Pm_step_amp_1', amp_step);

D_cases = [1.5, 7.5];
nD = numel(D_cases);
tau_per_D     = zeros(1, nD);
tau_R2_per_D  = zeros(1, nD);
n_peaks_per_D = zeros(1, nD);
first_peak_per_D = zeros(1, nD);

for di = 1:nD
    D = D_cases(di);
    for i = 1:4
        assignin('base', sprintf('M_%d', i), 24.0);
        assignin('base', sprintf('D_%d', i), D);
    end

    so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    ow = so.get('omega_ts_ES1');
    t = ow.Time(:); o = ow.Data(:);

    mask = t >= t_step;
    tt = t(mask) - t_step;
    yy = abs(o(mask) - 1.0);

    n_yy = numel(yy);
    is_peak = false(n_yy, 1);
    for i = 2:n_yy-1
        if yy(i) > yy(i-1) && yy(i) > yy(i+1), is_peak(i) = true; end
    end
    pk_t = tt(is_peak); pk_y = yy(is_peak);
    keep = pk_y > 1e-5; pk_t = pk_t(keep); pk_y = pk_y(keep);

    n_peaks_per_D(di) = numel(pk_y);
    if numel(pk_y) >= 1, first_peak_per_D(di) = pk_y(1); end
    if numel(pk_y) >= 3
        log_y = log(pk_y);
        p = polyfit(pk_t, log_y, 1);
        if p(1) < 0, tau_per_D(di) = -1.0/p(1); else, tau_per_D(di) = NaN; end
        y_fit = polyval(p, pk_t);
        ss_res = sum((log_y - y_fit).^2);
        ss_tot = sum((log_y - mean(log_y)).^2);
        if ss_tot > 0, tau_R2_per_D(di) = 1 - ss_res/ss_tot; else, tau_R2_per_D(di) = NaN; end
    else
        tau_per_D(di) = NaN; tau_R2_per_D(di) = NaN;
    end
    fprintf('RESULT: P2.5c D_all=%.2f n_peaks=%d tau=%.4f s R^2=%.3f first_peak=%.3e\n', ...
        D, n_peaks_per_D(di), tau_per_D(di), tau_R2_per_D(di), first_peak_per_D(di));
end

% Restore
for i = 1:4
    assignin('base', sprintf('M_%d', i), M_orig(i));
    assignin('base', sprintf('D_%d', i), D_orig(i));
end
assignin('base', 'Pm_step_t_1', 1e9);
assignin('base', 'Pm_step_amp_1', 0.0);

tau_ratio = tau_per_D(1) / tau_per_D(2);
g_in_band = ~isnan(tau_ratio) && tau_ratio >= 3.0 && tau_ratio <= 10.0;
g_R2 = all(tau_R2_per_D >= 0.7);
g_above_noise = all(n_peaks_per_D >= 3);
all_pass = g_in_band && g_R2 && g_above_noise;

fprintf('RESULT: P2.5c tau ratio D_all=1.5/D_all=7.5 = %.3f (expect ≈ 5, band [3, 10])\n', tau_ratio);
fprintf('RESULT: prior single-source ratio (P2.5b-L1) = 1.44 → coordinated improvement = %.2fx\n', tau_ratio / 1.44);
fprintf('RESULT: P2.5c gates  in_band=%d  R^2_ok=%d  above_noise=%d  ALL=%d\n', ...
    g_in_band, g_R2, g_above_noise, all_pass);

out.D_cases = D_cases;
out.tau_per_D = tau_per_D;
out.tau_R2_per_D = tau_R2_per_D;
out.n_peaks_per_D = n_peaks_per_D;
out.first_peak_per_D = first_peak_per_D;
out.tau_ratio = tau_ratio;
out.improvement_vs_single_source = tau_ratio / 1.44;
out.gate_pass = all_pass;

ic = struct();
ic.probe = 'p25c_d_multisource_decay';
ic.model = mdl;
ic.controlled_src = 'ES1 (Pm step injection)';
ic.observed_src = 'ES1 omega trajectory';
ic.t_step_s = t_step;
ic.amp_step_sys_pu = amp_step;
ic.M_fixed = 24.0;
ic.D_sweep_all_ESS = D_cases;
ic.tau_per_D_s = tau_per_D;
ic.tau_R2_per_D = tau_R2_per_D;
ic.n_peaks_per_D = n_peaks_per_D;
ic.first_peak_per_D = first_peak_per_D;
ic.tau_ratio = tau_ratio;
ic.expected_ratio = 5.0;
ic.tolerance_band = [3.0 10.0];
ic.prior_single_source_ratio = 1.44;
ic.coordinated_improvement_factor = tau_ratio / 1.44;
ic.gates = struct( ...
    'tau_ratio_in_band',  g_in_band, ...
    'r2_above_0p7',       g_R2, ...
    'above_noise_3plus_peaks', g_above_noise, ...
    'all_pass',           all_pass);
ic.gate_def = struct( ...
    'metric',     'tau via log-linear fit on cycle-peak envelope of |omega_ES1 - 1| post-step', ...
    'expected',   'all-ESS coordinated D sweep recovers tau ratio closer to simple-oscillator M/D = 5', ...
    'tolerance',  '[3, 10]');

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
