function pf = compute_kundur_cvs_v3_powerflow(out_json_path)
%COMPUTE_KUNDUR_CVS_V3_POWERFLOW  Lossy NR for Kundur 16-bus paper topology
%(15 active buses, no Bus 13). v3 path — paper-faithful 4-VSG + 3-SG +
%2-wind dispatch with the 4 ESS group absorbing the system net surplus.
%
%   Phase 1.1 of 2026-04-26_kundur_cvs_v3_plan.md.
%   Spec    : quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md
%
%   Properties:
%     - 15 active buses [1..12, 14, 15, 16]; Bus 13 skipped per paper Fig.3.
%     - Lossy Π-line model (R + jωL + jωC/2 shunts) — v2 NR was lossless.
%     - Bus 1 (G1) is the angle reference AND the numerical slack for the
%       inner NR; the OUTER iteration distributes the (G1_actual − P0_paper)
%       residual equally across the 4 ESS until G1's actual injection equals
%       the paper-fixed 700 MW. After convergence, G1 carries no slack:
%       all sources match their paper / derived schedules within the same
%       1e-3 closure tolerance v2 uses.
%     - DECISION-Q1 = (a) (spec §3.1): paper dispatch preserved for G1/G2/G3
%       and W1/W2; ESS Pm0 derived from
%         P_ES_each = − (P_gen + P_wind − P_load_at_V − P_loss) / 4
%       Sign convention: Pm < 0 ⇒ ESS absorbs / charges.
%     - DECISION-Q2 = (a): wind farms are constant-P injections in NR;
%       this script does not model Type-3/4 dynamics.
%     - Output: scenarios/kundur/kundur_ic_cvs_v3.json (additive extension
%       of v2 schema; v3 reader gets SG / wind slots, v2 reader still finds
%       the 4-ESS slots intact).
%
%   PHASE 1 SCOPE GUARD: this script must NOT touch v2 files, NE39 paths,
%   SAC code, the env, or shared bridge. It only writes the v3 IC JSON.

if nargin < 1
    this_dir = fileparts(mfilename('fullpath'));   % .../matlab_scripts
    repo_dir = fileparts(this_dir);                % .../scenarios/kundur
    out_json_path = fullfile(repo_dir, 'kundur_ic_cvs_v3.json');
end

%% ===== System parameters (LOCKED, must match build_kundur_cvs_v3.m) =====
fn        = 50;                          % Hz
wn        = 2*pi*fn;                     % rad/s
Sbase     = 100e6;                       % VA = 100 MVA
Vbase     = 230e3;                       % V (single voltage level)
Zbase     = Vbase^2 / Sbase;             % Ω = 529

% Source internal impedances on system base
SG_SN     = 900e6;
VSG_SN    = 200e6;
W2_SN     = 200e6;                       % W2 nameplate (informational; const-P in NR)
X_gen_sys = 0.30 * (Sbase / SG_SN);      % 0.0333 pu — G1, G2, G3
X_vsg_sys = 0.30 * (Sbase / VSG_SN);     % 0.15   pu — ES1..4
R_gen_sys = 0.003 * (Sbase / SG_SN);     % 3.33e-4 pu
R_vsg_sys = 0.003 * (Sbase / VSG_SN);    % 1.50e-3 pu

% Per-km line constants (verbatim from build_powerlib_kundur.m:230–238)
R_std   = 0.053;     L_std   = 1.41e-3;  C_std   = 0.009e-6;
R_short = 0.01;      L_short = 0.5e-3;   C_short = 0.009e-6;

% Bus 1 simulation-frame absolute angle (matches v2 / powerlib NR convention)
BUS1_ABS_DEG = 20.0;

%% ===== Bus inventory: 15 active buses, ID list skips 13 =====
% Task 1 (2026-04-28): Bus 11 removed; W2 moved to Bus 8 directly per
% paper line 894. System reduced from 15 active buses to 14.
bus_ids   = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 16]';
bus_lbl   = {'Bus1_G1','Bus2_G2','Bus3_G3','Bus4_W1','Bus5','Bus6', ...
             'Bus7_load','Bus8_W2','Bus9_load','Bus10', ...
             'Bus12_ES1','Bus14_ES3','Bus15_ES4','Bus16_ES2'}';
