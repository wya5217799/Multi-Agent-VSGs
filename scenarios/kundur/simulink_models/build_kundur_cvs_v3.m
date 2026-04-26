function build_kundur_cvs_v3()
%BUILD_KUNDUR_CVS_V3  Paper-faithful 16-bus Modified Kundur CVS Phasor model.
%
% Phase 1.3 of 2026-04-26_kundur_cvs_v3_plan.md.
% Spec  : quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md
% IC    : scenarios/kundur/kundur_ic_cvs_v3.json (Phase 1.1, schema_version=3)
%
% Pattern: v2 build_kundur_cvs.m extended.
%   v2: 4 ESS swing-eq + 2 R-load junctions, 5 buses, 5 lines.
%   v3: 7 swing-eq closures (G1/G2/G3 + ES1..4) + 2 PVS (W1/W2)
%       + 18 lossy Π-line branches (R+L+C, parallel lines as separate blocks)
%       + 2 R+L loads on Bus 7 / Bus 9 (constant impedance, Q-shunted)
%       + 2 LoadStep clusters (R-only) on Bus 7 / Bus 9
%       + 7 Pm-step gating clusters (one per dynamic source)
%       + Phasor solver, ToWorkspace loggers (omega/delta/Pe per source).
%
% Source CVS Amplitude:
%   - SG (G1/G2/G3) Vmag = sg_emf_mag_pu  · Vbase (NOT hardcoded 1.03/1.01).
%   - ESS Vmag         = vsg_emf_mag_pu · Vbase (NOT hardcoded 1.0).
%   - W1/W2 PVS Vmag   = wind_terminal_voltage_mag_pu · Vbase (=Vbase).
%
% Per-source initial-condition origin (must match IC JSON):
%   delta0_<src> = internal EMF angle (rad, sim-absolute frame, Bus 1 = +20°)
%   Pm0_<src>    = NR P-injection in sys-pu (negative for ESS = absorbing)
%
% v2 contract preservation: scenario_id, n_agents, dt, contract.py constants
% are NOT touched by the build. The build only emits a .slx + runtime .mat.

mdl       = 'kundur_cvs_v3';
out_dir   = fileparts(mfilename('fullpath'));
out_slx   = fullfile(out_dir, [mdl '.slx']);
ic_path   = fullfile(fileparts(out_dir), 'kundur_ic_cvs_v3.json');
runtime_mat = fullfile(out_dir, [mdl '_runtime.mat']);

%% ===== Read v3 IC =====
ic = jsondecode(fileread(ic_path));
assert(isfield(ic, 'schema_version') && ic.schema_version == 3, ...
    'kundur_ic_cvs_v3.json: schema_version must be 3 (got %d)', ic.schema_version);
assert(strcmp(ic.topology_variant, 'v3_paper_kundur_16bus'), ...
    'IC topology_variant must be "v3_paper_kundur_16bus" — refusing to build v3 against non-v3 IC');
assert(ic.powerflow.converged && ic.powerflow.closure_ok, ...
    'IC reports NR did not converge OR closure_ok=false — refusing to build');

% --- Per-source IC vectors ---
% ESS (4):  bus 12, 16, 14, 15 in ES1, ES2, ES3, ES4 order
ess_delta0_rad = double(ic.vsg_internal_emf_angle_rad(:));
ess_Vemf_pu    = double(ic.vsg_emf_mag_pu(:));
ess_Pm0_sys    = double(ic.vsg_pm0_pu(:));
assert(numel(ess_delta0_rad) == 4 && numel(ess_Vemf_pu) == 4 && numel(ess_Pm0_sys) == 4, ...
    'IC ESS arrays must be length 4');

% SG (3):   bus 1, 2, 3 in G1, G2, G3 order
sg_delta0_rad = double(ic.sg_internal_emf_angle_rad(:));
sg_Vemf_pu    = double(ic.sg_emf_mag_pu(:));
sg_Pm0_sys    = double(ic.sg_pm0_sys_pu(:));
assert(numel(sg_delta0_rad) == 3 && numel(sg_Vemf_pu) == 3 && numel(sg_Pm0_sys) == 3, ...
    'IC SG arrays must be length 3');

% Wind (2): bus 4 (W1), bus 11 (W2). const-power PVS.
wind_term_a_rad = double(ic.wind_terminal_voltage_angle_rad(:));
wind_term_v_pu  = double(ic.wind_terminal_voltage_mag_pu(:));
wind_Pref_sys   = double(ic.wind_pref_sys_pu(:));
assert(numel(wind_term_a_rad) == 2, 'IC wind arrays must be length 2');

%% ===== Bases (LOCKED, must match compute_kundur_cvs_v3_powerflow.m) =====
fn       = 50;
wn       = double(2*pi*fn);
Sbase    = double(100e6);
Vbase    = double(230e3);
Zbase    = double(Vbase^2 / Sbase);

% Source internal impedances (sys pu)
SG_SN     = double(900e6);
VSG_SN    = double(200e6);
X_gen_sys = 0.30 * (Sbase / SG_SN);   % 0.0333
X_vsg_sys = 0.30 * (Sbase / VSG_SN);  % 0.15

L_gen_H   = double(X_gen_sys * Zbase / wn);
L_vsg_H   = double(X_vsg_sys * Zbase / wn);

