function pf = compute_kundur_cvs_powerflow(out_json_path)
%COMPUTE_KUNDUR_CVS_POWERFLOW  NR power flow for the 7-bus CVS Phasor topology.
%
%   pf = compute_kundur_cvs_powerflow()
%   pf = compute_kundur_cvs_powerflow(out_json_path)
%
%   Standalone Newton-Raphson power flow for the simplified Kundur CVS
%   path (`scenarios/kundur/simulink_models/kundur_cvs.slx`):
%     7 buses : Bus_V1..V4 (PV), Bus_A, Bus_B (PQ), Bus_INF (slack)
%     6 lines : L_v_1..4, L_tie, L_inf
%     2 loads : Load_A, Load_B (constant impedance, modelled as Y-shunt)
%
%   Output schema follows Stage 2 plan §3 (`kundur_ic_cvs.json`) so that
%   downstream `build_kundur_cvs.m` and the D2 validator can read it
%   directly. The legacy `compute_kundur_powerflow.m` stays untouched.
%
%   This NR is single-base (Sbase=100MVA, Vbase=230kV, single-phase phasor)
%   and CVS-aware: each VSG terminal is a PV bus where the prescribed
%   voltage |V_i| equals the CVS magnitude and the bus angle equals the
%   internal δ_i (CVS output phase IS the bus voltage phase — no internal
%   EMF / step-up filter, unlike the legacy generator path).
%
%   Inputs:
%     out_json_path — destination for kundur_ic_cvs.json
%                     (default: scenarios/kundur/kundur_ic_cvs.json)
%
%   Returns struct pf with fields:
%     converged      — logical, NR converged flag
%     iterations     — int, NR iterations used
%     max_mismatch   — double, final max |ΔP|/|ΔQ| (pu)
%     bus_ids        — 7×1 string labels
%     V_mag_pu       — 7×1 bus voltage magnitudes (pu)
%     V_ang_rad      — 7×1 bus voltage angles (rad)
%     delta0_vsg_rad — 4×1 VSG internal angles = θ at Bus_V_i
%     Pm0_vsg_pu     — 4×1 VSG mechanical power (system-base pu)
%     v_mag_vsg_pu   — 4×1 VSG terminal voltage magnitude (pu)
%     Pe_target_vsg_pu — 4×1 = Pm0 at equilibrium

if nargin < 1
    this_dir = fileparts(mfilename('fullpath'));   % scenarios/kundur/matlab_scripts/
    repo_dir = fileparts(fileparts(this_dir));     % scenarios/
    out_json_path = fullfile(repo_dir, 'kundur', 'kundur_ic_cvs.json');
end

%% === System parameters (must mirror build_kundur_cvs.m) ===
fn       = 50;
wn       = 2*pi*fn;
Sbase    = 100e6;
Vbase    = 230e3;
Zbase    = Vbase^2 / Sbase;

X_v_pu   = 0.10;
X_tie_pu = 0.30;
X_inf_pu = 0.05;

P_loadA_pu = 0.4;
P_loadB_pu = 0.4;

% VSG operating set-points (single-base, no VSG_SN distinction in CVS path)
Pm0_pu      = 0.5;        % per-VSG mechanical power, system pu
Vmag_vsg_pu = 1.0;        % per-VSG CVS terminal magnitude, pu

%% === Bus inventory ===
% Internal index → (label, type, V_spec_pu, P_sch_pu, Q_sch_pu)
SLACK = 1; PV = 2; PQ = 3;
%        idx label      type   V_spec  P_sch   Q_sch
bus_table = {
    1, 'Bus_V1', PV,    Vmag_vsg_pu, Pm0_pu, 0.0;
    2, 'Bus_V2', PV,    Vmag_vsg_pu, Pm0_pu, 0.0;
    3, 'Bus_V3', PV,    Vmag_vsg_pu, Pm0_pu, 0.0;
    4, 'Bus_V4', PV,    Vmag_vsg_pu, Pm0_pu, 0.0;
    5, 'Bus_A',  PQ,    1.0,         0.0,    0.0;
    6, 'Bus_B',  PQ,    1.0,         0.0,    0.0;
    7, 'Bus_INF',SLACK, 1.0,         0.0,    0.0;
};
n_bus     = size(bus_table, 1);
bus_lbl   = bus_table(:, 2);
bus_type  = cell2mat(bus_table(:, 3));
V_spec    = cell2mat(bus_table(:, 4));
P_sch     = cell2mat(bus_table(:, 5));
Q_sch     = cell2mat(bus_table(:, 6));

%% === Branch list ===
% {from, to, X_pu}, all purely inductive
branches = {
    1, 5, X_v_pu;     % L_v_1
    2, 5, X_v_pu;     % L_v_2
    3, 6, X_v_pu;     % L_v_3
    4, 6, X_v_pu;     % L_v_4
    5, 6, X_tie_pu;   % L_tie
    6, 7, X_inf_pu;   % L_inf
};

