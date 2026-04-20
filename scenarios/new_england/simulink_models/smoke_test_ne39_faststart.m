%% smoke_test_ne39_faststart.m
% Quick sanity check for the NE39 FastRestart co-simulation pipeline.
%
% What it tests:
%   1. patch_ne39_faststart was applied (workspace var references exist)
%   2. slx_warmup (NE39 5-arg mode) completes without error
%   3. slx_step_and_read advances 1 step (t=0.5 → 0.7 s) without error
%   4. omega remains in [0.95, 1.05] — no frequency divergence
%
% Run from MATLAB command window:
%   cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\new_england\simulink_models')
%   addpath(genpath('C:\Users\27443\Desktop\Multi-Agent  VSGs\slx_helpers'))
%   smoke_test_ne39_faststart

mdl      = 'NE39bus_v2';
sbase_va = 100e6;
N        = 8;
agent_ids = 1:N;

fprintf('=== NE39 FastRestart smoke test ===\n\n');

% ── Step 0: Load model ────────────────────────────────────────────────────
fprintf('[0] Loading model...\n');
if ~bdIsLoaded(mdl)
    load_system(mdl);
end
fprintf('    OK: %s loaded\n\n', mdl);

% ── Step 1: Check patch was applied ──────────────────────────────────────
fprintf('[1] Checking patch_ne39_faststart was applied...\n');
ok = true;
for k = 1:N
    m0_path   = sprintf('%s/VSG_ES%d/M0', mdl, k);
    vsrc_path = sprintf('%s/VSrc_ES%d',   mdl, k);
    pe_path   = sprintf('%s/Pe_%d',       mdl, k);
    m0_val    = get_param(m0_path,   'Value');
    ph_val    = get_param(vsrc_path, 'PhaseAngle');
    pe_val    = get_param(pe_path,   'Value');
    expected_m = sprintf('M0_val_ES%d', k);
    expected_p = sprintf('phAng_ES%d',  k);
    expected_e = sprintf('Pe_ES%d',     k);
    if ~strcmp(m0_val, expected_m) || ~strcmp(ph_val, expected_p) || ~strcmp(pe_val, expected_e)
        fprintf('  FAIL: ES%d not patched (M0="%s", PhAng="%s", Pe="%s")\n', ...
                k, m0_val, ph_val, pe_val);
        ok = false;
    end
end
if ok
    fprintf('    OK: all 8 VSGs patched\n\n');
else
    fprintf('\n  >>> Run patch_ne39_faststart.m first, then re-run this test <<<\n');
    return;
end

% ── Step 2: Build cfg struct ─────────────────────────────────────────────
fprintf('[2] Building bridge cfg...\n');
cfg = slx_build_bridge_config( ...
    '{model}/VSG_ES{idx}/M0', ...
    '{model}/VSG_ES{idx}/D0', ...
    'omega_ES{idx}', ...
    'Vabc_ES{idx}', ...
    'Iabc_ES{idx}', ...
    '', '', 200e6, 'delta_ES{idx}', '', ...
    'M0_val_ES{idx}', 'D0_val_ES{idx}');
fprintf('    OK\n\n');

% ── Step 3: slx_warmup (NE39 5-arg mode) ─────────────────────────────────
fprintf('[3] Running slx_warmup (t_warmup=0.5s)...\n');
init_phAng = [-3.646, 0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181];
ip.M0      = 12.0;
ip.D0      =  3.0;
ip.phAng   = init_phAng;
ip.Pe0     =  0.5;
ip.t_warmup = 0.5;

[w_state, w_status] = slx_warmup(mdl, agent_ids, sbase_va, cfg, ip);

if ~w_status.success
    fprintf('  FAIL: slx_warmup error: %s\n', w_status.error);
    return;
end
fprintf('    OK: warmup in %.0f ms\n', w_status.elapsed_ms);
fprintf('    omega = [%s]\n', num2str(w_state.omega, '%.4f '));
fprintf('    Pe    = [%s]\n', num2str(w_state.Pe,    '%.4f '));
fprintf('    delta = [%s] deg\n\n', num2str(w_state.delta_deg, '%.2f '));

% ── Step 4: slx_step_and_read (1 step, t=0.5→0.7s) ──────────────────────
fprintf('[4] Running 1 RL step (t=0.5 -> 0.7s)...\n');
M_vals = repmat(12.0, 1, N);
D_vals = repmat( 3.0, 1, N);
t_stop = 0.7;

[s_state, s_status] = slx_step_and_read( ...
    mdl, agent_ids, M_vals, D_vals, ...
    t_stop, sbase_va, cfg, ...
    w_state.Pe, w_state.delta_deg);

if ~s_status.success
    fprintf('  FAIL: slx_step_and_read error: %s\n', s_status.error);
    return;
end
fprintf('    OK: step in %.0f ms\n', s_status.elapsed_ms);
fprintf('    omega = [%s]\n', num2str(s_state.omega, '%.4f '));
fprintf('    Pe    = [%s]\n', num2str(s_state.Pe,    '%.4f '));

% ── Step 5: Pass/fail on omega bounds ────────────────────────────────────
fprintf('\n[5] Checking omega in [0.95, 1.05]...\n');
omega_ok = all(s_state.omega >= 0.95 & s_state.omega <= 1.05);
if omega_ok
    fprintf('    PASS: omega stable\n');
else
    bad = find(s_state.omega < 0.95 | s_state.omega > 1.05);
    fprintf('    FAIL: agents [%s] out of bounds: [%s]\n', ...
            num2str(bad), num2str(s_state.omega(bad), '%.4f '));
end

fprintf('\n=== smoke test %s ===\n', ternary(omega_ok, 'PASSED', 'FAILED'));


% ── Helper ────────────────────────────────────────────────────────────────
function out = ternary(cond, a, b)
    if cond, out = a; else, out = b; end
end