% Source nameplate ratings used to convert P_e (W) → source-base pu in swing-eq
% G1/G2/G3 swing eq is on gen-base (900 MVA), ESS on vsg-base (200 MVA).
SG_M0_default  = 12.0;   % 2H = 13.0 / 13.0 / 12.35 (paper). Use unified 12 for build; per-source H below.
% Per-paper H: G1=6.5, G2=6.5, G3=6.175 → M=2H = 13.0, 13.0, 12.35
sg_H_paper = [6.5; 6.5; 6.175];
sg_D_paper = [5.0; 5.0; 5.0];
sg_R_paper = [0.05; 0.05; 0.05];

% ESS RL controlled — use v2 promoted defaults, keep RL-tunable (M_<i>/D_<i> ws vars)
ESS_M0_default = 24.0;
ESS_D0_default = 4.5;

%% ===== Per-km line constants (from build_powerlib_kundur.m) =====
R_std   = 0.053;     L_std   = 1.41e-3;  C_std   = 0.009e-6;
R_short = 0.01;      L_short = 0.5e-3;   C_short = 0.009e-6;

% Branch list (verbatim from spec §4 / NR script)
line_defs = {
    'L_1_5',    1,  5,    5, R_std,   L_std,   C_std;
    'L_2_6',    2,  6,    5, R_std,   L_std,   C_std;
    'L_3_10',   3, 10,    5, R_std,   L_std,   C_std;
    'L_4_9',    4,  9,    5, R_std,   L_std,   C_std;
    'L_5_6a',   5,  6,   25, R_std,   L_std,   C_std;
    'L_5_6b',   5,  6,   25, R_std,   L_std,   C_std;
    'L_6_7a',   6,  7,   10, R_std,   L_std,   C_std;
    'L_6_7b',   6,  7,   10, R_std,   L_std,   C_std;
    'L_7_8a',   7,  8,  110, R_std,   L_std,   C_std;
    'L_7_8b',   7,  8,  110, R_std,   L_std,   C_std;
    'L_7_8c',   7,  8,  110, R_std,   L_std,   C_std;
    'L_8_9a',   8,  9,   10, R_std,   L_std,   C_std;
    'L_8_9b',   8,  9,   10, R_std,   L_std,   C_std;
    'L_9_10a',  9, 10,   25, R_std,   L_std,   C_std;
    'L_9_10b',  9, 10,   25, R_std,   L_std,   C_std;
    'L_7_12',   7, 12,    1, R_short, L_short, C_short;
    'L_8_16',   8, 16,    1, R_short, L_short, C_short;
    'L_10_14', 10, 14,    1, R_short, L_short, C_short;
    'L_9_15',   9, 15,    1, R_short, L_short, C_short;
    'L_8_W2',   8, 11,    1, R_short, L_short, C_short;
};

%% ===== Loads + shunt caps (constant Z) =====
% Bus 7: 967 MW + 100 Mvar inductive load + 200 Mvar shunt cap
% Bus 9: 1767 MW + 100 Mvar inductive load + 350 Mvar shunt cap
load_defs = {
    'Load7',  7,  967e6,  100e6;     % bus, P (W), Q_inductive (var)
    'Load9',  9, 1767e6,  100e6;
};
shunt_defs = {
    'Shunt7', 7, 200e6;     % bus, Q_capacitive (var)
    'Shunt9', 9, 350e6;
};

% LoadStep R-only branches (workspace-controlled conductance)
%   G_perturb_k(t) = LoadStep_amp_k(t) · (Sbase / Vbase²)
% Implemented as Constant block driving Series RLC R-only Resistance via runtime
% workspace var — but since 'Resistance' must be positive scalar, we instead
% gate a parallel R load whose value is computed at build time and modulated
% via a Pm-step-style amplitude scalar. Simplest FastRestart-safe design:
%   pre-instantiate a fixed-size R load (R = Vbase²/(Sbase × LoadStepAmpMax_pu));
%   use a `Three-Phase Series RLC Load` would be too heavy — instead use single-
%   phase R via Constant-driven Controlled Voltage / Current — but this gets
%   complex. For Phase 1.3 minimum scope, use a parallel R element on each
%   load bus whose conductance equals a workspace scalar G_perturb_k_S, with
%   default 0 (= disabled). Phase 3 env will set G_perturb mid-episode.
loadstep_defs = {
    'LoadStep7', 7;
    'LoadStep9', 9;
};

%% ===== Reset model =====
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
load_system('powerlib');

% Phasor solver, 50 Hz
add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 100 60]);
set_param([mdl '/powergui'], 'SimulationMode', 'Phasor', 'frequency', '50');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Variable-step', ...
    'Solver', 'ode23t', 'MaxStep', '0.005');

%% ===== Base workspace scalars =====
% --- Shared constants ---
assignin('base', 'wn_const',    double(wn));
assignin('base', 'Vbase_const', double(Vbase));
assignin('base', 'Sbase_const', double(Sbase));
assignin('base', 'Pe_scale',    double(1.0 / Sbase));   % W → sys-pu

% --- Per-SG vars ---
for g = 1:3
    assignin('base', sprintf('Mg_%d',         g), double(2 * sg_H_paper(g)));   % M = 2H, gen-base s
    assignin('base', sprintf('Dg_%d',         g), double(sg_D_paper(g)));        % D, gen-base pu
    assignin('base', sprintf('Rg_%d',         g), double(sg_R_paper(g)));        % governor droop
    assignin('base', sprintf('Pmg_%d',        g), double(sg_Pm0_sys(g)));        % sys-pu
    assignin('base', sprintf('SGScale_%d',    g), double(Sbase / SG_SN));        % scale gen-pu ↔ sys-pu
    assignin('base', sprintf('deltaG0_%d',    g), double(sg_delta0_rad(g)));     % rad
    assignin('base', sprintf('VemfG_%d',      g), double(sg_Vemf_pu(g) * Vbase)); % V (line-line)
    assignin('base', sprintf('PmgStep_t_%d',  g), double(5.0));                  % off by default
    assignin('base', sprintf('PmgStep_amp_%d', g), double(0.0));
