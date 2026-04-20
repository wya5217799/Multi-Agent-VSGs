function path = slx_trace_signal(model_name, signal_name)
%SLX_TRACE_SIGNAL  Trace a signal from source to all sinks.
%   Returns a struct with source block, sinks, and intermediate blocks.

    load_system(model_name);
    ph = find_system(model_name, 'FindAll', 'on', 'Type', 'port', 'Name', signal_name);
    path = struct('source', '', 'sinks', {{}}, 'through', {{}});

    if isempty(ph)
        path.source = 'NOT_FOUND';
        return;
    end

    line_h = get_param(ph(1), 'Line');
    if line_h > 0
        src_h = get_param(line_h, 'SrcBlockHandle');
        path.source = getfullname(src_h);

        dst_h = get_param(line_h, 'DstBlockHandle');
        for i = 1:length(dst_h)
            path.sinks{end+1} = getfullname(dst_h(i));
        end
    end
end
