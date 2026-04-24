function results = probe_sps_workpoint_alignment(model_name, run_dir, mode)
% PROBE_SPS_WORKPOINT_ALIGNMENT
% Reusable Kundur SPS/Phasor workpoint diagnostic.
%
% Modes:
%   nr_only    - write nr_reference.json (runs compute_kundur_powerflow)
%   vi_only    - write ess1_vi_baseline.json (runs sim + VxI calculation)
%   bus7_only  - write bus7_angle_probe.json (reads existing workspace signals)
%   sweep_only - write ess1_phang_sweep.json (phAng_ES1 sweep loop)
%   all        - run all modes above in sequence
%
% Contract:
%   - No saved model edits. Never calls save_system.
%   - JSON artifacts written under run_dir/attachments/
%   - RESULT: lines printed for MCP quiet runner capture.
%   - addpath is called internally for required helpers.
%
% Args:
%   model_name - string, e.g. 'kundur_vsg_sps'
%   run_dir    - string, path to run directory (artifacts go in run_dir/attachments/)
%   mode       - string, one of: 'nr_only','vi_only','bus7_only','sweep_only','all'
%
% Returns:
%   results - struct with mode-specific fields

if nargin < 1; model_name = 'kundur_vsg_sps'; end
if nargin < 2; run_dir    = fullfile(pwd, 'run_probe'); end
if nargin < 3; mode       = 'all'; end

repo    = fileparts(fileparts(fileparts(mfilename('fullpath'))));
att_dir = fullfile(run_dir, 'attachments');
if ~exist(att_dir, 'dir'); mkdir(att_dir); end

results = struct();

switch lower(mode)
    case 'nr_only'
        results = run_nr_only(repo, att_dir);
    case 'vi_only'
        results = run_vi_only(model_name, repo, att_dir);
    case 'bus7_only'
        results = run_bus7_only(att_dir);
    case 'sweep_only'
        results = run_sweep_only(model_name, att_dir);
    case 'all'
        results.nr    = run_nr_only(repo, att_dir);
        results.vi    = run_vi_only(model_name, repo, att_dir);
        results.sweep = run_sweep_only(model_name, att_dir);
    otherwise
        error('probe_sps_workpoint_alignment: unknown mode "%s"', mode);
end

end

% =========================================================================
function results = run_nr_only(repo, att_dir)

addpath(fullfile(repo, 'scenarios', 'kundur', 'matlab_scripts'));
json_path = fullfile(repo, 'scenarios', 'kundur', 'kundur_ic.json');
pf = compute_kundur_powerflow(json_path);

ref.converged           = pf.converged;
ref.iterations          = pf.iterations;
ref.max_mismatch        = pf.max_mismatch;
ref.bus_ids             = pf.bus_ids(:)';
ref.main_bus_ang_abs_deg = pf.main_bus_ang_abs_deg(:)';
ref.ess_delta_deg       = pf.ess_delta_deg(:)';
ref.gen_delta_deg       = pf.gen_delta_deg(:)';
ref.G1_terminal_deg     = 20.0;
ref.G1_emf_deg          = pf.G1_emf_deg;
ref.gen_emf_deg_ext     = pf.gen_emf_deg_ext(:)';

