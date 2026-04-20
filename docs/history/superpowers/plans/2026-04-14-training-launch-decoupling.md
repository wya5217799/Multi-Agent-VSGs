# 训练启动解耦计划

**日期**: 2026-04-14  
**背景**: 启动训练消耗大量 token，根因是训练启动无独立控制面、输出提交时机早于 MATLAB 连接、launch_training.ps1 编码不兼容。  
**目标**: 短期消除硬故障，中期建立训练 / 建模独立控制面。

---

## 上下文（新对话必读）

本计划源自三轮讨论：

- **根因 1（硬故障）**: `launch_training.ps1` UTF-8 无 BOM + Windows PowerShell 5.1，中文字符触发 `TerminatorExpectedAtEndOfString`
- **根因 2（结构性）**: `training_status.json` 写 `running` 发生在 L235（`train_simulink.py`），此时 `env.reset()` 尚未调用（L334），MATLAB 未连接。连接失败留下孤立 run 目录
- **根因 3（认知开销）**: agent 启动一次训练需读 5-8 个文件拼事实，无单一查询入口
- **已确认正在运行的训练**: Kundur PID 10728，NE39 PID 49608，本计划改动不影响它们

---

## Phase 1：立即落地（低风险，不依赖训练结束）

### Step 1.1 — 修 launch_training.ps1 编码

**根本原因**: UTF-8 无 BOM，不是中文字符本身  
**文件**: `scripts/launch_training.ps1`  
**修法**（在 Git Bash 执行）:

```bash
powershell -Command "
\$content = Get-Content -Path 'scripts/launch_training.ps1' -Raw -Encoding UTF8
Set-Content -Path 'scripts/launch_training.ps1' -Value \$content -Encoding utf8BOM
"
```

**验证**: 从 Git Bash 执行 `powershell -File scripts/launch_training.ps1 kundur 1`，观察能否不报 parser 错误（进程起来即验证通过，不需要 MATLAB）。

---

### Step 1.2 — 把输出提交移到 bootstrap 成功之后

**影响文件**:
- `scenarios/kundur/train_simulink.py`
- `scenarios/new_england/train_simulink.py`

**当前错误顺序**（以 Kundur 为例，NE39 同理）:

```
train()
  L228  run_dir.mkdir() × 2
  L235  write_training_status("running")   ← 问题：MATLAB 未连接
  L245  make_env()
  L246  SACAgent()
  L269  auto-resume scan
  L300  ArtifactWriter()
  L310  save_run_meta()
  L314  load_or_create_log()
  L334  env.reset()                        ← MATLAB 第一次接触在这里
  L327  for ep in range(episodes):
```

**目标顺序**:

```
train()
  make_env()
  SACAgent()
  auto-resume scan + agent.load(ckpt)     ← 纯 Python，无副作用

  obs, _ = env.reset()                    ← MATLAB 连接、load_model、warmup
                                           ← 此处失败 → 直接 raise，无孤立文件

  run_dir.mkdir() × 2                     ← 以下全部移到 bootstrap 成功后
  write_training_status("running")
  ArtifactWriter()
  save_run_meta()
  load_or_create_log()

  for ep in range(start_episode, end_episode):   ← 训练循环不变
```

**具体改动步骤**（Kundur，NE39 同理）:

1. 把 L228-L243（`run_dir.mkdir` + `write_training_status`）剪切，暂放在注释里
2. 保留 L245（`make_env`）、L246（`SACAgent`）、L260-L293（auto-resume）原位
3. 在 L293（auto-resume 结束）之后、L327（训练循环）之前，按以下顺序重新插入：

```python
    # ── Phase B: Bootstrap backend ──────────────────────────────────────────
    # 第一次 env.reset() 触发 MATLAB 启动 / load_model / warmup。
    # 若此处失败，直接 raise；run_dir 尚未创建，无孤立副作用。
    dist_mag = np.random.uniform(env.DIST_MIN, env.DIST_MAX)
    if np.random.random() > 0.5:
        dist_mag = -dist_mag
    obs, _ = env.reset(options={"disturbance_magnitude": dist_mag})

    # ── Phase C: Commit outputs（只有 backend 就绪后才写）───────────────────
    if hasattr(args, "run_dir"):
        run_dir = Path(args.run_dir)
        (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    else:
        run_dir = Path(args.checkpoint_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[train] run_id={run_id}, output={run_dir}")

    write_training_status(run_dir, {
        "status": "running",
        "run_id": run_id,
        "scenario": "kundur",        # NE39 改为 "ne39"
        "episodes_total": args.episodes,
        "episodes_done": 0,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "last_reward": None,
    })
    os.makedirs(args.checkpoint_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.log_file), exist_ok=True)
    _log_dir = os.path.dirname(args.log_file)
    fresh_run = start_episode == 0
    writer = ArtifactWriter(_log_dir, reset_existing=fresh_run)
    writer.log_event(start_episode, "training_start", {
        "mode": args.mode,
        "start_episode": start_episode,
        "end_episode": start_episode + args.episodes,
    })
    meta_dir = getattr(args, "run_dir", args.checkpoint_dir)
    save_run_meta(meta_dir, args, _cfg_module)
    monitor = TrainingMonitor()
    log = load_or_create_log(args.log_file, fresh=fresh_run)
```