n_bus     = numel(bus_ids);
id2idx    = zeros(1, max(bus_ids));
for k = 1:n_bus
    id2idx(bus_ids(k)) = k;
end

SLACK = 1; PV = 2; PQ = 3;

%% ===== Branch list (verbatim §4 of spec) =====
% {from_bus, to_bus, length_km, R_per_km, L_per_km, C_per_km}
line_defs = {
    1,  5,    5, R_std,   L_std,   C_std;
    2,  6,    5, R_std,   L_std,   C_std;
    3, 10,    5, R_std,   L_std,   C_std;
    4,  9,    5, R_std,   L_std,   C_std;
    5,  6,   25, R_std,   L_std,   C_std;
    5,  6,   25, R_std,   L_std,   C_std;
    6,  7,   10, R_std,   L_std,   C_std;
    6,  7,   10, R_std,   L_std,   C_std;
    7,  8,  110, R_std,   L_std,   C_std;
    7,  8,  110, R_std,   L_std,   C_std;
    7,  8,  110, R_std,   L_std,   C_std;
    8,  9,   10, R_std,   L_std,   C_std;
    8,  9,   10, R_std,   L_std,   C_std;
    9, 10,   25, R_std,   L_std,   C_std;
    9, 10,   25, R_std,   L_std,   C_std;
    7, 12,    1, R_short, L_short, C_short;
    8, 16,    1, R_short, L_short, C_short;
   10, 14,    1, R_short, L_short, C_short;
    9, 15,    1, R_short, L_short, C_short;
};

%% ===== Y-bus (Π model) =====
Ybus = zeros(n_bus, n_bus);
n_lines = size(line_defs, 1);
branch_R_pu = zeros(n_lines, 1);
branch_X_pu = zeros(n_lines, 1);
branch_y_pu = zeros(n_lines, 1);
branch_from = zeros(n_lines, 1);
branch_to   = zeros(n_lines, 1);
for li = 1:n_lines
    fb = line_defs{li, 1};
    tb = line_defs{li, 2};
    L  = line_defs{li, 3};
    Rk = line_defs{li, 4};
    Lk = line_defs{li, 5};
    Ck = line_defs{li, 6};

    R_tot = Rk * L;                       % Ω
    X_tot = wn * Lk * L;                  % Ω
    B_tot = wn * Ck * L;                  % S

    z_pu  = (R_tot + 1j*X_tot) / Zbase;   % series impedance pu
    y_pu  = 1 / z_pu;
    ysh   = 1j * B_tot * Zbase / 2;       % half shunt at each end (pu)

    fi = id2idx(fb);
    ti = id2idx(tb);

    Ybus(fi, fi) = Ybus(fi, fi) + y_pu + ysh;
    Ybus(ti, ti) = Ybus(ti, ti) + y_pu + ysh;
    Ybus(fi, ti) = Ybus(fi, ti) - y_pu;
    Ybus(ti, fi) = Ybus(ti, fi) - y_pu;

    branch_R_pu(li) = real(z_pu);
    branch_X_pu(li) = imag(z_pu);
    branch_y_pu(li) = y_pu;
    branch_from(li) = fi;
    branch_to(li)   = ti;
end

%% ===== Bus data (paper dispatch + load + shunt cap, sys-pu) =====
% Loads enter as constant PQ at bus voltage (industry-standard NR). The
% Simulink build uses constant-Z; the V²-effect mismatch is bounded by
% the closure tol (=1e-3) just like in v2 (compute_kundur_cvs_powerflow.m).
%
% Bus 7: load 967 MW + 100 Mvar inductive; shunt cap 200 Mvar
%        Q_net at bus = 100 (inductive consumption) − 200 (cap injection)
%                     = −100 Mvar net cap → P_sch = −9.67, Q_sch = +1.0
% Bus 9: load 1767 MW + 100 Mvar; shunt cap 350 Mvar
%        Q_net = 100 − 350 = −250 Mvar cap → P_sch = −17.67, Q_sch = +2.5

% Task 2 (2026-04-28, paper line 993): Bus 14 has 248 MW pre-engaged load
% (LS1 disturbance is the "sudden reduction" of this load mid-episode).
% P_LS1_LOAD enters as a fixed PQ load offset on Bus 14; net injection at
% Bus 14 = P_ES_each (ES3 generation) − P_LS1_LOAD (pre-engaged load).
P_LS1_LOAD = 2.48;   % 248 MW = 2.48 sys-pu

