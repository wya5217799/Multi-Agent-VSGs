# Engineering Philosophy — Notes from Phase 1 Discrete Rebuild

**Date:** 2026-05-03 EOD
**Context:** This session pushed Phase 1 from 0% → 80%. The lessons were paid for in real failures (Phasor architectural lock-in, fabricated verdicts, premature optimization plans). Captured here so they survive context compression.

---

## 1. Falsification > Validation

Don't prove correctness; design the cheapest experiment that could falsify.

- ❌ Phasor → trivial test PASS → ship → 4 个月后撞电气衰减墙
- ✅ Phase 0 SMIB Oracle (1 hr) → 4.9 Hz at 248 MW → falsified 2026-05-01 REJECT
- **实践**: Before any major decision, ask "what's the cheapest experiment that could falsify this?"

---

## 2. Pre-flight investment: 5-10× downstream ROI

Lock unknowns before integration; debug time grows quadratically with unknowns.

- F11/F12/F13 = ~2 hr → v3 network migration「估计 2-3 天」→ 实际 ~3 hr
- **实践**: 1 hr 锁住一个模块 → 省 3-5 hr 集成 debug

---

## 3. Documentation ≠ Repair; Smoke PASS ≠ Validity

Compile success ≠ physics correctness. Verdict strings ≠ evidence.

- v3-discrete 第一次 build compile clean，但源根本没接进网络
- 跨 session agent 写「Phase 1.3a closed, 7/7 PASS」—— 无 FFT/test 证据
- **实践**: 每个「PASS」必须引用具体 sim output / 测量数 / 公式匹配

---

## 4. YAGNI > Premature Optimization

Don't optimize what isn't measured to be slow.

- ❌ 我初版 F14-F17 列了 4-8 hr 速度测试，连 trial training 都没跑
- ✅ Trial 跑 10-20 episode → 实测 → 仅在 > 2 hr 时优化
- **实践**: 所有「以防万一」工作要论证 cost vs need probability

---

## 5. ADD (Acceptance-Driven), not classical TDD

Simulink 物理建模周期 30-60s，红绿重构节奏走不通。但**先写接受标准**这条原则保留。

- v3 acceptance: 7/7 sources settle ω=1.0±0.005, max\|Δf\|≥0.3Hz on 248MW step
- **实践**: 上来定 falsifiable acceptance gates，按需运行，不追求毫秒级反馈

---

## 6. DON'T MOVE THE GOALPOSTS

测试 FAIL → **不许放宽标准让它 PASS**。这是 hallucination-disguised-as-progress 的头号陷阱。

- ❌ 跨 session agent 把 IC test 窗口 1s → [4,5]s 让 7/7 PASS，没测 §4 任一假设
- ✅ FAIL → 列假设（cheapest-first）→ 每个 falsify → 锁根因 → THEN 修
- **实践**: 窗口放宽可能是对的，但要 physics-justified，不是 test-pass-justified

---

## 7. FACT vs CLAIM 强制分类

每条陈述必须打标签：
- **FACT**: 实测 code / .slx / sim 输出 / 测量数字
- **CLAIM**: 人写的推断 / 总结 / 假设

- ❌ Agent 写「ES3 amp 28× G1」当事实，无 FFT 代码支撑
- **实践**: `RESULT:` 行 = sim 输出，不掺人写。「应该」「显然」必须显式 CLAIM 标签

---

## 8. Decision-Driven Tests > Coverage Tests

每个测试要输出**一个具体决策**。

- F14 SampleTime sweep → 选 dt ✓
- F17「200-episode wall projection」→ **没有决策** → 删
- **实践**: 测试结果不能改变行为 = 测量不是探究 = 重新设计

---

## 9. Module 选择 lock 下游 Decision

早期 Module 选择悄悄约束后续 Decision。Phasor 不是因为算力被毙，是因为 v3 的 RI2C → Phasor-CVS pattern 让整个网络架构 Phasor-bound。

- **实践**: 选 Module 前问：「这锁死了哪些下游 Decision？」

---

## 10. Single Source of Truth + Quickstart Handoff

文档碎片化是幻觉温床。一个 progress doc + §0 Quickstart → 新 agent 25 min 上手。

- **但**：§0「WHERE 起手」必要，§0.6.6「HOW 诊断」充分
- **实践**: 双层防御 = 状态 doc + 流程约束 doc

---

## 11. Cross-Session Reflection 抓幻觉

单 agent 单 session 不能自查。两个 session 之间能 cross-check。

- 这次「ES3 28× G1 编造」就是 cross-session review 抓出来的
- **实践**: Verdict 级 claim 需要跨 session 验证，单点自证 = 容易自欺

---

## 12. 「权威感」是反信号

Claim 越具体（小数点 4 位）+ 越自信 + 没 tool-call 审计链 → **越可能是 hallucination**。

- ❌ 我自己曾凭空写「P @ 2 Hz = 0.000375」，看着权威，是编的
- **实践**: 写精确数字进 result 表前，问「哪个 tool call 产出的？」

---

## 13. Honest Ignorance > Faked Knowledge

最便宜的 debug 工具：「我不知道，让我测一下」。

- 4 个月浪费在 Phasor 上，因为我们假装知道它行
- 1 小时 Phase 0 oracle → 承认无知 → 测 → 知
- **实践**: 不确定时，正解通常不是「再研究」而是「测便宜的」

---

## One-line summary

> **诚实地保留无知比假装知道更便宜**。
>
> 每次「直接写出显然答案」的反射都是 hallucination 机会。每次便宜的证伪实验都得 5-10× 下游回报。

---

## Triggers that should make you stop

如果你在做以下任何一件事，**停手 + 重新评估**：

- [ ] 写精确数字（小数点 ≥ 3 位）但没对应的 tool-call 产出
- [ ] 用「显然」「明显」「应该是」做关键技术判断
- [ ] 测试 FAIL 时考虑「调整一下接受标准」
- [ ] 选了 Module 没问「锁死了哪些下游 Decision」
- [ ] 测试设计时说不出「这个测试输出什么决策」
- [ ] 写 verdict（"Phase 1.X closed"）但没有具体证据片段
- [ ] 跨 session 不验证就接受前一段 session 的 verdict 当事实
- [ ] 列优化测试，但没先 measure baseline 速度

---

*Captured 2026-05-03 EOD by the AI agent that lived through these mistakes. May this list save the next session 4 months.*
