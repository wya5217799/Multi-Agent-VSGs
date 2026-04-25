function build_kundur_cvs()
% build_kundur_cvs  Stage 2 Day 1 — full 7-bus Kundur CVS Phasor topology.
%
% Purpose: upgrade the P1/P2 simplified BUS_left—L_tie—BUS_right layout to
% the paper Sec.IV-A modified Kundur two-area topology with 4 VSGs, 2 area
% junctions (with loads), and 1 AC infinite bus anchor. 7 buses total.
%
% Day 1 is a STRUCTURE-ONLY gate (no swing-equation closure). All driven
% CVS inputs are static RI2C(constant Vr, constant Vi) so we can verify
% compile + 0.5s sim purely on the network topology before D2 adds the
% formal NR initial condition and D3+ adds dynamics.
%
% Bus map (7 buses, paper Sec.IV-A "Fig.3" reference; numerical bus IDs
% chosen for this CVS path and recorded in the verdict report):
%   Bus_V1 : VSG1 terminal, area 1   (driven CVS, Source_Type=DC, Init=off)
%   Bus_V2 : VSG2 terminal, area 1   (driven CVS)
%   Bus_V3 : VSG3 terminal, area 2   (driven CVS)
%   Bus_V4 : VSG4 terminal, area 2   (driven CVS)
%   Bus_A  : area 1 junction          (Load_A, R-only constant impedance)
%   Bus_B  : area 2 junction          (Load_B, R-only constant impedance)
%   Bus_INF: system anchor            (powerlib AC Voltage Source)
%
% Branches (single-phase phasor, all inductive):
%   L_v1: Bus_V1 -- Bus_A      (VSG1 step-up + tie to area junction)
%   L_v2: Bus_V2 -- Bus_A
%   L_v3: Bus_V3 -- Bus_B
%   L_v4: Bus_V4 -- Bus_B
%   L_tie:  Bus_A -- Bus_B     (weak inter-area link, X_tie_pu=0.30)
%   L_inf:  Bus_B -- Bus_INF   (short anchor link, X_inf_pu=0.05)
%
% Engineering contracts honored (cvs_design.md):
%   H1  driven CVS: Source_Type=DC, Initialize=off, Measurements=None
%   H2  CVS input  : RI2C(double real, double imag)  -- ALL 4 VSGs uniform
%   H3  inf-bus    : powerlib/Electrical Sources/AC Voltage Source (no inport)
%   H4  solver     : powergui Phasor 50 Hz, ode23t, MaxStep=0.005
%   H5  base ws    : every numeric value forced to double()
%   D-CVS-9/10/11  : DC + Initialize=off; AC src for inf-bus; double types
%
% NOT in scope for Day 1 (deferred to D2/D3+):
%   - Swing equation (IntW/IntD/cosD/sinD/Pe-feedback) — D2 will add NR IC
%   - Newton-Raphson power flow init — D2
%   - 30 s zero-action stability gate — D3 (Gate 1)
%   - Disturbance sweep — D4 (Gate 2)
%
% References:
%   probes/kundur/gates/build_kundur_cvs_p1.m   (4-CVS structural template)
%   probes/kundur/gates/build_kundur_cvs_p2.m   (4-VSG swing-eq template)
%   docs/design/cvs_design.md                   (engineering contract)
%   docs/paper/yang2023-fact-base.md            (Sec.IV-A topology)

mdl = 'kundur_cvs';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

% ---- Physical parameters (force double per H5) ----
fn       = 50;
wn       = double(2*pi*fn);
Sbase    = double(100e6);
Vbase    = double(230e3);
Zbase    = double(Vbase^2 / Sbase);

X_v_pu   = 0.10;     % VSG step-up + short feeder to area junction
X_tie_pu = 0.30;     % weak inter-area tie (Bus_A <-> Bus_B)
X_inf_pu = 0.05;     % strong anchor (Bus_B <-> Bus_INF)

L_v_H    = double(X_v_pu   * Zbase / wn);
L_tie_H  = double(X_tie_pu * Zbase / wn);
L_inf_H  = double(X_inf_pu * Zbase / wn);

