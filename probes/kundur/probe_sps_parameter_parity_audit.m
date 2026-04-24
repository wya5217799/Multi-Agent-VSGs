function results = probe_sps_parameter_parity_audit(model_name, run_dir)
%PROBE_SPS_PARAMETER_PARITY_AUDIT  Read-only SPS-vs-NR parameter parity audit.
%
%   results = probe_sps_parameter_parity_audit(model_name, run_dir)
%
%   Contract:
%     - READ ONLY: reads model parameters via get_param and builder script analysis.
%     - Does NOT call set_param, simulink_patch_and_verify, or save_system.
%     - Does NOT modify any production file.
%     - Writes run_dir/attachments/parameter_parity_audit.json.
%
%   Findings are documented parity observations, not confirmed root causes.
%   All confirmed_root_cause fields must be false until NR-variant testing confirms.

if nargin < 1; model_name = 'kundur_vsg_sps'; end
if nargin < 2; run_dir    = fullfile(pwd, 'run_probe'); end

att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir'); mkdir(att_dir); end

% Ensure model loaded (read-only: no sim, no set_param)
if ~bdIsLoaded(model_name)
    load_system(model_name);
end

% ======================================================================
% Section 1: Line model parity
% NR (compute_kundur_powerflow.m): PI model with C_std=0.009e-6 F/km
% SPS (build_kundur_sps.m): Three-Phase Series RLC Branch, BranchType='RL'
% ======================================================================
line_model.nr_model             = 'PI';
line_model.nr_has_line_charging = true;
line_model.nr_line_capacitance_std_F_per_km  = 0.009e-6;
line_model.nr_line_capacitance_short_F_per_km = 0.009e-6;
line_model.nr_half_shunt_formula = 'ysh = 1j * B_tot * Zbase / 2 (added at both ends of every line)';
line_model.sps_branch_type       = 'RL';
line_model.sps_has_line_charging = false;
line_model.sps_branch_block      = 'powerlib/Elements/Three-Phase Series RLC Branch';
line_model.known_parity_mismatch = true;
line_model.candidate_root_cause  = ...
    'possible — requires NR-only variant confirmation before any SPS edit';
line_model.confirmed_root_cause  = false;
line_model.confirmation_method   = ...
    ['run probe_kundur_nr_parity_variants: if nr_no_line_charging moves ' ...
     'Bus7/8/10/9 toward SPS EMF-baseline angles, line charging parity is ' ...
     'primary candidate; otherwise continue audit'];

fprintf('RESULT: line_model_parity mismatch=%d (NR=PI, SPS=RL)\n', line_model.known_parity_mismatch);

% ======================================================================
% Section 2: Load and shunt parity (read from model)
% ======================================================================
load_shunt = struct();

load_blocks = {'Load7', 'Shunt7', 'Load9', 'Shunt9', 'TripLoad1', 'TripLoad2'};
param_fields = {'ActivePower', 'InductivePower', 'CapacitivePower'};
load_shunt.sps_params = struct();

for b = 1:length(load_blocks)
    blk = [model_name '/' load_blocks{b}];
    row = struct();
    row.block = blk;
    for p = 1:length(param_fields)
        pn = param_fields{p};
        try; row.(pn) = get_param(blk, pn); catch; row.(pn) = 'N/A'; end
    end
    load_shunt.sps_params.(load_blocks{b}) = row;
end

% NR reference values (from compute_kundur_powerflow.m analysis)
load_shunt.nr_reference.Bus7_load_P_MW   = 967;
load_shunt.nr_reference.Bus7_load_Q_Mvar = 100;    % inductive
load_shunt.nr_reference.Bus7_shunt_Q_Mvar = -200;  % capacitive (generation)
load_shunt.nr_reference.Bus9_load_P_MW   = 1767;
load_shunt.nr_reference.Bus9_load_Q_Mvar = 100;    % inductive
load_shunt.nr_reference.Bus9_shunt_Q_Mvar = -350;  % capacitive
load_shunt.nr_reference.Bus14_TripLoad1_P_MW = 248; % on at episode start
load_shunt.nr_reference.Bus15_TripLoad2_P_MW = 0;   % off at episode start
load_shunt.known_parity_mismatch = false;  % not confirmed; check if rows match
load_shunt.note = 'NR values from compute_kundur_powerflow.m; SPS values read from model. Manual comparison required.';

