function out = probe_5ep_smoke_mcp(json_out)
%PROBE_5EP_SMOKE_MCP  P3.4 — MATLAB-side 5-episode v3 wiring smoke.
%
%   MATLAB equivalent of probe_5ep_smoke.py. Runs entirely inside the
%   simulink-tools MCP MATLAB engine (long-lived, warm) instead of cold-
%   starting a new matlab.engine session from Python. Avoids the
%   24-min hang observed on the matlab.engine path.
%
%   What this probe is:
%     - Round-trip wiring smoke for `kundur_cvs_v3` (P3.0..P3.3 stack).
%     - Walks: load_system → slx_episode_warmup_cvs → slx_step_and_read_cvs.
%     - 5 episodes × 50 steps × 0.2 s.
%
%   What this probe is NOT:
%     - Not training, not SAC, not env, not bridge, not 50-ep gate.
%     - Action source = uniform random on [M_LO,M_HI]×[D_LO,D_HI];
%       this exercises the IPC pipeline, not learning.
%
%   Outputs heartbeat via 'RESULT: ' fprintf so simulink_poll_script
%   important_lines surface progress in real time.

if nargin < 1 || isempty(json_out)
    repo_root = local_repo_root();
    json_out = fullfile(repo_root, 'results', 'harness', 'kundur', ...
        'cvs_v3_phase3', 'p34_5ep_smoke_mcp.json');
end

repo_root = local_repo_root();
addpath(fullfile(repo_root, 'slx_helpers'));
addpath(fullfile(repo_root, 'slx_helpers', 'vsg_bridge'));

mdl = 'kundur_cvs_v3';
slx = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '.slx']);
ic_path = fullfile(repo_root, 'scenarios', 'kundur', 'kundur_ic_cvs_v3.json');
profile_path = fullfile(repo_root, 'scenarios', 'kundur', 'model_profiles', 'kundur_cvs_v3.json');

% --- Stage 1: identity probe ---
fprintf('RESULT: stage=identity\n');
fprintf('RESULT: model_name=%s\n', mdl);
fprintf('RESULT: profile_path=%s\n', profile_path);
fprintf('RESULT: ic_path=%s\n', ic_path);
runtime_mat_expected = fullfile(repo_root, 'scenarios', 'kundur', 'simulink_models', [mdl '_runtime.mat']);
runtime_mat_exists = exist(runtime_mat_expected, 'file') == 2;
fprintf('RESULT: runtime_mat_path=%s\n', runtime_mat_expected);
fprintf('RESULT: runtime_mat_exists=%d\n', runtime_mat_exists);

% Profile + IC dry-load checks
profile_raw = jsondecode(fileread(profile_path));
ic_raw      = jsondecode(fileread(ic_path));
fprintf('RESULT: profile_id=%s model_name_in_profile=%s\n', ...
    profile_raw.profile_id, profile_raw.model_name);
fprintf('RESULT: ic_schema_version=%d ic_topology_variant=%s\n', ...
    ic_raw.schema_version, ic_raw.topology_variant);

identity_ok = strcmp(profile_raw.model_name, mdl) && ...
              ic_raw.schema_version == 3 && ...
              strcmp(ic_raw.topology_variant, 'v3_paper_kundur_16bus') && ...
              runtime_mat_exists;
fprintf('RESULT: identity_ok=%d\n', identity_ok);

% --- Stage 2: load model + seed base ws ---
fprintf('RESULT: stage=load_model\n');
if bdIsLoaded(mdl), close_system(mdl, 0); end
t0 = tic; load_system(slx); load_wall = toc(t0);
fprintf('RESULT: load_wall_s=%.2f\n', load_wall);