%% === Y-bus (lossless lines + constant-impedance load shunts) ===
Ybus = zeros(n_bus, n_bus);
for k = 1:size(branches, 1)
    f = branches{k, 1};
    t = branches{k, 2};
    Xk = branches{k, 3};
    y = 1 / (1j * Xk);            % series admittance, no R, no shunt cap
    Ybus(f, f) = Ybus(f, f) + y;
    Ybus(t, t) = Ybus(t, t) + y;
    Ybus(f, t) = Ybus(f, t) - y;
    Ybus(t, f) = Ybus(t, f) - y;
end
% R-only loads as positive conductance shunt at Bus_A and Bus_B
Ybus(5, 5) = Ybus(5, 5) + P_loadA_pu;   % G_loadA = 1/R_pu = P at V=1
Ybus(6, 6) = Ybus(6, 6) + P_loadB_pu;

G = real(Ybus);
B = imag(Ybus);

%% === NR initialisation ===
slack_idx = find(bus_type == SLACK);
pv_idx    = find(bus_type == PV);
pq_idx    = find(bus_type == PQ);
non_slack = [pv_idx; pq_idx];
n_ns      = numel(non_slack);
n_pq      = numel(pq_idx);

theta = zeros(n_bus, 1);
Vmag  = V_spec;

max_iter = 50;
tol      = 1e-10;
converged = false;
max_mm = Inf;

for iter = 1:max_iter
    Vc = Vmag .* exp(1j*theta);
    S  = Vc .* conj(Ybus * Vc);
    Pc = real(S); Qc = imag(S);
    dP = P_sch - Pc;
    dQ = Q_sch - Qc;
    mm = [dP(non_slack); dQ(pq_idx)];
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
    Jac = [H(non_slack, non_slack), N_(non_slack, pq_idx); ...
           J(pq_idx,    non_slack), L_(pq_idx,    pq_idx)];
    dx = Jac \ mm;
    d_theta = dx(1:n_ns);
    d_Vrel  = dx(n_ns+1:end);
    theta(non_slack) = theta(non_slack) + d_theta;
    Vmag(pq_idx)     = Vmag(pq_idx) .* (1 + d_Vrel);
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
pf.X_inf_pu       = X_inf_pu;

%% === Source-hash and timestamp for the JSON ===
src_text = fileread([mfilename('fullpath') '.m']);
src_hash = compute_sha256(src_text);

ic = struct();
ic.schema_version             = 1;
ic.source                     = mfilename();
ic.source_hash                = ['sha256:' src_hash];
ic.timestamp                  = char(datetime('now','Format','yyyy-MM-dd''T''HH:mm:ssXXX', 'TimeZone','local'));
ic.powerflow                  = struct( ...
    'converged',     converged, ...
    'max_mismatch_pu', max_mm, ...
    'iterations',    iter );
ic.vsg_internal_emf_angle_rad = delta0_vsg_rad';
ic.vsg_terminal_voltage_mag_pu = Vmag_vsg_pu_out';
ic.vsg_terminal_voltage_angle_rad = delta0_vsg_rad';   % CVS path: terminal == internal
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
ic.x_inf_pu    = X_inf_pu;
ic.physical_invariants_checked = {'p_balance_per_bus', 'pv_bus_ang_eq_internal_delta'};

%% === Write JSON ===
out_dir = fileparts(out_json_path);
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
fid = fopen(out_json_path, 'w');
fwrite(fid, jsonencode(ic, 'PrettyPrint', true));
fclose(fid);

%% === Diagnostic ===
fprintf('\n--- compute_kundur_cvs_powerflow ---\n');
fprintf('  converged=%d  iter=%d  max_mismatch=%.3e pu\n', converged, iter, max_mm);
fprintf('  Bus  | type   |V|(pu)  ang(deg)   P(pu)     Q(pu)\n');
type_str = {'PV','PQ','SLACK'};
type_map = containers.Map({1,2,3}, {'SLACK','PV','PQ'}); %#ok<NASGU>
for k = 1:n_bus
    tlbl = 'PQ';
    if bus_type(k) == SLACK, tlbl = 'SLACK'; end
    if bus_type(k) == PV,    tlbl = 'PV';    end
    Sk = Vc(k) * conj(sum(Ybus(k,:) .* Vc(:).'));
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

function h = compute_sha256(text)
%COMPUTE_SHA256  Hex SHA-256 of a char array.
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(uint8(text));
raw = md.digest();                            % Java int8[] (-128..127)
u   = typecast(int8(raw), 'uint8');           % cast to MATLAB uint8 in-memory
hex = lower(dec2hex(u, 2));                   % 32×2 char matrix
h   = reshape(hex.', 1, []);                  % 1×64 hex string
end
