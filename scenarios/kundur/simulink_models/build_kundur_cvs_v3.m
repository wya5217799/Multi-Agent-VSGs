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
assert(strcmp(ic.topology_variant, 'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged'), ...
    'IC topology_variant must be "v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged" — refusing to build v3 against non-v3 IC (Task 1: W2 → Bus 8; Task 2: Bus 14 LS1 248 MW pre-engaged)');
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

% Wind (2): bus 4 (W1), bus 8 (W2). const-power PVS.
%   Task 1 (2026-04-28): W2 moved from bus 11 to bus 8 directly per
%   paper line 894 ("100 MW wind farm is connected to bus 8"). bus 11
%   intermediary node + L_8_W2 short Pi-line removed.
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

% LoadStep — Variable Resistor wired to bus 14 / bus 15 (paper-aligned).
%
% Phase A (2026-04-27): replace v3-Phase1.3 dead `Resistance='1e9'` Series RLC
% pattern with a `powerlib/Elements/Variable Resistor` whose R is driven by
% a Constant block reading workspace var `LoadStep_amp_<bus_label>`:
%
%     R(t) = Vbase_const^2 / max(LoadStep_amp_<lb>, 1e-3)
%
% Default amp=0 ⇒ R = 230kV² / 1e-3 ≈ 5.29e13 Ω ≈ open. With amp=X W and V=230kV,
% the absorbed power = V²/R = X W, so amp directly = active-power demand.
%
% Tunability: Constant.Value re-evaluates per sim() chunk (env writes amp BEFORE
% the chunk that crosses t_step). Default amp=0 keeps NR powerflow unchanged
% (load is electrically absent at IC), so kundur_ic_cvs_v3.json / runtime.mat
% are NOT regenerated for this wiring change.
%
% Direction: step-on semantics (engage R load mid-episode). Frequency drops on
% activation. Paper LoadStep 1 (Bus 14 *trip* = freq rises) requires either
% pre-engaged load + NR re-derive, or controlled current source — deferred.
loadstep_defs = {
    'LoadStep_bus14', 14, 'bus14';   % paper Bus 14 ≈ v3 ESS bus 14 (near ES3)
    'LoadStep_bus15', 15, 'bus15';   % paper Bus 15 ≈ v3 ESS bus 15 (near ES4)
};

