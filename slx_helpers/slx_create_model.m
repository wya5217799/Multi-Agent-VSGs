function summary = slx_create_model(model_name, open_model)
%SLX_CREATE_MODEL Create a blank Simulink model.

    if nargin < 2, open_model = true; end

    summary = struct( ...
        'ok', false, ...
        'model_name', char(model_name), ...
        'important_lines', {{}}, ...
        'error_message', '');

    try
        new_system(char(model_name));
        if logical(open_model)
            open_system(char(model_name));
        end
        summary.ok = true;
        summary.important_lines = {sprintf('Created model %s', char(model_name))};
    catch ME
        summary.error_message = char(ME.message);
    end
end
