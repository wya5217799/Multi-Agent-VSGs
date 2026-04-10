%% build_kundur_simulink.m
% Programmatically builds the Modified Kundur Two-Area System in Simulink
% using Simscape Electrical blocks.
%
% Topology (Yang et al., IEEE TPWRS 2023):
%   Area 1: G1(Bus1), G2(Bus2)
%   Area 2: G3(Bus3), W1(Bus4, wind farm replacing G4)
%   Tie:    Bus7 -- Bus8 (weak coupling, 3 parallel lines)
%   Wind:   W2(Bus8, 100 MW)
%   VSGs:   ES1(Bus12)->Bus7, ES2(Bus16)->Bus8,
%           ES3(Bus14)->Bus10, ES4(Bus15)->Bus9
%
% Block port maps (verified for R2025b):
%   SM Round Rotor: LConn1,2=field, LConn3=mech_C, LConn4=mech_R,
%                   RConn2=3ph_composite, RConn3=neutral
%   Simplified Generator: LConn1=mech_C, LConn2=mech_R,
%                          RConn1=3ph_composite, RConn2=neutral

%% ========== Parameters ==========
mdl = 'kundur_two_area';
Sbase = 100e6;   % 100 MVA system base
Vbase = 230e3;   % 230 kV transmission base
Vgen  = 20e3;    % 20 kV generator bus
fn    = 60;      % Nominal frequency (Hz)
Zbase = Vbase^2 / Sbase;  % 529 Ohm

% Standard Kundur line parameters (per unit on 100 MVA, 230 kV)
% Converted to physical for Simscape Transmission Line blocks
% R (Ohm/km), L (mH/km), C_line(uF/km), C_ground(uF/km)

% Intra-area lines: r=0.0001, x=0.001, b=0.00175 pu/km (approx)
% Tie line: r=0.0001, x=0.001, b=0.00175 pu/km

%% ========== Create Model ==========
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
open_system(mdl);

% Load required libraries
load_system('ee_lib');
load_system('nesl_utility');
load_system('fl_lib');
load_system('simulink');

% Set solver
set_param(mdl, 'Solver', 'ode23t', 'StopTime', '20', ...
    'RelTol', '1e-4', 'MaxStep', '0.01');

%% ========== Helper: Bus Bar Subsystem ==========
% Creates a subsystem acting as an electrical bus bar with N 3-phase ports
% Uses internal Simscape connection ports wired together

function create_bus_bar(mdl, busName, nPorts, pos)
    fullPath = [mdl '/' busName];
    add_block('built-in/Subsystem', fullPath, 'Position', pos);

    % Add connection ports inside
    for k = 1:nPorts
        portBlk = sprintf('%s/p%d', fullPath, k);
        add_block('nesl_utility/Connection Port', portBlk, ...
            'Position', [50, 50*k, 80, 50*k+20], ...
            'Side', 'left');
    end

    % Wire all ports together inside (chain: p1-p2, p2-p3, etc.)
    % For branching, connect each subsequent port to p1
    if nPorts > 1
        for k = 2:nPorts
            try
                add_line(fullPath, 'p1/RConn1', sprintf('p%d/RConn1', k));
            catch
                % If direct fails, try coordinate routing
                try
                    p1pos = get_param([fullPath '/p1'], 'Position');
                    pkpos = get_param(sprintf('%s/p%d', fullPath, k), 'Position');
                    midX = p1pos(3) + 30;
                    add_line(fullPath, [p1pos(3)+5, mean(p1pos([2,4])); ...
                                        midX, mean(p1pos([2,4])); ...
                                        midX, mean(pkpos([2,4])); ...
                                        pkpos(1)-5, mean(pkpos([2,4]))]);
                catch
                    warning('Bus %s: could not wire port %d to port 1', busName, k);
                end
            end
        end
    end
end

