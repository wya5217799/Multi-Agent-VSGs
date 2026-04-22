function result = slx_save_model(model_name, target_path)
%SLX_SAVE_MODEL Save a loaded model, optionally to a target path.

    if nargin < 2
        target_path = '';
    end

    model_name = char(model_name);
    target_path = char(target_path);
    result = struct( ...
        'model_name', model_name, ...
        'target_path', target_path, ...
        'saved', false, ...
        'dirty_after', '', ...
        'file_name', '', ...
        'ok', true, ...
        'error_message', '');

    try
        if ~bdIsLoaded(model_name)
            load_system(model_name);
        end
        if isempty(target_path)
            save_system(model_name);
        else
            save_system(model_name, target_path);
        end
        result.saved = true;
        result.dirty_after = char(get_param(model_name, 'Dirty'));
        result.file_name = char(get_param(model_name, 'FileName'));
    catch ME
        result.ok = false;
        result.error_message = char(ME.message);
    end
end
