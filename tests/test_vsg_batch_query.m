%TEST_VSG_BATCH_QUERY  Unit tests for slx_batch_query.
% Run from project root: results = runtests('tests/test_slx_batch_query.m')

function tests = test_slx_batch_query
    tests = functiontests(localfunctions);
end

function test_returns_struct_array(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    blocks = {'vdp/Mu'};
    result = slx_batch_query('vdp', blocks);
    tc.verifyClass(result, 'struct');
    tc.verifyEqual(numel(result), 1);
end

function test_block_field_populated(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    result = slx_batch_query('vdp', {'vdp/Mu'});
    tc.verifyEqual(result(1).block, 'vdp/Mu');
end

function test_params_is_struct(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    result = slx_batch_query('vdp', {'vdp/Mu'});
    tc.verifyClass(result(1).params, 'struct');
end

function test_multiple_blocks(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    blocks = {'vdp/Mu', 'vdp/Van der Pol Equation'};
    result = slx_batch_query('vdp', blocks);
    tc.verifyEqual(numel(result), 2);
    tc.verifyEqual(result(1).block, 'vdp/Mu');
    tc.verifyEqual(result(2).block, 'vdp/Van der Pol Equation');
end

function test_invalid_block_sets_error(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    result = slx_batch_query('vdp', {'vdp/NonExistentBlock'});
    tc.verifyNotEmpty(result(1).error);
    tc.verifyEmpty(fieldnames(result(1).params));
end

function test_empty_block_list(tc)
    load_system('vdp');
    tc.addTeardown(@() close_system('vdp', 0));
    result = slx_batch_query('vdp', {});
    tc.verifyEqual(numel(result), 0);
end
