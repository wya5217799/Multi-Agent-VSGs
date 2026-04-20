# slx_helpers — 通用 Simulink 操作内核

不含任何 VSG/模型专用逻辑。所有函数操作 Simulink 通用概念（block、line、port、param），
通过 `cfg` 结构体接收调用方提供的模型专用参数，不直接 `strcmp(model_name, ...)` 分支。

模型专用逻辑 → `engine/simulink_bridge.py` / `BridgeConfig`
单模型诊断脚本 → `probes/kundur/` 或 `probes/ne39/`
