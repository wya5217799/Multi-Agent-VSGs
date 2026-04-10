%% layout_model.m
% Rearranges the kundur_two_area Simulink model blocks into a clean,
% organized layout following the standard Kundur Two-Area single-line
% diagram: Area 1 (left) → Tie (center) → Area 2 (right).
%
% Run AFTER build_kundur_simulink.m and add_disturbance_and_interface.m.
% This script only changes block POSITIONS — no electrical changes.
%
% Layout:
%
%   G1    G2                                              G3    W1
%   |     |                                               |     |
%  Bus1  Bus2                                           Bus3  Bus4
%    \   /                                                \   /
%    Bus5             TIE LINES                          Bus10
%     |          =====================                     |
%    Bus6        L_7_8a  L_7_8b  L_7_8c                  Bus9
%     |          =====================                   / |  \
%    Bus7 ------==========-----------  Bus8 --------  Bus9 area
%    / | \                              / | \
% Load7 Sh7 ES1                     W2 ES2           Load9 Sh9 ES4  ES3
%                                                     SW14/15 + DLoads

mdl = 'kundur_two_area';
cd(fileparts(mfilename('fullpath')));

if ~bdIsLoaded(mdl)
    load_system(mdl);
end
open_system(mdl);

fprintf('Rearranging model layout...\n');

%% ========== Layout Constants ==========
% Block sizes (width x height)
GEN_W = 100; GEN_H = 130;   % Generators & VSGs
TL_W  = 130; TL_H  = 50;    % Transmission lines
LD_W  = 80;  LD_H  = 80;    % Loads / shunts
SW_W  = 60;  SW_H  = 80;    % Switches
STP_W = 40;  STP_H = 25;    % Step blocks
S2P_W = 40;  S2P_H = 35;    % Simulink-PS converters
SOL_W = 90;  SOL_H = 40;    % Solver
REF_W = 40;  REF_H = 40;    % References

% Column centers (x) — follows the bus topology left to right
%   Area 1 Gens | Area 1 Lines | Bus7 | Tie | Bus8 | Area 2 Lines | Area 2 Gens
COL = struct();
COL.G1    = 120;    % Generator G1
COL.G2    = 340;    % Generator G2
COL.SU1   = 500;    % Step-up area 1 (L_1_5, L_2_6 right end merges here)
COL.IA1a  = 680;    % Intra-area 1 first stage (L_5_6)
COL.IA1b  = 880;    % Intra-area 1 second stage (L_6_7)
COL.B7    = 1080;   % Bus 7 area (loads, shunt, ES1)
COL.TIE   = 1320;   % Tie lines (L_7_8)
COL.B8    = 1560;   % Bus 8 area (W2, ES2)
COL.IA2a  = 1760;   % Intra-area 2 first stage (L_8_9)
COL.IA2b  = 1960;   % Intra-area 2 second stage (L_9_10)
COL.SU2   = 2140;   % Step-up area 2
COL.G3    = 2300;   % Generator G3
COL.W1    = 2520;   % Wind farm W1
COL.B9    = 1960;   % Bus 9 area (reuse IA2b column for loads below)
COL.B10   = 2140;   % Bus 10 area

% Row centers (y)
ROW = struct();
ROW.infra   = 50;    % Solver, references
ROW.gen     = 230;   % Generators
ROW.stepup  = 430;   % Step-up lines
ROW.spine   = 580;   % Main transmission backbone (parallel lines, row a)
ROW.spineb  = 660;   % Parallel line row b
ROW.spinec  = 740;   % Parallel line row c (tie only)
ROW.load    = 880;   % Loads and shunts
ROW.vsgline = 1020;  % VSG connection lines
ROW.vsg     = 1160;  % VSG blocks
ROW.sw      = 1350;  % Switches
ROW.dload   = 1350;  % Disturbance loads (same row, offset right)
ROW.trip    = 1250;  % Trip step blocks

%% ========== Helper: position block centered at (cx, cy) ==========
function pos_block(blk, cx, cy, w, h)
    fullPath = blk;
    if ischar(fullPath)
        try
            set_param(fullPath, 'Position', ...
                [round(cx-w/2), round(cy-h/2), round(cx+w/2), round(cy+h/2)]);
        catch e
            warning('Could not position %s: %s', fullPath, e.message);
        end
    end
end

p = @(name, cx, cy, w, h) pos_block([mdl '/' name], cx, cy, w, h);

%% ========== 1. Infrastructure ==========
fprintf('  Positioning infrastructure...\n');
p('Solver',  120, ROW.infra, SOL_W, SOL_H);
p('GND',     300, ROW.infra, REF_W, REF_H);
p('MechRef', 420, ROW.infra, REF_W, REF_H);

