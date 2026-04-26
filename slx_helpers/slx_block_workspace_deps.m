function result = slx_block_workspace_deps(model_name, workspace_vars)
%SLX_BLOCK_WORKSPACE_DEPS Find which blocks consume given workspace variables.
%
%   result = slx_block_workspace_deps(MODEL_NAME, WORKSPACE_VARS)
%
%   Scans every block in the loaded model and reports, for each variable
%   listed in WORKSPACE_VARS, the set of (block, parameter, expression)
%   triples whose parameter Value/Expression text references that variable.
%   Used to detect "dead" workspace vars that are assignin'd but never
%   consumed by any block dialog parameter.
%
%   Inputs
%   ------
%     MODEL_NAME      char/string  Loaded Simulink model name (without .slx).
%     WORKSPACE_VARS  cellstr     List of base-workspace variable names to
%                                  check. The model is scanned once; the
%                                  same scan answers all variables.
%
%   Output
%   ------
%   A struct with fields:
%     model         char        — model_name
%     vars          struct      — fieldname = var name, value = struct with
%                                  consumed_by_blocks, consumer_count, verdict
%     scan_summary  struct      — blocks_scanned, params_scanned, elapsed_sec
%
%   Detection limits
%   ----------------
%   - Static text scan only. Mask blocks are unmasked via
%     LookUnderMasks='all'; explicit Constant/Gain/Resistance dialog
%     parameter Values that reference vars by name are detected.
%   - NOT detected: vars accessed via evalin('base', ...) inside callbacks
%     or m-script blocks. Such cases must be tracked separately.
%   - Word-boundary regex avoids false matches like "my_var_1" matching
%     "my_var_10" — but a substring like "my_var * 2" matches "my_var".
%
%   Project-neutral: contains no scenario-specific names. Project test
%   fixtures live under tests/fixtures/ — see plan §3.B.5.

    arguments
        model_name        (1,:) char
        workspace_vars    cell
    end

    t0 = tic;

    % Load if not already loaded — caller is responsible for load failures
    if ~bdIsLoaded(model_name)
        load_system(model_name);
    end

    % Normalize workspace_vars to cellstr
    var_names = cell(1, numel(workspace_vars));
    for k = 1:numel(workspace_vars)
        v = workspace_vars{k};
        if isstring(v)
            v = char(v);
        end
        var_names{k} = v;
    end

    % Pre-compile regex patterns: word boundary so 'foo' doesn't match 'foo_bar'
    patterns = cell(1, numel(var_names));
    for k = 1:numel(var_names)
        % MATLAB regex word boundary: \< and \> only work with -P ; use look-arounds
        patterns{k} = ['(?<![A-Za-z0-9_])', regexptranslate('escape', var_names{k}), '(?![A-Za-z0-9_])'];
    end

    % Initialize result struct
    vars_out = struct();
    for k = 1:numel(var_names)
        vars_out.(matlab.lang.makeValidName(var_names{k})) = struct( ...
            'var_name', var_names{k}, ...
            'consumed_by_blocks', {{}}, ...
            'consumer_count', 0, ...
            'verdict', 'DEAD');
    end

    blocks = find_system(model_name, 'LookUnderMasks', 'all', 'Type', 'block');
    blocks_scanned = numel(blocks);
    params_scanned = 0;

    for bi = 1:numel(blocks)
        block_path = blocks{bi};
        try
            dlg_params = get_param(block_path, 'DialogParameters');
        catch
            continue;
        end
        if ~isstruct(dlg_params)
            continue;
        end
        param_names = fieldnames(dlg_params);
        for pj = 1:numel(param_names)
            pname = param_names{pj};
            try
                pval = get_param(block_path, pname);
            catch
                continue;
            end
            if ~(ischar(pval) || (isstring(pval) && isscalar(pval)))
                continue;
            end
            pval_char = char(pval);
            if isempty(pval_char)
                continue;
            end
            params_scanned = params_scanned + 1;
            for k = 1:numel(var_names)
                if ~isempty(regexp(pval_char, patterns{k}, 'once'))
                    field_key = matlab.lang.makeValidName(var_names{k});
                    entry = struct( ...
                        'block_path', block_path, ...
                        'param', pname, ...
                        'expression', pval_char);
                    vars_out.(field_key).consumed_by_blocks{end+1} = entry;
                    vars_out.(field_key).consumer_count = vars_out.(field_key).consumer_count + 1;
                    vars_out.(field_key).verdict = 'LIVE';
                end
            end
        end
    end

    result = struct( ...
        'model', model_name, ...
        'vars', vars_out, ...
        'scan_summary', struct( ...
            'blocks_scanned', blocks_scanned, ...
            'params_scanned', params_scanned, ...
            'elapsed_sec', toc(t0)));
end