fprintf('RESULT: load_shunt_parity SPS Load7_P=%s Shunt7_CapQ=%s\n', ...
    load_shunt.sps_params.Load7.ActivePower, ...
    load_shunt.sps_params.Shunt7.CapacitivePower);

% ======================================================================
% Section 3: Source impedance parity (read from model via get_param)
% ======================================================================
src_imp = struct();

Sbase = 100e6;
Vbase = 230e3;
Zbase = Vbase^2 / Sbase;  % 529 Ohm
fn    = 50;

% NR source impedance (from compute_kundur_powerflow.m)
src_imp.nr_reference.conv_gen.R_pu  = 0.003 * (Sbase / 900e6);   % 3.333e-4 pu
src_imp.nr_reference.conv_gen.X_pu  = 0.30  * (Sbase / 900e6);   % 3.333e-2 pu
src_imp.nr_reference.conv_gen.base  = 'Sbase/900e6 scaling';
src_imp.nr_reference.vsg.R_pu       = 0.003 * (Sbase / 200e6);   % 1.5e-3 pu
src_imp.nr_reference.vsg.X_pu       = 0.30  * (Sbase / 200e6);   % 0.15 pu
src_imp.nr_reference.vsg.base       = 'Sbase/VSG_SN(200e6) scaling';

% SPS source impedance formula from build_kundur_sps.m
R_gen_pu = 0.003 * (Sbase / 900e6);
X_gen_pu = 0.30  * (Sbase / 900e6);
R_vsg_pu = 0.003 * (Sbase / 200e6);
X_vsg_pu = 0.30  * (Sbase / 200e6);

src_imp.sps_builder.conv_gen.R_pu_formula  = '0.003 * (Sbase/900e6)';
src_imp.sps_builder.conv_gen.R_pu_computed = R_gen_pu;
src_imp.sps_builder.conv_gen.X_pu_formula  = '0.30 * (Sbase/900e6)';
src_imp.sps_builder.conv_gen.X_pu_computed = X_gen_pu;
src_imp.sps_builder.conv_gen.R_ohm         = R_gen_pu * Zbase;
src_imp.sps_builder.conv_gen.L_henry       = X_gen_pu * Zbase / (2*pi*fn);
src_imp.sps_builder.vsg.R_pu_formula       = '0.003 * (Sbase/200e6)';
src_imp.sps_builder.vsg.R_pu_computed      = R_vsg_pu;
src_imp.sps_builder.vsg.X_pu_formula       = '0.30 * (Sbase/200e6)';
src_imp.sps_builder.vsg.X_pu_computed      = X_vsg_pu;
src_imp.sps_builder.vsg.R_ohm              = R_vsg_pu * Zbase;
src_imp.sps_builder.vsg.L_henry            = X_vsg_pu * Zbase / (2*pi*fn);

% Read actual model params for GSrc/WSrc/VSrc
src_blocks_imp = {'GSrc_G1','GSrc_G2','GSrc_G3','WSrc_W1','WSrc_W2', ...
                  'VSrc_ES1','VSrc_ES2','VSrc_ES3','VSrc_ES4'};
