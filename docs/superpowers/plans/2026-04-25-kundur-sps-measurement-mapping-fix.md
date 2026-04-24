# Kundur SPS — Measurement Mapping Fix (Option B)

**Prior plan:** `docs/superpowers/plans/2026-04-24-kundur-sps-task9-no-go-recovery.md`

**Status:** ACTIVE — authorized batch only. Old plan is historical record; do not amend it further.

---

## Inherited Constraints

Hard gates, prohibited-file list, dirty-state protection, and STOP rules from the prior plan all continue to apply. Key reminders:

```text
Prohibited files (no edit, no save):
  build_kundur_sps.m
  build_powerlib_kundur.m
  compute_kundur_powerflow.m
  kundur_ic.json
  kundur_vsg_sps.slx
  config_simulink.py
  docs/paper/experiment-index.md

Smoke Bridge / training / cutover: still blocked
simulink_save_model: prohibited in this batch
```

---

## Current State

```text
measurement_point_mapping.json written and confirmed.

Finding: sps_main_bus_angle_deg in static_workpoint_gate.json is the
  voltage angle at ESS dedicated bus (Bus 12/16/14/15), not at main bus
  (Bus 7/8/10/9). No Bus 7/8/10/9 voltage measurement blocks exist in
  the current SPS model.

Consequence: the ~15 deg angle gap in the old gate is not a clean
  diagnostic. It conflates source-angle error, tie-line impedance drop,
  and multi-pu current distortion.

Old gate field sps_main_bus_angle_deg: invalid as main-bus proxy.
Old gate is still valid as a Pe gate (passes_pe_gate=false for all configs).
```

---

## Authorized Batch — Option B: Like-for-Like ESS-Bus Comparison

Compare NR and SPS at the **same physical node** — ESS terminal buses
(Bus 12 / 16 / 14 / 15) — instead of comparing mismatched nodes.

### Step 1 — Check NR script for Bus 12/16/14/15

**Read-only.** No execution.

- [ ] Read `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m`.
- [ ] Identify whether the 15-bus Ybus includes dedicated ESS buses (12, 14, 15, 16).
- [ ] Record bus-index mapping and whether those buses produce angle output.

**STOP immediately if** the NR script does not include Bus 12/16/14/15 as
network nodes. Report: which buses are present, which are absent. Do not
extend the NR topology.

Verify: step produces a written finding (inline, not a new artifact) before Step 2.

---

### Step 2 — Generate NR Bus 12/16/14/15 reference angles

Only run if Step 1 confirms those buses are in the NR script.

```text
Tool: simulink_run_script
Script: compute_kundur_powerflow.m (read-only NR run, no file write)
Capture: theta_abs_deg for Bus 12, 16, 14, 15
```

- [ ] Run NR powerflow via `simulink_run_script` (no model open needed).
- [ ] Capture Bus 12/16/14/15 angles in absolute simulation frame.
- [ ] Verify powerflow converged (converged=true, max_mismatch < 1e-5 pu).

**STOP if** NR does not converge or does not output Bus 12/16/14/15 angles.

---

### Step 3 — Extract SPS ESS-bus angles from existing gate data

No new simulation needed. The `static_workpoint_gate.json` already contains
`sps_main_bus_angle_deg` which is the ESS terminal bus angle (confirmed by
measurement_point_mapping.json). Use that data directly.

- [ ] Extract `sps_main_bus_angle_deg` for all three configs from
  `static_workpoint_gate.json` (reinterpret as ESS-bus angle, not main-bus angle).
- [ ] Identify best config for comparison (lowest angle error from prior gate).

---

### Step 4 — Write ess_terminal_angle_comparison.json

- [ ] Write artifact:
  `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess_terminal_angle_comparison.json`

Required fields:

```json
{
  "schema_version": 1,
  "scenario_id": "kundur",
  "comparison_nodes": "ESS dedicated buses (12/16/14/15)",
  "nr_ess_bus_angles_deg": { "Bus12": ..., "Bus16": ..., "Bus14": ..., "Bus15": ... },
  "sps_ess_bus_angles_deg": {
    "persisted_current": { ... },
    "emf_reference": { ... },
    "terminal_reference": { ... }
  },
  "angle_errors_deg": { ... },
  "angle_gate_threshold_deg": 1.0,
  "any_config_passes_angle_gate": true | false,
  "best_config": "...",
  "verdict": "...",
  "provenance": { ... }
}
```

---

### Step 5 — Update summary.md

- [ ] Append to `results/harness/kundur/20260424-kundur-sps-workpoint-alignment/summary.md`:
  - Old gate angle-error field was a proxy (ESS bus, not main bus) — now corrected.
  - New like-for-like ESS-bus comparison result.
  - Whether source-angle root-cause branch still viable.

---

## STOP Conditions

```text
STOP 1: NR script does not include Bus 12/16/14/15.
  → Report missing buses. Do not extend NR topology. Await human decision.

STOP 2: ess_terminal_angle_comparison.json written.
  → Present results and verdict. Do not proceed to model edits.

STOP 3: Any artifact field reveals new semantic error affecting diagnosis.
  → Record, STOP, do not continue downstream.

STOP 4: Token circuit-breaker — ~5000 tokens with no gate, no tool call, no artifact.
  → Stop and report blockage.
```

---

## Output Artifact

```text
results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/ess_terminal_angle_comparison.json
```

This artifact ends the batch. Human review required before any further action.

---

## Prohibited Inference Chains

```text
angle error small → start Smoke Bridge
angle error large → patch build_kundur_sps.m
config X looks better → run training
NR buses absent → extend NR script unilaterally
```

Evidence triggers a plan update. It does not trigger an action.