%% ========== Helper: Add Simplified Generator ==========
function add_simplified_gen(mdl, name, pos, Prated, Vrms, J, D, fdroop)
    blk = [mdl '/' name];
    add_block('ee_lib/Electromechanical/Simplified Generator', blk, 'Position', pos);
    set_param(blk, 'RatedPower', num2str(Prated));
    set_param(blk, 'FRated', '60');
    set_param(blk, 'VinternalRMS', num2str(Vrms));
    set_param(blk, 'RotorInertia', num2str(J));
    set_param(blk, 'RotorDamping', num2str(D));
    set_param(blk, 'Fdroop', num2str(fdroop));
end

%% ========== Helper: Connect generator to bus and references ==========
function connect_simplified_gen(mdl, genName, busName, busPort, gndName, mechRefName)
    % 3-phase output -> bus
    add_line(mdl, [genName '/RConn1'], [busName '/LConn' num2str(busPort)]);
    % Neutral -> ground
    add_line(mdl, [genName '/RConn2'], [gndName '/LConn1']);
    % Mech shaft -> mech ref
    add_line(mdl, [genName '/LConn1'], [mechRefName '/LConn1']);
    % Mech ref -> mech ref
    add_line(mdl, [genName '/LConn2'], [mechRefName '/LConn1']);
end

%% ========== Section 1: Global References ==========
fprintf('Building model: %s\n', mdl);
fprintf('  Section 1: Global references...\n');

add_block('nesl_utility/Solver Configuration', [mdl '/Solver'], ...
    'Position', [20, 20, 100, 60]);
add_block('ee_lib/Connectors & References/Electrical Reference', [mdl '/GND'], ...
    'Position', [50, 900, 80, 930]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference', [mdl '/MechRef'], ...
    'Position', [150, 900, 180, 930]);

% Connect Solver to GND
add_line(mdl, 'Solver/RConn1', 'GND/LConn1');

%% ========== Section 2: Generators ==========
fprintf('  Section 2: Generators (G1-G3, W1, W2)...\n');

% Generator parameters (Kundur standard)
% Using Simplified Generator for all machines (swing equation built-in)
% Physical inertia J = 2*H*Sn / (2*pi*fn)^2

H_gen = 6.5;   % Inertia constant for G1,G2 (s)
H_g3  = 6.175; % Inertia constant for G3 (s)
Sn_gen = 900e6; % 900 MVA for main generators

% J = 2*H*Sn / omega_s^2, omega_s = 2*pi*fn/p, p=1 pole pair
omega_s = 2*pi*fn;
J_g12 = 2 * H_gen * Sn_gen / omega_s^2;
J_g3  = 2 * H_g3  * Sn_gen / omega_s^2;

% Internal voltage (line-to-line RMS / sqrt(3) for phase RMS)
Vint_gen = Vgen / sqrt(3);  % ~11.547 kV phase RMS
Vint_230 = Vbase / sqrt(3); % ~132.8 kV phase RMS for 230kV bus machines

% G1 - Bus 1 (Area 1, Slack)
add_simplified_gen(mdl, 'G1', [100, 100, 200, 250], ...
    Sn_gen*0.85, Vint_230, J_g12, 50, 0.05);

% G2 - Bus 2 (Area 1)
add_simplified_gen(mdl, 'G2', [100, 300, 200, 450], ...
    Sn_gen*0.78, Vint_230, J_g12, 50, 0.05);

% G3 - Bus 3 (Area 2)
add_simplified_gen(mdl, 'G3', [1200, 100, 1300, 250], ...
    Sn_gen*0.78, Vint_230, J_g3, 50, 0.05);

% W1 - Bus 4 (Area 2, wind farm replacing G4, ~900 MVA but low inertia)
% Wind farm: very low inertia, minimal droop (must be > 0 for Simplified Generator)
J_w1 = 2 * 0.5 * Sn_gen / omega_s^2;  % H=0.5s equivalent
add_simplified_gen(mdl, 'W1', [1200, 300, 1300, 450], ...
    Sn_gen*0.78, Vint_230, J_w1, 5, 0.001);

