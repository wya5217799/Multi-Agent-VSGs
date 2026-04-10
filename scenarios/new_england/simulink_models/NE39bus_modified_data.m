%% Modified New England 39-Bus System Parameters
% Based on IEEE 39-bus + paper Section IV-G modifications
% G1-G8 replaced with PMSG wind farms, G9/G10 retained as sync machines
% 8 ESS units with VSG control added at Bus 40-47
%
% System base: 100 MVA, 60 Hz (IEEE 39-bus original frequency)

clear; clc;

%% ========== System Constants ==========
Sbase = 100;        % MVA
fn    = 60;         % Hz (IEEE 39-bus original frequency)
omega_n = 2*pi*fn;  % rad/s

%% ========== Line Data (from original IEEE 39-bus) ==========
% Format: [From To R(pu) X(pu) B(pu) TapRatio baseMVA Vn(kV)]
line=[...
    1   2   0.0035  0.0411  0.6987  0   100 345
    1   39  0.001   0.025   0.75    0   100 345
    2   3   0.0013  0.0151  0.2572  0   100 345
    2   25  0.007   0.0086  0.146   0   100 345
    2   30  0       0.0181  0       1.025 100 22
    3   4   0.0013  0.0213  0.2214  0   100 345
    3   18  0.0011  0.0133  0.2138  0   100 345
    4   5   0.0008  0.0128  0.1342  0   100 345
    4   14  0.0008  0.0129  0.1382  0   100 345
    5   8   0.0008  0.0112  0.1476  0   100 345
    6   5   0.0002  0.0026  0.0434  0   100 345
    6   7   0.0006  0.0092  0.113   0   100 345
    6   11  0.0007  0.0082  0.1389  0   100 345
    7   8   0.0004  0.0046  0.078   0   100 345
    8   9   0.0023  0.0363  0.3804  0   100 345
    9   39  0.001   0.025   1.2     0   100 345
    10  11  0.0004  0.0043  0.0729  0   100 345
    10  13  0.0004  0.0043  0.0729  0   100 345
    10  32  0       0.02    0       1.07  100 22
    12  11  0.0016  0.0435  0       1.006 100 345
    12  13  0.0016  0.0435  0       1.006 100 345
    13  14  0.0009  0.0101  0.1723  0   100 345
    14  15  0.0018  0.0217  0.366   0   100 345
    15  16  0.0009  0.0094  0.171   0   100 345
    16  17  0.0007  0.0089  0.1342  0   100 345
    16  19  0.0016  0.0195  0.304   0   100 345
    16  21  0.0008  0.0135  0.2548  0   100 345
    16  24  0.0003  0.0059  0.068   0   100 345
    17  18  0.0007  0.0082  0.1319  0   100 345
    17  27  0.0013  0.0173  0.3216  0   100 345
    19  33  0.0007  0.0142  0       1.07  100 22
    19  20  0.0007  0.0138  0       1.06  100 345
    20  34  0.0009  0.018   0       1.009 100 22
    21  22  0.0008  0.014   0.2565  0   100 345
    22  23  0.0006  0.0096  0.1846  0   100 345
    22  35  0       0.0143  0       1.025 100 22
    23  24  0.0022  0.035   0.361   0   100 345
    23  36  0.0005  0.0272  0       1     100 22
    25  26  0.0032  0.0323  0.513   0   100 345
    25  37  0.0006  0.0232  0       1.025 100 22
    26  27  0.0014  0.0147  0.2396  0   100 345
    26  28  0.0043  0.0474  0.7802  0   100 345
    26  29  0.0057  0.0625  1.029   0   100 345
    28  29  0.0014  0.0151  0.249   0   100 345
    29  38  0.0008  0.0156  0       1.025 100 22
    31  6   0       0.025   0       1     100 22];

%% ========== Retained Synchronous Machines: G9 (Bus 38) and G10 (Bus 39) ==========
% Format: [No Bus Sn xl ra xd xd' xd'' Td0' Td0'' xq xq' xq'' Tq0' Tq0'' H D d1 Bus]
mac_con_retained = [
    9  38  1000.0 0.298 0.0030  2.106 0.570 0.01  4.790 0.003 2.050 0.587 0.03  1.960 0.005 3.450 0.000 0.00 38
   10  39  1000.0 0.030 0.0010  0.200 0.060 0.01  7.000 0.003 0.190 0.080 0.03  0.700 0.005 50.00 0.000 0.00 39];

