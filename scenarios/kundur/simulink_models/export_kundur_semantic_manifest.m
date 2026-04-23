% USAGE CONTRACT
% This function is NOT called automatically by the Python harness.
% To export: call via simulink_run_script after simulink_load_model succeeds.
%   export_kundur_semantic_manifest(model_name, out_path)
% where out_path = results/harness/<scenario>/<run_id>/attachments/semantic_manifest.json
% The Python harness (harness_model_inspect) reads this file on demand if it exists.

function payload = export_kundur_semantic_manifest(model_name, out_path)
load_system(model_name);

payload.schema_version = 1;
payload.scenario_id = 'kundur';
payload.model_name = model_name;
has_powergui = ~isempty(find_system(model_name, 'SearchDepth', 1, 'Name', 'powergui'));
if has_powergui
    payload.solver.family = 'sps_phasor';
else
    payload.solver.family = 'simscape_ee';
end
payload.solver.has_solver_config = ~isempty(find_system(model_name, 'SearchDepth', 1, 'Name', 'SolverConfig'));
payload.initialization.uses_pref_ramp = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', 'PrefRamp_.*'));
if payload.initialization.uses_pref_ramp
    payload.initialization.warmup_mode = 'physics_compensation';
else
    payload.initialization.warmup_mode = 'technical_reset_only';
end
has_vi = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', '.*VIMeas.*'));
has_pefb = ~isempty(find_system(model_name, 'Regexp', 'on', 'Name', 'Log_PeFb_.*'));
if has_vi
    payload.measurement.mode = 'vi';
elseif has_pefb
    payload.measurement.mode = 'feedback';
else
    payload.measurement.mode = 'unknown';
end
payload.units = struct([]);
payload.disturbances = struct([]);

txt = jsonencode(payload);
fid = fopen(out_path, 'w');
fprintf(fid, '%s\n', txt);
fclose(fid);
end
