%% build_comm_topology.m
% Add communication ring topology for ESS agents
% Each ES receives frequency info from 2 neighbors with optional delay

function build_comm_topology(model_name)

if nargin < 1
    model_name = 'NE39bus_modified';
end

run('NE39bus_modified_data.m');

if ~bdIsLoaded(model_name)
    load_system(model_name);
end

fprintf('=== Building Communication Topology ===\n');

comm_path = [model_name '/CommNetwork'];
try
    get_param(comm_path, 'BlockType');
    fprintf('CommNetwork already exists, deleting and rebuilding.\n');
    delete_block(comm_path);
catch
end

% Create communication subsystem
add_block('built-in/SubSystem', comm_path, ...
    'Position', [50 2000 500 2300]);

% Inputs: omega from each ESS (8 inputs)
for i = 1:n_ess
    add_block('built-in/Inport', ...
        sprintf('%s/omega_ES%d', comm_path, i), ...
        'Position', [30 30+60*(i-1) 60 50+60*(i-1)], ...
        'Port', num2str(i));
end

% Inputs: RoCoF from each ESS (8 more inputs)
for i = 1:n_ess
    add_block('built-in/Inport', ...
        sprintf('%s/rocof_ES%d', comm_path, i), ...
        'Position', [30 530+60*(i-1) 60 550+60*(i-1)], ...
        'Port', num2str(n_ess + i));
end

% For each ESS, create outputs: [neighbor1_omega, neighbor2_omega, neighbor1_rocof, neighbor2_rocof]
out_idx = 0;
for i = 1:n_ess
    neighbors = COMM_ADJ{i};

    for n_idx = 1:2
        nb = neighbors(n_idx);
        out_idx = out_idx + 1;

        % Omega from neighbor with transport delay (Gaussian mean ~0.05-0.15s)
        delay_name = sprintf('Delay_omega_%d_from_%d', i, nb);
        out_name = sprintf('omega_nb%d_ES%d', n_idx, i);

        % Variable transport delay block
        add_block('built-in/TransportDelay', ...
            sprintf('%s/%s', comm_path, delay_name), ...
            'Position', [200 30+40*(out_idx-1) 280 50+40*(out_idx-1)], ...
            'DelayTime', '0.1', ...  % default 100ms, overridable from workspace
            'InitialOutput', '1.0');

        % Connect input omega of neighbor to delay
        add_line(comm_path, ...
            sprintf('omega_ES%d/1', nb), ...
            sprintf('%s/1', delay_name));

        % Output port
        add_block('built-in/Outport', ...
            sprintf('%s/%s', comm_path, out_name), ...
            'Position', [320 30+40*(out_idx-1) 350 50+40*(out_idx-1)], ...
            'Port', num2str(out_idx));
        add_line(comm_path, ...
            sprintf('%s/1', delay_name), ...
            sprintf('%s/1', out_name));
    end

    % RoCoF from neighbors
    for n_idx = 1:2
        nb = neighbors(n_idx);
        out_idx = out_idx + 1;

        delay_name = sprintf('Delay_rocof_%d_from_%d', i, nb);
        out_name = sprintf('rocof_nb%d_ES%d', n_idx, i);

        add_block('built-in/TransportDelay', ...
            sprintf('%s/%s', comm_path, delay_name), ...
            'Position', [200 30+40*(out_idx-1) 280 50+40*(out_idx-1)], ...
            'DelayTime', '0.1', ...
            'InitialOutput', '0.0');

        add_line(comm_path, ...
            sprintf('rocof_ES%d/1', nb), ...
            sprintf('%s/1', delay_name));

        add_block('built-in/Outport', ...
            sprintf('%s/%s', comm_path, out_name), ...
            'Position', [320 30+40*(out_idx-1) 350 50+40*(out_idx-1)], ...
            'Port', num2str(out_idx));
        add_line(comm_path, ...
            sprintf('%s/1', delay_name), ...
            sprintf('%s/1', out_name));
    end
end

save_system(model_name);
fprintf('=== Communication topology built: 8-node ring, %d delay links ===\n', out_idx);
fprintf('Total outputs: %d (4 per ESS: 2 omega + 2 rocof from neighbors)\n', out_idx);

end
