%% build_complete_model.m
% Build the complete Modified NE39 model with:
% 1. Wind farms W1-W8 replacing generators at Bus 30-37
%    (Simulink blocks: G10, G2, G3, G4, G5, G6, G7, G8)
% 2. G9(Bus38), G1(Bus39) retained as sync machines (voltage source in R2025b)
% 3. 8 ESS-VSG subsystems connected to bus 30-37
% 4. Signal loggers for RL training interface
%
% Starts from NE39bus_v2 (already built by fix_sm_r2025b_v2.m)

evalin('base', 'clear all');
evalin('base', 'run(''NE39bus_data.m'')');
run('NE39bus_modified_data.m');
load_system('powerlib');

dst_model = 'NE39bus_v2';
if ~bdIsLoaded(dst_model), load_system(dst_model); end

n_ess = 8;
% ESS connected to wind farm buses (same as paper: buses 30-37)
parent_bus_nums = [30 31 32 33 34 35 36 37];
fn = 60; % System frequency (original IEEE 39-bus = 60Hz)

%% ======================================================================
%  Step 1: Cleanup any previous ESS blocks
%% ======================================================================
fprintf('=== Cleanup ===\n');
for i = 1:n_ess
    names_to_clean = {
        sprintf('VSG_ES%d', i), sprintf('VSrc_ES%d', i), ...
        sprintf('Meas_ES%d', i), sprintf('Zline_ES%d', i), ...
        sprintf('wref_%d', i), sprintf('dM_%d', i), sprintf('dD_%d', i), ...
        sprintf('Pref_%d', i), sprintf('Pe_%d', i), ...
        sprintf('Log_omega_ES%d', i), sprintf('Log_delta_ES%d', i), ...
        sprintf('Log_P_out_ES%d', i), ...
        sprintf('Log_Vabc_ES%d', i), sprintf('Log_Iabc_ES%d', i)
    };
    for c = 1:length(names_to_clean)
        try delete_block([dst_model '/' names_to_clean{c}]); catch, end
    end
end
fprintf('  Done.\n');

%% ======================================================================
%  Step 2: Build VSG subsystems (swing equation blocks)
%% ======================================================================
fprintf('\n=== Building VSG subsystems ===\n');