4. 训练循环第一个 `ep` 的 `env.reset()` 调用（原 L334）需要跳过，因为 Phase B 已经做了第一次 reset。改法：

```python
    # Phase B 已完成第 0 集的 reset，直接进入 step loop。
    # 之后每集从 ep = start_episode + 1 开始重新 reset。
    for ep in range(start_episode, end_episode):
        if ep > start_episode:                      # ← 新增这一行
            dist_mag = np.random.uniform(env.DIST_MIN, env.DIST_MAX)
            if np.random.random() > 0.5:
                dist_mag = -dist_mag
            obs, _ = env.reset(options={"disturbance_magnitude": dist_mag})
        # ... 其余 step loop 不变
```

**注意**: `run_id` 和 `run_dir` 变量在 Phase C 才赋值，但 `args.run_id` 在 `parse_args()` 里已生成，可以提前用。确认 `print(f"[train] run_id=...")` 调用时 `run_dir` 已存在。

**验证**: 用 `--mode standalone --episodes 2` 跑一次，确认正常完成。再用 `--mode simulink --episodes 1` 跑，确认 run 目录在 warmup 成功后才出现。

---

### Step 1.3 — 新增 get_training_launch_status()

**新文件**: `engine/training_launch.py`

```python
"""engine/training_launch.py — Lightweight training launch control plane.

Provides get_training_launch_status(scenario_id) as the single query
entry point before launching training.  Reads from existing harness
JSON (no new fact sources).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from engine.harness_reference import load_scenario_reference

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_TRAIN_ENTRIES = {
    "kundur": "scenarios/kundur/train_simulink.py",
    "ne39":   "scenarios/new_england/train_simulink.py",
}

_MODEL_PATHS = {
    "kundur": "scenarios/kundur/simulink_models/kundur_vsg.slx",
    "ne39":   "scenarios/new_england/simulink_models/NE39bus_v2.slx",
}


def get_training_launch_status(scenario_id: str) -> dict[str, Any]:
    """One-call answer to: can I launch training for this scenario?

    Returns a dict with all facts needed to decide and execute a launch.
    Does NOT start any process; does NOT write any files.
    """
    # --- 场景是否合法 ---
    try:
        ref = load_scenario_reference(scenario_id)
    except (ValueError, FileNotFoundError):
        return {"supported": False, "scenario_id": scenario_id,
                "error": "unknown scenario_id"}

    facts = {item["key"]: item["value"] for item in ref.get("reference_items", [])}

    train_entry  = facts.get("training_entry",
                             _TRAIN_ENTRIES.get(scenario_id, ""))
    model_name   = facts.get("model_name", "")

    # --- 模型文件是否存在 ---
    slx_rel      = _MODEL_PATHS.get(scenario_id, "")
    slx_abs      = _PROJECT_ROOT / slx_rel
    model_exists = slx_abs.exists() if slx_rel else None

    # --- 最近一次 run 状态 ---
    runs_root    = _PROJECT_ROOT / "results" / f"sim_{scenario_id}" / "runs"
    latest_run_id, latest_run_status, ckpt_count, resume_candidate = \
        _inspect_latest_run(runs_root)

    # --- 是否有正在运行的同场景进程 ---
    active_pid = _find_active_pid(train_entry)

    # --- 推荐命令 ---
    cmd = (f"python {train_entry} --mode simulink --episodes 500"
           if train_entry else "")

    return {
        "supported":         True,
        "scenario_id":       scenario_id,
        "train_entry":       train_entry,
        "model_name":        model_name,
        "model_file_exists": model_exists,
        "latest_run_id":     latest_run_id,
        "latest_run_status": latest_run_status,
        "latest_run_checkpoint_count": ckpt_count,
        "active_pid":        active_pid,
        "resume_candidate":  resume_candidate,
        "recommended_command": cmd,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _inspect_latest_run(runs_root: Path):
    """Find the most-recently-modified run dir and summarise its state."""
    import json

    if not runs_root.is_dir():
        return None, None, 0, None

    run_dirs = sorted(
        [d for d in runs_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not run_dirs:
        return None, None, 0, None

    latest = run_dirs[0]
    status_file = latest / "training_status.json"
    status = None
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8")).get("status")
        except Exception:
            pass

    ckpt_dir = latest / "checkpoints"
    ep_ckpts = sorted(
        [f for f in (ckpt_dir.iterdir() if ckpt_dir.is_dir() else [])
         if f.name.startswith("ep") and f.name.endswith(".pt")],
        key=lambda f: int(f.stem[2:]),
    )
    ckpt_count = len(ep_ckpts)
    resume_candidate = str(ep_ckpts[-1]) if ep_ckpts else (
        str(ckpt_dir / "final.pt") if (ckpt_dir / "final.pt").exists() else None
    )

    return latest.name, status, ckpt_count, resume_candidate


def _find_active_pid(train_entry: str) -> int | None:
    """Return PID of a running python process matching train_entry, or None."""
    if not train_entry:
        return None
    pattern = train_entry.replace("/", "\\").split("\\")[-1]   # e.g. train_simulink.py
    try:
        import subprocess, json
        result = subprocess.run(
            ["powershell", "-Command",
             f"Get-WmiObject Win32_Process -Filter \"name='python.exe'\" "
             f"| Where-Object {{ $_.CommandLine -like '*{pattern}*' }} "
             f"| Select-Object -First 1 -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        pid_str = result.stdout.strip()
        return int(pid_str) if pid_str.isdigit() else None
    except Exception:
        return None
```