% Initial ESS group dispatch — lossless guess; corrected by outer loop
P_ES_each_init = -((7.00 + 7.00 + 7.19) + (7.00 + 1.00) - (9.67 + 17.67 + P_LS1_LOAD)) / 4;
% = -(21.19 + 8.00 - 29.82)/4 = +0.6300/4 = +0.1575 sys-pu (Task 2: ESS sign flip absorb→generate)

V_BUS_DEFAULT = 1.00;

%      [bus_type V_spec   P_sch                Q_sch]
bus_data = zeros(n_bus, 4);
bus_data(id2idx(1),  :) = [SLACK, 1.03, 0,                       0  ];   % G1 numerical slack
bus_data(id2idx(2),  :) = [PV,    1.01, 7.00,                    0  ];   % G2 700 MW
bus_data(id2idx(3),  :) = [PV,    1.01, 7.19,                    0  ];   % G3 719 MW
bus_data(id2idx(4),  :) = [PV,    1.00, 7.00,                    0  ];   % W1 700 MW const-P
bus_data(id2idx(5),  :) = [PQ,    V_BUS_DEFAULT, 0,              0  ];   % junction
bus_data(id2idx(6),  :) = [PQ,    V_BUS_DEFAULT, 0,              0  ];   % junction
bus_data(id2idx(7),  :) = [PQ,    V_BUS_DEFAULT, -9.67,         +1.0];   % load+shunt
bus_data(id2idx(8),  :) = [PV,    1.00, 1.00,                    0  ];   % W2 100 MW const-P (Task 1: moved from Bus 11)
bus_data(id2idx(9),  :) = [PQ,    V_BUS_DEFAULT, -17.67,        +2.5];   % load+shunt
bus_data(id2idx(10), :) = [PQ,    V_BUS_DEFAULT, 0,              0  ];   % junction
bus_data(id2idx(12), :) = [PV,    1.00, P_ES_each_init,          0  ];   % ES1
bus_data(id2idx(14), :) = [PV,    1.00, P_ES_each_init - P_LS1_LOAD, 0];   % ES3 + 248 MW LS1 pre-engaged load (Task 2)
bus_data(id2idx(15), :) = [PV,    1.00, P_ES_each_init,          0  ];   % ES4
bus_data(id2idx(16), :) = [PV,    1.00, P_ES_each_init,          0  ];   % ES2

bus_type = bus_data(:, 1);
V_spec   = bus_data(:, 2);
P_sch    = bus_data(:, 3);
Q_sch    = bus_data(:, 4);

% Reference indices used by NR
slack_idx = find(bus_type == SLACK);
pv_idx    = find(bus_type == PV);
pq_idx    = find(bus_type == PQ);
non_slack = [pv_idx; pq_idx];

ess_bus_ids = [12, 16, 14, 15];
ess_idx     = arrayfun(@(b) id2idx(b), ess_bus_ids);   % rows in bus arrays
% Task 2: Bus 14 (ES3) has the 248 MW LS1 pre-engaged load. The outer-loop
% updates bus 14's P_sch with offset = (P_ES_each − P_LS1_LOAD); other ESS
% buses keep P_sch = P_ES_each.
ess_load_offset = double(ess_bus_ids == 14)' * P_LS1_LOAD;   % column: [0; 0; 2.48; 0]

%% ===== Outer iteration: G1 actual P-injection → 7.00 sys-pu =====
P_G1_paper = 7.00;
outer_max  = 30;
outer_tol  = 1e-9;
inner_tol  = 1e-10;
inner_max  = 60;

P_ES_each      = P_ES_each_init;
outer_history  = zeros(outer_max, 3);  % [iter, G1_inj, P_ES_each]
outer_iter     = 0;
outer_converged = false;
inner_iter_total = 0;
last_iter      = 0;
last_max_mm    = Inf;
P_loss_pu      = NaN;
Vmag_final     = [];
theta_final    = [];
S_final        = [];

