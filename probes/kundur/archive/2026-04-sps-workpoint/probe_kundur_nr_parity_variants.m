function results = probe_kundur_nr_parity_variants(run_dir)
%PROBE_KUNDUR_NR_PARITY_VARIANTS  Run NR power flow with/without PI line charging.
%
%   results = probe_kundur_nr_parity_variants(run_dir)
%
%   Contract:
%     - PURE MATLAB: no Simulink model opened, no save_system, no set_param.
%     - Does NOT call compute_kundur_powerflow() — replicates NR math internally.
%     - Does NOT modify any production file.
%     - Writes run_dir/attachments/nr_variant_line_charging.json.
%     - Prints RESULT: lines to stdout.
%
%   Hypothesis: SPS RL-only branches (no line charging) vs NR PI model.
%   If removing line charging from NR moves Bus7/8/10/9 toward SPS EMF-baseline,
%   line charging parity is the primary root-cause candidate.

% -----------------------------------------------------------------------
% Path setup
% -----------------------------------------------------------------------
this_dir = fileparts(mfilename('fullpath'));   % probes/kundur/
repo_dir = fileparts(fileparts(this_dir));     % repo root
matlab_scripts_dir = fullfile(repo_dir, 'scenarios', 'kundur', 'matlab_scripts');
addpath(matlab_scripts_dir);

if nargin < 1 || isempty(run_dir)
    run_dir = fullfile(repo_dir, 'results', 'harness', 'kundur', ...
        '20260424-kundur-sps-workpoint-alignment');
end

att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir')
    mkdir(att_dir);
end

% -----------------------------------------------------------------------
% Load initial conditions
% -----------------------------------------------------------------------
ic_path = fullfile(repo_dir, 'scenarios', 'kundur', 'kundur_ic.json');
ic = slx_load_kundur_ic(ic_path);
P0_vsg_base = ic.vsg_p0_vsg_base_pu;   % 1x4: [0.1,0.1,0.1,0.1] VSG-base pu

% -----------------------------------------------------------------------
% System parameters
% -----------------------------------------------------------------------
fn = 50;  wn = 2*pi*fn;
Sbase  = 100e6;
Vbase  = 230e3;
Zbase  = Vbase^2 / Sbase;   % 529 Ω
VSG_SN = 200e6;
X_vsg_sys = 0.30 * (Sbase / VSG_SN);   % 0.15 pu on system base

R_std   = 0.053;    L_std   = 1.41e-3;
R_short = 0.01;     L_short = 0.5e-3;

BUS1_ABS_DEG = 20.0;

% Bus IDs (15 buses, no Bus13)
bus_ids = [1,2,3,4,5,6,7,8,9,10,11,12,14,15,16]';
nbus    = numel(bus_ids);

% Helper: bus_id -> index
id2idx = @(b) find(bus_ids == b, 1);

% ESS main buses
ess_main_bus = [7, 8, 10, 9];

% ESS scheduled injection on system base
P_ES_sys = P0_vsg_base(:) * (VSG_SN / Sbase);   % 0.2 pu each

% Trip load (on at episode start)
TripLoad1_pu = 248 / 100;   % 2.48 pu

% -----------------------------------------------------------------------
% SPS EMF-baseline angles (hardcoded reference)
% -----------------------------------------------------------------------
sps_emf_baseline = [15.180089409742246, 5.9013365191946505, ...
                     9.2872197552380715, 5.4134858434722366];

