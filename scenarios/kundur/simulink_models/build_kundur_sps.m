function build_kundur_sps(varargin)
% build_kundur_sps  Rebuild kundur_vsg_sps.slx from scratch.
%
% USAGE CONTRACT
% --------------
% This is the REBUILD ARTIFACT for the kundur_vsg_sps.slx skeleton.
% The MCP-first sequence (simulink_create_model + simulink_add_block +
% simulink_set_block_params) was validated first; this script is the
% canonical serialised replay of that proven sequence.
%
% NOT a first-implementation path.  Edit this file only after the
% MCP-verified sequence passes simulink_compile_diagnostics.
%
% Run via:
%   run('scenarios/kundur/simulink_models/build_kundur_sps.m')
%   OR
%   build_kundur_sps()         % from MATLAB prompt with project on path
%
% Acceptance: compile + update must succeed with no errors.
%
% SPS Candidate profile invariants (kundur_sps_candidate.json):
%   solver.family          = sps_phasor
%   solver.has_solver_config = false
%   initialization.uses_pref_ramp = false
%   initialization.warmup_mode    = technical_reset_only
%   measurement.mode              = vi (wired in later Tasks 7+)
%
% At this skeleton stage only the root solver layer is placed.
% Electrical sources, network, measurements, VSG control, and
% disturbance subsystems are ported in Task 7 manifest-sized batches.

    mdl = 'kundur_vsg_sps';
    out_dir = fileparts(mfilename('fullpath'));
    out_path = fullfile(out_dir, [mdl '.slx']);

    % Close any stale copy in memory
    if bdIsLoaded(mdl)
        close_system(mdl, 0);
    end

    % ------------------------------------------------------------------
    % BATCH 1: Root solver layer  (SPS phasor, 50 Hz, 100 MVA)
    % ------------------------------------------------------------------
    new_system(mdl);
    load_system('powerlib');

    % powergui — phasor mode, 50 Hz, 100 MVA base
    add_block('powerlib/powergui', [mdl '/powergui'], ...
        'Position', [20 20 120 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
    set_param([mdl '/powergui'], 'frequency', '50');
    set_param([mdl '/powergui'], 'Pbase', '100e6');

    % Solver settings: variable-step ode23t, 100 ms default run
    set_param(mdl, 'StopTime',   '0.1');
    set_param(mdl, 'SolverType', 'Variable-step');
    set_param(mdl, 'Solver',     'ode23t');
    set_param(mdl, 'MaxStep',    '0.001');

    % No SolverConfig block (simscape_ee path only).
    % Invariant: solver.has_solver_config = false

    % ------------------------------------------------------------------
    % Save
    % ------------------------------------------------------------------
    save_system(mdl, out_path);
    fprintf('[build_kundur_sps] saved: %s\n', out_path);

    % ------------------------------------------------------------------
    % Structural check (Batch 1 sanity — no executable blocks yet)
    % A skeleton with only powergui cannot pass SimulationCommand:update
    % (all-virtual-block error is expected).  Instead verify the block
    % tree contains powergui with Phasor mode and no SolverConfig.
    % ------------------------------------------------------------------
    gui_hits = find_system(mdl, 'SearchDepth', 1, 'Name', 'powergui');
    if isempty(gui_hits)
        error('[build_kundur_sps] powergui block missing after save');
    end
    gui_mode = get_param(gui_hits{1}, 'SimulationMode');
    if ~strcmpi(gui_mode, 'Phasor')
        error('[build_kundur_sps] powergui not in Phasor mode (got %s)', gui_mode);
    end
    sc_hits = find_system(mdl, 'SearchDepth', 1, 'Name', 'SolverConfig');
    if ~isempty(sc_hits)
        error('[build_kundur_sps] SolverConfig found — must not exist in SPS skeleton');
    end
    fprintf('[build_kundur_sps] structural check OK — powergui=Phasor, no SolverConfig\n');

    close_system(mdl, 0);
    fprintf('[build_kundur_sps] done\n');
end
