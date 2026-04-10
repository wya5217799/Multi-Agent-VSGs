function tree = vsg_get_block_tree(model_name, root_path, max_depth)
%VSG_GET_BLOCK_TREE  Return hierarchical block structure as nested struct.
%   tree.name, tree.type, tree.path, tree.children{}

    if nargin < 2, root_path = model_name; end
    if nargin < 3, max_depth = 3; end

    load_system(model_name);
    tree = build_tree(root_path, 0, max_depth);
end

function node = build_tree(path, current_depth, max_depth)
    node.name = get_param(path, 'Name');
    try
        node.type = get_param(path, 'BlockType');
    catch
        node.type = get_param(path, 'Type');  % root block_diagram
    end
    node.path = path;
    node.children = {};

    if current_depth >= max_depth
        return;
    end

    if strcmp(node.type, 'SubSystem') || strcmp(node.type, 'block_diagram')
        children = find_system(path, 'SearchDepth', 1);
        children = children(2:end);  % exclude self
        for i = 1:length(children)
            node.children{end+1} = build_tree(children{i}, current_depth + 1, max_depth);
        end
    end
end
