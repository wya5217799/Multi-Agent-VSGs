function out = probe_hd_sensitivity(json_out)
%PROBE_HD_SENSITIVITY  Phase 2.5 — ESS H/D sensitivity for kundur_cvs_v3.
%
%   Verifies the RL action axes are physically meaningful:
%     - H controls ROCOF (= max |dω/dt|) for the controlled ESS
%     - D controls steady-region df envelope post-step
%
%   Method (uses Pm-step gate which P2.2 verified works mid-sim):
%     - Apply +0.2 sys-pu Pm step on ES1 at t = 35 s
%     - Sub-probe a (H sensitivity): D fixed, M ∈ {12, 60} (=2H ∈ {6, 30})
%         ROCOF_ratio = ROCOF(H=6) / ROCOF(H=30); expect ≈ 5
%     - Sub-probe b (D sensitivity): M fixed at 24 (=H=12), D ∈ {1.5, 7.5}
%         peak_df_ratio = peak_df(D=1.5) / peak_df(D=7.5); expect ≈ 5
%
%   Gate (PASS = both):
%     - ROCOF_ratio ∈ [3, 10] (factor-of-2 tolerance around the predicted 5×)
%     - peak_df_ratio ∈ [3, 10]
%     - both ROCOF and df values are non-zero / above noise (1 mHz floor)

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p25_hd_sensitivity.json');
end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);
fn = 50;

% Reset all disturbances + neutral wind
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
% Save defaults for restoration
M1_orig = evalin('base', 'M_1');
D1_orig = evalin('base', 'D_1');

t_step = 35.0;
t_post = 10.0;
amp_step = 0.2;        % +0.2 sys-pu Pm step on ES1
stop_time_s = t_step + t_post;
set_param(mdl, 'StopTime', sprintf('%.6f', stop_time_s));

assignin('base', 'Pm_step_t_1',   t_step);
assignin('base', 'Pm_step_amp_1', amp_step);

% --- Sub-probe a: H sensitivity (D fixed at 4.5 default) ---
H_cases = [6.0, 30.0];          % H = M/2, so M = [12, 60]
D_fix_a = D1_orig;
rocof_a_hz_per_s = zeros(1, numel(H_cases));
df_peak_a_hz     = zeros(1, numel(H_cases));
for hi = 1:numel(H_cases)
    H = H_cases(hi);
    assignin('base', 'M_1', 2 * H);
    assignin('base', 'D_1', D_fix_a);

    so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    ow = so.get('omega_ts_ES1');
    t = ow.Time(:); o = ow.Data(:);

    % Post-step window for ROCOF: first 200 ms after t_step
    mask_rocof = (t >= t_step) & (t <= t_step + 0.2);
    if sum(mask_rocof) >= 2
        tt = t(mask_rocof); oo = o(mask_rocof);
        dwdt = diff(oo) ./ diff(tt);                 % per-second
        rocof_a_hz_per_s(hi) = max(abs(dwdt)) * fn;  % Hz / s
    end

    % Post-step peak |Δω| (envelope) over [t_step, end]
    mask_post = t >= t_step;
    if any(mask_post)
        df_peak_a_hz(hi) = max(abs(o(mask_post) - 1.0)) * fn;
    end
    fprintf('RESULT: P2.5a H=%.1f (M=%.1f) D=%.1f  ROCOF=%.4f Hz/s  df_peak=%.4f Hz\n', ...
        H, 2*H, D_fix_a, rocof_a_hz_per_s(hi), df_peak_a_hz(hi));
end

ROCOF_ratio = rocof_a_hz_per_s(1) / rocof_a_hz_per_s(2);
fprintf('RESULT: P2.5a ROCOF_ratio H=6/H=30 = %.3f (expect ≈ 5)\n', ROCOF_ratio);

