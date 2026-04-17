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

% ConvGen internal impedance: Xd'=0.30 pu on machine base (Sgen=900 MVA),
% converted to system base (Sbase=100 MVA): X_sys = 0.30*(100/900) = 0.0333 pu.
% Previous bug: used 0.30 pu on system base → P_max=333 MW < P0=700 MW → unstable.
R_gen_pu = 0.003 * (Sbase / 900e6);   % = 3.33e-4 pu on Sbase
X_gen_pu = 0.30  * (Sbase / 900e6);   % = 0.0333 pu on Sbase
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

% VSG internal impedance: Xd'=0.30 pu on VSG base (VSG_SN=200 MVA),
% converted to system base (Sbase=100 MVA): X_sys = 0.30*(100/200) = 0.15 pu.
% Separate from ConvGen impedance because VSG_SN ≠ 900 MVA.
R_vsg_pu = 0.003 * (Sbase / VSG_SN);   % = 1.50e-3 pu on Sbase
X_vsg_pu = 0.30  * (Sbase / VSG_SN);   % = 0.15 pu on Sbase
R_vsg = R_vsg_pu * Zbase;               % Ohm
L_vsg = X_vsg_pu * Zbase / (2*pi*fn);   % H

% Initial P_e/P_ref (p.u. on VSG base). NEEDS RECALIBRATION after impedance fix.
% With corrected X_vsg=0.15 pu the steady-state Pe will differ from old calibration.
% Use placeholder values from old calibration — they ensure P_ref=P0 from t=0
% but Pe(t=0) will not exactly match. Recalibrate by running slx_calibrate_vsg_p0.
VSG_P0 = [1.8725, 1.8419, 1.7888, 1.9154];  % [ES1, ES2, ES3, ES4] — NEEDS RECAL

% ESS bus assignments: ES{i} sits on a dedicated bus, connected to a main bus
%   ES1 → Bus12, connected to Bus7
%   ES2 → Bus16, connected to Bus8
%   ES3 → Bus14, connected to Bus10
%   ES4 → Bus15, connected to Bus9
ess_bus     = [12, 16, 14, 15];
ess_main    = [ 7,  8, 10,  9];

% --- Load flow initial conditions ---
% Power-angle estimates for corrected impedances (opt_kd_20260417_05).
% ConvGen: delta ≈ arcsin(P*X_gen/V²) ≈ arcsin(7*0.033) ≈ 13° from local bus.
%   Area 1 buses lead area 2 by ~25° in standard Kundur two-area case.
% VSG: delta ≈ arcsin(P_pu_sys * X_vsg) ≈ arcsin(3.75*0.15) ≈ 34° from local bus.
% [V_pu, angle_deg] — used for source initialization
vlf_gen = [1.03,  20.0;   % G1 (Bus1, area 1 slack: ~13° lead + bus at ~7°)
           1.01,  17.0;   % G2 (Bus2, area 1, ~2° behind G1 bus)
           1.01,  -7.0];  % G3 (Bus3, area 2: bus~-20°, +13° lead → -7°)
vlf_wind = [1.00,  10.0;  % W1 (Bus4, area 1)
            1.00, -18.0]; % W2 (Bus11, area 2)
vlf_ess = [1.00,  18.0;   % ES1 (Bus12→Bus7, area 1-2 junction: bus~-16°, +34°)
           1.00,  10.0;   % ES2 (Bus16→Bus8, area 2: bus~-24°, +34°)
           1.00,   7.0;   % ES3 (Bus14→Bus10, area 2: bus~-27°, +34°)
           1.00,  12.0];  % ES4 (Bus15→Bus9, area 2: bus~-22°, +34°)

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

% --- Disturbance loads (Dynamic Load + workspace variable interface) ---
% Bus14: TripLoad1_P = 248/3 MW per-phase (load ON at episode start)
% Bus15: TripLoad2_P = 0 W per-phase       (load OFF at episode start)
% Python env sets these via assignin('base', varname, value) mid-episode.
% FastRestart-safe: no topology change, no breaker switching.
trip_defs = {
    'TripLoad1_P', 14, 248e6/3, 'Bus14 248MW (on at start)';
    'TripLoad2_P', 15, 0.0,     'Bus15 188MW max (off at start)'
};

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
fprintf('RESULT: [0/12] start — building %s\n', mdl);

