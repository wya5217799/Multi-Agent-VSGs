# Simulink 共享层修改笔记

> 改 `env/simulink/_base.py`、`plotting/evaluate.py`、`utils/training_viz.py`、`engine/simulink_bridge.py` 前读这个文件。
> 共享层的 bug 同时影响 Kundur 和 NE39，改完**要顺便查两份场景 NOTES**：
> - `scenarios/kundur/NOTES.md`
> - `scenarios/new_england/NOTES.md`

## 已知事实
- `_base.py::_compute_reward` Δω 用 **p.u.**（`omega - 1.0`），**不要**乘 F_NOM。任何"为了更直观用 Hz 或 rad/s"的 PR 先否掉，这个问题已经踩过一次（见 NE39 NOTES）。
- `plotting/evaluate.py` 的 `max_freq_dev` 基准必须 `getattr(env, "FN", 50.0)`，不要硬编码 50。
- `plotting/evaluate.py::_get_zero_action` 按 `env.ACTION_ENCODING` 属性分发；不要假设所有 env 的零动作定义相同（`action=[0,0]` 在非对称动作空间里**不是**"不控制"）。
- `engine/simulink_bridge.py` 的 `_fr_compiled` 是跨 episode 状态；warmup 失败必须重置，否则后续 reset 在坏模型上跑。

## 改这里之前
- 影响面：两个场景全部受影响。
- 改完必须跑两份 smoke：Kundur + NE39 都要 `harness_train_smoke_start` 验一次。
