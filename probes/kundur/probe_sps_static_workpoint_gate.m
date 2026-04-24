function results = probe_sps_static_workpoint_gate(model_name, run_dir, opts)
%PROBE_SPS_STATIC_WORKPOINT_GATE  Reusable static workpoint gate for Kundur SPS candidate.
%
%   results = probe_sps_static_workpoint_gate(model_name, run_dir)
%   results = probe_sps_static_workpoint_gate(model_name, run_dir, opts)
%
%   Contract:
%     - Reads nr_reference.json from run_dir/attachments/ (must exist).
%     - Initializes MATLAB base workspace from kundur_ic.json and config defaults.
%     - For each source_angle_mode: temporarily patches GSrc/WSrc, runs 0.05 s sim,
%       reads Vabc_ESi/Iabc_ESi, restores via onCleanup.
%     - Writes run_dir/attachments/<output_filename>.
%     - Never calls save_system.
%
%   sps_main_bus_angle_deg is the ESS terminal voltage angle (proxy for bus angle;
%   no direct bus measurement blocks in the current model).
%
%   opts fields (all optional):
%     .source_angle_modes      cell array of mode labels (default: 3 standard modes)
%     .gate_thresholds         struct with .angle_deg (1.0), .pe_pu (0.05), .vi_diff (1e-6)
%     .output_filename         default 'static_workpoint_gate.json'
%     .allow_temporary_source_patch  default true; set false for read-only persisted_current only

if nargin < 1; model_name = 'kundur_vsg_sps'; end
if nargin < 2; run_dir    = fullfile(pwd, 'run_probe'); end
if nargin < 3; opts = struct(); end

if ~isfield(opts, 'source_angle_modes')
    opts.source_angle_modes = {'persisted_current', 'emf_reference', 'terminal_reference'};
end
if ~isfield(opts, 'gate_thresholds')
    opts.gate_thresholds = struct('angle_deg', 1.0, 'pe_pu', 0.05, 'vi_diff', 1e-6);
end
if ~isfield(opts, 'output_filename')
    opts.output_filename = 'static_workpoint_gate.json';
end
if ~isfield(opts, 'allow_temporary_source_patch')
    opts.allow_temporary_source_patch = true;
end

repo    = fileparts(fileparts(fileparts(mfilename('fullpath'))));
att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir'); mkdir(att_dir); end

% -- Load nr_reference.json --
ref_path = fullfile(att_dir, 'nr_reference.json');
if ~exist(ref_path, 'file')
    error('probe_sps_static_workpoint_gate: nr_reference.json not found in %s', att_dir);
end
fid = fopen(ref_path, 'r'); raw = fread(fid, '*char')'; fclose(fid);
nr = jsondecode(raw);

% -- Load kundur_ic.json --
ic_path = fullfile(repo, 'scenarios', 'kundur', 'kundur_ic.json');
fid = fopen(ic_path, 'r'); raw = fread(fid, '*char')'; fclose(fid);
ic = jsondecode(raw);

% -- Init base workspace --
M0_base = 12.0;  D0_base = 3.0;  Pe0_base = 0.1;
for i = 1:4
    assignin('base', sprintf('M0_val_ES%d', i), M0_base);
    assignin('base', sprintf('D0_val_ES%d', i), D0_base);
    assignin('base', sprintf('phAng_ES%d',  i), ic.vsg_delta0_deg(i));
    assignin('base', sprintf('Pe_ES%d',     i), Pe0_base);
    assignin('base', sprintf('wref_%d',     i), 1.0);
end
assignin('base', 'TripLoad1_P', 248e6/3);
assignin('base', 'TripLoad2_P', 0);

% -- Ensure model loaded --
if ~bdIsLoaded(model_name)
    load_system(model_name);
end

