function pf = compute_kundur_powerflow(json_path)
%COMPUTE_KUNDUR_POWERFLOW  Newton-Raphson power flow for Kundur 15-bus network.
%
%   pf = compute_kundur_powerflow()
%   pf = compute_kundur_powerflow(json_path)
%
%   Builds Ybus from network parameters identical to build_powerlib_kundur.m,
%   runs a Newton-Raphson power flow, and computes equilibrium VSG delta angles
%   for writing to kundur_ic.json.
%
%   Inputs:
%     json_path — path to kundur_ic.json (default: auto-detected relative to
%                 this file's location in scenarios/kundur/matlab_scripts/)
%
%   Returns struct pf with fields:
%     converged       — logical, true if NR converged
%     iterations      — integer, number of NR iterations used
%     max_mismatch    — double, final max |ΔP|/|ΔQ| mismatch (pu)
%     Vmag            — 15×1, bus voltage magnitudes (pu), bus order: bus_ids
%     Vang_deg        — 15×1, bus voltage angles (deg), Bus1 = 0° reference
%     bus_ids         — 15×1, physical bus IDs corresponding to rows of Vmag/Vang_deg
%     main_bus_ang_abs_deg — 4×1, absolute simulation-frame angles for Bus7,8,10,9 (ES1-ES4 main buses)
%     ess_delta_deg   — 4×1, VSG internal EMF angles [ES1,ES2,ES3,ES4] in absolute simulation frame
%     sin_arg         — 4×1, sin(δ-θ_main) for each ESS — must be in (-1,1)
%
%   Derivation of ess_delta_deg:
%     VSG swing eq at equilibrium: ω=1, dδ/dt=0 → P_ref_vsg = P_e_vsg
%     P_e_vsg [vsg-base pu] = (E·V_main·sin(δ-θ)/X_vsg) × Sbase/VSG_SN
%     → sin(δ-θ) = P0_vsg_base × (VSG_SN/Sbase) × X_vsg_sys / V_main
%     → δ = θ_main_abs + arcsin(...)
%     where θ_main_abs = θ_pf_relative + 20° (Bus1 simulation initial angle)
%
%   Bus numbering: physical IDs [1,2,3,4,5,6,7,8,9,10,11,12,14,15,16]
%     (no Bus13 in this topology). Internal NR indices 1..15.
%
%   Bus types: Slack=Bus1(G1), PV=Bus2(G2)/Bus3(G3)/Bus4(W1), PQ=rest

if nargin < 1
    this_dir = fileparts(mfilename('fullpath'));   % scenarios/kundur/matlab_scripts/
    repo_dir = fileparts(fileparts(fileparts(this_dir)));
    json_path = fullfile(repo_dir, 'scenarios', 'kundur', 'kundur_ic.json');
end

ic = slx_load_kundur_ic(json_path);
P0_vsg_base = ic.vsg_p0_vsg_base_pu;   % 1×4, VSG-base pu [ES1,ES2,ES3,ES4]

%% === System parameters — must match build_powerlib_kundur.m exactly ===
fn    = 50;
wn    = 2*pi*fn;
Sbase = 100e6;
Vbase = 230e3;
Zbase = Vbase^2 / Sbase;   % 529 Ω

VSG_SN    = 200e6;
X_vsg_sys = 0.30 * (Sbase/VSG_SN);   % 0.15 pu on system base

R_std   = 0.053;    L_std   = 1.41e-3;  C_std   = 0.009e-6;
R_short = 0.01;     L_short = 0.5e-3;   C_short = 0.009e-6;

% Bus1 (G1 slack) initial angle in simulation frame [deg]
BUS1_ABS_DEG = 20.0;

%% === Bus numbering ===
% Physical bus IDs present in topology (no Bus13)
bus_ids = [1,2,3,4,5,6,7,8,9,10,11,12,14,15,16]';
n_bus   = length(bus_ids);   % 15

% Lookup: physical bus ID → internal 1..15 index
id2idx = zeros(1, 20);
for k = 1:n_bus
    id2idx(bus_ids(k)) = k;
end

%% === Ybus construction (PI line model) ===
Ybus = zeros(n_bus, n_bus);

% Line definitions: {from_bus, to_bus, len_km, R_km, L_km, C_km}
% Exactly matches line_defs in build_powerlib_kundur.m (parallel lines listed separately)
line_defs = {
    1,  5,   5,   R_std,   L_std,   C_std;
    2,  6,   5,   R_std,   L_std,   C_std;
    3,  10,  5,   R_std,   L_std,   C_std;
    4,  9,   5,   R_std,   L_std,   C_std;
    % Area 1
    5,  6,   25,  R_std,   L_std,   C_std;
    5,  6,   25,  R_std,   L_std,   C_std;
    6,  7,   10,  R_std,   L_std,   C_std;
    6,  7,   10,  R_std,   L_std,   C_std;
    % Inter-area tie (3 parallel 110 km)
    7,  8,   110, R_std,   L_std,   C_std;
    7,  8,   110, R_std,   L_std,   C_std;
    7,  8,   110, R_std,   L_std,   C_std;
    % Area 2
    8,  9,   10,  R_std,   L_std,   C_std;
    8,  9,   10,  R_std,   L_std,   C_std;
    9,  10,  25,  R_std,   L_std,   C_std;
    9,  10,  25,  R_std,   L_std,   C_std;
    % VSG connection lines (short, 1 km)
    7,  12,  1,   R_short, L_short, C_short;
    8,  16,  1,   R_short, L_short, C_short;
    10, 14,  1,   R_short, L_short, C_short;
    9,  15,  1,   R_short, L_short, C_short;
    % W2 connection
    8,  11,  1,   R_short, L_short, C_short;
};

for li = 1:size(line_defs, 1)
    fb  = line_defs{li, 1};
    tb  = line_defs{li, 2};
    len = line_defs{li, 3};
    Rk  = line_defs{li, 4};
    Lk  = line_defs{li, 5};
    Ck  = line_defs{li, 6};

    R_tot = Rk * len;
    X_tot = wn * Lk * len;
    B_tot = wn * Ck * len;

    z_pu = (R_tot + 1j*X_tot) / Zbase;
    y_pu = 1 / z_pu;
    ysh  = 1j * B_tot * Zbase / 2;   % half shunt at each end

    fi = id2idx(fb);
    ti = id2idx(tb);

    Ybus(fi,fi) = Ybus(fi,fi) + y_pu + ysh;
    Ybus(ti,ti) = Ybus(ti,ti) + y_pu + ysh;
    Ybus(fi,ti) = Ybus(fi,ti) - y_pu;
    Ybus(ti,fi) = Ybus(ti,fi) - y_pu;
end

%% === Bus data ===
% Columns: [bus_type, V_spec_pu, P_sch_pu, Q_sch_pu]
% P_sch: generation positive, load negative (system-base pu)
% bus_type: 1=Slack, 2=PV, 3=PQ
SLACK = 1;  PV = 2;  PQ = 3;

% Convert ESS P0 from VSG-base to system-base pu
% ESS order: ES1(Bus12→7), ES2(Bus16→8), ES3(Bus14→10), ES4(Bus15→9)
P_ES_sys = P0_vsg_base * (VSG_SN/Sbase);   % 1×4, system-base pu

% TripLoad1 at Bus14 = 248 MW total (on at episode start)
TripLoad1_pu = 248e6 / Sbase;   % 2.48 pu sys-base

% bus_data rows ordered by bus_ids = [1,2,3,4,5,6,7,8,9,10,11,12,14,15,16]
%                       [type   Vspec  P_sch              Q_sch]
bus_data = zeros(n_bus, 4);
bus_data(id2idx(1),  :) = [SLACK, 1.03,  0,                       0];   % G1 slack
bus_data(id2idx(2),  :) = [PV,    1.01,  700/100,                 0];   % G2
bus_data(id2idx(3),  :) = [PV,    1.01,  719/100,                 0];   % G3
bus_data(id2idx(4),  :) = [PV,    1.00,  700/100,                 0];   % W1 (constant PV)
bus_data(id2idx(5),  :) = [PQ,    1.00,  0,                       0];   % junction
bus_data(id2idx(6),  :) = [PQ,    1.00,  0,                       0];   % junction
% Bus7: Load 967MW + 100Mvar inductive; Shunt 200Mvar cap → net Q = -1.0+2.0 = +1.0 pu
bus_data(id2idx(7),  :) = [PQ,    1.00,  -967/100,                1.0];
bus_data(id2idx(8),  :) = [PQ,    1.00,  0,                       0];   % junction
% Bus9: Load 1767MW + 100Mvar; Shunt 350Mvar cap → net Q = -1.0+3.5 = +2.5 pu
bus_data(id2idx(9),  :) = [PQ,    1.00,  -1767/100,               2.5];
bus_data(id2idx(10), :) = [PQ,    1.00,  0,                       0];   % junction
bus_data(id2idx(11), :) = [PQ,    1.00,  100/100,                 0];   % W2
bus_data(id2idx(12), :) = [PQ,    1.00,  P_ES_sys(1),             0];   % ES1
% Bus14: ES3 injection minus TripLoad1 (248 MW, load ON at episode start)
bus_data(id2idx(14), :) = [PQ,    1.00,  P_ES_sys(3)-TripLoad1_pu, 0]; % ES3
bus_data(id2idx(15), :) = [PQ,    1.00,  P_ES_sys(4),             0];   % ES4 (TripLoad2=0)
bus_data(id2idx(16), :) = [PQ,    1.00,  P_ES_sys(2),             0];   % ES2

bus_type = bus_data(:, 1);
V_spec   = bus_data(:, 2);
P_sch    = bus_data(:, 3);
Q_sch    = bus_data(:, 4);

%% === NR initialization ===
slack_idx = find(bus_type == SLACK);
pv_idx    = find(bus_type == PV);
pq_idx    = find(bus_type == PQ);

% Non-slack buses (state variables: θ for all non-slack, |V| for PQ only)
non_slack_idx = [pv_idx; pq_idx];
n_ns = length(non_slack_idx);
n_pq = length(pq_idx);

theta = zeros(n_bus, 1);   % rad, all start at 0
Vmag  = V_spec;            % pu, initial guess from spec

G = real(Ybus);
B = imag(Ybus);

%% === Newton-Raphson iteration ===
max_iter    = 50;
tol         = 1e-8;
converged   = false;
max_mm      = Inf;

for iter = 1:max_iter
    % Complex bus voltages
    V_cmplx = Vmag .* exp(1j * theta);

    % P, Q injections calculated from network
    S_calc  = V_cmplx .* conj(Ybus * V_cmplx);
    P_calc  = real(S_calc);
    Q_calc  = imag(S_calc);

    % Mismatch (only for buses that have scheduled values)
    dP_all = P_sch - P_calc;
    dQ_all = Q_sch - Q_calc;

    dP_ns = dP_all(non_slack_idx);   % ΔP for all non-slack
    dQ_pq = dQ_all(pq_idx);          % ΔQ for PQ buses only

    mismatch = [dP_ns; dQ_pq];
    max_mm   = max(abs(mismatch));

    if max_mm < tol
        converged = true;
        break;
    end

    % --- Jacobian (polar formulation) ---
    % H = ∂P/∂θ,  N = (∂P/∂|V|)·|V|
    % J = ∂Q/∂θ,  L = (∂Q/∂|V|)·|V|
    H = zeros(n_bus);
    N = zeros(n_bus);
    J = zeros(n_bus);
    L = zeros(n_bus);

    for i = 1:n_bus
        Vi = Vmag(i);
        for j = 1:n_bus
            Vj  = Vmag(j);
            dth = theta(i) - theta(j);
            Gij = G(i,j);  Bij = B(i,j);
            if i ~= j
                H(i,j) =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
                N(i,j) =  Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                J(i,j) = -Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                L(i,j) =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
            end
        end
        % Diagonal terms
        H(i,i) = -Q_calc(i) - B(i,i)*Vi^2;
        N(i,i) =  P_calc(i) + G(i,i)*Vi^2;
        J(i,i) =  P_calc(i) - G(i,i)*Vi^2;
        L(i,i) =  Q_calc(i) - B(i,i)*Vi^2;
    end

    % Assemble reduced Jacobian: [ΔP_ns; ΔQ_pq] = Jac × [Δθ_ns; Δ|V|/|V|_pq]
    Jac = [H(non_slack_idx, non_slack_idx),  N(non_slack_idx, pq_idx); ...
           J(pq_idx,        non_slack_idx),  L(pq_idx,        pq_idx)];

    dx = Jac \ mismatch;

    d_theta = dx(1:n_ns);
    d_Vrel  = dx(n_ns+1:end);   % Δ|V|/|V|

    theta(non_slack_idx) = theta(non_slack_idx) + d_theta;
    Vmag(pq_idx)         = Vmag(pq_idx) .* (1 + d_Vrel);
end

Vang_deg = theta * 180/pi;

%% === Compute ESS delta angles ===
% ESS main buses: ES1→Bus7, ES2→Bus8, ES3→Bus10, ES4→Bus9
ess_main_bus = [7, 8, 10, 9];
main_idx     = arrayfun(@(b) id2idx(b), ess_main_bus);

% Main bus angles in absolute simulation frame (add Bus1 initial angle)
theta_main_pf  = Vang_deg(main_idx);            % power-flow relative [deg]
theta_main_abs = theta_main_pf + BUS1_ABS_DEG;  % absolute simulation frame [deg]
V_main         = Vmag(main_idx);                 % |V| at main buses [pu]

% SMIB equilibrium formula (derived from VSG IntD/IntW dynamics):
%   P_ref_vsg = P_e_vsg at ω=1
%   P_e_vsg [vsg-pu] = (E·V·sin(δ-θ)/X_vsg_sys) × Sbase/VSG_SN
%   → sin(δ-θ) = P0_vsg_base × (VSG_SN/Sbase) × X_vsg_sys / V_main
sin_arg = P0_vsg_base(:) .* (VSG_SN/Sbase) .* X_vsg_sys ./ V_main(:);

% Physical feasibility check — warn but do not abort (stale P0 may exceed Pmax)
for i = 1:4
    if abs(sin_arg(i)) >= 1.0
        fprintf(['  WARNING: ES%d sin_arg=%.4f exceeds ±1.0 — P0 may be too large ' ...
            'for current network.\n  delta_deg set to ±90° fallback.\n'], i, sin_arg(i));
        sin_arg(i) = sign(sin_arg(i)) * 0.9999;
    end
end

delta_offset_deg = asin(sin_arg) * 180/pi;   % 4×1 [deg]
ess_delta_deg    = theta_main_abs + delta_offset_deg;

%% === Generator / wind farm bus angles in absolute simulation frame ===
% Used to initialise vlf_gen and vlf_wind in build_powerlib_kundur.m so that
% all sources start at the NR-PF equilibrium — prevents Pe-mismatch transient.
gen_bus_ids  = [2,   3,   4,   11];   % G2(Bus2), G3(Bus3), W1(Bus4), W2(Bus11)
gen_bus_lbls = {'G2/Bus2', 'G3/Bus3', 'W1/Bus4', 'W2/Bus11'};
gen_idx = arrayfun(@(b) id2idx(b), gen_bus_ids);
gen_delta_deg = Vang_deg(gen_idx)' + BUS1_ABS_DEG;   % 1×4 absolute [deg]

%% === Source EMF angles and filter RL initial currents ===
% EMF angle = angle(V_bus + Z*I_gen) > terminal angle (Z*I_gen is the voltage drop).
% Setting IL on each RL filter block eliminates the DC-component transient from
% the Simscape local fixed-step solver initialising inductors to I=V_DC/R≈0.
%
% Physical impedances — must match build_powerlib_kundur.m exactly.
R_gen_pu_val = 0.003 * (Sbase / 900e6);   % 3.33e-4 pu on Sbase
X_gen_pu_val = 0.30  * (Sbase / 900e6);   % 0.0333 pu on Sbase
R_vsg_pu_val = 0.003 * (Sbase / VSG_SN);  % 1.50e-3 pu on Sbase
Vpk_base     = Vbase * sqrt(2/3);          % peak phase voltage at 1.0 pu [V]

% Net complex power injections from NR result (needed for G1 slack P and full Q)
V_cmplx_nr = Vmag .* exp(1j * theta);
S_inj      = V_cmplx_nr .* conj(Ybus * V_cmplx_nr);

% Source table — order: G1(Bus1), G2(Bus2), G3(Bus3), W1(Bus4), W2(Bus11)
src_bus_ids = [1,    2,    3,    4,    11   ];
src_vlf_mag = [1.03, 1.01, 1.01, 1.00, 1.00];  % CVS/PVS set voltage [pu]
src_R_pu    = repmat(R_gen_pu_val, 1, 5);
src_X_pu    = repmat(X_gen_pu_val, 1, 5);

n_src = length(src_bus_ids);
src_emf_abs_deg = zeros(1, n_src);
src_il_A        = zeros(n_src, 3);

for si = 1:n_src
    bi = id2idx(src_bus_ids(si));
    theta_bus_abs_rad = (Vang_deg(bi) + BUS1_ABS_DEG) * pi/180;
    Vmag_bus = Vmag(bi);
    V_bus_pu = Vmag_bus * exp(1j * theta_bus_abs_rad);

    % Complex generator current including reactive component: conj(S/V)
    I_gen_pu = conj(S_inj(bi) / V_bus_pu);
    Z_pu     = src_R_pu(si) + 1j * src_X_pu(si);
    V_emf_pu = V_bus_pu + Z_pu * I_gen_pu;
    src_emf_abs_deg(si) = angle(V_emf_pu) * 180/pi;

    % AC phasor IL at t=0 — sine convention (ia = Im[I_phasor])
    Vpk_src  = src_vlf_mag(si) * Vpk_base;
    Vpk_bus  = Vmag_bus * Vpk_base;
    V_src_pk = Vpk_src * exp(1j * (src_emf_abs_deg(si) * pi/180));
    V_bus_pk = Vpk_bus * exp(1j * theta_bus_abs_rad);
    Z_ohm    = (src_R_pu(si) + 1j * src_X_pu(si)) * Zbase;
    I_ph     = (V_src_pk - V_bus_pk) / Z_ohm;
    src_il_A(si, 1) = imag(I_ph);
    src_il_A(si, 2) = imag(I_ph * exp(-1j * 2*pi/3));
    src_il_A(si, 3) = imag(I_ph * exp(+1j * 2*pi/3));
end

% ESS filter IL for Zess_1..4
ess_il_A  = zeros(4, 3);
Z_vsg_ohm = (R_vsg_pu_val + 1j * X_vsg_sys) * Zbase;
for i = 1:4
    delta_abs_rad  = ess_delta_deg(i) * pi/180;
    theta_main_rad = theta_main_abs(i) * pi/180;
    Vpk_ess  = 1.0 * Vpk_base;
    Vpk_main = V_main(i) * Vpk_base;
    I_ess    = (Vpk_ess * exp(1j*delta_abs_rad) - Vpk_main * exp(1j*theta_main_rad)) / Z_vsg_ohm;
    ess_il_A(i, 1) = imag(I_ess);
    ess_il_A(i, 2) = imag(I_ess * exp(-1j * 2*pi/3));
    ess_il_A(i, 3) = imag(I_ess * exp(+1j * 2*pi/3));
end

%% === Package results ===
pf.converged          = converged;
pf.iterations         = iter;
pf.max_mismatch       = max_mm;
pf.Vmag               = Vmag;
pf.Vang_deg           = Vang_deg;
pf.bus_ids            = bus_ids;
pf.main_bus_ang_abs_deg = theta_main_abs;
pf.ess_delta_deg      = ess_delta_deg;
pf.sin_arg            = sin_arg;
pf.gen_delta_deg      = gen_delta_deg;   % 1×4: [G2,G3,W1,W2] terminal angles [deg]
pf.G1_terminal_deg = BUS1_ABS_DEG;              % G1 Bus1 terminal angle in abs frame [deg]
pf.G1_emf_deg         = src_emf_abs_deg(1);     % G1 EMF angle, abs frame [deg]
pf.gen_emf_deg_ext    = src_emf_abs_deg(2:5);   % [G2,G3,W1,W2] EMF angles [deg]
pf.src_il_G1_A        = src_il_A(1, :);          % Zgen_G1 IL [ia,ib,ic] A_peak
pf.src_il_G23_A       = src_il_A(2:3, :);        % Zgen_G2, Zgen_G3
pf.src_il_W12_A       = src_il_A(4:5, :);        % Zw_W1, Zw_W2
pf.ess_il_A           = ess_il_A;                 % 4×3, Zess_1..4

%% === Diagnostic printout ===
fprintf('\n--- compute_kundur_powerflow ---\n');
fprintf('  converged=%d  iterations=%d  max_mismatch=%.2e pu\n', ...
    converged, iter, max_mm);
fprintf('  P_G1(slack) = %.4f pu = %.1f MW\n', real(S_inj(id2idx(1))), real(S_inj(id2idx(1)))*Sbase/1e6);
fprintf('  Main bus angles (PF frame / absolute):\n');
ess_labels = {'ES1->Bus7','ES2->Bus8','ES3->Bus10','ES4->Bus9'};
for i = 1:4
    fprintf('    %s: θ_pf=%.3f°  θ_abs=%.3f°  sin_arg=%.4f  δ=%.3f°\n', ...
        ess_labels{i}, theta_main_pf(i), theta_main_abs(i), sin_arg(i), ess_delta_deg(i));
end
src_labels = {'G1/Bus1','G2/Bus2','G3/Bus3','W1/Bus4','W2/Bus11'};
fprintf('  Source EMF angles (absolute frame):\n');
for si = 1:5
    term_deg = Vang_deg(id2idx(src_bus_ids(si))) + BUS1_ABS_DEG;
    fprintf('    %s: terminal=%.3f°  EMF=%.3f°  ΔIL=[%.1f,%.1f,%.1f]A\n', ...
        src_labels{si}, term_deg, src_emf_abs_deg(si), src_il_A(si,:));
end
fprintf('  ESS IL peak [ia,ib,ic] (A) for Zess_1..4:\n');
for i = 1:4
    fprintf('    ES%d: [%.1f, %.1f, %.1f]\n', i, ess_il_A(i,1), ess_il_A(i,2), ess_il_A(i,3));
end
if ~converged
    fprintf('  WARNING: power flow did not converge — delta values unreliable.\n');
end

end
