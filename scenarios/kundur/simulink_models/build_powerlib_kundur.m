%% build_powerlib_kundur.m
% Build full 16-bus Modified Kundur Two-Area System with Simscape Electrical (ee_lib).
%
% Architecture (Yang et al. TPWRS 2023):
%   Area 1: G1(Bus1), G2(Bus2), W1(Bus4) — conventional gens + wind farm
%   Area 2: G3(Bus3), W2(Bus8 area) — conventional gen + wind farm
%   Tie:    Bus7–Bus8 (triple parallel 110km lines — weak inter-area link)
%   VSGs:   ES1(Bus12→Bus7), ES2(Bus16→Bus8), ES3(Bus14→Bus10), ES4(Bus15→Bus9)
%
% Components:
%   - 3 Conventional Generators (G1-G3): signal-domain swing eq + governor droop
%     → Controlled Voltage Source (Three-Phase) driven by omega/delta
%   - 2 Wind Farms (W1, W2): Programmable Voltage Source (Three-Phase)
%   - 4 VSG/ESS (ES1-ES4): signal-domain swing eq with RL control inputs
%     → Controlled Voltage Source (Three-Phase) driven by delta output
%   - 16-bus transmission network (Transmission Line Three-Phase)
%   - 2 constant loads + 2 shunt capacitors (Wye-Connected Load)
%   - 2 disturbance breakers + trip loads
%   - Solver Configuration + Electrical Reference (replaces powergui)
%   - Power Sensor (Three-Phase) for P_e feedback → closed-loop VSG
%   - ToWorkspace loggers for Python co-simulation
%
% P_e STRATEGY (v3 — Power Sensor, true closed-loop):
%   ESS:     P_e from Power Sensor (Three-Phase) → PS2S → Gain(1/VSG_SN)
%   ConvGen: P_e from Power Sensor (Three-Phase) → PS2S → Gain(1/Sbase)
%   Wind:    No swing equation, no P_e needed
%   P_ref:   Ramped 0→nominal over T_ramp=2s (avoids RL inrush voltage collapse)
%
% IMPORTANT: Uses ee_lib (Simscape Electrical) blocks exclusively.
%   Controlled Voltage Sources are driven by signal-domain swing equations
%   via Simulink-PS Converter, enabling true closed-loop VSG control.
%
% Port mapping (verified R2025b):
%   CVS:  LConn1=signal input, LConn2=neutral→GND, RConn1=3ph output
%   PVS:  LConn1=neutral→GND, RConn1=3ph output
%   TL:   LConn1/2=sending(3ph+gnd), RConn1/2=receiving(3ph+gnd)
%   WyeLoad: LConn1=3ph input, RConn1=neutral→GND
%   RLC3ph:  LConn1=side A, RConn1=side B
%   CB:   LConn1=signal control, LConn2=3ph side A, RConn1=3ph side B
%   PSensor: LConn1=3ph input, LConn2=P signal output, LConn3=Q signal output, RConn1=3ph pass-through
%
% Usage:
%   cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur\simulink_models')
%   build_powerlib_kundur
%
% Reference:
%   Yang et al., IEEE TPWRS 2023

clear all; close all; clc;

%% ======================================================================
%  Parameters
%% ======================================================================
fn = 50;                  % System frequency (Hz)
wn = 2*pi*fn;             % Angular frequency (rad/s)
Sbase = 100e6;            % System base (VA) = 100 MVA
Vbase = 230e3;            % System voltage (V) — single level, no transformers
Vpk = Vbase * sqrt(2/3);  % Peak phase voltage for instantaneous waveform

% Base impedance
Zbase = Vbase^2 / Sbase;  % 529 Ohm

% Generator internal impedance (on Sbase)
% Transient reactance Xd' ~ 0.30 pu, Ra ~ 0.003 pu
R_gen_pu = 0.003;
X_gen_pu = 0.30;
R_gen = R_gen_pu * Zbase;              % Ohm
L_gen = X_gen_pu * Zbase / (2*pi*fn);  % H

% P_ref ramp time — electrical RL time constant is L/R = 0.318s,
% need ~5*tau = 1.6s for steady state. Use 2s for margin.
T_ramp = 2.0;  % seconds: P_ref ramps from 0 to nominal over this duration

% --- Conventional generators G1-G3 ---
%   G1 at Bus1: H=6.5s, Sn=900MVA, P0=700MW, D=5.0, R=0.05
%   G2 at Bus2: H=6.5s, Sn=900MVA, P0=700MW, D=5.0, R=0.05
%   G3 at Bus3: H=6.175s, Sn=900MVA, P0=719MW, D=5.0, R=0.05
gen_cfg = struct( ...
    'name',  {'G1',   'G2',   'G3'}, ...
    'bus',   {1,      2,      3}, ...
    'H',     {6.5,    6.5,    6.175}, ...
    'Sn',    {900e6,  900e6,  900e6}, ...
    'P0_MW', {700,    700,    719}, ...
    'D',     {5.0,    5.0,    5.0}, ...
    'R',     {0.05,   0.05,   0.05});

% --- Wind farms W1, W2 ---
%   W1 at Bus4: 700 MW, Sn=900MVA (constant power, no swing eq)
%   W2 near Bus8: 100 MW, Sn=200MVA
wind_cfg = struct( ...
    'name',  {'W1',  'W2'}, ...
    'bus',   {4,     11}, ...   % Bus11 = W2 connection node near Bus8
    'P0_MW', {700,   100}, ...
    'Sn',    {900e6, 200e6});

% --- VSG/ESS parameters (from config.py / Yang et al.) ---
n_vsg = 4;
VSG_M0 = 12.0;            % M = 2H (s), H0 = 6.0 s
VSG_D0 = 3.0;             % Damping (p.u.)
VSG_SN = 200e6;            % VSG rated power (VA) = 200 MVA

% Initial P_e/P_ref (p.u. on VSG base), calibrated from steady-state V*I measurement.
% These values ensure P_mech = P_e at t=0 so omega stays at 1.0.
% Recalibrate if you change source voltages, angles, or line impedances.
VSG_P0 = [1.8725, 1.8419, 1.7888, 1.9154];  % [ES1, ES2, ES3, ES4]

% ESS bus assignments: ES{i} sits on a dedicated bus, connected to a main bus
%   ES1 → Bus12, connected to Bus7
%   ES2 → Bus16, connected to Bus8
%   ES3 → Bus14, connected to Bus10
%   ES4 → Bus15, connected to Bus9
ess_bus     = [12, 16, 14, 15];
ess_main    = [ 7,  8, 10,  9];

% --- Load flow initial conditions ---
% Rough initial angles (will be corrected by solver)
% [V_pu, angle_deg] — used for source initialization
vlf_gen = [1.03,  0.0;    % G1 (slack equivalent)
           1.01, -2.5;    % G2
           1.01, -5.0];   % G3
vlf_wind = [1.00, -1.0;   % W1
            1.00, -4.0];  % W2
vlf_ess = [1.00, -3.0;    % ES1
           1.00, -4.5;    % ES2
           1.00, -5.5;    % ES3
           1.00, -3.5];   % ES4

% --- Transmission line parameters ---
% Standard Kundur lines: R=0.053 Ohm/km, L=1.41 mH/km, C=0.009 uF/km
R_std = 0.053;   % Ohm/km
L_std = 1.41e-3; % H/km
C_std = 0.009e-6;% F/km

% Short VSG connection lines: R=0.01 Ohm/km, L=0.5 mH/km, C=0.009 uF/km
R_short = 0.01;
L_short = 0.5e-3;
C_short = 0.009e-6;

