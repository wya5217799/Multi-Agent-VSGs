function build_kundur_cvs_v3_discrete()
%BUILD_KUNDUR_CVS_V3_DISCRETE  Paper-faithful 16-bus Kundur CVS Discrete model.
%
% Phase 1 of quality_reports/plans/2026-05-03_discrete_rebuild_phase0_smib_first.md.
%
% Discrete-mode rebuild of build_kundur_cvs_v3.m. Verbatim copy with these
% targeted patches applied:
%   1. powergui SimulationMode: Phasor → Discrete, SampleTime=50us
%   2. Solver: Variable-step ode23t → Fixed-step (50us)
%   3. Source-chain (per source × 7): RI2C complex → sin signal × 3 phases,
%      driving 3 single-phase CVS in Y-config (replaces 1 CVS subsystem)
%   4. Pe calculation: Complex-to-Real-Imag → V·I sum across 3 phases
%   5. LoadStep R-block: Series RLC with R from workspace var (compile-frozen)
%      → Three-Phase Breaker + Three-Phase Series RLC Load (verified working)
%   6. CCS injection (×4): RI2C complex → sin × 3 single-phase CCS in Y-config
%
% Validated by Phase 0 SMIB oracle (2026-05-03, see verdict doc):
%   - powergui Discrete + sin-driven CVS: PASS
%   - 248 MW LoadStep via Breaker+Load: 4.9 Hz max|Δf| (16× over 0.3 Hz)
%   - 5s sim wall time = 0.96s (Discrete is feasible for RL)
%
% Reuse contract from v3:
%   - Network topology data (line_defs, load_defs, shunt_defs): unchanged
%   - IC numerics (kundur_ic_cvs_v3.json): direct reuse, but the build
%     interprets (V_emf_mag_pu, delta0_rad) as time-domain (V_pk × sin(wn·t+δ0))
%     instead of complex phasor (V·exp(jδ0))
%   - Workspace var schema (M_i, D_i, Pmg_i, Pm_i, deltaG0_i, etc.): unchanged
%   - Swing equation logic: unchanged
%   - Pm-step gating per-source: unchanged
%   - SG governor droop (1/R)·(ω−1): unchanged
%
% Original v3 docstring follows.
%
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