% Option E (2026-04-30): CCS at Bus 7 / Bus 9 — true network LoadStep at
% load center.  Reuses Phase A++ CCS Trip pattern (line ~365-425) but
% targets the actual paper-Fig.3 load buses (Bus 7 = 967 MW load, Bus 9 =
% 1767 MW load) instead of the ESS terminal buses (Bus 14/15) where the
% CCS Trip path gave only ~0.01 Hz signal due to electrical distance from
% load center. CCS injection at Bus 7/9 (where the 967+1767=2734 MW load
% lives) is the project's first true network-side disturbance with
% magnitude in the same ballpark as paper LoadStep 1 (248 MW reduction at
% Bus 14, paper Fig.3) and LoadStep 2 (188 MW increase at Bus 15).
%
% Convention: workspace var `CCS_Load_amp_bus<bus>` is in W (system base);
% positive amp = current INJECTION from GND→bus = generator-like = freq UP
% (mimics paper LoadStep "trip" semantics where load disconnects). Negative
% amp = current FROM bus→GND = additional load = freq DOWN (mimics paper
% LoadStep "engage" semantics).
%
% Default amp=0 ⇒ CCS electrically absent ⇒ NR / IC unaffected ⇒ no
% need to regenerate kundur_ic_cvs_v3.json.
ccs_load_defs = {
    'CCSLoad_bus7', 7, 'bus7';   % Bus 7 load center (967 MW load)
    'CCSLoad_bus9', 9, 'bus9';   % Bus 9 load center (1767 MW load)
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

% --- LoadStep workspace amplitudes (W = watts of absorbed active power) ---
% Phase A: paper-aligned naming `LoadStep_amp_bus14 / LoadStep_amp_bus15`.
% Task 2 (2026-04-28, paper line 993): Bus 14 LS1 load is pre-engaged at IC
% = 248e6 W; LS1 trigger = env writes 0 ⇒ R disengage ⇒ load drops out ⇒
% freq UP ("sudden load reduction" paper-faithful).
% Bus 15 LS2 default 0; LS2 trigger = env writes 188e6 ⇒ load engages ⇒
% freq DOWN ("sudden load increase" paper-aligned).
% Phase A++ CCS injection path retained (LoadStep_trip_amp_bus*) as alternate.
for k = 1:size(loadstep_defs, 1)
    lb = loadstep_defs{k, 3};
    if strcmp(lb, 'bus14')
        amp_default = double(248e6);   % Task 2: LS1 pre-engaged
    else
        amp_default = double(0.0);     % LS2 not engaged at IC
    end
    assignin('base', sprintf('LoadStep_amp_%s', lb), amp_default);
    assignin('base', sprintf('LoadStep_t_%s',   lb), double(5.0));   % s (informational)
end

%% ===== Build line branches (Π-line: series R+L + shunt C/2 each end) =====
% P2.1 fix-A (2026-04-26): NR uses lossy Π model with shunt cap at each
% line end (Y_sh = jωC·L/2, in Siemens). The earlier 'RL'-only build
% omitted ~200 MVAr line cap injection and caused a ω steady-region drift
% above 1 plus initial transient kick. Match NR by emitting:
%   - 1 series RL branch  (`<name>` block)
%   - 2 shunt C branches  (`<name>_Csh_F` and `<name>_Csh_T`), each = C·L/2
% Both shunt caps connect to ground at their respective bus end. Parallel
% lines instantiate independently (each parallel adds its own pair of caps).
n_lines = size(line_defs, 1);
for li = 1:n_lines
    name  = line_defs{li, 1};
    fb    = line_defs{li, 2};
    tb    = line_defs{li, 3};
    Lkm   = line_defs{li, 4};
    Rk    = line_defs{li, 5};
    Lk    = line_defs{li, 6};
    Ck    = line_defs{li, 7};

    R_tot = Rk * Lkm;                  % Ω
    L_tot = Lk * Lkm;                  % H
    C_half = Ck * Lkm / 2;             % F (per end)

    yposS = 200 + (li - 1) * 70;

    % Series RL branch
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [400 yposS 460 yposS+50]);
    set_param([mdl '/' name], 'BranchType', 'RL', ...
        'Resistance', sprintf('%.10g', R_tot), ...
        'Inductance', sprintf('%.10g', L_tot));
    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('from', fb, 'to', tb));

    % Shunt cap at FROM-end
    cshF = [name '_Csh_F'];
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' cshF], ...
        'Position', [320 yposS+70 380 yposS+110]);
    set_param([mdl '/' cshF], 'BranchType', 'C', ...
        'Capacitance', sprintf('%.10g', C_half));
    add_block('powerlib/Elements/Ground', [mdl '/' cshF '_GND'], ...
        'Position', [320 yposS+130 360 yposS+160]);
    add_line(mdl, [cshF '/RConn1'], [cshF '_GND/LConn1'], 'autorouting', 'smart');
    set_param([mdl '/' cshF], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', fb, 'src_line', name, 'role', 'shunt_C_half_F'));

    % Shunt cap at TO-end
    cshT = [name '_Csh_T'];
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' cshT], ...
        'Position', [480 yposS+70 540 yposS+110]);
    set_param([mdl '/' cshT], 'BranchType', 'C', ...
        'Capacitance', sprintf('%.10g', C_half));
    add_block('powerlib/Elements/Ground', [mdl '/' cshT '_GND'], ...
        'Position', [480 yposS+130 520 yposS+160]);
    add_line(mdl, [cshT '/RConn1'], [cshT '_GND/LConn1'], 'autorouting', 'smart');
    set_param([mdl '/' cshT], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', tb, 'src_line', name, 'role', 'shunt_C_half_T'));
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

% LoadStep — Series RLC R-only with workspace-expression Resistance.
% Phase A (2026-04-27): replaces v3-Phase1.3 dead `Resistance='1e9'`. The
% Resistance param is set to a string expression
%     'Vbase_const^2 / max(LoadStep_amp_<lb>, 1e-3)'
% which MATLAB re-evaluates from the base workspace at each sim() call.
% Verified Phasor-tunable in tmp_R_tune_test on 2026-04-27 (Variable Resistor
% requires Discrete solver and was rejected). env writes `LoadStep_amp_<lb>`
% mid-episode (W); amp=0 ⇒ R≈5e13 Ω (open); amp=X ⇒ R=V²/X draws X W at V≈Vbase.
% NR/IC unaffected by default amp=0 (load electrically absent at IC).
for k = 1:size(loadstep_defs, 1)
    name      = loadstep_defs{k, 1};
    bus       = loadstep_defs{k, 2};
    bus_label = loadstep_defs{k, 3};

    yposLS = 200 + (k - 1) * 100;
    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
        'Position', [1100 yposLS 1160 yposLS+60]);
    set_param([mdl '/' name], 'BranchType', 'R', ...
        'Resistance', sprintf('Vbase_const^2 / max(LoadStep_amp_%s, 1e-3)', bus_label));

    add_block('powerlib/Elements/Ground', [mdl '/GND_' name], ...
        'Position', [1100 yposLS+90 1140 yposLS+120]);
    add_line(mdl, [name '/RConn1'], ['GND_' name '/LConn1'], 'autorouting', 'smart');

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'bus_label', bus_label));
end

