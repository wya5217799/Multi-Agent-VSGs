function test_h1_no_breaker_bus14()
%TEST_H1_NO_BREAKER_BUS14  Phase 1.3a H1 falsification (NR-consistent variant).
%
% Hypothesis (§4 H1): the closed-state IC transient of the
% Three-Phase Breaker on Bus 14 (LS1 pre-engaged) is the dominant excitation
% source for the 2 Hz electromechanical mode that makes ES3 oscillate at
% std=0.00177 in the 1s baseline.
%
% NR-consistent test design:
%   - Build with workspace flag bus14_no_breaker=true.
%   - The Breaker_bus14 block is skipped; Three-Phase Series RLC Load
%     (248 MW, R-only) is connected DIRECTLY to Bus 14.
%   - LoadStep_amp_bus14 stays at 248e6 default so NR powerflow remains
%     consistent (Pm0_3 was solved assuming 248 MW absorption at Bus 14).
%   - Bus 15 keeps its breaker (initial state open) — only Bus 14 changes.
%
% Pre-registered decision (write before running, do NOT post-hoc adjust):
%   - ES3 std @ window [0.5, 1.0] s on 1s sim:
%       * < 0.001 -> H1 SUPPORTED (breaker IC transient is the source)
%       * >= 0.001 -> H1 FALSIFIED (breaker is NOT the source; proceed to H2)
%   - Q2 was unanswered; using strict baseline-aligned threshold (no slack).
%
% This test is a PERMANENT probe (per §1.0 registry / engineering_philosophy
% §3 Documentation ≠ Repair). After the run, results MUST be either filed
% in §1.0 registry as a new row, or recorded as a verdict in §4.

mdl = 'kundur_cvs_v3_discrete';
mdl_dir = 'C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models';
addpath(mdl_dir);

% Reference baseline std (from RESULT lines of test_v3_discrete_ic_settle, 1s sim, [0.5,1]s)
baseline_std = struct( ...
    'G1', 0.000288, 'G2', 0.000259, 'G3', 0.000410, ...
    'ES1', 0.000420, 'ES2', 0.000927, 'ES3', 0.001772, 'ES4', 0.001024);

%% Step 1 — Build with bus14_no_breaker=true
fprintf('RESULT: ===== H1 NR-consistent falsification (no Bus 14 breaker) =====\n');
if bdIsLoaded(mdl), close_system(mdl, 0); end
assignin('base', 'bus14_no_breaker', true);
build_kundur_cvs_v3_discrete();

%% Step 2 — Verify topology change took effect
load_system(fullfile(mdl_dir, [mdl '.slx']));
load(fullfile(mdl_dir, [mdl '_runtime.mat']));

% Sanity: LoadStepBreaker_bus14 should NOT exist; LoadStepBreaker_bus15 should
% still exist; LoadStep_bus14 should exist (load directly on bus).
breaker14_exists = ~isempty(find_system(mdl, 'SearchDepth', 1, 'Name', 'LoadStepBreaker_bus14'));
breaker15_exists = ~isempty(find_system(mdl, 'SearchDepth', 1, 'Name', 'LoadStepBreaker_bus15'));
load14_exists    = ~isempty(find_system(mdl, 'SearchDepth', 1, 'Name', 'LoadStep_bus14'));
fprintf('RESULT: LoadStepBreaker_bus14 present = %d (expected 0)\n', breaker14_exists);
fprintf('RESULT: LoadStepBreaker_bus15 present = %d (expected 1)\n', breaker15_exists);
fprintf('RESULT: LoadStep_bus14 present = %d (expected 1)\n', load14_exists);
if breaker14_exists || ~breaker15_exists || ~load14_exists
    fprintf('RESULT: VERDICT=FAIL_TOPOLOGY — flag did not toggle as expected\n');
    return;
end