% ---- Load resistances (constant impedance, R-only single-phase) ----
% Load_A on Bus_A: 0.4 pu absorbed at nominal voltage
% Load_B on Bus_B: 0.4 pu absorbed at nominal voltage
% R = V^2 / P (single-phase peak phasor at Vbase, Sbase pu base).
P_loadA_pu = 0.4;
P_loadB_pu = 0.4;
R_loadA    = double(Vbase^2 / (P_loadA_pu * Sbase));   % Ohm
R_loadB    = double(Vbase^2 / (P_loadB_pu * Sbase));   % Ohm

% ---- Per-VSG fixed-source angle / magnitude for D1 structural test ----
% Day 1 only: small differentiated angles, magnitudes near Vbase. D2 will
% replace these with NR-derived (delta0_i, V_i) pulled from kundur_ic_cvs.json.
delta0_default = double(asin(0.5 * X_v_pu));   % ~0.05 rad (SMIB approx)
delta0_rad = double([+delta0_default, +delta0_default*0.8, ...
                     -delta0_default*0.8, -delta0_default]);
v_mag      = double([1.0, 0.999, 1.001, 0.998]) * Vbase;

% ---- Reset model ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% ---- powergui Phasor (H4) ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

% ---- Push base ws scalars (H5: every value forced double) ----
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'L_v_H',       double(L_v_H));
assignin('base', 'L_tie_H',     double(L_tie_H));
assignin('base', 'L_inf_H',     double(L_inf_H));
assignin('base', 'R_loadA',     double(R_loadA));
assignin('base', 'R_loadB',     double(R_loadB));

% ---- Inter-area tie L_tie: Bus_A (LConn1) <-> Bus_B (RConn1) ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_tie'], ...
    'Position', [780 360 840 410]);
set_param([mdl '/L_tie'], 'BranchType', 'L', 'Inductance', 'L_tie_H');

% ---- Anchor link L_inf: Bus_B (LConn1) <-> Bus_INF (RConn1) ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_inf'], ...
    'Position', [900 360 960 410]);
set_param([mdl '/L_inf'], 'BranchType', 'L', 'Inductance', 'L_inf_H');

% ---- Bus_INF: AC Voltage Source (D-CVS-10) ----
add_block('powerlib/Electrical Sources/AC Voltage Source', ...
    [mdl '/AC_INF'], 'Position', [1020 360 1080 410]);
set_param([mdl '/AC_INF'], 'Amplitude', num2str(Vbase), ...
    'Phase', '0', 'Frequency', '50');
add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
    'Position', [1020 440 1060 470]);
add_line(mdl, 'AC_INF/RConn1', 'L_inf/RConn1', 'autorouting', 'smart');
add_line(mdl, 'AC_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');

% ---- Connect L_tie/RConn1 to L_inf/LConn1 (= Bus_B node) ----
add_line(mdl, 'L_tie/RConn1', 'L_inf/LConn1', 'autorouting', 'smart');

% ---- Load_A on Bus_A (R-only, between Bus_A node and ground) ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Load_A'], ...
    'Position', [700 460 760 510]);
set_param([mdl '/Load_A'], 'BranchType', 'R', 'Resistance', 'R_loadA');
add_block('powerlib/Elements/Ground', [mdl '/GND_LA'], ...
    'Position', [700 530 740 560]);
add_line(mdl, 'Load_A/RConn1', 'GND_LA/LConn1', 'autorouting', 'smart');
add_line(mdl, 'L_tie/LConn1',  'Load_A/LConn1', 'autorouting', 'smart');

% ---- Load_B on Bus_B (R-only, between Bus_B node and ground) ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/Load_B'], ...
    'Position', [880 460 940 510]);
set_param([mdl '/Load_B'], 'BranchType', 'R', 'Resistance', 'R_loadB');
add_block('powerlib/Elements/Ground', [mdl '/GND_LB'], ...
    'Position', [880 530 920 560]);
