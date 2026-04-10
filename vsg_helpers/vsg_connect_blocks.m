function summary = vsg_connect_blocks(system_path, source_port, destination_port, autorouting)
%VSG_CONNECT_BLOCKS Connect two named ports using add_line.

    if nargin < 4, autorouting = true; end

    summary = struct( ...
        'ok', false, ...
        'important_lines', {{}}, ...
        'error_message', '');

    try
        route_mode = 'off';
        if logical(autorouting)
            route_mode = 'on';
        end
        add_line(char(system_path), char(source_port), char(destination_port), 'autorouting', route_mode);
        summary.ok = true;
        summary.important_lines = {sprintf('Connected %s -> %s', char(source_port), char(destination_port))};
    catch ME
        summary.error_message = char(ME.message);
    end
end
