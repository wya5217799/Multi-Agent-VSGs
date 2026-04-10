%% test_gentpj_minimal.m
% Minimal test: ONE GENTPJ generator + ONE load
% Purpose: verify GENTPJ works with proper mechanical network
%   (Inertia + Damper + Torque Source + correct Efd)
%
% GENTPJ has NO built-in swing equation (no H parameter).
% The swing equation must come from external mechanical components:
%   J*dω/dt = Tm - Te - D*Δω
%   where: J = Inertia block, Tm = Torque Source, Te = from GENTPJ,
%          D = Rotational Damper

mdl = 'test_gentpj_min';
try close_system(mdl, 0); catch; end
if exist([mdl '.slx'], 'file'), delete([mdl '.slx']); end
new_system(mdl); open_system(mdl);

load_system('ee_lib');
load_system('nesl_utility');
load_system('fl_lib');
load_system('simulink');

set_param(mdl, 'Solver', 'ode23t', 'StopTime', '5', ...
    'RelTol', '1e-4', 'MaxStep', '0.005');

fprintf('Building minimal GENTPJ test model...\n');

%% Parameters
Sn = 900e6;       % 900 MVA
Vn = 24e3;        % 24 kV (generator rated voltage)
fn = 60;
omega_s = 2*pi*fn;
H = 6.5;          % Inertia constant (s)
D_mech = 2.0;     % Damping coefficient (pu)
Pm = 500e6;       % Mechanical power (W)

% Physical inertia and damping
J = 2*H*Sn / omega_s^2;          % kg·m²
D_phys = D_mech*Sn / omega_s^2;  % N·m·s/rad
Tm = Pm / omega_s;                % Torque (N·m)

fprintf('  J = %.0f kg·m², D = %.1f N·m·s, Tm = %.0f N·m\n', J, D_phys, Tm);

%% Global references
add_block('nesl_utility/Solver Configuration', [mdl '/Solver'], 'Position', [50,20,140,60]);
add_block('ee_lib/Connectors & References/Electrical Reference', [mdl '/GND'], 'Position', [200,20,240,60]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference', [mdl '/MechRef'], 'Position', [320,20,360,60]);
% Solver must connect to the physical network. Connect to MechRef
% (which bridges to electrical via GENTPJ)
add_line(mdl, 'Solver/RConn1', 'MechRef/LConn1');

%% GENTPJ Generator
refBlk = sprintf('ee_lib/Electromechanical/Synchronous/Synchronous Machine\nGENTPJ');
add_block(refBlk, [mdl '/G1'], 'Position', [400, 200, 500, 350]);

% Machine parameters
set_param([mdl '/G1'], 'SRated', num2str(Sn), 'VRated', num2str(Vn));
set_param([mdl '/G1'], 'FRated', '60', 'nPolePairs', '1');
set_param([mdl '/G1'], 'Ra', '0.0025', 'Xl', '0.2');
set_param([mdl '/G1'], 'Xd', '1.8', 'Xq', '1.7');
set_param([mdl '/G1'], 'Xdd', '0.3', 'Xqd', '0.55');
set_param([mdl '/G1'], 'Xddd', '0.25', 'Xqdd', '0.25');
set_param([mdl '/G1'], 'Td0d', '8.0', 'Tq0d', '0.4');
set_param([mdl '/G1'], 'Td0dd', '0.03', 'Tq0dd', '0.05');

% Load flow initialization
set_param([mdl '/G1'], 'source_type', 'ee.enum.sm.load_flow_source_type.Swing');
set_param([mdl '/G1'], 'Vmag0', num2str(Vn), 'Vang0', '0');
set_param([mdl '/G1'], 'Pt0', num2str(Pm), 'Qt0', '0');

fprintf('  GENTPJ added (VRated=%d kV)\n', Vn/1e3);

%% Efd input (LConn1 = Physical Signal)
% Compute approximate Efd for this operating point:
% At Vt=1pu, P=Pm/Sn, Q≈0: Efd ≈ |Vt + jXd*I| ≈ |1 + jXd*(P-jQ)/Vt|
P_pu = Pm/Sn; Q_pu = 0;
I_pu = P_pu - 1j*Q_pu;
E_pu = 1.0 + (0.0025 + 1j*1.8)*I_pu;
Efd_pu = abs(E_pu);
fprintf('  Computed Efd ≈ %.3f pu\n', Efd_pu);

add_block('fl_lib/Physical Signals/Sources/PS Constant', [mdl '/Efd'], ...
    'Position', [300, 210, 350, 240]);
set_param([mdl '/Efd'], 'constant', num2str(Efd_pu, '%.4f'));
add_line(mdl, 'Efd/RConn1', 'G1/LConn1');

%% Measurement output (RConn1 = Physical Signal) → terminate
add_block('nesl_utility/PS-Simulink Converter', [mdl '/PS2S'], ...
    'Position', [550, 210, 580, 240]);
add_block('simulink/Sinks/Terminator', [mdl '/Term'], ...
    'Position', [610, 215, 630, 235]);
add_line(mdl, 'G1/RConn1', 'PS2S/LConn1');
add_line(mdl, 'PS2S/1', 'Term/1');

%% Mechanical network on shaft
% All connected at shaft node (GENTPJ LConn2)
% GENTPJ LConn3 (mech R) → MechRef

% 1. Inertia (J = 2H*S/ω²)
add_block('fl_lib/Mechanical/Rotational Elements/Inertia', [mdl '/Inertia'], ...
    'Position', [300, 300, 360, 340]);
set_param([mdl '/Inertia'], 'inertia', num2str(J, '%.6g'));

% 2. Rotational Damper (D)
add_block('fl_lib/Mechanical/Rotational Elements/Rotational Damper', [mdl '/Damper'], ...
    'Position', [300, 370, 360, 410]);
set_param([mdl '/Damper'], 'D', num2str(D_phys, '%.6g'));

% 3. Ideal Torque Source (Pm)
add_block('fl_lib/Mechanical/Mechanical Sources/Ideal Torque Source', [mdl '/TmSrc'], ...
    'Position', [200, 300, 260, 350]);
add_block('fl_lib/Physical Signals/Sources/PS Constant', [mdl '/PmVal'], ...
    'Position', [120, 310, 170, 340]);
set_param([mdl '/PmVal'], 'constant', num2str(Tm, '%.6g'));
add_line(mdl, 'PmVal/RConn1', 'TmSrc/RConn1');  % signal input

% Wire mechanical network
% All "shaft side" ports connect together at the GENTPJ shaft node
% GENTPJ LConn2 = shaft (mech C)
% TorqueSource: one mech port → shaft, other → MechRef
% Inertia: one port → shaft, other → MechRef
% Damper: one port → shaft, other → MechRef

% First, find which ports connect where
% TS: LConn1=mechC, RConn2=mechR. We use RConn2→shaft (tested: RConn2→GENTPJ LConn2 works)
add_line(mdl, 'TmSrc/RConn2', 'G1/LConn2');    % TS_R → shaft
add_line(mdl, 'TmSrc/LConn1', 'MechRef/LConn1'); % TS_C → ref

% Inertia: ONE port only (LConn1), implicitly references absolute frame
add_line(mdl, 'Inertia/LConn1', 'G1/LConn2');     % I → shaft

% Damper: TWO ports (LConn1, RConn1)
add_line(mdl, 'Damper/LConn1', 'G1/LConn2');     % D → shaft
add_line(mdl, 'Damper/RConn1', 'MechRef/LConn1'); % D → ref

% GENTPJ reference port
add_line(mdl, 'G1/LConn3', 'MechRef/LConn1');

fprintf('  Mechanical network: TorqueSrc + Inertia(J) + Damper(D) on shaft\n');

%% Electrical load (at generator voltage, 24 kV)
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load', [mdl '/Load'], ...
    'Position', [550, 300, 630, 380]);