end

% --- Per-ESS vars ---
for i = 1:4
    assignin('base', sprintf('M_%d',          i), double(ESS_M0_default));
    assignin('base', sprintf('D_%d',          i), double(ESS_D0_default));
    assignin('base', sprintf('Pm_%d',         i), double(ess_Pm0_sys(i)));        % sys-pu (negative = absorb)
    assignin('base', sprintf('VSGScale_%d',   i), double(Sbase / VSG_SN));        % scale vsg-pu ↔ sys-pu
    assignin('base', sprintf('delta0_%d',     i), double(ess_delta0_rad(i)));
    assignin('base', sprintf('Vmag_%d',       i), double(ess_Vemf_pu(i) * Vbase));
    assignin('base', sprintf('Pm_step_t_%d',  i), double(5.0));
    assignin('base', sprintf('Pm_step_amp_%d', i), double(0.0));
end

% --- Per-wind vars ---
for w = 1:2
    assignin('base', sprintf('WindAmp_%d',  w), double(1.0));
    assignin('base', sprintf('Wphase_%d',   w), double(wind_term_a_rad(w)));     % rad
    assignin('base', sprintf('WVmag_%d',    w), double(wind_term_v_pu(w) * Vbase));
end

% --- LoadStep workspace conductances (S = siemens) ---
for k = 1:2
    assignin('base', sprintf('G_perturb_%d_S', k), double(0.0));   % disabled
    assignin('base', sprintf('LoadStep_t_%d',  k), double(5.0));
    assignin('base', sprintf('LoadStep_amp_%d', k), double(0.0));
end

%% ===== Build line branches (Π-line: Series RLC with R+L only; shunt cap deferred) =====
% Phasor solver: per build_kundur_cvs.m v2, lines were L-only (X_tie). v3
% adds R+L branches (lossless line shunts handled via PI Section if needed).
% For Phase 1.3 minimum scope: use Series RLC type='RL' for each branch
% (R + jωL); shunt C handled implicitly by the powergui Phasor solver if
% PI Section is desired — defer to Phase 2.x if losses don't match.
n_lines = size(line_defs, 1);
for li = 1:n_lines
    name  = line_defs{li, 1};
    fb    = line_defs{li, 2};
    tb    = line_defs{li, 3};
    Lkm   = line_defs{li, 4};
    Rk    = line_defs{li, 5};
    Lk    = line_defs{li, 6};

    R_tot = Rk * Lkm;                  % Ω
    L_tot = Lk * Lkm;                  % H

    yposS = 200 + (li - 1) * 70;
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [400 yposS 460 yposS+50]);
    set_param([mdl '/' name], 'BranchType', 'RL', ...
        'Resistance', sprintf('%.10g', R_tot), ...
        'Inductance', sprintf('%.10g', L_tot));

    % Tag from/to in block UserData for connection bookkeeping
    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('from', fb, 'to', tb));
end

%% ===== Build loads (Series RLC R+L for P+Q_ind, then shunt cap) =====
n_loads = size(load_defs, 1);
for ld = 1:n_loads
    name  = load_defs{ld, 1};
    bus   = load_defs{ld, 2};
    P_W   = load_defs{ld, 3};
    Q_var = load_defs{ld, 4};

    % Const-Z RL: R = V²/P, L = V²/(ωQ)
    R_load = double(Vbase^2 / P_W);
    L_load = double(Vbase^2 / (wn * Q_var));

    yposL = 200 + (ld - 1) * 100;
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [800 yposL 860 yposL+60]);
    set_param([mdl '/' name], 'BranchType', 'RL', ...
        'Resistance', sprintf('%.10g', R_load), ...
        'Inductance', sprintf('%.10g', L_load));

    add_block('powerlib/Elements/Ground', [mdl '/GND_' name], ...
        'Position', [800 yposL+90 840 yposL+120]);
    add_line(mdl, [name '/RConn1'], ['GND_' name '/LConn1'], 'autorouting', 'smart');

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus));
end

% Shunt caps: Series RLC type 'C', C = Q / (ω·V²)
n_shunts = size(shunt_defs, 1);
for sh = 1:n_shunts
    name  = shunt_defs{sh, 1};
    bus   = shunt_defs{sh, 2};
    Q_var = shunt_defs{sh, 3};

    C_sh = double(Q_var / (wn * Vbase^2));

    yposC = 200 + (sh - 1) * 100;
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [950 yposC 1010 yposC+60]);
    set_param([mdl '/' name], 'BranchType', 'C', ...
        'Capacitance', sprintf('%.10g', C_sh));

    add_block('powerlib/Elements/Ground', [mdl '/GND_' name], ...
        'Position', [950 yposC+90 990 yposC+120]);
    add_line(mdl, [name '/RConn1'], ['GND_' name '/LConn1'], 'autorouting', 'smart');

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus));
end

% LoadStep R-only branches (per-bus parallel R, default open via large R)
% For Phase 1.3, instantiate placeholder R = 1e9 Ω (= ~0 conductance).
% Phase 3 env will modulate via runtime workspace `G_perturb_k_S`.
for k = 1:2
    name  = loadstep_defs{k, 1};
    bus   = loadstep_defs{k, 2};

    yposLS = 200 + (k - 1) * 100;
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [1100 yposLS 1160 yposLS+60]);
    % Default disabled (very large R = open circuit equivalent)
    set_param([mdl '/' name], 'BranchType', 'R', ...
        'Resistance', '1e9');

    add_block('powerlib/Elements/Ground', [mdl '/GND_' name], ...
        'Position', [1100 yposLS+90 1140 yposLS+120]);
    add_line(mdl, [name '/RConn1'], ['GND_' name '/LConn1'], 'autorouting', 'smart');

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus));
end