% LoadStep TRIP direction (Phase A++ 2026-04-27) — Controlled Current Source
% per bus, in parallel with the Series RLC R load. Drives the trip-direction
% disturbance (freq UP) which a passive R cannot do. CCS is single-phase and
% Phasor-compatible (verified in library lookup).
%
% Wiring: LConn = ground, RConn = bus. Per powerlib convention current flows
% L → external → R, so positive Constant input ⇒ I from GND → bus =
% INJECTION (= "negative load" = generator-like = freq UP).
%
% Magnitude: Constant outputs complex current via Real-Imag-to-Complex
%     I_phasor = (LoadStep_trip_amp_<lb> / Vbase_const) + 0j  (A, peak)
% At bus voltage V ≈ Vbase∠δ_bus with small δ, real(V·conj(I)) ≈
% Vbase · I_real · cos(δ) ≈ amp_W active power injected. Direction is purely
% real (in phase with reference), close-to-active for small bus angles.
%
% Default amp_W = 0 ⇒ I_phasor = 0+0j ⇒ source electrically absent ⇒ NR / IC
% unaffected. env writes LoadStep_trip_amp_<lb> mid-episode.
for k = 1:size(loadstep_defs, 1)
    bus       = loadstep_defs{k, 2};
    bus_label = loadstep_defs{k, 3};

    trip_name   = sprintf('LoadStepTrip_%s', bus_label);
    re_name     = sprintf('ITripRe_%s',     bus_label);
    im_name     = sprintf('ITripIm_%s',     bus_label);
    ri2c_name   = sprintf('ITripRI2C_%s',   bus_label);
    gnd_name    = sprintf('GND_%s',         trip_name);

    yposLT = 600 + (k - 1) * 110;
    bxLT   = 1100;

    % Real component: amp_W / Vbase_const   (A, peak)
    add_block('simulink/Sources/Constant', [mdl '/' re_name], ...
        'Position', [bxLT-160 yposLT bxLT-100 yposLT+20], ...
        'Value', sprintf('LoadStep_trip_amp_%s / Vbase_const', bus_label));

    % Imag component: 0 (purely active injection at reference angle)
    add_block('simulink/Sources/Constant', [mdl '/' im_name], ...
        'Position', [bxLT-160 yposLT+30 bxLT-100 yposLT+50], 'Value', '0');

    % Real-Imag → Complex (Phasor signal type for the CCS input)
    add_block('simulink/Math Operations/Real-Imag to Complex', [mdl '/' ri2c_name], ...
        'Position', [bxLT-80 yposLT bxLT-40 yposLT+40]);
    add_line(mdl, [re_name '/1'], [ri2c_name '/1'], 'autorouting', 'smart');
    add_line(mdl, [im_name '/1'], [ri2c_name '/2'], 'autorouting', 'smart');

    % Controlled Current Source: LConn=GND, RConn=bus → +I = INJECTION
    add_block('powerlib/Electrical Sources/Controlled Current Source', ...
        [mdl '/' trip_name], 'Position', [bxLT yposLT bxLT+60 yposLT+50]);
    set_param([mdl '/' trip_name], 'Initialize', 'off', 'Measurements', 'None');
    add_line(mdl, [ri2c_name '/1'], [trip_name '/1'], 'autorouting', 'smart');

    % Ground at LConn (current source from ground side)
    add_block('powerlib/Elements/Ground', [mdl '/' gnd_name], ...
        'Position', [bxLT-50 yposLT+70 bxLT-10 yposLT+90]);
    add_line(mdl, [trip_name '/LConn1'], [gnd_name '/LConn1'], ...
        'autorouting', 'smart');

    set_param([mdl '/' trip_name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'bus_label', bus_label, ...
                           'mode', 'trip_inject'));
end

