<!--
USAGE: copy 到 quality_reports/research_loop/round_NN_plan.md
风格: caveman 中文, 200-500 字, 详见 spec §7.1
-->

# R<NN> Plan

**Status**: DRAFT
**Date**: YYYY-MM-DD
**Trigger**: <上轮 verdict / pivot / handoff>

## 上轮
ckpt=<X>  6axis=<Y>  G=ABCDEF (B=fail F=pass null=未跑)

## 假设
H1: 改 a → 期 Δb (一句理由)
H2: ...

## 跑啥 (K = <N>, 由 budget tier 算; AI override 写一行 rationale)
exp1: <cmd 简版> seed=<N> ep=<N> RAM≈<gb> hr≈<hr>  rationale=<一句>
exp2: ...

## 期
G<x> > <thr>  (跟 §1 spec gates 对齐)

## 不行咋办
回 R<NN-1> baseline / pivot / 见 §<x>
