%% test_simpgen_disturbance.m - 1 SimpGen + Load + Step Disturbance
mdl = 'test_sg_dist';
try close_system(mdl,0);catch;end
if exist([mdl '.slx'],'file'),delete([mdl '.slx']);end
new_system(mdl); open_system(mdl);
load_system('ee_lib'); load_system('nesl_utility'); load_system('fl_lib'); load_system('simulink');

Vbase=230e3; fn=60; omega_s=2*pi*fn; Sn=900e6;
Vint=Vbase/sqrt(3); H=6.5; J=2*H*Sn/omega_s^2;
Pm=Sn*0.85;

set_param(mdl,'Solver','ode15s','StopTime','3','RelTol','1e-3','MaxStep','0.001');

% Refs
add_block('nesl_utility/Solver Configuration',[mdl '/Solver'],'Position',[50,20,140,60]);
add_block('ee_lib/Connectors & References/Electrical Reference',[mdl '/GND'],'Position',[200,20,240,60]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference',[mdl '/MR'],'Position',[320,20,360,60]);
add_line(mdl,'Solver/RConn1','GND/LConn1');

% Generator
add_block('ee_lib/Electromechanical/Simplified Generator',[mdl '/G'],'Position',[300,150,400,300]);
set_param([mdl '/G'],'RatedPower',num2str(Pm),'FRated','60','VinternalRMS',num2str(Vint));
set_param([mdl '/G'],'RotorInertia',num2str(J),'RotorDamping','50','Fdroop','0.05');
% Free End on shaft
add_block('fl_lib/Mechanical/Rotational Elements/Rotational Free End',[mdl '/FE'],'Position',[230,210,260,240]);
add_line(mdl,'FE/LConn1','G/LConn1');
add_line(mdl,'G/LConn2','MR/LConn1');
add_line(mdl,'G/RConn2','GND/LConn1');

% Steady-state load (matched to generation)
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',[mdl '/Load'],'Position',[450,180,530,260]);
set_param([mdl '/Load'],'VRated',num2str(Vbase),'FRated','60','P',num2str(Pm));
set_param([mdl '/Load'],'component_structure','ee.enum.rlc.structure.R');
add_line(mdl,'G/RConn1','Load/LConn1');

% DISTURBANCE: +10% load step at t=1s via SPST switch
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',[mdl '/DLoad'],'Position',[550,300,630,380]);
set_param([mdl '/DLoad'],'VRated',num2str(Vbase),'FRated','60','P',num2str(Pm*0.1));
set_param([mdl '/DLoad'],'component_structure','ee.enum.rlc.structure.R');

add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)',[mdl '/SW'],'Position',[450,310,510,380]);
add_block('nesl_utility/Simulink-PS Converter',[mdl '/S2PS'],'Position',[390,320,420,350]);
add_block('simulink/Sources/Step',[mdl '/Step'],'Position',[330,325,370,345]);
set_param([mdl '/Step'],'Time','1','Before','0','After','1');

add_line(mdl,'Step/1','S2PS/1');
add_line(mdl,'S2PS/RConn1','SW/LConn1');
add_line(mdl,'G/RConn1','SW/LConn2');
add_line(mdl,'SW/RConn1','DLoad/LConn1');

try set_param(mdl,'SimscapeLogType','all','SimscapeLogName','simlog');catch;end
save_system(mdl);

% Simulate
fprintf('Simulating with disturbance at t=1...\n');
tic;
try
    out = sim(mdl);
    fprintf('Done in %.1fs\n', toc);
    simlog = out.simlog;
    v = simlog.G.omegaDel.series.values;
    t = simlog.G.omegaDel.series.time;
    fprintf('omegaDel range: [%.6f, %.6f] pu\n', min(v), max(v));
    fprintf('Δf range: [%.4f, %.4f] Hz\n', min(v)*60, max(v)*60);

    % Find value at t=1.5 (after disturbance)
    idx = find(t > 1.5, 1);
    if ~isempty(idx)
        fprintf('At t=1.5s: omegaDel=%.6f, Δf=%.4f Hz\n', v(idx), v(idx)*60);
    end
catch e
    fprintf('FAILED (%.1fs): %s\n', toc, e.message);
end
close_system(mdl, 0);