**验证**:
```python
from engine.training_launch import get_training_launch_status
import json
print(json.dumps(get_training_launch_status("kundur"), indent=2))
print(json.dumps(get_training_launch_status("ne39"),   indent=2))
```
输出应包含 `train_entry`、`model_file_exists: true`、`active_pid`（当前训练 PID）。

---

### Step 1.4 — 更新 CLAUDE.md harness 读取规则

在 CLAUDE.md 顶部 harness 规则改为：

```diff
- > **⚠ HARNESS FIRST — 行动前必读**
- > 任何行动前，先定位并读取 harness（`engine/harness_reference.py`）。
+ > **⚠ HARNESS FIRST**
+ > 修改合约 / 配置 / 测试相关代码前，先读 harness（`engine/harness_reference.py`）。
+ > **纯启动训练**：调用 `get_training_launch_status(scenario_id)` 即可，无需手动读 harness 文件。
```

---

## Phase 2：结构解耦（等当前 500 集训练结束后执行）

### Step 2.1 — scenario_registry.py（harness JSON 的只读投影）

**约束**：文件内**不得出现任何字面量场景常量**（n_agents、dt、t_episode 等），所有值从 `load_scenario_reference()` 派生。

```python
# engine/scenario_registry.py
"""Thin read-only projection of harness_reference.json for the training plane.

This file holds NO constants of its own.  All facts derive from harness JSON.
"""
from engine.harness_reference import load_scenario_reference

def resolve_training_spec(scenario_id: str) -> dict:
    ref = load_scenario_reference(scenario_id)
    facts = {item["key"]: item["value"] for item in ref["reference_items"]}
    return {
        "scenario_id":   scenario_id,
        "train_entry":   facts["training_entry"],
        "model_name":    facts["model_name"],
        "n_agents":      facts["n_agents"],
        "dt":            facts["dt"],
        "t_episode":     facts["t_episode"],
    }

def resolve_modeling_spec(scenario_id: str) -> dict:
    ref = load_scenario_reference(scenario_id)
    facts = {item["key"]: item["value"] for item in ref["reference_items"]}
    return {
        "scenario_id":      scenario_id,
        "model_name":       facts["model_name"],
        "disturbance_var1": facts.get("disturbance_var1"),
        "disturbance_var2": facts.get("disturbance_var2"),
    }
```

### Step 2.2 — training_pipeline.py（提取 Kundur / NE39 共同训练主流程）

**抽取内容**（两个 train_simulink.py 都有的重复部分）：

- auto-resume scan 逻辑
- Phase B bootstrap（env.reset）
- Phase C commit（write_training_status、ArtifactWriter、save_run_meta、load_or_create_log）
- 主训练循环骨架（per-step：select_actions → store → update → log）
- eval 间隔逻辑
- checkpoint 间隔逻辑
- monitor 检查
- 最终保存 + 状态写入

**adapter 接口**（每个场景只保留差异部分）：