for outer = 1:outer_max
    outer_iter = outer;
    P_sch(ess_idx) = P_ES_each - ess_load_offset;   % Task 2: bus 14 net = P_ES_each - P_LS1_LOAD

    % --- Inner Newton-Raphson (G1 = slack) ---
    theta = zeros(n_bus, 1);
    Vmag  = V_spec;
    G_y   = real(Ybus);
    B_y   = imag(Ybus);

    inner_converged = false;
    last_iter   = 0;
    last_max_mm = Inf;
    for it = 1:inner_max
        last_iter = it;
        Vc = Vmag .* exp(1j * theta);
        Sc = Vc .* conj(Ybus * Vc);
        Pc = real(Sc); Qc = imag(Sc);

        dP = P_sch - Pc;
        dQ = Q_sch - Qc;

        mm = [dP(non_slack); dQ(pq_idx)];
        last_max_mm = max(abs(mm));
        if last_max_mm < inner_tol
            inner_converged = true;
            break;
        end

        H = zeros(n_bus); N = zeros(n_bus);
        Jm = zeros(n_bus); L = zeros(n_bus);
        for i = 1:n_bus
            Vi = Vmag(i);
            for j = 1:n_bus
                Vj = Vmag(j);
                dth = theta(i) - theta(j);
                Gij = G_y(i, j); Bij = B_y(i, j);
                if i ~= j
                    H(i, j)  =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
                    N(i, j)  =  Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                    Jm(i, j) = -Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                    L(i, j)  =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
                end
            end
            H(i, i)  = -Qc(i) - B_y(i, i)*Vi^2;
            N(i, i)  =  Pc(i) + G_y(i, i)*Vi^2;
            Jm(i, i) =  Pc(i) - G_y(i, i)*Vi^2;
            L(i, i)  =  Qc(i) - B_y(i, i)*Vi^2;
        end

        Jac = [H(non_slack, non_slack), N(non_slack, pq_idx); ...
               Jm(pq_idx,    non_slack), L(pq_idx,    pq_idx)];
        dx = Jac \ mm;

        n_th = numel(non_slack);
        d_theta = dx(1:n_th);
        d_Vrel  = dx(n_th + 1:end);

        theta(non_slack) = theta(non_slack) + d_theta;
        Vmag(pq_idx)     = Vmag(pq_idx) .* (1 + d_Vrel);
    end
    inner_iter_total = inner_iter_total + last_iter;

    if ~inner_converged
        warning('compute_kundur_cvs_v3_powerflow:innerNotConverged', ...
            'Inner NR did not converge at outer iter %d (max_mm=%.3e).', ...
            outer, last_max_mm);
        break;
    end

    % --- Read G1 actual injection and re-distribute deviation ---
    Vc_now = Vmag .* exp(1j * theta);
    Sc_now = Vc_now .* conj(Ybus * Vc_now);
    G1_actual = real(Sc_now(slack_idx));
    delta = G1_actual - P_G1_paper;

    outer_history(outer, :) = [outer, G1_actual, P_ES_each];

    % Always store latest converged state so post-loop diagnostics work
    % even if the outer loop fails to converge.
    Vmag_final  = Vmag;
    theta_final = theta;
    S_final     = Sc_now;

    if abs(delta) < outer_tol
        outer_converged = true;
        break;
    end

    % Sign derivation: with ESS as PV and G1 as numerical slack,
    %   P_slack = P_loss + (ΣP_load − ΣP_other_PV) − 4·P_ES_each
    % To drive P_slack down by `delta` (= P_slack − P_G1_paper > 0 when G1
    % is over-absorbing), P_ES_each must become LESS negative — i.e. add
    % delta/4. Prior version subtracted, which is divergent.
    P_ES_each = P_ES_each + delta / 4;
end
outer_history = outer_history(1:outer_iter, :);

if ~outer_converged
    warning('compute_kundur_cvs_v3_powerflow:outerNotConverged', ...
        'Outer loop did not converge in %d iterations (last delta=%.3e).', ...
        outer_max, delta);
end

%% ===== Total losses (sum of per-line conductor losses) =====
P_loss_pu = 0;
for li = 1:n_lines
    fi = branch_from(li); ti = branch_to(li);
    Vf = Vmag_final(fi) * exp(1j * theta_final(fi));
    Vt = Vmag_final(ti) * exp(1j * theta_final(ti));
    I_branch = (Vf - Vt) * branch_y_pu(li);   % series current (pu)
    P_loss_pu = P_loss_pu + branch_R_pu(li) * abs(I_branch)^2;