% -----------------------------------------------------------------------
% Run NR for a given C value
% -----------------------------------------------------------------------
    function [Vmag, Vang_deg, theta_main_abs, ess_delta_deg, converged, iters] = ...
            run_nr(C_std_per_km, C_short_per_km)

        % --- Build Ybus ---
        Ybus = zeros(nbus, nbus);

        % Line definitions: [from_bus, to_bus, len_km, R_ohm/km, L_H/km, C_F/km]
        line_defs = [
            1,  5,   5,   R_std,   L_std,   C_std_per_km;
            2,  6,   5,   R_std,   L_std,   C_std_per_km;
            3,  10,  5,   R_std,   L_std,   C_std_per_km;
            4,  9,   5,   R_std,   L_std,   C_std_per_km;
            5,  6,   25,  R_std,   L_std,   C_std_per_km;
            5,  6,   25,  R_std,   L_std,   C_std_per_km;
            6,  7,   10,  R_std,   L_std,   C_std_per_km;
            6,  7,   10,  R_std,   L_std,   C_std_per_km;
            7,  8,   110, R_std,   L_std,   C_std_per_km;
            7,  8,   110, R_std,   L_std,   C_std_per_km;
            7,  8,   110, R_std,   L_std,   C_std_per_km;
            8,  9,   10,  R_std,   L_std,   C_std_per_km;
            8,  9,   10,  R_std,   L_std,   C_std_per_km;
            9,  10,  25,  R_std,   L_std,   C_std_per_km;
            9,  10,  25,  R_std,   L_std,   C_std_per_km;
            7,  12,  1,   R_short, L_short, C_short_per_km;
            8,  16,  1,   R_short, L_short, C_short_per_km;
            10, 14,  1,   R_short, L_short, C_short_per_km;
            9,  15,  1,   R_short, L_short, C_short_per_km;
            8,  11,  1,   R_short, L_short, C_short_per_km;
        ];

        for k = 1:size(line_defs, 1)
            fb  = line_defs(k,1);
            tb  = line_defs(k,2);
            len = line_defs(k,3);
            Rk  = line_defs(k,4);
            Lk  = line_defs(k,5);
            Ck  = line_defs(k,6);

            fi = id2idx(fb);
            ti = id2idx(tb);

            % Series impedance in pu
            z_pu = (Rk*len + 1j*wn*Lk*len) / Zbase;
            y_pu = 1 / z_pu;

            % Half-shunt susceptance
            B_tot = wn * Ck * len;
            ysh   = 1j * B_tot * Zbase / 2;   % when C=0: ysh=0, pure RL

            Ybus(fi,fi) = Ybus(fi,fi) + y_pu + ysh;
            Ybus(ti,ti) = Ybus(ti,ti) + y_pu + ysh;
            Ybus(fi,ti) = Ybus(fi,ti) - y_pu;
            Ybus(ti,fi) = Ybus(ti,fi) - y_pu;
        end

        G = real(Ybus);
        B = imag(Ybus);

        % --- Bus type and scheduled injections ---
        % Bus types: 1=Slack, 2=PV, 3=PQ
        bus_type = 3 * ones(nbus, 1);
        bus_type(id2idx(1)) = 1;   % Slack = Bus1 (G1)
        bus_type(id2idx(2)) = 2;   % PV: G2
        bus_type(id2idx(3)) = 2;   % PV: G3
        bus_type(id2idx(4)) = 2;   % PV: W1 (wind on VSG base but treated as PV)

        % Voltage specs
        Vspec = ones(nbus, 1);
        Vspec(id2idx(1))  = 1.03;
        Vspec(id2idx(2))  = 1.01;
        Vspec(id2idx(3))  = 1.01;
        Vspec(id2idx(4))  = 1.00;

        % Scheduled P injections (pu, generation positive)
        Psch = zeros(nbus, 1);
        Psch(id2idx(2))  = +700/100;    % G2
        Psch(id2idx(3))  = +719/100;    % G3
        Psch(id2idx(4))  = +700/100;    % W1 (wind farm, rated 700MW)
        % Loads and shunts
        Psch(id2idx(7))  = -967/100;
        Psch(id2idx(9))  = -1767/100;
        % ESS buses: scheduled injection at init
        Psch(id2idx(12)) = +P_ES_sys(1);   % ES1 at Bus12
        Psch(id2idx(16)) = +P_ES_sys(2);   % ES2 at Bus16
        Psch(id2idx(14)) = +P_ES_sys(3) - TripLoad1_pu;   % ES3 at Bus14 with trip load
        Psch(id2idx(15)) = +P_ES_sys(4);   % ES4 at Bus15
        % Bus11 has W2 (small wind generation) - treat as PQ=0 since we don't know exact
        Psch(id2idx(11)) = +1.0;           % W2: 100MW

        % Scheduled Q injections (pu)
        Qsch = zeros(nbus, 1);
        Qsch(id2idx(7)) = +1.0;    % net Q: load 100Mvar ind - shunt 200Mvar cap = +100Mvar gen
        Qsch(id2idx(9)) = +2.5;    % net Q: load 100Mvar ind - shunt 350Mvar cap = +250Mvar gen

        % --- Newton-Raphson ---
        % Initial voltage
        Vmag = Vspec;
        Vang = zeros(nbus, 1);   % all angles start at 0

        slack_idx = id2idx(1);
        pv_idx    = [id2idx(2); id2idx(3); id2idx(4)];
        pq_idx    = setdiff((1:nbus)', [slack_idx; pv_idx]);

        converged = false;
        iters     = 0;
        max_iter  = 50;
        tol       = 1e-8;

        while iters < max_iter
            iters = iters + 1;

            % Complex voltage
            V = Vmag .* exp(1j * Vang);

            % Power injections
            Scalc = V .* conj(Ybus * V);
            Pcalc = real(Scalc);
            Qcalc = imag(Scalc);

            % Mismatches
            dP = Psch - Pcalc;
            dQ = Qsch - Qcalc;

            % Zero out slack
            dP(slack_idx) = 0;
            dQ(slack_idx) = 0;
            % Zero out PV Q (free)
            dQ(pv_idx) = 0;

            % Check convergence (only pq/pv buses, pq buses for Q)
            dP_check = dP;  dP_check(slack_idx) = 0;
            dQ_check = dQ;  dQ_check(pv_idx)    = 0;  dQ_check(slack_idx) = 0;

            if max(abs([dP_check; dQ_check])) < tol
                converged = true;
                break;
            end

            % Build Jacobian
            n     = nbus;
            J11   = zeros(n, n);
            J12   = zeros(n, n);
            J21   = zeros(n, n);
            J22   = zeros(n, n);

            for i = 1:n
                for j = 1:n
                    if i == j
                        J11(i,i) = -Qcalc(i) - B(i,i)*Vmag(i)^2;
                        J12(i,i) =  Pcalc(i)/Vmag(i) + G(i,i)*Vmag(i);
                        J21(i,i) =  Pcalc(i) - G(i,i)*Vmag(i)^2;
                        J22(i,i) =  Qcalc(i)/Vmag(i) - B(i,i)*Vmag(i);
                    else
                        Vi = Vmag(i); Vj = Vmag(j);
                        th_ij = Vang(i) - Vang(j);
                        J11(i,j) = Vmag(i)*Vmag(j)*(G(i,j)*sin(th_ij) - B(i,j)*cos(th_ij));
                        J12(i,j) = Vmag(i)*(G(i,j)*cos(th_ij) + B(i,j)*sin(th_ij));
                        J21(i,j) = -Vmag(i)*Vmag(j)*(G(i,j)*cos(th_ij) + B(i,j)*sin(th_ij));
                        J22(i,j) = Vmag(i)*(G(i,j)*sin(th_ij) - B(i,j)*cos(th_ij));
                    end
                end
            end

            % Reduce Jacobian: remove slack row/col from dP/J11/J21
            % Remove slack from angle, remove slack+PV from Q/voltage
            ang_mask = true(n,1);  ang_mask(slack_idx) = false;
            mag_mask = true(n,1);  mag_mask(slack_idx) = false;  mag_mask(pv_idx) = false;

            F = [dP(ang_mask); dQ(mag_mask)];

            J_red = [J11(ang_mask, ang_mask), J12(ang_mask, mag_mask);
                     J21(mag_mask, ang_mask), J22(mag_mask, mag_mask)];

            dx = J_red \ F;

            n_ang = sum(ang_mask);
            dTheta = zeros(n,1);
            dTheta(ang_mask) = dx(1:n_ang);

            dV_over_V = zeros(n,1);
            dV_over_V(mag_mask) = dx(n_ang+1:end);

            Vang = Vang + dTheta;
            Vmag = Vmag .* (1 + dV_over_V);

            % Enforce PV voltage magnitude
            Vmag(slack_idx)  = Vspec(slack_idx);
            Vmag(pv_idx)     = Vspec(pv_idx);
        end

        % Final NR Vang in degrees
        Vang_deg = Vang * 180 / pi;

        % ESS main bus angles (absolute)
        main_idx = arrayfun(id2idx, ess_main_bus);
        theta_main_pf  = Vang_deg(main_idx);
        theta_main_abs = theta_main_pf + BUS1_ABS_DEG;
        V_main         = Vmag(main_idx);

        % ESS delta angle from main bus
        sin_arg = P0_vsg_base(:) .* (VSG_SN/Sbase) .* X_vsg_sys ./ V_main(:);
        for i = 1:4
            if abs(sin_arg(i)) >= 1.0
                sin_arg(i) = sign(sin_arg(i)) * 0.9999;
            end
        end
        ess_delta_deg = theta_main_abs(:) + asin(sin_arg) * 180 / pi;
    end

% -----------------------------------------------------------------------
% Run variant 1: with line charging (baseline, should match nr_reference.json)
% -----------------------------------------------------------------------
fprintf('Running NR with line charging (C_std=0.009e-6, C_short=0.009e-6)...\n');
[Vmag_wc, Vang_deg_wc, theta_main_abs_wc, ess_delta_wc, conv_wc, iters_wc] = ...
    run_nr(0.009e-6, 0.009e-6);

% -----------------------------------------------------------------------
% Run variant 2: no line charging (SPS RL-only)
% -----------------------------------------------------------------------
fprintf('Running NR without line charging (C_std=0, C_short=0)...\n');
[Vmag_nc, Vang_deg_nc, theta_main_abs_nc, ess_delta_nc, conv_nc, iters_nc] = ...
    run_nr(0, 0);

% -----------------------------------------------------------------------
% Compare to SPS EMF-baseline
% -----------------------------------------------------------------------
mae_with = mean(abs(theta_main_abs_wc(:) - sps_emf_baseline(:)));
mae_no   = mean(abs(theta_main_abs_nc(:) - sps_emf_baseline(:)));
delta_mae = mae_with - mae_no;  % positive = no_charging is closer

if mae_no < mae_with
    closer = 'nr_no_line_charging';
else
    closer = 'nr_with_line_charging';
end

% -----------------------------------------------------------------------
% Print RESULT lines
% -----------------------------------------------------------------------
fprintf('RESULT: nr_no_line_charging_bus7=%.6f deg\n',   theta_main_abs_nc(1));
fprintf('RESULT: nr_with_line_charging_bus7=%.6f deg\n', theta_main_abs_wc(1));
fprintf('RESULT: closer_to_sps_emf_baseline=%s\n',       closer);
fprintf('RESULT: mae_with=%.6f deg  mae_no=%.6f deg  delta_mae=%.6f deg\n', ...
    mae_with, mae_no, delta_mae);
fprintf('RESULT: nr_no_line_charging_all=[%.4f %.4f %.4f %.4f] deg\n', ...
    theta_main_abs_nc(1), theta_main_abs_nc(2), theta_main_abs_nc(3), theta_main_abs_nc(4));

% Additional diagnostics
fprintf('INFO: with_line_charging converged=%d iters=%d\n', conv_wc, iters_wc);
fprintf('INFO: no_line_charging  converged=%d iters=%d\n', conv_nc,  iters_nc);
fprintf('INFO: sps_emf_baseline=[%.4f %.4f %.4f %.4f] deg\n', ...
    sps_emf_baseline(1), sps_emf_baseline(2), sps_emf_baseline(3), sps_emf_baseline(4));
fprintf('INFO: nr_with=[%.4f %.4f %.4f %.4f] deg\n', ...
    theta_main_abs_wc(1), theta_main_abs_wc(2), theta_main_abs_wc(3), theta_main_abs_wc(4));
fprintf('INFO: nr_no  =[%.4f %.4f %.4f %.4f] deg\n', ...
    theta_main_abs_nc(1), theta_main_abs_nc(2), theta_main_abs_nc(3), theta_main_abs_nc(4));

% -----------------------------------------------------------------------
% Build results struct
% -----------------------------------------------------------------------
results = struct();
results.schema_version = 1;
results.probe = 'probe_kundur_nr_parity_variants';
results.timestamp = datestr(now, 'yyyy-mm-ddTHH:MM:SS');

% Variant: with line charging
v_with.label                 = 'nr_with_line_charging';
v_with.C_std_F_per_km        = 0.009e-6;
v_with.C_short_F_per_km      = 0.009e-6;
v_with.converged             = conv_wc;
v_with.iterations            = iters_wc;
v_with.main_bus_ang_pf_deg   = theta_main_abs_wc(:)' - BUS1_ABS_DEG;
v_with.main_bus_ang_abs_deg  = theta_main_abs_wc(:)';
v_with.ess_delta_deg         = ess_delta_wc(:)';
v_with.mae_vs_sps_emf        = mae_with;

% Variant: no line charging
v_no.label                 = 'nr_no_line_charging';
v_no.C_std_F_per_km        = 0;
v_no.C_short_F_per_km      = 0;
v_no.converged             = conv_nc;
v_no.iterations            = iters_nc;
v_no.main_bus_ang_pf_deg   = theta_main_abs_nc(:)' - BUS1_ABS_DEG;
v_no.main_bus_ang_abs_deg  = theta_main_abs_nc(:)';
v_no.ess_delta_deg         = ess_delta_nc(:)';
v_no.mae_vs_sps_emf        = mae_no;

results.variants = {v_with, v_no};

% Comparison
cmp = struct();
cmp.sps_emf_baseline_main_bus_ang_deg  = sps_emf_baseline;
cmp.bus_order                          = ess_main_bus;
cmp.which_nr_variant_is_closer         = closer;
cmp.mae_with_line_charging_deg         = mae_with;
cmp.mae_no_line_charging_deg           = mae_no;
cmp.delta_mae_deg                      = delta_mae;   % positive = no_charging is closer
cmp.hypothesis                         = ...
    'SPS uses RL-only branches; if nr_no_line_charging is closer to SPS, line charging is primary root cause';
cmp.conclusion                         = ...
    ['Variant closer to SPS: ' closer ...
     sprintf(' (delta_mae=%.4f deg)', delta_mae)];

results.comparison_to_sps_emf_baseline = cmp;

% NR reference cross-check (Bus7/8/10/9 abs from nr_reference.json)
nr_ref_abs = [10.913127677225445, 2.9712307723444127, 4.5191269028534364, 1.6089023192225262];
results.nr_reference_check.known_nr_ref_abs_deg = nr_ref_abs;
results.nr_reference_check.this_with_abs_deg    = theta_main_abs_wc(:)';
results.nr_reference_check.mae_vs_known_ref     = mean(abs(theta_main_abs_wc(:) - nr_ref_abs(:)));

% -----------------------------------------------------------------------
% Write JSON
% -----------------------------------------------------------------------
json_path = fullfile(att_dir, 'nr_variant_line_charging.json');

% Manual JSON encoding for better readability
fid = fopen(json_path, 'w', 'n', 'UTF-8');
fprintf(fid, '{\n');
fprintf(fid, '  "schema_version": 1,\n');
fprintf(fid, '  "probe": "probe_kundur_nr_parity_variants",\n');
fprintf(fid, '  "timestamp": "%s",\n', results.timestamp);

% Variants array
fprintf(fid, '  "variants": [\n');
variants_list = {v_with, v_no};
for vi = 1:2
    vv = variants_list{vi};
    if vi < 2; comma_v = ','; else; comma_v = ''; end
    fprintf(fid, '    {\n');
    fprintf(fid, '      "label": "%s",\n', vv.label);
    fprintf(fid, '      "C_std_F_per_km": %.6e,\n', vv.C_std_F_per_km);
    fprintf(fid, '      "C_short_F_per_km": %.6e,\n', vv.C_short_F_per_km);
    fprintf(fid, '      "converged": %s,\n', mat2str(logical(vv.converged)));
    fprintf(fid, '      "iterations": %d,\n', vv.iterations);
    fprintf(fid, '      "main_bus_ang_abs_deg": [%.10f, %.10f, %.10f, %.10f],\n', ...
        vv.main_bus_ang_abs_deg(1), vv.main_bus_ang_abs_deg(2), ...
        vv.main_bus_ang_abs_deg(3), vv.main_bus_ang_abs_deg(4));
    fprintf(fid, '      "ess_delta_deg": [%.10f, %.10f, %.10f, %.10f],\n', ...
        vv.ess_delta_deg(1), vv.ess_delta_deg(2), ...
        vv.ess_delta_deg(3), vv.ess_delta_deg(4));
    fprintf(fid, '      "mae_vs_sps_emf_deg": %.10f\n', vv.mae_vs_sps_emf);
    fprintf(fid, '    }%s\n', comma_v);
end
fprintf(fid, '  ],\n');

% Comparison
fprintf(fid, '  "comparison_to_sps_emf_baseline": {\n');
fprintf(fid, '    "sps_emf_baseline_main_bus_ang_deg": [%.10f, %.10f, %.10f, %.10f],\n', ...
    sps_emf_baseline(1), sps_emf_baseline(2), sps_emf_baseline(3), sps_emf_baseline(4));
fprintf(fid, '    "bus_order_bus7_8_10_9": [7, 8, 10, 9],\n');
fprintf(fid, '    "which_nr_variant_is_closer": "%s",\n', closer);
fprintf(fid, '    "mae_with_line_charging_deg": %.10f,\n', mae_with);
fprintf(fid, '    "mae_no_line_charging_deg": %.10f,\n', mae_no);
fprintf(fid, '    "delta_mae_deg": %.10f\n', delta_mae);
fprintf(fid, '  },\n');

% NR reference cross-check
fprintf(fid, '  "nr_reference_check": {\n');
fprintf(fid, '    "known_nr_ref_abs_deg": [%.10f, %.10f, %.10f, %.10f],\n', ...
    nr_ref_abs(1), nr_ref_abs(2), nr_ref_abs(3), nr_ref_abs(4));
fprintf(fid, '    "this_with_abs_deg": [%.10f, %.10f, %.10f, %.10f],\n', ...
    theta_main_abs_wc(1), theta_main_abs_wc(2), theta_main_abs_wc(3), theta_main_abs_wc(4));
fprintf(fid, '    "mae_vs_known_ref_deg": %.10f\n', ...
    results.nr_reference_check.mae_vs_known_ref);
fprintf(fid, '  }\n');
fprintf(fid, '}\n');
fclose(fid);

fprintf('RESULT: json_written=%s\n', json_path);
fprintf('--- probe_kundur_nr_parity_variants complete ---\n');

end