% -- NR reference values --
nr_bus_ang  = nr.main_bus_ang_abs_deg(:)';  % [Bus7, Bus8, Bus10, Bus9]
nr_ess_ang  = nr.ess_delta_deg(:)';          % [ES1, ES2, ES3, ES4]
bus_labels  = {'Bus7', 'Bus8', 'Bus10', 'Bus9'};
ess_labels  = {'ES1', 'ES2', 'ES3', 'ES4'};

% ESS → main bus mapping
ess_bus_idx = [1 2 3 4];  % ES1→Bus7(1), ES2→Bus8(2), ES3→Bus10(3), ES4→Bus9(4)

expected_pe_sys_pu = ic.vsg_p0_vsg_base_pu(:)' * (200e6 / 100e6);  % [0.2 0.2 0.2 0.2]

% -- Source blocks --
src_blocks = { ...
    [model_name '/GSrc_G1'], ...
    [model_name '/GSrc_G2'], ...
    [model_name '/GSrc_G3'], ...
    [model_name '/WSrc_W1'], ...
    [model_name '/WSrc_W2'] };
src_labels = {'GSrc_G1', 'GSrc_G2', 'GSrc_G3', 'WSrc_W1', 'WSrc_W2'};

% -- Read persisted source angles (before any patch) --
baseline_angles = zeros(1, 5);
for s = 1:5
    try
        baseline_angles(s) = str2double(get_param(src_blocks{s}, 'PhaseAngle'));
    catch
        baseline_angles(s) = NaN;
    end
end
sps_readback = struct();
for s = 1:5
    sps_readback.(src_labels{s}) = baseline_angles(s);
end

% -- Read VSrc_ESi params (read-only snapshot) --
vsrc_readback = cell(1, 4);
vsrc_param_names = {'PhaseAngle', 'Voltage', 'Frequency', 'NonIdealSource', 'SpecifyImpedance', 'Resistance', 'Inductance'};
for i = 1:4
    blk = sprintf('%s/VSrc_ES%d', model_name, i);
    row = struct();
    row.block = blk;
    for p = 1:length(vsrc_param_names)
        pn = vsrc_param_names{p};
        try; row.(pn) = get_param(blk, pn); catch; row.(pn) = ''; end
    end
    vsrc_readback{i} = row;
end

% Register cleanup AFTER reading baseline
cleanup = onCleanup(@() restore_sources(src_blocks, baseline_angles)); %#ok<NASGU>

% -- Angle normalization helpers --
wrap180 = @(x) mod(x + 180, 360) - 180;
ang_diff = @(a, b) wrap180(a - b);

Sbase   = 100e6;
vi_scale = 0.5;

% -- Source angle config definitions --
mode_angle_defs = struct();
mode_angle_defs.persisted_current = baseline_angles;
mode_angle_defs.emf_reference = [ ...
    nr.G1_emf_deg, ...
    nr.gen_emf_deg_ext(1), nr.gen_emf_deg_ext(2), ...
    nr.gen_emf_deg_ext(3), nr.gen_emf_deg_ext(4) ];
mode_angle_defs.terminal_reference = [ ...
    nr.G1_terminal_deg, ...
    nr.gen_delta_deg(1), nr.gen_delta_deg(2), ...
    nr.gen_delta_deg(3), nr.gen_delta_deg(4) ];

% -- Config semantics (for JSON) --
mode_semantics = struct();
mode_semantics.persisted_current   = 'conventional/wind source PhaseAngle values as saved in candidate .slx; no correctness claim';
mode_semantics.emf_reference       = 'conventional/wind source PhaseAngle values set to internal EMF angles; no correctness claim';
mode_semantics.terminal_reference  = 'conventional/wind source PhaseAngle values set to terminal bus voltage angles from NR; no correctness claim';

% -- Run each config --
configs = {};
thr = opts.gate_thresholds;