end

%% ===== Closure: aggregate balance + per-source schedule check =====
% Real loads (Bus 7, Bus 9, and Task 2 Bus 14 LS1 pre-engaged 248 MW).
% Bus 14 LS1 load is bundled into P_sch[bus14] = (P_ES_each − P_LS1_LOAD);
% report it as a separate explicit load entry for physical clarity.
P_load_total = sum(P_sch([id2idx(7), id2idx(9)])) + (-P_LS1_LOAD);   % negative = consumption
P_gen_paper  = P_G1_paper + 7.00 + 7.19;   % 21.19 sys-pu (3 SG only)
P_wind_paper = 7.00 + 1.00;                % 8.00 sys-pu (W1 + W2)
% P_ess_total here = ESS group GENERATION (sum of P_ES_each over 4 ESS),
% NOT the bus-net at ESS buses. Bus net at bus 14 = P_ES_each − P_LS1_LOAD
% (the LS1 load is already reported in P_load_total to avoid double counting).
P_ess_total  = 4 * P_ES_each;

% Verify each ESS injection equals scheduled P_sch (per-bus, with offset for
% Task 2 Bus 14 LS1 load).
ess_per_bus_inj = real(S_final(ess_idx));
ess_sched_dev   = max(abs(ess_per_bus_inj - (P_ES_each - ess_load_offset)));

% Hidden-slack check: G1 actual must equal paper 7.00 within outer_tol
G1_residual = abs(real(S_final(slack_idx)) - P_G1_paper);

% Aggregate identity: ΣP_gen_paper + ΣP_wind + ΣP_ESS + ΣP_load = P_loss
P_aggregate_residual = (P_gen_paper + P_wind_paper + P_ess_total + P_load_total) - P_loss_pu;
closure_residual = abs(P_aggregate_residual);
closure_ok = closure_residual < 1e-3;

%% ===== Internal EMF / delta angles for dynamic sources =====
% For each dynamic source (G1/G2/G3 + ES1..4), compute internal EMF angle
% (CVS swing-eq state) using V_emf = V_term + j·X_internal · I_inj.
% Wind farms (W1/W2) have no swing-eq; report only terminal angle.

dynamic_src_buses = [1, 2, 3, 12, 16, 14, 15];      % G1, G2, G3, ES1, ES2, ES3, ES4
dynamic_src_names = {'G1', 'G2', 'G3', 'ES1', 'ES2', 'ES3', 'ES4'};
dynamic_src_X     = [X_gen_sys, X_gen_sys, X_gen_sys, ...
                     X_vsg_sys, X_vsg_sys, X_vsg_sys, X_vsg_sys];
dynamic_src_R     = [R_gen_sys, R_gen_sys, R_gen_sys, ...
                     R_vsg_sys, R_vsg_sys, R_vsg_sys, R_vsg_sys];

n_dyn = numel(dynamic_src_buses);
dyn_term_v_pu  = zeros(n_dyn, 1);
dyn_term_a_rad = zeros(n_dyn, 1);
dyn_emf_v_pu   = zeros(n_dyn, 1);
dyn_emf_a_rad  = zeros(n_dyn, 1);
dyn_pinj_sys   = zeros(n_dyn, 1);
dyn_qinj_sys   = zeros(n_dyn, 1);
for s = 1:n_dyn
    bi = id2idx(dynamic_src_buses(s));
    th_abs_rad = theta_final(bi) + BUS1_ABS_DEG * pi / 180;
    Vt = Vmag_final(bi) * exp(1j * th_abs_rad);
    % Task 2 (paper line 993): bus 14 has 248 MW pre-engaged load (LS1).
    % S_final at bus 14 is the BUS NET = ES3 gen − P_LS1_LOAD. To get the
    % ES3 source's own gen + V_emf, undo the local load offset.
    if dynamic_src_buses(s) == 14
        P_local_load = P_LS1_LOAD;
    else
        P_local_load = 0.0;
    end
    Si_gen = (real(S_final(bi)) + P_local_load) + 1j * imag(S_final(bi));
    Ii = conj(Si_gen / (Vmag_final(bi) * exp(1j * theta_final(bi))));
    Z  = dynamic_src_R(s) + 1j * dynamic_src_X(s);
    V_emf = Vt + Z * Ii;

    dyn_term_v_pu(s)  = abs(Vt);
    dyn_term_a_rad(s) = th_abs_rad;
    dyn_emf_v_pu(s)   = abs(V_emf);
    dyn_emf_a_rad(s)  = angle(V_emf);
    dyn_pinj_sys(s)   = real(Si_gen);
    dyn_qinj_sys(s)   = imag(Si_gen);