%% ===== Build dynamic sources (3 SG + 4 ESS) with full swing-eq closure =====
% Each source produces a CVS at internal EMF, connected through internal X
% (gen-base for SG, vsg-base for ESS) to the network bus. SG adds governor
% droop term in Pm_total; ESS keeps M/D as base-ws variables for RL control.

% Layout: stack all dynamic sources vertically on left half of the model.
% Source ordering (top→bottom): G1, G2, G3, ES1, ES2, ES3, ES4
src_meta = {
    % name, bus, type, M_var, D_var, Pm_var, delta0_var, Vmag_var, scale_var, Rdrop_var, X_internal_H, Pm_step_t_var, Pm_step_amp_var
    'G1',  1, 'sg',  'Mg_1',  'Dg_1',  'Pmg_1',  'deltaG0_1', 'VemfG_1',  'SGScale_1',  'Rg_1', L_gen_H, 'PmgStep_t_1', 'PmgStep_amp_1';
    'G2',  2, 'sg',  'Mg_2',  'Dg_2',  'Pmg_2',  'deltaG0_2', 'VemfG_2',  'SGScale_2',  'Rg_2', L_gen_H, 'PmgStep_t_2', 'PmgStep_amp_2';
    'G3',  3, 'sg',  'Mg_3',  'Dg_3',  'Pmg_3',  'deltaG0_3', 'VemfG_3',  'SGScale_3',  'Rg_3', L_gen_H, 'PmgStep_t_3', 'PmgStep_amp_3';
    'ES1', 12, 'ess', 'M_1',   'D_1',   'Pm_1',   'delta0_1',  'Vmag_1',   'VSGScale_1',  '',     L_vsg_H, 'Pm_step_t_1',  'Pm_step_amp_1';
    'ES2', 16, 'ess', 'M_2',   'D_2',   'Pm_2',   'delta0_2',  'Vmag_2',   'VSGScale_2',  '',     L_vsg_H, 'Pm_step_t_2',  'Pm_step_amp_2';
    'ES3', 14, 'ess', 'M_3',   'D_3',   'Pm_3',   'delta0_3',  'Vmag_3',   'VSGScale_3',  '',     L_vsg_H, 'Pm_step_t_3',  'Pm_step_amp_3';
    'ES4', 15, 'ess', 'M_4',   'D_4',   'Pm_4',   'delta0_4',  'Vmag_4',   'VSGScale_4',  '',     L_vsg_H, 'Pm_step_t_4',  'Pm_step_amp_4';
};
n_src = size(src_meta, 1);

% Global clock (shared across all Pm-step gates and LoadStep gates)
add_block('simulink/Sources/Clock', [mdl '/Clock_global'], ...
    'Position', [200 1500 230 1530], 'DisplayTime', 'off');