% --- Sub-probe b: D sensitivity (H fixed at 12, M=24) ---
M_fix_b = 24.0;
D_cases = [1.5, 7.5];
rocof_b_hz_per_s = zeros(1, numel(D_cases));
df_peak_b_hz     = zeros(1, numel(D_cases));
for di = 1:numel(D_cases)
    D = D_cases(di);
    assignin('base', 'M_1', M_fix_b);
    assignin('base', 'D_1', D);

    so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
    ow = so.get('omega_ts_ES1');
    t = ow.Time(:); o = ow.Data(:);

    mask_rocof = (t >= t_step) & (t <= t_step + 0.2);
    if sum(mask_rocof) >= 2
        tt = t(mask_rocof); oo = o(mask_rocof);
        dwdt = diff(oo) ./ diff(tt);
        rocof_b_hz_per_s(di) = max(abs(dwdt)) * fn;
    end

    mask_post = t >= t_step;
    if any(mask_post)
        df_peak_b_hz(di) = max(abs(o(mask_post) - 1.0)) * fn;
    end
    fprintf('RESULT: P2.5b H=12 (M=24) D=%.2f  ROCOF=%.4f Hz/s  df_peak=%.4f Hz\n', ...
        D, rocof_b_hz_per_s(di), df_peak_b_hz(di));
end

PEAKDF_ratio = df_peak_b_hz(1) / df_peak_b_hz(2);
fprintf('RESULT: P2.5b peak_df ratio D=1.5/D=7.5 = %.3f (expect ≈ 5)\n', PEAKDF_ratio);

% --- Restore + reset step ---
assignin('base', 'M_1', M1_orig);
assignin('base', 'D_1', D1_orig);
assignin('base', 'Pm_step_t_1',   1e9);
assignin('base', 'Pm_step_amp_1', 0.0);

% --- Gate ---
g_rocof_in_band = (ROCOF_ratio >= 3.0) && (ROCOF_ratio <= 10.0);
g_peakdf_in_band = (PEAKDF_ratio >= 3.0) && (PEAKDF_ratio <= 10.0);
g_above_noise_a = all(rocof_a_hz_per_s >= 1e-3);
g_above_noise_b = all(df_peak_b_hz    >= 1e-3);
all_pass = g_rocof_in_band && g_peakdf_in_band && g_above_noise_a && g_above_noise_b;

fprintf('RESULT: P2.5 gates ROCOF_ratio_in[3,10]=%d peakdf_ratio_in[3,10]=%d above_noise_a=%d above_noise_b=%d ALL=%d\n', ...
    g_rocof_in_band, g_peakdf_in_band, g_above_noise_a, g_above_noise_b, all_pass);

out.H_cases = H_cases;
out.D_fix_a = D_fix_a;
out.rocof_a_hz_per_s = rocof_a_hz_per_s;
out.df_peak_a_hz = df_peak_a_hz;
out.ROCOF_ratio = ROCOF_ratio;
out.M_fix_b = M_fix_b;
out.D_cases = D_cases;
out.rocof_b_hz_per_s = rocof_b_hz_per_s;
out.df_peak_b_hz = df_peak_b_hz;
out.PEAKDF_ratio = PEAKDF_ratio;
out.gate_pass = all_pass;

ic = struct();
ic.probe = 'p25_hd_sensitivity';
ic.model = mdl;
ic.controlled_src = 'ES1';
ic.t_step_s = t_step;
ic.amp_step_sys_pu = amp_step;
ic.subprobe_a_H_sensitivity = struct( ...
    'H_cases', H_cases, ...
    'M_cases', 2 * H_cases, ...
    'D_fixed', D_fix_a, ...
    'rocof_hz_per_s', rocof_a_hz_per_s, ...
    'df_peak_hz', df_peak_a_hz, ...
    'rocof_ratio_H6_over_H30', ROCOF_ratio, ...
    'expected_ratio', 5.0, ...
    'tolerance_band', [3.0 10.0]);
ic.subprobe_b_D_sensitivity = struct( ...
    'M_fixed', M_fix_b, ...
    'D_cases', D_cases, ...
    'rocof_hz_per_s', rocof_b_hz_per_s, ...
    'df_peak_hz', df_peak_b_hz, ...
    'peak_df_ratio_D15_over_D75', PEAKDF_ratio, ...
    'expected_ratio', 5.0, ...
    'tolerance_band', [3.0 10.0]);
ic.gates = struct( ...
    'rocof_ratio_in_band',    g_rocof_in_band, ...
    'peakdf_ratio_in_band',   g_peakdf_in_band, ...
    'above_noise_a',          g_above_noise_a, ...
    'above_noise_b',          g_above_noise_b, ...
    'all_pass',               all_pass);

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
