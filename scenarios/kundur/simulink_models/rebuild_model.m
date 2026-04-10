%% rebuild_model.m
% Rebuilds kundur_two_area from scratch with CORRECT mechanical wiring.
% All machines use Simplified Generator + Ideal Torque Source prime mover.
%
% Verified port maps (R2025b):
%   Simplified Generator: LConn1=MechC, LConn2=MechR, RConn1=3ph, RConn2=neutral
%   Ideal Torque Source:  LConn1=MechC, RConn1=PhysSigS, RConn2=MechR
%   PS Constant:          RConn1=PhysSig output
%   Transmission Line:    LConn1=3ph_send, LConn2=gnd_send, RConn1=3ph_recv, RConn2=gnd_recv

mdl = 'kundur_two_area';
cd(fileparts(mfilename('fullpath')));

Vbase = 230e3; fn = 60; omega_s = 2*pi*fn;
Sn_gen = 900e6; Sn_w2 = 100e6; Sn_vsg = 200e6;
Vint = Vbase / sqrt(3);
R_line = 0.053; L_line = 1.41; C_line = 0.009;
R_vsg = 0.01;   L_vsg = 0.5;

if bdIsLoaded(mdl), close_system(mdl, 0); end
slxFile = fullfile(pwd, [mdl '.slx']);
if exist(slxFile, 'file'), delete(slxFile); end
new_system(mdl); open_system(mdl);
load_system('ee_lib'); load_system('nesl_utility'); load_system('fl_lib'); load_system('simulink');
% ode15s handles stiff multi-machine networks better than ode23t
set_param(mdl, 'Solver','ode15s', 'StopTime','10', 'RelTol','1e-3', 'MaxStep','0.001');

fprintf('Building %s...\n', mdl);

%% [1] References
fprintf('  [1/8] References\n');
add_block('nesl_utility/Solver Configuration', [mdl '/Solver'], 'Position',[100,30,190,70]);
add_block('ee_lib/Connectors & References/Electrical Reference', [mdl '/GND'], 'Position',[280,30,320,70]);
add_block('fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference', [mdl '/MechRef'], 'Position',[400,30,440,70]);
add_line(mdl, 'Solver/RConn1', 'GND/LConn1');

%% [2] Generators
fprintf('  [2/8] Generators\n');
H12=6.5; H3=6.175;
J12=2*H12*Sn_gen/omega_s^2; J3=2*H3*Sn_gen/omega_s^2;
Jw1=2*0.5*Sn_gen/omega_s^2;  Jw2=2*0.5*Sn_w2/omega_s^2;

add_simpgen(mdl,'G1', [250,200,350,330], Sn_gen*0.85,Vint,J12,50,0.05);
add_simpgen(mdl,'G2', [250,450,350,580], Sn_gen*0.78,Vint,J12,50,0.05);
add_simpgen(mdl,'G3', [2350,200,2450,330],Sn_gen*0.78,Vint,J3,50,0.05);
add_simpgen(mdl,'W1', [2350,450,2450,580],Sn_gen*0.78,Vint,Jw1,5,0.001);
add_simpgen(mdl,'W2', [1400,850,1500,980],Sn_w2*0.9,Vint,Jw2,2,0.001);

%% [3] VSGs
fprintf('  [3/8] VSGs\n');
M0=12; D0=3;
Jvsg=M0*Sn_vsg/omega_s^2; Dvsg=D0*Sn_vsg/omega_s^2;
add_simpgen(mdl,'ES1',[950,850,1050,980], Sn_vsg*0.5,Vint,Jvsg,Dvsg,0.05);
add_simpgen(mdl,'ES2',[1600,850,1700,980],Sn_vsg*0.5,Vint,Jvsg,Dvsg,0.05);
add_simpgen(mdl,'ES3',[2100,850,2200,980],Sn_vsg*0.5,Vint,Jvsg,Dvsg,0.05);
add_simpgen(mdl,'ES4',[1850,850,1950,980],Sn_vsg*0.5,Vint,Jvsg,Dvsg,0.05);