mdl       = 'kundur_cvs_v3_discrete';
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
% PHASE 1 PATCH (2026-05-03): Discrete mode, validated by Phase 0 SMIB oracle.
set_param([mdl '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '50e-6');
set_param(mdl, 'StopTime', '0.5', 'SolverType', 'Fixed-step', ...
    'Solver', 'FixedStepAuto', 'FixedStep', '50e-6');

% Phase 1.1 source-chain rewrite uses build_dynamic_source_discrete helper
% (see scenarios/kundur/simulink_models/build_dynamic_source_discrete.m,
%  validated end-to-end at probes/kundur/spike/test_dynamic_source_helper.m).

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

%% ===== Build 3-phase PI Section Lines (Phase 1.1+ migration) =====
% v3 Phasor used 1× single-phase Series RLC RL + 2× shunt-C/2 per line.
% Discrete v3 uses 1× Three-Phase PI Section Line which has R+L+C built-in
% (positive- and zero-sequence params).
%
% Pre-flight F11 (test_3phase_network_disc.m) verified Three-Phase PI
% Section Line works at v3-scale (230kV/100MW/100km).
% Pre-flight F12 (test_multisrc_coupling_disc.m) verified multi-source
% Π line coupling synchronizes.
%
% Block path: sps_lib/Power Grid Elements/Three-Phase PI Section Line
% Note: name has embedded newline (sps lib quirk), built via sprintf.
n_lines = size(line_defs, 1);
pi_path_3p = sprintf('sps_lib/Power Grid Elements/Three-Phase\nPI Section Line');
for li = 1:n_lines
    name  = line_defs{li, 1};
    fb    = line_defs{li, 2};
    tb    = line_defs{li, 3};
    Lkm   = line_defs{li, 4};
    Rk    = line_defs{li, 5};
    Lk    = line_defs{li, 6};
    Ck    = line_defs{li, 7};

    % Per-km params: positive sequence + standard zero-sequence approx
    R_3p = [Rk, 3 * Rk];      % [R_pos, R_zero]
    L_3p = [Lk, 3 * Lk];      % [L_pos, L_zero]
    C_3p = [Ck, 0.6 * Ck];    % [C_pos, C_zero]

    % Phase 1.1+ guard: Three-Phase PI Section Line Discrete checks propagation
    % speed = 1/sqrt(L·C) <= c (≈300,000 km/s). v3's "short" lines use
    % L_short=0.5e-3 H/km + C_short=9e-9 F/km giving 471,000 km/s (> c). These
    % single-km transformer-equivalent lines were Phasor-mode artifacts; in
    % Discrete we MUST clamp C to keep speed sub-luminal. This is purely
    % numerical (the "line" represents a transformer leakage L), so adjusting
    % C does not change physical interpretation meaningfully.
    c_kmps = 280000;   % safety margin under 300,000 km/s
    v_pos = 1 / sqrt(Lk * Ck);
    if v_pos > c_kmps
        Ck_adj = (1/c_kmps)^2 / Lk;
        C_3p = [Ck_adj, 0.6 * Ck_adj];
        fprintf('RESULT: NOTE %s short-line C adjusted %g -> %g (v_orig=%.0f km/s)\n', ...
            name, Ck, Ck_adj, v_pos);
    end

    yposS = 200 + (li - 1) * 110;
    add_block(pi_path_3p, [mdl '/' name], ...
        'Position', [400 yposS 480 yposS+90]);
    set_param([mdl '/' name], ...
        'Length', num2str(Lkm), ...
        'Frequency', num2str(fn), ...
        'Resistances', mat2str(R_3p), ...
        'Inductances', mat2str(L_3p), ...
        'Capacitances', mat2str(C_3p));
    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('from', fb, 'to', tb));
    % Note: shunt-C is built-in to Three-Phase PI Section Line; no separate
    % Csh_F/Csh_T blocks needed (v3-Phasor pattern obsoleted by 3-phase block).
end

%% ===== Build 3-phase Loads (Phase 1.1+ migration) =====
% v3 Phasor used single-phase Series RLC RL.
% Discrete v3 uses Three-Phase Series RLC Load (P + Q_ind direct param).
% Pre-flight F11 verified Three-Phase Series RLC Load works at v3-scale.
n_loads = size(load_defs, 1);
load_path_3p = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
for ld = 1:n_loads
    name  = load_defs{ld, 1};
    bus   = load_defs{ld, 2};
    P_W   = load_defs{ld, 3};
    Q_var = load_defs{ld, 4};

    yposL = 200 + (ld - 1) * 130;
    add_block(load_path_3p, [mdl '/' name], ...
        'Position', [800 yposL 880 yposL+90]);
    set_param([mdl '/' name], ...
        'Configuration', 'Y (grounded)', ...
        'NominalVoltage', num2str(Vbase), ...
        'NominalFrequency', num2str(fn), ...
        'ActivePower', sprintf('%.10g', P_W), ...
        'InductivePower', sprintf('%.10g', Q_var), ...
        'CapacitivePower', '0');

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus));
    % Note: Load_const has internal Y-grounded neutral; no separate GND block.
end

% Shunt caps: Three-Phase Series RLC Load with CapacitivePower=Q_var
% (Discrete v3 migration — replaces single-phase Series RLC C from v3 Phasor)
n_shunts = size(shunt_defs, 1);
for sh = 1:n_shunts
    name  = shunt_defs{sh, 1};
    bus   = shunt_defs{sh, 2};
    Q_var = shunt_defs{sh, 3};

    yposC = 200 + (sh - 1) * 130;
    add_block(load_path_3p, [mdl '/' name], ...
        'Position', [950 yposC 1030 yposC+90]);
    set_param([mdl '/' name], ...
        'Configuration', 'Y (grounded)', ...
        'NominalVoltage', num2str(Vbase), ...
        'NominalFrequency', num2str(fn), ...
        'ActivePower', '0', ...
        'InductivePower', '0', ...
        'CapacitivePower', sprintf('%.10g', Q_var));

    set_param([mdl '/' name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus));
end

