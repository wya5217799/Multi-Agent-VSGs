function results = probe_sps_source_angle_hypotheses(model_name, run_dir)
% PROBE_SPS_SOURCE_ANGLE_HYPOTHESES
% Reusable unsaved comparison of EMF-angle and terminal-angle source semantics.
%
% Contract:
%   - Read baseline source parameters first.
%   - Run 4 experiments: baseline, G1-terminal-only, all-terminal, EMF-restore.
%   - Restore every patched source parameter with onCleanup (ALWAYS, even on error).
%   - Write run_dir/attachments/source_angle_experiments.json.
%   - Never calls save_system.
%
% Args:
%   model_name - string, e.g. 'kundur_vsg_sps'
%   run_dir    - string, path to run directory
%
% Returns:
%   results - struct with experiments array and conclusion fields

if nargin < 1; model_name = 'kundur_vsg_sps'; end
if nargin < 2; run_dir    = fullfile(pwd, 'run_probe'); end

repo    = fileparts(fileparts(fileparts(mfilename('fullpath'))));
att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir'); mkdir(att_dir); end

% Load nr_reference.json for G1_terminal_deg and gen_delta_deg
ref_path = fullfile(att_dir, 'nr_reference.json');
if ~exist(ref_path, 'file')
    error('probe_sps_source_angle_hypotheses: nr_reference.json not found in %s — run nr_only first', att_dir);
end
fid = fopen(ref_path, 'r');
raw = fread(fid, '*char')';
fclose(fid);
ref = jsondecode(raw);

G1_terminal_deg = ref.G1_terminal_deg;          % scalar
gen_delta_deg   = ref.gen_delta_deg(:)';        % 1×4 [G2,G3,W1,W2]

% Ensure model is loaded
if ~bdIsLoaded(model_name)
    load_system(model_name);
end

% Source blocks in the model
src_blocks = { ...
    [model_name '/GSrc_G1'], ...
    [model_name '/GSrc_G2'], ...
    [model_name '/GSrc_G3'], ...
    [model_name '/WSrc_W1'], ...
    [model_name '/WSrc_W2'] };
src_labels = {'GSrc_G1', 'GSrc_G2', 'GSrc_G3', 'WSrc_W1', 'WSrc_W2'};
param_names = {'PhaseAngle', 'Voltage', 'NonIdealSource', 'SpecifyImpedance', ...
                'Resistance', 'Inductance'};

% Read baseline BEFORE any patch
n_src = length(src_blocks);
baseline_params(n_src) = struct();
for si = 1:n_src
    baseline_params(si).block = src_blocks{si};
    baseline_params(si).label = src_labels{si};
    for pj = 1:length(param_names)
        pn = param_names{pj};
        try
            baseline_params(si).(pn) = get_param(src_blocks{si}, pn);
        catch
            baseline_params(si).(pn) = '';
        end
    end
end

% Register cleanup IMMEDIATELY after reading baseline
cleanup = onCleanup(@() restore_baseline_sources(baseline_params)); %#ok<NASGU>

Sbase    = 100e6;
vi_scale = 0.5;

% ---- Experiment A: baseline (no patch) ----
exp_A = run_experiment('baseline', model_name, {}, {}, Sbase, vi_scale);

% ---- Experiment B: G1 terminal angle only ----
exp_B = run_experiment('G1_terminal_only', model_name, ...
    {[model_name '/GSrc_G1']}, ...
    {{'PhaseAngle', num2str(G1_terminal_deg, '%.6f')}}, ...
    Sbase, vi_scale);
restore_baseline_sources(baseline_params);

% ---- Experiment C: all sources at terminal angles ----
% G1 → G1_terminal_deg; G2/G3/W1/W2 → gen_delta_deg(1:4)
c_blocks = src_blocks;
c_params = { ...
    {'PhaseAngle', num2str(G1_terminal_deg,     '%.6f')}, ...
    {'PhaseAngle', num2str(gen_delta_deg(1),    '%.6f')}, ...
    {'PhaseAngle', num2str(gen_delta_deg(2),    '%.6f')}, ...
    {'PhaseAngle', num2str(gen_delta_deg(3),    '%.6f')}, ...
    {'PhaseAngle', num2str(gen_delta_deg(4),    '%.6f')} };
