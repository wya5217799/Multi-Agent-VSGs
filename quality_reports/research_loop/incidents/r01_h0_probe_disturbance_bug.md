# Incident — R01 BC probe (Phase C-pre H₀ sweep) 全 fail, root = probe bug 不是 env

**Date**: 2026-05-07
**Round**: R01
**Severity**: med (Phase B 通道仍 PASS, Phase C-pre 数据缺)

## 现象
`results/research_loop/r01_bc_probe.json::phase_C_h0_sweep` 4 个 H₀ 候选 (20/30/50/80 s)
全 pflow=False, error_type=ValueError, error_msg="'bus' is not in list".

## Root cause
probe `r01_bc_probe.py:99`:
```python
env.reset(delta_u={"bus": 7, "delta_p": 0.10})
```

但 `andes_vsg_env.py:_apply_disturbance` 期待 `delta_u: dict[pq_idx, dp]`:
```python
for pq_idx, dp in delta_u.items():
    pq_pos = list(self.ss.PQ.idx.v).index(pq_idx)
    self.ss.PQ.Ppf.v[pq_pos] += dp
```

probe 传了 `{"bus": 7, "delta_p": 0.10}` → `pq_idx="bus"` → `PQ.idx.v.index("bus")` ValueError.

**probe 自己的 schema 错**, 不是 env 不收敛, 不是 H₀ 不可行.

## 影响
Phase C-pre 数据全 0. R02 上 H₀=50 baseline 决策**没 sanity 数据**.

Phase B (governor add) 仍 PASS:
- IEEEG1.add(idx=PROBE_GOV_1, syn=1) ok=True
- EXST1.add(idx=PROBE_AVR_1, syn=1) ok=True
- pflow_after_add ok=True
→ R02 启 Phase B 仍可行.

## 修复
probe 改成传 `delta_u=None` (let random disturbance happen) 或传合法 pq_idx.
更稳: 用 V2 env factory pattern + `_v2_d0_sweep.py` 现有 `delta_u` 写法 (有效 pq_idx).

```python
# 旧 (bug):
env.reset(delta_u={"bus": 7, "delta_p": 0.10})

# 新 (fixed):
env.reset(delta_u=None)            # 走 random disturbance, 验 build sanity
# 或:
pq_idx = env.ss.PQ.idx.v[0]         # 取第一个合法 pq idx
env.reset(delta_u={pq_idx: 0.10})
```

## R02 行动
入 R02 pending: `r02_C_pre_h0_sweep_v2` 用修过的 probe 跑 H₀∈{20,30,50,80} pf+5step TDS.
~5 min, 单 cpu 槽, priority=10 (gates Phase C 决策).

## Lesson
probe script 必须先用最简 disturbance (None) sanity 一次, 再加复杂 dict. 我跳了 sanity 直接写
`delta_u={"bus": 7}` 抄 paper 概念没 cross-check env API. 写 probe 也得 schema 验.

## Cross-ref
- `scripts/research_loop/r01_bc_probe.py:99` — bug 行
- `env/andes/andes_vsg_env.py:158-176` — disturbance schema
- `scenarios/kundur/_v2_d0_sweep.py` — 已知合法 disturbance dict 例子