end

% Wind farm terminal info
wind_buses = [4, 8];   % Task 1 (2026-04-28): W2 moved Bus 11 → Bus 8
wind_names = {'W1', 'W2'};
n_wind = numel(wind_buses);
wind_term_v_pu  = zeros(n_wind, 1);
wind_term_a_rad = zeros(n_wind, 1);
for w = 1:n_wind
    bi = id2idx(wind_buses(w));
    wind_term_v_pu(w)  = Vmag_final(bi);
    wind_term_a_rad(w) = theta_final(bi) + BUS1_ABS_DEG * pi / 180;
end

%% ===== Pack pf result struct =====
pf.converged          = outer_converged;
pf.outer_iterations   = outer_iter;
pf.inner_iterations_total = inner_iter_total;
pf.max_mismatch_pu    = last_max_mm;
pf.outer_history      = outer_history;

pf.bus_ids            = bus_ids;
pf.bus_lbl            = bus_lbl;
pf.V_mag_pu           = Vmag_final;
pf.V_ang_rad          = theta_final;
pf.V_ang_abs_rad      = theta_final + BUS1_ABS_DEG * pi / 180;
pf.S_inj_pu           = S_final;
pf.P_loss_pu          = P_loss_pu;
pf.P_load_total_pu    = P_load_total;
pf.P_gen_paper_pu     = P_gen_paper;
pf.P_wind_paper_pu    = P_wind_paper;
pf.P_ess_total_pu     = P_ess_total;
pf.P_ES_each_pu       = P_ES_each;
pf.G1_residual_pu     = G1_residual;
pf.aggregate_residual_pu = closure_residual;
pf.closure_ok         = closure_ok;

pf.ess_bus_ids        = ess_bus_ids(:);
pf.ess_per_bus_inj_pu = ess_per_bus_inj;
pf.ess_sched_dev_pu   = ess_sched_dev;

pf.dyn_src_names      = dynamic_src_names;
pf.dyn_src_buses      = dynamic_src_buses;
pf.dyn_term_v_pu      = dyn_term_v_pu;
pf.dyn_term_a_rad     = dyn_term_a_rad;
pf.dyn_emf_v_pu       = dyn_emf_v_pu;
pf.dyn_emf_a_rad      = dyn_emf_a_rad;
pf.dyn_pinj_sys_pu    = dyn_pinj_sys;
pf.dyn_qinj_sys_pu    = dyn_qinj_sys;
pf.wind_names         = wind_names;
pf.wind_term_v_pu     = wind_term_v_pu;
pf.wind_term_a_rad    = wind_term_a_rad;

%% ===== JSON output (additive extension of v2 schema) =====
src_text = fileread([mfilename('fullpath') '.m']);
src_hash = local_sha256(src_text);

ic = struct();
ic.schema_version          = 3;
ic.source                  = mfilename();
ic.source_hash             = ['sha256:' src_hash];
ic.timestamp               = char(datetime('now', 'Format', ...
    'yyyy-MM-dd''T''HH:mm:ssXXX', 'TimeZone', 'local'));
ic.topology_variant        = 'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged';
ic.decisions               = struct( ...
    'q1_ess_dispatch',  '(a) preserve paper dispatch; ESS group absorbs surplus', ...
    'q2_wind_model',    '(a) const-power PVS; no Type-3/4');

ic.powerflow = struct( ...
    'converged',                outer_converged, ...
    'outer_iterations',         outer_iter, ...
    'inner_iterations_total',   inner_iter_total, ...
    'max_mismatch_pu',          last_max_mm, ...
    'closure_ok',               closure_ok, ...
    'closure_residual_pu',      closure_residual, ...
    'closure_tolerance_pu',     1e-3, ...
    'closure_residual_origin',  'aggregate_balance_const_PQ_load_NR_to_constZ_build_residual', ...
    'g1_residual_pu',           G1_residual, ...
    'g1_target_sys_pu',         P_G1_paper);

