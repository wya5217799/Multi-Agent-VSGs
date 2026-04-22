function result = slx_batch_query(model, block_paths, param_names)
%SLX_BATCH_QUERY  Query parameters for multiple blocks in one IPC call.
%
%   Replaces N separate evaluate_matlab_code calls with a single call.
%   Use this whenever Claude needs parameters from more than one block.
%   Supersedes slx_bulk_get_params (removed); accepts an optional third
%   argument to limit the parameters returned.
%
%   Inputs:
%     model       - model name string (auto-loaded if not already loaded)
%     block_paths - cell array of full block paths
%     param_names - (optional) cell array of parameter names to read.
%                   When omitted or empty, all DialogParameters are read.
%
%   Output:
%     result(i).block          - block path (same as input)
%     result(i).params         - struct of param_name -> value_string
%     result(i).missing_params - cell array of param names that could not
%                                be read (only populated when param_names
%                                is supplied; otherwise always {})
%     result(i).error          - error string if block not found, else ''
%
%   Example — read all params:
%     r = slx_batch_query('demo_model', {
%         'demo_model/Gain1',
%         'demo_model/Gain2'
%     });
%     r(1).params.Gain   % -> '2'
%
%   Example — read selected params only:
%     r = slx_batch_query('demo_model', {'demo_model/Gain1'}, {'Gain'});
%     r(1).missing_params  % -> {} or {'Gain'} if Gain does not exist
%
%   Token impact vs N separate get_param calls:
%     Before: N round-trips, each with full stdout
%     After:  1 round-trip, structured output only

    if isempty(block_paths)
        result = struct('block', {}, 'params', {}, 'missing_params', {}, 'error', {});
        return;
    end

    % Auto-load model if not already in memory (aligns with former
    % slx_bulk_get_params behaviour; harmless if already loaded).
    if ~bdIsLoaded(model)
        load_system(char(model));
    end

    % Determine whether we are in selective-params mode.
    selective = nargin >= 3 && ~isempty(param_names);

    n = numel(block_paths);
    result(n) = struct('block', '', 'params', struct(), 'missing_params', {{}}, 'error', '');

    for i = 1:n
        blk = block_paths{i};
        result(i).block          = blk;
        result(i).params         = struct();
        result(i).missing_params = {};
        result(i).error          = '';

        if selective
            % ── Selective mode: only read the requested param_names ──────
            try
                for j = 1:numel(param_names)
                    pname = char(param_names{j});
                    try
                        val = get_param(blk, pname);
                        result(i).params.(pname) = i_to_string(val);
                    catch
                        result(i).missing_params{end+1} = pname; %#ok<AGROW>
                    end
                end
            catch ME
                result(i).error          = ME.message;
                result(i).params         = struct();
                result(i).missing_params = {};
            end
        else
            % ── All-params mode: enumerate DialogParameters ───────────────
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
                        result(i).params.(fname) = i_to_string(val);
                    catch
                        result(i).params.(fname) = '<unreadable>';
                    end
                end
            catch ME
                result(i).error  = ME.message;
                result(i).params = struct();
            end
        end
    end
end

% ── Local helper ────────────────────────────────────────────────────────────
function value = i_to_string(raw)
    if ischar(raw) || isstring(raw)
        value = char(raw);
    elseif isnumeric(raw) && isscalar(raw)
        value = num2str(raw);
    else
        value = mat2str(raw);
    end
end
