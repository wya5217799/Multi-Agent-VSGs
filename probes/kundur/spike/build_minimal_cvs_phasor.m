function build_minimal_cvs_phasor()
% build_minimal_cvs_phasor  Minimal SMIB model probe for "SPS Phasor + CVS" feasibility.
%
% Purpose: prove or disprove that powergui Phasor mode can host an
% ee_lib (Simscape Electrical PS-domain) Controlled Voltage Source
% as a VSG terminal port, driven by a swing-equation signal chain.
%
% Scope: SPIKE ONLY. Read-only against project main artifacts. The
% generated .slx lives at probes/kundur/spike/minimal_cvs_smib.slx
% and must NEVER be referenced from main code paths.
%
% Topology (1 VSG vs infinite bus):
%   [Clock] -> [Gain wn] -> Sum(+IntD) -> theta -> [sinABC + Vpk gain]
%        -> [S2PS] -> [CVS_VSG, ee_lib] -> [RLC R+jX] -> [V-I Meas]
%        -> [Three-Phase Source = infinite bus 230 kV, 0 deg]
%   Pe = (V * I) computed via Goto/From + product
%   Swing eq:  domega/dt = (Pm - Pe - D*(omega-1)) / M ; ddelta/dt = wn*(omega-1)
%
% Outputs to base workspace (timeseries):
%   omega_ts, delta_ts, Pe_ts, Vabc_ts, Iabc_ts
%
% Author: spike for jaunty-imagining-lovelace.md eval
% Status: leaf probe — DO NOT promote to main.

mdl     = 'minimal_cvs_smib';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

% ---- Parameters ----
fn      = 50;
wn      = 2*pi*fn;
Sbase   = 100e6;
Vbase   = 230e3;
Vpk     = Vbase * sqrt(2/3);     % phase peak voltage
M0      = 12.0;                  % 2H, H=6
D0      = 3.0;
Pm      = 0.2;                   % VSG-base pu mech power
VSG_SN  = 200e6;
R_vsg   = 0.003 * (Vbase^2/VSG_SN);  % terminal series R
L_vsg   = 0.30  * (Vbase^2/VSG_SN) / wn;  % terminal series L

% ---- Reset / new model ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');
load_system('ee_lib');
load_system('nesl_utility');

addpath(fullfile(fileparts(out_dir), '..', '..', 'scenarios', 'kundur', 'simulink_models'));
paths = ee_lib_paths();

% ---- powergui Phasor 50 Hz ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', ...
    'frequency', num2str(fn), 'Pbase', num2str(Sbase));