%% ========== PMSG Wind Farms W1-W8 (replacing G1-G8) ==========
% Modeled as GENROU with near-zero inertia (M=0.1s) and no damping
% Governor R=999 effectively disables governor response
n_wind = 8;
WIND_FARM_M   = 0.1;   % s (near-zero inertia, M = 2H -> H = 0.05s)
WIND_FARM_D   = 0.0;   % p.u. (no damping)
WIND_FARM_GOV_R = 999.0; % effectively disabled

% Wind farm bus mapping (original generator buses)
wind_bus = [30, 31, 32, 33, 34, 35, 36, 37]; % Bus 30-37
% Original generation dispatch (p.u. on 1000 MVA base)
wind_p0 = [250, 520.81, 650, 632, 508, 650, 560, 540]' ./ 1000;

% GENROU parameters for wind farms (same structure, near-zero inertia)
mac_con_wind = [
    1  30  1000.0 0.125 0.0    1.000 0.310 0.01  10.20 0.003 0.690 0.08  0.03  1.500 0.005  0.050 0.000 0.00 30
    2  31  1000.0 0.350 0.0    2.950 0.697 0.01   6.56 0.003 2.820 1.7   0.03  1.500 0.005  0.050 0.000 0.00 31
    3  32  1000.0 0.304 0.0    2.495 0.531 0.01   5.70 0.003 2.370 0.876 0.03  1.500 0.005  0.050 0.000 0.00 32
    4  33  1000.0 0.295 0.0    2.620 0.436 0.01   5.69 0.003 2.580 1.66  0.03  1.500 0.005  0.050 0.000 0.00 33
    5  34  1000.0 0.540 0.0    6.700 1.320 0.01   5.40 0.003 6.200 1.66  0.03  0.440 0.005  0.050 0.000 0.00 34
    6  35  1000.0 0.224 0.0    2.540 0.500 0.01   7.30 0.003 2.410 0.814 0.03  0.400 0.005  0.050 0.000 0.00 35
    7  36  1000.0 0.322 0.0    2.950 0.490 0.01   5.66 0.003 2.920 1.86  0.03  1.500 0.005  0.050 0.000 0.00 36
    8  37  1000.0 0.280 0.0    2.900 0.570 0.01   6.70 0.003 2.800 0.911 0.03  0.410 0.005  0.050 0.000 0.00 37];
% H column (16) = M/2 = 0.05 for all wind farms

%% ========== ESS with VSG Control (ES1-ES8) ==========
n_ess = 8;

% VSG base parameters (GENCLS equivalent)
VSG_M0  = 12.0;    % s (M = 2H, so H0 = 6.0 s)
VSG_D0  = 3.0;     % p.u.
VSG_SN  = 200.0;   % MVA per unit
VSG_RA  = 0.001;   % p.u. armature resistance
VSG_XD1 = 0.15;    % p.u. transient reactance

% VSG action space (RL agent outputs)
DM_MIN = -6.0;     % s
DM_MAX = 18.0;     % s  -> M range [6.0, 30.0]
DD_MIN = -1.5;     % p.u.
DD_MAX = 4.5;      % p.u. -> D range [1.5, 7.5]

% PV interface parameters (initial operating point)
VSG_P0   = 0.5;    % p.u. initial active power
VSG_Q0   = 0.0;    % p.u. initial reactive power
VSG_PMAX = 5.0;    % p.u.
VSG_PMIN = 0.0;    % p.u.
VSG_QMAX = 5.0;    % p.u.
VSG_QMIN = -5.0;   % p.u.
VSG_V0   = 1.0;    % p.u. voltage setpoint

% ESS bus topology: new buses 40-47, connected to original gen buses 30-37
ess_new_bus   = 40:47;              % New bus numbers for ESS
ess_parent_bus = [30 31 32 33 34 35 36 37]; % Connected to original gen buses
VSG_BUS_VN = 22.0;                  % kV

% Connecting line parameters (short lines)
NEW_LINE_R = 0.001;    % p.u.
NEW_LINE_X = 0.10;     % p.u. (tunable via --x-line)
NEW_LINE_B = 0.0175;   % p.u.