%% ========== 2. Area 1 Generators ==========
fprintf('  Positioning Area 1 generators...\n');
p('G1', COL.G1, ROW.gen, GEN_W, GEN_H);
p('G2', COL.G2, ROW.gen, GEN_W, GEN_H);

%% ========== 3. Area 1 Step-up Lines ==========
fprintf('  Positioning Area 1 step-up lines...\n');
% L_1_5: G1 → Bus5
p('L_1_5', (COL.G1 + COL.SU1)/2, ROW.stepup - 60, TL_W, TL_H);
% L_2_6: G2 → Bus6
p('L_2_6', (COL.G2 + COL.SU1)/2, ROW.stepup + 60, TL_W, TL_H);

%% ========== 4. Area 1 Intra-area Lines ==========
fprintf('  Positioning Area 1 intra-area lines...\n');
% L_5_6a, L_5_6b: Bus5 → Bus6 (parallel)
p('L_5_6a', COL.IA1a, ROW.spine,  TL_W, TL_H);
p('L_5_6b', COL.IA1a, ROW.spineb, TL_W, TL_H);
% L_6_7a, L_6_7b: Bus6 → Bus7 (parallel)
p('L_6_7a', COL.IA1b, ROW.spine,  TL_W, TL_H);
p('L_6_7b', COL.IA1b, ROW.spineb, TL_W, TL_H);

%% ========== 5. Tie Lines ==========
fprintf('  Positioning tie lines...\n');
% L_7_8a, L_7_8b, L_7_8c: Bus7 → Bus8 (3 parallel)
p('L_7_8a', COL.TIE, ROW.spine,  TL_W, TL_H);
p('L_7_8b', COL.TIE, ROW.spineb, TL_W, TL_H);
p('L_7_8c', COL.TIE, ROW.spinec, TL_W, TL_H);

%% ========== 6. Area 2 Intra-area Lines ==========
fprintf('  Positioning Area 2 intra-area lines...\n');
% L_8_9a, L_8_9b: Bus8 → Bus9 (parallel)
p('L_8_9a', COL.IA2a, ROW.spine,  TL_W, TL_H);
p('L_8_9b', COL.IA2a, ROW.spineb, TL_W, TL_H);
% L_9_10a, L_9_10b: Bus9 → Bus10 (parallel)
p('L_9_10a', COL.IA2b, ROW.spine,  TL_W, TL_H);
p('L_9_10b', COL.IA2b, ROW.spineb, TL_W, TL_H);

%% ========== 7. Area 2 Step-up Lines ==========
fprintf('  Positioning Area 2 step-up lines...\n');
p('L_3_10', (COL.SU2 + COL.G3)/2, ROW.stepup - 60, TL_W, TL_H);
p('L_4_9',  (COL.SU2 + COL.W1)/2, ROW.stepup + 60, TL_W, TL_H);

%% ========== 8. Area 2 Generators ==========
fprintf('  Positioning Area 2 generators...\n');
p('G3', COL.G3, ROW.gen, GEN_W, GEN_H);
p('W1', COL.W1, ROW.gen, GEN_W, GEN_H);

%% ========== 9. Bus 7 Area: Loads, Shunt, VSG ==========
fprintf('  Positioning Bus 7 area...\n');
p('Load7',  COL.B7 - 60, ROW.load, LD_W, LD_H);
p('Shunt7', COL.B7 + 60, ROW.load, LD_W, LD_H);
p('L_7_12', COL.B7, ROW.vsgline, TL_W, TL_H);
p('ES1',    COL.B7, ROW.vsg, GEN_W, GEN_H);

%% ========== 10. Bus 8 Area: W2, VSG ==========
fprintf('  Positioning Bus 8 area...\n');
p('L_8_W2', COL.B8 - 80, ROW.load, TL_W, TL_H);
p('W2',     COL.B8 - 80, ROW.load + 120, GEN_W, GEN_H);
p('L_8_16', COL.B8 + 80, ROW.vsgline, TL_W, TL_H);
p('ES2',    COL.B8 + 80, ROW.vsg, GEN_W, GEN_H);

%% ========== 11. Bus 9 Area: Loads, Shunt, ES4 ==========
fprintf('  Positioning Bus 9 area...\n');
p('Load9',  COL.B9 - 60, ROW.load, LD_W, LD_H);
p('Shunt9', COL.B9 + 60, ROW.load, LD_W, LD_H);
p('L_9_15', COL.B9, ROW.vsgline, TL_W, TL_H);
p('ES4',    COL.B9, ROW.vsg, GEN_W, GEN_H);

