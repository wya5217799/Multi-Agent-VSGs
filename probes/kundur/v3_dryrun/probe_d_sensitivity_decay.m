function out = probe_d_sensitivity_decay(json_out)
%PROBE_D_SENSITIVITY_DECAY  P2.5b-L1 — D sensitivity via post-peak decay tau.
%
%   Same ES1 +0.2 sys-pu Pm-step setup as P2.5. M_1 fixed at 24 (H=12).
%   Sweep D_1 ∈ {1.5, 7.5}.
%   Metric: post-peak |ω−1| envelope decay time constant tau, extracted by
%   linear fit on log of successive cycle-peak amplitudes.
%   Predicted ratio: tau(D=1.5) / tau(D=7.5) ≈ 5  (tau ∝ M/D).
%   Pass band: [3, 10].

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p25b_d_sensitivity_decay.json');
end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);

% Reset all step amps + neutral wind + load steps off
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
M1_orig = evalin('base', 'M_1');
D1_orig = evalin('base', 'D_1');

t_step = 35.0;
t_post = 15.0;       % long post-step window so multiple cycles visible
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
peak_amp_per_D = cell(1, nD);
peak_t_per_D   = cell(1, nD);

for di = 1:nD
    D = D_cases(di);
    assignin('base', 'M_1', 24.0);
    assignin('base', 'D_1', D);

    so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    ow = so.get('omega_ts_ES1');
    t = ow.Time(:); o = ow.Data(:);

    % Restrict to post-step window
    mask = t >= t_step;
    tt = t(mask) - t_step;
    yy = abs(o(mask) - 1.0);   % envelope = |ω − 1|

    % Find local maxima of yy (successive cycle peaks)
    %   Manual: peaks at i where yy(i) > yy(i-1) and yy(i) > yy(i+1)
    n_yy = numel(yy);
    is_peak = false(n_yy, 1);
    for i = 2:n_yy-1
        if yy(i) > yy(i-1) && yy(i) > yy(i+1)
            is_peak(i) = true;
        end
    end
    pk_t = tt(is_peak);
    pk_y = yy(is_peak);

    % Filter to peaks ABOVE noise floor (1e-5 pu)
    keep = pk_y > 1e-5;
    pk_t = pk_t(keep);
    pk_y = pk_y(keep);

    n_peaks_per_D(di) = numel(pk_y);
    peak_amp_per_D{di} = pk_y(:)';
    peak_t_per_D{di}   = pk_t(:)';

    if numel(pk_y) >= 3
        % Fit log(pk_y) ≈ -t/tau + c  → slope = -1/tau
        log_y = log(pk_y);
        p = polyfit(pk_t, log_y, 1);
        slope = p(1);
        if slope < 0
            tau_per_D(di) = -1.0 / slope;
        else
            tau_per_D(di) = NaN;
        end
        y_fit = polyval(p, pk_t);
        ss_res = sum((log_y - y_fit).^2);
        ss_tot = sum((log_y - mean(log_y)).^2);
        if ss_tot > 0
            tau_R2_per_D(di) = 1 - ss_res / ss_tot;
        else
            tau_R2_per_D(di) = NaN;
        end
    else
        tau_per_D(di) = NaN;
        tau_R2_per_D(di) = NaN;
    end

    fprintf('RESULT: P2.5b-L1 D=%.2f  n_peaks=%d  tau=%.4f s  R^2=%.3f\n', ...
        D, n_peaks_per_D(di), tau_per_D(di), tau_R2_per_D(di));
    if numel(pk_y) >= 1
        fprintf('RESULT:   peak amplitudes: %s\n', mat2str(pk_y(:)', 4));
    end
end

% Restore + reset disturbance
assignin('base', 'M_1', M1_orig);
assignin('base', 'D_1', D1_orig);
assignin('base', 'Pm_step_t_1',   1e9);
assignin('base', 'Pm_step_amp_1', 0.0);

% Gate
tau_ratio = tau_per_D(1) / tau_per_D(2);
expected_ratio = 5.0;
g_in_band = ~isnan(tau_ratio) && tau_ratio >= 3.0 && tau_ratio <= 10.0;
g_R2 = all(tau_R2_per_D >= 0.7);
g_above_noise = all(n_peaks_per_D >= 3);
all_pass = g_in_band && g_R2 && g_above_noise;

fprintf('RESULT: P2.5b-L1 tau ratio D=1.5/D=7.5 = %.3f (expect ≈ %.1f, band [3, 10])\n', ...
    tau_ratio, expected_ratio);
fprintf('RESULT: P2.5b-L1 gates  in_band=%d  R^2_ok=%d  above_noise=%d  ALL=%d\n', ...
    g_in_band, g_R2, g_above_noise, all_pass);

out.D_cases = D_cases;
out.tau_per_D = tau_per_D;
out.tau_R2_per_D = tau_R2_per_D;
out.n_peaks_per_D = n_peaks_per_D;
out.tau_ratio = tau_ratio;
out.expected_ratio = expected_ratio;
out.gate_pass = all_pass;

ic = struct();
ic.probe = 'p25b_d_sensitivity_decay';
ic.model = mdl;
ic.controlled_src = 'ES1';
ic.t_step_s = t_step;
ic.amp_step_sys_pu = amp_step;
ic.M_fixed = 24.0;
ic.D_cases = D_cases;
ic.tau_per_D_s = tau_per_D;
ic.tau_R2_per_D = tau_R2_per_D;
ic.n_peaks_per_D = n_peaks_per_D;
ic.tau_ratio = tau_ratio;
ic.expected_ratio = expected_ratio;
ic.gates = struct( ...
    'tau_ratio_in_band',  g_in_band, ...
    'r2_above_0p7',       g_R2, ...
    'above_noise_3plus_peaks', g_above_noise, ...
    'all_pass',           all_pass);
ic.gate_def = struct( ...
    'metric',     'tau = -1 / slope of log(|ω−1|_peak_envelope) vs t_post_peak', ...
    'expected',   'tau ∝ M / D ⇒ tau(D=1.5)/tau(D=7.5) ≈ 5', ...
    'tolerance',  '[3, 10]', ...
    'r2_floor',   '0.7 on the linear fit', ...
    'noise_floor', 'at least 3 peaks above 1e-5 pu envelope');

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