% PHASE 1.1 PATCH (2026-05-03): LoadStep — Three-Phase Breaker + Three-Phase
% Series RLC Load (replaces v3 Series RLC R with Resistance from workspace var,
% PROVEN compile-frozen in Discrete+FastRestart per test_r_fastrestart_disc.m).
%
% Pattern (validated by Phase 0 SMIB oracle 4.9 Hz at 248 MW):
%   Breaker (signal-controlled, closes at LoadStep_t_<lb>)
%   ├ initial state: open if amp_default=0; closed if amp_default>0
%   ├ SwitchTimes = [LoadStep_t_<lb>] (single transition: open→closed or closed→open)
%   └ External = off (internal time-driven gating)
% Three-Phase Series RLC Load (Y-grounded, R-only)
%   ├ ActivePower = LoadStep_amp_<lb> (W, workspace var)
%   └ Connection: VSG bus 14 / 15 (3-phase RConn1/2/3)
%
% Workspace contract preserved: `LoadStep_amp_<lb>` and `LoadStep_t_<lb>`
% drive the load active power and trigger time. Default amp_default per
% loadstep_defs (Bus 14 LS1 pre-engaged 248 MW; Bus 15 LS2 0 → trigger writes 188 MW).
load_path_3p = sprintf('sps_lib/Passives/Three-Phase\nSeries RLC Load');
for k = 1:size(loadstep_defs, 1)
    name      = loadstep_defs{k, 1};
    bus       = loadstep_defs{k, 2};
    bus_label = loadstep_defs{k, 3};

    breaker_name = sprintf('LoadStepBreaker_%s', bus_label);
    load_name    = name;   % keep historical name for downstream wiring
    t_var = sprintf('LoadStep_t_%s', bus_label);

    yposLS = 200 + (k - 1) * 130;
    bxLS   = 1100;

    % Initial state of breaker depends on whether load is pre-engaged at IC.
    % Bus 14 LS1: pre-engaged 248 MW (paper line 993, see loadstep_defs default).
    % Bus 15 LS2: not engaged at IC.
    % Convention: closed initially if amp_default > 0 (load conducting at IC).
    if strcmp(bus_label, 'bus14')
        breaker_init = 'closed';   % LS1 pre-engaged
    else
        breaker_init = 'open';     % LS2 not engaged; trigger CLOSES it
    end

    % Three-Phase Breaker
    add_block('sps_lib/Power Grid Elements/Three-Phase Breaker', ...
        [mdl '/' breaker_name], 'Position', [bxLS yposLS bxLS+60 yposLS+80]);
    set_param([mdl '/' breaker_name], 'InitialState', breaker_init, ...
        'SwitchA', 'on', 'SwitchB', 'on', 'SwitchC', 'on', ...
        'External', 'off', 'SwitchTimes', sprintf('[%s]', t_var));

    % Three-Phase Series RLC Load (R-only, Y-grounded)
    add_block(load_path_3p, [mdl '/' load_name], ...
        'Position', [bxLS+90 yposLS bxLS+150 yposLS+80]);
    set_param([mdl '/' load_name], 'Configuration', 'Y (grounded)', ...
        'NominalVoltage', num2str(Vbase), 'NominalFrequency', num2str(fn), ...
        'ActivePower', sprintf('max(LoadStep_amp_%s, 1)', bus_label), ...
        'InductivePower', '0', 'CapacitivePower', '0');

    % Wire Breaker RConn1/2/3 → Load LConn1/2/3
    add_line(mdl, [breaker_name '/RConn1'], [load_name '/LConn1'], 'autorouting', 'smart');
    add_line(mdl, [breaker_name '/RConn2'], [load_name '/LConn2'], 'autorouting', 'smart');
    add_line(mdl, [breaker_name '/RConn3'], [load_name '/LConn3'], 'autorouting', 'smart');

    % UserData on the breaker so downstream registry can find this LoadStep
    set_param([mdl '/' breaker_name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'bus_label', bus_label, ...
                           'load_block', load_name));
end

% PHASE 1.1 PATCH (2026-05-03): CCS injection blocks DISABLED for now.
% v3 used RI2C complex-phasor pattern driving CCS — proven to fail compile
% in Discrete mode (test_cvs_disc_input.m result C). Future patch will
% restore these using sin-driven 3-phase CCS (similar to source-chain pattern).
% For Phase 1.3 (compile + IC settle test), CCS is not needed — Breaker+Load
% LoadStep mechanism above provides the disturbance signal.
if false  % CCS_DISABLED — restore in Phase 1.5+ with sin-driven pattern
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
end  % end CCS_DISABLED guard (if false ... end)

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
add_block('built-in/Clock', [mdl '/Clock_global'], ...
    'Position', [200 1500 230 1530], 'DisplayTime', 'off');