ic.global_balance = struct( ...
    'p_gen_paper_sys_pu',   P_gen_paper, ...
    'p_wind_paper_sys_pu',  P_wind_paper, ...
    'p_load_total_sys_pu',  P_load_total, ...
    'p_loss_sys_pu',        P_loss_pu, ...
    'p_loss_pct_load',      100 * P_loss_pu / abs(P_load_total), ...
    'p_ess_total_sys_pu',   P_ess_total, ...
    'p_es_each_sys_pu',     P_ES_each, ...
    'p_es_each_mw',         P_ES_each * Sbase / 1e6, ...
    'p_es_each_vsg_pu',     P_ES_each * (Sbase / VSG_SN), ...
    'no_hidden_slack',      G1_residual < 1e-6);

% --- v2-compatible 4-ESS slots (filled in ES1..ES4 order = bus 12,16,14,15) ---
ess_dyn_idx = [4, 5, 6, 7];   % positions of ES1..ES4 in dynamic_src_*
ic.vsg_internal_emf_angle_rad      = dyn_emf_a_rad(ess_dyn_idx)';
ic.vsg_terminal_voltage_mag_pu     = dyn_term_v_pu(ess_dyn_idx)';
ic.vsg_terminal_voltage_angle_rad  = dyn_term_a_rad(ess_dyn_idx)';
ic.vsg_pm0_pu                      = dyn_pinj_sys(ess_dyn_idx)';
ic.vsg_pe_target_pu                = dyn_pinj_sys(ess_dyn_idx)';
ic.vsg_emf_mag_pu                  = dyn_emf_v_pu(ess_dyn_idx)';

% --- v3-only SG slots ---
sg_dyn_idx = [1, 2, 3];
ic.sg_names                        = {dynamic_src_names{sg_dyn_idx}};
ic.sg_internal_emf_angle_rad       = dyn_emf_a_rad(sg_dyn_idx)';
ic.sg_terminal_voltage_mag_pu      = dyn_term_v_pu(sg_dyn_idx)';
ic.sg_terminal_voltage_angle_rad   = dyn_term_a_rad(sg_dyn_idx)';
ic.sg_pm0_sys_pu                   = dyn_pinj_sys(sg_dyn_idx)';
ic.sg_emf_mag_pu                   = dyn_emf_v_pu(sg_dyn_idx)';

% --- v3-only wind slots ---
ic.wind_names                      = wind_names;
ic.wind_terminal_voltage_mag_pu    = wind_term_v_pu';
ic.wind_terminal_voltage_angle_rad = wind_term_a_rad';
ic.wind_pref_sys_pu                = [7.00, 1.00];

ic.bus_voltages = struct();
for k = 1:n_bus
    fld = matlab.lang.makeValidName(bus_lbl{k});
    ic.bus_voltages.(fld) = struct( ...
        'bus_id',        bus_ids(k), ...
        'v_mag_pu',      Vmag_final(k), ...
        'v_ang_rad_pf',  theta_final(k), ...
        'v_ang_rad_abs', theta_final(k) + BUS1_ABS_DEG * pi / 180);
end

ic.x_v_pu = struct( ...
    'sg_internal',     X_gen_sys, ...
    'vsg_internal',    X_vsg_sys, ...
    'wind_const_power', NaN);

ic.physical_invariants_checked = { ...
    'p_balance_per_bus', ...
    'global_balance_no_hidden_slack', ...
    'pi_line_lossy_NR_with_R_jwL_jwC_2', ...
    'ess_group_distributed_slack_resolved'};

%% ===== Write JSON =====
out_dir = fileparts(out_json_path);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(out_json_path, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);

%% ===== Diagnostic print (RESULT: prefixes for important_lines) =====
fprintf('\n--- compute_kundur_cvs_v3_powerflow (lossy NR, v3 16-bus) ---\n');
fprintf('RESULT: outer_converged=%d  outer_iter=%d  inner_iter_total=%d\n', ...
    outer_converged, outer_iter, inner_iter_total);