% W2 - Bus 8 area (100 MW wind farm, low inertia)
Sn_w2 = 100e6;
J_w2 = 2 * 0.5 * Sn_w2 / omega_s^2;
add_simplified_gen(mdl, 'W2', [700, 600, 800, 750], ...
    Sn_w2*0.9, Vint_230, J_w2, 2, 0.001);

%% ========== Section 3: VSGs (ES1-ES4) ==========
fprintf('  Section 3: VSGs (ES1-ES4)...\n');

% VSG parameters from Yang et al.
Sn_vsg = 200e6;  % 200 MVA each
M0 = 12.0;       % M = 2H -> H = 6.0 s
D0 = 3.0;        % Damping coefficient

J_vsg = M0 * Sn_vsg / omega_s^2;  % Convert M to J
D_vsg = D0 * Sn_vsg / omega_s^2;  % Convert D to physical damping

% ES1 - Bus 12 (connected to Bus 7, Area 1)
add_simplified_gen(mdl, 'ES1', [500, 500, 600, 650], ...
    Sn_vsg*0.5, Vint_230, J_vsg, D_vsg, 0.05);

% ES2 - Bus 16 (connected to Bus 8, tie area)
add_simplified_gen(mdl, 'ES2', [700, 800, 800, 950], ...
    Sn_vsg*0.5, Vint_230, J_vsg, D_vsg, 0.05);

% ES3 - Bus 14 (connected to Bus 10, Area 2)
add_simplified_gen(mdl, 'ES3', [1100, 500, 1200, 650], ...
    Sn_vsg*0.5, Vint_230, J_vsg, D_vsg, 0.05);

% ES4 - Bus 15 (connected to Bus 9, Area 2)
add_simplified_gen(mdl, 'ES4', [900, 500, 1000, 650], ...
    Sn_vsg*0.5, Vint_230, J_vsg, D_vsg, 0.05);

%% ========== Section 4: Transmission Lines ==========
fprintf('  Section 4: Transmission lines...\n');

% Helper to add a transmission line
function add_tline(mdl, name, pos, len_km, R_ohm_km, L_mH_km, Cl_uF_km)
    blk = [mdl '/' name];
    add_block('ee_lib/Passive/Lines/Transmission Line (Three-Phase)', blk, ...
        'Position', pos);
    set_param(blk, 'length', num2str(len_km));
    set_param(blk, 'R', num2str(R_ohm_km));
    set_param(blk, 'L', num2str(L_mH_km));
    set_param(blk, 'Cl', num2str(Cl_uF_km));
    set_param(blk, 'freq', '60');
end

% Kundur standard line parameters (230 kV base)
% Typical values: r1=0.0529 Ohm/km, x1=0.529 Ohm/km, b1=3.31 uS/km
R_line = 0.053;   % Ohm/km
L_line = 1.41;    % mH/km (x = omega*L -> L = x/(2*pi*60))
C_line = 0.009;   % uF/km (shunt capacitance)

% Line lengths (standard Kundur):
% Bus5-Bus6: 25 km (x2 parallel)
% Bus6-Bus7: 10 km (x2 parallel)
% Bus7-Bus8: 110 km (x3 parallel, weak tie)
% Bus8-Bus9: 10 km (x2 parallel)
% Bus9-Bus10: 25 km (x2 parallel)

% Generator step-up equivalent lines (very short, transformer equivalent)
% Bus1->Bus5, Bus2->Bus6, Bus3->Bus10, Bus4->Bus9
add_tline(mdl, 'L_1_5',  [300, 130, 400, 180], 5, R_line, L_line, C_line);
add_tline(mdl, 'L_2_6',  [300, 350, 400, 400], 5, R_line, L_line, C_line);
add_tline(mdl, 'L_3_10', [1050, 130, 1150, 180], 5, R_line, L_line, C_line);
add_tline(mdl, 'L_4_9',  [1050, 350, 1150, 400], 5, R_line, L_line, C_line);

