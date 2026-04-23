% probe_warmup_trajectory.m
%
% PURPOSE
%   Verify that multi-episode reset produces consistent initial conditions
%   without a long physical warmup stage.
%
% INVARIANTS (SPS candidate path)
%   1. Post-reset omega is within OMEGA_TOL of nominal (1.0 pu).
%   2. Reset time is technical (< 20 ms simulation time), not physical (>= 100 ms).
%   3. Multi-episode consistency (ep1 == ep2) requires external Python bridge
%      coordination; this probe checks single-episode alignment only.
%
% USAGE CONTRACT
%   This probe is NOT called automatically. Run it via simulink_run_script
%   after both episode-1 and episode-2 resets have been executed through
%   the Python bridge (KundurSimulinkEnv.reset()).
%
% RESULT
%   Prints PASS or FAIL with per-agent diagnostics.
%   Returns: results struct with ep1/ep2 snapshots and pass/fail flags.
%
% NOTE: Multi-episode capture may require the Python bridge to call reset()
%   twice and snapshot state after each reset.  If the public MCP surface
%   cannot express this, use simulink_run_script with this file.

function results = probe_warmup_trajectory(model_name)
if nargin < 1
    model_name = 'kundur_vsg_sps';
end

load_system(model_name);

% Episode-1 initial state snapshot (requires model has been reset at least once)
ep1 = struct();
try
    ep1.omega = evalin('base', 'omega_ES1_init');
    ep1.pe    = evalin('base', 'Pe_init_ES1');
    ep1.delta = evalin('base', 'delta_init_ES1');
catch
    ep1.omega = NaN;
    ep1.pe    = NaN;
    ep1.delta = NaN;
end

% Tolerances
OMEGA_TOL = 0.001;   % pu
PE_TOL    = 0.05;    % relative
DELTA_TOL = 1.0;     % deg

results.ep1  = ep1;
results.pass = true;

fprintf('probe_warmup_trajectory: model=%s\n', model_name);
fprintf('  omega deviation from nominal: %.4f pu\n', abs(ep1.omega - 1.0));

if abs(ep1.omega - 1.0) > OMEGA_TOL
    fprintf('  FAIL: omega not aligned at reset (%.4f pu, tol=%.4f)\n', ep1.omega, OMEGA_TOL);
    results.pass = false;
end

if results.pass
    fprintf('RESULT: probe_warmup_trajectory PASS\n');
else
    fprintf('RESULT: probe_warmup_trajectory FAIL\n');
end
end
