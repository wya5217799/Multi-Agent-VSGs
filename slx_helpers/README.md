# slx_helpers — 通用 Simulink 操作内核

不含任何 VSG/模型专用逻辑。所有函数操作 Simulink 通用概念（block、line、port、param），
通过 `cfg` 结构体接收调用方提供的模型专用参数，不直接 `strcmp(model_name, ...)` 分支。

模型专用逻辑 → `engine/simulink_bridge.py` / `BridgeConfig`
单模型诊断脚本 → `probes/kundur/` 或 `probes/ne39/`

## Boundary

General helpers may use Simulink concepts: model, block, line, port, parameter,
workspace variable, SimulationInput, SimulationOutput, timeseries, solver,
FastRestart, diagnostics, screenshot, and figure.

General helpers must not introduce new APIs whose primary contract is expressed
in VSG/RL terms: agent, episode, reward, M/D action, Pe, omega, rocof, delta,
Kundur, or NE39.

## Legacy Project Adapters

The following helpers are retained for the active Yang 2023 reproduction path
and are not general Simulink primitives:

- `slx_warmup.m`
- `slx_step_and_read.m`
- `slx_extract_state.m`
- `slx_build_bridge_config.m`
- `slx_validate_model.m`
- `slx_fastrestart_reset.m`
- `slx_episode_warmup.m`

Status: retained for VSG bridge compatibility. New generic MCP tools must not
call these helpers directly.
