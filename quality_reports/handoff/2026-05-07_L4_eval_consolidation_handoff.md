# Handoff — L4 (eval 单一入口) + 轻量 L3 (sweeps) 重构

**Date**: 2026-05-07
**Trigger**: research-loop R03 verdict 暴露 5 个并存 eval 入口混乱; user 拍板执行 L4
**Predecessor session**: R01-R04 research-loop (`quality_reports/research_loop/`)
**Estimated wall**: 30-45 min in clean session
**Risk**: low (移动的全是 R0 历史脚本, daemon 不依赖)

---

## 0. 进新会话第一动作

```
1. 读这份 handoff (你正在读)
2. 读 quality_reports/research_loop/round_04_verdict.md (验 R04 完结)
3. git status (确认 clean)
4. ps -p $(cat /tmp/rloop_daemon.pid) 看 daemon 是否在跑
5. 进 §1 pre-flight
```

---

## 1. Pre-flight check

| 检查 | 命令 | 通过条件 |
|---|---|---|
| R04 完结 | `python3 -c "import json; s=json.load(open('quality_reports/research_loop/state.json')); print('round=',s['round_idx'],'pending=',len(s['pending']),'running=',len(s['running']))"` | round=4, pending=0, running=0 (或 R04 verdict 已写) |
| daemon idle | `ps -ef \| grep train_andes \| grep -v grep \| wc -l` | 0 (没 ANDES 跑, 移文件不 race) |
| git clean | `git status --short` | 没非预期修改 |
| 现 eval 单源已存在 | `ls scripts/research_loop/eval_paper_spec_v2.py` | 文件存在 (R03 已 build) |

⚠ 如 R04 还在跑 → 等到 ScheduleWakeup 后 R04 verdict 写完, 再启动 L4.
⚠ 如 daemon 死了 → 先复活: `nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &` (或不复活, 静态 refactor 也可).

---

## 2. Cross-ref audit (已跑, 数据如下)

### 2.1 Live code refs — 必须更新或接受 break

| 引用方 | 引用谁 | 处理 |
|---|---|---|
| `scenarios/kundur/_eval_paper_grade_andes_parallel.py` | `_eval_paper_grade_andes_one.py` (subprocess) | 都 archive, **内部 ref OK** (一起移) |
| `scenarios/kundur/_phase3_eval_v2.py` | `_eval_paper_grade_andes` family | 都 archive, **内部 OK** |
| `scenarios/kundur/_phase4_eval.py` | 同上 | 同 |
| `scenarios/kundur/_phase9_shared_*_reeval.py` × 3 | `_eval_paper_specific` (已丢) | 已 broken, archive 无副作用 |
| `scenarios/kundur/_re_eval_best_ckpts.py` | `_eval_paper_specific` | 已 broken, archive |
| **`probes/kundur/agent_state/_ablation.py`** | `_phase4_eval` | ⚠ **需 verify probe 是否活** — 见 §2.4 |
| `scripts/run_tier_a_post_training.sh` | `_eval_paper_grade_andes` family | 老脚本可能 dead, 跑下面 grep 验证 |

### 2.2 Path-table refs (项目导航文档) — **必须改**

```
CLAUDE.md                                           — 改 eval entry 指 scripts/research_loop/eval_paper_spec_v2.py
MEMORY.md                                           — 加 [LEARN:refactor] 1 行
.claude/skills/research-loop/SKILL.md               — eval driver 段更新
.claude/skills/andes-compare/SKILL.md               — eval entry 段更新 (heavy 引用)
scenarios/kundur/NOTES_ANDES.md                     — eval 段同步
docs/paper/andes_replication_status_2026-05-07_6axis.md  — 改 _eval_paper_specific.py 提及
paper/figures/MODELS_INDEX.md                       — 同
paper/figures/ENV_COMPARISON_V1_V2.md               — 同
paper/figure_scripts/_common.py                      — 已 fallback OK 不改 (只在 docstring 提)
paper/figure_scripts/run_all_variants.py             — 同
evaluation/paper_grade_axes.py                       — 同 (docstring only, no-op)
```

### 2.3 历史 doc refs — 留, 不改

quality_reports/{audits,plans,replications,reviews}/2026-05-{03,04,05}_*.md 系列 (~10 文件) — R0 历史,
保留不动. 在 L4 commit message 注明 "historical audits unchanged".

### 2.4 ⚠ Probe 验证 (Step 1.5)

