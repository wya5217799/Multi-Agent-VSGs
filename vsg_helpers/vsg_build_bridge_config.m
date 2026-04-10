function cfg = vsg_build_bridge_config( ...
    m_path_template, d_path_template, omega_signal, vabc_signal, iabc_signal, ...
    pe_path_template, src_path_template, vsg_sn, delta_signal, p_out_signal, ...
    m_var_template, d_var_template)
%VSG_BUILD_BRIDGE_CONFIG  Build bridge config struct from typed Python arguments.
%
%   Replaces the Python-side string-eval pattern:
%       session.eval("struct('omega_signal','omega_ES{idx}',...)")
%   with a typed MATLAB function call whose signature IS the data contract.
%   Field name mismatches between Python BridgeConfig and this function
%   cause an immediate argument error instead of silently using wrong defaults.
%
%   Required fields (used by vsg_step_and_read _extract_state):
%     omega_signal, vabc_signal, iabc_signal
%
%   Optional fields (set only when non-empty):
%     pe_path_template, src_path_template, p_out_signal
%
%   All string args are coerced via char() to handle both char and Python str.

    cfg.m_path_template = char(m_path_template);
    cfg.d_path_template = char(d_path_template);
    cfg.omega_signal    = char(omega_signal);
    cfg.vabc_signal     = char(vabc_signal);
    cfg.iabc_signal     = char(iabc_signal);
    cfg.vsg_sn          = double(vsg_sn);
    cfg.delta_signal    = char(delta_signal);
    cfg.m_var_template  = char(m_var_template);
    cfg.d_var_template  = char(d_var_template);

    % Optional: only set if caller provides non-empty value
    pe = char(pe_path_template);
    if ~isempty(pe)
        cfg.pe_path_template = pe;
    end

    src = char(src_path_template);
    if ~isempty(src)
        cfg.src_path_template = src;
    end

    p_out = char(p_out_signal);
    if ~isempty(p_out)
        cfg.p_out_signal = p_out;
    end
end
