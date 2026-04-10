function info = vsg_inspect_model(model_name, depth)
%VSG_INSPECT_MODEL  Return complete model structure as a serializable struct.
%   info.block_count  - total blocks found
%   info.blocks{}     - cell array of structs {path, type, name, key_params}
%   info.signal_count - total signal lines
%   info.subsystems{} - subsystem hierarchy

    if nargin < 2, depth = 3; end
    load_system(model_name);

    blocks = find_system(model_name, 'SearchDepth', depth);
    info.block_count = length(blocks);
    info.blocks = cell(length(blocks), 1);

    for i = 1:length(blocks)
        b.path = blocks{i};
        try
            b.type = get_param(blocks{i}, 'BlockType');
        catch
            b.type = get_param(blocks{i}, 'Type');  % root block_diagram
        end
        b.name = get_param(blocks{i}, 'Name');
        try
            dp = get_param(blocks{i}, 'DialogParameters');
            fn = fieldnames(dp);
            b.key_params = struct();
            for j = 1:min(length(fn), 10)
                b.key_params.(fn{j}) = get_param(blocks{i}, fn{j});
            end
        catch
            b.key_params = struct();
        end
        info.blocks{i} = b;
    end

    subs = find_system(model_name, 'SearchDepth', depth, 'BlockType', 'SubSystem');
    info.subsystems = subs;

    lines = find_system(model_name, 'SearchDepth', depth, 'FindAll', 'on', 'Type', 'line');
    info.signal_count = length(lines);
end