%% [4] Transmission Lines
fprintf('  [4/8] Lines\n');
add_tl(mdl,'L_1_5', [450,240,570,290],5);   add_tl(mdl,'L_2_6', [450,490,570,540],5);
add_tl(mdl,'L_3_10',[2130,240,2250,290],5);  add_tl(mdl,'L_4_9', [2130,490,2250,540],5);
add_tl(mdl,'L_5_6a',[650,350,770,400],25);   add_tl(mdl,'L_5_6b',[650,430,770,480],25);
add_tl(mdl,'L_6_7a',[850,350,970,400],10);   add_tl(mdl,'L_6_7b',[850,430,970,480],10);
add_tl(mdl,'L_7_8a',[1100,330,1220,380],110);add_tl(mdl,'L_7_8b',[1100,410,1220,460],110);
add_tl(mdl,'L_7_8c',[1100,490,1220,540],110);
add_tl(mdl,'L_8_9a',[1350,350,1470,400],10); add_tl(mdl,'L_8_9b',[1350,430,1470,480],10);
add_tl(mdl,'L_9_10a',[1550,350,1670,400],25);add_tl(mdl,'L_9_10b',[1550,430,1670,480],25);
add_tlv(mdl,'L_7_12', [950,680,1070,730],1); add_tlv(mdl,'L_8_16', [1600,680,1720,730],1);
add_tlv(mdl,'L_10_14',[2100,680,2220,730],1);add_tlv(mdl,'L_9_15', [1850,680,1970,730],1);
add_tlv(mdl,'L_8_W2', [1400,680,1520,730],1);

%% [5] Loads
fprintf('  [5/8] Loads\n');
add_ld(mdl,'Load7', [1000,570,1080,650],967e6,100e6);
add_ld(mdl,'Load9', [1800,570,1880,650],1767e6,100e6);
add_ld(mdl,'Shunt7',[1100,570,1180,650],1000,-200e6);
add_ld(mdl,'Shunt9',[1900,570,1980,650],1000,-350e6);

%% [6] Network Wiring
fprintf('  [6/8] Wiring\n');
% Gen → lines
add_line(mdl,'G1/RConn1','L_1_5/LConn1');  add_line(mdl,'G2/RConn1','L_2_6/LConn1');
add_line(mdl,'G3/RConn1','L_3_10/LConn1'); add_line(mdl,'W1/RConn1','L_4_9/LConn1');
% VSG → lines
add_line(mdl,'ES1/RConn1','L_7_12/RConn1');  add_line(mdl,'ES2/RConn1','L_8_16/RConn1');
add_line(mdl,'ES3/RConn1','L_10_14/RConn1'); add_line(mdl,'ES4/RConn1','L_9_15/RConn1');
add_line(mdl,'W2/RConn1','L_8_W2/LConn1');
% Bus5
add_line(mdl,'L_1_5/RConn1','L_5_6a/LConn1'); add_line(mdl,'L_1_5/RConn1','L_5_6b/LConn1');
% Bus6
add_line(mdl,'L_5_6a/RConn1','L_6_7a/LConn1'); add_line(mdl,'L_5_6a/RConn1','L_6_7b/LConn1');
add_line(mdl,'L_5_6b/RConn1','L_5_6a/RConn1'); add_line(mdl,'L_2_6/RConn1','L_5_6a/RConn1');
% Bus7
add_line(mdl,'L_6_7a/RConn1','L_7_8a/LConn1'); add_line(mdl,'L_6_7a/RConn1','L_7_8b/LConn1');
add_line(mdl,'L_6_7a/RConn1','L_7_8c/LConn1'); add_line(mdl,'L_6_7a/RConn1','Load7/LConn1');
add_line(mdl,'L_6_7a/RConn1','Shunt7/LConn1'); add_line(mdl,'L_6_7a/RConn1','L_7_12/LConn1');
add_line(mdl,'L_6_7b/RConn1','L_6_7a/RConn1');
% Bus8
add_line(mdl,'L_7_8a/RConn1','L_8_9a/LConn1'); add_line(mdl,'L_7_8a/RConn1','L_8_9b/LConn1');
add_line(mdl,'L_7_8a/RConn1','L_8_16/LConn1'); add_line(mdl,'L_7_8a/RConn1','L_8_W2/RConn1');
add_line(mdl,'L_7_8b/RConn1','L_7_8a/RConn1'); add_line(mdl,'L_7_8c/RConn1','L_7_8a/RConn1');
% Bus9
add_line(mdl,'L_8_9a/RConn1','L_9_10a/LConn1');add_line(mdl,'L_8_9a/RConn1','L_9_10b/LConn1');
add_line(mdl,'L_8_9a/RConn1','Load9/LConn1');   add_line(mdl,'L_8_9a/RConn1','Shunt9/LConn1');
add_line(mdl,'L_8_9a/RConn1','L_9_15/LConn1');
add_line(mdl,'L_8_9b/RConn1','L_8_9a/RConn1');  add_line(mdl,'L_4_9/RConn1','L_8_9a/RConn1');
% Bus10
add_line(mdl,'L_9_10a/RConn1','L_10_14/LConn1');
add_line(mdl,'L_9_10b/RConn1','L_9_10a/RConn1');add_line(mdl,'L_3_10/RConn1','L_9_10a/RConn1');

