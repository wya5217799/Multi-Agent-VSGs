function paths = ee_lib_paths()
% ee_lib_paths  Resolve ee_lib / nesl_utility block library paths.
%
% Returns a struct with verified block library paths for use in build scripts.
% ee_lib and nesl_utility must already be loaded before calling this function.
%
% Fields:
%   .cvs        Controlled Voltage Source (Three-Phase)
%   .pvs        Programmable Voltage Source (Three-Phase)
%   .tl         Transmission Line (Three-Phase)
%   .wl         Wye-Connected Load
%   .rlc3       RLC (Three-Phase)
%   .gnd        Electrical Reference
%   .dynload3ph Dynamic Load (Three-Phase)
%   .ps         Power Sensor (Three-Phase)
%   .solver     Solver Configuration
%   .s2ps       Simulink-PS Converter
%   .ps2s       PS-Simulink Converter
%
% Usage (in build scripts):
%   load_system('ee_lib'); load_system('nesl_utility');
%   paths = ee_lib_paths();
%   add_block(paths.cvs, [mdl '/MyCVS']);
%
% To print all paths for a new MATLAB version, run discover_ee_lib_paths.m.

if ~bdIsLoaded('ee_lib') || ~bdIsLoaded('nesl_utility')
    error('[ee_lib_paths] ee_lib and nesl_utility must be loaded first. Call load_system(''ee_lib'') and load_system(''nesl_utility'') before invoking ee_lib_paths().');
end

paths.cvs  = resolve_one(find_system('ee_lib/Sources', 'SearchDepth', 1, ...
    'RegExp', 'on', 'Name', '.*Controlled Voltage.*Three.*'), ...
    'Controlled Voltage Source (Three-Phase)');

paths.pvs  = resolve_one(find_system('ee_lib/Sources', 'SearchDepth', 1, ...
    'RegExp', 'on', 'Name', '.*Programmable Voltage.*Three.*'), ...
    'Programmable Voltage Source (Three-Phase)');

paths.tl   = resolve_one(find_system('ee_lib', 'SearchDepth', 5, ...
    'RegExp', 'on', 'Name', '.*Transmission Line.*Three.*'), ...
    'Transmission Line (Three-Phase)');

paths.wl   = resolve_one(find_system('ee_lib', 'SearchDepth', 5, ...
    'Name', 'Wye-Connected Load'), 'Wye-Connected Load');

paths.rlc3 = resolve_one(find_system('ee_lib/Passive/RLC Assemblies', 'SearchDepth', 1, ...
    'Name', 'RLC (Three-Phase)'), 'RLC (Three-Phase)');

paths.gnd  = resolve_one(find_system('ee_lib', 'SearchDepth', 3, ...
    'Name', 'Electrical Reference'), 'Electrical Reference');

paths.ps   = resolve_one(find_system('ee_lib', 'SearchDepth', 5, ...
    'RegExp', 'on', 'Name', '.*Power Sensor.*Three.*'), ...
    'Power Sensor (Three-Phase)');

paths.solver = resolve_one(find_system('nesl_utility', 'SearchDepth', 1, ...
    'Name', 'Solver Configuration'), 'Solver Configuration');

paths.s2ps = resolve_one(find_system('nesl_utility', 'SearchDepth', 2, ...
    'RegExp', 'on', 'Name', '.*Simulink-PS.*'), 'Simulink-PS Converter');

paths.ps2s = resolve_one(find_system('nesl_utility', 'SearchDepth', 2, ...
    'RegExp', 'on', 'Name', '.*PS-Simulink.*'), 'PS-Simulink Converter');

% Dynamic Load: two-depth fallback (R2025b SearchDepth=3 sometimes misses).
dl3ph_res = find_system('ee_lib', 'SearchDepth', 3, 'RegExp', 'on', 'Name', 'Dynamic Load.*Three.*');
if isempty(dl3ph_res)
    dl3ph_res = find_system('ee_lib', 'SearchDepth', 5, 'RegExp', 'on', 'Name', 'Dynamic Load.*Three.*');
end
if isempty(dl3ph_res)
    error('[ee_lib_paths] Dynamic Load (Three-Phase) not found in ee_lib. Check Simscape Electrical R2025b.');
end
paths.dynload3ph = strtrim(char(dl3ph_res(1)));

end


function s = resolve_one(result, label)
% Take first row of a find_system result, strip whitespace; error if empty.
if isempty(result)
    error('[ee_lib_paths] Block not found: %s. Ensure ee_lib/nesl_utility is loaded.', label);
end
s = strtrim(char(result(1,:)));
end
