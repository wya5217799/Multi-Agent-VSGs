function build_kundur_cvs_p1()
% build_kundur_cvs_p1  Gate P1 — 4-CVS structure-only model.
%
% Purpose: verify that 4 SPS native Controlled Voltage Sources can be
% wired in a Kundur-like inter-area topology under powergui Phasor mode,
% with all input signals as fixed complex constants (no swing eq yet).
% This gate proves the 4-CVS structural compatibility before any
% swing-equation closure is attempted (Gate P2).
%
% Topology (reduced 4-VSG inter-area):
%   CVS_VSG1, CVS_VSG2 -- L_left -- BUS_left -- L_tie -- BUS_right
%       \-- GND                                   \-- L_right -- CVS_VSG3, CVS_VSG4
%       \-- AC_INF (one fixed AC inf-bus reference at BUS_left to anchor frame)
%
% For Gate P1, all CVS inputs are constant complex values from RI2C blocks
% (no IntD/IntW/swing eq) — pure structural / compile / static-sim test.
%
% Contract refs:
%   - cvs_design.md §1 H1-H6 (CVS config, signal type, FR, double types)
%   - Pre-Flight Q1 (mcp_q1_4cvs PASS)

mdl = 'kundur_cvs_p1';
out_dir = fileparts(mfilename('fullpath'));
out_slx = fullfile(out_dir, [mdl '.slx']);

% ---- Force base ws doubles ----
fn = 50;
wn = 2*pi*fn;
Sbase = 100e6;
Vbase = 230e3;
X_line_pu = 0.10;
X_tie_pu  = 0.30;
L_line_H = double(X_line_pu * Vbase^2 / Sbase / wn);
L_tie_H  = double(X_tie_pu  * Vbase^2 / Sbase / wn);

% Per-VSG nominal phase offsets (deg) — small, just to differentiate
phases_deg = double([0.0, -0.5, +0.5, -0.3]);
mags       = double([1.0, 0.999, 1.001, 0.998]);

% ---- Reset model ----
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% ---- powergui Phasor (H4) ----
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

% ---- Two buses connected by L_tie, plus AC inf-bus anchored to BUS_left ----
add_block('powerlib/Elements/Series RLC Branch', [mdl '/L_tie'], ...
    'Position', [600 200 660 250]);
set_param([mdl '/L_tie'], 'BranchType', 'L', 'Inductance', num2str(L_tie_H));

% AC inf-bus anchors BUS_left (D-CVS-10: fixed AC source, not driven CVS)
add_block('powerlib/Electrical Sources/AC Voltage Source', ...
    [mdl '/AC_INF'], 'Position', [500 320 560 380]);
set_param([mdl '/AC_INF'], 'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '50');

add_block('powerlib/Elements/Ground', [mdl '/GND_INF'], ...
    'Position', [500 410 540 440]);

% ---- 4 CVS, each through its own L to its bus ----
% VSG1, VSG2 → BUS_left (= L_tie/LConn1)
% VSG3, VSG4 → BUS_right (= L_tie/RConn1)
for i = 1:4
    cy = 80 + (i-1)*120;
    cvs   = sprintf('CVS_VSG%d', i);
    Vr_b  = sprintf('Vr_%d', i);
    Vi_b  = sprintf('Vi_%d', i);
    ri2c  = sprintf('RI2C_%d', i);
    Lline = sprintf('L_line_%d', i);
    gnd   = sprintf('GND_%d', i);

    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/' cvs], 'Position', [400 cy 460 cy+50]);
    % H1: Source_Type=DC + Initialize=off
    set_param([mdl '/' cvs], ...
        'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', num2str(Vbase), 'Phase', '0', 'Frequency', '0', ...
        'Measurements', 'None');

    % H2: Vr/Vi constants (double) → RI2C → CVS inport
    Vr_val = double(mags(i) * Vbase * cos(phases_deg(i)*pi/180));
    Vi_val = double(mags(i) * Vbase * sin(phases_deg(i)*pi/180));

    add_block('built-in/Constant', [mdl '/' Vr_b], ...
        'Position', [180 cy 220 cy+15], 'Value', num2str(Vr_val));
    add_block('built-in/Constant', [mdl '/' Vi_b], ...
        'Position', [180 cy+20 220 cy+35], 'Value', num2str(Vi_val));
    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/' ri2c], 'Position', [260 cy 300 cy+30]);

    add_line(mdl, [Vr_b '/1'], [ri2c '/1']);
    add_line(mdl, [Vi_b '/1'], [ri2c '/2']);
    add_line(mdl, [ri2c '/1'], [cvs '/1']);

    % L_line between CVS RConn and bus
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lline], ...
        'Position', [500 cy 540 cy+30]);
    set_param([mdl '/' Lline], 'BranchType', 'L', 'Inductance', num2str(L_line_H));
    add_line(mdl, [cvs '/RConn1'], [Lline '/LConn1'], 'autorouting', 'smart');

    % VSG1, VSG2 → L_tie/LConn1; VSG3, VSG4 → L_tie/RConn1
    if i <= 2
        add_line(mdl, [Lline '/RConn1'], 'L_tie/LConn1', 'autorouting', 'smart');
    else
        add_line(mdl, [Lline '/RConn1'], 'L_tie/RConn1', 'autorouting', 'smart');
    end

    % CVS LConn1 to its own ground
    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [400 cy+60 440 cy+90]);
    add_line(mdl, [cvs '/LConn1'], [gnd '/LConn1'], 'autorouting', 'smart');
end

% Anchor AC_INF to BUS_left so frame is well-defined
add_line(mdl, 'AC_INF/RConn1', 'L_tie/LConn1', 'autorouting', 'smart');
add_line(mdl, 'AC_INF/LConn1', 'GND_INF/LConn1', 'autorouting', 'smart');

% ---- Save ----
save_system(mdl, out_slx);
fprintf('RESULT: kundur_cvs_p1 built at %s\n', out_slx);
fprintf('RESULT: 4 CVS + 1 AC_INF + L_tie + 4 L_line + 5 GND structural model saved\n');

end