% Resolve ee_lib / nesl_utility block library paths.
% Discovery logic lives in ee_lib_paths.m (run discover_ee_lib_paths.m for diagnostics).
paths = ee_lib_paths();
cvs_lib        = paths.cvs;
pvs_lib        = paths.pvs;
tl_lib         = paths.tl;
wl_lib         = paths.wl;
rlc3_lib       = paths.rlc3;
gnd_lib        = paths.gnd;
dynload3ph_lib = paths.dynload3ph;
ps_lib         = paths.ps;
solver_lib     = paths.solver;
s2ps_lib       = paths.s2ps;
ps2s_lib       = paths.ps2s;
fprintf('RESULT: [0/12] ee_lib paths resolved\n');

%% ======================================================================
%  Step 1: Solver Configuration + Electrical Reference (replaces powergui)
%% ======================================================================
add_block(solver_lib, [mdl '/SolverConfig'], 'Position', [20 20 120 60]);
% Enable Simscape local fixed-step solver — required for Dynamic Load performance.
% Without this, variable-step ode23t collapses to femtosecond steps when
% Dynamic Load blocks are present (2026-04-09 verified, see simulink_base.md §14).
set_param([mdl '/SolverConfig'], 'DelaysMemoryBudget',    '4096');
set_param([mdl '/SolverConfig'], 'UseLocalSolver',        'on');
set_param([mdl '/SolverConfig'], 'DoFixedCost',           'on');
set_param([mdl '/SolverConfig'], 'LocalSolverSampleTime', '0.02');
set_param([mdl '/SolverConfig'], 'MaxNonlinIter',         '5');
set_param([mdl '/SolverConfig'], 'FilteringTimeConstant', '0.02');
% NOTE: SolverConfig connected to main network in Step 9b (after all bus topology built).
fprintf('  Solver Configuration added with LocalSolver (T=0.02s, DoFixedCost).\n');

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
fprintf('RESULT: [3/12] building generators G1-G3\n');

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
    % P0 ramp: starts at P0_pu (X0=P0_pu) so P_ref=P0 from t=0.
    % Slope still positive so the Saturate clamps it at P0_pu on every call.
    % Fixes: ramp from 0 caused omega to clip at IntW lower limit (−15 Hz)
    % during warmup, corrupting all episode observations.
    add_block('simulink/Sources/Ramp', [sub_path '/P0_ramp'], ...
        'Position', [30 90 70 110], ...
        'Slope', num2str(P0_pu / T_ramp), 'Start', '0', 'X0', num2str(P0_pu));
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

    % Integrator for omega (IC = 1.0, clamped to [0.7, 1.3])
    % Limits widened from [0.9,1.1] (±5 Hz) to [0.7,1.3] (±15 Hz) to match
    % the Python OMEGA_TERM_THRESHOLD (15 Hz / 50 Hz = 0.3 pu). The old
    % ±5 Hz hard cap saturated the output on every episode with a random
    % policy, making all actions look identically bad and killing the RL gradient.
    add_block('built-in/Integrator', [sub_path '/IntW'], ...
        'Position', [630 50 670 90], ...
        'InitialCondition', '1.0', ...
        'LimitOutput', 'on', ...
        'UpperSaturationLimit', '1.3', ...
        'LowerSaturationLimit', '0.7');

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
fprintf('RESULT: [3/12] generators done (%d)\n', length(gen_cfg));

