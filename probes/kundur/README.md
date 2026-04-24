# probes/kundur — Kundur Regression Probes

Standalone MATLAB/Python scripts for Kundur scenario diagnostics.

## Active Regression Probes

| File | Purpose |
|---|---|
| `probe_sps_minimal.m` | Minimal SPS model smoke test |
| `probe_sps_parameter_parity_audit.m` | Parameter parity between ee_lib and SPS models |
| `probe_sps_static_workpoint_gate.m` | Static workpoint gate check |
| `probe_sps_workpoint_alignment.m` | Workpoint alignment verification |
| `probe_meas_topology.m` | Measurement block topology audit |
| `probe_warmup_trajectory.m` | Warm-up trajectory consistency |
| `probe_zero_action_pe_alignment.m` | Zero-action PE signal alignment |
| `validate_phase3_zero_action.py` | Phase-3 zero-action Python validator |

## Archive

`archive/2026-04-sps-workpoint/` — One-time hypothesis-testing probes used
during the SPS workpoint alignment investigation (Apr 2026). Completed;
not used in the regular regression pipeline.
