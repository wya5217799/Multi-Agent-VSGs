function result = slx_run_window(model_name, start_time, stop_time, capture_errors)
%SLX_RUN_WINDOW Run one model over a controlled simulation window.

    if nargin < 4 || isempty(capture_errors)
        capture_errors = true;
    end

    model_name = char(model_name);
    result = struct( ...
        'model_name', model_name, ...
        'start_time', double(start_time), ...
        'stop_time', double(stop_time), ...
        'sim_time_reached', [], ...
        'ok', true, ...
        'error_message', '');

    try
        load_system(model_name);
        sim_in = Simulink.SimulationInput(model_name);
        if logical(capture_errors)
            capture_value = 'on';
        else
            capture_value = 'off';
        end
        sim_in = sim_in.setModelParameter( ...
            'StartTime', num2str(double(start_time), '%.9g'), ...
            'StopTime', num2str(double(stop_time), '%.9g'), ...
            'CaptureErrors', capture_value);
        sim_out = sim(sim_in); %#ok<NASGU>
        result.sim_time_reached = double(stop_time);
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