% Line definitions: {name, from_bus, to_bus, length_km, R, L, C}
line_defs = {
    % Gen-to-bus connections (short)
    'L_1_5',   1,  5,   5, R_std, L_std, C_std;
    'L_2_6',   2,  6,   5, R_std, L_std, C_std;
    'L_3_10',  3, 10,   5, R_std, L_std, C_std;
    'L_4_9',   4,  9,   5, R_std, L_std, C_std;  % W1 at Bus4 → Bus9
    % Area 1 network
    'L_5_6a',  5,  6,  25, R_std, L_std, C_std;
    'L_5_6b',  5,  6,  25, R_std, L_std, C_std;
    'L_6_7a',  6,  7,  10, R_std, L_std, C_std;
    'L_6_7b',  6,  7,  10, R_std, L_std, C_std;
    % Inter-area tie (weak — triple parallel 110 km)
    'L_7_8a',  7,  8, 110, R_std, L_std, C_std;
    'L_7_8b',  7,  8, 110, R_std, L_std, C_std;
    'L_7_8c',  7,  8, 110, R_std, L_std, C_std;
    % Area 2 network
    'L_8_9a',  8,  9,  10, R_std, L_std, C_std;
    'L_8_9b',  8,  9,  10, R_std, L_std, C_std;
    'L_9_10a', 9, 10,  25, R_std, L_std, C_std;
    'L_9_10b', 9, 10,  25, R_std, L_std, C_std;
    % VSG connection lines (short, low impedance)
    'L_7_12',  7, 12,   1, R_short, L_short, C_short;  % ES1
    'L_8_16',  8, 16,   1, R_short, L_short, C_short;  % ES2
    'L_10_14',10, 14,   1, R_short, L_short, C_short;  % ES3
    'L_9_15',  9, 15,   1, R_short, L_short, C_short;  % ES4
    'L_8_W2',  8, 11,   1, R_short, L_short, C_short;  % W2 connection
};

% --- Loads ---
% Load7 at Bus7: 967 MW + 100 Mvar
% Load9 at Bus9: 1767 MW + 100 Mvar
load_defs = struct( ...
    'name',  {'Load7',  'Load9'}, ...
    'bus',   {7,        9}, ...
    'P_MW',  {967,      1767}, ...
    'Q_Mvar',{100,      100});

% --- Shunt capacitors ---
% Shunt7 at Bus7: 200 Mvar capacitive
% Shunt9 at Bus9: 350 Mvar capacitive
shunt_defs = struct( ...
    'name',   {'Shunt7', 'Shunt9'}, ...
    'bus',    {7,        9}, ...
    'Q_Mvar', {200,      350});

% --- Disturbance breakers ---
% Breaker_1 at Bus14: TripLoad_1 = 248 MW, initially CLOSED, opens at t=100
% Breaker_2 at Bus15: TripLoad_2 = 188 MW, initially OPEN, closes at t=100
brk_defs = struct( ...
    'name',       {'Breaker_1',  'Breaker_2'}, ...
    'bus',        {14,           15}, ...
    'trip_P_MW',  {248,          188}, ...
    'init_state', {'closed',     'open'}, ...
    'switch_time',{100,          100});

%% ======================================================================
%  Step 0: Create new model and find ee_lib block paths
%% ======================================================================
mdl = 'kundur_vsg';
model_dir = fileparts(mfilename('fullpath'));

if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('ee_lib');
load_system('nesl_utility');

fprintf('=== Building %s (16-bus Modified Kundur, ee_lib, Power Sensor P_e) ===\n', mdl);

% --- Find ee_lib block library paths dynamically ---
cvs_lib = char(find_system('ee_lib/Sources', 'SearchDepth', 1, 'RegExp', 'on', 'Name', '.*Controlled Voltage.*Three.*'));
pvs_lib = char(find_system('ee_lib/Sources', 'SearchDepth', 1, 'RegExp', 'on', 'Name', '.*Programmable Voltage.*Three.*'));
tl_lib = char(find_system('ee_lib', 'SearchDepth', 5, 'RegExp', 'on', 'Name', '.*Transmission Line.*Three.*'));
wl_lib = char(find_system('ee_lib', 'SearchDepth', 5, 'Name', 'Wye-Connected Load'));
rlc3_lib = char(find_system('ee_lib/Passive/RLC Assemblies', 'SearchDepth', 1, 'Name', 'RLC (Three-Phase)'));
gnd_lib = char(find_system('ee_lib', 'SearchDepth', 3, 'Name', 'Electrical Reference'));
cb_lib = char(find_system('ee_lib', 'SearchDepth', 5, 'RegExp', 'on', 'Name', '.*Circuit Breaker.*Three.*'));
ps_lib = char(find_system('ee_lib', 'SearchDepth', 5, 'RegExp', 'on', 'Name', '.*Power Sensor.*Three.*'));
solver_lib = char(find_system('nesl_utility', 'SearchDepth', 1, 'Name', 'Solver Configuration'));
s2ps_lib = char(find_system('nesl_utility', 'SearchDepth', 2, 'RegExp', 'on', 'Name', '.*Simulink-PS.*'));
ps2s_lib = char(find_system('nesl_utility', 'SearchDepth', 2, 'RegExp', 'on', 'Name', '.*PS-Simulink.*'));
if size(ps2s_lib,1) > 1, ps2s_lib = ps2s_lib(1,:); end
ps2s_lib = strtrim(ps2s_lib);

% Handle multi-row results from find_system (take first row)
if size(cvs_lib,1) > 1, cvs_lib = cvs_lib(1,:); end
if size(pvs_lib,1) > 1, pvs_lib = pvs_lib(1,:); end
if size(tl_lib,1) > 1, tl_lib = tl_lib(1,:); end
if size(wl_lib,1) > 1, wl_lib = wl_lib(1,:); end
if size(rlc3_lib,1) > 1, rlc3_lib = rlc3_lib(1,:); end
if size(gnd_lib,1) > 1, gnd_lib = gnd_lib(1,:); end
if size(cb_lib,1) > 1, cb_lib = cb_lib(1,:); end
if size(ps_lib,1) > 1, ps_lib = ps_lib(1,:); end
if size(solver_lib,1) > 1, solver_lib = solver_lib(1,:); end

cvs_lib = strtrim(cvs_lib);
pvs_lib = strtrim(pvs_lib);
tl_lib = strtrim(tl_lib);
wl_lib = strtrim(wl_lib);
rlc3_lib = strtrim(rlc3_lib);
gnd_lib = strtrim(gnd_lib);
cb_lib = strtrim(cb_lib);
ps_lib = strtrim(ps_lib);
solver_lib = strtrim(solver_lib);

fprintf('  CVS lib: %s\n', cvs_lib);
fprintf('  PVS lib: %s\n', pvs_lib);
fprintf('  TL lib:  %s\n', tl_lib);
fprintf('  WyeLoad: %s\n', wl_lib);
fprintf('  RLC3ph:  %s\n', rlc3_lib);
fprintf('  GND lib: %s\n', gnd_lib);
fprintf('  CB lib:  %s\n', cb_lib);
fprintf('  PSensor: %s\n', ps_lib);
fprintf('  Solver:  %s\n', solver_lib);

%% ======================================================================
%  Step 1: Solver Configuration + Electrical Reference (replaces powergui)
%% ======================================================================
add_block(solver_lib, [mdl '/SolverConfig'], 'Position', [20 20 120 60]);
% NOTE: SolverConfig connected to main network in Step 9b (after all bus topology built).
fprintf('  Solver Configuration added (will connect to network in Step 9b).\n');

%% ======================================================================
%  Step 2: Bus node tracking
%% ======================================================================
% bus_nodes{bus_id} = {block_name, port_fmt} for the bus representative.
bus_nodes = cell(1, 20);  % up to 20 buses

% Global ground counter for unique GND names
gnd_count = 0;

