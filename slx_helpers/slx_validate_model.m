function report = slx_validate_model(model_name, expected_cfg)
%SLX_VALIDATE_MODEL  Check model against expected configuration.
%   expected_cfg.n_agents       - expected number of VSG subsystems
%   expected_cfg.subsys_pattern - e.g. 'VSG_ES' or 'VSG_W'
%   expected_cfg.required_blocks - cell array of block types that must exist
%
%   report.passed    - boolean
%   report.errors{}  - cell array of error descriptions
%   report.warnings{} - cell array of warnings

    load_system(model_name);
    report.passed = true;
    report.errors = {};
    report.warnings = {};

    % Check VSG subsystem count
    vsg_subs = find_system(model_name, 'SearchDepth', 1, ...
        'Name', [expected_cfg.subsys_pattern '*']);
    actual_count = length(vsg_subs);
    if actual_count ~= expected_cfg.n_agents
        report.passed = false;
        report.errors{end+1} = sprintf('Expected %d VSG subsystems, found %d', ...
            expected_cfg.n_agents, actual_count);
    end

    % Check required blocks exist
    for i = 1:length(expected_cfg.required_blocks)
        found = find_system(model_name, 'BlockType', expected_cfg.required_blocks{i});
        if isempty(found)
            report.passed = false;
            report.errors{end+1} = sprintf('Missing required block type: %s', ...
                expected_cfg.required_blocks{i});
        end
    end

    % Check solver settings
    solver = get_param(model_name, 'Solver');
    if ~strcmp(solver, 'ode23t') && ~strcmp(solver, 'ode15s')
        report.warnings{end+1} = sprintf('Solver is %s, expected ode23t or ode15s', solver);
    end
end