% ESS connecting lines: [From To R X B Tap baseMVA Vn]
line_ess = zeros(n_ess, 8);
for i = 1:n_ess
    line_ess(i,:) = [ess_parent_bus(i), ess_new_bus(i), ...
                     NEW_LINE_R, NEW_LINE_X, NEW_LINE_B, 0, Sbase, VSG_BUS_VN];
end

%% ========== Communication Topology (8-node ring) ==========
% Each ES has exactly 2 neighbors (m=2)
% ES1<->ES2<->ES3<->ES4<->ES5<->ES6<->ES7<->ES8<->ES1
COMM_ADJ = {
    [2, 8],   % ES1 neighbors
    [1, 3],   % ES2
    [2, 4],   % ES3
    [3, 5],   % ES4
    [4, 6],   % ES5
    [5, 7],   % ES6
    [6, 8],   % ES7
    [7, 1],   % ES8
};
MAX_NEIGHBORS = 2;
COMM_FAIL_PROB = 0.1;   % per link per episode during training

%% ========== Simulation Parameters ==========
DT          = 0.2;      % s, control step
T_EPISODE   = 10.0;     % s, episode duration
STEPS_PER_EPISODE = T_EPISODE / DT;  % 50 steps
N_SUBSTEPS  = 5;        % parameter interpolation substeps
T_WARMUP    = 0.5;      % s, warmup before disturbance

%% ========== Reward Function Weights ==========
PHI_F = 200.0;  % frequency synchronization weight
PHI_H = 1.0;    % inertia control weight
PHI_D = 1.0;    % damping control weight
TDS_FAIL_PENALTY = -50.0;

%% ========== Disturbance Parameters ==========
DIST_MIN = 1.0;    % p.u. minimum disturbance magnitude
DIST_MAX = 3.0;    % p.u. maximum disturbance magnitude

%% ========== Observation Space ==========
OBS_DIM = 7;
% [0] local P_es / 2.0
% [1] local freq deviation: (omega - 1.0) * omega_n / 3.0
% [2] local RoCoF: d_omega * omega_n / 5.0
% [3] neighbor1 freq deviation (same norm)
% [4] neighbor2 freq deviation (same norm)
% [5] neighbor1 RoCoF (same norm)
% [6] neighbor2 RoCoF (same norm)

%% ========== RL Hyperparameters ==========
RL_LR          = 3e-4;
RL_GAMMA       = 0.99;
RL_TAU_SOFT    = 0.005;
RL_BUFFER_SIZE = 2500;
RL_BATCH_SIZE  = 32;
RL_WARMUP      = 500;
RL_HIDDEN      = [128, 128, 128, 128];

%% ========== AVR for Retained Machines ==========
AVR_Data_retained = [
    0.01  200  0.015  10  1  1.03  -5  5    % G9
    0.01  200  0.015  10  1  1.03  -5  5];  % G10

%% ========== PSS for Retained Machines ==========
MB = [1  0.2  30  1.25  40  12  160];

%% ========== Bus Data (extended with ESS buses) ==========
Bus = [
     1  345;  2  345;  3  345;  4  345;  5  345;
     6  345;  7  345;  8  345;  9  345; 10  345;
    11  345; 12  230; 13  345; 14  345; 15  345;
    16  345; 17  345; 18  345; 19  345; 20  345;
    21  345; 22  345; 23  345; 24  345; 25  345;
    26  345; 27  345; 28  345; 29  345; 30   22;
    31   22; 32   22; 33   22; 34   22; 35   22;
    36   22; 37   22; 38   22; 39  345;
    40   22; 41   22; 42   22; 43   22;     % ESS buses
    44   22; 45   22; 46   22; 47   22];

%% ========== Combine all lines ==========
line_all = [line; line_ess];

%% ========== PQ Load Mode ==========
PQ_P2P = 1.0;  % constant power
PQ_P2Z = 0.0;  % no constant impedance
PQ_Q2Q = 1.0;
PQ_Q2Z = 0.0;

fprintf('Modified NE 39-bus system data loaded successfully.\n');
fprintf('  Retained sync machines: G9 (Bus 38), G10 (Bus 39)\n');
fprintf('  PMSG wind farms: W1-W8 at Bus 30-37\n');
fprintf('  ESS with VSG: ES1-ES8 at Bus 40-47\n');
fprintf('  Communication: 8-node ring, m=2\n');