exp_C = run_experiment('all_terminal', model_name, c_blocks, c_params, Sbase, vi_scale);
restore_baseline_sources(baseline_params);

% ---- Experiment D: restore EMF (control group — explicitly re-apply baseline) ----
% The cleanup would also do this; here we do it explicitly for logging clarity.
restore_baseline_sources(baseline_params);
exp_D = run_experiment('EMF_restore', model_name, {}, {}, Sbase, vi_scale);

% ---- Conclusion ----
expected_pe_sys = 0.1 * (200e6 / 100e6);  % fallback only if JSON read fails
try
    repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    addpath(fullfile(repo, 'slx_helpers', 'vsg_bridge'));
    ic = slx_load_kundur_ic(fullfile(repo, 'scenarios', 'kundur', 'kundur_ic.json'));
    expected_pe_sys = ic.vsg_p0_vsg_base_pu(1) * (200e6 / 100e6);
catch
end

abs_tol = 0.05;
sign_improved = (exp_C.Pe_sys_pu > 0) && (exp_A.Pe_sys_pu < 0);
terminal_magnitude_ok = abs(exp_C.Pe_sys_pu - expected_pe_sys) <= abs_tol;

conclusion.expected_ess1_pe_sys_pu = expected_pe_sys;
conclusion.abs_tol_sys_pu = abs_tol;
conclusion.terminal_sign_improved = sign_improved;
conclusion.terminal_magnitude_ok = terminal_magnitude_ok;
conclusion.terminal_fix_promising = sign_improved && terminal_magnitude_ok;
conclusion.invalid_if_sign_only = sign_improved && ~terminal_magnitude_ok;
conclusion.g1_only_shift_deg      = exp_B.V_angle_deg - exp_A.V_angle_deg;

% ---- Write JSON ----
out.baseline_params  = baseline_params;
out.experiments      = {exp_A, exp_B, exp_C, exp_D};
out.conclusion       = conclusion;

out_path = fullfile(att_dir, 'source_angle_experiments.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(out));
fclose(fid);

fprintf('RESULT: expA_Pe=%.6f expB_Pe=%.6f expC_Pe=%.6f expD_Pe=%.6f terminal_sign_improved=%d terminal_magnitude_ok=%d terminal_fix_promising=%d\n', ...
    exp_A.Pe_sys_pu, exp_B.Pe_sys_pu, exp_C.Pe_sys_pu, exp_D.Pe_sys_pu, ...
    conclusion.terminal_sign_improved, conclusion.terminal_magnitude_ok, conclusion.terminal_fix_promising);

results.experiments  = {exp_A, exp_B, exp_C, exp_D};
results.conclusion   = conclusion;
end

% =========================================================================
function exp = run_experiment(label, model_name, blocks, param_sets, Sbase, vi_scale)
% Apply patches, run 50 ms sim, read ES1 V/I/Pe, restore nothing (caller restores).

for bi = 1:length(blocks)
    for pj = 1:size(param_sets{bi}, 1)
        set_param(blocks{bi}, param_sets{bi}{pj, 1}, param_sets{bi}{pj, 2});
    end
end

simOut = sim(model_name, 'StopTime', '0.05');

Vabc_ts = simOut.get('Vabc_ES1');
Iabc_ts = simOut.get('Iabc_ES1');
V_row   = Vabc_ts.Data(end, :);
I_row   = Iabc_ts.Data(end, :);
raw_W   = real(sum(V_row .* conj(I_row)));

Pe_k    = vi_scale * raw_W / Sbase;
V_ang   = angle(V_row(1)) * 180/pi;   % complex phasor
I_ang   = angle(I_row(1)) * 180/pi;   % complex phasor

exp.label       = label;
exp.Pe_sys_pu   = Pe_k;
exp.V_angle_deg = V_ang;
exp.I_angle_deg = I_ang;
end

% =========================================================================
function restore_baseline_sources(baseline_params)
param_names = {'PhaseAngle', 'Voltage', 'NonIdealSource', 'SpecifyImpedance', ...
                'Resistance', 'Inductance'};
for si = 1:length(baseline_params)
    blk = baseline_params(si).block;
    for pj = 1:length(param_names)
        pn  = param_names{pj};
        val = baseline_params(si).(pn);
        if ~isempty(val)
            try
                set_param(blk, pn, val);
            catch
            end
        end
    end
end
end
