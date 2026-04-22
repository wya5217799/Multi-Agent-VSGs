function result = slx_runtime_reset(model_name, fast_restart, clear_sdi, clear_workspace_pattern)
%SLX_RUNTIME_RESET Reset general Simulink runtime state.

    if nargin < 2 || isempty(fast_restart)
        fast_restart = '';
    end
    if nargin < 3 || isempty(clear_sdi)
        clear_sdi = false;
    end
    if nargin < 4
        clear_workspace_pattern = '';
    end

    model_name = char(model_name);
    fast_restart = char(fast_restart);
    clear_workspace_pattern = char(clear_workspace_pattern);

    result = struct( ...
        'ok', true, ...
        'model_name', model_name, ...
        'fast_restart', fast_restart, ...
        'cleared_sdi', false, ...
        'cleared_workspace_pattern', clear_workspace_pattern, ...
        'error_message', '');

    try
        load_system(model_name);
        if logical(clear_sdi)
            try
                Simulink.sdi.clear;
                result.cleared_sdi = true;
            catch
            end
        end
        if ~isempty(clear_workspace_pattern)
            evalin('base', sprintf('clearvars -regexp ''%s''', clear_workspace_pattern));
        end
        if ~isempty(fast_restart)
            set_param(model_name, 'FastRestart', fast_restart);
        end
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