% Build_kundur_cvs_v3.m sets ~30 base-ws scalars at build time. The runtime
% sidecar saves only some (wn_const, Vbase_const, Sbase_const, Pe_scale,
% L_gen_H, L_vsg_H, SG_SN, VSG_SN, SG_M_paper, SG_D_paper, SG_R_paper,
% ESS_M0, ESS_D0, VemfG_1..3, deltaG0_1..3, Pmg_1..3, Vmag_1..4, delta0_1..4,
% Pm_1..4, Wphase_1..2, WVmag_1..2). Vars that are derived at build time but
% NOT saved to the sidecar (Mg_<g>, Dg_<g>, Rg_<g>, SGScale_<g>,
% VSGScale_<i>, governor / loadstep / pm-step gates, WindAmp_*) are lost
% when the MCP session restarts. Re-seed them here from paper constants
% so the warmup helper can run without first calling build_kundur_cvs_v3().
fprintf('RESULT: stage=seed_base_ws\n');
sg_H = [6.5, 6.5, 6.175];
sg_D = [5.0, 5.0, 5.0];
sg_R = [0.05, 0.05, 0.05];
SG_SN  = 900e6;
VSG_SN = 200e6;
Sbase  = 100e6;
for g = 1:3
    assignin('base', sprintf('Mg_%d',  g), 2 * sg_H(g));        % M = 2H
    assignin('base', sprintf('Dg_%d',  g), sg_D(g));
    assignin('base', sprintf('Rg_%d',  g), sg_R(g));
    assignin('base', sprintf('SGScale_%d', g), Sbase / SG_SN);   % 0.1111
    assignin('base', sprintf('PmgStep_t_%d',   g), 1e9);
    assignin('base', sprintf('PmgStep_amp_%d', g), 0.0);
end
for i = 1:4
    assignin('base', sprintf('VSGScale_%d', i), Sbase / VSG_SN); % 0.5
    assignin('base', sprintf('Pm_step_t_%d',   i), 1e9);
    assignin('base', sprintf('Pm_step_amp_%d', i), 0.0);
end
for w = 1:2
    assignin('base', sprintf('WindAmp_%d', w), 1.0);
end
for k = 1:2
    assignin('base', sprintf('G_perturb_%d_S', k), 0.0);
    assignin('base', sprintf('LoadStep_t_%d',   k), 1e9);
    assignin('base', sprintf('LoadStep_amp_%d', k), 0.0);
end
fprintf('RESULT: base_ws seeded (SG: Mg/Dg/Rg/SGScale/PmgStep_*; ESS: VSGScale/Pm_step_*; Wind: WindAmp; LoadStep: gates)\n');

% --- Stage 3: warmup helper round-trip ---
fprintf('RESULT: stage=warmup\n');
agent_ids = 1:4;
N = numel(agent_ids);

cfg.m_var_template = 'M_{idx}';
cfg.d_var_template = 'D_{idx}';

init_params = struct();
init_params.M0          = 24.0;
init_params.D0          = 4.5;
init_params.Pm0_pu      = double(ic_raw.vsg_pm0_pu(:))';
init_params.delta0_rad  = double(ic_raw.vsg_internal_emf_angle_rad(:))';
% Use V_emf magnitude × Vbase (P3.0c established this is the right CVS amp)
init_params.Vmag_volts  = double(ic_raw.vsg_emf_mag_pu(:))' * 230e3;
init_params.Pm_step_t   = 1e9;
init_params.Pm_step_amp = 0.0;
init_params.t_warmup    = 10.0;

% Reset SG and wind disturbance gates (not in init_params schema; set directly)
for g = 1:3
    assignin('base', sprintf('PmgStep_t_%d',   g), 1e9);
    assignin('base', sprintf('PmgStep_amp_%d', g), 0.0);
end
for w = 1:2
    assignin('base', sprintf('WindAmp_%d', w), 1.0);
end
% Force LoadStep blocks open (P2.3 pattern)
set_param([mdl '/LoadStep7'], 'Resistance', '1e9');
set_param([mdl '/LoadStep9'], 'Resistance', '1e9');

t0 = tic;
[wstate, wstatus] = slx_episode_warmup_cvs(mdl, agent_ids, 100e6, cfg, init_params, true);
warmup_wall = toc(t0);

warmup_ok = wstatus.success && all(isfinite(wstate.omega)) && all(abs(wstate.omega) > 0);
fprintf('RESULT: warmup_success=%d warmup_wall_s=%.2f\n', logical(wstatus.success), warmup_wall);
if ~wstatus.success
    fprintf('RESULT: warmup_error=%s\n', wstatus.error);
end
fprintf('RESULT: warmup_omega=[%+.6f %+.6f %+.6f %+.6f]\n', wstate.omega);
fprintf('RESULT: warmup_Pe=[%+.6f %+.6f %+.6f %+.6f]\n', wstate.Pe);
fprintf('RESULT: warmup_delta=[%+.6f %+.6f %+.6f %+.6f]\n', wstate.delta);
fprintf('RESULT: warmup_ok=%d\n', warmup_ok);

% Init shared step state
omega_init = wstate.omega(:)';
Pe_init    = wstate.Pe(:)';
delta_init = wstate.delta(:)' * 180/pi;

% --- Stage 4: 5 episodes × 50 steps ---
fprintf('RESULT: stage=episodes\n');
n_ep   = 5;
n_step = 50;
DT     = 0.2;
fn     = 50;

