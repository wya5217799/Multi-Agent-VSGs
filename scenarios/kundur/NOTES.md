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
- **vlf_ess [18,10,7,12]° 过时根因**：阻抗修复前 X_vsg = 0.30 pu（错用机端 base），修复后 X_vsg_sys = 0.30×(100/200) = 0.15 pu。P_max 增大，旧角度处 Pe_elec >> Pe_mech，均衡角已偏移。
- **正确方法**：在 `build_powerlib_kundur.m` 中用 ee_lib 潮流 API（`power_loadflow` 或等效）直接求 ESS 各母线平衡相角，delta_eq = theta_bus + arcsin(Pe_nom/P_max)，结果写入 `kundur_ic.json`，消除手动校准需求。
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

### Phase 5b 均衡角搜索（2026-04-19）——以下方法全部无效
- **高阻尼法 D=50，60s，从 0° 强制平启**：delta → -∞，omega 立刻饱和在 0.7。0° 与网络状态完全不匹配。
- **高阻尼法 D=50，60s，从 baked ICs [18,10,7,12]°**：delta 仍飞到 -100,000°，omega 饱和在 0.7。
  - 根本原因：Pe_excess = Pe_elec(18°) - Pe_mech >> D×(1-0.7) = 15 pu，高阻尼的恢复力不够。
  - 物理约束：只要 Pe_excess > D×0.3，omega 就无法从 0.7 恢复，任何 D 值的高阻尼法都失效。
- **短仿真 1s + D=3，从 [18,10,7,12]° 读 t=0.8s Pe**（分析排除，未实际运行）：
  - D=3 的恢复力仅 0.9 pu，同样被 Pe_excess 压垮，omega 在 0.5s 内已饱和。
- **从 1° 小角出发**（分析排除，未实际运行）：
  - Pe_mech >> Pe_elec(1°) → omega 打上限 1.3 → dδ/dt = ωn×0.3 ≈ 94 rad/s → delta 几百 ms 内飞到数百度。
- **冻角法（measure_pe_frozen.m）**（2026-04-19 实际运行）：
  - 思路：固定 delta=常数，短仿真读稳态 Pe，再解 δ = arcsin(Pe/Pmax)。
  - 结果：Pe 测量值 30–44× 高于 Pe_mech，完全不物理。
  - 根因：PeFb 信号单位异常（已记录于 NOTES 已知事实），任何依赖 PeFb 的反推路线均无效。
- **静态潮流 power_loadflow / ee_lib API**（分析排除）：power_loadflow 是 powerlib 函数，本模型用 ee_lib，API 不兼容。simscape.op.create 只能提取已有稳态 OP，不能从参数直接解潮流。
- **根本教训**：均衡角搜索不能依赖动力学仿真（任何偏离均衡的初始角度 → 快速饱和），也不能依赖 PeFb 信号（单位异常），也不能用 simscape.op 做初始潮流。正确路线：纯静态 Newton-Raphson 潮流（见下）。

### Phase 6：Newton-Raphson 潮流参数化（2026-04-19 实施）
**为何必须走潮流参数化：**
- 阻抗 base 修复后（commit 216d8b9）X_vsg 从 0.30 → 0.15 pu，P_max 翻倍，旧 [18,10,7,12]° 不再是均衡点。
- 所有动力学探针路线（高阻尼/冻角/短仿真）已证明失效（见上）。
- P0 变化时，delta0 必须自动重算，否则每次参数改动都需要手动校准 → 工程上不可维护。

**vsg_delta0_deg 语义（追踪代码确认）：**
- 在 build_powerlib_kundur.m 第 695-698 行：delta0_rad 是 `IntD` 积分器 IC，IntD 输出 = delta，delta 进入 theta = wn*t + delta → CVS 电压。
- 因此 vsg_delta0_deg = VSG 内部电势（CVS 输出电压）的**初始相位角**，即内电势角 δ，不是母线电压角。
- 绝对仿真帧基准：Bus1（G1）从 vlf_gen(1,2)=20° 启动，潮流求解以 Bus1=0° 为参考，最终转换公式：δ_abs = θ_pf_relative + 20° + arcsin(...)