for i = 1:n_ess
    vsg_name = sprintf('VSG_ES%d', i);
    vsg_path = [dst_model '/' vsg_name];

    % Position in model
    bx = 50 + mod(i-1, 4) * 450;
    by = 2600 + floor((i-1)/4) * 500;

    % Create subsystem
    add_block('built-in/SubSystem', vsg_path, ...
        'Position', [bx by bx+120 by+100]);

    % 5 inputs: omega_ref, delta_M, delta_D, P_ref, P_e
    % 3 outputs: omega, delta, P_out
    input_names = {'omega_ref', 'delta_M', 'delta_D', 'P_ref', 'P_e'};
    for k = 1:5
        inp = sprintf('%s/In%d', vsg_path, k);
        add_block('built-in/Inport', inp, ...
            'Position', [30, 20+(k-1)*50, 60, 34+(k-1)*50], ...
            'Port', num2str(k));
        set_param(inp, 'Name', input_names{k});
    end

    output_names = {'omega', 'delta', 'P_out'};
    for k = 1:3
        outp = sprintf('%s/Out%d', vsg_path, k);
        add_block('built-in/Outport', outp, ...
            'Position', [600, 30+(k-1)*80, 630, 44+(k-1)*80], ...
            'Port', num2str(k));
        set_param(outp, 'Name', output_names{k});
    end

    % Internal blocks for swing equation:
    % M_total = M0 + delta_M
    % D_total = D0 + delta_D
    % d(omega)/dt = (1/M_total) * (P_ref - P_e - D_total*(omega - omega_ref))
    % d(delta)/dt = omega_n * (omega - omega_ref)
    % P_out = P_ref - D_total*(omega - omega_ref)

    % Constants
    add_block('built-in/Constant', [vsg_path '/M0'], ...
        'Position', [100 10 150 30], 'Value', num2str(VSG_M0));
    add_block('built-in/Constant', [vsg_path '/D0'], ...
        'Position', [100 60 150 80], 'Value', num2str(VSG_D0));
    add_block('built-in/Constant', [vsg_path '/wn'], ...
        'Position', [300 260 350 280], 'Value', num2str(2*pi*fn));

    % M_total = M0 + delta_M
    add_block('built-in/Sum', [vsg_path '/SumM'], ...
        'Position', [180 15 210 45], 'Inputs', '++');
    add_line(vsg_path, 'M0/1', 'SumM/1');
    add_line(vsg_path, 'delta_M/1', 'SumM/2');

    % D_total = D0 + delta_D
    add_block('built-in/Sum', [vsg_path '/SumD'], ...
        'Position', [180 65 210 95], 'Inputs', '++');
    add_line(vsg_path, 'D0/1', 'SumD/1');
    add_line(vsg_path, 'delta_D/1', 'SumD/2');

    % omega_error = omega - omega_ref
    add_block('built-in/Sum', [vsg_path '/SumW'], ...
        'Position', [350 120 380 150], 'Inputs', '+-');

    % D_term = D_total * omega_error
    add_block('built-in/Product', [vsg_path '/MulD'], ...
        'Position', [420 80 450 110], 'Inputs', '**');

    % P_accel = P_ref - P_e - D_term
    add_block('built-in/Sum', [vsg_path '/SumP'], ...
        'Position', [490 80 520 140], 'Inputs', '+--');

    % d_omega = P_accel / M_total
    add_block('built-in/Product', [vsg_path '/DivM'], ...
        'Position', [550 80 580 120], 'Inputs', '*/');

    % Integrator for omega
    add_block('built-in/Integrator', [vsg_path '/IntW'], ...
        'Position', [620 80 660 120], ...
        'InitialCondition', '1.0', ...
        'UpperSaturationLimit', '1.1', ...
        'LowerSaturationLimit', '0.9');

    % Integrator for delta
    add_block('built-in/Integrator', [vsg_path '/IntD'], ...
        'Position', [500 240 540 280], ...
        'InitialCondition', '0');

    % Connect swing equation
    % omega output -> feedback to SumW
    add_line(vsg_path, 'IntW/1', 'omega/1');

    % SumW: omega - omega_ref
    add_line(vsg_path, 'IntW/1', 'SumW/1');
    add_line(vsg_path, 'omega_ref/1', 'SumW/2');

    % D_term = D_total * omega_error
    add_line(vsg_path, 'SumD/1', 'MulD/1');
    add_line(vsg_path, 'SumW/1', 'MulD/2');

    % P_accel = P_ref - P_e - D_term
    add_line(vsg_path, 'P_ref/1', 'SumP/1');
    add_line(vsg_path, 'P_e/1', 'SumP/2');
    add_line(vsg_path, 'MulD/1', 'SumP/3');

    % d_omega = P_accel / M_total
    add_line(vsg_path, 'SumP/1', 'DivM/1');
    add_line(vsg_path, 'SumM/1', 'DivM/2');

    % omega integrator
    add_line(vsg_path, 'DivM/1', 'IntW/1');

    % delta: d(delta)/dt = wn * (omega - omega_ref)
    add_block('built-in/Product', [vsg_path '/MulWn'], ...
        'Position', [420 240 450 280], 'Inputs', '**');
    add_line(vsg_path, 'wn/1', 'MulWn/1');
    add_line(vsg_path, 'SumW/1', 'MulWn/2');
    add_line(vsg_path, 'MulWn/1', 'IntD/1');
    add_line(vsg_path, 'IntD/1', 'delta/1');

    % P_out = P_ref - D_total*(omega - omega_ref) = P_ref - D_term
    add_block('built-in/Sum', [vsg_path '/SumPout'], ...
        'Position', [490 310 520 340], 'Inputs', '+-');
    add_line(vsg_path, 'P_ref/1', 'SumPout/1');
    add_line(vsg_path, 'MulD/1', 'SumPout/2');
    add_line(vsg_path, 'SumPout/1', 'P_out/1');

    fprintf('  Built %s\n', vsg_name);
end

%% ======================================================================
%  Step 3: Add ESS voltage sources with V-I measurement
%% ======================================================================
fprintf('\n=== Adding ESS voltage sources ===\n');

