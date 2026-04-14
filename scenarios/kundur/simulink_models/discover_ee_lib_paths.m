%% discover_ee_lib_paths.m
% One-time diagnostic: print all ee_lib/nesl_utility library paths for the
% current MATLAB installation.
%
% Run this before building a model on a new MATLAB version or installation.
% Copy any changed paths into docs/knowledge/simulink_base.md.
%
% Usage:
%   cd('<project_root>/scenarios/kundur/simulink_models')
%   discover_ee_lib_paths

load_system('ee_lib');
load_system('nesl_utility');
paths = ee_lib_paths();

fprintf('\n=== ee_lib / nesl_utility Library Paths ===\n');
fprintf('  CVS (Controlled Voltage Source 3ph): %s\n', paths.cvs);
fprintf('  PVS (Programmable Voltage Source 3ph): %s\n', paths.pvs);
fprintf('  TL  (Transmission Line 3ph):           %s\n', paths.tl);
fprintf('  WL  (Wye-Connected Load):              %s\n', paths.wl);
fprintf('  RLC3 (RLC Three-Phase):                %s\n', paths.rlc3);
fprintf('  GND (Electrical Reference):            %s\n', paths.gnd);
fprintf('  DynLoad3ph (Dynamic Load Three-Phase): %s\n', paths.dynload3ph);
fprintf('  PSensor (Power Sensor Three-Phase):    %s\n', paths.ps);
fprintf('  Solver (Solver Configuration):         %s\n', paths.solver);
fprintf('  S2PS (Simulink-PS Converter):          %s\n', paths.s2ps);
fprintf('  PS2S (PS-Simulink Converter):          %s\n', paths.ps2s);
fprintf('=== Done. Update simulink_base.md if any path changed. ===\n');