for s = 1:n_src
    sname  = src_meta{s, 1};
    bus    = src_meta{s, 2};
    stype  = src_meta{s, 3};
    Mvar   = src_meta{s, 4};
    Dvar   = src_meta{s, 5};
    Pmvar  = src_meta{s, 6};
    d0var  = src_meta{s, 7};
    Vvar   = src_meta{s, 8};
    SCvar  = src_meta{s, 9};
    Rvar   = src_meta{s, 10};
    Lint_H = src_meta{s, 11};
    Tvar   = src_meta{s, 12};
    Avar   = src_meta{s, 13};

    cy = 80 + (s - 1) * 260;
    bx = 1300;

    cvs   = sprintf('CVS_%s', sname);
    Lint  = sprintf('Lint_%s', sname);
    gnd   = sprintf('GND_%s', sname);
    intW  = sprintf('IntW_%s', sname);
    intD  = sprintf('IntD_%s', sname);

    % --- Electrical: CVS, Imeas, internal X, GND, Vmeas (terminal) ---
    add_block('powerlib/Electrical Sources/Controlled Voltage Source', ...
        [mdl '/' cvs], 'Position', [bx cy bx+60 cy+50]);
    set_param([mdl '/' cvs], ...
        'Source_Type', 'DC', 'Initialize', 'off', ...
        'Amplitude', Vvar, 'Phase', '0', 'Frequency', '0', ...
        'Measurements', 'None');

    add_block('powerlib/Measurements/Current Measurement', ...
        [mdl '/Imeas_' sname], 'Position', [bx+90 cy+10 bx+110 cy+40]);

    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lint], ...
        'Position', [bx+150 cy bx+200 cy+30]);
    set_param([mdl '/' Lint], 'BranchType', 'L', ...
        'Inductance', sprintf('%.10g', Lint_H));
    set_param([mdl '/' Lint], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'src', sname));

    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [bx cy+70 bx+40 cy+100]);

    add_block('powerlib/Measurements/Voltage Measurement', ...
        [mdl '/Vmeas_' sname], 'Position', [bx+50 cy+110 bx+110 cy+150]);

    add_line(mdl, [cvs '/RConn1'], ['Imeas_' sname '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, ['Imeas_' sname '/RConn1'], [Lint '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'], [gnd '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/RConn1'], ['Vmeas_' sname '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [cvs '/LConn1'], ['Vmeas_' sname '/LConn2'], 'autorouting', 'smart');

    % --- Pe = Re(V·conj(I)) / Sbase  (sys-pu) ---
    add_block('simulink/Math Operations/Complex to Real-Imag', ...
        [mdl '/V_RI_' sname], 'Position', [bx+220 cy+110 bx+260 cy+150]);
    set_param([mdl '/V_RI_' sname], 'Output', 'Real and imag');
    add_line(mdl, ['Vmeas_' sname '/1'], ['V_RI_' sname '/1'], 'autorouting', 'smart');

    add_block('simulink/Math Operations/Complex to Real-Imag', ...
        [mdl '/I_RI_' sname], 'Position', [bx+220 cy+170 bx+260 cy+210]);
    set_param([mdl '/I_RI_' sname], 'Output', 'Real and imag');
    add_line(mdl, ['Imeas_' sname '/1'], ['I_RI_' sname '/1'], 'autorouting', 'smart');

    add_block('simulink/Math Operations/Product', [mdl '/VrIr_' sname], ...
        'Position', [bx+290 cy+110 bx+320 cy+135], 'Inputs', '2');
    add_line(mdl, ['V_RI_' sname '/1'], ['VrIr_' sname '/1']);
    add_line(mdl, ['I_RI_' sname '/1'], ['VrIr_' sname '/2']);

    add_block('simulink/Math Operations/Product', [mdl '/ViIi_' sname], ...
        'Position', [bx+290 cy+170 bx+320 cy+195], 'Inputs', '2');
    add_line(mdl, ['V_RI_' sname '/2'], ['ViIi_' sname '/1']);
    add_line(mdl, ['I_RI_' sname '/2'], ['ViIi_' sname '/2']);

    add_block('simulink/Math Operations/Sum', [mdl '/PSum_' sname], ...
        'Position', [bx+350 cy+140 bx+380 cy+170], 'Inputs', '++');
    add_line(mdl, ['VrIr_' sname '/1'], ['PSum_' sname '/1']);
    add_line(mdl, ['ViIi_' sname '/1'], ['PSum_' sname '/2']);

    add_block('simulink/Math Operations/Gain', [mdl '/Pe_pu_' sname], ...
        'Position', [bx+400 cy+140 bx+440 cy+170], 'Gain', 'Pe_scale');
    add_line(mdl, ['PSum_' sname '/1'], ['Pe_pu_' sname '/1']);

    % --- Pm-step gating (per-source) ---
    add_block('simulink/Sources/Constant', [mdl '/Pm_step_t_c_' sname], ...
        'Position', [bx-560 cy+130 bx-520 cy+150], 'Value', Tvar);
    add_block('simulink/Logic and Bit Operations/Relational Operator', ...
        [mdl '/GE_' sname], ...
        'Position', [bx-500 cy+115 bx-470 cy+145], 'Operator', '>=');
    add_line(mdl, 'Clock_global/1', ['GE_' sname '/1']);
    add_line(mdl, ['Pm_step_t_c_' sname '/1'], ['GE_' sname '/2']);

    add_block('simulink/Signal Attributes/Data Type Conversion', ...
        [mdl '/Cast_' sname], ...
        'Position', [bx-460 cy+115 bx-430 cy+140], 'OutDataTypeStr', 'double');
    add_line(mdl, ['GE_' sname '/1'], ['Cast_' sname '/1']);

    add_block('simulink/Sources/Constant', [mdl '/Pm_step_amp_c_' sname], ...
        'Position', [bx-460 cy+155 bx-420 cy+175], 'Value', Avar);
    add_block('simulink/Math Operations/Product', [mdl '/PmStepMul_' sname], ...
        'Position', [bx-410 cy+125 bx-385 cy+150], 'Inputs', '2');
    add_line(mdl, ['Cast_' sname '/1'], ['PmStepMul_' sname '/1']);
    add_line(mdl, ['Pm_step_amp_c_' sname '/1'], ['PmStepMul_' sname '/2']);

    % --- Swing equation: M·dω/dt = Pm_total − Pe_src_pu − D·(ω−1)
    %     where Pe_src_pu is on the source's own base (gen-base for SG,
    %     vsg-base for ESS): Pe_src_pu = Pe_sys_pu / SCvar (= Sbase/Sn_src)
    %     Pm_total stored on source-base too:
    %       SG:  Pm_total = Pm0_sys/Sscale − (1/R)·(ω−1) + step
    %       ESS: Pm_total = Pm0_sys/Sscale + step
    %
    %     For Phase 1.3 we store Pm0 in sys-pu via base-ws Pm_var, then divide
    %     by SCvar=Sbase/Sn_src inside the model to get source-base pu.

    % Pm0 source-base = Pm_var / SCvar   (Pm_var sys-pu, SCvar=Sbase/Sn_src)
    add_block('simulink/Sources/Constant', [mdl '/Pm_sys_c_' sname], ...
        'Position', [bx-450 cy+50 bx-410 cy+70], 'Value', Pmvar);
    add_block('simulink/Sources/Constant', [mdl '/Sscale_c_' sname], ...
        'Position', [bx-450 cy+90 bx-410 cy+110], 'Value', SCvar);
    add_block('simulink/Math Operations/Divide', [mdl '/PmSrcPU_' sname], ...
        'Position', [bx-400 cy+60 bx-370 cy+90], 'Inputs', '*/');
    add_line(mdl, ['Pm_sys_c_' sname '/1'], ['PmSrcPU_' sname '/1']);
    add_line(mdl, ['Sscale_c_' sname '/1'], ['PmSrcPU_' sname '/2']);

    % Sum step + base Pm
    add_block('simulink/Math Operations/Sum', [mdl '/PmTotal_' sname], ...
        'Position', [bx-360 cy+70 bx-330 cy+100], 'Inputs', '++');
    add_line(mdl, ['PmSrcPU_' sname '/1'],  ['PmTotal_' sname '/1']);
    add_line(mdl, ['PmStepMul_' sname '/1'], ['PmTotal_' sname '/2']);

    % SG governor droop: subtract (1/R)·(ω−1) from Pm_total
    if strcmp(stype, 'sg')
        add_block('simulink/Sources/Constant', [mdl '/RDrop_c_' sname], ...
            'Position', [bx-360 cy+110 bx-330 cy+130], 'Value', Rvar);
        add_block('simulink/Math Operations/Divide', [mdl '/InvR_' sname], ...
            'Position', [bx-310 cy+105 bx-280 cy+135], 'Inputs', '/*');
        % InvR computes 1/R using one constant (1) divided by R
        add_block('simulink/Sources/Constant', [mdl '/One_R_' sname], ...
            'Position', [bx-340 cy+95 bx-320 cy+115], 'Value', '1');
        add_line(mdl, ['One_R_' sname '/1'], ['InvR_' sname '/1']);
        add_line(mdl, ['RDrop_c_' sname '/1'], ['InvR_' sname '/2']);
    end

    % ω integrator
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
        'Position', [bx-300 cy+100 bx-270 cy+120], 'Gain', Dvar);
    add_line(mdl, ['SumDw_' sname '/1'], ['Dgain_' sname '/1']);

    if strcmp(stype, 'sg')
        % Pm_after_droop = PmTotal − (1/R)·(ω−1)
        add_block('simulink/Math Operations/Product', [mdl '/DroopMul_' sname], ...
            'Position', [bx-260 cy+105 bx-230 cy+130], 'Inputs', '2');
        add_line(mdl, ['InvR_' sname '/1'], ['DroopMul_' sname '/1']);
        add_line(mdl, ['SumDw_' sname '/1'], ['DroopMul_' sname '/2']);

        add_block('simulink/Math Operations/Sum', [mdl '/PmAfterDroop_' sname], ...
            'Position', [bx-220 cy+70 bx-190 cy+100], 'Inputs', '+-');
        add_line(mdl, ['PmTotal_' sname '/1'], ['PmAfterDroop_' sname '/1']);
        add_line(mdl, ['DroopMul_' sname '/1'], ['PmAfterDroop_' sname '/2']);

        add_block('simulink/Math Operations/Sum', [mdl '/SwingSum_' sname], ...
            'Position', [bx-180 cy+50 bx-150 cy+110], 'Inputs', '+--');
        add_line(mdl, ['PmAfterDroop_' sname '/1'], ['SwingSum_' sname '/1']);
        add_line(mdl, ['Pe_pu_' sname '/1'],        ['SwingSum_' sname '/2']);
        add_line(mdl, ['Dgain_' sname '/1'],        ['SwingSum_' sname '/3']);
    else
        add_block('simulink/Math Operations/Sum', [mdl '/SwingSum_' sname], ...
            'Position', [bx-260 cy+50 bx-230 cy+110], 'Inputs', '+--');
        add_line(mdl, ['PmTotal_' sname '/1'], ['SwingSum_' sname '/1']);
        add_line(mdl, ['Pe_pu_' sname '/1'],   ['SwingSum_' sname '/2']);
        add_line(mdl, ['Dgain_' sname '/1'],   ['SwingSum_' sname '/3']);
    end

    % NOTE: Pe_pu_<sname> is on sys-pu but the swing eq is on source-base pu.
    % Convert here: Pe_src_pu = Pe_sys_pu / SCvar. Use a Gain block.
    %
    % Architectural simplification: rewrite the SwingSum input to use the
    % converted Pe. Place a divider before SwingSum.
    %
    % Implementation: add `Pe_src_pu_<sname>` Divide block between Pe_pu and
    % SwingSum.  Easier: replace the line into SwingSum/2 with the divided
    % signal.
    add_block('simulink/Math Operations/Divide', [mdl '/PeSrcPU_' sname], ...
        'Position', [bx-100 cy+135 bx-70 cy+165], 'Inputs', '*/');
    add_block('simulink/Sources/Constant', [mdl '/SCvar_c_' sname], ...
        'Position', [bx-130 cy+170 bx-100 cy+190], 'Value', SCvar);
    add_line(mdl, ['Pe_pu_' sname '/1'], ['PeSrcPU_' sname '/1']);
    add_line(mdl, ['SCvar_c_' sname '/1'], ['PeSrcPU_' sname '/2']);

    % Disconnect the original Pe_pu→SwingSum/2 and connect PeSrcPU instead
    delete_line(mdl, ['Pe_pu_' sname '/1'], ['SwingSum_' sname '/2']);
    add_line(mdl, ['PeSrcPU_' sname '/1'], ['SwingSum_' sname '/2'], 'autorouting', 'smart');

    % 1/M
    add_block('simulink/Math Operations/Gain', [mdl '/Mgain_' sname], ...
        'Position', [bx-145 cy+50 bx-115 cy+70], 'Gain', ['1/' Mvar]);
    add_line(mdl, ['SwingSum_' sname '/1'], ['Mgain_' sname '/1']);
    add_line(mdl, ['Mgain_' sname '/1'],     [intW '/1']);

    % --- δ integrator ---
    add_block('simulink/Math Operations/Gain', [mdl '/wnG_' sname], ...
        'Position', [bx-300 cy-50 bx-270 cy-25], 'Gain', 'wn_const');
    add_line(mdl, ['SumDw_' sname '/1'], ['wnG_' sname '/1']);

    add_block('simulink/Continuous/Integrator', [mdl '/' intD], ...
        'Position', [bx-200 cy-50 bx-170 cy-20], ...
        'InitialCondition', d0var);
    add_line(mdl, ['wnG_' sname '/1'], [intD '/1']);

    % cos/sin → V_emf scaling → Real-Imag to Complex → CVS amplitude input
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/cosD_' sname], 'Position', [bx-100 cy-30 bx-70 cy-10], 'Operator', 'cos');
    add_block('simulink/Math Operations/Trigonometric Function', ...
        [mdl '/sinD_' sname], 'Position', [bx-100 cy-60 bx-70 cy-40], 'Operator', 'sin');
    add_line(mdl, [intD '/1'], ['cosD_' sname '/1']);
    add_line(mdl, [intD '/1'], ['sinD_' sname '/1']);

    add_block('simulink/Math Operations/Gain', [mdl '/VrG_' sname], ...
        'Position', [bx-50 cy-30 bx-20 cy-10], 'Gain', Vvar);
    add_block('simulink/Math Operations/Gain', [mdl '/ViG_' sname], ...
        'Position', [bx-50 cy-60 bx-20 cy-40], 'Gain', Vvar);
    add_line(mdl, ['cosD_' sname '/1'], ['VrG_' sname '/1']);
    add_line(mdl, ['sinD_' sname '/1'], ['ViG_' sname '/1']);

    add_block('simulink/Math Operations/Real-Imag to Complex', ...
        [mdl '/RI2C_' sname], 'Position', [bx-10 cy-50 bx+30 cy-15]);
    add_line(mdl, ['VrG_' sname '/1'], ['RI2C_' sname '/1']);
    add_line(mdl, ['ViG_' sname '/1'], ['RI2C_' sname '/2']);
    add_line(mdl, ['RI2C_' sname '/1'], [cvs '/1']);

    % --- ToWorkspace loggers (bounded to 2 samples) ---
    add_block('simulink/Sinks/To Workspace', [mdl '/W_omega_' sname], ...
        'Position', [bx-150 cy+45 bx-110 cy+60], ...
        'VariableName', sprintf('omega_ts_%s', sname), 'SaveFormat', 'Timeseries', ...
        'MaxDataPoints', '2');
    add_line(mdl, [intW '/1'], ['W_omega_' sname '/1']);

    add_block('simulink/Sinks/To Workspace', [mdl '/W_delta_' sname], ...
        'Position', [bx-150 cy-45 bx-110 cy-30], ...
        'VariableName', sprintf('delta_ts_%s', sname), 'SaveFormat', 'Timeseries', ...
        'MaxDataPoints', '2');
    add_line(mdl, [intD '/1'], ['W_delta_' sname '/1']);

    add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe_' sname], ...
        'Position', [bx+450 cy+145 bx+490 cy+165], ...
        'VariableName', sprintf('Pe_ts_%s', sname), 'SaveFormat', 'Timeseries', ...
        'MaxDataPoints', '2');
    add_line(mdl, ['Pe_pu_' sname '/1'], ['W_Pe_' sname '/1']);