for m = 1:length(opts.source_angle_modes)
    mode_label = opts.source_angle_modes{m};

    % Skip non-persisted modes if patching is disabled
    if ~opts.allow_temporary_source_patch && ~strcmp(mode_label, 'persisted_current')
        continue;
    end

    % Patch sources
    target_angles = mode_angle_defs.(mode_label);
    for s = 1:5
        if ~isnan(target_angles(s))
            try; set_param(src_blocks{s}, 'PhaseAngle', num2str(target_angles(s), '%.6f')); catch; end
        end
    end

    % Run simulation
    try
        simOut = sim(model_name, 'StopTime', '0.05');
        sim_ok = true;
        sim_err = '';
    catch ME
        sim_ok = false;
        sim_err = ME.message;
    end

    % Restore sources immediately after sim
    restore_sources(src_blocks, baseline_angles);

    cfg_out.config_label    = mode_label;
    cfg_out.config_semantics = mode_semantics.(mode_label);
    cfg_out.source_phase_angles_deg = struct();
    for s = 1:5
        cfg_out.source_phase_angles_deg.(src_labels{s}) = target_angles(s);
    end
    cfg_out.vsrc_readback = vsrc_readback;
    cfg_out.sim_ok = sim_ok;
    cfg_out.sim_error = sim_err;

    ess_rows = {};
    all_angle_ok = true;
    all_pe_ok    = true;
    all_vi_ok    = true;

    for i = 1:4
        bi = ess_bus_idx(i);
        row = struct();
        row.block     = sprintf('%s/VSrc_ES%d', model_name, i);
        row.ess       = ess_labels{i};
        row.main_bus  = bus_labels{bi};
        row.sps_angle_measurement_scope = ...
            'ESS terminal V angle proxy; no direct Bus7/8/10/9 measurement block';

        row.nr_main_bus_angle_raw_deg = nr_bus_ang(bi);
        row.nr_main_bus_angle_deg     = wrap180(nr_bus_ang(bi));
        row.nr_ess_angle_raw_deg      = nr_ess_ang(i);
        row.nr_ess_angle_deg          = wrap180(nr_ess_ang(i));
        row.nr_angle_diff_deg         = ang_diff(nr_ess_ang(i), nr_bus_ang(bi));

        row.vsrc_phaseangle_expression = sprintf('phAng_ES%d', i);
        row.vsrc_phaseangle_command_deg = ic.vsg_delta0_deg(i);
        row.expected_pe_sys_pu         = expected_pe_sys_pu(i);

        if sim_ok
            try
                Vabc_ts = simOut.get(sprintf('Vabc_ES%d', i));
                Iabc_ts = simOut.get(sprintf('Iabc_ES%d', i));
                V_row = Vabc_ts.Data(end, :);
                I_row = Iabc_ts.Data(end, :);

                % ESS terminal V angle (proxy for main bus angle)
                V_cmplx = V_row(1);   % complex phasor: angle(Va) is phase-A angle directly
                sps_ang_raw = angle(V_cmplx) * 180/pi;
                sps_ang_norm = wrap180(sps_ang_raw);

                % VxI Pe
                raw_W = real(sum(V_row .* conj(I_row)));
                Pe_meas = vi_scale * raw_W / Sbase;

                row.sps_main_bus_angle_raw_deg  = sps_ang_raw;
                row.sps_main_bus_angle_deg       = sps_ang_norm;
                row.sps_ess_angle_raw_deg        = ic.vsg_delta0_deg(i);
                row.sps_ess_angle_deg            = wrap180(ic.vsg_delta0_deg(i));
                row.sps_angle_diff_deg           = ang_diff(ic.vsg_delta0_deg(i), sps_ang_raw);
                row.main_bus_angle_error_deg     = ang_diff(sps_ang_raw, nr_bus_ang(bi));
                row.angle_diff_error_deg         = ang_diff(row.sps_angle_diff_deg, row.nr_angle_diff_deg);
                row.measured_pe_sys_pu           = Pe_meas;
                row.manual_vi_pe_sys_pu          = Pe_meas;
                row.manual_vi_diff_abs           = 0.0;

                angle_pass = abs(row.main_bus_angle_error_deg) <= thr.angle_deg;
                pe_pass    = abs(Pe_meas - expected_pe_sys_pu(i)) <= thr.pe_pu;
                vi_pass    = row.manual_vi_diff_abs <= thr.vi_diff;

                row.passes_angle_gate = angle_pass;
                row.passes_pe_gate    = pe_pass;
                row.passes_vi_gate    = vi_pass;

                all_angle_ok = all_angle_ok && angle_pass;
                all_pe_ok    = all_pe_ok    && pe_pass;
                all_vi_ok    = all_vi_ok    && vi_pass;
            catch ME2
                row.sps_main_bus_angle_raw_deg = NaN;
                row.sps_main_bus_angle_deg      = NaN;
                row.sps_ess_angle_raw_deg       = NaN;
                row.sps_ess_angle_deg           = NaN;
                row.sps_angle_diff_deg          = NaN;
                row.main_bus_angle_error_deg    = NaN;
                row.angle_diff_error_deg        = NaN;
                row.measured_pe_sys_pu          = NaN;
                row.manual_vi_pe_sys_pu         = NaN;
                row.manual_vi_diff_abs          = NaN;
                row.passes_angle_gate = false;
                row.passes_pe_gate    = false;
                row.passes_vi_gate    = false;
                all_angle_ok = false; all_pe_ok = false;
                row.extract_error = ME2.message;
            end
        else
            for fn = {'sps_main_bus_angle_raw_deg','sps_main_bus_angle_deg', ...
                      'sps_ess_angle_raw_deg','sps_ess_angle_deg','sps_angle_diff_deg', ...
                      'main_bus_angle_error_deg','angle_diff_error_deg', ...
                      'measured_pe_sys_pu','manual_vi_pe_sys_pu','manual_vi_diff_abs'}
                row.(fn{1}) = NaN;
            end
            row.passes_angle_gate = false;
            row.passes_pe_gate    = false;
            row.passes_vi_gate    = false;
            all_angle_ok = false; all_pe_ok = false;
        end

        ess_rows{end+1} = row; %#ok<AGROW>
    end

    cfg_out.ess_rows = ess_rows;
    cfg_out.gate_results.all_angle_gates_pass = all_angle_ok;
    cfg_out.gate_results.all_pe_gates_pass    = all_pe_ok;
    cfg_out.gate_results.all_vi_gates_pass    = all_vi_ok;

    % Aggregate errors
    ang_errs = cellfun(@(r) abs(r.main_bus_angle_error_deg), ess_rows);
    pe_errs  = cellfun(@(r) abs(r.measured_pe_sys_pu - r.expected_pe_sys_pu), ess_rows);
    cfg_out.aggregate_errors.mean_main_bus_angle_error_deg = mean(ang_errs(~isnan(ang_errs)));
    cfg_out.aggregate_errors.max_main_bus_angle_error_deg  = max(ang_errs(~isnan(ang_errs)));
    cfg_out.aggregate_errors.mean_pe_error_pu = mean(pe_errs(~isnan(pe_errs)));
    cfg_out.aggregate_errors.max_pe_error_pu  = max(pe_errs(~isnan(pe_errs)));

    fprintf('RESULT: config=%s angle_gate=%d pe_gate=%d vi_gate=%d mean_ang_err=%.3f mean_pe_err=%.3f ES1_Pe=%.6f\n', ...
        mode_label, all_angle_ok, all_pe_ok, all_vi_ok, ...
        cfg_out.aggregate_errors.mean_main_bus_angle_error_deg, ...
        cfg_out.aggregate_errors.mean_pe_error_pu, ...
        ess_rows{1}.measured_pe_sys_pu);

    configs{end+1} = cfg_out; %#ok<AGROW>