%% ======================================================================
%  Step 3: Conventional Generators G1-G3
%% ======================================================================
% Each gen has:
%   - ConvGen_G{i} subsystem (signal-domain swing eq + governor droop)
%   - Voltage generation: Clock*wn + delta → sin → 3ph Vabc
%   - Simulink-PS Converter → Controlled Voltage Source (Three-Phase)
%   - RLC (Three-Phase) for generator impedance
%   - P_e = constant P0_pu (governor droop handles regulation internally)
%
% Swing equation:
%   M = 2*H
%   P_mech = P0 - (omega-1) * Sn / (R * Sbase)   (governor droop)
%   d(omega)/dt = (1/M) * (P_mech - P_e - D*(omega-1))
%   d(delta)/dt = wn * (omega - 1)

fprintf('\n=== Building conventional generators G1-G3 ===\n');

for gi = 1:length(gen_cfg)
    g = gen_cfg(gi);
    gname = g.name;
    bus_id = g.bus;
    M = 2 * g.H;
    P0_pu = g.P0_MW * 1e6 / Sbase;   % p.u. on Sbase
    droop_gain = g.Sn / (g.R * Sbase); % Sn/(R*Sbase)
    V_gen = Vbase * vlf_gen(gi, 1);
    Vpk_gen = V_gen * sqrt(2/3);

    bx = 100 + (gi-1)*500;
    by = 100;

    % --- Subsystem: ConvGen_G{i} (signal-domain swing equation) ---
    sub_path = [mdl '/ConvGen_' gname];
    add_block('built-in/SubSystem', sub_path, ...
        'Position', [bx by bx+120 by+80]);

    % Input: P_e (electrical power feedback — constant for ConvGen)
    add_block('built-in/Inport', [sub_path '/P_e'], ...
        'Position', [30 50 60 64], 'Port', '1');
    % Outputs: omega, delta
    add_block('built-in/Outport', [sub_path '/omega'], ...
        'Position', [700 50 730 64], 'Port', '1');
    add_block('built-in/Outport', [sub_path '/delta'], ...
        'Position', [700 150 730 164], 'Port', '2');

    % Constants
    add_block('built-in/Constant', [sub_path '/M_val'], ...
        'Position', [100 10 150 30], 'Value', num2str(M));
    add_block('built-in/Constant', [sub_path '/D_val'], ...
        'Position', [100 180 150 200], 'Value', num2str(g.D));
    % P0 ramp: 0 → P0_pu over T_ramp seconds (avoids RL inrush collapse)
    add_block('built-in/Ramp', [sub_path '/P0_ramp'], ...
        'Position', [30 90 70 110], ...
        'Slope', num2str(P0_pu / T_ramp), 'Start', '0', 'X0', '0');
    add_block('built-in/Saturate', [sub_path '/P0_sat'], ...
        'Position', [100 90 140 110], ...
        'UpperLimit', num2str(P0_pu), 'LowerLimit', '0');
    add_line(sub_path, 'P0_ramp/1', 'P0_sat/1');
    add_block('built-in/Constant', [sub_path '/DroopGain'], ...
        'Position', [100 130 150 150], 'Value', num2str(droop_gain));
    add_block('built-in/Constant', [sub_path '/wn_val'], ...
        'Position', [350 180 400 200], 'Value', num2str(wn));

    % omega_error = omega - 1
    add_block('built-in/Constant', [sub_path '/One'], ...
        'Position', [350 80 380 100], 'Value', '1');
    add_block('built-in/Sum', [sub_path '/SumWerr'], ...
        'Position', [420 50 450 80], 'Inputs', '+-');

    % Governor droop: P_gov_term = droop_gain * omega_error
    add_block('built-in/Product', [sub_path '/MulDroop'], ...
        'Position', [300 120 330 150], 'Inputs', '**');

    % P_mech = P0 - P_gov_term
    add_block('built-in/Sum', [sub_path '/SumPmech'], ...
        'Position', [370 100 400 130], 'Inputs', '+-');

    % D_term = D * omega_error
    add_block('built-in/Product', [sub_path '/MulD'], ...
        'Position', [470 120 500 150], 'Inputs', '**');

    % P_accel = P_mech - P_e - D_term
    add_block('built-in/Sum', [sub_path '/SumP'], ...
        'Position', [530 50 560 110], 'Inputs', '+--');

    % d_omega = P_accel / M
    add_block('built-in/Product', [sub_path '/DivM'], ...
        'Position', [580 50 610 90], 'Inputs', '*/');

    % Integrator for omega (IC = 1.0, clamped to [0.9, 1.1])
    add_block('built-in/Integrator', [sub_path '/IntW'], ...
        'Position', [630 50 670 90], ...
        'InitialCondition', '1.0', ...
        'LimitOutput', 'on', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');

    % Integrator for delta
    delta0_rad = vlf_gen(gi, 2) * pi / 180;
    add_block('built-in/Integrator', [sub_path '/IntD'], ...
        'Position', [500 170 540 210], ...
        'InitialCondition', num2str(delta0_rad));

    % delta rate: wn * omega_error
    add_block('built-in/Product', [sub_path '/MulWn'], ...
        'Position', [440 170 470 210], 'Inputs', '**');

    % === Wiring inside subsystem ===
    add_line(sub_path, 'IntW/1', 'omega/1');
    add_line(sub_path, 'IntW/1', 'SumWerr/1');
    add_line(sub_path, 'One/1', 'SumWerr/2');

    add_line(sub_path, 'DroopGain/1', 'MulDroop/1');
    add_line(sub_path, 'SumWerr/1', 'MulDroop/2');

    add_line(sub_path, 'P0_sat/1', 'SumPmech/1');
    add_line(sub_path, 'MulDroop/1', 'SumPmech/2');

    add_line(sub_path, 'D_val/1', 'MulD/1');
    add_line(sub_path, 'SumWerr/1', 'MulD/2');

    add_line(sub_path, 'SumPmech/1', 'SumP/1');
    add_line(sub_path, 'P_e/1', 'SumP/2');
    add_line(sub_path, 'MulD/1', 'SumP/3');

    add_line(sub_path, 'SumP/1', 'DivM/1');
    add_line(sub_path, 'M_val/1', 'DivM/2');
    add_line(sub_path, 'DivM/1', 'IntW/1');

    add_line(sub_path, 'wn_val/1', 'MulWn/1');
    add_line(sub_path, 'SumWerr/1', 'MulWn/2');
    add_line(sub_path, 'MulWn/1', 'IntD/1');
    add_line(sub_path, 'IntD/1', 'delta/1');

    % --- Voltage generation: Va = Vpk*sin(wn*t + delta), Vb, Vc ---
    % Clock → *wn → + delta → sin(theta), sin(theta - 2pi/3), sin(theta + 2pi/3)
    % → *Vpk → Mux → S2PS → CVS

    clk_name = sprintf('Clk_%s', gname);
    add_block('built-in/Clock', [mdl '/' clk_name], ...
        'Position', [bx-100 by+150 bx-70 by+170]);

    % wn*t
    wnt_name = sprintf('wnt_%s', gname);
    add_block('built-in/Gain', [mdl '/' wnt_name], ...
        'Position', [bx-50 by+150 bx-20 by+170], 'Gain', num2str(wn));
    add_line(mdl, [clk_name '/1'], [wnt_name '/1'], 'autorouting', 'smart');

    % theta = wn*t + delta
    theta_name = sprintf('Theta_%s', gname);
    add_block('built-in/Sum', [mdl '/' theta_name], ...
        'Position', [bx by+150 bx+30 by+180], 'Inputs', '++');
    add_line(mdl, [wnt_name '/1'], [theta_name '/1'], 'autorouting', 'smart');
    % delta comes from ConvGen subsystem output 2
    add_line(mdl, sprintf('ConvGen_%s/2', gname), [theta_name '/2'], 'autorouting', 'smart');

    % MATLAB Function block for 3-phase voltage generation
    fcn_name = sprintf('Vabc_%s', gname);
    fcn_path = [mdl '/' fcn_name];
    add_block('built-in/SubSystem', fcn_path, ...
        'Position', [bx+50 by+140 bx+180 by+200]);
    % Remove default content and build a Fcn-based 3-phase generator
    try, delete_line(fcn_path, 'In1/1', 'Out1/1'); catch, end
    try, delete_block([fcn_path '/In1']); catch, end
    try, delete_block([fcn_path '/Out1']); catch, end

    % Theta input
    add_block('built-in/Inport', [fcn_path '/theta'], ...
        'Position', [30 50 60 64], 'Port', '1');
    % Va, Vb, Vc via Trigonometric Function blocks
    add_block('built-in/Trigonometry', [fcn_path '/sinA'], ...
        'Position', [120 40 160 60], 'Operator', 'sin');
    % theta - 2pi/3 for phase B
    add_block('built-in/Constant', [fcn_path '/shift_B'], ...
        'Position', [80 90 120 110], 'Value', num2str(-2*pi/3));
    add_block('built-in/Sum', [fcn_path '/sumB'], ...
        'Position', [140 80 170 110], 'Inputs', '++');
    add_block('built-in/Trigonometry', [fcn_path '/sinB'], ...
        'Position', [200 80 240 100], 'Operator', 'sin');
    % theta + 2pi/3 for phase C
    add_block('built-in/Constant', [fcn_path '/shift_C'], ...
        'Position', [80 140 120 160], 'Value', num2str(2*pi/3));
    add_block('built-in/Sum', [fcn_path '/sumC'], ...
        'Position', [140 130 170 160], 'Inputs', '++');
    add_block('built-in/Trigonometry', [fcn_path '/sinC'], ...
        'Position', [200 130 240 150], 'Operator', 'sin');
    % Vpk gain for each phase
    add_block('built-in/Gain', [fcn_path '/GainA'], ...
        'Position', [200 40 240 60], 'Gain', num2str(Vpk_gen));
    add_block('built-in/Gain', [fcn_path '/GainB'], ...
        'Position', [270 80 310 100], 'Gain', num2str(Vpk_gen));
    add_block('built-in/Gain', [fcn_path '/GainC'], ...
        'Position', [270 130 310 150], 'Gain', num2str(Vpk_gen));
    % Mux
    add_block('built-in/Mux', [fcn_path '/MuxABC'], ...
        'Position', [340 40 345 155], 'Inputs', '3');
    % Output
    add_block('built-in/Outport', [fcn_path '/Vabc'], ...
        'Position', [380 90 410 104], 'Port', '1');

    % Wire inside Vabc subsystem
    add_line(fcn_path, 'theta/1', 'sinA/1');
    add_line(fcn_path, 'sinA/1', 'GainA/1');
    add_line(fcn_path, 'theta/1', 'sumB/1');
    add_line(fcn_path, 'shift_B/1', 'sumB/2');
    add_line(fcn_path, 'sumB/1', 'sinB/1');
    add_line(fcn_path, 'sinB/1', 'GainB/1');
    add_line(fcn_path, 'theta/1', 'sumC/1');
    add_line(fcn_path, 'shift_C/1', 'sumC/2');
    add_line(fcn_path, 'sumC/1', 'sinC/1');
    add_line(fcn_path, 'sinC/1', 'GainC/1');
    add_line(fcn_path, 'GainA/1', 'MuxABC/1');
    add_line(fcn_path, 'GainB/1', 'MuxABC/2');
    add_line(fcn_path, 'GainC/1', 'MuxABC/3');
    add_line(fcn_path, 'MuxABC/1', 'Vabc/1');

    % Wire theta to Vabc subsystem
    add_line(mdl, [theta_name '/1'], [fcn_name '/1'], 'autorouting', 'smart');

    % --- S2PS Converter ---
    s2ps_name = sprintf('S2PS_%s', gname);
    add_block(s2ps_lib, [mdl '/' s2ps_name], ...
        'Position', [bx+200 by+150 bx+240 by+190]);
    add_line(mdl, [fcn_name '/1'], [s2ps_name '/1'], 'autorouting', 'smart');

    % --- Controlled Voltage Source (Three-Phase) ---
    cvs_name = sprintf('CVS_%s', gname);
    add_block(cvs_lib, [mdl '/' cvs_name], ...
        'Position', [bx+260 by+150 bx+340 by+230]);
    % CVS LConn1 = signal input ← S2PS
    add_line(mdl, [s2ps_name '/RConn1'], [cvs_name '/LConn1'], 'autorouting', 'smart');
    % CVS LConn2 = neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [bx+260 by+250 bx+290 by+280]);
    add_line(mdl, [cvs_name '/LConn2'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    % --- RLC (Three-Phase) for generator impedance ---
    rlc_name = sprintf('Zgen_%s', gname);
    add_block(rlc3_lib, [mdl '/' rlc_name], ...
        'Position', [bx+360 by+150 bx+430 by+230]);
    % component_structure = 4 (RL), parameterization = 1 (impedance)
    set_param([mdl '/' rlc_name], 'component_structure', '4');  % RL
    set_param([mdl '/' rlc_name], 'R', num2str(R_gen));
    set_param([mdl '/' rlc_name], 'L', num2str(L_gen));  % H (ee_lib expects H, not mH)
    % CVS RConn1 (3ph output) → RLC LConn1
    add_line(mdl, [cvs_name '/RConn1'], [rlc_name '/LConn1'], 'autorouting', 'smart');

    % --- Power Sensor (Three-Phase) ---
    psens_name = sprintf('PSens_%s', gname);
    add_block(ps_lib, [mdl '/' psens_name], ...
        'Position', [bx+450 by+150 bx+530 by+230]);
    % RLC RConn1 → PSensor LConn1
    add_line(mdl, [rlc_name '/RConn1'], [psens_name '/LConn1'], 'autorouting', 'smart');

    % Register PSensor RConn1 (3ph output) as bus node
    bus_nodes = do_wire_ee(mdl, bus_nodes, bus_id, psens_name, '%s/RConn1');

    % --- P_e feedback: PSensor → PS2S → Gain(1/Sbase) → ConvGen P_e input ---
    ps2s_name = sprintf('PS2S_%s', gname);
    add_block(ps2s_lib, [mdl '/' ps2s_name], ...
        'Position', [bx+550 by+170 bx+590 by+190]);
    % Power sensor P output port — connect the active power output
    add_line(mdl, [psens_name '/LConn2'], [ps2s_name '/LConn1'], 'autorouting', 'smart');

    pe_gain_name = sprintf('PeGain_%s', gname);
    add_block('built-in/Gain', [mdl '/' pe_gain_name], ...
        'Position', [bx+610 by+170 bx+660 by+190], ...
        'Gain', num2str(1/Sbase));
    add_line(mdl, [ps2s_name '/1'], [pe_gain_name '/1'], 'autorouting', 'smart');
    add_line(mdl, [pe_gain_name '/1'], sprintf('ConvGen_%s/1', gname), 'autorouting', 'smart');

    fprintf('  %s at Bus%d: H=%.3f, M=%.1f, P0=%.0fMW, D=%.1f, R=%.2f (P_e=sensor)\n', ...
        gname, bus_id, g.H, M, g.P0_MW, g.D, g.R);
end

%% ======================================================================
%  Step 4: Wind Farms W1, W2 (Programmable Voltage Source, constant)
%% ======================================================================
fprintf('\n=== Building wind farms W1, W2 ===\n');

for wi = 1:length(wind_cfg)
    w = wind_cfg(wi);
    wname = w.name;
    bus_id = w.bus;

    bx = 100 + (wi-1)*500;
    by = 500;

    V_src = Vbase * vlf_wind(wi, 1);
    A_src = vlf_wind(wi, 2);
    Vpk_w = V_src * sqrt(2/3);

    % --- Programmable Voltage Source (Three-Phase) ---
    pvs_name = ['PVS_' wname];
    add_block(pvs_lib, [mdl '/' pvs_name], ...
        'Position', [bx by bx+80 by+80]);
    % Set voltage (RMS line-line), frequency, phase
    % vline_rms = V_src (line-line RMS = phase_peak * sqrt(3)/sqrt(2) = Vbase*vlf * 1)
    set_param([mdl '/' pvs_name], ...
        'vline_rms', num2str(V_src), ...
        'freq', num2str(fn), ...
        'shift', num2str(A_src));

    % PVS LConn1 = neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [bx-20 by+100 bx+10 by+130]);
    add_line(mdl, [pvs_name '/LConn1'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    % --- RLC impedance for wind farm ---
    rlc_name = ['Zw_' wname];
    add_block(rlc3_lib, [mdl '/' rlc_name], ...
        'Position', [bx+100 by bx+170 by+80]);
    set_param([mdl '/' rlc_name], 'component_structure', '4');  % RL
    set_param([mdl '/' rlc_name], 'R', num2str(R_gen));
    set_param([mdl '/' rlc_name], 'L', num2str(L_gen));  % H (ee_lib expects H, not mH)

    % PVS RConn1 (3ph) → RLC LConn1
    add_line(mdl, [pvs_name '/RConn1'], [rlc_name '/LConn1'], 'autorouting', 'smart');

    % Register RLC RConn1 as bus node
    bus_nodes = do_wire_ee(mdl, bus_nodes, bus_id, rlc_name, '%s/RConn1');

    fprintf('  %s at Bus%d: P0=%.0fMW, Sn=%.0fMVA\n', ...
        wname, bus_id, w.P0_MW, w.Sn/1e6);
end

%% ======================================================================
%  Step 5: VSG/ESS subsystems (signal-domain swing equation with RL inputs)
%% ======================================================================
% EXACT SAME internal structure as original: 5 inputs, 3 outputs,
% M0+delta_M, D0+delta_D, swing equation, integrators.
% Block names VSG_ES{i}/M0, VSG_ES{i}/D0 are required by Python env.
%
% P_e comes from Power Sensor (wired inline via PSensor → PS2S → Gain).
% Voltage driven by delta output → 3-phase instantaneous voltages → CVS.

fprintf('\n=== Building VSG/ESS subsystems ES1-ES4 ===\n');

vsg_pos_x = [1800, 2300, 1800, 2300];
vsg_pos_y = [100,  100,  500,  500];

for i = 1:n_vsg
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = [mdl '/' vsg_name];
    bx = vsg_pos_x(i);
    by = vsg_pos_y(i);
    bus_id = ess_bus(i);
    V_ess = Vbase * vlf_ess(i, 1);
    Vpk_ess = V_ess * sqrt(2/3);

    % --- Create subsystem ---
    add_block('built-in/SubSystem', vsg_path, ...
        'Position', [bx by bx+120 by+100]);

    % 5 inputs: omega_ref, delta_M, delta_D, P_ref, P_e
    input_names = {'omega_ref', 'delta_M', 'delta_D', 'P_ref', 'P_e'};
    for k = 1:5
        inp = sprintf('%s/In%d', vsg_path, k);
        add_block('built-in/Inport', inp, ...
            'Position', [30, 20+(k-1)*50, 60, 34+(k-1)*50], ...
            'Port', num2str(k));
        set_param(inp, 'Name', input_names{k});
    end

    % 3 outputs: omega, delta, P_out
    output_names = {'omega', 'delta', 'P_out'};
    for k = 1:3
        outp = sprintf('%s/Out%d', vsg_path, k);
        add_block('built-in/Outport', outp, ...
            'Position', [700, 30+(k-1)*80, 730, 44+(k-1)*80], ...
            'Port', num2str(k));
        set_param(outp, 'Name', output_names{k});
    end

    % === Internal swing equation blocks (PRESERVED from original) ===
    % Constants — block names M0, D0 are referenced by Python env
    add_block('built-in/Constant', [vsg_path '/M0'], ...
        'Position', [100 10 150 30], 'Value', num2str(VSG_M0));
    add_block('built-in/Constant', [vsg_path '/D0'], ...
        'Position', [100 60 150 80], 'Value', num2str(VSG_D0));
    add_block('built-in/Constant', [vsg_path '/wn'], ...
        'Position', [300 260 350 280], 'Value', num2str(wn));

    % M_total = M0 + delta_M
    add_block('built-in/Sum', [vsg_path '/SumM'], ...
        'Position', [180 15 210 45], 'Inputs', '++');
    add_line(vsg_path, 'M0/1', 'SumM/1');
    add_line(vsg_path, 'delta_M/1', 'SumM/2');

    % D_total = D0 + delta_D
    add_block('built-in/Sum', [vsg_path '/SumD'], ...
        'Position', [180 65 210 95], 'Inputs', '++');
    add_line(vsg_path, 'D0/1', 'SumD/1');
    add_line(vsg_path, 'delta_D/1', 'SumD/2');

    % omega_error = omega - omega_ref
    add_block('built-in/Sum', [vsg_path '/SumW'], ...
        'Position', [350 120 380 150], 'Inputs', '+-');

    % D_term = D_total * omega_error
    add_block('built-in/Product', [vsg_path '/MulD'], ...
        'Position', [420 80 450 110], 'Inputs', '**');

    % P_accel = P_ref - P_e - D_term
    add_block('built-in/Sum', [vsg_path '/SumP'], ...
        'Position', [490 80 520 140], 'Inputs', '+--');

    % d_omega = P_accel / M_total
    add_block('built-in/Product', [vsg_path '/DivM'], ...
        'Position', [550 80 580 120], 'Inputs', '*/');

    % Integrator for omega (IC = 1.0 pu, clamped to [0.9, 1.1])
    add_block('built-in/Integrator', [vsg_path '/IntW'], ...
        'Position', [620 80 660 120], ...
        'InitialCondition', '1.0', ...
        'LimitOutput', 'on', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');

    % Integrator for delta
    delta0_rad = vlf_ess(i, 2) * pi / 180;
    add_block('built-in/Integrator', [vsg_path '/IntD'], ...
        'Position', [500 240 540 280], ...
        'InitialCondition', num2str(delta0_rad));

    % === Wiring (PRESERVED from original) ===
    add_line(vsg_path, 'IntW/1', 'omega/1');
    add_line(vsg_path, 'IntW/1', 'SumW/1');
    add_line(vsg_path, 'omega_ref/1', 'SumW/2');

    add_line(vsg_path, 'SumD/1', 'MulD/1');
    add_line(vsg_path, 'SumW/1', 'MulD/2');

    add_line(vsg_path, 'P_ref/1', 'SumP/1');
    add_line(vsg_path, 'P_e/1', 'SumP/2');
    add_line(vsg_path, 'MulD/1', 'SumP/3');

    add_line(vsg_path, 'SumP/1', 'DivM/1');
    add_line(vsg_path, 'SumM/1', 'DivM/2');
    add_line(vsg_path, 'DivM/1', 'IntW/1');

    % delta: d(delta)/dt = wn * (omega - omega_ref)
    add_block('built-in/Product', [vsg_path '/MulWn'], ...
        'Position', [420 240 450 280], 'Inputs', '**');
    add_line(vsg_path, 'wn/1', 'MulWn/1');
    add_line(vsg_path, 'SumW/1', 'MulWn/2');
    add_line(vsg_path, 'MulWn/1', 'IntD/1');
    add_line(vsg_path, 'IntD/1', 'delta/1');

    % P_out = P_ref - D_term
    add_block('built-in/Sum', [vsg_path '/SumPout'], ...
        'Position', [490 310 520 340], 'Inputs', '+-');
    add_line(vsg_path, 'P_ref/1', 'SumPout/1');
    add_line(vsg_path, 'MulD/1', 'SumPout/2');
    add_line(vsg_path, 'SumPout/1', 'P_out/1');

    % --- External constant blocks for VSG inputs (ports 1-3) ---
    const_defs = {
        sprintf('wref_%d', i),  '1.0';
        sprintf('dM_%d', i),    '0';
        sprintf('dD_%d', i),    '0';
    };
    for cb = 1:size(const_defs, 1)
        cname = const_defs{cb, 1};
        cval = const_defs{cb, 2};
        cpath = [mdl '/' cname];
        cx = bx - 120;
        cy = by - 10 + (cb-1) * 25;
        add_block('built-in/Constant', cpath, ...
            'Position', [cx cy cx+40 cy+15], 'Value', cval);
        add_line(mdl, [cname '/1'], ...
            sprintf('%s/%d', vsg_name, cb), 'autorouting', 'smart');
    end

    % --- P_ref ramp for port 4: 0 → VSG_P0(i) over T_ramp seconds ---
    pref_ramp_name = sprintf('PrefRamp_%d', i);
    pref_sat_name = sprintf('PrefSat_%d', i);
    cx = bx - 120;
    cy = by - 10 + 3 * 25;  % same row as old Pref constant (4th row)
    add_block('built-in/Ramp', [mdl '/' pref_ramp_name], ...
        'Position', [cx-80 cy cx-40 cy+15], ...
        'Slope', num2str(VSG_P0(i) / T_ramp), 'Start', '0', 'X0', '0');
    add_block('built-in/Saturate', [mdl '/' pref_sat_name], ...
        'Position', [cx cy cx+40 cy+15], ...
        'UpperLimit', num2str(VSG_P0(i)), 'LowerLimit', '0');
    add_line(mdl, [pref_ramp_name '/1'], [pref_sat_name '/1'], 'autorouting', 'smart');
    add_line(mdl, [pref_sat_name '/1'], sprintf('%s/4', vsg_name), 'autorouting', 'smart');

    % --- Voltage generation from delta output ---
    % theta = wn*t + delta → 3-phase voltages → S2PS → CVS

    clk_name = sprintf('Clk_ES%d', i);
    add_block('built-in/Clock', [mdl '/' clk_name], ...
        'Position', [bx-100 by+250 bx-70 by+270]);

    wnt_name = sprintf('wnt_ES%d', i);
    add_block('built-in/Gain', [mdl '/' wnt_name], ...
        'Position', [bx-50 by+250 bx-20 by+270], 'Gain', num2str(wn));
    add_line(mdl, [clk_name '/1'], [wnt_name '/1'], 'autorouting', 'smart');

    theta_name = sprintf('Theta_ES%d', i);
    add_block('built-in/Sum', [mdl '/' theta_name], ...
        'Position', [bx by+250 bx+30 by+280], 'Inputs', '++');
    add_line(mdl, [wnt_name '/1'], [theta_name '/1'], 'autorouting', 'smart');
    add_line(mdl, sprintf('%s/2', vsg_name), [theta_name '/2'], 'autorouting', 'smart');

    % Vabc subsystem for ESS
    fcn_name = sprintf('Vabc_ES%d', i);
    fcn_path = [mdl '/' fcn_name];
    add_block('built-in/SubSystem', fcn_path, ...
        'Position', [bx+50 by+240 bx+180 by+300]);
    try, delete_line(fcn_path, 'In1/1', 'Out1/1'); catch, end
    try, delete_block([fcn_path '/In1']); catch, end
    try, delete_block([fcn_path '/Out1']); catch, end

    add_block('built-in/Inport', [fcn_path '/theta'], ...
        'Position', [30 50 60 64], 'Port', '1');
    add_block('built-in/Trigonometry', [fcn_path '/sinA'], ...
        'Position', [120 40 160 60], 'Operator', 'sin');
    add_block('built-in/Constant', [fcn_path '/shift_B'], ...
        'Position', [80 90 120 110], 'Value', num2str(-2*pi/3));
    add_block('built-in/Sum', [fcn_path '/sumB'], ...
        'Position', [140 80 170 110], 'Inputs', '++');
    add_block('built-in/Trigonometry', [fcn_path '/sinB'], ...
        'Position', [200 80 240 100], 'Operator', 'sin');
    add_block('built-in/Constant', [fcn_path '/shift_C'], ...
        'Position', [80 140 120 160], 'Value', num2str(2*pi/3));
    add_block('built-in/Sum', [fcn_path '/sumC'], ...
        'Position', [140 130 170 160], 'Inputs', '++');
    add_block('built-in/Trigonometry', [fcn_path '/sinC'], ...
        'Position', [200 130 240 150], 'Operator', 'sin');
    add_block('built-in/Gain', [fcn_path '/GainA'], ...
        'Position', [200 40 240 60], 'Gain', num2str(Vpk_ess));
    add_block('built-in/Gain', [fcn_path '/GainB'], ...
        'Position', [270 80 310 100], 'Gain', num2str(Vpk_ess));
    add_block('built-in/Gain', [fcn_path '/GainC'], ...
        'Position', [270 130 310 150], 'Gain', num2str(Vpk_ess));
    add_block('built-in/Mux', [fcn_path '/MuxABC'], ...
        'Position', [340 40 345 155], 'Inputs', '3');
    add_block('built-in/Outport', [fcn_path '/Vabc'], ...
        'Position', [380 90 410 104], 'Port', '1');

    add_line(fcn_path, 'theta/1', 'sinA/1');
    add_line(fcn_path, 'sinA/1', 'GainA/1');
    add_line(fcn_path, 'theta/1', 'sumB/1');
    add_line(fcn_path, 'shift_B/1', 'sumB/2');
    add_line(fcn_path, 'sumB/1', 'sinB/1');
    add_line(fcn_path, 'sinB/1', 'GainB/1');
    add_line(fcn_path, 'theta/1', 'sumC/1');
    add_line(fcn_path, 'shift_C/1', 'sumC/2');
    add_line(fcn_path, 'sumC/1', 'sinC/1');
    add_line(fcn_path, 'sinC/1', 'GainC/1');
    add_line(fcn_path, 'GainA/1', 'MuxABC/1');
    add_line(fcn_path, 'GainB/1', 'MuxABC/2');
    add_line(fcn_path, 'GainC/1', 'MuxABC/3');
    add_line(fcn_path, 'MuxABC/1', 'Vabc/1');

    add_line(mdl, [theta_name '/1'], [fcn_name '/1'], 'autorouting', 'smart');

    % --- S2PS → CVS ---
    s2ps_name = sprintf('S2PS_ES%d', i);
    add_block(s2ps_lib, [mdl '/' s2ps_name], ...
        'Position', [bx+200 by+250 bx+240 by+290]);
    add_line(mdl, [fcn_name '/1'], [s2ps_name '/1'], 'autorouting', 'smart');

    cvs_name = sprintf('CVS_ES%d', i);
    add_block(cvs_lib, [mdl '/' cvs_name], ...
        'Position', [bx+260 by+250 bx+340 by+330]);
    add_line(mdl, [s2ps_name '/RConn1'], [cvs_name '/LConn1'], 'autorouting', 'smart');

    % CVS neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [bx+260 by+350 bx+290 by+380]);
    add_line(mdl, [cvs_name '/LConn2'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    % --- RLC impedance ---
    rlc_name = sprintf('Zess_%d', i);
    add_block(rlc3_lib, [mdl '/' rlc_name], ...
        'Position', [bx+360 by+250 bx+430 by+330]);
    set_param([mdl '/' rlc_name], 'component_structure', '4');
    set_param([mdl '/' rlc_name], 'R', num2str(R_gen));
    set_param([mdl '/' rlc_name], 'L', num2str(L_gen));  % H (ee_lib expects H, not mH)
    add_line(mdl, [cvs_name '/RConn1'], [rlc_name '/LConn1'], 'autorouting', 'smart');

    % --- Power Sensor ---
    psens_name = sprintf('PSens_ES%d', i);
    add_block(ps_lib, [mdl '/' psens_name], ...
        'Position', [bx+450 by+250 bx+530 by+330]);
    add_line(mdl, [rlc_name '/RConn1'], [psens_name '/LConn1'], 'autorouting', 'smart');

    % Register on ESS bus
    bus_nodes = do_wire_ee(mdl, bus_nodes, bus_id, psens_name, '%s/RConn1');

    % --- P_e feedback: PSensor → PS2S → Gain(1/VSG_SN) → VSG P_e input (port 5) ---
    ps2s_name = sprintf('PS2S_ES%d', i);
    add_block(ps2s_lib, [mdl '/' ps2s_name], ...
        'Position', [bx+550 by+270 bx+590 by+290]);
    add_line(mdl, [psens_name '/LConn2'], [ps2s_name '/LConn1'], 'autorouting', 'smart');

    pe_gain_name = sprintf('PeGain_ES%d', i);
    add_block('built-in/Gain', [mdl '/' pe_gain_name], ...
        'Position', [bx+610 by+270 bx+660 by+290], ...
        'Gain', num2str(1/VSG_SN));
    add_line(mdl, [ps2s_name '/1'], [pe_gain_name '/1'], 'autorouting', 'smart');
    add_line(mdl, [pe_gain_name '/1'], sprintf('%s/5', vsg_name), 'autorouting', 'smart');

    % --- ToWorkspace loggers for VSG outputs ---
    out_log_names = {'omega', 'delta', 'P_out'};
    for out_idx = 1:3
        log_name = sprintf('Log_%s_ES%d', out_log_names{out_idx}, i);
        log_path = [mdl '/' log_name];
        lx = bx + 200;
        ly = by - 10 + (out_idx-1) * 30;
        add_block('built-in/ToWorkspace', log_path, ...
            'Position', [lx ly lx+60 ly+20], ...
            'VariableName', sprintf('%s_ES%d', out_log_names{out_idx}, i), ...
            'SaveFormat', 'Timeseries');
        add_line(mdl, sprintf('%s/%d', vsg_name, out_idx), ...
            [log_name '/1'], 'autorouting', 'smart');
    end

    fprintf('  VSG_ES%d at Bus%d (->Bus%d): M0=%.1f, D0=%.1f, P0=%.4f pu\n', ...
        i, bus_id, ess_main(i), VSG_M0, VSG_D0, VSG_P0(i));
end

%% ======================================================================
%  Step 6: Transmission lines (Transmission Line Three-Phase)
%% ======================================================================
fprintf('\n=== Adding transmission lines ===\n');

n_lines = size(line_defs, 1);
line_y_base = 800;

for li = 1:n_lines
    lname    = line_defs{li, 1};
    from_bus = line_defs{li, 2};
    to_bus   = line_defs{li, 3};
    len_km   = line_defs{li, 4};
    R_km     = line_defs{li, 5};
    L_km     = line_defs{li, 6};
    C_km     = line_defs{li, 7};

    lx = 100 + mod(li-1, 5) * 300;
    ly = line_y_base + floor((li-1)/5) * 120;

    line_path = [mdl '/' lname];

    add_block(tl_lib, line_path, 'Position', [lx ly lx+80 ly+50]);
    % Set parameters: R (Ohm/km), L (mH/km), Cl (nF/km), length (km), freq (Hz)
    set_param(line_path, ...
        'R', num2str(R_km), ...
        'L', num2str(L_km * 1000), ...     % H/km → mH/km
        'Cl', num2str(C_km * 1e9), ...     % F/km → nF/km
        'length', num2str(len_km), ...
        'freq', num2str(fn));

    % Wire LConn1 (sending 3ph) to from_bus
    bus_nodes = do_wire_ee(mdl, bus_nodes, from_bus, lname, '%s/LConn1');
    % Wire RConn1 (receiving 3ph) to to_bus
    bus_nodes = do_wire_ee(mdl, bus_nodes, to_bus, lname, '%s/RConn1');

    % Ground connections for TL: LConn2 and RConn2
    gnd_count = gnd_count + 1;
    gnd_s = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_s], ...
        'Position', [lx-20 ly+60 lx+10 ly+90]);
    add_line(mdl, [lname '/LConn2'], [gnd_s '/LConn1'], 'autorouting', 'smart');

    gnd_count = gnd_count + 1;
    gnd_r = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_r], ...
        'Position', [lx+90 ly+60 lx+120 ly+90]);
    add_line(mdl, [lname '/RConn2'], [gnd_r '/LConn1'], 'autorouting', 'smart');

    fprintf('  %s: Bus%d -> Bus%d, %.0fkm\n', lname, from_bus, to_bus, len_km);
end

%% ======================================================================
%  Step 7: Loads (Wye-Connected Load)
%% ======================================================================
fprintf('\n=== Adding loads ===\n');

for li = 1:length(load_defs)
    ld = load_defs(li);
    load_path = [mdl '/' ld.name];
    lx = 100 + (li-1)*300;
    ly = 1400;

    add_block(wl_lib, load_path, 'Position', [lx ly lx+60 ly+50]);
    % parameterization=2 (rated power), component_structure=4 (RL)
    set_param(load_path, ...
        'parameterization', '2', ...
        'component_structure', '4', ...
        'VRated', num2str(Vbase), ...
        'FRated', num2str(fn), ...
        'P', num2str(ld.P_MW * 1e6), ...
        'Qpos', num2str(ld.Q_Mvar * 1e6));

    % LConn1 = 3-phase input → bus
    bus_nodes = do_wire_ee(mdl, bus_nodes, ld.bus, ld.name, '%s/LConn1');
    % RConn1 = neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [lx+80 ly lx+110 ly+30]);
    add_line(mdl, [ld.name '/RConn1'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    fprintf('  %s at Bus%d: P=%.0fMW, Q=%.0fMvar\n', ...
        ld.name, ld.bus, ld.P_MW, ld.Q_Mvar);
end

%% ======================================================================
%  Step 8: Shunt capacitors (Wye-Connected Load, capacitive only)
%% ======================================================================
fprintf('\n=== Adding shunt capacitors ===\n');

for si = 1:length(shunt_defs)
    sh = shunt_defs(si);
    shunt_path = [mdl '/' sh.name];
    sx = 100 + (si-1)*300;
    sy = 1550;

    % Wye-Connected Load with C only (component_structure=3)
    add_block(wl_lib, shunt_path, 'Position', [sx sy sx+60 sy+50]);
    set_param(shunt_path, ...
        'parameterization', '2', ...
        'component_structure', '3', ...
        'VRated', num2str(Vbase), ...
        'FRated', num2str(fn), ...
        'Qneg', num2str(sh.Q_Mvar * 1e6));

    bus_nodes = do_wire_ee(mdl, bus_nodes, sh.bus, sh.name, '%s/LConn1');
    % neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [sx+80 sy sx+110 sy+30]);
    add_line(mdl, [sh.name '/RConn1'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    fprintf('  %s at Bus%d: %.0f Mvar capacitive\n', ...
        sh.name, sh.bus, sh.Q_Mvar);
end

%% ======================================================================
%  Step 9: Disturbance breakers + trip loads
%% ======================================================================
fprintf('\n=== Adding disturbance breakers ===\n');

for bi = 1:length(brk_defs)
    b = brk_defs(bi);
    brk_path = [mdl '/' b.name];
    bx_b = 800 + (bi-1)*400;
    by_b = 1400;

    % --- Circuit Breaker (Three-Phase) ---
    add_block(cb_lib, brk_path, 'Position', [bx_b by_b bx_b+80 by_b+50]);

    % --- Step block for breaker control signal ---
    % CB RConn1 = signal control input (>0.5 = closed, <0.5 = open)
    step_name = sprintf('BrkCtrl_%d', bi);
    step_path = [mdl '/' step_name];
    add_block('built-in/Step', step_path, ...
        'Position', [bx_b-80 by_b+60 bx_b-40 by_b+80]);

    if strcmp(b.init_state, 'closed')
        % Initially closed (1), opens at switch_time (→0)
        set_param(step_path, 'Time', num2str(b.switch_time), ...
            'Before', '1', 'After', '0');
    else
        % Initially open (0), closes at switch_time (→1)
        set_param(step_path, 'Time', num2str(b.switch_time), ...
            'Before', '0', 'After', '1');
    end

    % Step → S2PS → CB LConn1 (signal control)
    s2ps_brk = sprintf('S2PS_Brk%d', bi);
    add_block(s2ps_lib, [mdl '/' s2ps_brk], ...
        'Position', [bx_b-30 by_b+60 bx_b+10 by_b+80]);
    add_line(mdl, [step_name '/1'], [s2ps_brk '/1'], 'autorouting', 'smart');
    add_line(mdl, [s2ps_brk '/RConn1'], [b.name '/LConn1'], 'autorouting', 'smart');

    % --- Trip load (Wye-Connected Load, purely resistive) ---
    trip_name = sprintf('TripLoad_%d', bi);
    trip_path = [mdl '/' trip_name];
    add_block(wl_lib, trip_path, 'Position', [bx_b+120 by_b bx_b+180 by_b+50]);
    set_param(trip_path, ...
        'parameterization', '2', ...
        'component_structure', '1', ...
        'VRated', num2str(Vbase), ...
        'FRated', num2str(fn), ...
        'P', num2str(b.trip_P_MW * 1e6));

    % CB LConn2 (3ph side A) → bus
    bus_nodes = do_wire_ee(mdl, bus_nodes, b.bus, b.name, '%s/LConn2');
    % CB RConn1 (3ph side B) → TripLoad LConn1
    add_line(mdl, [b.name '/RConn1'], [trip_name '/LConn1'], 'autorouting', 'smart');
    % TripLoad neutral → GND
    gnd_count = gnd_count + 1;
    gnd_name = sprintf('GND_%d', gnd_count);
    add_block(gnd_lib, [mdl '/' gnd_name], ...
        'Position', [bx_b+200 by_b bx_b+230 by_b+30]);
    add_line(mdl, [trip_name '/RConn1'], [gnd_name '/LConn1'], 'autorouting', 'smart');

    fprintf('  %s at Bus%d: TripLoad=%.0fMW, init=%s, switch@%.0fs\n', ...
        b.name, b.bus, b.trip_P_MW, b.init_state, b.switch_time);
end

%% ======================================================================
%  Step 9b: Connect Solver Configuration to electrical network
%% ======================================================================
% Solver Config must share a physical node with the network.
% Wire SolverConfig/RConn1 to Bus1's representative node.
bus1_rep = bus_nodes{1};
add_line(mdl, ...
    'SolverConfig/RConn1', ...
    sprintf(bus1_rep{2}, bus1_rep{1}), ...
    'autorouting', 'smart');
fprintf('\n  Solver Configuration connected to Bus1 network.\n');

%% ======================================================================
%  Step 10: Clock + time logger
%% ======================================================================
add_block('built-in/Clock', [mdl '/Clock'], ...
    'Position', [20 80 50 100]);
add_block('built-in/ToWorkspace', [mdl '/Log_time'], ...
    'Position', [80 80 140 100], ...
    'VariableName', 'sim_time', ...
    'SaveFormat', 'Timeseries');
add_line(mdl, 'Clock/1', 'Log_time/1');

%% ======================================================================
%  Step 11: Solver configuration and save
%% ======================================================================
set_param(mdl, ...
    'StopTime', '10.0', ...
    'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', ...
    'MaxStep', '0.001', ...
    'RelTol', '1e-4');

model_path = fullfile(model_dir, [mdl '.slx']);
save_system(mdl, model_path);
fprintf('\n=== Model saved to %s ===\n', model_path);

%% ======================================================================
%  Step 12: Test simulation (1 second)
%% ======================================================================
fprintf('\n=== Running 1-second test simulation ===\n');
try
    simOut = sim(mdl, 'StopTime', '1.0');
    fprintf('SUCCESS! 1-second simulation completed.\n');

    % Check logged VSG outputs
    vars = {'omega_ES1', 'delta_ES1', 'P_out_ES1', 'sim_time'};
    for v = 1:length(vars)
        try
            ts = simOut.get(vars{v});
            if ~isempty(ts)
                fprintf('  %s: %d samples, final=%.6f\n', ...
                    vars{v}, length(ts.Data), ts.Data(end));
            end
        catch
            try
                data = evalin('base', vars{v});
                fprintf('  %s: available in base workspace\n', vars{v});
            catch
                fprintf('  %s: not found in simOut\n', vars{v});
            end
        end
    end
catch me
    fprintf('SIMULATION FAILED: %s\n', me.message);
    if ~isempty(me.cause)
        for ci = 1:length(me.cause)
            fprintf('  Cause %d: %s\n', ci, me.cause{ci}.message);
        end
    end
end

%% ======================================================================
%  Summary
%% ======================================================================
fprintf('\n=== build_powerlib_kundur done (ee_lib, Power Sensor P_e) ===\n');
fprintf('Model: %s\n', model_path);
fprintf('Topology: 16-bus Modified Kundur Two-Area System\n');
fprintf('Conv Gens: G1(Bus1), G2(Bus2), G3(Bus3) — swing eq + CVS, P_e=sensor\n');
fprintf('Wind Farms: W1(Bus4)=700MW, W2(Bus11->8)=100MW — PVS constant\n');
fprintf('VSGs: ES1(Bus12->7), ES2(Bus16->8), ES3(Bus14->10), ES4(Bus15->9)\n');
fprintf('  VSG feedback: Power Sensor -> P_e -> swing eq -> delta -> CVS\n');
fprintf('Loads: Bus7=967MW, Bus9=1767MW (Wye-Connected Load)\n');
fprintf('Shunts: Bus7=200Mvar, Bus9=350Mvar\n');
fprintf('Breakers: Bus14(248MW,closed), Bus15(188MW,open) — Step+S2PS->CB\n');
fprintf('Solver: ode23t variable-step, Simscape Electrical\n');
fprintf('Total lines: %d\n', n_lines);

%% ======================================================================
%  Local function: wire a block's composite 3-phase port to a bus node
%% ======================================================================
function bus_nodes = do_wire_ee(mdl, bus_nodes, bus_id, blk_name, port_fmt)
%DO_WIRE_EE Connect a block to a bus node via composite 3-phase port (ee_lib).
%   Unlike powerlib which uses separate LConn1/2/3 for 3 phases,
%   ee_lib uses a single composite port (LConn1 or RConn1) for all 3 phases.
    if isempty(bus_nodes{bus_id})
        bus_nodes{bus_id} = {blk_name, port_fmt};
    else
        existing = bus_nodes{bus_id};
        add_line(mdl, ...
            sprintf(existing{2}, existing{1}), ...
            sprintf(port_fmt, blk_name), ...
            'autorouting', 'smart');
    end
end