% Bus-specific load flow voltages (from original model)
vlf_map = containers.Map(...
    {30, 31, 32, 33, 34, 35, 36, 37}, ...
    {[1.048, -3.646], [0.982, 0], [0.9831, 2.466], [0.9972, 4.423], ...
     [1.012, 3.398], [1.049, 5.698], [1.063, 8.494], [1.028, 2.181]});

% Impedance parameters
Vbase_v_ess = VSG_BUS_VN * 1000;
Zbase_ess = Vbase_v_ess^2 / (Sbase * 1e6);

for i = 1:n_ess
    bus_num = parent_bus_nums(i);
    fprintf('\n  ESS %d -> Bus %d\n', i, bus_num);

    bx = 50 + mod(i-1, 4) * 450;
    by = 3400 + floor((i-1)/4) * 300;

    ess_src_name = sprintf('VSrc_ES%d', i);
    ess_src_path = [dst_model '/' ess_src_name];
    meas_name = sprintf('Meas_ES%d', i);
    meas_path = [dst_model '/' meas_name];

    % Bus-specific voltage and angle from load flow
    vl = vlf_map(bus_num);
    V_ess = Vbase_v_ess * vl(1);  % Voltage in V (bus-specific)
    A_ess = vl(2);                 % Phase angle in degrees
    R_ess = max(VSG_RA * Zbase_ess, 0.01);
    L_ess = VSG_XD1 * Zbase_ess / (2*pi*fn);

    % Add Three-Phase Source with internal impedance
    add_block('powerlib/Electrical Sources/Three-Phase Source', ...
        ess_src_path, 'Position', [bx by bx+80 by+80]);
    set_param(ess_src_path, ...
        'Voltage', num2str(V_ess), ...
        'PhaseAngle', num2str(A_ess), ...
        'Frequency', num2str(fn), ...
        'InternalConnection', 'Yg', ...
        'NonIdealSource', 'on', ...
        'SpecifyImpedance', 'on', ...
        'Resistance', num2str(R_ess), ...
        'Inductance', num2str(L_ess));
    fprintf('    VSrc: V=%.1fV, ang=%.1f, R=%.4f, L=%.6f\n', ...
        V_ess, A_ess, R_ess, L_ess);

    % Add Three-Phase V-I Measurement between source and bus
    try
        add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
            meas_path, 'Position', [bx+120 by bx+200 by+80]);
        % Connect: Source -> Meas -> Bus
        for p = 1:3
            add_line(dst_model, ...
                sprintf('%s/RConn%d', ess_src_name, p), ...
                sprintf('%s/LConn%d', meas_name, p), ...
                'autorouting', 'smart');
        end
        fprintf('    V-I Measurement added.\n');
    catch e
        fprintf('    Meas add err: %s\n', e.message);
    end

    % Connect measurement output to parent bus node
    bus_name = num2str(bus_num);
    connected = false;
    try
        for p = 1:3
            add_line(dst_model, ...
                sprintf('%s/RConn%d', meas_name, p), ...
                sprintf('%s/LConn%d', bus_name, p), ...
                'autorouting', 'smart');
        end
        fprintf('    Meas -> Bus %s (LConn)\n', bus_name);
        connected = true;
    catch, end
    if ~connected
        try
            for p = 1:3
                add_line(dst_model, ...
                    sprintf('%s/RConn%d', meas_name, p), ...
                    sprintf('%s/RConn%d', bus_name, p), ...
                    'autorouting', 'smart');
            end
            fprintf('    Meas -> Bus %s (RConn)\n', bus_name);
            connected = true;
        catch, end
    end
    if ~connected
        % Fallback: connect source directly to bus (skip measurement)
        fprintf('    WARN: Meas connection failed, direct connect.\n');
        try
            for p = 1:3
                add_line(dst_model, ...
                    sprintf('%s/RConn%d', ess_src_name, p), ...
                    sprintf('%s/LConn%d', bus_name, p), ...
                    'autorouting', 'smart');
            end
        catch
            try
                for p = 1:3
                    add_line(dst_model, ...
                        sprintf('%s/RConn%d', ess_src_name, p), ...
                        sprintf('%s/RConn%d', bus_name, p), ...
                        'autorouting', 'smart');
                end
            catch, end
        end
    end

    % Log Vabc and Iabc from V-I measurement (signal ports 1,2)
    % Python computes P_e = real(sum(Vabc .* conj(Iabc))) between steps
    meas_logs = {'Vabc', 'Iabc'};
    for ml = 1:2
        log_name = sprintf('Log_%s_ES%d', meas_logs{ml}, i);
        log_path = [dst_model '/' log_name];
        lx = bx + 250;
        ly = by + (ml-1)*40;
        try
            add_block('built-in/ToWorkspace', log_path, ...
                'Position', [lx ly lx+60 ly+20], ...
                'VariableName', sprintf('%s_ES%d', meas_logs{ml}, i), ...
                'SaveFormat', 'Timeseries');
            add_line(dst_model, sprintf('%s/%d', meas_name, ml), ...
                [log_name '/1'], 'autorouting', 'smart');
        catch, end
    end

    %% Connect signal inputs to VSG subsystem
    % P_e is a Constant block - Python updates it via set_param between RL steps
    % using measured power: P_e = real(sum(Vabc .* conj(Iabc))) / Sbase
    vsg_name = sprintf('VSG_ES%d', i);
    const_defs = {
        sprintf('wref_%d', i), '1.0';
        sprintf('dM_%d', i), '0';
        sprintf('dD_%d', i), '0';
        sprintf('Pref_%d', i), num2str(VSG_P0);
        sprintf('Pe_%d', i), num2str(VSG_P0);
    };

    for cb = 1:size(const_defs, 1)
        cname = const_defs{cb, 1};
        cval = const_defs{cb, 2};
        cpath = [dst_model '/' cname];
        cx = bx - 120;
        cy = by - 100 + (cb-1) * 25;
        try
            add_block('built-in/Constant', cpath, ...
                'Position', [cx cy cx+40 cy+15], 'Value', cval);
            add_line(dst_model, [cname '/1'], ...
                sprintf('%s/%d', vsg_name, cb), 'autorouting', 'smart');
        catch, end
    end

    %% Add ToWorkspace loggers for VSG outputs
    out_names = {'omega', 'delta', 'P_out'};
    for out_idx = 1:3
        log_name = sprintf('Log_%s_ES%d', out_names{out_idx}, i);
        log_path = [dst_model '/' log_name];
        lx = bx + 200;
        ly = by - 100 + (out_idx-1) * 30;
        try
            add_block('built-in/ToWorkspace', log_path, ...
                'Position', [lx ly lx+60 ly+20], ...
                'VariableName', sprintf('%s_ES%d', out_names{out_idx}, i), ...
                'SaveFormat', 'Timeseries');
            add_line(dst_model, sprintf('%s/%d', vsg_name, out_idx), ...
                [log_name '/1'], 'autorouting', 'smart');
        catch, end
    end

    fprintf('    Signal + logging connected.\n');
