# probes/kundur — Kundur Regression Probes

Standalone MATLAB scripts for Kundur scenario diagnostics. Only keep a probe
here if it is reusable across sessions and bound to a concrete model invariant.
One-off investigative scripts go directly to `archive/`.

## Active Regression Probes

| File | Purpose |
|---|---|
| `probe_sps_static_workpoint_gate.m` | Static workpoint PASS/FAIL gate — checks Pe/angle at t≈0 for each source_angle_mode |
| `probe_sps_workpoint_alignment.m` | NR + SPS workpoint diagnostic (nr_only / sps_only / compare modes) |
| `probe_sps_parameter_parity_audit.m` | Read-only SPS-vs-NR parameter parity audit; re-run after any model rebuild |
| `probe_meas_topology.m` | Topology audit — confirms Meas_ES{i} measures correct branch current |
| `probe_warmup_trajectory.m` | Reset consistency gate — verifies multi-episode reset gives stable ICs |

## Subdirectories

| Directory | Contents |
|---|---|
| `gates/` | Pipeline gate scripts for the current CVS development phase (p4_d*) |
| `archive/` | Retired probes kept for historical reference — do not run |

## Archive Index

| Archive folder | What it was |
|---|---|
| `archive/2026-04-sps-workpoint/` | One-time hypothesis-testing probes from the SPS workpoint investigation (Apr 2026) |
| `archive/2026-04-sps-investigation/` | G0 feasibility, Phase-3 zero-action, and CVS spike prototypes (Apr 2026) |
