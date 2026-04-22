function [state, status] = slx_warmup(model_name, agent_ids_or_duration, sbase_va, cfg, init_params, do_recompile)
%SLX_WARMUP  Compatibility wrapper — delegates to slx_fastrestart_reset or slx_episode_warmup.
%
% Kundur (2-arg) mode:
%   slx_warmup(model_name, duration)
%
% Kundur (3-arg) mode:
%   slx_warmup(model_name, duration, do_recompile)
%
% NE39 (5-arg or 6-arg) mode:
%   [state, status] = slx_warmup(model_name, agent_ids, sbase_va, cfg, init_params)
%   [state, status] = slx_warmup(model_name, agent_ids, sbase_va, cfg, init_params, do_recompile)

    if nargin == 2
        duration = agent_ids_or_duration;
        slx_fastrestart_reset(model_name, duration, true);
        state  = [];
        status = [];
        return;
    end

    if nargin == 3
        duration     = agent_ids_or_duration;
        do_recompile = logical(sbase_va);
        slx_fastrestart_reset(model_name, duration, do_recompile);
        state  = [];
        status = [];
        return;
    end

    if nargin < 6, do_recompile = true; end
    [state, status] = slx_episode_warmup( ...
        model_name, agent_ids_or_duration, sbase_va, cfg, init_params, do_recompile);
end
