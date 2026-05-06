<!--
USAGE: copy 到 quality_reports/research_loop/round_NN_verdict.md
风格: caveman 中文, 300-800 字, 详见 spec §7.2
-->

# R<NN> Verdict

**Status**: FINAL
**Date**: YYYY-MM-DD

## 实测 (强制区分 train vs paper-grade)
exp1:
  train_reward     (R_avg10, 5 seed mean±std): <X>
  paper_grade      (cum_rf @50 fixed test seeds, mean±std): <Y>
  6axis_overall    (LS1 + LS2 mean): <Z>  G=<ABCDEF>
  log: <path>
exp2: ...

> ⚠ Why 强制双 metric: 2026-05-06 throughput G6 surprise — cum_rf 单 seed
> 改 8.6× "改进" 实为 RNG drift, 不是真改. paper_grade @50 fixed seeds 是
> 真信号. 单 seed train_reward 不可独自 anchor.

## 对比
vs 上轮: 升/降, 哪 axis (引 round_NN_compare.md 如有)
vs 论文: 哪 axis 还差几倍

## 假设验证
H1: 验 / 证伪 / 部分 (一行理由)
H2: ...

## 接下轮
继 H<x> / pivot 见 pivots/<file> / done

## (可选) 数据表
| axis | LS1 | LS2 | paper | gap |
|---|---|---|---|---|
| max_df | ... | ... | 0.13 | ... |