out_path = fullfile(att_dir, 'nr_reference.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(ref));
fclose(fid);

fprintf('RESULT: nr_converged=%d max_mismatch=%.3e bus7_abs=%.6f ess1_delta=%.6f G1_terminal=%.6f G1_emf=%.6f\n', ...
    ref.converged, ref.max_mismatch, ref.main_bus_ang_abs_deg(1), ...
    ref.ess_delta_deg(1), ref.G1_terminal_deg, ref.G1_emf_deg);

results = ref;
end

% =========================================================================
function results = run_vi_only(model_name, repo, att_dir)

addpath(fullfile(repo, 'slx_helpers', 'vsg_bridge'));

Sbase    = 100e6;
vi_scale = 0.5;

simOut = sim(model_name, 'StopTime', '0.05');

Vabc_ts = simOut.get('Vabc_ES1');
Iabc_ts = simOut.get('Iabc_ES1');

V_row = Vabc_ts.Data(end, :);
I_row = Iabc_ts.Data(end, :);

V_cmplx = V_row(1) + 1j*V_row(2);
I_cmplx = I_row(1) + 1j*I_row(2);

raw_W      = real(sum(V_row .* conj(I_row)));
Pe_sys_pu  = vi_scale * raw_W / Sbase;

% Independent verification via slx_build_bridge_config + slx_extract_state
cfg = slx_build_bridge_config( ...
    '', '', 'omega_ES{idx}', 'Vabc_ES{idx}', 'Iabc_ES{idx}', ...
    '', [model_name '/VSrc_ES{idx}'], 200e6, 'delta_ES{idx}', '', ...
    'M0_val_ES{idx}', 'D0_val_ES{idx}', 'vi', 'absolute_with_loadflow', ...
    zeros(1, 4), 1.0, 'PeFb_ES{idx}', vi_scale);

[state, meas_failures] = slx_extract_state(simOut, 1:4, cfg, Sbase);
Pe_extract = state.Pe(1);

V_mag   = abs(V_cmplx);
V_ang   = angle(V_cmplx) * 180/pi;
I_mag   = abs(I_cmplx);
I_ang   = angle(I_cmplx) * 180/pi;

vi.V_real           = real(V_cmplx);
vi.V_imag           = imag(V_cmplx);
vi.V_mag            = V_mag;
vi.V_angle_deg      = V_ang;
vi.I_real           = real(I_cmplx);
vi.I_imag           = imag(I_cmplx);
vi.I_mag            = I_mag;
vi.I_angle_deg      = I_ang;
vi.raw_W_before_peak_scale   = raw_W;
vi.vi_scale                  = vi_scale;
vi.Pe_sys_pu                 = Pe_sys_pu;
vi.slx_extract_state_Pe_sys_pu  = Pe_extract;
vi.slx_extract_state_failures   = meas_failures;
vi.diff_manual_minus_extract    = Pe_sys_pu - Pe_extract;

out_path = fullfile(att_dir, 'ess1_vi_baseline.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(vi));
fclose(fid);

fprintf('RESULT: ESS1_raw_W=%.6e ESS1_Pe_manual=%.9f ESS1_Pe_extract=%.9f diff=%.3e VangA=%.6f IangA=%.6f\n', ...
    raw_W, Pe_sys_pu, Pe_extract, vi.diff_manual_minus_extract, V_ang, I_ang);

results = vi;
end

% =========================================================================
function results = run_bus7_only(att_dir)

ref_path = fullfile(att_dir, 'nr_reference.json');
if ~exist(ref_path, 'file')
    fprintf('RESULT: bus7_only SKIPPED (nr_reference.json not found — run nr_only first)\n');
    results = struct('skipped', true);
    return;
end

fid  = fopen(ref_path, 'r');
raw  = fread(fid, '*char')';
fclose(fid);
ref  = jsondecode(raw);
nr_bus7_deg = ref.main_bus_ang_abs_deg(1);

% Try reading signals from base workspace
missing = false;
try
    Vabc_Bus7 = evalin('base', 'Vabc_Bus7_probe');
catch
    missing = true;
end

if missing
    fprintf('RESULT: bus7_only SKIPPED (no Vabc_Bus7_probe in workspace)\n');
    results = struct('skipped', true);
    return;
end

try
    Vabc_ES1 = evalin('base', 'Vabc_ES1');
    Iabc_ES1 = evalin('base', 'Iabc_ES1');
catch ME
    fprintf('RESULT: bus7_only SKIPPED (Vabc_ES1/Iabc_ES1 not in workspace: %s)\n', ME.message);
    results = struct('skipped', true);
    return;
end

% Last row of each signal (timeseries or plain matrix)
V7_row  = extract_last_row(Vabc_Bus7);
VES_row = extract_last_row(Vabc_ES1);
IES_row = extract_last_row(Iabc_ES1);

sps_bus7_deg  = angle(V7_row(1)  + 1j*V7_row(2))  * 180/pi;
ess1_v_deg    = angle(VES_row(1) + 1j*VES_row(2)) * 180/pi;
angle_error   = sps_bus7_deg - nr_bus7_deg;
ess1_vs_bus7  = ess1_v_deg  - sps_bus7_deg;

b7.nr_bus7_deg     = nr_bus7_deg;
b7.sps_bus7_deg    = sps_bus7_deg;
b7.ess1_v_deg      = ess1_v_deg;
b7.angle_error_deg = angle_error;
b7.ess1_minus_bus7 = ess1_vs_bus7;

out_path = fullfile(att_dir, 'bus7_angle_probe.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(b7));
fclose(fid);

fprintf('RESULT: nr_bus7=%.6f sps_bus7=%.6f ess1_v=%.6f angle_error=%.6f ess1_minus_bus7=%.6f\n', ...
    nr_bus7_deg, sps_bus7_deg, ess1_v_deg, angle_error, ess1_vs_bus7);

results = b7;
end

% =========================================================================
function results = run_sweep_only(model_name, att_dir)

Sbase    = 100e6;
vi_scale = 0.5;
angles   = 0:2.5:40;

if ~bdIsLoaded(model_name)
    load_system(model_name);
end

n      = length(angles);
pts    = struct('phAng_deg', cell(1,n), 'Pe_sys_pu', cell(1,n), ...
                'V_angle_deg', cell(1,n), 'omega_end', cell(1,n));

for k = 1:n
    assignin('base', 'phAng_ES1', angles(k));
    simOut = sim(model_name, 'StopTime', '0.05');

    Vabc_ts = simOut.get('Vabc_ES1');
    Iabc_ts = simOut.get('Iabc_ES1');
    V_row   = Vabc_ts.Data(end, :);
    I_row   = Iabc_ts.Data(end, :);
    raw_W   = real(sum(V_row .* conj(I_row)));

    Pe_k = vi_scale * raw_W / Sbase;
    V_ang_k = angle(V_row(1)) * 180/pi;   % complex phasor: direct phase-A angle

    omega_k = NaN;
    try
        om_ts   = simOut.get('omega_ES1');
        omega_k = om_ts.Data(end);
    catch
    end

    pts(k).phAng_deg   = angles(k);
    pts(k).Pe_sys_pu   = Pe_k;
    pts(k).V_angle_deg = V_ang_k;
    pts(k).omega_end   = omega_k;
end

% Find zero crossing of Pe by linear interpolation
Pe_vals = [pts.Pe_sys_pu];
zero_cross_deg = NaN;
for k = 1:n-1
    if Pe_vals(k) * Pe_vals(k+1) <= 0
        % Linear interpolation between angles(k) and angles(k+1)
        dPe = Pe_vals(k+1) - Pe_vals(k);
        if abs(dPe) > 1e-15
            zero_cross_deg = angles(k) - Pe_vals(k) * (angles(k+1) - angles(k)) / dPe;
        else
            zero_cross_deg = angles(k);
        end
        break;
    end
end

sw.results        = pts;
sw.zero_cross_deg = zero_cross_deg;
sw.n_points       = n;

out_path = fullfile(att_dir, 'ess1_phang_sweep.json');
fid = fopen(out_path, 'w');
fprintf(fid, '%s', jsonencode(sw));
fclose(fid);

fprintf('RESULT: ESS1_sweep_zero_cross_deg=%.6f points=%d\n', zero_cross_deg, n);

results = sw;
end

% =========================================================================
function row = extract_last_row(sig)
% Handle timeseries, Simulink.SimulationData.Signal, or plain matrix.
if isa(sig, 'timeseries') || (isstruct(sig) && isfield(sig, 'Data'))
    d = sig.Data;
elseif isnumeric(sig)
    d = sig;
else
    try
        d = sig.Data;
    catch
        d = double(sig);
    end
end
if size(d, 1) > 1
    row = d(end, :);
else
    row = d;
end
end