% Action ranges (mirror config_simulink + config_simulink_base; values from
% Phase 1 log: M_LO=22.5 M_HI=28.5 D_LO=3.0 D_HI=9.0)
M_LO = 22.5; M_HI = 28.5;
D_LO = 3.0;  D_HI = 9.0;

rng(42, 'twister');

ep_records   = cell(n_ep, 1);
all_episodes_complete = true;
nan_inf_seen = false;
clip_or_fail_seen = false;

% Persist Pm0 / delta0 / Vmag across steps via base ws (slx_episode_warmup_cvs
% already wrote them). Per-step we only assign M_<i> / D_<i>.

t_episode_start = init_params.t_warmup;  % continue sim from warmup end
for ep = 1:n_ep
    fprintf('RESULT: stage=ep%d_start\n', ep-1);

    % Per-episode disturbance: alternating sign, ±0.4 sys-pu split across
    % all 4 ESS via the existing CVS path — but the build wires Pm_step_amp
    % per-VSG and the NR stack expects targeted single-VSG step (see
    % env.apply_disturbance for kundur_cvs branch). Use VSG[0] only.
    if mod(ep-1, 2) == 0
        amp_per_vsg = +0.4 * 100e6 / 1 / 100e6;   % sys-pu → vsg-pu cancels
    else
        amp_per_vsg = -0.4 * 100e6 / 1 / 100e6;
    end
    t_now = t_episode_start;
    for i = 1:N
        idx = agent_ids(i);
        if i == 1
            assignin('base', sprintf('Pm_step_t_%d',   idx), t_now);
            assignin('base', sprintf('Pm_step_amp_%d', idx), amp_per_vsg);
        else
            assignin('base', sprintf('Pm_step_t_%d',   idx), 1e9);
            assignin('base', sprintf('Pm_step_amp_%d', idx), 0.0);
        end
    end

    omega_ts = nan(n_step, N);
    Pe_ts    = nan(n_step, N);
    delta_ts = nan(n_step, N);
    actions_M = nan(n_step, N);
    actions_D = nan(n_step, N);
    rewards_proxy = nan(n_step, 1);
    omega_dev_max = 0;
    max_freq_dev_hz_ep = 0;
    ep_complete = true;
    ep_nan_inf = false;
    ep_clip = false;

    Pe_prev    = Pe_init;
    delta_prev = delta_init;
    t_stop_ep_start = t_episode_start;

    t0_ep = tic;
    for s = 1:n_step
        M_vals = M_LO + (M_HI - M_LO) * rand(1, N);
        D_vals = D_LO + (D_HI - D_LO) * rand(1, N);
        actions_M(s, :) = M_vals;
        actions_D(s, :) = D_vals;

        t_stop = t_stop_ep_start + s * DT;
        try
            [state, status] = slx_step_and_read_cvs( ...
                mdl, agent_ids, M_vals, D_vals, t_stop, 100e6, cfg, ...
                Pe_prev, delta_prev);
        catch ME
            fprintf('RESULT: ep%d_step%d_EXCEPTION=%s\n', ep-1, s, ME.message);
            ep_complete = false;
            all_episodes_complete = false;
            break;
        end

        if ~status.success
            fprintf('RESULT: ep%d_step%d_status_fail=%s\n', ep-1, s, status.error);
            ep_complete = false;
            ep_clip = true;
            clip_or_fail_seen = true;
            break;
        end

        omega_ts(s, :) = state.omega(:)';
        Pe_ts(s, :)    = state.Pe(:)';
        delta_ts(s, :) = state.delta(:)';
        Pe_prev    = state.Pe(:)';
        delta_prev = state.delta_deg(:)';

        if any(~isfinite(state.omega)) || any(~isfinite(state.Pe))
            ep_nan_inf = true;
            nan_inf_seen = true;
        end
        omega_dev_max = max(omega_dev_max, max(abs(state.omega - 1.0)));
        max_freq_dev_hz_ep = max(max_freq_dev_hz_ep, max(abs(state.omega - 1.0)) * fn);

        % Reward proxy (paper-aligned r_f sign): -mean((omega-1)^2)
        rewards_proxy(s) = -mean((state.omega - 1.0).^2);
    end
    ep_wall = toc(t0_ep);

    if ep_complete
        steps_done = n_step;
    else
        steps_done = sum(~isnan(omega_ts(:, 1)));
        all_episodes_complete = false;
    end

    rec = struct();
    rec.episode = ep - 1;
    rec.steps_done = steps_done;
    rec.expected_steps = n_step;
    rec.complete = ep_complete;
    rec.nan_inf = ep_nan_inf;
    rec.clip_or_fail = ep_clip;
    rec.omega_min = min(omega_ts, [], 1);
    rec.omega_max = max(omega_ts, [], 1);
    rec.omega_dev_max_pu = omega_dev_max;
    rec.max_freq_dev_hz = max_freq_dev_hz_ep;
    rec.M_action_mean = nanmean(actions_M, 1);
    rec.D_action_mean = nanmean(actions_D, 1);
    rec.reward_proxy_mean = nanmean(rewards_proxy);
    rec.amp_per_vsg_sys_pu = amp_per_vsg;
    rec.wall_s = ep_wall;
    ep_records{ep} = rec;

    fprintf('RESULT: ep%d done steps=%d/%d wall=%.2fs omega_dev_max=%.3e Pe_dev|=NaN/Inf=%d clip=%d max_freq_dev=%.4fHz reward_proxy=%.3e\n', ...
        ep-1, steps_done, n_step, ep_wall, omega_dev_max, ep_nan_inf, ep_clip, max_freq_dev_hz_ep, rec.reward_proxy_mean);

    if ~ep_complete, break; end
    t_episode_start = t_stop;   % continue sim time
