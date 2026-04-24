%% test_simpgen_minimal.m - Absolute minimal: 1 SimpGen + 1 Load
mdl = 'test_sg_min';
try close_system(mdl,0);catch;end
if exist([mdl '.slx'],'file'),delete([mdl '.slx']);end
new_system(mdl); open_system(mdl);
load_system('ee_lib'); load_system('nesl_utility'); load_system('fl_lib');

Vbase=230e3; fn=60; omega_s=2*pi*fn; Sn=900e6;
Vint=Vbase/sqrt(3); H=6.5;
J=2*H*Sn/omega_s^2;

% Solver settings - try multiple approaches
set_param(mdl,'Solver','ode15s','StopTime','3','RelTol','1e-3','MaxStep','0.001');

% References
add_block('nesl_utility/Solver Configuration',[mdl '/Solver'],'Position',[50,20,140,60]);
add_block('ee_lib/Connectors & References/Electrical Reference',[mdl '/GND'],'Position',[200,20,240,60]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference',[mdl '/MR'],'Position',[320,20,360,60]);
add_line(mdl,'Solver/RConn1','GND/LConn1');

% Simplified Generator
add_block('ee_lib/Electromechanical/Simplified Generator',[mdl '/G'],'Position',[300,150,400,300]);
set_param([mdl '/G'],'RatedPower',num2str(Sn*0.85),'FRated','60');
set_param([mdl '/G'],'VinternalRMS',num2str(Vint));
set_param([mdl '/G'],'RotorInertia',num2str(J));
set_param([mdl '/G'],'RotorDamping','50');
set_param([mdl '/G'],'Fdroop','0.05');

% Free End on shaft
add_block('fl_lib/Mechanical/Rotational Elements/Rotational Free End',[mdl '/FE'],'Position',[230,210,260,240]);
add_line(mdl,'FE/LConn1','G/LConn1');
% Ref on LConn2
add_line(mdl,'G/LConn2','MR/LConn1');
% Neutral
add_line(mdl,'G/RConn2','GND/LConn1');

% Load (P = rated power, purely resistive)
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',[mdl '/Load'],'Position',[450,200,530,280]);
set_param([mdl '/Load'],'VRated',num2str(Vbase),'FRated','60','P',num2str(Sn*0.85));
set_param([mdl '/Load'],'component_structure','ee.enum.rlc.structure.R');
add_line(mdl,'G/RConn1','Load/LConn1');

try set_param(mdl,'SimscapeLogType','all','SimscapeLogName','simlog');catch;end
save_system(mdl);

fprintf('=== Test 1: FreeEnd + ode15s ===\n');
try
    tic; out=sim(mdl,'StopTime','1'); fprintf('OK in %.1fs\n',toc);
    try
        v=out.simlog.G.omegaDel.series.values;
        fprintf('  omegaDel: [%.6f, %.6f] pu\n',min(v),max(v));
        fprintf('  Δf: [%.4f, %.4f] Hz\n',min(v)*60,max(v)*60);
    catch e, fprintf('  %s\n',e.message);end
catch e, fprintf('FAIL(%.1fs): %s\n',toc,e.message);end

fprintf('\n=== Test 2: FreeEnd + ode23t (original) ===\n');
set_param(mdl,'Solver','ode23t','MaxStep','0.001');
try
    tic; out=sim(mdl,'StopTime','1'); fprintf('OK in %.1fs\n',toc);
    try
        v=out.simlog.G.omegaDel.series.values;
        fprintf('  Δf: [%.4f, %.4f] Hz\n',min(v)*60,max(v)*60);
    catch e, fprintf('  %s\n',e.message);end
catch e, fprintf('FAIL(%.1fs): %s\n',toc,e.message);end

fprintf('\n=== Test 3: Both ports to MechRef (original, expect Δf=0) ===\n');
% Reconnect LConn1 to MechRef
try ph=get_param([mdl '/FE'],'PortHandles');
    lh=get_param(ph.LConn(1),'Line'); if lh~=-1,delete_line(lh);end
    delete_block([mdl '/FE']);
catch;end
add_line(mdl,'G/LConn1','MR/LConn1');
set_param(mdl,'Solver','ode23t','MaxStep','0.01');
try
    tic; out=sim(mdl,'StopTime','1'); fprintf('OK in %.1fs\n',toc);
    try
        v=out.simlog.G.omegaDel.series.values;
        fprintf('  Δf: [%.4f, %.4f] Hz (expect 0)\n',min(v)*60,max(v)*60);
    catch e, fprintf('  %s\n',e.message);end
catch e, fprintf('FAIL(%.1fs): %s\n',toc,e.message);end

close_system(mdl,0);