```bash
# probes/kundur/agent_state/_ablation.py 是否活?
grep -n "_phase4_eval" probes/kundur/agent_state/_ablation.py
# 如果是 import 链 → archive _phase4_eval 会破; 改 _ablation.py import 路径或留 _phase4_eval
# 如果是 docstring/comment 引用 → 安全 archive
```
若 probe 活 → 把 `_phase4_eval.py` 留 (或软链 _legacy/_phase4_eval.py → 原位).

---

## 3. 执行步骤

### Step 1: probe verification (5 min)
```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
grep -n "_phase4_eval\|_phase3_eval_v2\|_eval_paper_grade" probes/kundur/agent_state/_ablation.py
# 决: 若 active import → 标 _phase4_eval 为"待迁但保留", 其他 archive
```

### Step 2: 物理 move (10 min)
```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
mkdir -p scenarios/kundur/_legacy_2026-04
cd scenarios/kundur

# eval scripts (10)
mv _eval_paper_grade_andes.py            _legacy_2026-04/
mv _eval_paper_grade_andes_one.py        _legacy_2026-04/
mv _eval_paper_grade_andes_parallel.py   _legacy_2026-04/
mv _eval_paper_grade_warmstart.py        _legacy_2026-04/
mv _phase3_eval_v2.py                    _legacy_2026-04/
mv _phase4_eval.py                       _legacy_2026-04/    # ⚠ 看 §2.4 决定
mv _phase9_shared_3seed_reeval.py        _legacy_2026-04/
mv _phase9_shared_5seed_reeval.py        _legacy_2026-04/
mv _phase9_shared_seed42_pilot_reeval.py _legacy_2026-04/
mv _re_eval_best_ckpts.py                _legacy_2026-04/

# 轻量 L3 (sweeps + runner, 3)
mv _v2_d0_sweep.py                       _legacy_2026-04/
mv _v2_linex_sweep.py                    _legacy_2026-04/
mv _run_v2_5seed.sh                      _legacy_2026-04/

cd ../..
echo "scenarios/kundur/ 文件: $(ls scenarios/kundur/*.py scenarios/kundur/*.sh 2>/dev/null | wc -l)"
echo "_legacy 内: $(ls scenarios/kundur/_legacy_2026-04/ | wc -l)"
```
预期: scenarios/kundur 主目录 41→28 文件, _legacy 13 文件.

### Step 3: 写 _legacy/README.md (5 min)
```markdown
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
| _eval_paper_grade_andes{,_one,_parallel,_warmstart}.py | R0 paper-grade eval | scripts/research_loop/eval_paper_spec_v2.py |
| _phase3_eval_v2.py / _phase4_eval.py | phase3/4 reeval | 同上 |
| _phase9_shared_{3seed,5seed,seed42_pilot}_reeval.py | phase9 reeval (broken) | 同上 |
| _re_eval_best_ckpts.py | best vs final 对比 (broken) | 同上 |
| _v2_d0_sweep.py / _v2_linex_sweep.py | V2 baseline sweep | (V2 verdict 已锁, 不再 sweep) |
| _run_v2_5seed.sh | V2 5seed runner | research_loop daemon |

## 历史 verdicts 引用
quality_reports/audits/2026-05-04_*.md 系列引用了这些脚本作为 eval 来源.
保留不改, 因为 verdicts 是历史快照.
```

### Step 4: path tables 更新 (15 min)

#### CLAUDE.md (项目根)
找到 "## 常见修改点定位" 表, 加新行 OR 改老行:
```
| Eval (V2 paper-spec) — 单一入口 | scripts/research_loop/eval_paper_spec_v2.py |
| 6-axis 量化 | evaluation/paper_grade_axes.py |
| Fig 6/7/8/9 生成 | paper/figure_scripts/figs6_9_ls_traces.py |
```
找到所有 `_eval_paper_specific` 提及 → 改为 `scripts/research_loop/eval_paper_spec_v2.py` (已 stash 丢, R03 重建).

#### MEMORY.md (~/.claude/projects/.../memory/MEMORY.md)
加 1 行 [LEARN]:
```
- [LEARN:refactor 2026-05-07] scenarios/kundur/ L4+L3 重构: 13 老 eval/sweep 脚本归档进
  _legacy_2026-04/. 单一 eval 入口 = scripts/research_loop/eval_paper_spec_v2.py.
  不要从 _legacy/ import.
```