% Intra-Area 1 lines
add_tline(mdl, 'L_5_6a', [450, 200, 550, 250], 25, R_line, L_line, C_line);
add_tline(mdl, 'L_5_6b', [450, 280, 550, 330], 25, R_line, L_line, C_line);
add_tline(mdl, 'L_6_7a', [550, 130, 650, 180], 10, R_line, L_line, C_line);
add_tline(mdl, 'L_6_7b', [550, 200, 650, 250], 10, R_line, L_line, C_line);

% Tie lines (Bus7-Bus8, weak coupling)
add_tline(mdl, 'L_7_8a', [680, 300, 780, 350], 110, R_line, L_line, C_line);
add_tline(mdl, 'L_7_8b', [680, 370, 780, 420], 110, R_line, L_line, C_line);
add_tline(mdl, 'L_7_8c', [680, 440, 780, 490], 110, R_line, L_line, C_line);

% Intra-Area 2 lines
add_tline(mdl, 'L_8_9a', [850, 200, 950, 250], 10, R_line, L_line, C_line);
add_tline(mdl, 'L_8_9b', [850, 280, 950, 330], 10, R_line, L_line, C_line);
add_tline(mdl, 'L_9_10a', [950, 130, 1050, 180], 25, R_line, L_line, C_line);
add_tline(mdl, 'L_9_10b', [950, 200, 1050, 250], 25, R_line, L_line, C_line);

% VSG connection lines (short, low impedance)
R_vsg_line = 0.01;  % Ohm/km
L_vsg_line = 0.5;   % mH/km
add_tline(mdl, 'L_7_12',  [550, 450, 620, 500], 1, R_vsg_line, L_vsg_line, C_line);
add_tline(mdl, 'L_8_16',  [750, 650, 820, 700], 1, R_vsg_line, L_vsg_line, C_line);
add_tline(mdl, 'L_10_14', [1100, 450, 1170, 500], 1, R_vsg_line, L_vsg_line, C_line);
add_tline(mdl, 'L_9_15',  [900, 450, 970, 500], 1, R_vsg_line, L_vsg_line, C_line);

%% ========== Section 5: Loads + Shunt Compensation ==========
fprintf('  Section 5: Loads and shunt compensation...\n');

function add_wye_load(mdl, name, pos, Vrated, P, Q)
    blk = [mdl '/' name];
    add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load', blk, 'Position', pos);
    set_param(blk, 'VRated', num2str(Vrated), 'FRated', '60');
    set_param(blk, 'P', num2str(P));
    if Q >= 0
        set_param(blk, 'component_structure', 'ee.enum.rlc.structure.RL');
        set_param(blk, 'Qpos', num2str(max(Q, 1)));
    else
        set_param(blk, 'component_structure', 'ee.enum.rlc.structure.RC');
        set_param(blk, 'Qneg', num2str(Q));
    end
end

% Area 1 Load (Bus 7): 967 MW + j100 MVAr
add_wye_load(mdl, 'Load7', [620, 500, 690, 600], Vbase, 967e6, 100e6);

% Area 2 Load (Bus 9): 1767 MW + j100 MVAr
add_wye_load(mdl, 'Load9', [870, 500, 940, 600], Vbase, 1767e6, 100e6);

% Shunt compensation Bus 7: 200 MVAr capacitive (tiny P required > 0)
add_wye_load(mdl, 'Shunt7', [620, 620, 690, 700], Vbase, 1000, -200e6);

% Shunt compensation Bus 9: 350 MVAr capacitive
add_wye_load(mdl, 'Shunt9', [870, 620, 940, 700], Vbase, 1000, -350e6);