% ---- Solver settings ----
set_param(mdl, 'StopTime', '5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

% ---- ee_lib needs a Solver Configuration block for PS-domain ----
add_block(paths.solver, [mdl '/SolverConfig'], 'Position', [120 20 160 50]);

% ---- Signal chain for VSG terminal voltage ----
% Clock -> wn -> + IntD -> theta -> sin*Vpk per phase
add_block('built-in/Clock', [mdl '/Clk'], 'Position', [60 200 90 220]);
add_block('built-in/Gain', [mdl '/wnGain'], 'Position', [120 200 160 220], ...
    'Gain', num2str(wn));
add_line(mdl, 'Clk/1', 'wnGain/1');

% IntD initial value 0; will integrate (omega-1)*wn
add_block('built-in/Sum', [mdl '/SumThetaDelta'], ...
    'Position', [200 200 230 220], 'Inputs', '++');
add_line(mdl, 'wnGain/1', 'SumThetaDelta/1');

% IntD integrator + wired below from omega path (placeholder constant for now)
add_block('built-in/Integrator', [mdl '/IntD'], ...
    'Position', [400 280 430 310], 'InitialCondition', '0');

% IntW integrator: input = (Pm - Pe - D*(omega-1))/M; output = omega
add_block('built-in/Integrator', [mdl '/IntW'], ...
    'Position', [400 380 430 410], 'InitialCondition', '1');

% omega - 1 for swing eq
add_block('built-in/Constant', [mdl '/One'], ...
    'Position', [200 350 230 370], 'Value', '1');
add_block('built-in/Sum', [mdl '/SumDw'], ...
    'Position', [260 380 290 410], 'Inputs', '+-');
add_line(mdl, 'IntW/1', 'SumDw/1');
add_line(mdl, 'One/1', 'SumDw/2');

% IntD input = (omega-1)*wn
add_block('built-in/Gain', [mdl '/wnGainD'], ...
    'Position', [320 280 360 310], 'Gain', num2str(wn));
add_line(mdl, 'SumDw/1', 'wnGainD/1');
add_line(mdl, 'wnGainD/1', 'IntD/1');
add_line(mdl, 'IntD/1', 'SumThetaDelta/2');

% ---- Vabc generation: sin(theta), sin(theta-2pi/3), sin(theta+2pi/3) * Vpk ----
% Build inside subsystem
sub = [mdl '/Vabc_gen'];
add_block('built-in/SubSystem', sub, 'Position', [260 180 360 240]);
try, delete_line(sub, 'In1/1', 'Out1/1'); catch, end
try, delete_block([sub '/In1']); catch, end
try, delete_block([sub '/Out1']); catch, end

add_block('built-in/Inport',  [sub '/theta'], 'Position', [20 60 50 74], 'Port', '1');
add_block('built-in/Trigonometry', [sub '/sinA'], 'Position', [120 50 160 70], 'Operator', 'sin');
add_block('built-in/Constant', [sub '/shB'], 'Position', [80 100 110 120], 'Value', num2str(-2*pi/3));
add_block('built-in/Sum', [sub '/sumB'], 'Position', [140 100 170 120], 'Inputs', '++');
add_block('built-in/Trigonometry', [sub '/sinB'], 'Position', [200 100 240 120], 'Operator', 'sin');
add_block('built-in/Constant', [sub '/shC'], 'Position', [80 150 110 170], 'Value', num2str(2*pi/3));
add_block('built-in/Sum', [sub '/sumC'], 'Position', [140 150 170 170], 'Inputs', '++');
add_block('built-in/Trigonometry', [sub '/sinC'], 'Position', [200 150 240 170], 'Operator', 'sin');
add_block('built-in/Gain', [sub '/GA'], 'Position', [200 50 240 70], 'Gain', num2str(Vpk));
add_block('built-in/Gain', [sub '/GB'], 'Position', [270 100 310 120], 'Gain', num2str(Vpk));
add_block('built-in/Gain', [sub '/GC'], 'Position', [270 150 310 170], 'Gain', num2str(Vpk));
add_block('built-in/Mux', [sub '/Mux'], 'Position', [340 50 345 175], 'Inputs', '3');
add_block('built-in/Outport', [sub '/Vabc'], 'Position', [380 100 410 114], 'Port', '1');

add_line(sub, 'theta/1', 'sinA/1');
add_line(sub, 'sinA/1', 'GA/1');
add_line(sub, 'theta/1', 'sumB/1');
add_line(sub, 'shB/1', 'sumB/2');
add_line(sub, 'sumB/1', 'sinB/1');
add_line(sub, 'sinB/1', 'GB/1');
add_line(sub, 'theta/1', 'sumC/1');
add_line(sub, 'shC/1', 'sumC/2');
add_line(sub, 'sumC/1', 'sinC/1');
add_line(sub, 'sinC/1', 'GC/1');
add_line(sub, 'GA/1', 'Mux/1');
add_line(sub, 'GB/1', 'Mux/2');
add_line(sub, 'GC/1', 'Mux/3');
add_line(sub, 'Mux/1', 'Vabc/1');

add_line(mdl, 'SumThetaDelta/1', 'Vabc_gen/1', 'autorouting', 'smart');

% ---- S2PS converter (3 individual S2PS blocks for 3 phases via demux) ----
% Use 1 S2PS for vector signal (Mux'd) - ee_lib S2PS supports vector
add_block(paths.s2ps, [mdl '/S2PS'], 'Position', [400 195 440 225]);
add_line(mdl, 'Vabc_gen/1', 'S2PS/1');

% ---- CVS (ee_lib Three-Phase Controlled Voltage Source) ----
add_block(paths.cvs, [mdl '/CVS_VSG'], 'Position', [470 180 540 250]);
% ee_lib CVS LConn1 = signal input (PS), LConn2 = neutral, RConn1 = 3-phase
add_line(mdl, 'S2PS/RConn1', 'CVS_VSG/LConn1', 'autorouting', 'smart');

% Neutral to GND
add_block(paths.gnd, [mdl '/GND_VSG'], 'Position', [470 280 510 310]);
add_line(mdl, 'CVS_VSG/LConn2', 'GND_VSG/LConn1', 'autorouting', 'smart');

% ---- RLC series impedance ----
add_block(paths.rlc3, [mdl '/Zvsg'], 'Position', [580 180 650 250]);
set_param([mdl '/Zvsg'], 'component_structure', '4');  % series RL
set_param([mdl '/Zvsg'], 'R', num2str(R_vsg));
set_param([mdl '/Zvsg'], 'L', num2str(L_vsg));
add_line(mdl, 'CVS_VSG/RConn1', 'Zvsg/LConn1', 'autorouting', 'smart');

% ---- V-I Measurement (powerlib SPS block) ----
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/VImeas'], 'Position', [690 180 750 250]);
set_param([mdl '/VImeas'], 'VoltageMeasurement', 'phase-to-ground', ...
    'CurrentMeasurement', 'yes', ...
    'SetLabelV', 'on', 'LabelV', 'Vabc_VSG', ...
    'SetLabelI', 'on', 'LabelI', 'Iabc_VSG');

% RLC right side -> VImeas LConn (powerlib SPS port)
% NOTE: ee_lib RLC RConn1 outputs PS-domain electrical, while VImeas takes
% SPS-domain electrical input. THIS IS A HYBRID DOMAIN BOUNDARY.
% To bridge, ee_lib provides "Power Sensor" in PS-domain; SPS needs separate path.
% For this spike, we test the simplest connection and let compile diagnose.
add_line(mdl, 'Zvsg/RConn1', 'VImeas/LConn1', 'autorouting', 'smart');

% ---- Infinite bus: powerlib Three-Phase Source 230 kV / 0 deg ----
add_block('powerlib/Electrical Sources/Three-Phase Source', ...
    [mdl '/InfBus'], 'Position', [800 180 870 260]);
set_param([mdl '/InfBus'], 'Voltage', num2str(Vbase), ...
    'PhaseAngle', '0', 'Frequency', num2str(fn), ...
    'NonIdealSource', 'on', 'SpecifyImpedance', 'on', ...
    'ShortCircuitLevel', '1e9', 'BaseVoltage', num2str(Vbase), 'XRratio', '7');

add_line(mdl, 'VImeas/LConn2', 'InfBus/LConn1', 'autorouting', 'smart');

% ---- Pe computation: From Vabc/Iabc broadcast tags ----
add_block('built-in/From', [mdl '/FromV'], 'Position', [780 380 820 400], ...
    'GotoTag', 'Vabc_VSG');
add_block('built-in/From', [mdl '/FromI'], 'Position', [780 420 820 440], ...
    'GotoTag', 'Iabc_VSG');
% V * I element-wise then sum / 3
add_block('built-in/Product', [mdl '/PeProd'], 'Position', [840 390 870 420], ...
    'Inputs', '2');
add_line(mdl, 'FromV/1', 'PeProd/1');
add_line(mdl, 'FromI/1', 'PeProd/2');
add_block('built-in/Sum', [mdl '/PeSum'], 'Position', [890 395 920 415], ...
    'IconShape', 'rectangular', 'Inputs', '+');
add_line(mdl, 'PeProd/1', 'PeSum/1');

% Pe -> per VSG_SN scaling
add_block('built-in/Gain', [mdl '/Pe_pu'], 'Position', [940 395 980 415], ...
    'Gain', num2str(0.5/VSG_SN));  % 0.5 because Phasor V*I returns peak phasor
add_line(mdl, 'PeSum/1', 'Pe_pu/1');

% Pe ToWorkspace
add_block('simulink/Sinks/To Workspace', [mdl '/Pe_log'], ...
    'Position', [1000 395 1050 415], 'VariableName', 'Pe_ts', ...
    'SaveFormat', 'Timeseries');
add_line(mdl, 'Pe_pu/1', 'Pe_log/1');

% ---- Swing eq input: (Pm - Pe - D*(omega-1)) / M ----
add_block('built-in/Constant', [mdl '/Pm_const'], ...
    'Position', [200 440 230 460], 'Value', num2str(Pm));
add_block('built-in/Gain', [mdl '/Dgain'], ...
    'Position', [320 470 360 490], 'Gain', num2str(D0));
add_line(mdl, 'SumDw/1', 'Dgain/1');

add_block('built-in/Sum', [mdl '/SumSwing'], ...
    'Position', [330 425 360 480], 'Inputs', '+--');
add_line(mdl, 'Pm_const/1', 'SumSwing/1');
% Pe input
add_line(mdl, 'Pe_pu/1', 'SumSwing/2');
add_line(mdl, 'Dgain/1', 'SumSwing/3');

add_block('built-in/Gain', [mdl '/Mgain'], ...
    'Position', [370 425 400 445], 'Gain', num2str(1/M0));
add_line(mdl, 'SumSwing/1', 'Mgain/1');
add_line(mdl, 'Mgain/1', 'IntW/1');

% ---- Loggers ----
add_block('simulink/Sinks/To Workspace', [mdl '/omega_log'], ...
    'Position', [460 380 510 400], 'VariableName', 'omega_ts', ...
    'SaveFormat', 'Timeseries');
add_line(mdl, 'IntW/1', 'omega_log/1');

add_block('simulink/Sinks/To Workspace', [mdl '/delta_log'], ...
    'Position', [460 280 510 300], 'VariableName', 'delta_ts', ...
    'SaveFormat', 'Timeseries');
add_line(mdl, 'IntD/1', 'delta_log/1');

% ---- Save ----
save_system(mdl, out_slx);
fprintf('RESULT: minimal_cvs_smib built at %s\n', out_slx);
fprintf('RESULT: powergui mode = Phasor; CVS source = %s\n', paths.cvs);

end