%% ========== 12. Bus 10 Area: ES3 ==========
fprintf('  Positioning Bus 10 area...\n');
p('L_10_14', COL.B10, ROW.vsgline, TL_W, TL_H);
p('ES3',     COL.B10, ROW.vsg, GEN_W, GEN_H);

%% ========== 13. Disturbance Switches (Bus14 via Bus10, Bus15 via Bus9) ==========
fprintf('  Positioning disturbance switches...\n');

% SW14 + DLoad14 (Bus14, connected to L_10_14)
try
    p('SW14',    COL.B10 - 40, ROW.sw, SW_W, SW_H);
    p('DLoad14', COL.B10 + 80, ROW.dload, LD_W, LD_H);
    p('S2PS_14', COL.B10 - 100, ROW.trip, S2P_W, S2P_H);
    p('Trip14',  COL.B10 - 160, ROW.trip, STP_W, STP_H);
catch; end

% SW15 + DLoad15 (Bus15, connected to L_9_15)
try
    p('SW15',    COL.B9 - 40, ROW.sw, SW_W, SW_H);
    p('DLoad15', COL.B9 + 80, ROW.dload, LD_W, LD_H);
    p('S2PS_15', COL.B9 - 100, ROW.trip, S2P_W, S2P_H);
    p('Trip15',  COL.B9 - 160, ROW.trip, STP_W, STP_H);
catch; end

%% ========== 14. Add Annotations (Text) ==========
fprintf('  Adding area annotations...\n');

% Remove old annotations if any
oldAnnot = find_system(mdl, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'annotation');
for k = 1:length(oldAnnot)
    try delete(oldAnnot(k)); catch; end
end

% Area labels
add_annotation(mdl, 'AREA 1',        [COL.IA1a-50,  ROW.infra-10]);
add_annotation(mdl, 'TIE',           [COL.TIE-20,   ROW.infra-10]);
add_annotation(mdl, 'AREA 2',        [COL.IA2a-50,  ROW.infra-10]);

% Bus labels along the backbone
add_annotation(mdl, 'Bus5',  [COL.SU1,      ROW.spine - 50]);
add_annotation(mdl, 'Bus6',  [COL.IA1a+70,  ROW.spine - 50]);
add_annotation(mdl, 'Bus7',  [COL.B7,       ROW.spine - 50]);
add_annotation(mdl, 'Bus8',  [COL.B8,       ROW.spine - 50]);
add_annotation(mdl, 'Bus9',  [COL.B9,       ROW.spine - 50]);
add_annotation(mdl, 'Bus10', [COL.B10,      ROW.spine - 50]);
add_annotation(mdl, 'Bus1',  [COL.G1,       ROW.stepup - 100]);
add_annotation(mdl, 'Bus2',  [COL.G2,       ROW.stepup + 20]);
add_annotation(mdl, 'Bus3',  [COL.G3,       ROW.stepup - 100]);
add_annotation(mdl, 'Bus4',  [COL.W1,       ROW.stepup + 20]);

% VSG labels
add_annotation(mdl, 'ES1 (Bus12)', [COL.B7,       ROW.vsg + 80]);
add_annotation(mdl, 'ES2 (Bus16)', [COL.B8+80,    ROW.vsg + 80]);
add_annotation(mdl, 'ES3 (Bus14)', [COL.B10,      ROW.vsg + 80]);
add_annotation(mdl, 'ES4 (Bus15)', [COL.B9,       ROW.vsg + 80]);

%% ========== 15. Final Cleanup ==========
fprintf('  Fitting to view...\n');

% Save
save_system(mdl);

% Zoom to fit
set_param(mdl, 'ZoomFactor', 'FitSystem');

fprintf('Layout complete! Model saved.\n');
fprintf('\nBlock arrangement:\n');
fprintf('  Top row:     G1, G2 (left)  |  G3, W1 (right)\n');
fprintf('  Middle row:  Transmission backbone (L → R)\n');
fprintf('  Bottom row:  Loads, VSGs, switches\n');
fprintf('\nOpen the model to see the result:\n');
fprintf('  open_system(''%s'')\n', mdl);

%% ========== Helper: add annotation ==========
function add_annotation(mdl, txt, pos)
    try
        h = Simulink.Annotation([mdl '/' txt]);
        h.Position = pos;
        h.FontSize = 12;
        h.FontWeight = 'bold';
    catch
        % Fallback for older MATLAB versions
        try
            add_block('built-in/Note', [mdl '/' txt '_label'], ...
                'Position', [pos(1), pos(2), pos(1)+80, pos(2)+20]);
        catch; end
    end
end