% Disturbance loads (Bus 14, Bus 15)
% Load14: 248 MW steady-state (can be tripped for Load Step 1)
add_wye_load(mdl, 'Load14', [1150, 600, 1220, 680], Vbase, 248e6, 0);
% Load15: 1 MW placeholder (increased to 188 MW for Load Step 2)
add_wye_load(mdl, 'Load15', [950, 600, 1020, 680], Vbase, 1e6, 0);

%% ========== Section 6: Network Connections ==========
fprintf('  Section 6: Wiring network...\n');

% Helper: connect a generator's RConn1 (3ph) to a line's LConn1 or RConn1
% and its RConn2 (neutral) and LConn1/2 (mech) to references

% Connect generators to their lines
% G1 -> L_1_5
connect_simplified_gen_to_line(mdl, 'G1', 'L_1_5', 'L', 'GND', 'MechRef');
% G2 -> L_2_6
connect_simplified_gen_to_line(mdl, 'G2', 'L_2_6', 'L', 'GND', 'MechRef');
% G3 -> L_3_10
connect_simplified_gen_to_line(mdl, 'G3', 'L_3_10', 'L', 'GND', 'MechRef');
% W1 -> L_4_9
connect_simplified_gen_to_line(mdl, 'W1', 'L_4_9', 'L', 'GND', 'MechRef');

% VSGs to their connection lines
connect_simplified_gen_to_line(mdl, 'ES1', 'L_7_12', 'R', 'GND', 'MechRef');
connect_simplified_gen_to_line(mdl, 'ES2', 'L_8_16', 'R', 'GND', 'MechRef');
connect_simplified_gen_to_line(mdl, 'ES3', 'L_10_14', 'R', 'GND', 'MechRef');
connect_simplified_gen_to_line(mdl, 'ES4', 'L_9_15', 'R', 'GND', 'MechRef');

% W2 -> Bus 8 area (direct connection via dedicated line)
add_tline(mdl, 'L_8_W2', [700, 750, 770, 800], 1, R_vsg_line, L_vsg_line, C_line);
connect_simplified_gen_to_line(mdl, 'W2', 'L_8_W2', 'L', 'GND', 'MechRef');

% Now wire the transmission network (line-to-line connections)
% Bus 5: L_1_5/R -> L_5_6a/L, L_5_6b/L
wire_lines(mdl, 'L_1_5', 'R', 'L_5_6a', 'L');
add_line(mdl, 'L_1_5/RConn1', 'L_5_6b/LConn1');

% Bus 6: L_5_6a/R, L_5_6b/R, L_2_6/R -> L_6_7a/L, L_6_7b/L
wire_lines(mdl, 'L_5_6a', 'R', 'L_6_7a', 'L');
add_line(mdl, 'L_5_6a/RConn1', 'L_6_7b/LConn1');
add_line(mdl, 'L_5_6b/RConn1', 'L_5_6a/RConn1');
add_line(mdl, 'L_2_6/RConn1', 'L_5_6a/RConn1');

% Bus 7: L_6_7a/R, L_6_7b/R -> L_7_8a/L, L_7_8b/L, L_7_8c/L, Load7, Shunt7, L_7_12/L
wire_lines(mdl, 'L_6_7a', 'R', 'L_7_8a', 'L');
add_line(mdl, 'L_6_7a/RConn1', 'L_7_8b/LConn1');
add_line(mdl, 'L_6_7a/RConn1', 'L_7_8c/LConn1');
add_line(mdl, 'L_6_7a/RConn1', 'Load7/LConn1');
add_line(mdl, 'L_6_7a/RConn1', 'Shunt7/LConn1');
add_line(mdl, 'L_6_7a/RConn1', 'L_7_12/LConn1');
add_line(mdl, 'L_6_7b/RConn1', 'L_6_7a/RConn1');

