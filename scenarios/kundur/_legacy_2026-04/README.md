# scenarios/kundur/_legacy_2026-04/

R0 baseline 期 (2026-04~05) eval/sweep 脚本归档. 不要从这里 import.

## 为啥归档

research-loop R03 (2026-05-07) 用 6-axis evaluator 闭环验证, eval 单一入口确立为
`scripts/research_loop/eval_paper_spec_v2.py`. 老入口 5+ 个并存制造混淆,
其中 `_eval_paper_specific.py` 在 stash 事故 (2026-05-07) 中丢失,
依赖它的 `_phase9_shared_*_reeval.py` / `_re_eval_best_ckpts.py` 已 broken.

## 文件清单

| 文件 | 原职责 | 替代品 |
|---|---|---|
| `_eval_paper_grade_andes.py` | R0 paper-grade eval 主入口 | `scripts/research_loop/eval_paper_spec_v2.py` |
| `_eval_paper_grade_andes_one.py` | R0 paper-grade eval 单 ckpt | 同上 |
| `_eval_paper_grade_andes_parallel.py` | R0 paper-grade eval 并行 (subprocess `_one`) | 同上 |
| `_eval_paper_grade_warmstart.py` | R0 warmstart eval | 同上 |
| `_phase3_eval_v2.py` | phase3 reeval (_eval_paper_grade family) | 同上 |
| `_phase4_eval.py` | phase4 reeval | 同上 |
| `_phase9_shared_3seed_reeval.py` | phase9 reeval (broken — 依赖丢失的 `_eval_paper_specific.py`) | 同上 |
| `_phase9_shared_5seed_reeval.py` | 同上 (broken) | 同上 |
| `_phase9_shared_seed42_pilot_reeval.py` | 同上 (broken) | 同上 |
| `_re_eval_best_ckpts.py` | best vs final 对比 (broken) | 同上 |
| `_v2_d0_sweep.py` | V2 baseline d0 sweep | (V2 verdict 已锁, 不再 sweep) |
| `_v2_linex_sweep.py` | V2 linex sweep | 同上 |
| `_run_v2_5seed.sh` | V2 5seed runner | `scripts/research_loop_daemon.sh` (新 daemon) |

## 历史 verdicts 引用

`quality_reports/audits/2026-05-04_*.md` / `quality_reports/replications/2026-05-03_*.md` 系列
引用了这些脚本作为 eval 来源. 保留不改, 因为 verdicts 是历史快照.

## Probe 引用 (已审)

`probes/kundur/agent_state/_ablation.py:27` 的 `_phase3_eval_v2.py` 提及为 **comment**,
不是 import — 安全归档.