#### .claude/skills/research-loop/SKILL.md
找到 "L4 单一入口" / "eval driver" 相关段, 改 path 指 `scripts/research_loop/eval_paper_spec_v2.py`.
若没现成段 → 加新段:
```
## eval 单一入口 (L4 lock-in 2026-05-07)
ANDES paper-spec eval 唯一脚本: scripts/research_loop/eval_paper_spec_v2.py.
老入口 (_eval_paper_grade_andes*, _phase{3,4,9}*_eval) 已归档进
scenarios/kundur/_legacy_2026-04/, 不要再用.
```

#### .claude/skills/andes-compare/SKILL.md
该 skill 用 _eval_paper_grade_andes 跑 5 controllers. 改 path 指新入口, 或注明 "需先调
eval_paper_spec_v2.py 跑出 paper-spec JSON, andes-compare 读 JSON 做 same-context align".

#### scenarios/kundur/NOTES_ANDES.md
找到 eval 段更新 path. 加 1 段 "L4 重构 2026-05-07: 13 脚本移 _legacy/, 唯一入口 X".

#### 其余文档 (paper/figures/MODELS_INDEX.md / ENV_COMPARISON_V1_V2.md / docs/paper/andes_replication_status_2026-05-07_6axis.md)
全文 sed 替换 `_eval_paper_specific` → `scripts/research_loop/eval_paper_spec_v2.py`:
```bash
for f in paper/figures/MODELS_INDEX.md \
         paper/figures/ENV_COMPARISON_V1_V2.md \
         docs/paper/andes_replication_status_2026-05-07_6axis.md; do
    sed -i 's|_eval_paper_specific\.py|scripts/research_loop/eval_paper_spec_v2.py|g' "$f"
done
```

### Step 5: verify (5 min)
```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"

# 1. syntax 仍 OK
python3 -m py_compile scripts/research_loop/eval_paper_spec_v2.py
python3 -m py_compile scenarios/kundur/train_andes.py
python3 -m py_compile scenarios/kundur/train_andes_v2.py

# 2. eval driver smoke (用 R04 ckpt)
PYTHONUNBUFFERED=1 /home/wya/andes_venv/bin/python scripts/research_loop/eval_paper_spec_v2.py \
    --ckpt-dir results/research_loop/r04_A_phid1p0_s42 \
    --suffix best \
    --label   ddic_smoke_post_L4 \
    --out-dir /tmp/eval_post_L4_smoke 2>&1 | tail -5

# 3. daemon log 没 "no launcher" 错 (确认 daemon 不指向已移文件)
tail -20 /tmp/rloop_daemon.log | grep -E "no launcher|skip|fail"
# (空 = OK)

# 4. state.json 仍合法
python3 -m scripts.research_loop.check_state quality_reports/research_loop/state.json

# 5. grep 残留 — 应只剩历史 verdicts 引用
grep -rln "_eval_paper_specific\|_eval_paper_grade_andes" \
    --include="*.py" --include="*.md" --include="*.sh" \
    --exclude-dir=__pycache__ --exclude-dir=_legacy_2026-04 \
    --exclude-dir=_archive_R0_2026-05-06 --exclude-dir=.git \
    | grep -v "quality_reports/audits/2026-05-04\|quality_reports/replications/2026-05-03"
# 应只剩: 我们已改的 nav 文档 (CLAUDE.md / SKILL.md / MEMORY.md / NOTES_ANDES.md)
```

