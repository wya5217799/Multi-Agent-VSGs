# NE39 修模笔记

> 改 `env/simulink/ne39_simulink_env.py`、`scenarios/new_england/` 前读这个文件。
> "已知事实"失效直接删。"试过没用的"不要删——防重试记忆。
> 改完顺手更新这份笔记。

## 现在在修
- r_f 奖励单位 bug 已修（commit **92d43b8**，`env/simulink/_base.py:207-221`）。
  上一次 run `ne39_simulink_20260417_062136` 在修复前 settled_rate=0。需要新 run 验证：r_f 在总 reward 中的占比从 90% 回落到 ~50%，`settled_rate > 0`。

## 已知事实（改代码前看一眼）
- **NE39 是 60 Hz**。`plotting/evaluate.py`、reward、监控面板里任何 50Hz 硬编码都是 bug。用 `getattr(env, "FN", 50.0)` 读。
- `_compute_reward` 里 Δω 必须用 **p.u.**（`omega - 1.0`），**不要乘 F_NOM**。论文 PHI_F=100 是对 p.u. Δω 校准的；乘 60 会让有效 PHI_F 放大 3600 倍，r_f 在总 reward 占比压到 90%+，策略退化为被动（ΔH≈0, ΔD≈0）。
- `BridgeConfig` 不要 `BridgeConfig(...)` 手写构造；用 `dataclasses.replace(NE39_BRIDGE_CONFIG, model_dir=...)`。否则 `pe_measurement`、`pe0_default_vsg` 等字段会丢，`config_simulink.py` 的改动会被静默忽略。
- 训练和评估 **必须用同一个 disturbance_mode（gen_trip）**。训练用 `apply_disturbance(±5-15 MW)` + 评估用 `gen_trip(100 MW)` 差 7-20x，学到的策略不迁移。
- `warmup` 失败后 except 块要强制 `bridge._fr_compiled = False`，否则下次 reset 跳过重编译、持续在坏模型上跑。`vsg_warmup` 返回 `None` 要 explicit check，不要 truthy 检查。
- `SACAgent.save()` 调用要带 `save_buffer=False`，否则 TypeError crash。

## 当前工作参数（applied，未经 outcome 验证）
- `BATCH_SIZE=256`, `WARMUP_STEPS=2000`（commit `27a51c3`）。原 BS=32 只用到 8 agents × 50 steps = 400 transitions 的 8%，梯度方差过高。
- FastRestart 首次编译后 `_fr_compiled=True`，后续 reset 跳过 `vsg_warmup` 的 Step 1+3（commit `06a53bf`）。约省每 episode 12s。

## 试过没用的
（暂无明确被标 `harmful`/`ineffective` 的修改；opt_ne_01..08 全部 `applied` 但多数未进入 outcome 阶段，请用"当前工作参数"的眼光看待）
