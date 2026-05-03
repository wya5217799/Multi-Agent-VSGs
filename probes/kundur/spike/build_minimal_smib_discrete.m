function build_minimal_smib_discrete()
% build_minimal_smib_discrete  Phase 0 oracle (REWRITE) — all-SPS topology.
%
% Goal: prove Discrete + LoadStep step gives >= 0.3 Hz on minimal SMIB.
% Plan: quality_reports/plans/2026-05-03_discrete_rebuild_phase0_smib_first.md
%
% Architecture (all SimPowerSystems / spsElectrical domain — single library
% to avoid PS↔SPS domain mismatch):
%
%   3 phases sin(theta-k·2pi/3) × Vpk → 3 SPS Controlled Voltage Sources
%        → Y-connected to neutral GND
%   Phase A/B/C wires → Series RLC (Zvsg per phase, R+L) → Bus node
%   Bus node → Three-Phase V-I Measurement
%   Bus → Three-Phase Series RLC Load (constant 200 MW)
%   Bus → Three-Phase Breaker → Three-Phase Series RLC Load (step 248 MW,
%                                breaker closes at t_step)
%
%   Pe via Three-Phase V-I Measurement broadcast (Vabc, Iabc) + Goto/From
%   Swing eq:  dω/dt = (Pm - Pe - D*(ω-1))/M ; dδ/dt = wn*(ω-1)
%
% Why all-SPS not ee_lib + powerlib:
%   ee_lib (PS-Electrical) and powerlib/sps (spsElectrical) cannot directly
%   connect under Discrete (Phasor mode uses implicit conversion that's
%   absent in Discrete). Single-library = no domain mismatch.
%
% Workspace vars (settable across sims):
%   Pm_pu_vsg          — VSG mech power vsg-base pu (default 0.2)
%   M_vsg, D_vsg       — swing eq params (default 24, 4.5)
%   LoadStep_t_s       — breaker close time (default 2.0)
%   LoadStep_amp_W     — step load active power (default 248e6)
%
% Outputs (timeseries to base ws):
%   omega_ts, delta_ts, Pe_ts, Vabc_VSG, Iabc_VSG

mdl     = 'minimal_smib_discrete';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

% ---- Parameters (match v3 ESS defaults) ----
fn       = 50;
wn       = 2*pi*fn;
Sbase    = 100e6;
Vbase    = 230e3;          % L-L RMS
Vpk_ph   = Vbase * sqrt(2/3);  % phase peak (single-phase to neutral)
M0       = 24.0;
D0       = 4.5;
Pm0      = 0.2;
VSG_SN   = 200e6;
R_vsg    = 0.003 * (Vbase^2/VSG_SN);
L_vsg    = 0.30  * (Vbase^2/VSG_SN) / wn;

% Constant load: match Pm to maintain IC steady state
% Pm0 = 0.2 vsg-pu × VSG_SN(200 MVA) = 40 MW
P_const_W = Pm0 * VSG_SN;     % 40 MW
% For SPS Three-Phase Series RLC Load: takes line voltage + 3-phase active power
% no need to compute per-phase R manually

% ---- Reset ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% ---- Workspace vars (parametric) ----
assignin('base', 'Pm_pu_vsg',      double(Pm0));
assignin('base', 'M_vsg',          double(M0));
assignin('base', 'D_vsg',          double(D0));
assignin('base', 'LoadStep_t_s',   double(2.0));
assignin('base', 'LoadStep_amp_W', double(248e6));
assignin('base', 'Vbase_const',    double(Vbase));

% ---- powergui Discrete 50us ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', ...
    'SampleTime', '50e-6');