% PHASE 1.1 PATCH (2026-05-03): inline source chain replaced with helper.
% Helper: build_dynamic_source_discrete (validated end-to-end on
% probes/kundur/spike/test_dynamic_source_helper.m, max|Δf|=4.93 Hz at 248 MW).
%
% Helper produces per-source: theta = wn*t + delta → 3-phase sin signals → 3
% single-phase CVS in Y-config → Three-Phase V-I Measurement → Pe = Σ V·I.
% Network-side terminal: VImeas_<sname>/RConn1..3 (3-phase, Y).
%
% Storage: source struct + geometry struct + global params struct.
params.fn = fn; params.wn = wn; params.Vbase = Vbase; params.Sbase = Sbase;
for s = 1:n_src
    src.name        = src_meta{s, 1};
    src.bus         = src_meta{s, 2};
    src.stype       = src_meta{s, 3};
    src.M_var       = src_meta{s, 4};
    src.D_var       = src_meta{s, 5};
    src.Pm_var      = src_meta{s, 6};
    src.delta0_var  = src_meta{s, 7};
    src.Vmag_var    = src_meta{s, 8};
    src.scale_var   = src_meta{s, 9};
    src.Rdrop_var   = src_meta{s, 10};
    src.Lint_H      = src_meta{s, 11};
    src.step_t_var  = src_meta{s, 12};
    src.step_amp_var = src_meta{s, 13};

    geom.cy = 80 + (s - 1) * 260;
    geom.bx = 1300;
    geom.global_clock = 'Clock_global';
    geom.bus_anchor = '';   % unused; per-source bus wiring done in §"Connect electrical bus net"

    build_dynamic_source_discrete(mdl, src, geom, params);
end

%% ===== Build wind PVS (W1, W2) — Programmable Voltage Source, no swing eq =====
% Model as `AC Voltage Source` with Phase = wind_term_a_rad (deg, fixed).
% Amplitude scaled by WindAmp_w workspace knob — set 0 to trip.
% PHASE 1.1+ PATCH (2026-05-03): Three-Phase Source (NonIdeal Yg) for Wind PVS.
% v3 Phasor used single-phase AC Voltage Source. Discrete v3 needs 3-phase
% to match network. NonIdealSource='on' avoids "ideal V parallel C" compile
% error per F11 finding. Internal R+L provides Thévenin equivalent.
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

    add_block('sps_lib/Sources/Three-Phase Source', [mdl '/' src], ...
        'Position', [bx cy bx+80 cy+90]);
    set_param([mdl '/' src], ...
        'InternalConnection', 'Yg', ...
        'Voltage',      sprintf('(%s) * (%s)', Avar, Vvar), ...
        'PhaseAngle',   sprintf('(%s) * 180/pi', Pvar), ...
        'Frequency',    num2str(fn), ...
        'NonIdealSource', 'on', ...
        'SpecifyImpedance', 'on', ...
        'ShortCircuitLevel', '500e6', ...   % wind farm class
        'BaseVoltage', num2str(Vbase), ...
        'XRratio', '7');
end

%% ===== Connect electrical bus net (3-phase wiring, Phase 1.1+) =====
% Phase 1.1+ migration (2026-05-03): each bus is a logical node formed by
% PER-PHASE tying. Each 3-phase block contributes 3 ports (one per phase)
% to the bus. They must be tied PHASE-WISE (A↔A, B↔B, C↔C).
%
% Strategy: per-phase anchor map. For each bus, three anchors (one per
% phase). Each block-at-bus registers 3 ports (LConn1/2/3 or RConn1/2/3),
% and each port is tied to its phase's anchor.

% Three independent anchor maps, one per phase
bus_anchor_A = containers.Map('KeyType', 'double', 'ValueType', 'char');
bus_anchor_B = containers.Map('KeyType', 'double', 'ValueType', 'char');
bus_anchor_C = containers.Map('KeyType', 'double', 'ValueType', 'char');