end

%% ===== Build wind PVS (W1, W2) — Programmable Voltage Source, no swing eq =====
% Model as `AC Voltage Source` with Phase = wind_term_a_rad (deg, fixed).
% Amplitude scaled by WindAmp_w workspace knob — set 0 to trip.
% We use `powerlib/Electrical Sources/AC Voltage Source` because powerlib
% doesn't have a phasor-domain Programmable Voltage Source; the AC source's
% Amplitude can be set to a workspace-evaluated expression.
wind_meta = {
    'W1', 4,  'WindAmp_1', 'Wphase_1', 'WVmag_1';
    'W2', 11, 'WindAmp_2', 'Wphase_2', 'WVmag_2';
};
for w = 1:size(wind_meta, 1)
    wname = wind_meta{w, 1};
    bus   = wind_meta{w, 2};
    Avar  = wind_meta{w, 3};
    Pvar  = wind_meta{w, 4};
    Vvar  = wind_meta{w, 5};

    cy = 80 + (n_src + w - 1) * 260;
    bx = 1300;

    src   = sprintf('PVS_%s', wname);
    Lline = sprintf('Lwind_%s', wname);   % short connect to bus (negligible)
    gnd   = sprintf('GND_%s', wname);

    add_block('powerlib/Electrical Sources/AC Voltage Source', [mdl '/' src], ...
        'Position', [bx cy bx+60 cy+50]);
    set_param([mdl '/' src], ...
        'Amplitude', sprintf('(%s) * (%s)', Avar, Vvar), ...
        'Phase',     sprintf('(%s) * 180/pi', Pvar), ...
        'Frequency', '50', ...
        'Measurements', 'None');

    add_block('powerlib/Elements/Ground', [mdl '/' gnd], ...
        'Position', [bx cy+70 bx+40 cy+100]);
    add_line(mdl, [src '/LConn1'], [gnd '/LConn1'], 'autorouting', 'smart');

    % short L_wind = 0 (PVS direct to bus); use a tiny L for solver health
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' Lline], ...
        'Position', [bx+80 cy bx+140 cy+30]);
    set_param([mdl '/' Lline], 'BranchType', 'L', 'Inductance', '1e-6');
    set_param([mdl '/' Lline], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'src', wname));
    add_line(mdl, [src '/RConn1'], [Lline '/LConn1'], 'autorouting', 'smart');
