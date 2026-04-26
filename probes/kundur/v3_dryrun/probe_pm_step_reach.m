function out = probe_pm_step_reach(json_out, t_pre_s, t_step_s, amp_sys_pu)
%PROBE_PM_STEP_REACH  Phase 2.2 — per-source Pm-step reach for kundur_cvs_v3.
%
%   For each dynamic source (G1/G2/G3/ES1..4), apply a +amp_sys_pu Pm step
%   at t = t_pre_s (default 35 s, after the 30 s zero-action warmup).
%   Sim until t_pre_s + t_step_s. Measure system-wide df_max =
%   max_t max_i |omega_i(t) - 1| · fn observed in the post-step window.
%
%   Gate: each source's df_max ∈ [0.05, 5] Hz.

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase2', 'p22_pm_step_reach.json');
end
if nargin < 2 || isempty(t_pre_s),    t_pre_s   = 35.0; end
if nargin < 3 || isempty(t_step_s),   t_step_s  = 15.0; end
if nargin < 4 || isempty(amp_sys_pu), amp_sys_pu = 0.2; end

repo_root = local_repo_root();
mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
if ~bdIsLoaded(mdl), load_system(slx); end

src_names = {'G1','G2','G3','ES1','ES2','ES3','ES4'};
n = numel(src_names);

stop_time_s = t_pre_s + t_step_s;
fn = 50;

% Unbound loggers
for k = 1:n
    s = src_names{k};
    set_param([mdl '/W_omega_' s], 'MaxDataPoints', 'inf');
    set_param([mdl '/W_delta_' s], 'MaxDataPoints', 'inf');
    set_param([mdl '/W_Pe_'    s], 'MaxDataPoints', 'inf');
end
set_param(mdl, 'StopTime', sprintf('%.6f', stop_time_s));

df_max_hz = zeros(1, n);
df_max_idx = zeros(1, n);   % source where the peak observed
omega_post_min = zeros(n, n);   % per-tested-source × per-observed-source
omega_post_max = zeros(n, n);

t_start_total = tic;
for which = 1:n
    % Reset all step amps to 0
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
    for w = 1:2
        assignin('base', sprintf('WindAmp_%d', w), 1.0);
        assignin('base', sprintf('LoadStep_t_%d',   w), 1e9);
        assignin('base', sprintf('LoadStep_amp_%d', w), 0.0);
    end

    % Arm the step on `which` at t = t_pre_s, amp = amp_sys_pu
    sname = src_names{which};
    if startsWith(sname, 'G')
        gid = sscanf(sname, 'G%d');
        assignin('base', sprintf('PmgStep_t_%d',   gid), t_pre_s);
        assignin('base', sprintf('PmgStep_amp_%d', gid), amp_sys_pu);
    else
        eid = sscanf(sname, 'ES%d');
        assignin('base', sprintf('Pm_step_t_%d',   eid), t_pre_s);
        assignin('base', sprintf('Pm_step_amp_%d', eid), amp_sys_pu);
    end

    so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');

    df_peak = 0;
    df_at = 0;
    for k = 1:n
        s = src_names{k};
        ow = so.get(['omega_ts_' s]);
        t = ow.Time(:); o = ow.Data(:);
        post = t >= t_pre_s;
        if any(post)
            d = max(abs(o(post) - 1.0)) * fn;
            omega_post_min(which, k) = min(o(post));
            omega_post_max(which, k) = max(o(post));
            if d > df_peak
                df_peak = d;
                df_at = k;
            end
        end
    end
    df_max_hz(which) = df_peak;
    df_max_idx(which) = df_at;
    fprintf('RESULT: P2.2 step on %-3s amp=%+.2f sys-pu df_max=%.4f Hz at %s\n', ...
        sname, amp_sys_pu, df_peak, src_names{df_at});
end
elapsed = toc(t_start_total);

% Reset step amps after probe
for k = 1:n
    s = src_names{k};
    if startsWith(s, 'G')
        assignin('base', sprintf('PmgStep_amp_%d', sscanf(s, 'G%d')), 0.0);
    else
        assignin('base', sprintf('Pm_step_amp_%d', sscanf(s, 'ES%d')), 0.0);
    end
end

% Gate
g_in_band = all(df_max_hz >= 0.05 & df_max_hz <= 5.0);

out.src_names = src_names;
out.df_max_hz = df_max_hz;
out.df_at_src = src_names(df_max_idx);
out.amp_sys_pu = amp_sys_pu;
out.t_pre_s = t_pre_s;
out.t_step_s = t_step_s;
out.gate_in_band_005_5_Hz = g_in_band;
out.wall_time_s = elapsed;

fprintf('RESULT: gate df_in [0.05, 5] Hz: %d (wall %.1fs)\n', g_in_band, elapsed);

ic = struct();
ic.probe = 'p22_pm_step_reach';
ic.model = mdl;
ic.amp_sys_pu = amp_sys_pu;
ic.t_pre_s = t_pre_s;
ic.t_step_s = t_step_s;
ic.src_names = src_names;
ic.df_max_hz = df_max_hz;
ic.df_max_at_src = src_names(df_max_idx);
ic.gate_in_band_005_5_Hz = g_in_band;
ic.wall_time_s = elapsed;
ic.gate_def = '|omega-1|*fn ∈ [0.05, 5] Hz post-step for the maximally responding source per tested source';

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