set_param([mdl '/Load'], 'VRated', num2str(Vn), 'FRated', '60');
set_param([mdl '/Load'], 'P', num2str(Pm));
set_param([mdl '/Load'], 'component_structure', 'ee.enum.rlc.structure.R');

% Connect 3ph: GENTPJ RConn2 → Load
add_line(mdl, 'G1/RConn2', 'Load/LConn1');

%% Step disturbance: add extra load at t=2s
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load', [mdl '/DLoad'], ...
    'Position', [650, 300, 730, 380]);
set_param([mdl '/DLoad'], 'VRated', num2str(Vn), 'FRated', '60');
set_param([mdl '/DLoad'], 'P', num2str(Pm*0.1));  % 10% step
set_param([mdl '/DLoad'], 'component_structure', 'ee.enum.rlc.structure.R');

add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)', [mdl '/SW'], ...
    'Position', [580, 350, 640, 420]);
add_block('nesl_utility/Simulink-PS Converter', [mdl '/S2PS'], ...
    'Position', [520, 370, 550, 400]);
add_block('simulink/Sources/Step', [mdl '/Trip'], ...
    'Position', [460, 375, 500, 395]);
set_param([mdl '/Trip'], 'Time', '2', 'Before', '0', 'After', '1');

add_line(mdl, 'Trip/1', 'S2PS/1');
add_line(mdl, 'S2PS/RConn1', 'SW/LConn1');
add_line(mdl, 'G1/RConn2', 'SW/LConn2');
add_line(mdl, 'SW/RConn1', 'DLoad/LConn1');

%% Enable logging and save
try set_param(mdl, 'SimscapeLogType', 'all', 'SimscapeLogName', 'simlog'); catch; end
save_system(mdl);
fprintf('Model saved: %s.slx\n\n', mdl);

%% Run simulation
fprintf('Simulating...\n');
tic;
try
    out = sim(mdl, 'StopTime', '5');
    fprintf('Done in %.1fs\n', toc);

    % Check frequency response
    try
        simlog = out.simlog;
        % Try to find omegaDel or omega
        try
            v = simlog.G1.omegaDel.series.values;
            t = simlog.G1.omegaDel.series.time;
            fprintf('G1 omegaDel: min=%.6f, max=%.6f (pu)\n', min(v), max(v));
            fprintf('G1 Δf: [%.4f, %.4f] Hz\n', min(v)*60, max(v)*60);
        catch
            fprintf('No omegaDel found. Checking Inertia speed...\n');
            try
                w = simlog.Inertia.w.series.values;
                t = simlog.Inertia.w.series.time;
                fprintf('Inertia ω: [%.4f, %.4f] rad/s (nominal=%.2f)\n', ...
                    min(w), max(w), 2*pi*60);
                dw = w - 2*pi*60;
                fprintf('Δω: [%.4f, %.4f] rad/s → Δf: [%.4f, %.4f] Hz\n', ...
                    min(dw), max(dw), min(dw)/(2*pi), max(dw)/(2*pi));
            catch e2
                fprintf('Also no Inertia.w: %s\n', e2.message);
            end
        end
    catch e
        fprintf('Could not read simlog: %s\n', e.message);
    end
catch e
    fprintf('Simulation FAILED (%.1fs): %s\n', toc, e.message);
    % Print first few warnings
    w = lastwarn;
    if ~isempty(w), fprintf('Last warning: %s\n', w); end
end
