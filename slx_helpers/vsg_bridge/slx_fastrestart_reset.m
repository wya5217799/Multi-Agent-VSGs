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
%   Uses slx_runtime_reset for FastRestart management.
%   Uses direct set_param+sim() for the warmup sim — NOT slx_run_window.
%   Simulink.SimulationInput (used inside slx_run_window) is incompatible
%   with FastRestart warm-restart stepping in R2022b+.

    if nargin < 3, do_recompile = true; end
    model_name = char(model_name);

    if logical(do_recompile)
        slx_runtime_reset(model_name, 'off', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
        slx_runtime_reset(model_name, 'on', false, '');
    else
        slx_runtime_reset(model_name, '', true, '^(omega|delta|Vabc|Iabc)_ES\d+$');
    end

    set_param(model_name, 'StopTime', num2str(double(duration), '%.6f'));
    sim(model_name);
    fprintf('RESULT: slx_fastrestart_reset done, t_warmup=%.3f s, recompile=%d\n', ...
            double(duration), logical(do_recompile));
end
