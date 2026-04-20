%TEST_VSG_RUN_QUIET  Unit tests for slx_run_quiet.
% Run from project root: results = runtests('tests/test_slx_run_quiet.m')

function tests = test_slx_run_quiet
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    % Ensure slx_helpers is on the path regardless of working directory.
    project_root = fileparts(fileparts(mfilename('fullpath')));
    helpers_dir  = fullfile(project_root, 'slx_helpers');
    addpath(helpers_dir);
    tc.addTeardown(@() rmpath(helpers_dir));
end

% ---------------------------------------------------------------------------
% Helpers
% ---------------------------------------------------------------------------

function tmp = write_temp_script(tc, lines)
    % Write a cell array of lines to a temporary .m file and register cleanup.
    tmp = [tempname, '.m'];
    fid = fopen(tmp, 'w');
    tc.assertTrue(fid ~= -1, 'Could not create temp script');
    for k = 1:numel(lines)
        fprintf(fid, '%s\n', lines{k});
    end
    fclose(fid);
    tc.addTeardown(@() delete_if_exists(tmp));
end

function delete_if_exists(path)
    if exist(path, 'file')
        delete(path);
    end
end

% ---------------------------------------------------------------------------
% Basic contract tests
% ---------------------------------------------------------------------------

function test_ok_field_true_for_clean_code(tc)
    result = slx_run_quiet("x = 1 + 1;");
    tc.verifyTrue(result.ok);
end

function test_ok_field_false_for_erroring_code(tc)
    result = slx_run_quiet("error('intentional test error');");
    tc.verifyFalse(result.ok);
    tc.verifyNotEmpty(result.error_message);
end

function test_error_message_captured(tc)
    result = slx_run_quiet("error('sentinel_error_xyz');");
    tc.verifySubstring(result.error_message, 'sentinel_error_xyz');
end

function test_elapsed_is_positive(tc)
    result = slx_run_quiet("pause(0);");
    tc.verifyGreaterThan(result.elapsed, 0);
end

% ---------------------------------------------------------------------------
% Regression: clear all inside evalc must not surface as a failure
% ---------------------------------------------------------------------------

function test_clear_all_in_script_does_not_mask_success(tc)
    % Bug: build scripts call 'clear all', which deletes caught_error from
    % i_run_target's workspace.  After the fix, slx_run_quiet must still
    % report ok=true when the script itself completes without error.
    tmp = write_temp_script(tc, {
        'clear all; close all; clc;'
        'x = 42;'   % trivial work after the clear
    });
    result = slx_run_quiet(tmp);
    tc.verifyTrue(result.ok, ...
        sprintf('Expected ok=true but got error: %s', result.error_message));
end

function test_clear_all_in_script_zero_errors(tc)
    tmp = write_temp_script(tc, {
        'clear all;'
        'disp(''done'');'
    });
    result = slx_run_quiet(tmp);
    tc.verifyEqual(result.n_errors, 0);
end

function test_clear_all_followed_by_error_still_reports_failure(tc)
    % Even after clear all, a subsequent error must still be caught.
    tmp = write_temp_script(tc, {
        'clear all;'
        'error(''post_clear_error_xyz'');'
    });
    result = slx_run_quiet(tmp);
    tc.verifyFalse(result.ok);
    tc.verifySubstring(result.error_message, 'post_clear_error_xyz');
end