% Bus 8: L_7_8a/R, L_7_8b/R, L_7_8c/R -> L_8_9a/L, L_8_9b/L, L_8_16/L, L_8_W2/R
wire_lines(mdl, 'L_7_8a', 'R', 'L_8_9a', 'L');
add_line(mdl, 'L_7_8a/RConn1', 'L_8_9b/LConn1');
add_line(mdl, 'L_7_8a/RConn1', 'L_8_16/LConn1');
add_line(mdl, 'L_7_8a/RConn1', 'L_8_W2/RConn1');
add_line(mdl, 'L_7_8b/RConn1', 'L_7_8a/RConn1');
add_line(mdl, 'L_7_8c/RConn1', 'L_7_8a/RConn1');

% Bus 9: L_8_9a/R, L_8_9b/R, L_4_9/R -> L_9_10a/L, L_9_10b/L, Load9, Shunt9, L_9_15/L
wire_lines(mdl, 'L_8_9a', 'R', 'L_9_10a', 'L');
add_line(mdl, 'L_8_9a/RConn1', 'L_9_10b/LConn1');
add_line(mdl, 'L_8_9a/RConn1', 'Load9/LConn1');
add_line(mdl, 'L_8_9a/RConn1', 'Shunt9/LConn1');
add_line(mdl, 'L_8_9a/RConn1', 'L_9_15/LConn1');
add_line(mdl, 'L_8_9b/RConn1', 'L_8_9a/RConn1');
add_line(mdl, 'L_4_9/RConn1', 'L_8_9a/RConn1');

% Bus 10: L_9_10a/R, L_9_10b/R, L_3_10/R -> L_10_14/L
wire_lines(mdl, 'L_9_10a', 'R', 'L_10_14', 'L');
add_line(mdl, 'L_9_10b/RConn1', 'L_9_10a/RConn1');
add_line(mdl, 'L_3_10/RConn1', 'L_9_10a/RConn1');
add_line(mdl, 'L_9_10a/RConn1', 'Load14/LConn1');

% Bus 15: L_9_15/R -> Load15
add_line(mdl, 'L_9_15/RConn1', 'Load15/LConn1');

%% ========== Section 7: Ground connections for TLines ==========
fprintf('  Section 7: Ground connections...\n');

% Each transmission line has LConn2 and RConn2 as ground references
% Connect all to GND
tlines = {'L_1_5','L_2_6','L_3_10','L_4_9',...
          'L_5_6a','L_5_6b','L_6_7a','L_6_7b',...
          'L_7_8a','L_7_8b','L_7_8c',...
          'L_8_9a','L_8_9b','L_9_10a','L_9_10b',...
          'L_7_12','L_8_16','L_10_14','L_9_15','L_8_W2'};

for i = 1:length(tlines)
    try
        add_line(mdl, [tlines{i} '/LConn2'], 'GND/LConn1');
    catch; end
    try
        add_line(mdl, [tlines{i} '/RConn2'], 'GND/LConn1');
    catch; end
end

%% ========== Section 8: Save ==========
fprintf('  Saving model...\n');
save_system(mdl);
fprintf('Model %s.slx built successfully!\n', mdl);

%% ========== Helper Functions ==========
function connect_simplified_gen_to_line(mdl, genName, lineName, side, gndName, mechRefName)
    % Connect gen 3ph output to line
    if strcmp(side, 'L')
        add_line(mdl, [genName '/RConn1'], [lineName '/LConn1']);
    else
        add_line(mdl, [genName '/RConn1'], [lineName '/RConn1']);
    end
    % Neutral -> ground
    add_line(mdl, [genName '/RConn2'], [gndName '/LConn1']);
    % Mechanical -> reference
    add_line(mdl, [genName '/LConn1'], [mechRefName '/LConn1']);
    add_line(mdl, [genName '/LConn2'], [mechRefName '/LConn1']);
end

function wire_lines(mdl, line1, side1, line2, side2)
    % Connect two transmission lines at a bus
    port1 = [line1 '/' side1 'Conn1'];
    port2 = [line2 '/' side2 'Conn1'];
    add_line(mdl, port1, port2);
end