%% [7] Ground for lines
fprintf('  [7/8] Ground\n');
tls={'L_1_5','L_2_6','L_3_10','L_4_9','L_5_6a','L_5_6b','L_6_7a','L_6_7b',...
     'L_7_8a','L_7_8b','L_7_8c','L_8_9a','L_8_9b','L_9_10a','L_9_10b',...
     'L_7_12','L_8_16','L_10_14','L_9_15','L_8_W2'};
for i=1:length(tls)
    try add_line(mdl,[tls{i} '/LConn2'],'GND/LConn1'); catch;end
    try add_line(mdl,[tls{i} '/RConn2'],'GND/LConn1'); catch;end
end

%% [8] Disturbance switches
fprintf('  [8/8] Switches\n');
% SW14 (Bus14, trip load -248MW at t=1)
add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)',[mdl '/SW14'],'Position',[2050,1100,2110,1180]);
add_ld(mdl,'DLoad14',[2150,1100,2230,1180],248e6,0);
add_block('nesl_utility/Simulink-PS Converter',[mdl '/S2PS_14'],'Position',[1980,1090,2010,1120]);
add_block('simulink/Sources/Step',[mdl '/Trip14'],'Position',[1920,1095,1960,1115]);
set_param([mdl '/Trip14'],'Time','1','Before','1','After','0');
add_line(mdl,'Trip14/1','S2PS_14/1'); add_line(mdl,'S2PS_14/RConn1','SW14/LConn1');
add_line(mdl,'L_10_14/RConn1','SW14/LConn2'); add_line(mdl,'SW14/RConn1','DLoad14/LConn1');

% SW15 (Bus15, add load +188MW at t)
add_block('ee_lib/Switches & Breakers/SPST Switch (Three-Phase)',[mdl '/SW15'],'Position',[1800,1100,1860,1180]);
add_ld(mdl,'DLoad15',[1900,1100,1980,1180],188e6,0);
add_block('nesl_utility/Simulink-PS Converter',[mdl '/S2PS_15'],'Position',[1730,1090,1760,1120]);
add_block('simulink/Sources/Step',[mdl '/Trip15'],'Position',[1670,1095,1710,1115]);
set_param([mdl '/Trip15'],'Time','100','Before','0','After','1');
add_line(mdl,'Trip15/1','S2PS_15/1'); add_line(mdl,'S2PS_15/RConn1','SW15/LConn1');
add_line(mdl,'L_9_15/RConn1','SW15/LConn2'); add_line(mdl,'SW15/RConn1','DLoad15/LConn1');