end

% --- Stage 5: gates ---
fprintf('RESULT: stage=gates\n');
omega_non_stale = false;
nonzero_freq_dev = false;
% ep_records is a cell array of structs (or empty cells if early-exit)
filled = ~cellfun(@isempty, ep_records);
if any(filled)
    omega_non_stale = all(cellfun(@(r) (r.complete && r.omega_dev_max_pu > 1e-6), ep_records(filled)));
    nonzero_freq_dev = any(cellfun(@(r) (r.complete && r.max_freq_dev_hz > 0), ep_records(filled)));
end

gates = struct();
gates.identity_ok                = logical(identity_ok);
gates.runtime_mat_v3_correct     = logical(runtime_mat_exists);
gates.warmup_passed              = logical(warmup_ok);
gates.all_5_episodes_complete    = logical(all_episodes_complete);
gates.no_nan_inf                 = logical(~nan_inf_seen);
gates.no_clip_or_fail            = logical(~clip_or_fail_seen);
gates.omega_non_stale            = logical(omega_non_stale);
gates.max_freq_dev_nonzero       = logical(nonzero_freq_dev);
all_pass = gates.identity_ok && gates.runtime_mat_v3_correct && ...
           gates.warmup_passed && gates.all_5_episodes_complete && ...
           gates.no_nan_inf && gates.no_clip_or_fail && ...
           gates.omega_non_stale && gates.max_freq_dev_nonzero;

fn_names = fieldnames(gates);
for k = 1:numel(fn_names)
    fprintf('RESULT: gate %s=%d\n', fn_names{k}, gates.(fn_names{k}));
end
fprintf('RESULT: ALL_PASS=%d\n', all_pass);

% --- Stage 6: write JSON ---
ic_out = struct();
ic_out.probe = 'p34_5ep_smoke_mcp';
ic_out.model_name = mdl;
ic_out.profile_path = profile_path;
ic_out.ic_path = ic_path;
ic_out.runtime_mat_path = runtime_mat_expected;
ic_out.runtime_mat_exists = logical(runtime_mat_exists);
ic_out.profile_id = profile_raw.profile_id;
ic_out.ic_schema_version = ic_raw.schema_version;
ic_out.ic_topology_variant = ic_raw.topology_variant;
ic_out.warmup_state = struct( ...
    'omega', wstate.omega(:)', ...
    'Pe',    wstate.Pe(:)', ...
    'delta_rad', wstate.delta(:)');
ic_out.warmup_status = struct( ...
    'success', logical(wstatus.success), ...
    'error',   wstatus.error, ...
    'wall_s',  warmup_wall);
ic_out.episodes = ep_records;
ic_out.gates = gates;
ic_out.all_pass = logical(all_pass);
ic_out.timestamp = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX', 'TimeZone', 'local'));

out_dir = fileparts(json_out);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(json_out, 'w');
fwrite(fid, jsonencode(ic_out, 'PrettyPrint', true));
fclose(fid);
fprintf('RESULT: wrote %s\n', json_out);

out = ic_out;
end


function r = local_repo_root()
this_dir = fileparts(mfilename('fullpath'));
r = fileparts(fileparts(fileparts(this_dir)));
end
