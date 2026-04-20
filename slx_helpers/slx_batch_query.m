function result = slx_batch_query(model, block_paths)
%SLX_BATCH_QUERY  Query DialogParameters for multiple blocks in one IPC call.
%
%   Replaces N separate evaluate_matlab_code calls with a single call.
%   Use this whenever Claude needs parameters from more than one block.
%
%   Inputs:
%     model       - model name string (must already be loaded)
%     block_paths - cell array of full block paths
%
%   Output:
%     result(i).block   - block path (same as input)
%     result(i).params  - struct of param_name -> value_string
%     result(i).error   - error string if block not found, else ''
%
%   Example:
%     load_system('kundur_vsg');
%     r = slx_batch_query('kundur_vsg', {
%         'kundur_vsg/VSG_ES1/M0',
%         'kundur_vsg/VSG_ES2/M0'
%     });
%     r(1).params.Value   % -> '6.0'
%
%   Token impact vs N separate get_param calls:
%     Before: N round-trips, each with full stdout
%     After:  1 round-trip, structured output only

    if isempty(block_paths)
        result = struct('block', {}, 'params', {}, 'error', {});
        return;
    end

    if ~bdIsLoaded(model)
        error('slx_batch_query: model ''%s'' is not loaded. Call load_system first.', model);
    end

    n = numel(block_paths);
    result(n) = struct('block', '', 'params', struct(), 'error', '');

    for i = 1:n
        blk = block_paths{i};
        result(i).block = blk;
        result(i).params = struct();
        result(i).error = '';

        try
            dp = get_param(blk, 'DialogParameters');
            if isempty(dp)
                continue;
            end
            fields = fieldnames(dp);
            for fi = 1:numel(fields)
                fname = fields{fi};
                try
                    val = get_param(blk, fname);
                    if ischar(val) || isstring(val)
                        result(i).params.(fname) = char(val);
                    elseif isnumeric(val) && isscalar(val)
                        result(i).params.(fname) = num2str(val);
                    else
                        result(i).params.(fname) = mat2str(val);
                    end
                catch
                    result(i).params.(fname) = '<unreadable>';
                end
            end
        catch ME
            result(i).error = ME.message;
            result(i).params = struct();
        end
    end
end
