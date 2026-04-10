%% add_disturbance_and_interface.m
% Adds to the kundur_two_area model:
%   1. Switchable loads at Bus14/Bus15 for disturbance testing
%   2. From Workspace / To Workspace blocks for Python-Simulink interface
%   3. Measurement outputs for RL observations
%
% Run AFTER build_kundur_simulink.m has created the base model.
%
% SPST Switch (Three-Phase) port map:
%   LConn1 = Physical signal control (voltage > threshold → closed)
%   LConn2 = 3ph composite (line side)
%   RConn1 = 3ph composite (load side)

mdl = 'kundur_two_area';

if ~bdIsLoaded(mdl)
    load_system(mdl);
end

fprintf('Adding disturbance mechanism and interface to %s...\n', mdl);

%% ========== Section 1: Switchable Disturbance Loads ==========
fprintf('  Section 1: Switchable loads at Bus14, Bus15...\n');

% --- Bus 14: Replace fixed Load14 with Switch + Load ---
% Delete existing Load14 and its connections
try
    ph14 = get_param([mdl '/Load14'], 'PortHandles');
    for p = ph14.LConn
        lh = get_param(p, 'Line');
        if lh ~= -1, delete_line(lh); end
    end
    delete_block([mdl '/Load14']);
catch; end

% Add switch for Load14
add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)', [mdl '/SW14'], ...
    'Position', [1120, 580, 1170, 660]);

% Add disturbance load (248 MW)
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load', [mdl '/DLoad14'], ...
    'Position', [1200, 580, 1270, 660]);
set_param([mdl '/DLoad14'], 'VRated', '230e3', 'FRated', '60', 'P', '248e6');
set_param([mdl '/DLoad14'], 'component_structure', 'ee.enum.rlc.structure.R');

% Control signal for SW14 (Step: closed initially, opens at t_trip)
add_block('nesl_utility/Simulink-PS Converter', [mdl '/S2PS_14'], ...
    'Position', [1060, 570, 1090, 600]);
add_block('simulink/Sources/Step', [mdl '/Trip14'], ...
    'Position', [1010, 575, 1040, 595]);
% Initially closed (value=1), trip at t=1s (value=0 -> open)
set_param([mdl '/Trip14'], 'Time', '1', 'Before', '1', 'After', '0');

% Wire SW14
add_line(mdl, 'Trip14/1', 'S2PS_14/1');
add_line(mdl, 'S2PS_14/RConn1', 'SW14/LConn1');  % control
add_line(mdl, 'L_10_14/RConn1', 'SW14/LConn2');   % bus side (Bus14 node)
add_line(mdl, 'SW14/RConn1', 'DLoad14/LConn1');    % load side
fprintf('    SW14 + DLoad14 (248 MW) added\n');

% --- Bus 15: Replace fixed Load15 with Switch + Load ---
try
    ph15 = get_param([mdl '/Load15'], 'PortHandles');
    for p = ph15.LConn
        lh = get_param(p, 'Line');
        if lh ~= -1, delete_line(lh); end
    end
    delete_block([mdl '/Load15']);
catch; end

% Add switch for Load15
add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)', [mdl '/SW15'], ...
    'Position', [920, 580, 970, 660]);

% Add disturbance load (188 MW)
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load', [mdl '/DLoad15'], ...
    'Position', [1000, 580, 1070, 660]);
set_param([mdl '/DLoad15'], 'VRated', '230e3', 'FRated', '60', 'P', '188e6');
set_param([mdl '/DLoad15'], 'component_structure', 'ee.enum.rlc.structure.R');

% Control signal for SW15 (Step: open initially, closes at t_trip)
add_block('nesl_utility/Simulink-PS Converter', [mdl '/S2PS_15'], ...
    'Position', [860, 570, 890, 600]);
add_block('simulink/Sources/Step', [mdl '/Trip15'], ...
    'Position', [810, 575, 840, 595]);
% Initially open (value=0), close at t=1s (value=1 -> close, adds load)
set_param([mdl '/Trip15'], 'Time', '100', 'Before', '0', 'After', '1');
% Default: t=100 means switch stays open (no disturbance)

% Wire SW15
add_line(mdl, 'Trip15/1', 'S2PS_15/1');
add_line(mdl, 'S2PS_15/RConn1', 'SW15/LConn1');
add_line(mdl, 'L_9_15/RConn1', 'SW15/LConn2');
add_line(mdl, 'SW15/RConn1', 'DLoad15/LConn1');
fprintf('    SW15 + DLoad15 (188 MW) added\n');

%% ========== Section 2: Measurement Outputs (To Workspace) ==========
fprintf('  Section 2: Measurement outputs (simlog-based)...\n');

% Enable Simscape logging with selective logging for performance
set_param(mdl, 'SimscapeLogType', 'all', 'SimscapeLogName', 'simlog');
% Note: For fast RL training, set SimscapeLogType='none' and use
% custom measurement blocks instead.

%% ========== Section 3: Configure for Python Interface ==========
fprintf('  Section 3: Python interface configuration...\n');

% Set simulation parameters for RL training
set_param(mdl, 'StopTime', '10');       % 10s per episode
set_param(mdl, 'Solver', 'ode23t');
set_param(mdl, 'RelTol', '1e-4');
set_param(mdl, 'MaxStep', '0.01');

% The Trip14/Trip15 Step block times can be set from Python via:
%   eng.set_param('kundur_two_area/Trip14', 'Time', '2.0', nargout=0)
% before each episode to configure disturbance timing.

%% ========== Save ==========
save_system(mdl);
fprintf('Disturbance mechanism and interface added. Model saved.\n');
fprintf('\nUsage:\n');
fprintf('  Load Step 1 (Bus14, -248 MW): set Trip14 Time to desired trip time\n');
fprintf('  Load Step 2 (Bus15, +188 MW): set Trip15 Time to desired connect time\n');
fprintf('  No disturbance: set Trip14 Time > StopTime, Trip15 Time > StopTime\n');
fprintf('\nFrom Python (matlab.engine):\n');
fprintf('  eng.set_param(''kundur_two_area/Trip14'', ''Time'', ''1.0'', nargout=0)\n');
fprintf('  eng.sim(''kundur_two_area'', nargout=1)\n');
