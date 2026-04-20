function summary = slx_add_subsystem(subsystem_path, position, make_name_unique)
% SLX_ADD_SUBSYSTEM  Add a blank subsystem block to a model.
    summary = struct('ok', false, 'block_path', char(subsystem_path), ...
                     'important_lines', {{}}, 'error_message', '');
    try
        pos_arg    = {};
        unique_arg = {};
        if isnumeric(position) && numel(position) == 4
            pos_arg = {'Position', position(:)'};
        end
        if make_name_unique
            unique_arg = {'MakeNameUnique', 'on'};
        end
        blk = add_block('built-in/Subsystem', char(subsystem_path), ...
            pos_arg{:}, unique_arg{:});
        actual_path = getfullname(blk);
        summary.ok         = true;
        summary.block_path = char(actual_path);
        summary.important_lines = {['Added subsystem: ', char(actual_path)]};
    catch ME
        summary.error_message = ME.message;
    end
end
