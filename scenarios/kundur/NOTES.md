# Kundur 修模笔记

> 改 `env/simulink/kundur_simulink_env.py`、`scenarios/kundur/` 前读这个文件。
> "已知事实"失效直接删。"试过没用的"不要删——防重试记忆。
> 改完顺手更新这份笔记。

## 现在在修
- omega 100% 饱和 from step 0。已修阻抗 base 转换 bug（commit **216d8b9**，`scenarios/kundur/simulink_models/build_powerlib_kundur.m`），**未回归验证**。
  下一步：
  1. **先重新校准 VSG_P0**（opt_kd_05 遗留 TODO）。阻抗改了之后 P0/P_max 比例也变了，不校准直接跑训练会在错误工作点上。
  2. 再跑一次训练，确认 `omega_saturated < 50%`、`mean_freq_dev < 8Hz`。

## 已知事实（改代码前看一眼）
- `KundurStandaloneEnv`（ODE 后端）的 `_P_mech = 0.5` 与 Simulink 主线 `VSG_P0_SBASE`（4 元向量，system-base pu）不一致；ODE 路径未列入本次 Pe 契约修复（2026-04-18）。若重启 ODE 路径需单独对齐。
- `build_powerlib_kundur.m` 里 Xd=0.30 pu 是 **machine base**，必须乘 `Sbase/S_machine` 转到 system base 再写进模型。错了会让 P_max < P0，永久振荡。
- IntW 饱和限 [0.7, 1.3] ≡ ±15 Hz。**饱和不会触发 `tds_failed`**，但 omega 读数失真 → reward 失真 → replay buffer 污染。监控用 `omega_saturated` info flag，不要只看 `tds_failed`。
- Kundur 两区域模式 ≈ 0.5 Hz。振幅相对稳态的放大倍数 **未实测**（曾推断 2-2.5x，无证据，不要当结论引用）。
- Q7（论文 D 量纲）未解决前，**不要把 D 改到 100+ 量级**。参见 `docs/paper/yang2023-fact-base.md` §Q7。
- Kundur 是 **50 Hz**（NE39 是 60 Hz，别混）。
- 固定 50 步 episode + 无 Python 频率早停是论文对齐，正确；IntW 饱和命中要作为"模型失真事件"监控，不是终止条件。

## 试过没用的（别再试）
- `DIST_MAX` 3.0 → 1.5：单独无效（commit `d5732ec`）。稳态公式忽略了 inter-area 振荡放大。
- 删除 `omega_unstable` guard：单独无效（commit `fea0839`）。对齐论文方向正确，但不解决饱和根因。
- M/D rate limiting（`DELTA_M_MAX_PER_STEP`）：单独无效。真正根因是阻抗 base bug（已由 216d8b9 修）。
- 以上三者的共同盲点：都在治"episode 不要提前结束"，未处理"频率物理上为何这么高"。
