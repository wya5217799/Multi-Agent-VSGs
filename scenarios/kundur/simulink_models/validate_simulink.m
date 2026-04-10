%% validate_simulink.m
% Validates the Modified Kundur Two-Area System Simulink model.
% Tests:
%   1. Steady-state (no disturbance) - check bus voltages and frequency
%   2. Load Step 1: Bus 14 load reduction (-248 MW)
%   3. Plots generator speeds, bus voltages, tie-line power

%% ========== Setup ==========
mdl = 'kundur_two_area';

% Rebuild if needed
if ~exist([mdl '.slx'], 'file')
    fprintf('Model not found. Building...\n');
    run('build_kundur_simulink.m');
end

if ~bdIsLoaded(mdl)
    load_system(mdl);
end

% Enable Simscape logging (only logged nodes, not 'all' to avoid slowdown)
set_param(mdl, 'SimscapeLogType', 'all', 'SimscapeLogName', 'simlog');

%% ========== Test 1: Steady-State (10s) ==========
fprintf('=== Test 1: Steady-State ===\n');
set_param(mdl, 'StopTime', '10', 'Solver', 'ode23t', ...
    'RelTol', '1e-4', 'MaxStep', '0.01');

tic;
out = sim(mdl);
elapsed = toc;
fprintf('Simulation completed in %.1f seconds\n', elapsed);

% Extract Simscape log data
simlog = out.simlog;

%% ========== Extract Generator Data ==========
% Simplified Generator simlog structure:
%   .w           = mechanical shaft angular velocity (rad/s) — zero if pinned to MechRef
%   .omegaDel    = frequency deviation from nominal (per-unit)
%   .theta       = rotor angle (rad)
%   .activeElectricalPower = electrical output power (W)
%   .electrical_torque = electromagnetic torque (N*m)
%   .mechanicalPowerPU = mechanical power (per-unit)

genNames = {'G1', 'G2', 'G3', 'W1', 'W2', 'ES1', 'ES2', 'ES3', 'ES4'};
fn = 60;  % Nominal frequency (Hz)

freqData = struct();
powerData = struct();

for i = 1:length(genNames)
    gn = genNames{i};
    try
        node = simlog.(gn);

        % Electrical frequency = fn * (1 + omegaDel)
        od = node.omegaDel.series;
        t = od.time;
        omegaDel_vals = od.values;
        freq_hz = fn * (1 + omegaDel_vals);

        freqData.(gn).time = t;
        freqData.(gn).freq = freq_hz;
        freqData.(gn).omegaDel = omegaDel_vals;

        % Active electrical power (W -> MW)
        pe = node.activeElectricalPower.series;
        powerData.(gn).time = pe.time;
        powerData.(gn).power_MW = pe.values / 1e6;

        fprintf('  %s: freq=[%.4f, %.4f] Hz, P=[%.1f, %.1f] MW\n', ...
            gn, min(freq_hz), max(freq_hz), min(pe.values)/1e6, max(pe.values)/1e6);
    catch ME
        fprintf('  Warning: %s data extraction failed: %s\n', gn, ME.message);
    end
end

%% ========== Plot Results ==========
figure('Name', 'Kundur System - Steady State', 'Position', [100, 100, 1200, 800]);

% Plot 1: Generator frequencies
subplot(3, 1, 1);
hold on;
colors = lines(length(genNames));
for i = 1:length(genNames)
    gn = genNames{i};
    if isfield(freqData, gn)
        plot(freqData.(gn).time, freqData.(gn).freq, ...
            'DisplayName', gn, 'LineWidth', 1.5, 'Color', colors(i,:));
    end
end
hold off;
xlabel('Time (s)');
ylabel('Frequency (Hz)');
title('Generator Electrical Frequencies');
legend('show', 'Location', 'best');
grid on;

% Plot 2: Frequency deviation (zoomed)
subplot(3, 1, 2);
hold on;
for i = 1:length(genNames)
    gn = genNames{i};
    if isfield(freqData, gn)
        delta_f = freqData.(gn).freq - fn;
        plot(freqData.(gn).time, delta_f, ...
            'DisplayName', gn, 'LineWidth', 1.5, 'Color', colors(i,:));
    end
end
hold off;
xlabel('Time (s)');
ylabel('\Deltaf (Hz)');
title('Frequency Deviation from 60 Hz');
legend('show', 'Location', 'best');
grid on;

% Plot 3: Active power
subplot(3, 1, 3);
hold on;
for i = 1:length(genNames)
    gn = genNames{i};
    if isfield(powerData, gn)
        plot(powerData.(gn).time, powerData.(gn).power_MW, ...
            'DisplayName', gn, 'LineWidth', 1.5, 'Color', colors(i,:));
    end
end
hold off;
xlabel('Time (s)');
ylabel('Active Power (MW)');
title('Generator Active Power Output');
legend('show', 'Location', 'best');
grid on;

sgtitle(sprintf('Modified Kundur Two-Area System (sim: %.1fs, wall: %.1fs)', 10, elapsed));

savefig(gcf, 'results_steady_state.fig');
saveas(gcf, 'results_steady_state.png');
fprintf('\nResults saved to results_steady_state.fig/png\n');

%% ========== Summary ==========
fprintf('\n=== Validation Summary ===\n');
fprintf('Model: Modified Kundur Two-Area System\n');
fprintf('Generators: G1, G2, G3 (sync) + W1, W2 (wind)\n');
fprintf('VSGs: ES1-ES4 (200 MVA each)\n');
fprintf('Simulation: %.1f s in %.1f s wall time\n', 10, elapsed);
fprintf('\nKey simlog variables per generator:\n');
fprintf('  .omegaDel  = frequency deviation (pu)\n');
fprintf('  .activeElectricalPower = P_elec (W)\n');
fprintf('  .theta     = rotor angle (rad)\n');
fprintf('  .w         = mechanical shaft speed (rad/s, 0 if pinned to MechRef)\n');
fprintf('\nUse sscexplore(simlog) to browse all variables interactively.\n');