```python
# scenarios/kundur/training_adapter.py
class KundurTrainingAdapter:
    scenario_id = "kundur"

    def make_env(self, args) -> gym.Env: ...
    def evaluate(self, env, agent, n_eval=3) -> dict: ...
    def sample_disturbance(self, env) -> float: ...
    def apply_disturbance(self, env, magnitude: float) -> None: ...
    def scenario_constants(self) -> dict: ...   # N_AGENTS, OBS_DIM 等
```

### Step 2.3 — launch_training.ps1 降级为薄包装

改成只做：

```powershell
param([string]$Scenario = "both", [int]$Episodes = 500)
$PYTHON = 'C:\Users\27443\miniconda3\envs\andes_env\python.exe'
$Root   = 'C:\Users\27443\Desktop\Multi-Agent  VSGs'

function Launch($s) {
    $cmd = "& '$PYTHON' '$Root\scripts\train_launch.py' --scenario $s --episodes $Episodes"
    Start-Process powershell -WorkingDirectory $Root -ArgumentList '-NoExit','-Command',$cmd
}

if ($Scenario -in "kundur","both") { Launch "kundur" }
if ($Scenario -in "ne39","both")   { Launch "ne39" }
```

业务逻辑全部移入 `scripts/train_launch.py`。

### Step 2.4 — 新增 scripts/train_launch.py（唯一训练入口）

```python
# scripts/train_launch.py
"""Single CLI entry point for launching Simulink training.

Usage:
    python scripts/train_launch.py --scenario kundur --episodes 500
    python scripts/train_launch.py --scenario ne39   --episodes 500
    python scripts/train_launch.py --scenario both   --episodes 500
    python scripts/train_launch.py --scenario kundur --dry-run
"""
import argparse, subprocess, sys
from pathlib import Path
from engine.training_launch import get_training_launch_status

PYTHON = r"C:\Users\27443\miniconda3\envs\andes_env\python.exe"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=["kundur", "ne39", "both"], required=True)
    p.add_argument("--episodes", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    scenarios = ["kundur", "ne39"] if args.scenario == "both" else [args.scenario]

    for sid in scenarios:
        status = get_training_launch_status(sid)
        if not status["supported"]:
            print(f"[SKIP] {sid}: {status.get('error')}")
            continue
        if status["active_pid"]:
            print(f"[SKIP] {sid}: already running (PID {status['active_pid']})")
            continue
        cmd = [PYTHON, status["train_entry"],
               "--mode", "simulink", "--episodes", str(args.episodes)]
        print(f"[launch] {sid}: {' '.join(cmd)}")
        if not args.dry_run:
            subprocess.Popen(cmd, cwd=str(Path(__file__).parents[1]))

if __name__ == "__main__":
    main()
```

---

## 验证检查清单

### Phase 1 完成标准

- [ ] `powershell -File scripts/launch_training.ps1 kundur 1` 不报 parser 错误
- [ ] standalone 模式 2 集跑完，run 目录**在第一步 env.reset 成功后**才出现
- [ ] `get_training_launch_status("kundur")` 返回 active_pid = 当前 PID（训练进行中时）
- [ ] `get_training_launch_status("ne39")` 同上
- [ ] 现有 pytest 全绿（`pytest tests/ -x -q`）

### Phase 2 完成标准

- [ ] `scenario_registry.py` 通过 grep 验证无字面量常量（`grep -n "[0-9]" engine/scenario_registry.py`）
- [ ] `python scripts/train_launch.py --scenario both --dry-run` 打印两条 launch 命令，不实际启动进程
- [ ] Kundur / NE39 训练各跑 5 集，输出目录结构与 Phase 1 前一致
- [ ] 现有 pytest 全绿

---

## 文件改动汇总

| 文件 | 动作 | Phase |
|------|------|-------|
| `scripts/launch_training.ps1` | 加 UTF-8 BOM | 1.1 |
| `scenarios/kundur/train_simulink.py` | 调整 commit 顺序 | 1.2 |
| `scenarios/new_england/train_simulink.py` | 同上 | 1.2 |
| `engine/training_launch.py` | 新增 | 1.3 |
| `CLAUDE.md` | 修改 harness 规则范围 | 1.4 |
| `engine/scenario_registry.py` | 新增（薄投影） | 2.1 |
| `engine/training_pipeline.py` | 新增 | 2.2 |
| `scenarios/kundur/training_adapter.py` | 新增 | 2.2 |
| `scenarios/new_england/training_adapter.py` | 新增 | 2.2 |
| `scripts/train_launch.py` | 新增 | 2.4 |
| `scripts/launch_training.ps1` | 降级为薄包装 | 2.3 |