end

%% ======================================================================
%  Step 4: Save and test simulation
%% ======================================================================
save_system(dst_model);
fprintf('\n=== Model saved ===\n');

fprintf('\n=== Running 1-second test simulation ===\n');
set_param(dst_model, 'StopTime', '1.0');
try
    simOut = sim(dst_model, 'StopTime', '1.0');
    fprintf('SUCCESS! 1-second simulation completed.\n');

    % Check logged outputs
    vars_to_check = {'omega_ES1', 'delta_ES1', 'P_out_ES1'};
    for v = 1:length(vars_to_check)
        try
            ts = simOut.get(vars_to_check{v});
            if ~isempty(ts)
                fprintf('  %s: %d samples, final=%.6f\n', ...
                    vars_to_check{v}, length(ts.Data), ts.Data(end));
            end
        catch
            % Try evalin base
            try
                data = evalin('base', vars_to_check{v});
                fprintf('  %s: available in base workspace\n', vars_to_check{v});
            catch
                fprintf('  %s: not found\n', vars_to_check{v});
            end
        end
    end
catch me
    fprintf('FAIL: %s\n', me.message);
    if ~isempty(me.cause)
        fprintf('Cause: %s\n', me.cause{1}.message);
    end
end

fprintf('\n=== build_complete_model done ===\n');
