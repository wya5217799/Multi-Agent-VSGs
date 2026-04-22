# slx_helpers - General Simulink Operation Core

Root-level helpers in this directory are general Simulink primitives. They
operate on model, block, line, port, parameter, workspace variable,
SimulationInput, SimulationOutput, timeseries, solver, FastRestart,
diagnostics, screenshot, and figure concepts.

Root-level helpers must not introduce new APIs whose primary contract is
expressed in VSG/RL terms: agent, episode, reward, M/D action, Pe, omega,
rocof, delta, Kundur, or NE39.

Model-specific logic belongs in Python project adapters:

- `engine/simulink_bridge.py`
- `env/simulink/`
- `scenarios/*/config_simulink.py`

Reusable one-scenario diagnostics belong under:

- `probes/kundur/`
- `probes/ne39/`

## Directory Boundary

```text
slx_helpers/
  *.m
    General Simulink primitives only.

slx_helpers/vsg_bridge/
  *.m
    VSG/RL bridge compatibility adapters used by engine/simulink_bridge.py.
```

## VSG Bridge Compatibility Adapters

The following helpers are retained for the active Yang 2023 reproduction path
and are not general Simulink primitives:

- `vsg_bridge/slx_warmup.m`
- `vsg_bridge/slx_step_and_read.m`
- `vsg_bridge/slx_extract_state.m`
- `vsg_bridge/slx_build_bridge_config.m`
- `vsg_bridge/slx_validate_model.m`
- `vsg_bridge/slx_fastrestart_reset.m`
- `vsg_bridge/slx_episode_warmup.m`

Status: retained for VSG bridge compatibility. New generic MCP tools must not
call these helpers directly.
