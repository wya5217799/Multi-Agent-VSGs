function summary = slx_delete_block(block_path)
% SLX_DELETE_BLOCK  Delete a block without touching its connected lines.
    summary = struct('ok', false, 'block_path', char(block_path), ...
                     'important_lines', {{}}, 'error_message', '');
    try
        delete_block(char(block_path));
        summary.ok = true;
        summary.important_lines = {['Deleted: ', char(block_path)]};
    catch ME
        summary.error_message = ME.message;
    end
end
