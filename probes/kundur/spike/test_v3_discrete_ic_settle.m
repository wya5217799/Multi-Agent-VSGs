function test_v3_discrete_ic_settle()
%TEST_V3_DISCRETE_IC_SETTLE  Phase 1.1+ TDD acceptance gate.
%
% Goal: verify build_kundur_cvs_v3_discrete() produces a model whose
% steady-state IC actually settles within 1s of zero-disturbance simulation.
%
% This is the Layer 2 TDD test (direct sim + check, no env wrapper).
% Layer 3 (probe_state Phase 3) comes later in Phase 1.4 once the model is
% validated end-to-end.
%
% Acceptance criteria (per Phase 0 P0.2 standard):
%   For all 7 sources (4 ESS + 3 SG):
%     - omega settles to 1.0 ± 0.005 (mean of last 0.5s)
%     - omega std over last 0.5s < 0.001
%     - sim wall-clock < 5s (target real-time-or-better)
%
% Failure modes captured:
%   - FAIL_BUILD: build_kundur_cvs_v3_discrete() throws
%   - FAIL_COMPILE: simulink_compile_diagnostics returns errors
%   - FAIL_SIM: sim() throws or no omega_ts produced
%   - FAIL_DRIFT: omega drifts outside 1.0 ± 0.005 (typically: source not
%     connected to network, or IC mismatch, or solver instability)
%   - FAIL_OSCILLATE: omega oscillates (std > 0.001, typically: solver
%     mismatch or unbalanced load)
%
% Output: prints RESULT lines and a final PASS/FAIL verdict.

mdl = 'kundur_cvs_v3_discrete';
build_dir = 'C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models';
helper_dir = build_dir;

addpath(build_dir);
addpath(helper_dir);

% --- Step 1: Build ---
fprintf('RESULT: ===== Phase 1.1+ TDD: v3 Discrete IC settle =====\n');
build_ok = false;
build_err = '';
try
    build_kundur_cvs_v3_discrete();
    build_ok = true;
    fprintf('RESULT: build OK\n');
catch ME
    build_err = ME.message;
    fprintf('RESULT: FAIL_BUILD: %s\n', build_err);
end

if ~build_ok
    fprintf('RESULT: VERDICT=FAIL_BUILD — %s\n', build_err);
    return;
end

% --- Step 2: Load + compile diagnostic ---
if bdIsLoaded(mdl), close_system(mdl, 0); end
load_system(fullfile(build_dir, [mdl '.slx']));

compile_ok = false;
try
    set_param(mdl, 'SimulationCommand', 'update');
    compile_ok = true;
    fprintf('RESULT: compile OK\n');
catch ME
    fprintf('RESULT: FAIL_COMPILE: %s\n', ME.message);
end

if ~compile_ok
    fprintf('RESULT: VERDICT=FAIL_COMPILE\n');
    return;
end

% --- Step 3: Override MaxDataPoints on all loggers BEFORE sim ---
src_names_for_log = {'G1', 'G2', 'G3', 'ES1', 'ES2', 'ES3', 'ES4'};
for s = 1:numel(src_names_for_log)
    sname = src_names_for_log{s};
    try
        set_param([mdl '/W_omega_' sname], 'MaxDataPoints', 'inf');
        set_param([mdl '/W_delta_' sname], 'MaxDataPoints', 'inf');
        set_param([mdl '/W_Pe_' sname], 'MaxDataPoints', 'inf');
    catch
        % Logger not present; let downstream check catch missing data
    end
end

% --- Step 4: Run 5s zero-disturbance sim ---
% Force all step amplitudes to 0 — pure IC settle test
fprintf('RESULT: setting all step amplitudes to 0 for IC test\n');
for k = 1:4
    assignin('base', sprintf('Pm_step_amp_%d', k), 0.0);
    assignin('base', sprintf('Pm_step_t_%d', k), 100.0);
