function ic = slx_load_kundur_ic(json_path)
%SLX_LOAD_KUNDUR_IC  Load and validate Kundur initial conditions from JSON.
%
%   ic = slx_load_kundur_ic(json_path)
%
%   Canonical loader for kundur_ic.json.  Equivalent validation to the
%   Python loader in scenarios/kundur/kundur_ic.py.  All callers in
%   build scripts must use this function -- no bare jsondecode.
%
%   Returns:
%     ic.schema_version       — integer (must be 1)
%     ic.calibration_status   — string
%     ic.vsg_p0_vsg_base_pu  — 1×4 double row vector, VSG-base pu
%     ic.source_hash          — string ('sha256:<64-hex>')
%
%   Raises:
%     error() if file not found or validation fails.

    if ~isfile(json_path)
        error('slx_load_kundur_ic:fileNotFound', ...
            'kundur_ic.json not found at: %s\nRun build_powerlib_kundur.m or restore from git.', ...
            json_path);
    end

    raw = fileread(json_path);
    data = jsondecode(raw);

    errors = {};

    % schema_version
    if ~isfield(data, 'schema_version') || data.schema_version ~= 1
        errors{end+1} = sprintf('schema_version must be 1, got %s', ...
            num2str(data.schema_version));
    end

    % calibration_status
    valid_statuses = {'placeholder_pre_impedance_fix', 'calibrated'};
    if ~isfield(data, 'calibration_status') || ...
            ~any(strcmp(data.calibration_status, valid_statuses))
        errors{end+1} = sprintf('calibration_status=%s is not valid', ...
            data.calibration_status);
    end

    % vsg_p0_vsg_base_pu: must be length-4 positive vector
    if ~isfield(data, 'vsg_p0_vsg_base_pu')
        errors{end+1} = 'missing field: vsg_p0_vsg_base_pu';
    else
        p0 = double(data.vsg_p0_vsg_base_pu(:)');  % force row vector
        if numel(p0) ~= 4
            errors{end+1} = sprintf('vsg_p0_vsg_base_pu must have 4 elements, got %d', numel(p0));
        elseif any(p0 <= 0)
            errors{end+1} = 'all vsg_p0_vsg_base_pu values must be positive';
        end
    end

    % units
    if isfield(data, 'units') && isfield(data.units, 'vsg_p0_vsg_base_pu')
        if ~strcmp(data.units.vsg_p0_vsg_base_pu, 'pu_on_vsg_base')
            errors{end+1} = sprintf('units.vsg_p0_vsg_base_pu must be ''pu_on_vsg_base'', got %s', ...
                data.units.vsg_p0_vsg_base_pu);
        end
    end

    % source_hash: must start with 'sha256:' followed by 64 hex chars
    if ~isfield(data, 'source_hash') || ...
            isempty(regexp(data.source_hash, '^sha256:[0-9a-f]{64}$', 'once'))
        errors{end+1} = sprintf('source_hash=%s must match sha256:<64-hex-chars>', ...
            char(data.source_hash));
    end

    if ~isempty(errors)
        msg = strjoin(errors, '\n  - ');
        error('slx_load_kundur_ic:validationFailed', ...
            'KundurIC validation failed:\n  - %s', msg);
    end

    ic.schema_version      = data.schema_version;
    ic.calibration_status  = data.calibration_status;
    ic.vsg_p0_vsg_base_pu = double(data.vsg_p0_vsg_base_pu(:)');  % 1×4 row vector
    ic.source_hash         = data.source_hash;
end