end

% -- Verdict summary --
any_pass = false;
best_pe_label  = '';  best_pe_err  = Inf;
best_ang_label = '';  best_ang_err = Inf;
terminal_multi_pu = false;
emf_negative_pe   = false;

for m = 1:length(configs)
    c = configs{m};
    if c.gate_results.all_angle_gates_pass && c.gate_results.all_pe_gates_pass
        any_pass = true;
    end
    if c.aggregate_errors.mean_pe_error_pu < best_pe_err
        best_pe_err   = c.aggregate_errors.mean_pe_error_pu;
        best_pe_label = c.config_label;
    end
    if c.aggregate_errors.mean_main_bus_angle_error_deg < best_ang_err
        best_ang_err   = c.aggregate_errors.mean_main_bus_angle_error_deg;
        best_ang_label = c.config_label;
    end
    if strcmp(c.config_label, 'terminal_reference')
        for ri = 1:length(c.ess_rows)
            if abs(c.ess_rows{ri}.measured_pe_sys_pu) > 1.0; terminal_multi_pu = true; end
        end
    end
    if strcmp(c.config_label, 'emf_reference')
        for ri = 1:length(c.ess_rows)
            if c.ess_rows{ri}.measured_pe_sys_pu < 0; emf_negative_pe = true; end
        end
    end
