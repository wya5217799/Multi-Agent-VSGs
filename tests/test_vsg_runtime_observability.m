function tests = test_vsg_runtime_observability
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    tc.TestData.model = "diag_runtime_wave6_test";
    new_system(tc.TestData.model);
    open_system(tc.TestData.model);

    add_block("simulink/Sources/Sine Wave", tc_path(tc, "Sine"), ...
        "Position", [40 40 90 70], ...
        "Amplitude", "2", ...
        "Frequency", "1");
    add_block("simulink/Math Operations/Gain", tc_path(tc, "Gain"), ...
        "Position", [140 35 190 75], ...
        "Gain", "2");
    add_block("simulink/Sinks/Out1", tc_path(tc, "Out1"), ...
        "Position", [360 45 390 65]);
    add_block("simulink/Sinks/To Workspace", tc_path(tc, "ToWs"), ...
        "Position", [250 100 330 130], ...
        "VariableName", "sine_ws", ...
        "SaveFormat", "Timeseries");

    add_line(tc.TestData.model, "Sine/1", "Gain/1", "autorouting", "on");
    add_line(tc.TestData.model, "Gain/1", "Out1/1", "autorouting", "on");
    add_line(tc.TestData.model, "Gain/1", "ToWs/1", "autorouting", "on");

    set_param(tc.TestData.model, ...
        "StopTime", "1.0", ...
        "SignalLogging", "on", ...
        "ReturnWorkspaceOutputs", "on", ...
        "SignalLoggingName", "logsout");

    gain_ph = get_param(tc_path(tc, "Gain"), "PortHandles");
    gain_line = get_param(gain_ph.Outport(1), "Line");
    gain_segment = get_param(gain_line, "Object");
    gain_segment.DataLogging = true;
    gain_segment.DataLoggingNameMode = "Custom";
    gain_segment.DataLoggingName = "gain_logged";
end

function teardownOnce(tc)
    if bdIsLoaded(tc.TestData.model)
        close_system(tc.TestData.model, 0);
    end
    evalin('base', 'if exist(''sine_ws'', ''var''), clear(''sine_ws''); end');
end

function test_solver_warning_summary_collapses_repeated_lines(tc)
    code = [
        "disp('Warning: Minimum step size violation at t=4.9008; min step = 1.74e-14');" + newline + ...
        "disp('Warning: Minimum step size violation at t=4.9008; min step = 1.73e-14');" + newline + ...
        "disp('Warning: Minimum step size violation at t=4.9008; min step = 1.72e-14');"
    ];

    result = vsg_solver_warning_summary(tc.TestData.model, code, 10, {}, true);

    tc.verifyTrue(result.ok, result.error_message);
    tc.verifyEqual(result.unique_warning_types, 1);
    tc.verifyEqual(numel(result.collapsed_warnings), 1);
    tc.verifyEqual(result.collapsed_warnings{1}.count, 3);
    tc.verifyEqual(result.stiffness_detected, true);
    tc.verifyEqual(result.likely_stuck_time, 4.9008, 'AbsTol', 1e-9);
end

function test_signal_snapshot_reads_logsout_toworkspace_and_block_output(tc)
    result = vsg_signal_snapshot(tc.TestData.model, 0.25, ...
        {'logsout:gain_logged', 'toworkspace:sine_ws', struct('block_path', tc_path(tc, "Gain"), 'port_index', 1), 'logsout:missing'}, ...
        true);

    tc.verifyTrue(result.read_ok, strjoin(result.warnings, newline));
    keys = cellfun(@(item) char(item.signal), result.values, 'UniformOutput', false);
    tc.verifyTrue(any(strcmp(keys, 'logsout:gain_logged')));
    tc.verifyTrue(any(strcmp(keys, 'toworkspace:sine_ws')));
    tc.verifyTrue(any(strcmp(keys, ['block:' char(tc_path(tc, "Gain")) ':1'])));
    tc.verifyEqual(result.missing_signals, {'logsout:missing'});
end

function out = tc_path(tc, block_name)
    out = char(string(tc.TestData.model) + "/" + string(block_name));
end
