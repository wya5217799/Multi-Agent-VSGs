%% run_gentpj_test.m — Run GENTPJ minimal test and save results to file
mdl = 'test_gentpj_min';
cd('C:\Users\27443\Desktop\Multi-Agent  VSGs\scenarios\kundur');

if ~bdIsLoaded(mdl), load_system(mdl); end

fprintf('[%s] Starting simulation...\n', datestr(now, 'HH:MM:SS'));
tic;
try
    out = sim(mdl, 'StopTime', '3');
    elapsed = toc;
    fprintf('[%s] Done in %.1fs\n', datestr(now, 'HH:MM:SS'), elapsed);

    result.success = true;
    result.elapsed = elapsed;

    simlog = out.simlog;
    fn = fieldnames(simlog);
    result.simlog_fields = fn;
    fprintf('Simlog fields: %s\n', strjoin(fn, ', '));

    % Try to read frequency data
    try
        w = simlog.Inertia.w.series;
        result.inertia_w = w.values;
        result.inertia_t = w.time;
        dw = w.values - 2*pi*60;
        result.delta_f_min = min(dw)/(2*pi);
        result.delta_f_max = max(dw)/(2*pi);
        fprintf('Δf: [%.4f, %.4f] Hz\n', result.delta_f_min, result.delta_f_max);
    catch e
        fprintf('No Inertia.w: %s\n', e.message);
        result.inertia_error = e.message;
    end

    % Try G1.omegaDel
    try
        od = simlog.G1.omegaDel.series;
        result.omegaDel = od.values;
        result.omegaDel_t = od.time;
        fprintf('G1.omegaDel: [%.6f, %.6f]\n', min(od.values), max(od.values));
    catch; end

catch e
    elapsed = toc;
    fprintf('[%s] FAILED after %.1fs: %s\n', datestr(now, 'HH:MM:SS'), elapsed, e.message);
    result.success = false;
    result.error = e.message;
    result.elapsed = elapsed;
end

% Save results
save('gentpj_test_result.mat', 'result');
fprintf('Results saved to gentpj_test_result.mat\n');
exit;