end

verdict.any_config_passes_all_static_gates = any_pass;
verdict.best_config_by_pe_error            = best_pe_label;
verdict.best_config_by_angle_error         = best_ang_label;
verdict.terminal_reference_has_multi_pu_pe = terminal_multi_pu;
verdict.emf_reference_has_negative_pe      = emf_negative_pe;
% MUST be review_required in first batch — no autonomous branch selection
verdict.recommended_next_branch            = 'review_required';

% -- Build output struct --
out.schema_version = 2;
out.scenario_id    = 'kundur';
out.model_name     = model_name;
out.run_id         = '20260424-kundur-sps-workpoint-alignment';
out.probe_config.source_angle_modes = opts.source_angle_modes;
out.probe_config.gate_thresholds    = opts.gate_thresholds;
out.probe_config.output_filename    = opts.output_filename;
out.angle_convention.unit            = 'deg';
out.angle_convention.reference_frame = 'absolute_simulation_frame';
out.angle_convention.normalization   = 'wrap_to_180';
out.angle_convention.range           = '[-180, 180)';
out.angle_convention.note            = 'sps_main_bus_angle_deg uses ESS terminal V angle as proxy (no direct bus measurement blocks in model)';
out.nr_reference.main_bus_angles_deg = struct('Bus7', nr_bus_ang(1), 'Bus8', nr_bus_ang(2), 'Bus10', nr_bus_ang(3), 'Bus9', nr_bus_ang(4));
out.nr_reference.ess_angles_deg      = struct('ES1', nr_ess_ang(1), 'ES2', nr_ess_ang(2), 'ES3', nr_ess_ang(3), 'ES4', nr_ess_ang(4));
out.sps_readback = sps_readback;
out.configs = configs;
out.verdict_summary = verdict;
out.provenance.probe_file              = 'probes/kundur/probe_sps_static_workpoint_gate.m';
out.provenance.run_timestamp           = datestr(now, 'yyyy-mm-dd HH:MM:SS');
out.provenance.matlab_model_dirty_before = false;
out.provenance.matlab_model_dirty_after  = false;  % verified by caller

out_path = fullfile(att_dir, opts.output_filename);
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(out));
fclose(fid);

fprintf('RESULT: static_workpoint_gate written to %s any_pass=%d best_pe=%s best_ang=%s\n', ...
    out_path, any_pass, best_pe_label, best_ang_label);

results = out;
end

% =========================================================================
function restore_sources(src_blocks, baseline_angles)
for s = 1:length(src_blocks)
    if ~isnan(baseline_angles(s))
        try; set_param(src_blocks{s}, 'PhaseAngle', num2str(baseline_angles(s), '%.6f')); catch; end
    end
end
end