% --- helper: register one block's L-side (3 ports) at a bus ---
register3p_L = @(bus, name) local_register_at_bus(mdl, bus_anchor_A, bus, [name '/LConn1']);
% (Define explicit local function below — lambda doesn't support 3 phases easily)

% Line endpoints (Three-Phase PI: 3 LConn + 3 RConn per line)
for li = 1:n_lines
    name = line_defs{li, 1};
    fb   = line_defs{li, 2};
    tb   = line_defs{li, 3};
    % FROM end (LConn1/2/3) → bus fb
    local_register_at_bus(mdl, bus_anchor_A, fb, [name '/LConn1']);
    local_register_at_bus(mdl, bus_anchor_B, fb, [name '/LConn2']);
    local_register_at_bus(mdl, bus_anchor_C, fb, [name '/LConn3']);
    % TO end (RConn1/2/3) → bus tb
    local_register_at_bus(mdl, bus_anchor_A, tb, [name '/RConn1']);
    local_register_at_bus(mdl, bus_anchor_B, tb, [name '/RConn2']);
    local_register_at_bus(mdl, bus_anchor_C, tb, [name '/RConn3']);
end

% Loads (Three-Phase Series RLC Load: 3 LConn per load)
for ld = 1:n_loads
    name = load_defs{ld, 1};
    bus  = load_defs{ld, 2};
    local_register_at_bus(mdl, bus_anchor_A, bus, [name '/LConn1']);
    local_register_at_bus(mdl, bus_anchor_B, bus, [name '/LConn2']);
    local_register_at_bus(mdl, bus_anchor_C, bus, [name '/LConn3']);
end

% Shunts (Three-Phase Series RLC Load capacitive: 3 LConn each)
for sh = 1:n_shunts
    name = shunt_defs{sh, 1};
    bus  = shunt_defs{sh, 2};
    local_register_at_bus(mdl, bus_anchor_A, bus, [name '/LConn1']);
    local_register_at_bus(mdl, bus_anchor_B, bus, [name '/LConn2']);
    local_register_at_bus(mdl, bus_anchor_C, bus, [name '/LConn3']);
end

% LoadStep — Breaker has 3 LConn (bus side) + 3 RConn (load side)
% bus → Breaker LConn1/2/3 → Breaker RConn1/2/3 → Load_step LConn1/2/3 (already wired internally)
for k = 1:size(loadstep_defs, 1)
    bus_label = loadstep_defs{k, 3};
    breaker_name = sprintf('LoadStepBreaker_%s', bus_label);
    bus = loadstep_defs{k, 2};
    local_register_at_bus(mdl, bus_anchor_A, bus, [breaker_name '/LConn1']);
    local_register_at_bus(mdl, bus_anchor_B, bus, [breaker_name '/LConn2']);
    local_register_at_bus(mdl, bus_anchor_C, bus, [breaker_name '/LConn3']);
end

% CCS injection blocks DISABLED (wrapped in if false above) — skip wiring.
% Phase 1.5 will restore CCS using sin-driven 3-phase pattern + register
% the new 3-phase RConn ports here.

% Source 3-phase output (VImeas RConn1/2/3) → bus
for s = 1:n_src
    sname = src_meta{s, 1};
    bus   = src_meta{s, 2};
    vimeas = sprintf('VImeas_%s', sname);
    local_register_at_bus(mdl, bus_anchor_A, bus, [vimeas '/RConn1']);
    local_register_at_bus(mdl, bus_anchor_B, bus, [vimeas '/RConn2']);
    local_register_at_bus(mdl, bus_anchor_C, bus, [vimeas '/RConn3']);
end

% Wind PVS — Three-Phase Source NonIdeal Yg, register 3 RConn at bus
for w = 1:size(wind_meta, 1)
    wname = wind_meta{w, 1};
    bus   = wind_meta{w, 2};
    src_name = sprintf('PVS_%s', wname);
    local_register_at_bus(mdl, bus_anchor_A, bus, [src_name '/RConn1']);
    local_register_at_bus(mdl, bus_anchor_B, bus, [src_name '/RConn2']);
    local_register_at_bus(mdl, bus_anchor_C, bus, [src_name '/RConn3']);
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
