function result = slx_patch_and_verify(model_name, edits, run_update, smoke_test_stop_time, timeout_sec)
%SLX_PATCH_AND_VERIFY Apply edits, read them back, and optionally run update/smoke test.

    if nargin < 3, run_update = true; end
    if nargin < 4, smoke_test_stop_time = []; end
    if nargin < 5, timeout_sec = 60; end %#ok<NASGU>

    load_system(char(model_name));

    applied = {};
    readback = {};
    warnings = {};
    errors = {};
    update_ok = true;
    smoke_test_ok = [];
    smoke_summary = [];

    try
        for i = 1:numel(edits)
            edit = edits{i};
            block_path = char(edit.block_path);
            params = edit.params;
            fields = fieldnames(params);
            for j = 1:numel(fields)
                pname = fields{j};
                set_param(block_path, pname, char(string(params.(pname))));
            end
            applied{end + 1, 1} = struct('block_path', block_path, 'params', params); %#ok<AGROW>
            readback_params = struct();
            for j = 1:numel(fields)
                pname = fields{j};
                readback_params.(pname) = char(string(get_param(block_path, pname)));
            end
            readback{end + 1, 1} = struct('block_path', block_path, 'params', readback_params); %#ok<AGROW>
        end
    catch ME
        errors{end + 1, 1} = char(ME.message); %#ok<AGROW>
    end

    if logical(run_update) && isempty(errors)
        try
            set_param(char(model_name), 'SimulationCommand', 'Update');
        catch ME
            update_ok = false;
            errors{end + 1, 1} = char(ME.message); %#ok<AGROW>
        end
    end

    if ~isempty(smoke_test_stop_time) && isempty(errors)
        try
            evalc(sprintf('sim(''%s'', ''StopTime'', ''%s'');', char(model_name), num2str(smoke_test_stop_time)));
            smoke_test_ok = true;
            smoke_summary = struct('status', 'success', 'sim_time_reached', double(smoke_test_stop_time));
        catch ME
            smoke_test_ok = false;
            smoke_summary = struct('status', 'error', 'message', char(ME.message));
            warnings{end + 1, 1} = char(ME.message); %#ok<AGROW>
        end
    end

    result = struct( ...
        'ok', isempty(errors), ...
        'applied_edits', {applied}, ...
        'readback', {readback}, ...
        'update_ok', logical(update_ok), ...
        'smoke_test_ok', smoke_test_ok, ...
        'smoke_test_summary', smoke_summary, ...
        'warnings', {warnings}, ...
        'errors', {errors});
end
