function build_dynamic_source_discrete(mdl, src, geom, params)
%BUILD_DYNAMIC_SOURCE_DISCRETE  Add one Discrete-mode dynamic source closure.
%
% Phase 1.1 helper for build_kundur_cvs_v3_discrete.m. Encapsulates the
% per-source SMIB pattern validated by Phase 0 oracle 2026-05-03:
%
%   theta_<src> = wn·t + δ_<src>(t)   (δ from per-source IntD)
%   sin(theta + 0)        × Vpk → CVS_<src>_A → Y-bus phase A
%   sin(theta - 2π/3)     × Vpk → CVS_<src>_B → Y-bus phase B
%   sin(theta + 2π/3)     × Vpk → CVS_<src>_C → Y-bus phase C
%   3 single-phase CVS, neutral via common GND, RConn to Three-Phase V-I Meas
%   Pe = sum(Vabc .* Iabc) / Sbase   (instantaneous, 100 Hz oscillation)
%   Swing eq: M·dω/dt = Pm_total − Pe_src_pu − D·(ω−1)
%       SG:   Pm_total = (Pm_sys × SCvar) − (1/R)·(ω−1) + step
%       ESS:  Pm_total = (Pm_sys × SCvar) + step
%
% INPUT
% =====
% mdl    char    parent model name
% src    struct  per-source metadata:
%                .name (str)       e.g. 'ES1', 'G1'
%                .stype (str)      'sg' | 'ess'
%                .bus (int)        bus number (1..16)
%                .M_var (str)      workspace var name for M (= 2H)
%                .D_var (str)      workspace var name for D
%                .Pm_var (str)     workspace var name for Pm (sys-pu)
%                .delta0_var (str) workspace var name for δ0 (rad)
%                .Vmag_var (str)   workspace var name for V_emf (line-line peak ×Vbase scaling)
%                .scale_var (str)  workspace var name for SCvar (Sbase/Sn_src)
%                .Rdrop_var (str)  governor droop var (SG only); '' for ESS
%                .Lint_H (double)  internal inductance (H)
%                .step_t_var (str) Pm step trigger time var
%                .step_amp_var (str) Pm step amplitude var
% geom   struct  layout/wiring:
%                .bx, .cy (int)    base x, y for block placement
%                .global_clock (str)  path to global Clock block (e.g. 'Clock_global')
%                .bus_anchor (str)    path to network bus block to wire RConn into
% params struct  global params:
%                .fn (Hz)          50
%                .wn (rad/s)       2π·fn
%                .Vbase (V)        230e3
%                .Sbase (W)        100e6
%
% OUTPUT (no return; mutates the model)
% =====================================
% Adds blocks under [mdl '/...'] with names suffixed by src.name. Connects
% RConn1 of all 3 CVS to a Three-Phase V-I Measurement; the V-I Measurement
% RConn1/2/3 are wired to bus_anchor (caller's responsibility to provide).
%
% Workspace contract: all *_var inputs are READ at compile time (Constant
% blocks reference them). Matching workspace assignments must exist in base
% workspace before this helper is called.
%
% Logger contract (matches v3 build for env compat):
%   ESS sources: VariableName uses int suffix (1..n_agents) per
%     slx_helpers/vsg_bridge contract: omega_ts_<idx>, delta_ts_<idx>, Pe_ts_<idx>
%   SG / wind sources: string suffix (omega_ts_G1 etc), diagnostic-only
%
% See: probes/kundur/spike/build_minimal_smib_discrete.m for the validated
% pattern, quality_reports/plans/2026-05-03_phase0_smib_discrete_verdict.md
% for the proof.

sname = src.name;
stype = src.stype;
bx    = geom.bx;
cy    = geom.cy;
fn    = params.fn;
wn    = params.wn;
Vbase = params.Vbase;
Sbase = params.Sbase;

% Vpk per-phase (line-to-neutral peak). Vmag_var stores V_emf_pu × Vbase
% (line-line RMS); convert to phase peak: × sqrt(2/3).
% We use a Gain block on top of the workspace var so the build is reentrant.
Vpk_factor = sqrt(2/3);

% ===================================================================
% SWING EQUATION (paradigm-independent, mirrors v3 lines ~620-720)
% ===================================================================

% --- Pm_step gating (per-source) ---
% gate = Clock >= step_t_var ; result × step_amp_var = step contribution
add_block('simulink/Sources/Constant', [mdl '/Pm_step_t_c_' sname], ...
    'Position', [bx-560 cy+130 bx-520 cy+150], 'Value', src.step_t_var);
add_block('simulink/Logic and Bit Operations/Relational Operator', ...
    [mdl '/GE_' sname], ...
    'Position', [bx-500 cy+115 bx-470 cy+145], 'Operator', '>=');
add_line(mdl, [geom.global_clock '/1'], ['GE_' sname '/1']);
add_line(mdl, ['Pm_step_t_c_' sname '/1'], ['GE_' sname '/2']);

add_block('simulink/Signal Attributes/Data Type Conversion', ...
    [mdl '/Cast_' sname], ...
    'Position', [bx-460 cy+115 bx-430 cy+140], 'OutDataTypeStr', 'double');
add_line(mdl, ['GE_' sname '/1'], ['Cast_' sname '/1']);

add_block('simulink/Sources/Constant', [mdl '/Pm_step_amp_c_' sname], ...
    'Position', [bx-460 cy+155 bx-420 cy+175], 'Value', src.step_amp_var);
add_block('simulink/Math Operations/Product', [mdl '/PmStepMul_' sname], ...
    'Position', [bx-410 cy+125 bx-385 cy+150], 'Inputs', '2');
add_line(mdl, ['Cast_' sname '/1'], ['PmStepMul_' sname '/1']);
add_line(mdl, ['Pm_step_amp_c_' sname '/1'], ['PmStepMul_' sname '/2']);

% Pm_src_pu = Pm_sys × SCvar (Pm_sys is sys-pu, SCvar = Sbase/Sn_src)
add_block('simulink/Sources/Constant', [mdl '/Pm_sys_c_' sname], ...
    'Position', [bx-450 cy+50 bx-410 cy+70], 'Value', src.Pm_var);
add_block('simulink/Sources/Constant', [mdl '/Sscale_c_' sname], ...
    'Position', [bx-450 cy+90 bx-410 cy+110], 'Value', src.scale_var);
add_block('simulink/Math Operations/Product', [mdl '/PmSrcPU_' sname], ...
    'Position', [bx-400 cy+60 bx-370 cy+90], 'Inputs', '2');
add_line(mdl, ['Pm_sys_c_' sname '/1'], ['PmSrcPU_' sname '/1']);
add_line(mdl, ['Sscale_c_' sname '/1'], ['PmSrcPU_' sname '/2']);

% Sum step + base Pm
add_block('simulink/Math Operations/Sum', [mdl '/PmTotal_' sname], ...
    'Position', [bx-360 cy+70 bx-330 cy+100], 'Inputs', '++');
add_line(mdl, ['PmSrcPU_' sname '/1'],  ['PmTotal_' sname '/1']);
add_line(mdl, ['PmStepMul_' sname '/1'], ['PmTotal_' sname '/2']);

% SG governor droop: subtract (1/R)·(ω−1) from Pm_total
if strcmp(stype, 'sg')
    add_block('simulink/Math Operations/Gain', [mdl '/InvR_' sname], ...
        'Position', [bx-310 cy+105 bx-280 cy+135], ...
        'Gain', ['1/' src.Rdrop_var]);
end

% ω integrator (IC = 1)
intW = ['IntW_' sname];
add_block('simulink/Continuous/Integrator', [mdl '/' intW], ...
    'Position', [bx-200 cy+40 bx-170 cy+70], 'InitialCondition', '1');

add_block('simulink/Sources/Constant', [mdl '/One_' sname], ...
    'Position', [bx-360 cy+10 bx-330 cy+30], 'Value', '1');
add_block('simulink/Math Operations/Sum', [mdl '/SumDw_' sname], ...
    'Position', [bx-300 cy+40 bx-270 cy+70], 'Inputs', '+-');
add_line(mdl, [intW '/1'], ['SumDw_' sname '/1']);
add_line(mdl, ['One_' sname '/1'], ['SumDw_' sname '/2']);

% D · (ω − 1)
add_block('simulink/Math Operations/Gain', [mdl '/Dgain_' sname], ...
    'Position', [bx-300 cy+100 bx-270 cy+120], 'Gain', src.D_var);
add_line(mdl, ['SumDw_' sname '/1'], ['Dgain_' sname '/1']);

% Build SwingSum input chain — differs by SG/ESS due to governor droop
if strcmp(stype, 'sg')
    add_line(mdl, ['SumDw_' sname '/1'], ['InvR_' sname '/1']);
    add_block('simulink/Math Operations/Sum', [mdl '/PmAfterDroop_' sname], ...
        'Position', [bx-220 cy+70 bx-190 cy+100], 'Inputs', '+-');
    add_line(mdl, ['PmTotal_' sname '/1'], ['PmAfterDroop_' sname '/1']);
    add_line(mdl, ['InvR_' sname '/1'],   ['PmAfterDroop_' sname '/2']);
    add_block('simulink/Math Operations/Sum', [mdl '/SwingSum_' sname], ...
        'Position', [bx-180 cy+50 bx-150 cy+110], 'Inputs', '+--');
    add_line(mdl, ['PmAfterDroop_' sname '/1'], ['SwingSum_' sname '/1']);
    add_line(mdl, ['Dgain_' sname '/1'],        ['SwingSum_' sname '/3']);
else
    add_block('simulink/Math Operations/Sum', [mdl '/SwingSum_' sname], ...
        'Position', [bx-260 cy+50 bx-230 cy+110], 'Inputs', '+--');
    add_line(mdl, ['PmTotal_' sname '/1'], ['SwingSum_' sname '/1']);
    add_line(mdl, ['Dgain_' sname '/1'],   ['SwingSum_' sname '/3']);
end
% Pe input wired below after Pe_pu computed.

% 1/M
add_block('simulink/Math Operations/Gain', [mdl '/Mgain_' sname], ...
    'Position', [bx-145 cy+50 bx-115 cy+70], 'Gain', ['1/' src.M_var]);
add_line(mdl, ['SwingSum_' sname '/1'], ['Mgain_' sname '/1']);
add_line(mdl, ['Mgain_' sname '/1'],     [intW '/1']);

% δ integrator (IC = delta0_var)
intD = ['IntD_' sname];
add_block('simulink/Math Operations/Gain', [mdl '/wnG_' sname], ...
    'Position', [bx-300 cy-50 bx-270 cy-25], 'Gain', 'wn_const');
add_line(mdl, ['SumDw_' sname '/1'], ['wnG_' sname '/1']);

add_block('simulink/Continuous/Integrator', [mdl '/' intD], ...
    'Position', [bx-200 cy-50 bx-170 cy-20], ...
    'InitialCondition', src.delta0_var);
add_line(mdl, ['wnG_' sname '/1'], [intD '/1']);

% ===================================================================
% PHASE 1 PATCH: theta = wn·t + δ → 3 sin signals → 3 single-phase CVS
% (replaces v3's cosD/sinD/VrG/ViG/RI2C → 1 CVS pattern)
% ===================================================================

% theta = wn·t + δ (δ from IntD)
add_block('simulink/Math Operations/Gain', [mdl '/wnt_' sname], ...
    'Position', [bx-130 cy-90 bx-100 cy-70], 'Gain', 'wn_const');
add_line(mdl, [geom.global_clock '/1'], ['wnt_' sname '/1']);

add_block('simulink/Math Operations/Sum', [mdl '/SumTheta_' sname], ...
    'Position', [bx-80 cy-70 bx-50 cy-50], 'Inputs', '++');
add_line(mdl, ['wnt_' sname '/1'], ['SumTheta_' sname '/1']);
add_line(mdl, [intD '/1'],         ['SumTheta_' sname '/2']);

% Per-phase phase shifts
add_block('simulink/Sources/Constant', [mdl '/PhaseB_' sname], ...
    'Position', [bx-80 cy-50 bx-50 cy-30], 'Value', num2str(-2*pi/3));
add_block('simulink/Sources/Constant', [mdl '/PhaseC_' sname], ...
    'Position', [bx-80 cy-30 bx-50 cy-10], 'Value', num2str(2*pi/3));

add_block('simulink/Math Operations/Sum', [mdl '/SumThetaB_' sname], ...
    'Position', [bx-30 cy-60 bx cy-40], 'Inputs', '++');
add_line(mdl, ['SumTheta_' sname '/1'], ['SumThetaB_' sname '/1']);
add_line(mdl, ['PhaseB_' sname '/1'],   ['SumThetaB_' sname '/2']);

add_block('simulink/Math Operations/Sum', [mdl '/SumThetaC_' sname], ...
    'Position', [bx-30 cy-40 bx cy-20], 'Inputs', '++');
add_line(mdl, ['SumTheta_' sname '/1'], ['SumThetaC_' sname '/1']);
add_line(mdl, ['PhaseC_' sname '/1'],   ['SumThetaC_' sname '/2']);

% sin blocks per phase
add_block('simulink/Math Operations/Trigonometric Function', ...
    [mdl '/SinA_' sname], 'Position', [bx+10 cy-80 bx+40 cy-60], 'Operator', 'sin');
add_block('simulink/Math Operations/Trigonometric Function', ...
    [mdl '/SinB_' sname], 'Position', [bx+10 cy-60 bx+40 cy-40], 'Operator', 'sin');
add_block('simulink/Math Operations/Trigonometric Function', ...
    [mdl '/SinC_' sname], 'Position', [bx+10 cy-40 bx+40 cy-20], 'Operator', 'sin');
add_line(mdl, ['SumTheta_' sname '/1'],  ['SinA_' sname '/1']);
add_line(mdl, ['SumThetaB_' sname '/1'], ['SinB_' sname '/1']);
add_line(mdl, ['SumThetaC_' sname '/1'], ['SinC_' sname '/1']);

% Vpk gain per phase (Vmag_var × sqrt(2/3))
% Vpk_<src>_<phase> = Vmag_var × Vpk_factor where Vpk_factor = sqrt(2/3)
% Vmag_var stores V_emf_pu × Vbase (line-line magnitude); convert to phase peak.
Vpk_expr = sprintf('%s * %.10g', src.Vmag_var, Vpk_factor);
add_block('simulink/Math Operations/Gain', [mdl '/VpkA_' sname], ...
    'Position', [bx+50 cy-80 bx+80 cy-60], 'Gain', Vpk_expr);
add_block('simulink/Math Operations/Gain', [mdl '/VpkB_' sname], ...
    'Position', [bx+50 cy-60 bx+80 cy-40], 'Gain', Vpk_expr);
add_block('simulink/Math Operations/Gain', [mdl '/VpkC_' sname], ...
    'Position', [bx+50 cy-40 bx+80 cy-20], 'Gain', Vpk_expr);
add_line(mdl, ['SinA_' sname '/1'], ['VpkA_' sname '/1']);
add_line(mdl, ['SinB_' sname '/1'], ['VpkB_' sname '/1']);
add_line(mdl, ['SinC_' sname '/1'], ['VpkC_' sname '/1']);

% 3 single-phase CVS (sps_lib/Sources/Controlled Voltage Source variant)
% Each takes a single signal input → produces 1 line voltage.
cvs_lib = 'spsControlledVoltageSourceLib/Controlled Voltage Source';
add_block(cvs_lib, [mdl '/CVS_' sname '_A'], 'Position', [bx+100 cy-95 bx+140 cy-65]);
set_param([mdl '/CVS_' sname '_A'], 'Initialize', 'on');
add_block(cvs_lib, [mdl '/CVS_' sname '_B'], 'Position', [bx+100 cy-55 bx+140 cy-25]);
set_param([mdl '/CVS_' sname '_B'], 'Initialize', 'on');
add_block(cvs_lib, [mdl '/CVS_' sname '_C'], 'Position', [bx+100 cy-15 bx+140 cy+15]);
set_param([mdl '/CVS_' sname '_C'], 'Initialize', 'on');

add_line(mdl, ['VpkA_' sname '/1'], ['CVS_' sname '_A/1']);
add_line(mdl, ['VpkB_' sname '/1'], ['CVS_' sname '_B/1']);
add_line(mdl, ['VpkC_' sname '/1'], ['CVS_' sname '_C/1']);

% Common neutral GND
add_block('powerlib/Elements/Ground', [mdl '/GND_neutral_' sname], ...
    'Position', [bx+100 cy+30 bx+140 cy+50]);
add_line(mdl, ['CVS_' sname '_A/LConn1'], ['GND_neutral_' sname '/LConn1'], 'autorouting', 'smart');
add_line(mdl, ['CVS_' sname '_B/LConn1'], ['GND_neutral_' sname '/LConn1'], 'autorouting', 'smart');
add_line(mdl, ['CVS_' sname '_C/LConn1'], ['GND_neutral_' sname '/LConn1'], 'autorouting', 'smart');

% Three-Phase V-I Measurement at terminal
% Note: per-source Vabc/Iabc tags used in Pe calc + downstream
vimeas = ['VImeas_' sname];
v_tag = ['Vabc_' sname];
i_tag = ['Iabc_' sname];
add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
    [mdl '/' vimeas], 'Position', [bx+170 cy-95 bx+240 cy+15]);
set_param([mdl '/' vimeas], 'VoltageMeasurement', 'phase-to-ground', ...
    'CurrentMeasurement', 'yes', ...
    'SetLabelV', 'on', 'LabelV', v_tag, ...
    'SetLabelI', 'on', 'LabelI', i_tag);

add_line(mdl, ['CVS_' sname '_A/RConn1'], [vimeas '/LConn1'], 'autorouting', 'smart');
add_line(mdl, ['CVS_' sname '_B/RConn1'], [vimeas '/LConn2'], 'autorouting', 'smart');
add_line(mdl, ['CVS_' sname '_C/RConn1'], [vimeas '/LConn3'], 'autorouting', 'smart');

% Caller wires vimeas RConn1/2/3 → bus_anchor (caller's responsibility).

% ===================================================================
% PHASE 1 PATCH: Pe = sum(Vabc .* Iabc) / Sbase  (instantaneous)
% (replaces v3's Complex-to-Real-Imag → Vr·Ir + Vi·Ii pattern)
% ===================================================================

add_block('built-in/From', [mdl '/FromV_' sname], ...
    'Position', [bx+260 cy+110 bx+300 cy+130], 'GotoTag', v_tag);
add_block('built-in/From', [mdl '/FromI_' sname], ...
    'Position', [bx+260 cy+140 bx+300 cy+160], 'GotoTag', i_tag);

% Element-wise V·I (3-vector product)
add_block('simulink/Math Operations/Product', [mdl '/PeProd_' sname], ...
    'Position', [bx+320 cy+115 bx+350 cy+145], 'Inputs', '2');
add_line(mdl, ['FromV_' sname '/1'], ['PeProd_' sname '/1']);
add_line(mdl, ['FromI_' sname '/1'], ['PeProd_' sname '/2']);

% Sum 3 phases (collapse vector to scalar)
add_block('simulink/Math Operations/Sum', [mdl '/PeSum_' sname], ...
    'Position', [bx+370 cy+120 bx+400 cy+140], ...
    'IconShape', 'rectangular', 'Inputs', '+', ...
    'CollapseMode', 'All dimensions', 'CollapseDim', '1');
add_line(mdl, ['PeProd_' sname '/1'], ['PeSum_' sname '/1']);

% Scale W → sys-pu
add_block('simulink/Math Operations/Gain', [mdl '/Pe_pu_' sname], ...
    'Position', [bx+410 cy+120 bx+450 cy+140], 'Gain', 'Pe_scale');
add_line(mdl, ['PeSum_' sname '/1'], ['Pe_pu_' sname '/1']);

% Convert to source-base pu: Pe_src_pu = Pe_sys_pu × SCvar
add_block('simulink/Math Operations/Product', [mdl '/PeSrcPU_' sname], ...
    'Position', [bx-100 cy+135 bx-70 cy+165], 'Inputs', '2');
add_block('simulink/Sources/Constant', [mdl '/SCvar_c_' sname], ...
    'Position', [bx-130 cy+170 bx-100 cy+190], 'Value', src.scale_var);
add_line(mdl, ['Pe_pu_' sname '/1'],  ['PeSrcPU_' sname '/1']);
add_line(mdl, ['SCvar_c_' sname '/1'], ['PeSrcPU_' sname '/2']);

% Wire converted Pe into SwingSum/2 (the negative input we left dangling earlier)
add_line(mdl, ['PeSrcPU_' sname '/1'], ['SwingSum_' sname '/2'], 'autorouting', 'smart');

% ===================================================================
% Loggers (unchanged from v3 contract — bridge expects integer suffix on ESS)
% ===================================================================
if strcmp(stype, 'ess')
    ess_idx = sscanf(sname, 'ES%d');
    var_omega = sprintf('omega_ts_%d', ess_idx);
    var_delta = sprintf('delta_ts_%d', ess_idx);
    var_pe    = sprintf('Pe_ts_%d',    ess_idx);
else
    var_omega = sprintf('omega_ts_%s', sname);
    var_delta = sprintf('delta_ts_%s', sname);
    var_pe    = sprintf('Pe_ts_%s',    sname);
end

add_block('simulink/Sinks/To Workspace', [mdl '/W_omega_' sname], ...
    'Position', [bx-150 cy+45 bx-110 cy+60], ...
    'VariableName', var_omega, 'SaveFormat', 'Timeseries', 'MaxDataPoints', '2');
add_line(mdl, [intW '/1'], ['W_omega_' sname '/1']);

add_block('simulink/Sinks/To Workspace', [mdl '/W_delta_' sname], ...
    'Position', [bx-150 cy-45 bx-110 cy-30], ...
    'VariableName', var_delta, 'SaveFormat', 'Timeseries', 'MaxDataPoints', '2');
add_line(mdl, [intD '/1'], ['W_delta_' sname '/1']);

add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe_' sname], ...
    'Position', [bx+460 cy+125 bx+500 cy+145], ...
    'VariableName', var_pe, 'SaveFormat', 'Timeseries', 'MaxDataPoints', '2');
add_line(mdl, ['Pe_pu_' sname '/1'], ['W_Pe_' sname '/1']);

end
