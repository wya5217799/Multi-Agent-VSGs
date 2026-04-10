%% test_simpgen_torque.m - 1 SimpGen with Torque Source + Disturbance
% Test if omegaDel responds when mechanical power is provided externally
mdl = 'test_sg_torque';
try close_system(mdl,0);catch;end
if exist([mdl '.slx'],'file'),delete([mdl '.slx']);end
new_system(mdl); open_system(mdl);
load_system('ee_lib'); load_system('nesl_utility'); load_system('fl_lib'); load_system('simulink');

Vbase=230e3; fn=60; omega_s=2*pi*fn; Sn=900e6;
Vint=Vbase/sqrt(3); H=6.5; J=2*H*Sn/omega_s^2;
Pm=Sn*0.85; Tm=Pm/omega_s;

set_param(mdl,'Solver','ode15s','StopTime','3','RelTol','1e-3','MaxStep','0.001');

% Refs
add_block('nesl_utility/Solver Configuration',[mdl '/Solver'],'Position',[50,20,140,60]);
add_block('ee_lib/Connectors & References/Electrical Reference',[mdl '/GND'],'Position',[200,20,240,60]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference',[mdl '/MR'],'Position',[320,20,360,60]);
add_line(mdl,'Solver/RConn1','GND/LConn1');

% Generator - set MINIMAL internal J and D (external ones will do the work)
add_block('ee_lib/Electromechanical/Simplified Generator',[mdl '/G'],'Position',[400,150,500,300]);
set_param([mdl '/G'],'RatedPower',num2str(Pm),'FRated','60','VinternalRMS',num2str(Vint));
set_param([mdl '/G'],'RotorInertia',num2str(J),'RotorDamping','50','Fdroop','0.05');

% Torque Source on shaft (LConn1)
add_block('fl_lib/Physical Signals/Sources/PS Constant',[mdl '/PmVal'],'Position',[200,200,250,230]);
set_param([mdl '/PmVal'],'constant',num2str(Tm,'%.6g'));
add_block('fl_lib/Mechanical/Mechanical Sources/Ideal Torque Source',[mdl '/TS'],'Position',[280,190,340,240]);
add_line(mdl,'PmVal/RConn1','TS/RConn1');    % signal
add_line(mdl,'TS/RConn2','G/LConn1');         % TS_R → shaft C
add_line(mdl,'TS/LConn1','MR/LConn1');        % TS_C → ref
add_line(mdl,'G/LConn2','MR/LConn1');         % Gen ref → MR
add_line(mdl,'G/RConn2','GND/LConn1');        % neutral

% Matched load
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',[mdl '/Load'],'Position',[550,180,630,260]);
set_param([mdl '/Load'],'VRated',num2str(Vbase),'FRated','60','P',num2str(Pm));
set_param([mdl '/Load'],'component_structure','ee.enum.rlc.structure.R');
add_line(mdl,'G/RConn1','Load/LConn1');

% DISTURBANCE: +10% load at t=1s
add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',[mdl '/DLoad'],'Position',[650,300,730,380]);
set_param([mdl '/DLoad'],'VRated',num2str(Vbase),'FRated','60','P',num2str(Pm*0.1));
set_param([mdl '/DLoad'],'component_structure','ee.enum.rlc.structure.R');

add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)',[mdl '/SW'],'Position',[550,310,610,380]);
add_block('nesl_utility/Simulink-PS Converter',[mdl '/S2P'],'Position',[490,320,520,350]);
add_block('simulink/Sources/Step',[mdl '/Step'],'Position',[430,325,470,345]);
set_param([mdl '/Step'],'Time','1','Before','0','After','1');
add_line(mdl,'Step/1','S2P/1');
add_line(mdl,'S2P/RConn1','SW/LConn1');
add_line(mdl,'G/RConn1','SW/LConn2');
add_line(mdl,'SW/RConn1','DLoad/LConn1');

try set_param(mdl,'SimscapeLogType','all','SimscapeLogName','simlog');catch;end
save_system(mdl);

% Run
fprintf('Simulating with TorqueSource + Disturbance...\n');
tic;
try
    out = sim(mdl);
    fprintf('Done in %.1fs\n', toc);

    simlog = out.simlog;

    % Check omegaDel
    try
        v = simlog.G.omegaDel.series.values;
        t = simlog.G.omegaDel.series.time;
        fprintf('G.omegaDel: [%.6f, %.6f] pu\n', min(v), max(v));
        fprintf('Δf: [%.4f, %.4f] Hz\n', min(v)*60, max(v)*60);
    catch e
        fprintf('No G.omegaDel: %s\n', e.message);
    end

    % List ALL simlog fields for the generator
    try
        glog = simlog.G;
        fn = fieldnames(glog);
        fprintf('\nAll G simlog fields:\n');
        for k = 1:length(fn)
            try
                s = glog.(fn{k}).series;
                fprintf('  G.%-15s: [%.6f, %.6f]\n', fn{k}, min(s.values), max(s.values));
            catch; end
        end
    catch; end

catch e
    fprintf('FAILED (%.1fs): %s\n', toc, e.message);
end
close_system(mdl,0);