%% Step 3 — Run 1s zero-disturbance sim, same gate as baseline
src_names = {'G1', 'G2', 'G3', 'ES1', 'ES2', 'ES3', 'ES4'};
for s = 1:numel(src_names)
    sname = src_names{s};
    try
        set_param([mdl '/W_omega_' sname], 'MaxDataPoints', 'inf');
        set_param([mdl '/W_delta_' sname], 'MaxDataPoints', 'inf');
        set_param([mdl '/W_Pe_'    sname], 'MaxDataPoints', 'inf');
    catch
    end
end
for k = 1:4
    assignin('base', sprintf('Pm_step_t_%d', k), 100.0);
    assignin('base', sprintf('Pm_step_amp_%d', k), 0.0);
end
for g = 1:3
    assignin('base', sprintf('PmgStep_t_%d', g), 100.0);
    assignin('base', sprintf('PmgStep_amp_%d', g), 0.0);
end
assignin('base', 'LoadStep_t_bus14', 100.0);
assignin('base', 'LoadStep_t_bus15', 100.0);

set_param(mdl, 'StopTime', '1.0');
t_start = tic;
out = sim(mdl);
elapsed = toc(t_start);
fprintf('RESULT: 1s sim wall=%.2fs\n', elapsed);

%% Step 4 — Per-source comparison and pre-registered decision
src_meta = {
    'G1',  'omega_ts_G1';
    'G2',  'omega_ts_G2';
    'G3',  'omega_ts_G3';
    'ES1', 'omega_ts_1';
    'ES2', 'omega_ts_2';
    'ES3', 'omega_ts_3';
    'ES4', 'omega_ts_4';
};

fprintf('RESULT: ----- per-source comparison (window [0.5,1.0]s) -----\n');
fprintf('RESULT: %-4s | %-12s | %-12s | %-9s | %s\n', ...
    'src', 'baseline_std', 'h1_nr_cons', 'delta_pct', 'mean');
es3_std_h1 = NaN;
for s = 1:size(src_meta, 1)
    sname = src_meta{s, 1};
    var   = src_meta{s, 2};
    omega = out.get(var);
    od = omega.Data;
    t  = omega.Time;
    mask = (t >= 0.5) & (t <= 1.0);
    od_w = od(mask);
    sd_h1 = std(od_w);
    m_h1  = mean(od_w);
    sd_base = baseline_std.(sname);
    delta_pct = 100 * (sd_h1 - sd_base) / sd_base;
    fprintf('RESULT: %-4s | %-12.6f | %-12.6f | %+6.1f%%  | %.6f\n', ...
        sname, sd_base, sd_h1, delta_pct, m_h1);
    if strcmp(sname, 'ES3'), es3_std_h1 = sd_h1; end
end

%% Step 5 — Pre-registered verdict
fprintf('RESULT: ----- H1 NR-consistent verdict -----\n');
fprintf('RESULT: ES3 std (H1, 1s window [0.5,1.0]) = %.6f\n', es3_std_h1);
fprintf('RESULT: threshold = 0.001 (strict baseline alignment)\n');
if es3_std_h1 < 0.001
    fprintf('RESULT: VERDICT=H1_SUPPORTED — ES3 settles when breaker removed\n');
    fprintf('RESULT: -> root cause = Bus 14 breaker IC transient excites 2 Hz mode\n');
else
    fprintf('RESULT: VERDICT=H1_FALSIFIED — ES3 still oscillates without breaker\n');
    fprintf('RESULT: -> proceed to H2 (NR re-derive) or H3/H4\n');
end

%% Step 6 — Save raw data for follow-up
out_mat = fullfile(mdl_dir, 'phase1_3a_h1_nr_consistent.mat');
omega_data = struct();
for s = 1:size(src_meta, 1)
    sname = src_meta{s, 1};
    var   = src_meta{s, 2};
    omega = out.get(var);
    omega_data.(sname).t = omega.Time;
    omega_data.(sname).w = omega.Data;
end
save(out_mat, '-struct', 'omega_data');
fprintf('RESULT: saved %s\n', out_mat);

%% Step 7 — Reset flag (don't poison subsequent builds)
evalin('base', 'clear bus14_no_breaker');
fprintf('RESULT: flag cleared from base workspace\n');

end
