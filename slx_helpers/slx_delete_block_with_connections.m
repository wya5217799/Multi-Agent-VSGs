function summary = slx_delete_block_with_connections(model_name, block_path, delete_lines)
% SLX_DELETE_BLOCK_WITH_CONNECTIONS  Delete a block and optionally its lines.
    summary = struct('ok', false, 'block_path', char(block_path), ...
                     'deleted_lines', {{}}, 'error_message', '');
    try
        if delete_lines
            ph = get_param(char(block_path), 'PortHandles');
            all_port_handles = [ph.Inport, ph.Outport, ph.Enable, ph.Trigger, ph.LConn, ph.RConn];
            deleted = [];
            seen   = [];
            for p = all_port_handles(:)'
                lh = get_param(p, 'Line');
                if lh > 0 && ~ismember(lh, seen)
                    seen(end+1)    = lh; %#ok<AGROW>
                    deleted(end+1) = lh; %#ok<AGROW>
                    delete_line(lh);
                end
            end
            summary.deleted_lines = num2cell(deleted);
        end
        delete_block(char(block_path));
        summary.ok = true;
    catch ME
        summary.error_message = ME.message;
    end
end
