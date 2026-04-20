function report = slx_check_params(model_name, varargin)
%SLX_CHECK_PARAMS Minimal parameter audit placeholder for MCP workflows.

    depth = 5;
    for i = 1:2:numel(varargin)
        if strcmpi(char(varargin{i}), 'depth') && i + 1 <= numel(varargin)
            depth = varargin{i + 1};
        end
    end

    load_system(char(model_name));
    blocks = find_system(char(model_name), 'SearchDepth', double(depth));
    n_blocks = max(numel(blocks) - 1, 0);

    report = struct( ...
        'passed', true, ...
        'n_checked', 0, ...
        'n_suspect', 0, ...
        'n_skipped', n_blocks, ...
        'suspects', {{}});
end