end
for g = 1:3
    assignin('base', sprintf('PmgStep_amp_%d', g), 0.0);
    assignin('base', sprintf('PmgStep_t_%d', g), 100.0);
end
% LoadStep: keep amps but push t out of sim window
for lb = {'bus14', 'bus15'}
    assignin('base', sprintf('LoadStep_t_%s', lb{1}), 100.0);
    % keep amp at default per build (Bus 14 LS1 248e6 pre-engaged, Bus 15 0)
end

set_param(mdl, 'StopTime', '1.0');

t_start = tic;
sim_ok = false;
sim_err = '';
out = [];
try
    out = sim(mdl);
    sim_ok = true;
    elapsed = toc(t_start);
    fprintf('RESULT: 1s sim wall=%.2fs\n', elapsed);
catch ME
    sim_err = ME.message;
    fprintf('RESULT: FAIL_SIM: %s\n', sim_err);
end

if ~sim_ok
    fprintf('RESULT: VERDICT=FAIL_SIM — %s\n', sim_err);
    return;
end

% --- Step 4: Check IC settling for all 7 sources ---
src_names = {'G1', 'G2', 'G3', 'ES1', 'ES2', 'ES3', 'ES4'};
ess_indices = [4 5 6 7];   % ES1=index4, ES2=index5, ES3=index6, ES4=index7
sg_names = {'G1', 'G2', 'G3'};

n_pass = 0;
n_fail = 0;
fail_details = {};

for s = 1:numel(src_names)
    sname = src_names{s};
    if any(s == ess_indices)
        ess_idx = s - 3;   % ES1 → 1, ES2 → 2, etc.
        var_name = sprintf('omega_ts_%d', ess_idx);
    else
        var_name = sprintf('omega_ts_%s', sname);
    end

    omega = [];
    try
        omega = out.get(var_name);
    catch
    end

    if isempty(omega) || ~isa(omega, 'timeseries')
        fprintf('RESULT: %s: NO_OMEGA (var=%s missing)\n', sname, var_name);
        n_fail = n_fail + 1;
        fail_details{end+1} = sprintf('%s: missing omega', sname);
        continue;
    end

    od = omega.Data;
    t  = omega.Time;
    if numel(od) < 10
        fprintf('RESULT: %s: TOO_FEW_SAMPLES (n=%d)\n', sname, numel(od));
        n_fail = n_fail + 1;
        fail_details{end+1} = sprintf('%s: only %d samples', sname, numel(od));
        continue;
    end

    % Check last 0.5s window
    mask_late = t > 0.5;
    if ~any(mask_late)
        mask_late = (1:numel(od))' > round(0.5 * numel(od));
    end
    late = od(mask_late);
    late_mean = mean(late);
    late_std  = std(late);

    dev = abs(late_mean - 1.0);
    if dev < 0.005 && late_std < 0.001
        n_pass = n_pass + 1;
        fprintf('RESULT: %s: PASS mean=%.6f std=%.8f\n', sname, late_mean, late_std);
    else
        n_fail = n_fail + 1;
        fprintf('RESULT: %s: FAIL mean=%.6f std=%.8f (dev=%.4f, std>%g)\n', ...
            sname, late_mean, late_std, dev, late_std);
        if dev >= 0.005
            fail_details{end+1} = sprintf('%s: drift (mean=%.4f)', sname, late_mean);
        else
            fail_details{end+1} = sprintf('%s: oscillate (std=%.6f)', sname, late_std);
        end
    end
end

% --- Step 5: Final verdict ---
fprintf('RESULT: ----- summary -----\n');
fprintf('RESULT: %d/%d sources settled\n', n_pass, numel(src_names));
if n_pass == numel(src_names)
    fprintf('RESULT: VERDICT=PASS — all 7 sources settled within 1s\n');
else
    fprintf('RESULT: VERDICT=FAIL — %d/%d sources did not settle:\n', n_fail, numel(src_names));
    for k = 1:numel(fail_details)
        fprintf('RESULT:   %s\n', fail_details{k});
    end
end

end