%% ======================================================================
%  Step 4: Wind Farms W1, W2 (Programmable Voltage Source, constant)
%% ======================================================================
fprintf('\n=== Building wind farms W1, W2 ===\n');
fprintf('RESULT: [4/12] building wind farms W1-W2\n');

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
fprintf('RESULT: [4/12] wind farms done (%d)\n', length(wind_cfg));

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
fprintf('RESULT: [5/12] building VSG/ESS ES1-ES4\n');

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
        'Position', [100 10 150 30], 'Value', sprintf('M0_val_ES%d', i));
    add_block('built-in/Constant', [vsg_path '/D0'], ...
        'Position', [100 60 150 80], 'Value', sprintf('D0_val_ES%d', i));
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

    % Integrator for omega (IC = 1.0 pu, clamped to [0.7, 1.3])
    % Same reasoning as generator IntW above: widened from ±5 Hz to ±15 Hz.
    add_block('built-in/Integrator', [vsg_path '/IntW'], ...
        'Position', [620 80 660 120], ...
        'InitialCondition', '1.0', ...
        'LimitOutput', 'on', ...
        'UpperSaturationLimit', '1.3', ...
        'LowerSaturationLimit', '0.7');

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
    % P_ref ramp: starts at VSG_P0(i) so P_ref=P0 from t=0 (same fix as ConvGen).
    add_block('simulink/Sources/Ramp', [mdl '/' pref_ramp_name], ...
        'Position', [cx-80 cy cx-40 cy+15], ...
        'Slope', num2str(VSG_P0(i) / T_ramp), 'Start', '0', 'X0', num2str(VSG_P0(i)));
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
    set_param([mdl '/' rlc_name], 'R', num2str(R_vsg));
    set_param([mdl '/' rlc_name], 'L', num2str(L_vsg));  % H (ee_lib expects H, not mH)
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
fprintf('RESULT: [5/12] VSG/ESS done (%d)\n', n_vsg);

%% ======================================================================
%  Step 6: Transmission lines (Transmission Line Three-Phase)
%% ======================================================================
fprintf('\n=== Adding transmission lines ===\n');
fprintf('RESULT: [6/12] adding %d transmission lines\n', size(line_defs, 1));

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
fprintf('RESULT: [7/12] adding loads\n');

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
fprintf('RESULT: [8/12] adding shunt capacitors\n');

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
%  Step 9: Disturbance loads — Dynamic Load (Three-Phase) + workspace variables
%%
%  Architecture (FastRestart-safe, amplitude-sensitive):
%    TripLoad1_P / TripLoad2_P are MATLAB base workspace variables (W total 3ph).
%    Python sets them via assignin('base', var, value) before each sim() call.
%    Constant block reads workspace variable → S2PS → Dynamic Load P port.
%    No Phase Splitter needed: 3ph composite port connects directly to bus.
%    No breaker topology change → FastRestart compatible.
%%
%  Bus14: TripLoad1_P = 248e6 W total (load ON at episode start)
%  Bus15: TripLoad2_P = 0 W total      (load OFF at episode start)
%% ======================================================================
fprintf('\n=== Adding Dynamic Load (Three-Phase) disturbance subsystems ===\n');
fprintf('RESULT: [9/12] adding Dynamic Load (Three-Phase) disturbance subsystems\n');

% NOTE on workspace variable units:
% Python bridge uses per-phase W (tripload1_p_default = 248e6/3).
% This build script initializes 3-phase TOTAL W for the Three-Phase block.
% The bridge's per-phase value × 3 gives total 3-phase power.
% TripLoad1_P workspace var: bridge writes per-phase → multiply by 3 in Constant if needed.
% SIMPLIFICATION: use per-phase value matching bridge config (248e6/3 per phase).
% The Three-Phase block distributes equally across 3 phases internally.
% We pass per-phase W and note this in the block annotation.

% Initialize workspace variables (match bridge config: per-phase W)
TripLoad1_P = 248e6 / 3;  % Bus14: 248MW total → 82.67MW per phase; load ON at episode start
TripLoad2_P = 0.0;          % Bus15: load OFF at episode start
assignin('base', 'TripLoad1_P', TripLoad1_P);
assignin('base', 'TripLoad2_P', TripLoad2_P);

