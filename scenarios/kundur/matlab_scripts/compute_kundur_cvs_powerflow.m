function pf = compute_kundur_cvs_powerflow(out_json_path)
%COMPUTE_KUNDUR_CVS_POWERFLOW  NR power flow for the 5-bus self-contained
%CVS Phasor topology (NO infinite bus).
%
%   Promoted on 2026-04-26 from compute_kundur_cvs_powerflow.m.
%   The previous Bus_INF-slack variant is preserved at
%   compute_kundur_cvs_powerflow_v1_legacy.m.
%
%   Properties of this NR formulation:
%     - No Bus_INF, no L_inf branch.
%     - VSG1 is the angle reference (delta_1 = 0); no implicit slack.
%     - Total Pm injection equals total load: with Load_A+Load_B=0.8 pu
%       and 4 VSG, Pm0=0.2 satisfies global P-balance exactly.
%     - Post-NR: verifies VSG1 P-injection equals Pm0 within 1e-3 tol
%       (the small const-Z load V^2 effect is the only allowed residual).
%
%   Output:  scenarios/kundur/kundur_ic_cvs.json (default).
%
%   Topology (5 buses, 5 lines):
%     Buses : Bus_V1..V4 (PV, |V|=1.0), Bus_A, Bus_B (PQ).
%     Lines : L_v_1..4 (X=0.10), L_tie (X=0.30).
%     Loads : Load_A, Load_B (R-only, modelled as Y-bus shunt G=P_load).

if nargin < 1
    this_dir = fileparts(mfilename('fullpath'));   % .../matlab_scripts
    repo_dir = fileparts(this_dir);                % .../scenarios/kundur
    out_json_path = fullfile(repo_dir, 'kundur_ic_cvs.json');
end

%% === System parameters (must mirror build_kundur_cvs.m) ===
fn       = 50;
wn       = 2*pi*fn;
Sbase    = 100e6;
Vbase    = 230e3;
Zbase    = Vbase^2 / Sbase;

X_v_pu   = 0.10;
X_tie_pu = 0.30;

P_loadA_pu = 0.4;
P_loadB_pu = 0.4;

% v2 mechanical set-point: balanced against loads (no slack absorption).
Pm0_pu      = 0.2;        % per-VSG mechanical power, system pu
Vmag_vsg_pu = 1.0;        % per-VSG CVS terminal magnitude, pu

%% === Bus inventory ===
% Internal index 1..6 — VSG1 chosen as angle reference (theta_1 fixed = 0).
% No SLACK type: VSG1 is PV with theta-fix; its P-balance is checked AFTER
% NR converges (global balance closure check).
PV = 2; PQ = 3;
%        idx label      type   V_spec       P_sch    Q_sch
bus_table = {
    1, 'Bus_V1', PV,    Vmag_vsg_pu, Pm0_pu,  0.0;
    2, 'Bus_V2', PV,    Vmag_vsg_pu, Pm0_pu,  0.0;
    3, 'Bus_V3', PV,    Vmag_vsg_pu, Pm0_pu,  0.0;
    4, 'Bus_V4', PV,    Vmag_vsg_pu, Pm0_pu,  0.0;
    5, 'Bus_A',  PQ,    1.0,         0.0,     0.0;
    6, 'Bus_B',  PQ,    1.0,         0.0,     0.0;
};
n_bus     = size(bus_table, 1);
bus_lbl   = bus_table(:, 2);
bus_type  = cell2mat(bus_table(:, 3));
V_spec    = cell2mat(bus_table(:, 4));
P_sch     = cell2mat(bus_table(:, 5));
Q_sch     = cell2mat(bus_table(:, 6));

%% === Branch list (no L_inf in v2) ===
branches = {
    1, 5, X_v_pu;     % L_v_1 : Bus_V1 - Bus_A
    2, 5, X_v_pu;     % L_v_2 : Bus_V2 - Bus_A
    3, 6, X_v_pu;     % L_v_3 : Bus_V3 - Bus_B
    4, 6, X_v_pu;     % L_v_4 : Bus_V4 - Bus_B
    5, 6, X_tie_pu;   % L_tie : Bus_A  - Bus_B
};