% ---- Solver: Fixed-step discrete ----
set_param(mdl, 'StopTime', '5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

% ===================================================================
% Block 1: theta generation chain (Clock -> wn -> Sum -> theta)
% ===================================================================
add_block('built-in/Clock', [mdl '/Clk'], 'Position', [60 200 90 220]);
add_block('built-in/Gain', [mdl '/wnGain'], 'Position', [120 200 160 220], ...
    'Gain', num2str(wn));
add_line(mdl, 'Clk/1', 'wnGain/1');

add_block('built-in/Sum', [mdl '/SumThetaDelta'], ...
    'Position', [200 200 230 220], 'Inputs', '++');
add_line(mdl, 'wnGain/1', 'SumThetaDelta/1');

% IntD (delta integrator)
add_block('built-in/Integrator', [mdl '/IntD'], ...
    'Position', [400 280 430 310], 'InitialCondition', '0');

% IntW (omega integrator)
add_block('built-in/Integrator', [mdl '/IntW'], ...
    'Position', [400 380 430 410], 'InitialCondition', '1');

% omega - 1
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

% ===================================================================
% Block 2: Per-phase sin signal generation (3 separate channels)
% ===================================================================
% theta_A = theta
% theta_B = theta - 2pi/3
% theta_C = theta + 2pi/3

add_block('built-in/Constant', [mdl '/PhaseShiftB'], ...
    'Position', [240 240 270 260], 'Value', num2str(-2*pi/3));
add_block('built-in/Constant', [mdl '/PhaseShiftC'], ...
    'Position', [240 280 270 300], 'Value', num2str(2*pi/3));

add_block('built-in/Sum', [mdl '/SumThetaB'], ...
    'Position', [290 220 320 250], 'Inputs', '++');
add_block('built-in/Sum', [mdl '/SumThetaC'], ...
    'Position', [290 260 320 290], 'Inputs', '++');
add_line(mdl, 'SumThetaDelta/1', 'SumThetaB/1');
add_line(mdl, 'PhaseShiftB/1', 'SumThetaB/2');
add_line(mdl, 'SumThetaDelta/1', 'SumThetaC/1');
add_line(mdl, 'PhaseShiftC/1', 'SumThetaC/2');

% sin blocks per phase
add_block('built-in/Trigonometry', [mdl '/SinA'], ...
    'Position', [340 200 370 220], 'Operator', 'sin');
add_block('built-in/Trigonometry', [mdl '/SinB'], ...
    'Position', [340 230 370 250], 'Operator', 'sin');
add_block('built-in/Trigonometry', [mdl '/SinC'], ...
    'Position', [340 270 370 290], 'Operator', 'sin');
add_line(mdl, 'SumThetaDelta/1', 'SinA/1');
add_line(mdl, 'SumThetaB/1', 'SinB/1');
add_line(mdl, 'SumThetaC/1', 'SinC/1');

% Scale by Vpk_ph
add_block('built-in/Gain', [mdl '/VpkA'], ...
    'Position', [390 200 420 220], 'Gain', num2str(Vpk_ph));
add_block('built-in/Gain', [mdl '/VpkB'], ...
    'Position', [390 230 420 250], 'Gain', num2str(Vpk_ph));
add_block('built-in/Gain', [mdl '/VpkC'], ...
    'Position', [390 270 420 290], 'Gain', num2str(Vpk_ph));
add_line(mdl, 'SinA/1', 'VpkA/1');
add_line(mdl, 'SinB/1', 'VpkB/1');
add_line(mdl, 'SinC/1', 'VpkC/1');

% ===================================================================
% Block 3: 3 SPS Controlled Voltage Sources (one per phase)
% ===================================================================
% spsControlledVoltageSourceLib/Controlled Voltage Source — single phase,
% takes signal input and produces voltage at LConn1/RConn1 terminals
add_block('spsControlledVoltageSourceLib/Controlled Voltage Source', ...
    [mdl '/CVS_A'], 'Position', [450 195 490 235]);
set_param([mdl '/CVS_A'], 'Initialize', 'on');
add_block('spsControlledVoltageSourceLib/Controlled Voltage Source', ...
    [mdl '/CVS_B'], 'Position', [450 245 490 285]);
set_param([mdl '/CVS_B'], 'Initialize', 'on');
add_block('spsControlledVoltageSourceLib/Controlled Voltage Source', ...
    [mdl '/CVS_C'], 'Position', [450 295 490 335]);
set_param([mdl '/CVS_C'], 'Initialize', 'on');

add_line(mdl, 'VpkA/1', 'CVS_A/1');
add_line(mdl, 'VpkB/1', 'CVS_B/1');
add_line(mdl, 'VpkC/1', 'CVS_C/1');

% Neutral: connect all CVS LConn2 (negative terminal) to GND
% SPS CVS has LConn1 = neg, RConn1 = pos
add_block('powerlib/Elements/Ground', [mdl '/GND_neutral'], ...
    'Position', [450 380 490 410]);
add_line(mdl, 'CVS_A/LConn1', 'GND_neutral/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CVS_B/LConn1', 'GND_neutral/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CVS_C/LConn1', 'GND_neutral/LConn1', 'autorouting', 'smart');

% ===================================================================
% Block 4: Per-phase line impedance (Series RLC R+L)
% ===================================================================
add_block('spsSeriesRLCBranchLib/Series RLC Branch', ...
    [mdl '/Zvsg_A'], 'Position', [520 195 560 235]);
set_param([mdl '/Zvsg_A'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));
add_block('spsSeriesRLCBranchLib/Series RLC Branch', ...
    [mdl '/Zvsg_B'], 'Position', [520 245 560 285]);
set_param([mdl '/Zvsg_B'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));
add_block('spsSeriesRLCBranchLib/Series RLC Branch', ...
    [mdl '/Zvsg_C'], 'Position', [520 295 560 335]);
set_param([mdl '/Zvsg_C'], 'BranchType', 'RL', ...
    'Resistance', num2str(R_vsg), 'Inductance', num2str(L_vsg));

add_line(mdl, 'CVS_A/RConn1', 'Zvsg_A/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CVS_B/RConn1', 'Zvsg_B/LConn1', 'autorouting', 'smart');
add_line(mdl, 'CVS_C/RConn1', 'Zvsg_C/LConn1', 'autorouting', 'smart');

% ===================================================================
% Block 5: Three-Phase V-I Measurement on bus side
% ===================================================================
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/VImeas'], 'Position', [600 195 670 335]);
set_param([mdl '/VImeas'], 'VoltageMeasurement', 'phase-to-ground', ...
    'CurrentMeasurement', 'yes', ...
    'SetLabelV', 'on', 'LabelV', 'Vabc_VSG', ...
    'SetLabelI', 'on', 'LabelI', 'Iabc_VSG');

% VImeas has 3 LConn (A,B,C input from source) + 3 RConn (A,B,C output to load)
add_line(mdl, 'Zvsg_A/RConn1', 'VImeas/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_B/RConn1', 'VImeas/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Zvsg_C/RConn1', 'VImeas/LConn3', 'autorouting', 'smart');

% ===================================================================
% Block 6: Constant 3-phase load (Three-Phase Series RLC Load, R-only)
% Block path uses newline embedded in name (sps library quirk):
%   'sps_lib/Passives/Three-Phase\nSeries RLC Load'
% ===================================================================
load_path = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
add_block(load_path, [mdl '/Load_const'], 'Position', [710 195 780 335]);
set_param([mdl '/Load_const'], 'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
    'ActivePower', num2str(P_const_W), ...
    'InductivePower', '0', 'CapacitivePower', '0');

add_line(mdl, 'VImeas/RConn1', 'Load_const/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn2', 'Load_const/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn3', 'Load_const/LConn3', 'autorouting', 'smart');

% ===================================================================
% Block 7: LoadStep — Three-Phase Breaker + Three-Phase Series RLC Load
% Breaker closes at t=t_step, switches in 248 MW additional load
% ===================================================================
% Three-Phase Breaker (internal switch times mode, no External)
add_block('sps_lib/Power Grid Elements/Three-Phase Breaker', ...
    [mdl '/Breaker_step'], 'Position', [710 380 780 460]);
set_param([mdl '/Breaker_step'], 'InitialState', 'open', ...
    'SwitchA', 'on', 'SwitchB', 'on', 'SwitchC', 'on', ...
    'External', 'off', ...
    'SwitchTimes', '[LoadStep_t_s]');

add_block(load_path, [mdl '/Load_step'], 'Position', [820 380 890 460]);
set_param([mdl '/Load_step'], 'Configuration', 'Y (grounded)', ...
    'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
    'ActivePower', 'LoadStep_amp_W', ...
    'InductivePower', '0', 'CapacitivePower', '0');

% Wire VImeas/RConn -> Breaker -> Load_step
add_line(mdl, 'VImeas/RConn1', 'Breaker_step/LConn1', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn2', 'Breaker_step/LConn2', 'autorouting', 'smart');
add_line(mdl, 'VImeas/RConn3', 'Breaker_step/LConn3', 'autorouting', 'smart');
add_line(mdl, 'Breaker_step/RConn1', 'Load_step/LConn1', 'autorouting', 'smart');
add_line(mdl, 'Breaker_step/RConn2', 'Load_step/LConn2', 'autorouting', 'smart');
add_line(mdl, 'Breaker_step/RConn3', 'Load_step/LConn3', 'autorouting', 'smart');

% ===================================================================
% Block 8: Pe computation (V·I sum from broadcast tags)
% ===================================================================
add_block('built-in/From', [mdl '/FromV'], 'Position', [780 580 820 600], ...
    'GotoTag', 'Vabc_VSG');
add_block('built-in/From', [mdl '/FromI'], 'Position', [780 620 820 640], ...
    'GotoTag', 'Iabc_VSG');

% Element-wise V*I (3-vector product), then sum 3 phases
add_block('built-in/Product', [mdl '/PeProd'], 'Position', [840 590 870 620], ...
    'Inputs', '2');
add_line(mdl, 'FromV/1', 'PeProd/1');
add_line(mdl, 'FromI/1', 'PeProd/2');

% Sum 3 phases — vector input collapsed to scalar
add_block('built-in/Sum', [mdl '/PeSum'], 'Position', [890 595 920 615], ...
    'IconShape', 'rectangular', 'Inputs', '+', ...
    'CollapseMode', 'All dimensions', 'CollapseDim', '1');
add_line(mdl, 'PeProd/1', 'PeSum/1');

% Scale to vsg-base pu (instantaneous P_3ph / VSG_SN)
add_block('built-in/Gain', [mdl '/Pe_pu'], 'Position', [940 595 980 615], ...
    'Gain', num2str(1.0/VSG_SN));
add_line(mdl, 'PeSum/1', 'Pe_pu/1');

% Optional: low-pass filter to smooth instantaneous (oscillates at 2x f_n)
% Use a simple discrete moving average via Transfer Fcn (1/(s+wn_filter))
% For now: feed raw Pe_pu directly to swing eq + log

% Pe ToWorkspace
add_block('simulink/Sinks/To Workspace', [mdl '/Pe_log'], ...
    'Position', [1000 595 1050 615], 'VariableName', 'Pe_ts', ...
    'SaveFormat', 'Timeseries');
add_line(mdl, 'Pe_pu/1', 'Pe_log/1');

% ===================================================================
% Block 9: Swing eq feedback
% ===================================================================
add_block('built-in/Constant', [mdl '/Pm_const'], ...
    'Position', [200 440 230 460], 'Value', 'Pm_pu_vsg');
add_block('built-in/Gain', [mdl '/Dgain'], ...
    'Position', [320 470 360 490], 'Gain', 'D_vsg');
add_line(mdl, 'SumDw/1', 'Dgain/1');

add_block('built-in/Sum', [mdl '/SumSwing'], ...
    'Position', [330 425 360 480], 'Inputs', '+--');
add_line(mdl, 'Pm_const/1', 'SumSwing/1');
add_line(mdl, 'Pe_pu/1', 'SumSwing/2');
add_line(mdl, 'Dgain/1', 'SumSwing/3');

add_block('built-in/Gain', [mdl '/Mgain'], ...
    'Position', [370 425 400 445], 'Gain', '1/M_vsg');
add_line(mdl, 'SumSwing/1', 'Mgain/1');
add_line(mdl, 'Mgain/1', 'IntW/1');

% ===================================================================
% Block 10: Loggers
% ===================================================================
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
fprintf('RESULT: minimal_smib_discrete (all-SPS) built at %s\n', out_slx);
fprintf('RESULT: powergui mode = Discrete (SampleTime=50us)\n');
fprintf('RESULT: Pm_pu_vsg=%.3f, M=%.1f, D=%.1f\n', Pm0, M0, D0);
fprintf('RESULT: P_const=%g W, P_step=248e6 W at t=2s\n', P_const_W);

end
