# Kundur Model Routing

> **Repository overlay** — Model-specific routing for the Kundur two-area
> four-machine system. Must not be placed in the shared installed
> `simulink-toolbox` skill.

## Identity

| Field | Value |
|---|---|
| `scenario_id` | `kundur` |
| `model_name` | `kundur_vsg` |
| Train entry | `scenarios/kundur/train_simulink.py` |
| Config | `scenarios/kundur/config_simulink.py` |
| Model file | `scenarios/kundur/simulink_models/kundur_vsg.slx` |

## Supported scenario_id values

Only `"kundur"` is valid. Do not use:

- `"kundur_simulink"` (registry does not recognise this)
- `"kundur_vsg"`
- any other variant

## Cold-start caveats

- MATLAB Engine first launch takes 30–90 s (R2025b typical).
- The first `harness_train_smoke_minimal` call may time out on a cold engine;
  confirm `bridge_ready` from `harness_scenario_status` before judging failure.
- Model load time for Kundur is shorter than NE39 (typically under 30 s).

## Smoke routing

```
harness_scenario_status   { "scenario_id": "kundur" }  → confirm model_exists + bridge_ready
harness_train_smoke_minimal { "scenario_id": "kundur" } → single-step smoke
```

## Known operational notes

- Frequency nominal: **50 Hz**. Do not confuse with NE39's 60 Hz baseline.
- VSG parameters: H ∈ [H_MIN, H_MAX], D ∈ [D_MIN, D_MAX] per `config.py`.
- 4 VSG agents, matching Table II of Yang et al. TPWRS 2023.
- IC file: `scenarios/kundur/kundur_ic.json` — check when obs contains NaN/Inf.
- Bridge config: `scenarios/kundur/config_simulink.py::KUNDUR_BRIDGE_CONFIG`.