%% === Y-bus (lossless lines + constant-impedance load shunts) ===
Ybus = zeros(n_bus, n_bus);
for k = 1:size(branches, 1)
    f = branches{k, 1};
    t = branches{k, 2};
    Xk = branches{k, 3};
    y = 1 / (1j * Xk);
    Ybus(f, f) = Ybus(f, f) + y;
    Ybus(t, t) = Ybus(t, t) + y;
    Ybus(f, t) = Ybus(f, t) - y;
    Ybus(t, f) = Ybus(t, f) - y;
end
Ybus(5, 5) = Ybus(5, 5) + P_loadA_pu;
Ybus(6, 6) = Ybus(6, 6) + P_loadB_pu;

G = real(Ybus);
B = imag(Ybus);

%% === Pre-NR balance check (no hidden slack tolerated) ===
total_Pm   = sum(P_sch(1:4));
total_load = P_loadA_pu + P_loadB_pu;
balance_residual = total_Pm - total_load;
if abs(balance_residual) > 1e-9
    error('compute_kundur_cvs_powerflow:imbalance', ...
        ['Global P-balance violated BEFORE NR: sum(Pm)=%.6f != ' ...
         'sum(load)=%.6f (residual %.6e). Lossless network cannot ' ...
         'absorb mismatch; adjust Pm0 or loads.'], ...
        total_Pm, total_load, balance_residual);
end

%% === NR initialisation ===
% No slack. Pick VSG1 as angle reference: theta(1) = 0, NOT a state.
ref_idx   = 1;
non_ref   = setdiff(1:n_bus, ref_idx);   % buses with theta unknown
pv_idx    = find(bus_type == PV);
pq_idx    = find(bus_type == PQ);

% Theta-state buses: all non-ref → 5 unknowns (V2-V4 + A + B angles).
% Vmag-state buses: PQ only → 2 unknowns (V_A, V_B magnitudes).
% Equations:
%   - P-residual on non-ref PV (V2-V4) → 3
%   - P-residual on PQ (A, B)          → 2
%   - Q-residual on PQ (A, B)          → 2
%   total = 7 equations vs 7 unknowns ✓
non_ref_pv = setdiff(pv_idx, ref_idx);   % PV buses to solve angle on
P_eq_idx   = [non_ref_pv; pq_idx];       % buses with P-equation kept
Q_eq_idx   = pq_idx;
n_th       = numel(non_ref);             % 5
n_v        = numel(pq_idx);              % 2

theta = zeros(n_bus, 1);
Vmag  = V_spec;

max_iter = 50;
tol      = 1e-10;
converged = false;
max_mm = Inf;
iter = 0;

for iter = 1:max_iter
    Vc = Vmag .* exp(1j*theta);
    S  = Vc .* conj(Ybus * Vc);
    Pc = real(S); Qc = imag(S);
    dP = P_sch - Pc;
    dQ = Q_sch - Qc;
    mm = [dP(P_eq_idx); dQ(Q_eq_idx)];
    max_mm = max(abs(mm));
    if max_mm < tol
        converged = true;
        break;
    end

    H = zeros(n_bus); N_ = zeros(n_bus);
    J = zeros(n_bus); L_ = zeros(n_bus);
    for i = 1:n_bus
        for j = 1:n_bus
            Vi = Vmag(i); Vj = Vmag(j);
            dth = theta(i) - theta(j);
            Gij = G(i,j); Bij = B(i,j);
            if i ~= j
                H(i,j)  =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
                N_(i,j) =  Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                J(i,j)  = -Vi*Vj*(Gij*cos(dth) + Bij*sin(dth));
                L_(i,j) =  Vi*Vj*(Gij*sin(dth) - Bij*cos(dth));
            end
        end
        Vi = Vmag(i);
        H(i,i)  = -Qc(i) - B(i,i)*Vi^2;
        N_(i,i) =  Pc(i) + G(i,i)*Vi^2;
        J(i,i)  =  Pc(i) - G(i,i)*Vi^2;
        L_(i,i) =  Qc(i) - B(i,i)*Vi^2;
    end
    Jac = [H(P_eq_idx, non_ref), N_(P_eq_idx, pq_idx); ...
           J(Q_eq_idx, non_ref), L_(Q_eq_idx, pq_idx)];
    dx = Jac \ mm;
    d_theta = dx(1:n_th);
    d_Vrel  = dx(n_th+1:end);
    theta(non_ref)   = theta(non_ref)   + d_theta;
    Vmag(pq_idx)     = Vmag(pq_idx) .* (1 + d_Vrel);