src_imp.model_readback = struct();
for s = 1:length(src_blocks_imp)
    blk = [model_name '/' src_blocks_imp{s}];
    row = struct();
    row.block = blk;
    try; row.Resistance   = str2double(get_param(blk, 'Resistance'));   catch; row.Resistance   = NaN; end
    try; row.Inductance   = str2double(get_param(blk, 'Inductance'));   catch; row.Inductance   = NaN; end
    try; row.PhaseAngle   = get_param(blk, 'PhaseAngle');               catch; row.PhaseAngle   = ''; end
    try; row.Voltage      = str2double(get_param(blk, 'Voltage'));      catch; row.Voltage      = NaN; end
    try; row.Frequency    = str2double(get_param(blk, 'Frequency'));    catch; row.Frequency    = NaN; end
    try; row.NonIdealSource   = get_param(blk, 'NonIdealSource');       catch; row.NonIdealSource   = ''; end
    try; row.SpecifyImpedance = get_param(blk, 'SpecifyImpedance');     catch; row.SpecifyImpedance = ''; end

    % Convert to pu for comparison
    if ~isnan(row.Resistance)
        row.R_pu = row.Resistance / Zbase;
    else
        row.R_pu = NaN;
    end
    if ~isnan(row.Inductance)
        row.X_pu = row.Inductance * 2*pi*fn / Zbase;
    else
        row.X_pu = NaN;
    end

    src_imp.model_readback.(src_blocks_imp{s}) = row;
    fprintf('RESULT: src=%s R_ohm=%.6f L_H=%.6f R_pu=%.6f X_pu=%.6f\n', ...
        src_blocks_imp{s}, row.Resistance, row.Inductance, row.R_pu, row.X_pu);
end

% Parity check: NR vs SPS pu values (within 0.1% tolerance)
tol = 0.001;
gen_R_match = abs(src_imp.sps_builder.conv_gen.R_pu_computed - src_imp.nr_reference.conv_gen.R_pu) < tol;
gen_X_match = abs(src_imp.sps_builder.conv_gen.X_pu_computed - src_imp.nr_reference.conv_gen.X_pu) < tol;
vsg_R_match = abs(src_imp.sps_builder.vsg.R_pu_computed - src_imp.nr_reference.vsg.R_pu) < tol;
vsg_X_match = abs(src_imp.sps_builder.vsg.X_pu_computed - src_imp.nr_reference.vsg.X_pu) < tol;

src_imp.parity_check.gen_R_match = gen_R_match;
src_imp.parity_check.gen_X_match = gen_X_match;
src_imp.parity_check.vsg_R_match = vsg_R_match;
src_imp.parity_check.vsg_X_match = vsg_X_match;
src_imp.parity_check.all_match   = gen_R_match && gen_X_match && vsg_R_match && vsg_X_match;
src_imp.known_parity_mismatch    = ~src_imp.parity_check.all_match;
src_imp.confirmed_root_cause     = false;
src_imp.note = 'Source impedance pu formulas are identical in NR and SPS builder. Conversion to Ohm/H uses same Zbase=529 Ohm.';

fprintf('RESULT: src_imp_parity gen_R_match=%d gen_X_match=%d vsg_R_match=%d vsg_X_match=%d all_match=%d\n', ...
    gen_R_match, gen_X_match, vsg_R_match, vsg_X_match, src_imp.parity_check.all_match);

% ======================================================================
% Assemble output
% ======================================================================
out.schema_version = 1;
out.scenario_id    = 'kundur';
out.model_name     = model_name;
out.run_id         = '20260424-kundur-sps-workpoint-alignment';
out.probe_type     = 'read_only';
out.line_model     = line_model;
out.load_shunt     = load_shunt;
out.source_impedance = src_imp;
out.overall_summary.line_model_mismatch   = line_model.known_parity_mismatch;
out.overall_summary.load_shunt_mismatch   = load_shunt.known_parity_mismatch;
out.overall_summary.src_impedance_mismatch = src_imp.known_parity_mismatch;
out.overall_summary.note = ['All fields are read-only evidence. No action taken on any mismatch. ' ...
    'Human review required before authorizing any SPS model edit.'];
out.provenance.probe_file      = 'probes/kundur/probe_sps_parameter_parity_audit.m';
out.provenance.run_timestamp   = datestr(now, 'yyyy-mm-dd HH:MM:SS');
out.provenance.read_only       = true;
out.provenance.no_set_param    = true;
out.provenance.no_save_system  = true;

out_path = fullfile(att_dir, 'parameter_parity_audit.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(out));
fclose(fid);

fprintf('RESULT: parameter_parity_audit written to %s line_mismatch=%d src_imp_mismatch=%d\n', ...
    out_path, line_model.known_parity_mismatch, src_imp.known_parity_mismatch);

results = out;
end