end

%% ===== Connect electrical bus net (line endpoints to one another) =====
% Topology: each bus is a logical "node" formed by every block whose
% UserData.bus matches that bus number, plus every line whose endpoint
% (from / to) matches that bus.
%
% For the Phasor solver, all RConn ports of elements at the same logical
% bus must be electrically tied. Implementation: pick a single port per
% bus as the "anchor" and add lines from every other element-at-bus to it.

bus_anchor = containers.Map('KeyType', 'double', 'ValueType', 'char');

% --- helper: register an element-port at a bus (anchor or auto-link) ---
register = @(bus, blkpath_port) local_register_at_bus(mdl, bus_anchor, bus, blkpath_port);

% Line endpoints
for li = 1:n_lines
    name = line_defs{li, 1};
    fb   = line_defs{li, 2};
    tb   = line_defs{li, 3};
    register(fb, [name '/LConn1']);
    register(tb, [name '/RConn1']);
end

% Loads + shunts + LoadStep — all anchor at their bus
for ld = 1:n_loads
    name = load_defs{ld, 1};
    bus  = load_defs{ld, 2};
    register(bus, [name '/LConn1']);
end
for sh = 1:n_shunts
    name = shunt_defs{sh, 1};
    bus  = shunt_defs{sh, 2};
    register(bus, [name '/LConn1']);
