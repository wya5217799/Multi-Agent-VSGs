# exp3 — Paper disturbance audit (低优, R05 已部分 falsify)

> Read-only audit, R06 priority 6. Source: `kd_4agent_paper_facts.md` §8.4, `eval_paper_spec_v2.py:40-43`, `env/andes/andes_vsg_env.py:65-83,167-182`, R05 trace `ddic_r05_baseline_paper_s42_load_step_1.json`.

## §1 paper LS magnitude (paper_facts.md §8.4 / Sec.IV-C)

**Quote** (paper_facts.md:561):
> "Load step 1 and load step 2 represent the sudden load reduction of 248 MW at bus 14 and the sudden load increase of 188 MW at bus 15, respectively."

| Scenario | Bus | Direction | MW | sys_pu (100 MVA base) |
|---|---|---|---|---|
| LS1 | 14 | reduction | 248 | **−2.48** |
| LS2 | 15 | increase  | 188 | **+1.88** |

Step shape: sudden (instantaneous load step at t=0 of episode), held constant for the 50-step (5 s) episode. Single-event, no ramp / noise.

## §2 项目 disturbance 实现

- **Train env** (`env/andes/andes_vsg_env.py:66-67, 178-182`): `random_disturbance=True` → 每 reset 从 `uniform(DIST_MIN=0.5, DIST_MAX=2.0)` sys_pu 抽 magnitude (random sign, random PQ bus). R05 `disturb_5x` arm: `DISTURB_SCALE=5` → DIST_MIN=2.5, DIST_MAX=10.0.
- **Eval driver** (`scripts/research_loop/eval_paper_spec_v2.py:40-43`):
  ```python
  SCENARIOS = {
      "load_step_1": {"PQ_Bus14": -2.48},
      "load_step_2": {"PQ_Bus15":  1.88},
  }
  ```
  `random_disturbance=False`, 通过 `env.reset(delta_u=...)` 写死 paper magnitude. **完全对齐 paper §8.4**.
- **R05 trace 实测** (`ddic_r05_baseline_paper_s42_load_step_1.json` traces[0], step=1, t=1.1s): `delta_P_es ≈ [0.21, 0.25, 1.71, ...]` MW per ESS (这是 ESS 注入的 ΔP, 不是 load step 注入量本身). Eval 注入是写死 −2.48 sys_pu — JSON metadata `scenario="load_step_1"` 与 SCENARIOS 字典直读, 量级与 paper 一致.

## §3 比对结论

- [x] **paper magnitude 跟 eval 一致** (LS1 −2.48 / LS2 +1.88 sys_pu, 完全字面对齐 paper "248 MW at bus 14" / "188 MW at bus 15")
- [ ] paper magnitude 跟 eval 不一致 → 不需修

**Train vs eval 离差** (已知, 非本审范围): train uniform [0.5, 2.0] vs eval fixed 2.48/1.88 → train 平均 magnitude (≈1.25) ≈ eval 一半. R05 `disturb_5x` 即用 train scale=5 推到 [2.5, 10] 覆盖 eval magnitude, **6-axis 仍 0.037 没改善** → train↔eval magnitude gap **不是 root**.

## §4 R07 决策

**结论**: paper LS magnitude (−2.48 / +1.88 sys_pu) 跟 eval driver SCENARIOS 字典字面一致, **disturbance protocol 不是 6-axis fail 的 root cause**. R05 disturb_5x arm 实证 5× train magnitude 也无改善, 进一步证伪 magnitude scale 假设.

**动作**: exp3 关闭, 不需 R07 修改 LS magnitude 配置. 进 R06 verdict, root 候选锁定 exp1 (action range starvation, --phi-d 0.05 vs paper 1.0 偏 20×) / exp2 (其他 hyperparam diff). exp3 文档化为 negative-result, 防 R07+ 重复审.

**残留 minor flag** (不阻 R06): train uniform [0.5, 2.0] 严格说不匹配 paper Sec.IV-A 训练扰动描述 ("50 个不同位置不同大小功率阶跃"), 但 paper 未给训练 magnitude 分布范围 → unspecified, 当前 [0.5, 2.0] 不算违规, 仅记录.
