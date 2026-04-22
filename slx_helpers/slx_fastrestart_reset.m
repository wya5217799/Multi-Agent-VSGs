function slx_fastrestart_reset(model_name, duration, do_recompile)
%SLX_FASTRESTART_RESET  Kundur-mode FastRestart warmup reset.
%
%   slx_fastrestart_reset(model_name, duration, do_recompile)
%
%   do_recompile=true  (first episode):
%     Sets FastRestart off (clears SDI and workspace), then re-enables on,
%     and runs a warmup simulation window.
%
%   do_recompile=false (subsequent episodes):
%     Keeps FastRestart on; clears SDI and workspace only.
%     sim() restarts from t=0 automatically when StopTime < current sim time.
%
%   Uses slx_runtime_reset and slx_run_window general primitives.

    if nargin < 3, do_recompile = true; end
    model_name = char(model_name);

    if logical(do_recompile)
        slx_runtime_reset(model_name, 'off', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
        slx_runtime_reset(model_name, 'on', false, '');
    else
        slx_runtime_reset(model_name, '', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
    end

    run_result = slx_run_window(model_name, 0.0, double(duration), true);
    if ~run_result.ok
        error('slx_fastrestart_reset: warmup sim failed: %s', run_result.error_message);
    end

    fprintf('RESULT: slx_fastrestart_reset done, t_warmup=%.3f s, recompile=%d\n', ...
            double(duration), logical(do_recompile));
end