%% Save
try set_param(mdl,'SimscapeLogType','all','SimscapeLogName','simlog'); catch;end
save_system(mdl);
fprintf('\n=== Model built! ===\n');

%% ============= Simulate =============
fprintf('\nSimulating (StopTime=5, Trip14@t=1)...\n');
set_param([mdl '/Trip14'],'Time','1');
set_param([mdl '/Trip15'],'Time','100');
set_param(mdl,'StopTime','5');
tic; out = sim(mdl); fprintf('Done in %.1fs\n',toc);

simlog = out.simlog;
machines = {'G1','G2','G3','W1','W2','ES1','ES2','ES3','ES4'};
fprintf('\n=== Frequency Response ===\n');
for i=1:length(machines)
    g=machines{i};
    try
        v = simlog.(g).omegaDel.series.values;
        fprintf('  %s: Δf = [%.4f, %.4f] Hz\n',g,min(v)*60,max(v)*60);
    catch
        fprintf('  %s: no omegaDel data\n',g);
    end
end

%% ============= Local Functions =============
function add_simpgen(mdl, name, pos, Prated, Vrms, J, D, fdroop)
    % Simplified Generator has BUILT-IN swing equation (J, D, Fdroop).
    % NO external torque source needed. Just free the shaft port.
    blk = [mdl '/' name];
    add_block('ee_lib/Electromechanical/Simplified Generator', blk, 'Position', pos);
    set_param(blk,'RatedPower',num2str(Prated),'FRated','60','VinternalRMS',num2str(Vrms));
    set_param(blk,'RotorInertia',num2str(J),'RotorDamping',num2str(D),'Fdroop',num2str(fdroop));
    % LConn1 (shaft C) → Rotational Free End (free to rotate, no external torque)
    feName = ['Free_' name];
    px = pos(1)-60; py = mean(pos([2,4]));
    add_block('fl_lib/Mechanical/Rotational Elements/Rotational Free End', ...
        [mdl '/' feName], 'Position', [px, py-10, px+30, py+10]);
    add_line(mdl, [feName '/LConn1'], [name '/LConn1']);  % free end → shaft C
    % LConn2 (ref R) → MechRef
    add_line(mdl, [name '/LConn2'], 'MechRef/LConn1');
    % RConn2 (neutral) → GND
    add_line(mdl, [name '/RConn2'], 'GND/LConn1');
end

function add_tl(mdl, name, pos, len_km)
    blk=[mdl '/' name];
    add_block('ee_lib/Passive/Lines/Transmission Line (Three-Phase)',blk,'Position',pos);
    set_param(blk,'length',num2str(len_km),'R','0.053','L','1.41','Cl','0.009','freq','60');
end

function add_tlv(mdl, name, pos, len_km)
    blk=[mdl '/' name];
    add_block('ee_lib/Passive/Lines/Transmission Line (Three-Phase)',blk,'Position',pos);
    set_param(blk,'length',num2str(len_km),'R','0.01','L','0.5','Cl','0.009','freq','60');
end

function add_ld(mdl, name, pos, P, Q)
    blk=[mdl '/' name];
    add_block('ee_lib/Passive/RLC Assemblies/Wye-Connected Load',blk,'Position',pos);
    set_param(blk,'VRated','230e3','FRated','60','P',num2str(P));
    if Q>=0
        set_param(blk,'component_structure','ee.enum.rlc.structure.RL');
        set_param(blk,'Qpos',num2str(max(Q,1)));
    else
        set_param(blk,'component_structure','ee.enum.rlc.structure.RC');
        set_param(blk,'Qneg',num2str(Q));
    end
end
