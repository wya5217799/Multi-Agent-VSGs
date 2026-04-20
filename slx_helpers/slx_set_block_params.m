function summary = slx_set_block_params(block_path, params)
% SLX_SET_BLOCK_PARAMS  Set dialog parameters on a block.
% Python wrapper expects params_written to be a scalar integer.
    summary = struct('ok', false, 'block_path', char(block_path), ...
                     'params_written', 0, 'written_params', {{}}, ...
                     'important_lines', {{}}, 'error_message', '');
    try
        names = fieldnames(params);
        for k = 1:numel(names)
            set_param(char(block_path), names{k}, char(params.(names{k})));
        end
        summary.ok = true;
        summary.params_written = numel(names);
        summary.written_params = names;
        summary.important_lines = {sprintf('Set %d param(s) on %s', numel(names), char(block_path))};
    catch ME
        summary.error_message = ME.message;
    end
end