**采用方案（compute_kundur_powerflow.m）：**
1. 用与 build_powerlib_kundur.m 完全一致的网络参数构建 15 母线（1-16，跳过 13）Ybus
2. Newton-Raphson 潮流（Bus1 松弛，Bus2/3/4 PV，其余 PQ）
3. 得到主母线 Bus7/8/9/10 的相角 θ_pf
4. 转换到绝对仿真帧：θ_abs = θ_pf + 20°
5. 用 SMIB 公式（从 VSG IntD/IntW 摆动方程严格推导）计算内电势角：
   δ_i = θ_main_abs_i + arcsin(P0_vsg_base_i × (VSG_SN/Sbase) × X_vsg_sys / V_main_i)
   其中 X_vsg_sys = 0.15 pu，V_main 来自潮流，P0_vsg_base 来自 kundur_ic.json
6. 写回 kundur_ic.json（calibration_status = 'powerflow_parametric'）

**验证标准：**
- 潮流收敛（converged=true，max_mismatch < 1e-5 pu）
- sin_arg = P0_sys × X_vsg / V_main ∈ (-1, 1)（物理可行）
- 4 个 delta 角处于合理量级（|δ - θ_main| < 90°）
- build → load 链路：slx_load_kundur_ic 能读到新 delta 值

**已知限制：**
- 当前 P0 值（vsg_p0_vsg_base_pu ≈ 1.87 pu，标记为 placeholder_pre_impedance_fix）是过时占位符，P0 重校准是独立 TODO（见"现在在修"一节）。
- 潮流以当前 P0 为 ESS 注入量运行，松弛母线会吸收多余功率（G1 可能变为吸收状态）。数值上仍收敛，delta0 结果与 P0 参数一致，待 P0 更新后重跑 build 即可自动更新 delta0。

### Phase 5b 第二轮修复（2026-04-19 实施，全部无效）

**背景**：NR 潮流已给出正确 delta0（B3 ✅），模型重建（B4）成功，但 Phase 3 验证（B5）仍 FAIL。以下修复均已在 B4 重建中实施。

- **EMF 角 + IL_specify/IL 设置（Zess RLC 三相块）**：设置 `IL_specify='on'`、`IL=[ILa,ILb,ILc]`（AC 相量，从 NR 潮流反算感应器电流）。
  - 无效原因：Simscape 本地固步长求解器 DC 初始化将感应器初始电流置 ≈ 0（50 Hz 交流源在 DC 分析时贡献为 0），IL 参数被完全忽略。任何依赖 IL_specify 设置 AC phasor 初始电流的路线均无效。

- **P_ref 斜坡 X0=0（ConvGen + VSG）**：`build_powerlib_kundur.m` 中 ConvGen P0_ramp 和 VSG PrefRamp X0 从 `num2str(P0)` 改为 `'0'`。
  - 物理直觉：t=0 时 P_ref=0=Pe，P_accel=0，不触发 omega 冲击。
  - 结果：模型重建成功，Phase 3 仍 FAIL（POST-WARMUP delta=[-90,-90,-90,-90]）。
  - 关键线索：验证脚本输出"warmup ~0.5 s"——说明 T_WARMUP=3.0 override 未被脚本读到，0.5s warmup 内 P_ref 斜坡远未完成（T_ramp=2s）。

- **T_WARMUP=3.0 override（`scenarios/kundur/config_simulink.py`）**：在 import 段后新增 `T_WARMUP = 3.0`，覆盖 base 的 0.5s。
  - validate_phase3_zero_action.py 仍显示"warmup ~0.5 s"——脚本 T_WARMUP import 路径未经过此 override，根因未查明。
  - **待查**：validate 脚本从何处读 T_WARMUP？是否直接 import config_simulink_base？还是 bridge 内硬编码？

- **C4 PASS 而 delta=-90° 的含义**：drift=0 deg/step 不是"稳定"，而是 IntD 积分器触下限（-π/2）后停止运动（hard clamp）。说明 warmup 期间发散已完成，T_WARMUP 延长未必有效（若冲击在最初 0.1s 内触发饱和）。

- **下一步**：读 `probes/kundur/validate_phase3_zero_action.py` 追查 T_WARMUP import 路径；检查 `slx_helpers/slx_warmup.m` 内实际使用的 t_warmup 值来源；分析 ConvGen omega 在 t=0 的冲击大小与时间尺度。

## Active migration rule

- JSON profile controls only known semantic slots.
- Semantic manifest is the exported fact layer.
- Reintroducing `PrefRamp_*` or long physical warmup on the SPS path is a regression.
- `validate_phase3_zero_action.py` now checks SPS invariants: early Pe convergence + no -90° false stability.
- `probe_warmup_trajectory.m` verifies reset consistency across episodes (run via simulink_run_script).
