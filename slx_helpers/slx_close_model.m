function slx_close_model(model_name)
%SLX_CLOSE_MODEL Close a loaded model without saving.

    mdl = char(model_name);
    if bdIsLoaded(mdl)
        try
            set_param(mdl, 'FastRestart', 'off');
        catch
        end
        close_system(mdl, 0);
    end
end