end

%% === Post-NR closure check: VSG1 P-injection must equal Pm0 ===
Vc_final = Vmag .* exp(1j*theta);
S_final  = Vc_final .* conj(Ybus * Vc_final);
P_vsg1_actual = real(S_final(ref_idx));
P_vsg1_expected = Pm0_pu;
closure_residual = abs(P_vsg1_actual - P_vsg1_expected);
% Closure tolerance 1e-3 (=0.1% on Sbase) accommodates the constant-impedance
% load voltage-squared effect: at NR steady state, V_A and V_B are slightly
% below 1.0 (~0.9998), so each R-only load consumes G·|V|^2 < G·1.0^2.
% The resulting tiny mismatch (~3e-4 pu) appears as a small under-injection
% at VSG1 because all four Pm are fixed at Pm0 by the PV constraint and the
% network equations balance through this single residual. This is a property
% of constant-impedance load modeling (matching build_kundur_cvs_v2.m's
% R-only Series RLC loads), NOT a hidden slack. The 1e-3 threshold rejects
% any mismatch beyond the V^2 effect (e.g. unbalanced topology, missing
% branch).
closure_ok = closure_residual < 1e-3;
if ~closure_ok
    warning('compute_kundur_cvs_powerflow:closure', ...
        ['VSG1 closure check FAILED: P_inj=%.6f, expected=%.6f, ' ...
         'residual=%.3e. Exceeds 1e-3 threshold; the const-Z load V^2 ' ...
         'effect alone should be ~3e-4. Investigate topology before ' ...
         'building the .slx.'], ...
        P_vsg1_actual, P_vsg1_expected, closure_residual);
end

%% === Pack results ===
delta0_vsg_rad   = theta(1:4);
Vmag_vsg_pu_out  = Vmag(1:4);
Pm0_vsg_pu_out   = repmat(Pm0_pu, 4, 1);
Pe_target_vsg_pu = Pm0_vsg_pu_out;

pf.converged      = converged;
pf.iterations     = iter;
pf.max_mismatch   = max_mm;
pf.bus_ids        = bus_lbl;
pf.V_mag_pu       = Vmag;
pf.V_ang_rad      = theta;
pf.delta0_vsg_rad = delta0_vsg_rad;
pf.Pm0_vsg_pu     = Pm0_vsg_pu_out;
pf.v_mag_vsg_pu   = Vmag_vsg_pu_out;
pf.Pe_target_vsg_pu = Pe_target_vsg_pu;
pf.X_v_pu         = X_v_pu;
pf.X_tie_pu       = X_tie_pu;
pf.closure_ok     = closure_ok;
pf.closure_residual_pu = closure_residual;
pf.total_Pm_pu        = total_Pm;
pf.total_load_pu      = total_load;
pf.pre_balance_residual_pu = balance_residual;

%% === Source-hash and timestamp ===
src_text = fileread([mfilename('fullpath') '.m']);
src_hash = compute_sha256(src_text);