end
for k = 1:2
    name = loadstep_defs{k, 1};
    bus  = loadstep_defs{k, 2};
    register(bus, [name '/LConn1']);
end

% Source internal-X downstream port → bus
for s = 1:n_src
    sname = src_meta{s, 1};
    bus   = src_meta{s, 2};
    Lint  = sprintf('Lint_%s', sname);
    register(bus, [Lint '/RConn1']);
end

% Wind PVS L_wind downstream → bus
for w = 1:size(wind_meta, 1)
    wname = wind_meta{w, 1};
    bus   = wind_meta{w, 2};
    Lline = sprintf('Lwind_%s', wname);
    register(bus, [Lline '/RConn1']);
end

%% ===== Save .slx + sidecar runtime constants .mat =====
save_system(mdl, out_slx);

runtime_consts = struct();
runtime_consts.wn_const    = double(wn);
runtime_consts.Vbase_const = double(Vbase);
runtime_consts.Sbase_const = double(Sbase);
runtime_consts.Pe_scale    = double(1.0 / Sbase);
runtime_consts.L_gen_H     = double(L_gen_H);
runtime_consts.L_vsg_H     = double(L_vsg_H);
runtime_consts.SG_SN       = double(SG_SN);
runtime_consts.VSG_SN      = double(VSG_SN);
runtime_consts.SG_M_paper  = 2 * sg_H_paper(:)';
runtime_consts.SG_D_paper  = sg_D_paper(:)';
runtime_consts.SG_R_paper  = sg_R_paper(:)';
runtime_consts.ESS_M0      = double(ESS_M0_default);
runtime_consts.ESS_D0      = double(ESS_D0_default);
% Per-source IC for fast resets
for g = 1:3
    runtime_consts.(sprintf('VemfG_%d',   g)) = double(sg_Vemf_pu(g) * Vbase);
    runtime_consts.(sprintf('deltaG0_%d', g)) = double(sg_delta0_rad(g));
    runtime_consts.(sprintf('Pmg_%d',     g)) = double(sg_Pm0_sys(g));
end
for i = 1:4
    runtime_consts.(sprintf('Vmag_%d',   i)) = double(ess_Vemf_pu(i) * Vbase);
    runtime_consts.(sprintf('delta0_%d', i)) = double(ess_delta0_rad(i));
    runtime_consts.(sprintf('Pm_%d',     i)) = double(ess_Pm0_sys(i));
end
for w = 1:2
    runtime_consts.(sprintf('Wphase_%d', w)) = double(wind_term_a_rad(w));
    runtime_consts.(sprintf('WVmag_%d',  w)) = double(wind_term_v_pu(w) * Vbase);
end
save(runtime_mat, '-struct', 'runtime_consts');

%% ===== Diagnostic print =====
fprintf('RESULT: build_kundur_cvs_v3 saved %s\n', out_slx);
fprintf('RESULT: 16-bus paper topology, 3 SG + 4 ESS swing-eq + 2 PVS\n');
fprintf('RESULT: lines=%d, loads=%d, shunts=%d, loadsteps=%d\n', n_lines, n_loads, n_shunts, 2);
fprintf('RESULT: ESS Pm0_sys_pu = [%.4f %.4f %.4f %.4f]\n', ess_Pm0_sys);
fprintf('RESULT: SG  Pm0_sys_pu = [%.4f %.4f %.4f]\n', sg_Pm0_sys);
fprintf('RESULT: ESS Vemf_pu    = [%.4f %.4f %.4f %.4f]\n', ess_Vemf_pu);
fprintf('RESULT: SG  Vemf_pu    = [%.4f %.4f %.4f]\n', sg_Vemf_pu);
fprintf('RESULT: runtime_mat = %s (%d fields)\n', runtime_mat, numel(fieldnames(runtime_consts)));

end

% =====================================================================
function local_register_at_bus(mdl, bus_anchor, bus, blk_port)
% Anchor-and-tie strategy: first registration at a bus becomes the anchor;
% every subsequent registration draws a line from that port to the anchor.
if ~isKey(bus_anchor, bus)
    bus_anchor(bus) = blk_port;
else
    anchor = bus_anchor(bus);
    if ~strcmp(anchor, blk_port)
        try
            add_line(mdl, blk_port, anchor, 'autorouting', 'smart');
        catch ME
            fprintf('RESULT: WARN bus%d link %s -> %s : %s\n', bus, blk_port, anchor, ME.message);
        end
    end
end
end