### Step 6: commit + push (5 min)
```bash
git add scenarios/kundur/_legacy_2026-04/
git add scenarios/kundur/{NOTES_ANDES.md}  # 改了
git add CLAUDE.md MEMORY.md .claude/skills/{research-loop,andes-compare}/SKILL.md
git add paper/figures/{MODELS_INDEX.md,ENV_COMPARISON_V1_V2.md}
git add docs/paper/andes_replication_status_2026-05-07_6axis.md
# 别 add 历史 audits/replications/ — 它们引用归档脚本是历史正确

git status  # verify

git commit -m "$(cat <<'EOF'
refactor(scenarios/kundur): consolidate ANDES eval to single-source [L4 + 轻量 L3]

研究循环 R03 verdict 暴露 5+ 并存 eval 入口混乱; R04 build paper-spec 闭环
后确立 scripts/research_loop/eval_paper_spec_v2.py 为唯一入口. 13 个 R0 期
(2026-04~05) eval/sweep 脚本归档.

文件移动 (13):
  · 4 _eval_paper_grade_andes{,_one,_parallel,_warmstart}
  · 5 _phase{3,4,9}*_eval{,_v2,_reeval}
  · _re_eval_best_ckpts (已 broken — _eval_paper_specific 在 stash 事故丢)
  · 2 _v2_{d0,linex}_sweep + _run_v2_5seed.sh

Path tables 更新:
  · CLAUDE.md / MEMORY.md / NOTES_ANDES.md 路径表指新入口
  · .claude/skills/research-loop/SKILL.md L4 段加 lock-in
  · .claude/skills/andes-compare/SKILL.md eval 段同步
  · paper/figures/{MODELS_INDEX,ENV_COMPARISON_V1_V2}.md / docs/paper/*.md sed 替换

Verify:
  · eval_paper_spec_v2.py smoke on R04 ckpt PASS
  · daemon log 无 "no launcher" 错
  · state.json schema OK
  · 残留引用仅历史 verdicts (audits/2026-05-04, replications/2026-05-03)

Don't-do:
  · train_*.py / evaluate_*.py 主入口不动 (daemon 仍依赖)
  · disturbance_protocols / scenario_loader / config_simulink 不动 (core)
  · results/ 老 dir 不动 (历史快照)

scenarios/kundur/ 文件: 41 → 28 active + 13 _legacy/.
EOF
)"

git push origin main
```

---

## 4. 不做的事 (out of scope, 留给未来)

- ❌ `train_andes.py / train_andes_v2.py / train_andes_v3.py / train_ode.py / train_simulink.py` — daemon 在用, 主入口不动
- ❌ `evaluate_andes.py / evaluate_simulink.py / evaluate_ode.py` — 历史 evaluate 入口, 暂不动
- ❌ `disturbance_protocols.py / scenario_loader.py / workspace_vars.py / calibrate.py / config*.py` — core, 不动
- ❌ `results/andes_phase{4,9}*` 等老 dir 重整 (66 个) — 占盘但不影响代码, 留 R06+ 做
- ❌ 改 verdict 历史 markdown (audits/replications/2026-05-{03,04,05}) — 是历史快照, 不改

---

## 5. 失败模式

| 失败 | 处理 |
|---|---|
| Step 1 probe 是活的 | 把 `_phase4_eval.py` 留主目录, 其他 12 个仍 archive. README 加 note |
| Step 4 sed 替换破坏 markdown 格式 | git diff 看; 手工修 |
| Step 5 eval smoke 失败 | git revert 整个 commit; 不破 |
| Step 5 daemon 报 "no launcher" | 说明 daemon state.pending 还指老 path; 改 state.json (但 R04 已完, 应不会) |
| Step 6 push 被拒 (远程更新) | git pull --rebase main; 解冲突; push |

---

## 6. R05 衔接

L4 commit 完, 下一 round (R05) 的 plan 必须用新 eval 入口:
- 现 `quality_reports/research_loop/round_04_plan.md` §L4 副线 段已规划, R04 verdict 时同步落 R05 plan.
- R05 候选 eval 段 cmd 必为 `scripts/research_loop/eval_paper_spec_v2.py --ckpt-dir ... --label ... --out-dir ...`.

---

## 7. 一行接续

新会话进来粘:
> 续 L4: 读 `quality_reports/handoff/2026-05-07_L4_eval_consolidation_handoff.md` → §0 5 步 → §1 pre-flight → §3 6 step → §6 push.

---

## 8. 状态快照 (写 handoff 时)

- round_idx: 4 (R04 daemon 跑 7/8 候选, ~30 min wall)
- L1 done: SKILL.md 加 verdict 6-段模板 (`.claude/skills/research-loop/SKILL.md`)
- L2 done: `paper/figures/_archive_R0_2026-05-06/` 归 8 R0 baseline
- L4 准备: `scripts/research_loop/eval_paper_spec_v2.py` 已 build + smoke (R02/R03 ckpt 跑通)
- 7 R04 候选 daemon 跑中: V3 smoke + 5 PHI_D=1.0 + obs9 smoke
- ScheduleWakeup 19:12 写 R04 verdict
- adaptive baseline ✅ done: 6-axis=0.010 (=no_ctrl, **解耦结论 = 实现/平台问题**)

---

*生成时间: 2026-05-07 ~17:50 UTC+8*
*生成者: research-loop AI agent (R04 daemon 跑期间)*
