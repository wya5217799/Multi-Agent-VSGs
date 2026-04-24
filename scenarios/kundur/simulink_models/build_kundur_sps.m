function build_kundur_sps(varargin)
% build_kundur_sps  Rebuild kundur_vsg_sps.slx — full SPS/Phasor electrical layer.
%
% Task 7 of kundur-sps-phasor-migration-v4:
%   Port complete electrical layer from ee_lib to SPS/Phasor in manifest-sized batches.
%
% SPS candidate profile invariants (kundur_sps_candidate.json):
%   solver_family          = sps_phasor
%   has_solver_config      = false       (no SolverConfig block)
%   uses_pref_ramp         = false       (no PrefRamp_* / PrefSat_* blocks)
%   warmup_mode            = technical_reset_only
%   pe_measurement         = vi          (Vabc/Iabc ToWorkspace, Pe computed in bridge)
%
% Workspace variable protocol (bridge writes before each sim() call):
%   phAng_ES{i}   — Three-Phase Source phase angle (degrees)
%   Pe_ES{i}      — Pe feedback to VSG swing eq (VSG-base pu)
%   M0_val_ES{i}  — M0+action for VSG M constant
%   D0_val_ES{i}  — D0+action for VSG D constant
%
% Signals logged to workspace (read by slx_extract_state.m):
%   omega_ES{i}   — VSG angular frequency (pu)
%   delta_ES{i}   — VSG rotor angle (rad)
%   Vabc_ES{i}    — three-phase voltages (timeseries)
%   Iabc_ES{i}    — three-phase currents (timeseries)

    %% ================================================================
    %  Parameters
    %% ================================================================
    fn    = 50;
    Sbase = 100e6;
    Vbase = 230e3;
    Zbase = Vbase^2 / Sbase;   % 529 Ohm

    VSG_SN    = 200e6;
    VSG_M0    = 12.0;           % 2*H, H=6.0 s
    VSG_D0    = 3.0;
    R_vsg_pu  = 0.003 * (Sbase / VSG_SN);
    X_vsg_pu  = 0.30  * (Sbase / VSG_SN);
    R_vsg     = R_vsg_pu * Zbase;
    L_vsg     = X_vsg_pu * Zbase / (2*pi*fn);

    R_gen_pu  = 0.003 * (Sbase / 900e6);
    X_gen_pu  = 0.30  * (Sbase / 900e6);
    R_gen     = R_gen_pu * Zbase;
    L_gen     = X_gen_pu * Zbase / (2*pi*fn);

    R_std    = 0.053;    % Ohm/km
    L_std    = 1.41e-3;  % H/km
    R_short  = 0.01;
    L_short  = 0.5e-3;

    % ESS bus assignments
    ess_bus  = [12, 16, 14, 15];   % ES1..ES4 dedicated buses
    ess_main = [ 7,  8, 10,  9];   % ES1..ES4 main buses (for reference)

    % Load ICs from kundur_ic.json (powerflow delta0 + VSG P0)
    build_dir    = fileparts(mfilename('fullpath'));
    scenario_dir = fileparts(build_dir);
    ic_path      = fullfile(scenario_dir, 'kundur_ic.json');
    ic_raw       = fileread(ic_path);
    ic           = jsondecode(ic_raw);
    VSG_P0          = ic.vsg_p0_vsg_base_pu(:)';    % 1×4 VSG-base pu
    ess_delta0_deg  = ic.vsg_delta0_deg(:)';         % 1×4 degrees

    % Source angles for conventional gens and wind farms.
    % Using EMF angles from previous power flow run (stored in ic JSON if present,
    % otherwise fall back to reasonable approximations).
    % These are fixed-angle sources so accuracy determines initial Pe.
    vlf_gen  = [1.03, 25.0;   % G1 Bus1
                1.01, 22.0;   % G2 Bus2
                1.01, -5.0];  % G3 Bus3
    vlf_wind = [1.00, 15.0;   % W1 Bus4
                1.00, -20.0]; % W2 Bus11

    % Try to use powerflow angles from ic.json if available
    if isfield(ic, 'gen_emf_deg') && numel(ic.gen_emf_deg) >= 3
        vlf_gen(1,2) = ic.gen_emf_deg(1);
        vlf_gen(2,2) = ic.gen_emf_deg(2);
        vlf_gen(3,2) = ic.gen_emf_deg(3);
    end
    if isfield(ic, 'wind_emf_deg') && numel(ic.wind_emf_deg) >= 2
        vlf_wind(1,2) = ic.wind_emf_deg(1);
        vlf_wind(2,2) = ic.wind_emf_deg(2);
    end

    %% ================================================================
    %  Model setup
    %% ================================================================
    mdl      = 'kundur_vsg_sps';
    out_path = fullfile(build_dir, [mdl '.slx']);

    if bdIsLoaded(mdl), close_system(mdl, 0); end
    new_system(mdl);
    load_system('powerlib');

    bus_nodes = cell(1, 20);   % bus_nodes{k} = {blk_name, port_tmpl} or []

    fprintf('[build_kundur_sps] Starting full electrical layer build...\n');

    %% ================================================================
    %  BATCH 0: powergui — Phasor 50 Hz 100 MVA
    %% ================================================================
    add_block('powerlib/powergui', [mdl '/powergui'], 'Position', [20 20 120 60]);
    set_param([mdl '/powergui'], 'SimulationMode', 'Phasor');
    set_param([mdl '/powergui'], 'frequency', num2str(fn));
    set_param([mdl '/powergui'], 'Pbase', num2str(Sbase));
    set_param(mdl, 'StopTime', '0.1', 'SolverType', 'Variable-step', ...
        'Solver', 'ode23t', 'MaxStep', '0.001');
    fprintf('[build_kundur_sps] Batch 0: powergui Phasor done\n');

    %% ================================================================
    %  BATCH 1: VSG sources (Three-Phase Source) + V-I Measurement + loggers
    %           ES1..ES4 on their dedicated buses (12, 16, 14, 15)
    %% ================================================================
    for i = 1:4
        bx = 150 + (i-1)*750;
        by = 120;

        src_name  = sprintf('VSrc_ES%d', i);
        meas_name = sprintf('Meas_ES%d', i);

        % Three-Phase Source: PhaseAngle = workspace variable
        add_block('powerlib/Electrical Sources/Three-Phase Source', ...
            [mdl '/' src_name], 'Position', [bx by bx+80 by+60]);
        set_param([mdl '/' src_name], 'Voltage',            num2str(Vbase));
        set_param([mdl '/' src_name], 'PhaseAngle',         sprintf('phAng_ES%d', i));
        set_param([mdl '/' src_name], 'Frequency',          num2str(fn));
        set_param([mdl '/' src_name], 'InternalConnection', 'Yg');
        set_param([mdl '/' src_name], 'NonIdealSource',     'on');
        set_param([mdl '/' src_name], 'SpecifyImpedance',   'on');
        set_param([mdl '/' src_name], 'Resistance',         num2str(R_vsg));
        set_param([mdl '/' src_name], 'Inductance',         num2str(L_vsg));

        assignin('base', sprintf('phAng_ES%d', i), ess_delta0_deg(i));

        % Three-Phase V-I Measurement
        add_block('powerlib/Measurements/Three-Phase V-I Measurement', ...
            [mdl '/' meas_name], 'Position', [bx+120 by bx+200 by+60]);
        set_param([mdl '/' meas_name], 'VoltageMeasurement', 'phase-to-ground');
        set_param([mdl '/' meas_name], 'CurrentMeasurement', 'yes');

        % Source → Measurement (3 separate phase connections)
        add_line(mdl, [src_name '/RConn1'], [meas_name '/LConn1'], 'autorouting', 'smart');
        add_line(mdl, [src_name '/RConn2'], [meas_name '/LConn2'], 'autorouting', 'smart');
        add_line(mdl, [src_name '/RConn3'], [meas_name '/LConn3'], 'autorouting', 'smart');

        % Register Meas output (RConn) as bus representative for ess_bus(i)
        bus_nodes = do_wire_sps(mdl, bus_nodes, ess_bus(i), meas_name, '%s/RConn%d');

        % ToWorkspace: Vabc_ES{i} (port 1), Iabc_ES{i} (port 2)
        log_v = sprintf('Log_Vabc_ES%d', i);
        log_i = sprintf('Log_Iabc_ES%d', i);
        add_block('simulink/Sinks/To Workspace', [mdl '/' log_v], ...
            'Position', [bx+220 by bx+290 by+22], ...
            'VariableName', sprintf('Vabc_ES%d', i), 'SaveFormat', 'Timeseries');
        add_block('simulink/Sinks/To Workspace', [mdl '/' log_i], ...
            'Position', [bx+220 by+28 bx+290 by+50], ...
            'VariableName', sprintf('Iabc_ES%d', i), 'SaveFormat', 'Timeseries');
        add_line(mdl, [meas_name '/1'], [log_v '/1'], 'autorouting', 'smart');
        add_line(mdl, [meas_name '/2'], [log_i '/1'], 'autorouting', 'smart');
    end
    fprintf('[build_kundur_sps] Batch 1: VSrc+Meas+loggers done (4 ESS)\n');

    %% ================================================================
    %  BATCH 2: VSG control subsystems (copied from kundur_vsg)
    %           + workspace-variable inputs + omega/delta loggers
    %% ================================================================
    % The VSG subsystem is a pure-Simulink swing equation.
    % Pe feedback comes from workspace variable Pe_ES{i} (set by bridge).
    % delta output logged to workspace (read by bridge → phAng update).
    % No PrefRamp: P_ref is a constant (allow_pref_ramp=false per profile).
    legacy_mdl  = 'kundur_vsg';
    legacy_path = fullfile(build_dir, [legacy_mdl '.slx']);

    already_loaded = bdIsLoaded(legacy_mdl);
    if ~already_loaded
        load_system(legacy_path);
    end

    for i = 1:4
        bx = 150 + (i-1)*750;
        by = 330;

        vsg_name = sprintf('VSG_ES%d', i);
        src_blk  = [legacy_mdl '/' vsg_name];
        dst_blk  = [mdl '/' vsg_name];

        % Copy entire subsystem (preserves M0/D0 workspace var references internally)
        add_block(src_blk, dst_blk, 'Position', [bx by bx+130 by+110]);

        % Port 1: omega_ref = 1.0
        cname = sprintf('wref_ES%d', i);
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [bx-130 by bx-70 by+18], 'Value', '1.0');
        add_line(mdl, [cname '/1'], sprintf('%s/1', vsg_name), 'autorouting', 'smart');

        % Port 2: delta_M = 0 (bridge action already incorporated in M0_val_ES{i})
        cname = sprintf('dM_ES%d', i);
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [bx-130 by+22 bx-70 by+40], 'Value', '0');
        add_line(mdl, [cname '/1'], sprintf('%s/2', vsg_name), 'autorouting', 'smart');

        % Port 3: delta_D = 0
        cname = sprintf('dD_ES%d', i);
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [bx-130 by+44 bx-70 by+62], 'Value', '0');
        add_line(mdl, [cname '/1'], sprintf('%s/3', vsg_name), 'autorouting', 'smart');

        % Port 4: P_ref = nominal (constant, no ramp — profile: allow_pref_ramp=false)
        cname = sprintf('Pref_ES%d', i);
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [bx-130 by+66 bx-70 by+84], 'Value', num2str(VSG_P0(i)));
        add_line(mdl, [cname '/1'], sprintf('%s/4', vsg_name), 'autorouting', 'smart');

        % Port 5: P_e from workspace variable (bridge writes Pe_ES{i} each step)
        cname = sprintf('Pe_cst_ES%d', i);
        add_block('built-in/Constant', [mdl '/' cname], ...
            'Position', [bx-130 by+88 bx-70 by+106], ...
            'Value', sprintf('Pe_ES%d', i));
        add_line(mdl, [cname '/1'], sprintf('%s/5', vsg_name), 'autorouting', 'smart');

        % Initialize workspace variables
        assignin('base', sprintf('Pe_ES%d',      i), VSG_P0(i));
        assignin('base', sprintf('M0_val_ES%d',  i), VSG_M0);
        assignin('base', sprintf('D0_val_ES%d',  i), VSG_D0);

        % ToWorkspace: omega_ES{i} (port 1), delta_ES{i} (port 2)
        for k = 1:2
            sig_names = {'omega', 'delta'};
            log_name  = sprintf('Log_%s_ES%d', sig_names{k}, i);
            lx = bx + 150;
            ly = by + (k-1)*30;
            add_block('simulink/Sinks/To Workspace', [mdl '/' log_name], ...
                'Position', [lx ly lx+70 ly+20], ...
                'VariableName', sprintf('%s_ES%d', sig_names{k}, i), ...
                'SaveFormat', 'Timeseries');
            add_line(mdl, sprintf('%s/%d', vsg_name, k), [log_name '/1'], ...
                'autorouting', 'smart');
        end
    end

    if ~already_loaded
        close_system(legacy_mdl, 0);
    end
    fprintf('[build_kundur_sps] Batch 2: VSG control subsystems done (4 ESS)\n');

    %% ================================================================
    %  BATCH 3: Conventional generators G1-G3 and wind farms W1, W2
    %           Fixed-angle Three-Phase Sources (no swing equation in SPS model)
    %% ================================================================
    gen_cfg = struct( ...
        'name',  {'GSrc_G1', 'GSrc_G2', 'GSrc_G3'}, ...
        'bus',   {1, 2, 3}, ...
        'V_pu',  {vlf_gen(1,1),  vlf_gen(2,1),  vlf_gen(3,1)}, ...
        'ang',   {vlf_gen(1,2),  vlf_gen(2,2),  vlf_gen(3,2)}, ...
        'R',     {R_gen, R_gen, R_gen}, ...
        'L',     {L_gen, L_gen, L_gen});

    wind_cfg = struct( ...
        'name',  {'WSrc_W1', 'WSrc_W2'}, ...
        'bus',   {4, 11}, ...
        'V_pu',  {vlf_wind(1,1),  vlf_wind(2,1)}, ...
        'ang',   {vlf_wind(1,2),  vlf_wind(2,2)}, ...
        'R',     {R_gen, R_gen}, ...
        'L',     {L_gen, L_gen});

    all_src_cfg = [gen_cfg, wind_cfg];

    for si = 1:length(all_src_cfg)
        s    = all_src_cfg(si);
        bx   = 150 + (si-1)*650;
        by   = 700;
        sblk = [mdl '/' s.name];

        add_block('powerlib/Electrical Sources/Three-Phase Source', ...
            sblk, 'Position', [bx by bx+80 by+60]);
        set_param(sblk, 'Voltage',            num2str(Vbase * s.V_pu));
        set_param(sblk, 'PhaseAngle',         num2str(s.ang));
        set_param(sblk, 'Frequency',          num2str(fn));
        set_param(sblk, 'InternalConnection', 'Yg');
        set_param(sblk, 'NonIdealSource',     'on');
        set_param(sblk, 'SpecifyImpedance',   'on');
        set_param(sblk, 'Resistance',         num2str(s.R));
        set_param(sblk, 'Inductance',         num2str(s.L));

        bus_nodes = do_wire_sps(mdl, bus_nodes, s.bus, s.name, '%s/RConn%d');
    end
    fprintf('[build_kundur_sps] Batch 3: Conv gens G1-G3 and wind W1-W2 done\n');

    %% ================================================================
    %  BATCH 4: Transmission lines (Three-Phase Series RLC Branch, RL only)
    %           20 lines matching build_powerlib_kundur.m topology
    %% ================================================================
    line_defs = {
        'L_1_5',    1,  5,   5, R_std,   L_std;
        'L_2_6',    2,  6,   5, R_std,   L_std;
        'L_3_10',   3, 10,   5, R_std,   L_std;
        'L_4_9',    4,  9,   5, R_std,   L_std;
        'L_5_6a',   5,  6,  25, R_std,   L_std;
        'L_5_6b',   5,  6,  25, R_std,   L_std;
        'L_6_7a',   6,  7,  10, R_std,   L_std;
        'L_6_7b',   6,  7,  10, R_std,   L_std;
        'L_7_8a',   7,  8, 110, R_std,   L_std;
        'L_7_8b',   7,  8, 110, R_std,   L_std;
        'L_7_8c',   7,  8, 110, R_std,   L_std;
        'L_8_9a',   8,  9,  10, R_std,   L_std;
        'L_8_9b',   8,  9,  10, R_std,   L_std;
        'L_9_10a',  9, 10,  25, R_std,   L_std;
        'L_9_10b',  9, 10,  25, R_std,   L_std;
        'L_7_12',   7, 12,   1, R_short, L_short;
        'L_8_16',   8, 16,   1, R_short, L_short;
        'L_10_14', 10, 14,   1, R_short, L_short;
        'L_9_15',   9, 15,   1, R_short, L_short;
        'L_8_W2',   8, 11,   1, R_short, L_short;
    };

    n_lines = size(line_defs, 1);
    for li = 1:n_lines
        lname    = line_defs{li, 1};
        from_bus = line_defs{li, 2};
        to_bus   = line_defs{li, 3};
        len_km   = line_defs{li, 4};
        R_km     = line_defs{li, 5};
        L_km     = line_defs{li, 6};

        lx = 150 + mod(li-1, 5) * 380;
        ly = 1100 + floor((li-1)/5) * 130;

        lpath = [mdl '/' lname];
        add_block('powerlib/Elements/Three-Phase Series RLC Branch', ...
            lpath, 'Position', [lx ly lx+80 ly+50]);
        set_param(lpath, 'BranchType',  'RL');
        set_param(lpath, 'Resistance',  num2str(R_km * len_km));
        set_param(lpath, 'Inductance',  num2str(L_km * len_km));

        % LConn1/2/3 = from_bus side, RConn1/2/3 = to_bus side
        bus_nodes = do_wire_sps(mdl, bus_nodes, from_bus, lname, '%s/LConn%d');
        bus_nodes = do_wire_sps(mdl, bus_nodes, to_bus,   lname, '%s/RConn%d');
    end
    fprintf('[build_kundur_sps] Batch 4: %d transmission lines done\n', n_lines);

    %% ================================================================
    %  BATCH 5: Loads and shunt capacitors (Three-Phase Parallel RLC Load)
    %% ================================================================
    % Constant loads
    load_defs = {
        'Load7', 7, 967e6,  100e6;
        'Load9', 9, 1767e6, 100e6;
    };
    for li = 1:size(load_defs, 1)
        lname = load_defs{li, 1};
        lbus  = load_defs{li, 2};
        P_W   = load_defs{li, 3};
        Q_W   = load_defs{li, 4};
        lx    = 150 + (li-1)*450;
        ly    = 1760;

        lpath = [mdl '/' lname];
        add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
            lpath, 'Position', [lx ly lx+80 ly+60]);
        set_param(lpath, 'NominalVoltage',   num2str(Vbase));
        set_param(lpath, 'NominalFrequency', num2str(fn));
        set_param(lpath, 'ActivePower',      num2str(P_W));
        set_param(lpath, 'InductivePower',   num2str(Q_W));
        set_param(lpath, 'CapacitivePower',  '0');

        bus_nodes = do_wire_sps(mdl, bus_nodes, lbus, lname, '%s/LConn%d');
    end

    % Shunt capacitors (capacitive reactive power — negative InductivePower or positive CapacitivePower)
    shunt_defs = {
        'Shunt7', 7, 200e6;
        'Shunt9', 9, 350e6;
    };
    for si = 1:size(shunt_defs, 1)
        sname = shunt_defs{si, 1};
        sbus  = shunt_defs{si, 2};
        Q_W   = shunt_defs{si, 3};
        sx    = 650 + (si-1)*450;
        sy    = 1760;

        spath = [mdl '/' sname];
        add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
            spath, 'Position', [sx sy sx+80 sy+60]);
        set_param(spath, 'NominalVoltage',   num2str(Vbase));
        set_param(spath, 'NominalFrequency', num2str(fn));
        set_param(spath, 'ActivePower',      '0');
        set_param(spath, 'InductivePower',   '0');
        set_param(spath, 'CapacitivePower',  num2str(Q_W));

        bus_nodes = do_wire_sps(mdl, bus_nodes, sbus, sname, '%s/LConn%d');
    end
    fprintf('[build_kundur_sps] Batch 5: loads and shunts done\n');

    %% ================================================================
    %  BATCH 6: Disturbance loads (workspace-variable ActivePower)
    %           TripLoad1 at Bus14 (ES3 bus), TripLoad2 at Bus15 (ES4 bus)
    %           Python bridge sets TripLoad{i}_P per-phase watts via assignin.
    %           Three-Phase Parallel RLC Load distributes equally across phases,
    %           so ActivePower = total 3-phase watts = var * 3.
    %% ================================================================
    trip_defs = {
        'TripLoad1', 14, 'TripLoad1_P', 248e6;
        'TripLoad2', 15, 'TripLoad2_P', 1.0;   % 1 W (not 0 — block mask rejects all-zero params)
    };
    for ti = 1:size(trip_defs, 1)
        tname = trip_defs{ti, 1};
        tbus  = trip_defs{ti, 2};
        tvar  = trip_defs{ti, 3};
        tdef  = trip_defs{ti, 4};
        tx    = 150 + (ti-1)*500;
        ty    = 1940;

        assignin('base', tvar, tdef);

        tpath = [mdl '/' tname];
        add_block('powerlib/Elements/Three-Phase Parallel RLC Load', ...
            tpath, 'Position', [tx ty tx+80 ty+60]);
        set_param(tpath, 'NominalVoltage',   num2str(Vbase));
        set_param(tpath, 'NominalFrequency', num2str(fn));
        set_param(tpath, 'ActivePower',      tvar);   % workspace variable reference
        set_param(tpath, 'InductivePower',   '0');
        set_param(tpath, 'CapacitivePower',  '1');   % 1 VAR floor so block is valid when P=0

        bus_nodes = do_wire_sps(mdl, bus_nodes, tbus, tname, '%s/LConn%d');
    end
    fprintf('[build_kundur_sps] Batch 6: TripLoad1/2 disturbance loads done\n');

    %% ================================================================
    %  Clock + time logger
    %% ================================================================
    add_block('built-in/Clock', [mdl '/Clock'], 'Position', [20 80 50 100]);
    add_block('simulink/Sinks/To Workspace', [mdl '/Log_time'], ...
        'Position', [80 80 150 100], ...
        'VariableName', 'sim_time', 'SaveFormat', 'Timeseries');
    add_line(mdl, 'Clock/1', 'Log_time/1');

    %% ================================================================
    %  Save
    %% ================================================================
    save_system(mdl, out_path);
    fprintf('[build_kundur_sps] saved → %s\n', out_path);

    %% ================================================================
    %  Structural validation
    %% ================================================================
    % 1. powergui must be Phasor
    gui_mode = get_param([mdl '/powergui'], 'SimulationMode');
    if ~strcmpi(gui_mode, 'Phasor')
        error('[build_kundur_sps] FAIL: powergui mode = %s (expected Phasor)', gui_mode);
    end

    % 2. No SolverConfig (Simscape ee_lib only)
    sc_hits = find_system(mdl, 'SearchDepth', 1, 'BlockType', 'SubSystem', ...
        'Name', 'SolverConfig');
    if ~isempty(sc_hits)
        error('[build_kundur_sps] FAIL: SolverConfig block found');
    end

    % 3. No PrefRamp_* blocks (allow_pref_ramp=false)
    pr_hits = find_system(mdl, 'SearchDepth', 1, 'RegExp', 'on', 'Name', 'PrefRamp.*');
    if ~isempty(pr_hits)
        error('[build_kundur_sps] FAIL: PrefRamp block found: %s', pr_hits{1});
    end

    % 4. All 4 VSrc sources present
    for i = 1:4
        h = find_system(mdl, 'SearchDepth', 1, 'Name', sprintf('VSrc_ES%d', i));
        if isempty(h)
            error('[build_kundur_sps] FAIL: VSrc_ES%d missing', i);
        end
    end

    % 5. All 4 VSG subsystems present
    for i = 1:4
        h = find_system(mdl, 'SearchDepth', 1, 'Name', sprintf('VSG_ES%d', i));
        if isempty(h)
            error('[build_kundur_sps] FAIL: VSG_ES%d missing', i);
        end
    end

    % 6. All 20 transmission lines present
    for li = 1:size(line_defs, 1)
        h = find_system(mdl, 'SearchDepth', 1, 'Name', line_defs{li, 1});
        if isempty(h)
            error('[build_kundur_sps] FAIL: line %s missing', line_defs{li, 1});
        end
    end

    fprintf('[build_kundur_sps] structural check OK — powergui=Phasor, no SolverConfig, no PrefRamp\n');
    fprintf('[build_kundur_sps]   VSrc×4, VSG×4, lines×%d, loads×%d, shunts×2, trips×2\n', ...
        n_lines, size(load_defs,1));

    close_system(mdl, 0);
    fprintf('[build_kundur_sps] done\n');
end

%% ================================================================
%  Local helper: do_wire_sps
%% ================================================================
function bus_nodes = do_wire_sps(mdl, bus_nodes, bus_id, blk_name, port_tmpl)
% DO_WIRE_SPS  Connect a block to a bus node (SPS 3-separate-phase ports).
%
%   port_tmpl:  sprintf-style template with two %s/%d placeholders:
%               e.g. '%s/RConn%d' or '%s/LConn%d'
%
%   First block at bus_id becomes the representative (no line drawn).
%   Subsequent blocks connect their port to the representative's port,
%   creating a multi-way electrical node (SPS allows fan-out on physical lines).
    if isempty(bus_nodes{bus_id})
        bus_nodes{bus_id} = {blk_name, port_tmpl};
    else
        rep = bus_nodes{bus_id};
        for ph = 1:3
            rep_port = sprintf(rep{2}, rep{1}, ph);
            new_port = sprintf(port_tmpl, blk_name, ph);
            add_line(mdl, rep_port, new_port, 'autorouting', 'smart');
        end
    end
end