% Option E (2026-04-30): CCS at Bus 7 / Bus 9 load centers. Same pattern
% as Phase A++ Trip CCS above, but at network load center rather than ESS
% terminal. Workspace var `CCS_Load_amp_<lb>` drives Real component;
% Imag = 0 (purely active). Default amp=0 ⇒ NR/IC untouched.
for k = 1:size(ccs_load_defs, 1)
    bus       = ccs_load_defs{k, 2};
    bus_label = ccs_load_defs{k, 3};

    ccs_name    = sprintf('CCSLoad_%s', bus_label);
    re_name     = sprintf('CCSLoadRe_%s',     bus_label);
    im_name     = sprintf('CCSLoadIm_%s',     bus_label);
    ri2c_name   = sprintf('CCSLoadRI2C_%s',   bus_label);
    gnd_name    = sprintf('GND_%s',           ccs_name);

    yposCC = 850 + (k - 1) * 110;
    bxCC   = 1100;

    % Real component: amp_W / Vbase_const   (A, peak)
    add_block('simulink/Sources/Constant', [mdl '/' re_name], ...
        'Position', [bxCC-160 yposCC bxCC-100 yposCC+20], ...
        'Value', sprintf('CCS_Load_amp_%s / Vbase_const', bus_label));

    % Imag component: 0 (purely active injection at reference angle)
    add_block('simulink/Sources/Constant', [mdl '/' im_name], ...
        'Position', [bxCC-160 yposCC+30 bxCC-100 yposCC+50], 'Value', '0');

    % Real-Imag → Complex (Phasor signal type for the CCS input)
    add_block('simulink/Math Operations/Real-Imag to Complex', [mdl '/' ri2c_name], ...
        'Position', [bxCC-80 yposCC bxCC-40 yposCC+40]);
    add_line(mdl, [re_name '/1'], [ri2c_name '/1'], 'autorouting', 'smart');
    add_line(mdl, [im_name '/1'], [ri2c_name '/2'], 'autorouting', 'smart');

    % Controlled Current Source: LConn=GND, RConn=bus → +I = INJECTION
    add_block('powerlib/Electrical Sources/Controlled Current Source', ...
        [mdl '/' ccs_name], 'Position', [bxCC yposCC bxCC+60 yposCC+50]);
    set_param([mdl '/' ccs_name], 'Initialize', 'off', 'Measurements', 'None');
    add_line(mdl, [ri2c_name '/1'], [ccs_name '/1'], 'autorouting', 'smart');

    % Ground at LConn
    add_block('powerlib/Elements/Ground', [mdl '/' gnd_name], ...
        'Position', [bxCC-50 yposCC+70 bxCC-10 yposCC+90]);
    add_line(mdl, [ccs_name '/LConn1'], [gnd_name '/LConn1'], ...
        'autorouting', 'smart');

    set_param([mdl '/' ccs_name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'bus_label', bus_label, ...
                           'mode', 'ccs_load_center'));
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

    % Pm0 source-base = Pm_var * SCvar  (Pm_var sys-pu, SCvar=Sbase/Sn_src)
    % MULTIPLY: P_src_pu = P_W/Sn = (P_W/Sbase)*(Sbase/Sn) = Pm_sys * SCvar
    add_block('simulink/Sources/Constant', [mdl '/Pm_sys_c_' sname], ...
        'Position', [bx-450 cy+50 bx-410 cy+70], 'Value', Pmvar);
    add_block('simulink/Sources/Constant', [mdl '/Sscale_c_' sname], ...
        'Position', [bx-450 cy+90 bx-410 cy+110], 'Value', SCvar);
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
    % Use Gain with literal '1/<Rvar>' so 1/R is computed once at compile.
    if strcmp(stype, 'sg')
        add_block('simulink/Math Operations/Gain', [mdl '/InvR_' sname], ...
            'Position', [bx-310 cy+105 bx-280 cy+135], ...
            'Gain', ['1/' Rvar]);
        % InvR will be wired to (ω−1) downstream via DroopMul.
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
        % InvR Gain consumes (ω−1) directly: InvR/1 = (1/R)·(ω−1)
        add_line(mdl, ['SumDw_' sname '/1'], ['InvR_' sname '/1']);

        % Pm_after_droop = PmTotal − (1/R)·(ω−1)
        add_block('simulink/Math Operations/Sum', [mdl '/PmAfterDroop_' sname], ...
            'Position', [bx-220 cy+70 bx-190 cy+100], 'Inputs', '+-');
        add_line(mdl, ['PmTotal_' sname '/1'], ['PmAfterDroop_' sname '/1']);
        add_line(mdl, ['InvR_' sname '/1'],   ['PmAfterDroop_' sname '/2']);

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
    % Pe_src_pu = Pe_sys_pu * SCvar  (multiply, see Pm conversion above)
    add_block('simulink/Math Operations/Product', [mdl '/PeSrcPU_' sname], ...
        'Position', [bx-100 cy+135 bx-70 cy+165], 'Inputs', '2');
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
    %
    % P3.0b interface fix (2026-04-26): align ESS logger VariableName with the
    % shared CVS step helper contract. slx_helpers/vsg_bridge/slx_step_and_read_cvs.m
    % hardcodes simOut.get(sprintf('omega_ts_%d', idx)) for agent_ids 1..n_agents.
    % The previous v3 build emitted 'omega_ts_ES1..ES4' (string suffix),
    % which the helper's %d format cannot retrieve, returning empty → bridge
    % returned zero state. ESS loggers now emit integer suffixes 1..4.
    %
    % Block paths (W_omega_<sname>) keep the descriptive suffix for in-model
    % readability — only the VariableName field (which controls simOut access)
    % changes. SG / wind loggers keep their string suffix because the helper
    % does not consume them (they are diagnostic-only).
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
        'VariableName', var_omega, 'SaveFormat', 'Timeseries', ...
        'MaxDataPoints', '2');
    add_line(mdl, [intW '/1'], ['W_omega_' sname '/1']);

    add_block('simulink/Sinks/To Workspace', [mdl '/W_delta_' sname], ...
        'Position', [bx-150 cy-45 bx-110 cy-30], ...
        'VariableName', var_delta, 'SaveFormat', 'Timeseries', ...
        'MaxDataPoints', '2');
    add_line(mdl, [intD '/1'], ['W_delta_' sname '/1']);

    add_block('simulink/Sinks/To Workspace', [mdl '/W_Pe_' sname], ...
        'Position', [bx+450 cy+145 bx+490 cy+165], ...
        'VariableName', var_pe, 'SaveFormat', 'Timeseries', ...
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
    'W1', 4, 'WindAmp_1', 'Wphase_1', 'WVmag_1';
    'W2', 8, 'WindAmp_2', 'Wphase_2', 'WVmag_2';
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

% Line endpoints + Π shunt caps (each line: 2 series ports + 2 shunt-C ports)
for li = 1:n_lines
    name = line_defs{li, 1};
    fb   = line_defs{li, 2};
    tb   = line_defs{li, 3};
    register(fb, [name '/LConn1']);
    register(tb, [name '/RConn1']);
    register(fb, [name '_Csh_F/LConn1']);    % shunt C/2 at FROM-end → bus fb
    register(tb, [name '_Csh_T/LConn1']);    % shunt C/2 at TO-end   → bus tb
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

% Phase A++ trip CCS: register RConn at bus (current INJECTION side; LConn
% is at ground per build above).
for k = 1:size(loadstep_defs, 1)
    bus       = loadstep_defs{k, 2};
    bus_label = loadstep_defs{k, 3};
    trip_name = sprintf('LoadStepTrip_%s', bus_label);
    register(bus, [trip_name '/RConn1']);
end

% Option E (2026-04-30): CCS at Bus 7 / Bus 9 load centers — register
% RConn at the load-center bus.
for k = 1:size(ccs_load_defs, 1)
    bus       = ccs_load_defs{k, 2};
    bus_label = ccs_load_defs{k, 3};
    ccs_name  = sprintf('CCSLoad_%s', bus_label);
    register(bus, [ccs_name '/RConn1']);
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
% P4.1a-v2 (2026-04-27): the runtime contract was previously incomplete —
% these per-source dynamics + scale factors were seeded ONLY via build-time
% `assignin('base', ...)` at L170-190, which lives in the BUILD-process
% workspace and does NOT survive a cold-start MATLAB engine. Cold-start sim
% then failed at Mgain_G<g> / Dgain_G<g> / InvR_G<g> / Pm_step_amp_c_G<g> /
% Pm_step_t_c_G<g> / SCvar_c_<src> / Sscale_c_<src> blocks with unrecognized
% variable errors. Plug the gap by routing every block-referenced workspace
% scalar through `runtime_consts` so `slx_episode_warmup_cvs` Phase 0 .mat
% load seeds them on every cold-start. `runtime.mat` regen is approved by
% the user GO message; .slx topology unchanged (deterministic build inputs).
for g = 1:3
    runtime_consts.(sprintf('VemfG_%d',     g)) = double(sg_Vemf_pu(g) * Vbase);
    runtime_consts.(sprintf('deltaG0_%d',   g)) = double(sg_delta0_rad(g));
    runtime_consts.(sprintf('Pmg_%d',       g)) = double(sg_Pm0_sys(g));
    % SG dynamics — referenced by Mgain_G<g> / Dgain_G<g> / InvR_G<g>.
    runtime_consts.(sprintf('Mg_%d',        g)) = double(2 * sg_H_paper(g));
    runtime_consts.(sprintf('Dg_%d',        g)) = double(sg_D_paper(g));
    runtime_consts.(sprintf('Rg_%d',        g)) = double(sg_R_paper(g));
    % SG Pm-step gating defaults (off) — referenced by Pm_step_t_c_G<g> and
    % Pm_step_amp_c_G<g> Constants. helper Phase 1b only seeds the ESS
    % Pm_step_t/amp variants; SG analogues live here.
    runtime_consts.(sprintf('PmgStep_t_%d',  g)) = double(5.0);
    runtime_consts.(sprintf('PmgStep_amp_%d', g)) = double(0.0);
    % SG source scale factor (gen-pu -> sys-pu) — referenced by SCvar_c_G<g>
    % and Sscale_c_G<g> Constants.
    runtime_consts.(sprintf('SGScale_%d',    g)) = double(Sbase / SG_SN);
end
for i = 1:4
    runtime_consts.(sprintf('Vmag_%d',     i)) = double(ess_Vemf_pu(i) * Vbase);
    runtime_consts.(sprintf('delta0_%d',   i)) = double(ess_delta0_rad(i));
    runtime_consts.(sprintf('Pm_%d',       i)) = double(ess_Pm0_sys(i));
    % ESS source scale factor (vsg-pu -> sys-pu) — referenced by SCvar_c_ES<i>
    % and Sscale_c_ES<i> Constants.
    runtime_consts.(sprintf('VSGScale_%d', i)) = double(Sbase / VSG_SN);
end
for w = 1:2
    runtime_consts.(sprintf('Wphase_%d', w)) = double(wind_term_a_rad(w));
    runtime_consts.(sprintf('WVmag_%d',  w)) = double(wind_term_v_pu(w) * Vbase);
    % WindAmp_<w> default 1.0 = full wind injection (matches build-time
    % default at L195). v3 supports W1/W2 partial trip via
    % `apply_workspace_var('WindAmp_<w>', <0..1>)` at runtime. P4.1a (2026-04-27).
    runtime_consts.(sprintf('WindAmp_%d', w)) = double(1.0);
end
% Phase A (2026-04-27): LoadStep amp/t defaults referenced by Constants.
% Cold-start MATLAB needs these in runtime.mat.
% Task 2 (2026-04-28): Bus 14 LS1 default = 248e6 W (pre-engaged per paper
% line 993 "sudden load reduction"); Bus 15 LS2 default = 0 W (LS2 = step-on
% direction per paper line 994).
for k = 1:size(loadstep_defs, 1)
    lb = loadstep_defs{k, 3};
    if strcmp(lb, 'bus14')
        rt_amp_default = double(248e6);   % Task 2: LS1 pre-engaged
    else
        rt_amp_default = double(0.0);     % LS2 default off
    end
    runtime_consts.(sprintf('LoadStep_amp_%s', lb)) = rt_amp_default;
    runtime_consts.(sprintf('LoadStep_t_%s',   lb)) = double(5.0);
end
% Phase A++ (2026-04-27): trip-direction current source amp defaults
% referenced by Constants ITripRe_<lb>. amp=0 ⇒ I_phasor = 0+0j ⇒ source
% electrically absent ⇒ NR / IC unaffected. env writes mid-episode.
for k = 1:size(loadstep_defs, 1)
    lb = loadstep_defs{k, 3};
    runtime_consts.(sprintf('LoadStep_trip_amp_%s', lb)) = double(0.0);
end
% Option E (2026-04-30): CCS load center amp defaults at Bus 7/9.
% Same convention as LoadStep_trip_amp_*: amp=0 ⇒ NR/IC untouched.
for k = 1:size(ccs_load_defs, 1)
    lb = ccs_load_defs{k, 3};
    runtime_consts.(sprintf('CCS_Load_amp_%s', lb)) = double(0.0);
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