fprintf('RESULT: inner_max_mismatch_pu=%.3e (tol=%.0e)\n', last_max_mm, inner_tol);
fprintf('RESULT: G1_residual_pu=%.3e  G1_target_sys_pu=%.4f\n', G1_residual, P_G1_paper);
fprintf('RESULT: closure_ok=%d  aggregate_residual_pu=%.3e (tol=1e-3)\n', closure_ok, closure_residual);
fprintf('RESULT: P_gen_paper_sys_pu=%.4f  P_load_total_sys_pu=%.4f\n', P_gen_paper, P_load_total);
fprintf('RESULT: P_loss_sys_pu=%.4f  (%.2f%% of |load|)\n', ...
    P_loss_pu, 100 * P_loss_pu / abs(P_load_total));
fprintf('RESULT: P_ess_total_sys_pu=%.4f  P_ES_each_sys_pu=%.4f  (%.2f MW, %.4f vsg-pu)\n', ...
    P_ess_total, P_ES_each, P_ES_each * Sbase / 1e6, P_ES_each * (Sbase / VSG_SN));
fprintf('RESULT: hidden_slack_check no_hidden_slack=%d (G1_residual=%.3e < 1e-6)\n', ...
    G1_residual < 1e-6, G1_residual);

fprintf('\n  Bus  | type   |V|(pu)  ang_pf(deg)  ang_abs(deg)  P(pu)     Q(pu)\n');
for k = 1:n_bus
    if bus_type(k) == SLACK, tlbl = 'SLK*';
    elseif bus_type(k) == PV, tlbl = 'PV';
    else, tlbl = 'PQ'; end
    fprintf('  %-12s | %-4s | %.4f  %+8.3f    %+8.3f    %+.4f   %+.4f\n', ...
        bus_lbl{k}, tlbl, Vmag_final(k), ...
        theta_final(k) * 180/pi, ...
        (theta_final(k) + BUS1_ABS_DEG * pi/180) * 180/pi, ...
        real(S_final(k)), imag(S_final(k)));
end

fprintf('\n  Dynamic source EMF angles (absolute simulation frame, deg):\n');
for s = 1:n_dyn
    fprintf('  %-4s @ Bus %2d : V_term=%.4f∠%+8.3f°   V_emf=%.4f∠%+8.3f°   P=%+.4f Q=%+.4f\n', ...
        dynamic_src_names{s}, dynamic_src_buses(s), ...
        dyn_term_v_pu(s), dyn_term_a_rad(s) * 180/pi, ...
        dyn_emf_v_pu(s), dyn_emf_a_rad(s) * 180/pi, ...
        dyn_pinj_sys(s), dyn_qinj_sys(s));
end
fprintf('  Wind:\n');
for w = 1:n_wind
    fprintf('  %-4s @ Bus %2d : V_term=%.4f∠%+8.3f°  P_const=%.4f sys-pu\n', ...
        wind_names{w}, wind_buses(w), ...
        wind_term_v_pu(w), wind_term_a_rad(w) * 180/pi, ...
        ic.wind_pref_sys_pu(w));
end

fprintf('\n  Outer-loop history (G1_actual, P_ES_each):\n');
for r = 1:outer_iter
    fprintf('    %2d  G1=%+.6f sys-pu   P_ES_each=%+.6f sys-pu\n', ...
        outer_history(r, 1), outer_history(r, 2), outer_history(r, 3));
end

fprintf('\nRESULT: dyn_emf_a_deg_min=%+.4f  dyn_emf_a_deg_max=%+.4f\n', ...
    min(dyn_emf_a_rad) * 180/pi, max(dyn_emf_a_rad) * 180/pi);
fprintf('RESULT: V_mag_min=%.4f  V_mag_max=%.4f\n', min(Vmag_final), max(Vmag_final));
fprintf('RESULT: V_ang_pf_deg_min=%+.4f  V_ang_pf_deg_max=%+.4f\n', ...
    min(theta_final) * 180/pi, max(theta_final) * 180/pi);
fprintf('RESULT: ESS_per_bus_dispatch_dev_pu=%.3e\n', ess_sched_dev);
fprintf('RESULT: output_json=%s\n', out_json_path);

end

% ----- helper -----
function h = local_sha256(text)
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(uint8(text));
raw = md.digest();
u   = typecast(int8(raw), 'uint8');
hex = lower(dec2hex(u, 2));
h   = reshape(hex.', 1, []);
end