add_line(mdl, 'Load_B/RConn1', 'GND_LB/LConn1', 'autorouting', 'smart');
add_line(mdl, 'L_tie/RConn1',  'Load_B/LConn1', 'autorouting', 'smart');

% ---- 4 driven CVSs: VSG1,VSG2 -> Bus_A ; VSG3,VSG4 -> Bus_B ----
% Layout:
%   row i = 1..4: cy = 80 + (i-1)*150
%   columns: Vr/Vi const (180..220) -> RI2C (260..300) -> CVS (400..460)
%            -> L_v (500..560) -> Bus_A (i<=2) or Bus_B (i>=3)
for i = 1:4
    cy   = 80 + (i-1)*150;
    cvs  = sprintf('CVS_VSG%d', i);
    gnd  = sprintf('GND_VSG%d', i);
    Vr_b = sprintf('Vr_%d', i);
    Vi_b = sprintf('Vi_%d', i);
    ri2c = sprintf('RI2C_%d', i);
    Lv   = sprintf('L_v_%d', i);

    % --- Constants for V_r, V_i (H5 double; H2 RI2C path) ---
    Vr_val = double(v_mag(i) * cos(delta0_rad(i)));
    Vi_val = double(v_mag(i) * sin(delta0_rad(i)));

    add_block('built-in/Constant', [mdl '/' Vr_b], ...
        'Position', [180 cy 220 cy+15], 'Value', num2str(Vr_val));
    add_block('built-in/Constant', [mdl '/' Vi_b], ...
        'Position', [180 cy+25 220 cy+40], 'Value', num2str(Vi_val));
    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/' ri2c], 'Position', [260 cy 300 cy+30]);
    add_line(mdl, [Vr_b '/1'], [ri2c '/1']);
    add_line(mdl, [Vi_b '/1'], [ri2c '/2']);

    % --- Driven CVS (H1: DC + Initialize=off) ---
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/' cvs], 'Position', [400 cy 460 cy+50]);
    set_param([mdl '/' cvs], ...
        'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '0', ...
        'Measurements', 'None');
    add_line(mdl, [ri2c '/1'], [cvs '/1']);

    % --- VSG ground on CVS LConn1 ---
    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [400 cy+60 440 cy+90]);
    add_line(mdl, [cvs '/LConn1'], [gnd '/LConn1'], 'autorouting', 'smart');

    % --- L_v: CVS RConn1 -> Bus_A (i<=2) or Bus_B (i>=3) ---
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lv], ...
        'Position', [500 cy 560 cy+30]);
    set_param([mdl '/' Lv], 'BranchType', 'L', 'Inductance', 'L_v_H');
    add_line(mdl, [cvs '/RConn1'], [Lv '/LConn1'], 'autorouting', 'smart');

    if i <= 2
        % VSG1, VSG2 -> Bus_A (= L_tie/LConn1 node)
        add_line(mdl, [Lv '/RConn1'], 'L_tie/LConn1', 'autorouting', 'smart');
    else
        % VSG3, VSG4 -> Bus_B (= L_tie/RConn1 node)
        add_line(mdl, [Lv '/RConn1'], 'L_tie/RConn1', 'autorouting', 'smart');
    end
end

% ---- Save ----
save_system(mdl, out_slx);

fprintf('RESULT: kundur_cvs.slx saved at %s\n', out_slx);
fprintf('RESULT: 7-bus topology = {Bus_V1..V4 (driven CVS), Bus_A, Bus_B, Bus_INF}\n');
fprintf('RESULT: branches L_v1..v4, L_tie, L_inf; loads R-only on Bus_A and Bus_B\n');
fprintf('RESULT: X_v=%.4f X_tie=%.4f X_inf=%.4f pu (single-phase phasor)\n', ...
    X_v_pu, X_tie_pu, X_inf_pu);
fprintf('RESULT: R_loadA=%.2f R_loadB=%.2f Ohm (P_loadA=P_loadB=%.2f pu)\n', ...
    R_loadA, R_loadB, P_loadA_pu);

end