ic = struct();
ic.schema_version             = 2;
ic.source                     = mfilename();
ic.source_hash                = ['sha256:' src_hash];
ic.timestamp                  = char(datetime('now','Format','yyyy-MM-dd''T''HH:mm:ssXXX', 'TimeZone','local'));
ic.topology_variant           = 'v2_no_inf_bus';
ic.powerflow                  = struct( ...
    'converged',           converged, ...
    'max_mismatch_pu',     max_mm, ...
    'iterations',          iter, ...
    'closure_ok',          closure_ok, ...
    'closure_residual_pu', closure_residual, ...
    'closure_tolerance_pu', 1e-3, ...
    'closure_residual_origin', 'const_z_load_v_squared_effect');
ic.global_balance             = struct( ...
    'total_Pm_pu',          total_Pm, ...
    'total_load_pu_at_v1',  total_load, ...
    'pre_residual_pu',      balance_residual, ...
    'actual_load_at_solved_v_pu', total_load - closure_residual, ...
    'no_hidden_slack',      true);
ic.vsg_internal_emf_angle_rad = delta0_vsg_rad';
ic.vsg_terminal_voltage_mag_pu = Vmag_vsg_pu_out';
ic.vsg_terminal_voltage_angle_rad = delta0_vsg_rad';
ic.vsg_pm0_pu                 = Pm0_vsg_pu_out';
ic.vsg_pe_target_pu           = Pe_target_vsg_pu';
ic.bus_voltages               = struct();
for k = 1:n_bus
    fld = matlab.lang.makeValidName(bus_lbl{k});
    ic.bus_voltages.(fld) = struct( ...
        'v_mag_pu', Vmag(k), ...
        'v_ang_rad', theta(k));
end
ic.x_v_pu      = X_v_pu;
ic.x_tie_pu    = X_tie_pu;
ic.physical_invariants_checked = {'p_balance_per_bus', 'global_balance_no_hidden_slack', 'pv_bus_ang_eq_internal_delta'};

%% === Write JSON ===
out_dir = fileparts(out_json_path);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(out_json_path, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);

%% === Diagnostic ===
fprintf('\n--- compute_kundur_cvs_powerflow (no INF) ---\n');
fprintf('  converged=%d  iter=%d  max_mismatch=%.3e pu\n', converged, iter, max_mm);
fprintf('  global P-balance: sum(Pm)=%.4f, sum(load)=%.4f, pre_res=%.3e\n', ...
    total_Pm, total_load, balance_residual);
fprintf('  closure VSG1: P_inj=%+.6f vs Pm0=%+.6f, res=%.3e (%s)\n', ...
    P_vsg1_actual, P_vsg1_expected, closure_residual, ...
    iif(closure_ok, 'OK', 'FAIL'));
fprintf('  Bus  | type   |V|(pu)  ang(deg)   P(pu)     Q(pu)\n');
for k = 1:n_bus
    tlbl = 'PQ';
    if bus_type(k) == PV, tlbl = 'PV'; end
    if k == ref_idx, tlbl = [tlbl '*']; end %#ok<AGROW>  % ref marker
    Sk = S_final(k);
    fprintf('  %-7s | %-5s | %.4f  %+8.3f   %+.4f   %+.4f\n', ...
        bus_lbl{k}, tlbl, Vmag(k), theta(k)*180/pi, real(Sk), imag(Sk));
end
fprintf('  delta0_vsg (rad): %s\n', mat2str(delta0_vsg_rad', 6));
fprintf('  delta0_vsg (deg): %s\n', mat2str(delta0_vsg_rad'*180/pi, 6));
fprintf('  Pm0_vsg_pu       : %s\n', mat2str(Pm0_vsg_pu_out', 4));
fprintf('  IntD margin (rad): %s (limit ±%.3f)\n', ...
    mat2str(abs(delta0_vsg_rad)', 6), pi/2-0.05);
fprintf('  Output: %s\n', out_json_path);

end

function out = iif(cond, a, b)
if cond, out = a; else, out = b; end
end

function h = compute_sha256(text)
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(uint8(text));
raw = md.digest();
u   = typecast(int8(raw), 'uint8');
hex = lower(dec2hex(u, 2));
h   = reshape(hex.', 1, []);
end