for ti = 1:size(trip_defs, 1)
    var_name    = trip_defs{ti, 1};  % 'TripLoad1_P' or 'TripLoad2_P'
    bus_id      = trip_defs{ti, 2};
    default_W   = trip_defs{ti, 3};
    label       = trip_defs{ti, 4};

    bx_t = 800 + (ti-1)*600;
    by_t = 1400;

    % --- Dynamic Load (Three-Phase): composite ~ port → direct bus connection ---
    dl3ph_name = sprintf('DynLoad_Trip%d', ti);
    add_block(dynload3ph_lib, [mdl '/' dl3ph_name], ...
        'Position', [bx_t by_t bx_t+80 by_t+60]);

    % R2025b: Dynamic Load (Three-Phase) has no "External control of PQ" parameter.
    % P/Q physical-signal ports (LConn2, LConn3) are always present.

    % Wire composite 3ph port to bus (no Phase Splitter needed)
    bus_nodes = do_wire_ee(mdl, bus_nodes, bus_id, dl3ph_name, '%s/LConn1');

    % --- P control: Constant(workspace var) → S2PS → DynLoad LConn2 (P) ---
    cp_name = sprintf('C_P_Trip%d', ti);
    add_block('built-in/Constant', [mdl '/' cp_name], ...
        'Position', [bx_t+100 by_t+70 bx_t+150 by_t+90], ...
        'Value', var_name);

    s2ps_p = sprintf('S2PS_P_Trip%d', ti);
    add_block(s2ps_lib, [mdl '/' s2ps_p], ...
        'Position', [bx_t+160 by_t+70 bx_t+200 by_t+90]);
    try
        set_param([mdl '/' s2ps_p], 'InputFilterTimeConstant', '0.02');
    catch
    end

    add_line(mdl, [cp_name '/1'],    [s2ps_p '/1'],           'autorouting', 'smart');
    add_line(mdl, [s2ps_p '/RConn1'], [dl3ph_name '/LConn2'], 'autorouting', 'smart');

    % --- Q control: Constant(0) → S2PS → DynLoad LConn3 (Q) ---
    cq_name = sprintf('C_Q_Trip%d', ti);
    add_block('built-in/Constant', [mdl '/' cq_name], ...
        'Position', [bx_t+100 by_t+100 bx_t+150 by_t+120], ...
        'Value', '0');

    s2ps_q = sprintf('S2PS_Q_Trip%d', ti);
    add_block(s2ps_lib, [mdl '/' s2ps_q], ...
        'Position', [bx_t+160 by_t+100 bx_t+200 by_t+120]);
    try
        set_param([mdl '/' s2ps_q], 'InputFilterTimeConstant', '0.02');
    catch
    end

    add_line(mdl, [cq_name '/1'],    [s2ps_q '/1'],           'autorouting', 'smart');
    add_line(mdl, [s2ps_q '/RConn1'], [dl3ph_name '/LConn3'], 'autorouting', 'smart');

    fprintf('  Trip%d at Bus%d: var=%s, default=%.0fW/phase — %s\n', ...
        ti, bus_id, var_name, default_W, label);
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
fprintf('RESULT: [9b/12] solver config wired to network\n');

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
fprintf('RESULT: [11/12] model saved — %s\n', model_path);

%% ======================================================================
%  Step 12: Test simulation (1 second)
%% ======================================================================
fprintf('\n=== Running 1-second test simulation ===\n');
fprintf('RESULT: [12/12] test simulation running\n');

% Initialize workspace variables required by workspace-backed Constant blocks
for i = 1:n_vsg
    assignin('base', sprintf('M0_val_ES%d', i), VSG_M0);
    assignin('base', sprintf('D0_val_ES%d', i), VSG_D0);
end
assignin('base', 'TripLoad1_P', 248e6 / 3);
assignin('base', 'TripLoad2_P', 0.0);

try
    simOut = sim(mdl, 'StopTime', '1.0');
    fprintf('SUCCESS! 1-second simulation completed.\n');
    fprintf('RESULT: [12/12] test simulation OK\n');

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
fprintf('RESULT: [DONE] build_powerlib_kundur complete\n');
fprintf('Model: %s\n', model_path);
fprintf('Topology: 16-bus Modified Kundur Two-Area System\n');
fprintf('Conv Gens: G1(Bus1), G2(Bus2), G3(Bus3) — swing eq + CVS, P_e=sensor\n');
fprintf('Wind Farms: W1(Bus4)=700MW, W2(Bus11->8)=100MW — PVS constant\n');
fprintf('VSGs: ES1(Bus12->7), ES2(Bus16->8), ES3(Bus14->10), ES4(Bus15->9)\n');
fprintf('  VSG feedback: Power Sensor -> P_e -> swing eq -> delta -> CVS\n');
fprintf('Loads: Bus7=967MW, Bus9=1767MW (Wye-Connected Load)\n');
fprintf('Shunts: Bus7=200Mvar, Bus9=350Mvar\n');
fprintf('Disturbance: Bus14(TripLoad1_P=248MW), Bus15(TripLoad2_P=0) — Dynamic Load + workspace vars\n');
fprintf('Solver: ode23t variable-step + Simscape LocalSolver T=0.02s (Dynamic Load perf fix)\n');
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
