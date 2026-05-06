# Research Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现自动研究循环 (daemon + AI agent + state.json) 跑 ANDES 6-axis recovery 自治化.

**Architecture:** 3 层 (AI 会话 + state 持久化 + WSL daemon). 全部跨层 file-only. caveman 中文文档. 详见 `quality_reports/specs/2026-05-07_research_loop_design.md`.

**Tech Stack:** Python 3 (state schema + check), bash (daemon + backends), pytest (Python tests), shellcheck + plain bash assertions (shell tests). Reuse: `evaluation/paper_grade_axes.py`, `templates/{plan,verdict}-minimal.md`, `/andes-compare`.

**Spec**: `quality_reports/specs/2026-05-07_research_loop_design.md` (18 节)

---

## File Structure (lock decomposition)

**新建**:

```
scripts/research_loop/
├── __init__.py
├── check_state.py              # state.json schema 检查 (Python)
├── state_io.py                 # state.json 读写 + 锁 (Python, daemon+AI 共用)
├── k_max_calc.py               # budget tier → K_max 算
└── handoff_index.py            # handoffs/INDEX.md 维护

scripts/backends/
├── _resource_check.sh          # free -g / nvidia-smi 抽象
├── andes_cpu.sh                # ANDES TDS launcher (今日)
├── sac_gpu.sh                  # stub: 未来 GPU
└── matlab_session.sh           # stub: 未来 Simulink

scripts/research_loop_daemon.sh  # 主守护循环

templates/
├── plan-caveman.md             # caveman 计划模板
└── verdict-caveman.md          # caveman verdict 模板

.claude/skills/research-loop/
└── SKILL.md                    # AI agent 入口 (项目本地 skill)

quality_reports/research_loop/
├── README.md                   # 目录说明 + 索引
├── state.json                  # 运行时状态 (空启动)
├── handoffs/
│   └── INDEX.md
├── incidents/
├── audits/
└── pivots/

tests/research_loop/
├── test_check_state.py         # schema 检查单测
├── test_state_io.py            # 读写锁单测
├── test_k_max_calc.py          # 算 K 单测
├── test_handoff_index.py       # INDEX 更新单测
├── test_resource_check.sh      # bash 单测
├── test_andes_cpu.sh           # bash 单测 (mock python)
└── test_daemon_dry_run.sh      # daemon dry-run integration
```

**修改**:
- `quality_reports/research_loop/handoffs/INDEX.md` (新建后日常追加)
- `MEMORY.md` (注册 research-loop skill 在 user & approach 节)

---

## Task 1: state.json schema + check_state.py

**Files:**
- Create: `scripts/research_loop/__init__.py`
- Create: `scripts/research_loop/check_state.py`
- Create: `tests/research_loop/__init__.py`
- Create: `tests/research_loop/test_check_state.py`
- Create: `tests/research_loop/fixtures/state_v1_legal.json`
- Create: `tests/research_loop/fixtures/state_missing_field.json`
- Create: `tests/research_loop/fixtures/state_old_version.json`

- [ ] **Step 1.1: 写 fixture 合法 state.json**

`tests/research_loop/fixtures/state_v1_legal.json`:
```json
{
  "version": "1.0",
  "round_idx": 0,
  "started_at_utc": "2026-05-07T00:00:00Z",
  "budget": {
    "rounds_used": 0, "rounds_cap": 20,
    "wall_hr_used": 0.0, "wall_hr_cap": 72,
    "tokens_used": 0, "tokens_cap": 800000
  },
  "ram": { "free_gb_min_hard": 4, "per_run_estimate_gb": 2.5 },
  "gates": { "G1": null, "G2": null, "G3": null, "G4": null, "G5": null, "G6": null },
  "stagnation": { "last_3_overall": [], "delta_pct": null },
  "pending": [],
  "running": [],
  "done": [],
  "killed": [],
  "ai_session_log": [],
  "handoff_pointers": []
}
```

- [ ] **Step 1.2: 写 fixture 缺字段 state.json**

`tests/research_loop/fixtures/state_missing_field.json` (缺 `budget`):
```json
{
  "version": "1.0",
  "round_idx": 0,
  "started_at_utc": "2026-05-07T00:00:00Z",
  "ram": { "free_gb_min_hard": 4, "per_run_estimate_gb": 2.5 },
  "gates": { "G1": null, "G2": null, "G3": null, "G4": null, "G5": null, "G6": null },
  "stagnation": { "last_3_overall": [], "delta_pct": null },
  "pending": [], "running": [], "done": [], "killed": [],
  "ai_session_log": [], "handoff_pointers": []
}
```

- [ ] **Step 1.3: 写 fixture 老 version state.json**

`tests/research_loop/fixtures/state_old_version.json` (version="0.9"):
```json
{ "version": "0.9", "round_idx": 0 }
```

- [ ] **Step 1.4: 写 failing test for check_state**

`tests/research_loop/test_check_state.py`:
```python
"""check_state.py 单测."""
import json
from pathlib import Path
import pytest

from scripts.research_loop.check_state import (
    check_state_dict,
    StateSchemaError,
    SUPPORTED_VERSIONS,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_legal_state_passes():
    state = _load("state_v1_legal.json")
    assert check_state_dict(state) is None  # no exception


def test_missing_field_raises():
    state = _load("state_missing_field.json")
    with pytest.raises(StateSchemaError, match="budget"):
        check_state_dict(state)


def test_old_version_raises():
    state = _load("state_old_version.json")
    with pytest.raises(StateSchemaError, match="version"):
        check_state_dict(state)


def test_supported_versions_documented():
    assert "1.0" in SUPPORTED_VERSIONS
```

- [ ] **Step 1.5: 跑测试验证 fail**

```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_check_state.py -v
```
Expected: ImportError / FAIL (`scripts.research_loop` not exist).

- [ ] **Step 1.6: 实现 check_state.py**

`scripts/research_loop/__init__.py`: 空文件.

`scripts/research_loop/check_state.py`:
```python
"""state.json schema 检查 (硬契约).

Daemon + AI 每写 state.json 前调 check_state_dict(state). schema 见
quality_reports/specs/2026-05-07_research_loop_design.md §4.
"""

from __future__ import annotations

SUPPORTED_VERSIONS = {"1.0"}

REQUIRED_TOP = {
    "version", "round_idx", "started_at_utc",
    "budget", "ram", "gates", "stagnation",
    "pending", "running", "done", "killed",
    "ai_session_log", "handoff_pointers",
}
REQUIRED_BUDGET = {
    "rounds_used", "rounds_cap",
    "wall_hr_used", "wall_hr_cap",
    "tokens_used", "tokens_cap",
}
REQUIRED_RAM = {"free_gb_min_hard", "per_run_estimate_gb"}
REQUIRED_GATES = {"G1", "G2", "G3", "G4", "G5", "G6"}
REQUIRED_STAGN = {"last_3_overall", "delta_pct"}


class StateSchemaError(ValueError):
    pass


def check_state_dict(state: dict) -> None:
    """Raise StateSchemaError on schema violation. Return None on legal."""
    if not isinstance(state, dict):
        raise StateSchemaError("state must be dict")

    version = state.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise StateSchemaError(
            f"version {version!r} not in SUPPORTED_VERSIONS={SUPPORTED_VERSIONS}"
        )

    missing_top = REQUIRED_TOP - set(state.keys())
    if missing_top:
        raise StateSchemaError(f"missing top-level keys: {sorted(missing_top)}")

    for sub_key, required in [
        ("budget", REQUIRED_BUDGET),
        ("ram", REQUIRED_RAM),
        ("gates", REQUIRED_GATES),
        ("stagnation", REQUIRED_STAGN),
    ]:
        sub = state[sub_key]
        if not isinstance(sub, dict):
            raise StateSchemaError(f"{sub_key} must be dict")
        missing = required - set(sub.keys())
        if missing:
            raise StateSchemaError(f"{sub_key} missing: {sorted(missing)}")

    for list_key in ["pending", "running", "done", "killed",
                     "ai_session_log", "handoff_pointers"]:
        if not isinstance(state[list_key], list):
            raise StateSchemaError(f"{list_key} must be list")


def check_state_file(path: str) -> None:
    """Read JSON file and check."""
    import json
    with open(path) as f:
        state = json.load(f)
    check_state_dict(state)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: check_state.py <state.json>", file=sys.stderr)
        sys.exit(2)
    try:
        check_state_file(sys.argv[1])
        print("OK")
    except StateSchemaError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
```

`tests/research_loop/__init__.py`: 空文件.

- [ ] **Step 1.7: 跑测试验证 PASS**

```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_check_state.py -v
```
Expected: 4 passed.

- [ ] **Step 1.8: Commit**

```bash
git add scripts/research_loop/__init__.py scripts/research_loop/check_state.py \
       tests/research_loop/__init__.py tests/research_loop/test_check_state.py \
       tests/research_loop/fixtures/
git commit -m "feat(research-loop): state.json schema check (T1)"
```

---

## Task 2: state_io.py — 锁 + 读写

**Files:**
- Create: `scripts/research_loop/state_io.py`
- Create: `tests/research_loop/test_state_io.py`

- [ ] **Step 2.1: 写 failing test**

`tests/research_loop/test_state_io.py`:
```python
"""state_io.py 锁 + 读写单测."""
import json
import os
from pathlib import Path

import pytest

from scripts.research_loop.state_io import (
    read_state, write_state, with_state_lock, default_empty_state,
)
from scripts.research_loop.check_state import StateSchemaError


def test_default_empty_state_passes_check():
    """Empty state must pass schema (起步态)."""
    from scripts.research_loop.check_state import check_state_dict
    check_state_dict(default_empty_state())


def test_round_trip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = default_empty_state()
    s["round_idx"] = 5
    write_state(p, s)
    s2 = read_state(p)
    assert s2["round_idx"] == 5


def test_write_invalid_state_raises(tmp_path: Path):
    p = tmp_path / "state.json"
    bad = {"version": "0.0"}
    with pytest.raises(StateSchemaError):
        write_state(p, bad)


def test_lock_roundtrip(tmp_path: Path):
    """Lock 必须 acquire + release 不挂."""
    p = tmp_path / "state.json"
    write_state(p, default_empty_state())
    with with_state_lock(p):
        s = read_state(p)
        s["round_idx"] += 1
        write_state(p, s)
    assert read_state(p)["round_idx"] == 1
```

- [ ] **Step 2.2: 跑 fail**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_state_io.py -v
```
Expected: ImportError.

- [ ] **Step 2.3: 实现 state_io.py**

`scripts/research_loop/state_io.py`:
```python
"""state.json 读写 + 文件锁 (daemon + AI 共用)."""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import time
from pathlib import Path
from typing import Iterator

from scripts.research_loop.check_state import check_state_dict


def default_empty_state() -> dict:
    """起步空 state, 通过 schema 检查."""
    return {
        "version": "1.0",
        "round_idx": 0,
        "started_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "budget": {
            "rounds_used": 0, "rounds_cap": 20,
            "wall_hr_used": 0.0, "wall_hr_cap": 72,
            "tokens_used": 0, "tokens_cap": 800000,
        },
        "ram": {"free_gb_min_hard": 4, "per_run_estimate_gb": 2.5},
        "gates": {"G1": None, "G2": None, "G3": None, "G4": None, "G5": None, "G6": None},
        "stagnation": {"last_3_overall": [], "delta_pct": None},
        "pending": [],
        "running": [],
        "done": [],
        "killed": [],
        "ai_session_log": [],
        "handoff_pointers": [],
    }


def read_state(path: Path | str) -> dict:
    """读 state.json, 校验 schema."""
    p = Path(path)
    with open(p) as f:
        state = json.load(f)
    check_state_dict(state)
    return state


def write_state(path: Path | str, state: dict) -> None:
    """写 state.json (写前校验, atomic rename)."""
    check_state_dict(state)
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


@contextlib.contextmanager
def with_state_lock(path: Path | str, timeout_s: float = 30.0) -> Iterator[None]:
    """简文件锁: 创建 <path>.lock, 写完删除. POSIX-only.

    daemon + AI 都通过它互斥. 不用 fcntl.flock 因 cross-platform 复杂.
    """
    p = Path(path)
    lock = p.with_suffix(p.suffix + ".lock")
    deadline = time.time() + timeout_s
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.time() > deadline:
                raise TimeoutError(f"state lock {lock} held > {timeout_s}s")
            time.sleep(0.5)
    try:
        yield
    finally:
        try:
            os.unlink(str(lock))
        except FileNotFoundError:
            pass
```

- [ ] **Step 2.4: 跑 PASS**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_state_io.py -v
```
Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add scripts/research_loop/state_io.py tests/research_loop/test_state_io.py
git commit -m "feat(research-loop): state_io read/write/lock (T2)"
```

---

## Task 3: k_max_calc.py — budget tier → K_max

**Files:**
- Create: `scripts/research_loop/k_max_calc.py`
- Create: `tests/research_loop/test_k_max_calc.py`

- [ ] **Step 3.1: 写 failing test**

`tests/research_loop/test_k_max_calc.py`:
```python
"""k_max_calc 单测 (并行启发式)."""
import pytest

from scripts.research_loop.k_max_calc import calc_k_max, calc_budget_pct


def test_budget_pct_fresh():
    assert calc_budget_pct(rounds_used=0, rounds_cap=20,
                            wall_hr_used=0, wall_hr_cap=72,
                            tokens_used=0, tokens_cap=800000) == 1.0


def test_budget_pct_takes_min():
    """三维 min: rounds 50%, hr 80%, tok 30% → 30%."""
    pct = calc_budget_pct(
        rounds_used=10, rounds_cap=20,        # 50% remain
        wall_hr_used=14.4, wall_hr_cap=72,    # 80% remain
        tokens_used=560000, tokens_cap=800000 # 30% remain
    )
    assert abs(pct - 0.30) < 1e-3


def test_k_max_high_budget_returns_4():
    assert calc_k_max(0.50) == 4


def test_k_max_mid_budget_returns_2():
    assert calc_k_max(0.30) == 2


def test_k_max_low_budget_returns_1():
    assert calc_k_max(0.10) == 1


def test_k_max_boundary_high():
    assert calc_k_max(0.40) == 2  # 0.40 是 mid 上限
    assert calc_k_max(0.4001) == 4


def test_k_max_boundary_low():
    assert calc_k_max(0.20) == 1
    assert calc_k_max(0.2001) == 2
```

- [ ] **Step 3.2: 跑 fail**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_k_max_calc.py -v
```
Expected: ImportError.

- [ ] **Step 3.3: 实现 k_max_calc.py**

`scripts/research_loop/k_max_calc.py`:
```python
"""Budget tier → K_max 启发式. AI 可 override (写 rationale)."""

from __future__ import annotations


def calc_budget_pct(
    rounds_used: int, rounds_cap: int,
    wall_hr_used: float, wall_hr_cap: float,
    tokens_used: int, tokens_cap: int,
) -> float:
    """min over 三维剩余比例 (0-1)."""
    return min(
        max(0.0, (rounds_cap - rounds_used) / rounds_cap),
        max(0.0, (wall_hr_cap - wall_hr_used) / wall_hr_cap),
        max(0.0, (tokens_cap - tokens_used) / tokens_cap),
    )


def calc_k_max(budget_pct: float) -> int:
    """启发式: 默认 tier 切片. AI override 走 rationale, 不走这."""
    if budget_pct > 0.40:
        return 4
    if budget_pct > 0.20:
        return 2
    return 1
```

- [ ] **Step 3.4: 跑 PASS**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_k_max_calc.py -v
```
Expected: 7 passed.

- [ ] **Step 3.5: Commit**

```bash
git add scripts/research_loop/k_max_calc.py tests/research_loop/test_k_max_calc.py
git commit -m "feat(research-loop): k_max calc by budget tier (T3)"
```

---

## Task 4: handoff_index.py — 维护 INDEX.md

**Files:**
- Create: `scripts/research_loop/handoff_index.py`
- Create: `tests/research_loop/test_handoff_index.py`

- [ ] **Step 4.1: 写 failing test**

`tests/research_loop/test_handoff_index.py`:
```python
"""handoff_index 单测."""
from pathlib import Path

from scripts.research_loop.handoff_index import (
    add_handoff_entry,
    init_index_if_missing,
)


def test_init_creates_header(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    text = idx.read_text(encoding="utf-8")
    assert "# Handoffs Index" in text


def test_add_prepends_top(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    add_handoff_entry(idx, round_idx=1, path="2026-05-07_R01.md",
                     ctx_tok=655000, summary="phase A smoke done")
    add_handoff_entry(idx, round_idx=2, path="2026-05-08_R02.md",
                     ctx_tok=695000, summary="phase B governor pivot")
    text = idx.read_text(encoding="utf-8")
    # newest 在最上
    assert text.index("R02") < text.index("R01")


def test_init_idempotent(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    add_handoff_entry(idx, round_idx=1, path="r01.md", ctx_tok=1, summary="x")
    init_index_if_missing(idx)
    # 不覆盖已有内容
    assert "r01.md" in idx.read_text(encoding="utf-8")
```

- [ ] **Step 4.2: 跑 fail**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_handoff_index.py -v
```
Expected: ImportError.

- [ ] **Step 4.3: 实现 handoff_index.py**

`scripts/research_loop/handoff_index.py`:
```python
"""handoffs/INDEX.md 维护. 最新在最上."""

from __future__ import annotations

import datetime
from pathlib import Path

HEADER = """# Handoffs Index

> 最新 handoff 在最上. 新会话进来读最上一行的 path.
> 维护: scripts/research_loop/handoff_index.py
"""


def init_index_if_missing(path: Path | str) -> None:
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(HEADER + "\n", encoding="utf-8")


def add_handoff_entry(
    path: Path | str,
    round_idx: int,
    path_relative: str | None = None,
    *,
    ctx_tok: int,
    summary: str,
    when_utc: str | None = None,
    # 兼容 kw 调用
    **kwargs,
) -> None:
    """Prepend 一行到 index 末 (header 后)."""
    if path_relative is None:
        # 兼容 test 调用 path=...
        path_relative = kwargs.get("path", "")
    if not path_relative:
        raise ValueError("path_relative required")
    p = Path(path)
    init_index_if_missing(p)
    when = when_utc or datetime.datetime.utcnow().isoformat() + "Z"
    line = (f"- **R{round_idx:02d}** | {when} | ctx={ctx_tok} | "
            f"[{path_relative}]({path_relative}) — {summary}\n")
    text = p.read_text(encoding="utf-8")
    # Header 后插入新条目 (top-of-list)
    parts = text.split("\n", )
    # 找 header 末尾 (第一个空行 after "维护: " 行)
    insert_at = text.find("维护: scripts/research_loop/handoff_index.py\n")
    if insert_at < 0:
        # 老/空 header, 直接 append
        new = text.rstrip() + "\n\n" + line
    else:
        marker_end = text.find("\n", insert_at) + 1
        head = text[:marker_end] + "\n"
        rest = text[marker_end:].lstrip("\n")
        new = head + line + rest
    p.write_text(new, encoding="utf-8")
```

- [ ] **Step 4.4: 跑 PASS**

```bash
/home/wya/andes_venv/bin/python -m pytest tests/research_loop/test_handoff_index.py -v
```
Expected: 3 passed.

- [ ] **Step 4.5: Commit**

```bash
git add scripts/research_loop/handoff_index.py tests/research_loop/test_handoff_index.py
git commit -m "feat(research-loop): handoffs/INDEX.md updater (T4)"
```

---

## Task 5: caveman 模板

**Files:**
- Create: `templates/plan-caveman.md`
- Create: `templates/verdict-caveman.md`

- [ ] **Step 5.1: 写 plan-caveman.md**

`templates/plan-caveman.md`:
```markdown
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
```

- [ ] **Step 5.2: 写 verdict-caveman.md**

`templates/verdict-caveman.md`:
```markdown
<!--
USAGE: copy 到 quality_reports/research_loop/round_NN_verdict.md
风格: caveman 中文, 300-800 字, 详见 spec §7.2
-->

# R<NN> Verdict

**Status**: FINAL
**Date**: YYYY-MM-DD

## 实测
exp1: 6axis=<X>  overall=<Y>  G=<ABCDEF>  log=<path>
exp2: ...

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
```

- [ ] **Step 5.3: Commit**

```bash
git add templates/plan-caveman.md templates/verdict-caveman.md
git commit -m "docs(research-loop): caveman plan + verdict templates (T5)"
```

---

## Task 6: backends/_resource_check.sh — RAM 抽象

**Files:**
- Create: `scripts/backends/_resource_check.sh`
- Create: `tests/research_loop/test_resource_check.sh`

- [ ] **Step 6.1: 写 failing test**

`tests/research_loop/test_resource_check.sh`:
```bash
#!/bin/bash
# bash 单测 _resource_check.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO/scripts/backends/_resource_check.sh"

# 子测函数
fail() { echo "FAIL: $1" >&2; exit 1; }

# T1: 文件存在 + 可执行
[[ -f "$SCRIPT" ]] || fail "_resource_check.sh missing"
[[ -x "$SCRIPT" ]] || fail "_resource_check.sh not executable"

# T2: free_gb 输出整数
out=$(bash "$SCRIPT" free_gb)
[[ "$out" =~ ^[0-9]+$ ]] || fail "free_gb returned non-int: $out"

# T3: fit_count 0 free 返 0
out=$(FREE_GB_OVERRIDE=0 bash "$SCRIPT" fit_count 4 2.5)
[[ "$out" == "0" ]] || fail "fit_count(0,4,2.5) expected 0 got $out"

# T4: fit_count 10 free, hard=4, per=2.5 → floor((10-4)/2.5)=2
out=$(FREE_GB_OVERRIDE=10 bash "$SCRIPT" fit_count 4 2.5)
[[ "$out" == "2" ]] || fail "fit_count(10,4,2.5) expected 2 got $out"

# T5: fit_count 100 free → 大数
out=$(FREE_GB_OVERRIDE=100 bash "$SCRIPT" fit_count 4 2.5)
(( out >= 30 )) || fail "fit_count(100,4,2.5) expected >=30 got $out"

echo "ALL PASS (5 cases)"
```

```bash
chmod +x tests/research_loop/test_resource_check.sh
bash tests/research_loop/test_resource_check.sh
```
Expected: FAIL ("_resource_check.sh missing").

- [ ] **Step 6.2: 实现 _resource_check.sh**

`scripts/backends/_resource_check.sh`:
```bash
#!/bin/bash
# 资源检查抽象. backend-agnostic.
# Usage:
#   _resource_check.sh free_gb              → 输出 free RAM (GB int)
#   _resource_check.sh fit_count <hard> <per_run>  → 输出能起几个进程
# Env:
#   FREE_GB_OVERRIDE=<int>  测试 mock free RAM
set -euo pipefail

cmd="${1:-}"

case "$cmd" in
    free_gb)
        if [[ -n "${FREE_GB_OVERRIDE:-}" ]]; then
            echo "$FREE_GB_OVERRIDE"
        else
            # WSL/Linux: free -g 第二行 available 列 (第 7 字段)
            free -g | awk '/^Mem:/ {print $7}'
        fi
        ;;
    fit_count)
        hard="${2:?hard threshold required}"
        per_run="${3:?per_run estimate required}"
        if [[ -n "${FREE_GB_OVERRIDE:-}" ]]; then
            free="$FREE_GB_OVERRIDE"
        else
            free=$(free -g | awk '/^Mem:/ {print $7}')
        fi
        # 算: floor((free - hard) / per_run), 负数夹到 0
        usable=$(awk -v f="$free" -v h="$hard" 'BEGIN{r=f-h; if(r<0)r=0; print r}')
        count=$(awk -v u="$usable" -v p="$per_run" 'BEGIN{print int(u/p)}')
        echo "$count"
        ;;
    *)
        echo "usage: $0 {free_gb|fit_count <hard> <per_run>}" >&2
        exit 2
        ;;
esac
```

```bash
chmod +x scripts/backends/_resource_check.sh
```

- [ ] **Step 6.3: 跑 PASS**

```bash
bash tests/research_loop/test_resource_check.sh
```
Expected: ALL PASS (5 cases).

- [ ] **Step 6.4: Commit**

```bash
git add scripts/backends/_resource_check.sh tests/research_loop/test_resource_check.sh
git commit -m "feat(research-loop): backends/_resource_check.sh (T6)"
```

---

## Task 7: backends/andes_cpu.sh — ANDES launcher

**Files:**
- Create: `scripts/backends/andes_cpu.sh`
- Create: `scripts/backends/sac_gpu.sh` (stub)
- Create: `scripts/backends/matlab_session.sh` (stub)
- Create: `tests/research_loop/test_andes_cpu.sh`

- [ ] **Step 7.1: 写 failing test**

`tests/research_loop/test_andes_cpu.sh`:
```bash
#!/bin/bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO/scripts/backends/andes_cpu.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -x "$SCRIPT" ]] || fail "andes_cpu.sh not executable"

# T1: --help 不报错
bash "$SCRIPT" --help >/dev/null 2>&1 || fail "--help exited non-0"

# T2: launch mode 用 ANDES_CPU_DRY_RUN=1 mock 起进程, 输出 pid
tmpdir=$(mktemp -d)
out_dir="$tmpdir/run01"
log="$tmpdir/run01.log"
ANDES_CPU_DRY_RUN=1 bash "$SCRIPT" launch \
    --id mock_run01 \
    --cmd "echo hello" \
    --out-dir "$out_dir" \
    --log "$log" \
    > "$tmpdir/launch.out" 2>&1
pid=$(grep -oE 'pid=[0-9]+' "$tmpdir/launch.out" | head -1 | cut -d= -f2)
[[ -n "$pid" ]] || fail "launch did not output pid"

# 等 mock 进程结束
sleep 1
kill -0 "$pid" 2>/dev/null && fail "mock process should be dead"

# T3: log 文件应有 hello
grep -q hello "$log" || fail "log missing 'hello'"

# T4: 退出码 0 应该写 done.json (在 out_dir/_done.json)
[[ -f "$out_dir/_done.json" ]] || fail "_done.json missing"
grep -q '"exit_code": 0' "$out_dir/_done.json" || fail "_done.json wrong exit_code"

rm -rf "$tmpdir"
echo "ALL PASS (4 cases)"
```

```bash
chmod +x tests/research_loop/test_andes_cpu.sh
bash tests/research_loop/test_andes_cpu.sh
```
Expected: FAIL.

- [ ] **Step 7.2: 实现 andes_cpu.sh**

`scripts/backends/andes_cpu.sh`:
```bash
#!/bin/bash
# ANDES TDS launcher. daemon 调它起单个 ANDES 训练.
# Usage:
#   andes_cpu.sh launch --id <run_id> --cmd <cmd> --out-dir <dir> --log <path>
#   andes_cpu.sh --help
# Env:
#   ANDES_CPU_DRY_RUN=1   不真起 ANDES, 跑 cmd 字面值测试
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<EOF
ANDES CPU backend. Spawns one training process via nohup.

Usage:
  andes_cpu.sh launch --id <id> --cmd <cmd> --out-dir <dir> --log <path>

Output (stdout): "pid=<pid>"
Side effect: 进程跑完写 <out-dir>/_done.json (exit_code, finished_at_utc).
EOF
    exit 0
fi

[[ "${1:-}" == "launch" ]] || { echo "first arg must be 'launch' or --help" >&2; exit 2; }
shift

run_id=""; cmd=""; out_dir=""; log_path=""
while (( $# > 0 )); do
    case "$1" in
        --id)      run_id="$2"; shift 2 ;;
        --cmd)     cmd="$2"; shift 2 ;;
        --out-dir) out_dir="$2"; shift 2 ;;
        --log)     log_path="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$run_id"   ]] || { echo "--id required"  >&2; exit 2; }
[[ -n "$cmd"      ]] || { echo "--cmd required" >&2; exit 2; }
[[ -n "$out_dir"  ]] || { echo "--out-dir required" >&2; exit 2; }
[[ -n "$log_path" ]] || { echo "--log required" >&2; exit 2; }

mkdir -p "$out_dir" "$(dirname "$log_path")"

# 包装: 跑 cmd, 完成后写 _done.json
done_json="$out_dir/_done.json"

if [[ "${ANDES_CPU_DRY_RUN:-}" == "1" ]]; then
    # 测试模式: 直接 sh -c 跑, 同步等
    (
        bash -c "$cmd" > "$log_path" 2>&1
        ec=$?
        printf '{"id":"%s","exit_code":%d,"finished_at_utc":"%s"}\n' \
            "$run_id" "$ec" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$done_json"
    ) &
    pid=$!
    echo "pid=$pid"
else
    # 正式: nohup 后台
    (
        bash -c "$cmd" > "$log_path" 2>&1
        ec=$?
        printf '{"id":"%s","exit_code":%d,"finished_at_utc":"%s"}\n' \
            "$run_id" "$ec" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$done_json"
    ) &
    pid=$!
    disown $pid
    echo "pid=$pid"
fi
```

`scripts/backends/sac_gpu.sh` (stub):
```bash
#!/bin/bash
# Stub: 未来 GPU SAC backend. 现不实现.
echo "sac_gpu backend not yet implemented (see spec §11)" >&2
exit 99
```

`scripts/backends/matlab_session.sh` (stub):
```bash
#!/bin/bash
# Stub: 未来 Simulink MATLAB session backend. 现不实现.
echo "matlab_session backend not yet implemented (see spec §11)" >&2
exit 99
```

```bash
chmod +x scripts/backends/andes_cpu.sh scripts/backends/sac_gpu.sh scripts/backends/matlab_session.sh
```

- [ ] **Step 7.3: 跑 PASS**

```bash
bash tests/research_loop/test_andes_cpu.sh
```
Expected: ALL PASS (4 cases).

- [ ] **Step 7.4: Commit**

```bash
git add scripts/backends/andes_cpu.sh scripts/backends/sac_gpu.sh \
       scripts/backends/matlab_session.sh tests/research_loop/test_andes_cpu.sh
git commit -m "feat(research-loop): backends andes_cpu (real) + GPU/MATLAB stubs (T7)"
```

---

## Task 8: research_loop_daemon.sh — 主守护

**Files:**
- Create: `scripts/research_loop_daemon.sh`
- Create: `tests/research_loop/test_daemon_dry_run.sh`

- [ ] **Step 8.1: 写 failing test (dry-run integration)**

`tests/research_loop/test_daemon_dry_run.sh`:
```bash
#!/bin/bash
# Daemon dry-run integration: 5 tick, mock training (echo hello), 验 state 流转.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DAEMON="$REPO/scripts/research_loop_daemon.sh"
PY="/home/wya/andes_venv/bin/python"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -x "$DAEMON" ]] || fail "daemon script not executable"

tmpdir=$(mktemp -d)
state_file="$tmpdir/state.json"
log_file="$tmpdir/daemon.log"

# 起 state 含 1 个 mock pending
"$PY" -c "
import json, sys
sys.path.insert(0, '$REPO')
from scripts.research_loop.state_io import default_empty_state
s = default_empty_state()
s['pending'].append({
    'id': 'mock_run01', 'backend': 'andes_cpu',
    'cmd': 'echo hello && sleep 1',
    'out_dir': '$tmpdir/run01',
    'log': '$tmpdir/run01.log',
    'expected_hr': 0.001, 'ram_gb': 0.1, 'priority': 5,
    'rationale': 'dry-run smoke', 'queued_by': 'test'
})
print(json.dumps(s))
" > "$state_file"

# 跑 daemon dry-run 5 tick (TICK_S=1, MAX_TICKS=5, ANDES_CPU_DRY_RUN=1)
TICK_S=1 MAX_TICKS=5 ANDES_CPU_DRY_RUN=1 FREE_GB_OVERRIDE=20 \
    STATE_FILE="$state_file" DAEMON_LOG="$log_file" \
    bash "$DAEMON" || fail "daemon exited non-0"

# 验 done 已写
done_count=$("$PY" -c "
import json
s = json.load(open('$state_file'))
print(len(s['done']))
")
[[ "$done_count" == "1" ]] || fail "done count expected 1 got $done_count"

# 验 daemon.log 有 5 行 tick
tick_lines=$(grep -c "tick=" "$log_file" || true)
(( tick_lines >= 3 )) || fail "tick lines < 3 got $tick_lines"

rm -rf "$tmpdir"
echo "ALL PASS (3 assertions)"
```

```bash
chmod +x tests/research_loop/test_daemon_dry_run.sh
bash tests/research_loop/test_daemon_dry_run.sh
```
Expected: FAIL ("daemon script not executable").

- [ ] **Step 8.2: 实现 daemon**

`scripts/research_loop_daemon.sh`:
```bash
#!/bin/bash
# Research Loop Daemon. 60s tick, pending → fit → 起训练 → 监 → done.
# spec §5.
# Env:
#   STATE_FILE=<path>             默认 quality_reports/research_loop/state.json
#   DAEMON_LOG=<path>             默认 /tmp/rloop_daemon.log
#   TICK_S=60                     tick 间隔
#   MAX_TICKS=0                   0=无限, 测试用 5
#   FREE_GB_OVERRIDE=             mock free RAM (测试)
#   ANDES_CPU_DRY_RUN=            mock backend
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/wya/andes_venv/bin/python}"
STATE_FILE="${STATE_FILE:-$REPO/quality_reports/research_loop/state.json}"
DAEMON_LOG="${DAEMON_LOG:-/tmp/rloop_daemon.log}"
TICK_S="${TICK_S:-60}"
MAX_TICKS="${MAX_TICKS:-0}"
LOCK_FILE="${LOCK_FILE:-/tmp/rloop_daemon.lock}"

source "$REPO/scripts/backends/_resource_check.sh" 2>/dev/null || true

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$DAEMON_LOG"
}

# 单实例锁
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "another daemon running" >&2; exit 1; }

# Daemon 主循环
tick=0
log "daemon=START state=$STATE_FILE tick_s=$TICK_S max_ticks=$MAX_TICKS"

while true; do
    tick=$((tick + 1))

    # 退出条件
    if (( MAX_TICKS > 0 )) && (( tick > MAX_TICKS )); then
        log "daemon=END max_ticks reached"
        break
    fi

    # 读 state
    if [[ ! -f "$STATE_FILE" ]]; then
        log "tick=$tick state_file missing, halt"
        break
    fi

    # 算 free RAM
    free_gb=$(bash "$REPO/scripts/backends/_resource_check.sh" free_gb)

    # daemon 主操作 (Python)
    "$PY" - <<PYEOF >> "$DAEMON_LOG" 2>&1 || true
import json, os, subprocess, sys
sys.path.insert(0, "$REPO")
from scripts.research_loop.state_io import read_state, write_state, with_state_lock

STATE = "$STATE_FILE"
free_gb = int("$free_gb")
TICK = $tick
DRY = os.environ.get("ANDES_CPU_DRY_RUN", "")
REPO = "$REPO"

with with_state_lock(STATE):
    s = read_state(STATE)
    hard = s["ram"]["free_gb_min_hard"]
    per = s["ram"]["per_run_estimate_gb"]

    # 1. 监 running 进程 → done / fail
    still_running = []
    for r in s["running"]:
        pid = r["pid"]
        try:
            os.kill(pid, 0)
            still_running.append(r)
        except ProcessLookupError:
            done_json = os.path.join(r["out_dir"], "_done.json")
            if os.path.exists(done_json):
                d = json.load(open(done_json))
                s["done"].append({
                    "id": r["id"],
                    "exit_code": d["exit_code"],
                    "finished_at_utc": d["finished_at_utc"],
                    "verdict_path": None,
                    "overall_score_v2": None,
                    "axes": {},
                })
                print(f"tick={TICK} done id={r['id']} exit={d['exit_code']}")
            else:
                s["killed"].append({
                    "id": r["id"], "reason": "process gone, no _done.json",
                    "killed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                })
    s["running"] = still_running

    # 2. RAM 紧 → kill 低优先级
    if free_gb < hard and s["running"]:
        # 杀最低 priority 那个 (注: pending 有 priority, running 缺 → 跳过这步)
        # MVP: 简单 log 警报, 不主动 kill (待 v2)
        print(f"tick={TICK} RAM_TIGHT free={free_gb} hard={hard} running={len(s['running'])}")

    # 3. fit 起 pending
    usable = max(0, free_gb - hard)
    fit_count = int(usable / per) if per > 0 else 0
    fit_count = max(0, fit_count - len(s["running"]))

    # 按 priority desc 选 pending
    s["pending"].sort(key=lambda x: -x.get("priority", 0))
    started = 0
    new_pending = []
    for p in s["pending"]:
        if started >= fit_count:
            new_pending.append(p)
            continue
        # 调 backend launcher
        backend = p.get("backend", "andes_cpu")
        launcher = os.path.join(REPO, "scripts/backends", f"{backend}.sh")
        if not os.path.exists(launcher):
            new_pending.append(p)  # backend 未实现, 留 pending
            print(f"tick={TICK} skip id={p['id']} backend={backend} (no launcher)")
            continue
        out = subprocess.run(
            [launcher, "launch",
             "--id", p["id"],
             "--cmd", p["cmd"],
             "--out-dir", p["out_dir"],
             "--log", p["log"]],
            env={**os.environ},
            capture_output=True, text=True
        )
        # 解析 pid=<pid>
        pid = None
        for line in out.stdout.splitlines():
            if line.startswith("pid="):
                pid = int(line.split("=")[1])
                break
        if pid is None:
            print(f"tick={TICK} launch_fail id={p['id']} stderr={out.stderr[:200]}")
            new_pending.append(p)
            continue
        s["running"].append({
            "id": p["id"], "pid": pid,
            "started_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            "log_tail_check_ok": True,
            "out_dir": p["out_dir"], "log": p["log"],
        })
        started += 1
        print(f"tick={TICK} started id={p['id']} pid={pid}")
    s["pending"] = new_pending

    write_state(STATE, s)
    print(f"tick={TICK} ram={free_gb}GB run={len(s['running'])} pend={len(s['pending'])} done={len(s['done'])}")
PYEOF

    sleep "$TICK_S"
done

log "daemon=EXIT"
```

```bash
chmod +x scripts/research_loop_daemon.sh
```

- [ ] **Step 8.3: 跑 PASS**

```bash
bash tests/research_loop/test_daemon_dry_run.sh
```
Expected: ALL PASS (3 assertions).

- [ ] **Step 8.4: Commit**

```bash
git add scripts/research_loop_daemon.sh tests/research_loop/test_daemon_dry_run.sh
git commit -m "feat(research-loop): daemon main loop + dry-run integration test (T8)"
```

---

## Task 9: AI skill — `.claude/skills/research-loop/SKILL.md`

**Files:**
- Create: `.claude/skills/research-loop/SKILL.md`

- [ ] **Step 9.1: 写 SKILL.md**

`.claude/skills/research-loop/SKILL.md`:
```markdown
---
name: research-loop
description: ANDES 6-axis recovery 自治研究循环. 用户说 "续 research-loop" 或新会话进来读 handoff 后. AI 读 state.json + 最新 verdict, 写 plan/verdict (caveman), 入队, 睡到下一轮.
---

# Research Loop AI Agent

> Spec: `quality_reports/specs/2026-05-07_research_loop_design.md`
> Auto-trigger: 用户说 "续 research-loop" / "进 research-loop" / "继续 research-loop"

## 进会话第一动作 (强制)

1. 读 `quality_reports/research_loop/state.json` (Schema 检查走 `scripts/research_loop/check_state.py`)
2. 读 `quality_reports/research_loop/handoffs/INDEX.md` 顶行 → 读对应 handoff
3. 读最新 `round_NN_verdict.md` (如有)
4. 进 §决策树

## 自由度宪章 (硬约束)

1. 默认走启发式. 例外要写理由 (一行也行)
2. 不预设的现象 → 允许新建 `audits/<topic>.md` ad-hoc 分析
3. 候选不限调参——允许提: 换 metric / 改 obs / 重写 reward / 加 ablation / 跑 sanity probe
4. 跑飞 (OOM/NaN/发散) → 自写 `incidents/<round>.md`, 不等用户
5. 觉得方向不对 → 写 `pivots/<round>.md` 提议, 入 state.pending 等下轮采纳
6. 用户在任何时插话 → 优先级最高, 立刻停手听
7. caveman 默认. "为啥这么干"段落允许说人话
8. 对话框只总结, 详写文档

## 决策树 (per wake)

```
看 state + done.last vs verdict 写没写:
├ done 末尾 verdict 未写 → 写 verdict + 提下轮
├ pending 满 + 无 done 新增 → ScheduleWakeup(estimated_remaining_min)
├ state.killed[] 新增 → 写 incident
├ done.exit_code ≠ 0 → 写 incident
├ stagnation.delta_pct < 5% 连 3 round → 写 pivot
├ ctx > 650k → 找自然断点 → handoff (软触发)
├ ctx > 700k → 强 handoff, 不再做新分析
├ G1-G6 全 PASS → 写 final_verdict
└ 无新事件 → 短 wait (5min) 再查
```

## Root-Cause 分析 (强制 fork)

主上下文不做长篇分析. fork:
- subagent_type=`domain-reviewer` 做物理 root-cause
- subagent_type=`tracer` 做证据-假设跟踪

主上下文只接 subagent 摘要 (≤50 字) + 关键数字. 每次 wake 主上下文目标 ≤ 10k token.

## /andes-compare 调用契约

verdict 阶段必调 `/andes-compare` 当:
- 本轮 K ≥ 2 (多候选互比)
- 本轮 best vs 上轮 best (跨轮强制 same-context alignment)
- 本轮 vs 论文 → 走 6-axis JSON, 不再单独调 compare

输出落 `quality_reports/research_loop/round_NN_compare.md`.

## 文档产出 (caveman, 见 spec §7)

- `round_NN_plan.md`         (template: `templates/plan-caveman.md`)
- `round_NN_verdict.md`      (template: `templates/verdict-caveman.md`)
- `round_NN_compare.md`      (调 `/andes-compare` 自动产)
- `incidents/<id>.md`        (随写)
- `audits/<topic>.md`        (随写)
- `pivots/<round>.md`        (随写)
- `handoffs/<date>_R<NN>.md` (ctx 触发)

## 起步 (第一轮)

不动 `quality_reports/plans/2026-05-07_andes_6axis_recovery.md`.

读现 6-axis 真相 (`docs/paper/andes_replication_status_2026-05-07_6axis.md`) +
recovery plan (作 prior knowledge), AI 自决 2-4 个候选.

## Daemon 启动 (用户做)

```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &
echo $! > /tmp/rloop_daemon.pid
```

终止: `kill $(cat /tmp/rloop_daemon.pid)`

## Handoff 流程 (ctx 满)

ctx > 650k 软触发:
1. 选下个自然断点 (写完 verdict 算)
2. write `handoffs/<date>_R<NN>.md` (template: spec §7.6)
3. update `handoffs/INDEX.md` 加一行 (调 `scripts/research_loop/handoff_index.py`)
4. update `state.json.ai_session_log[]`
5. say 用户: "续: 开新对话粘 `续 research-loop, 读 <handoff>`"

ctx > 700k 强触发: 跳自然断点等待, 立即写.

## 失败模式 (见 spec §15)

参考 spec, 不复述.
```

- [ ] **Step 9.2: Commit**

```bash
git add .claude/skills/research-loop/SKILL.md
git commit -m "feat(research-loop): AI agent SKILL.md (T9)"
```

---

## Task 10: 起步 — research_loop/ 目录 + 空 state

**Files:**
- Create: `quality_reports/research_loop/README.md`
- Create: `quality_reports/research_loop/state.json` (空起步)
- Create: `quality_reports/research_loop/handoffs/INDEX.md`
- Create: `quality_reports/research_loop/incidents/.gitkeep`
- Create: `quality_reports/research_loop/audits/.gitkeep`
- Create: `quality_reports/research_loop/pivots/.gitkeep`

- [ ] **Step 10.1: 写 README.md**

`quality_reports/research_loop/README.md`:
```markdown
# Research Loop Workspace

Auto research loop runtime artifacts. 见 spec
`quality_reports/specs/2026-05-07_research_loop_design.md`.

## 文件

- `state.json` — daemon + AI 共用运行时状态 (schema § spec §4)
- `round_NN_plan.md` / `round_NN_verdict.md` — caveman 计划+判决
- `handoffs/` + `INDEX.md` — 跨会话续命
- `incidents/` — OOM/NaN/发散 复盘
- `audits/` — 跨 round 现象审计
- `pivots/` — 方向转换提案

## Daemon 启停

启:
```bash
nohup bash scripts/research_loop_daemon.sh > /tmp/rloop_daemon.log 2>&1 &
echo $! > /tmp/rloop_daemon.pid
```

停: `kill $(cat /tmp/rloop_daemon.pid)`

## AI 会话进入

新会话第一句:
> 续 research-loop, 读 quality_reports/research_loop/handoffs/<最新>

或老会话:
> 进 research-loop
```

- [ ] **Step 10.2: 写 空 state.json**

```bash
mkdir -p "quality_reports/research_loop/handoffs"
mkdir -p "quality_reports/research_loop/incidents"
mkdir -p "quality_reports/research_loop/audits"
mkdir -p "quality_reports/research_loop/pivots"
touch "quality_reports/research_loop/incidents/.gitkeep"
touch "quality_reports/research_loop/audits/.gitkeep"
touch "quality_reports/research_loop/pivots/.gitkeep"

cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
/home/wya/andes_venv/bin/python -c "
import json, sys
sys.path.insert(0, '.')
from scripts.research_loop.state_io import default_empty_state, write_state
write_state('quality_reports/research_loop/state.json', default_empty_state())
"
```

- [ ] **Step 10.3: 写 INDEX.md**

```bash
/home/wya/andes_venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from scripts.research_loop.handoff_index import init_index_if_missing
init_index_if_missing('quality_reports/research_loop/handoffs/INDEX.md')
"
```

验:
```bash
cat quality_reports/research_loop/handoffs/INDEX.md
# 期望: '# Handoffs Index' header
/home/wya/andes_venv/bin/python -m scripts.research_loop.check_state quality_reports/research_loop/state.json
# 期望: OK
```

- [ ] **Step 10.4: Commit**

```bash
git add quality_reports/research_loop/
git commit -m "feat(research-loop): workspace skeleton + empty state (T10)"
```

---

## Task 11: 端到端 smoke (1 candidate × 30 ep, 真 ANDES)

**Files:**
- 不新增. 跑现有 daemon + andes_cpu backend + train_andes_v2.py.
- 产出 round_01_plan.md / round_01_verdict.md (caveman, AI 写).

- [ ] **Step 11.1: 由 AI (本会话或新开会话) 写 round_01_plan.md**

人手准备 1 个候选 plan 进 state.pending. 例 (AI 提的 Phase A smoke):

```bash
/home/wya/andes_venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from scripts.research_loop.state_io import read_state, write_state, with_state_lock

STATE = 'quality_reports/research_loop/state.json'
with with_state_lock(STATE):
    s = read_state(STATE)
    s['pending'].append({
        'id': 'r01_phaseA_smoothing_smoke_seed42',
        'backend': 'andes_cpu',
        'cmd': '/home/wya/andes_venv/bin/python scenarios/kundur/train_andes_v2.py --episodes 30 --seed 42 --phi-d 0.05 --save-dir results/andes_v2_smooth_smoke_seed42',
        'out_dir': 'results/andes_v2_smooth_smoke_seed42',
        'log': 'results/andes_v2_smooth_smoke_seed42.train.log',
        'expected_hr': 0.6, 'ram_gb': 2.5, 'priority': 5,
        'rationale': 'R01 Phase A smoothing 30ep smoke (smoke before full)',
        'queued_by': 'manual_test_T11'
    })
    write_state(STATE, s)
print('queued')
"
```

- [ ] **Step 11.2: 启 daemon (单 tick 测试)**

```bash
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
TICK_S=30 MAX_TICKS=3 bash scripts/research_loop_daemon.sh
```
Expected: state.running 出现 1 项 → 30ep 跑完 (~30-40 min) → state.done 加 1 项, exit_code=0.

- [ ] **Step 11.3: 验 done + 6-axis (人手, 后续 daemon 自动化)**

```bash
ls results/andes_v2_smooth_smoke_seed42/
# 期望: best.pt + final.pt + train.log

# 跑 6-axis (TODO daemon 自动跑, 现在手动)
EVAL_PAPER_SPEC_ENV=v2 /home/wya/andes_venv/bin/python scenarios/kundur/_eval_paper_specific.py \
    --model-dir results/andes_v2_smooth_smoke_seed42 --ckpt final.pt
/home/wya/andes_venv/bin/python evaluation/paper_grade_axes.py \
    results/andes_eval_paper_specific_v2_envV2_hetero/ddic_smooth_smoke_seed42*
```

- [ ] **Step 11.4: AI 写 round_01_verdict.md (caveman)**

参考 `templates/verdict-caveman.md`. 落到 `quality_reports/research_loop/round_01_verdict.md`.

- [ ] **Step 11.5: Commit (人手验完)**

```bash
git add quality_reports/research_loop/round_01_*.md
git commit -m "test(research-loop): R01 Phase A smoothing smoke + verdict (T11)"
```

---

## Task 12: MEMORY.md 注册

**Files:**
- Modify: `MEMORY.md` (project root) — 加一行指向 spec + skill

- [ ] **Step 12.1: Read 当前 MEMORY.md**

```bash
head -10 "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs/MEMORY.md"
```

- [ ] **Step 12.2: 加一行到 "Core Reference" 节末尾**

加:
```markdown
- **`quality_reports/specs/2026-05-07_research_loop_design.md`** — 自动研究循环 spec (3 层架构, daemon + state.json + AI 会话, 跨会话续命, caveman 文档). Skill: `.claude/skills/research-loop/`.
```

- [ ] **Step 12.3: Commit**

```bash
git add MEMORY.md
git commit -m "docs(research-loop): register skill in MEMORY.md (T12)"
```

---

## Self-Review Checklist

**Spec coverage** (vs `quality_reports/specs/2026-05-07_research_loop_design.md`):

| Spec § | Topic | Task |
|---|---|---|
| §3 | 3 层架构 | T1+T2+T8+T9 |
| §4 | state.json schema | T1 |
| §5 | Daemon 行为 | T8 |
| §6 | AI Agent 行为 | T9 |
| §7 | caveman 文档 | T5 |
| §8 | 软警报 + 硬熔断 | T8 (RAM hard) + T9 (软 由 AI 写) |
| §9 | 并行启发式 | T3 (k_max) + T8 (fit) |
| §10 | Handoff 流程 | T4 (INDEX) + T9 (流程) |
| §11 | Backend 适配位 | T6+T7 |
| §12 | 复用既有 infra | T9 (引 spec) + T11 (引 paper_grade_axes) |
| §13 | 第一轮起步 | T11 |
| §14 | 自由度宪章 | T9 (写 SKILL.md) |
| §15 | 失败模式 | T9 (引 spec) |
| §16 | 测试策略 | T1-T8 单测 + T8 dry-run + T11 smoke |

未直接覆盖 (后续 V2):
- 软熔断 budget extension 流程 (Round/WallHr/Token > cap → AI 写 budget_extension.md)
- final_verdict 模板 (G1-G6 全 PASS 时)
- daemon RAM 紧时主动 kill 低优先级 (T8 step 2 留 stub, MVP 仅 log)

→ 这些 V2 加, 不阻塞 MVP 启用.

**Placeholder 扫**: 已检. T11 步骤 3 提"TODO daemon 自动化", 是合理 V2 标记不是计划失败.

**类型一致性**:
- `default_empty_state()` 返 dict ↔ `read_state` 返 dict ↔ `check_state_dict(dict)`: 一致
- `pending[].id` (str) 一致出现在 daemon 起进程, running[], done[], killed[]
- `add_handoff_entry()` kw `path` vs `path_relative`: T4 实现写了 kw 兼容
- `_resource_check.sh fit_count` 返 int (echo) ↔ daemon Python `int(fit_count)`: 一致

**总结**: 12 task, ~50 atomic steps, MVP 完整闭环. 跨任务依赖图:

```
T1 (state schema) → T2 (state_io) → T3 (k_max) → T4 (handoff_index)
T5 (caveman tpl)  独立
T6 (_resource)    → T7 (andes_cpu)  → T8 (daemon)
T9 (skill)        独立 (引 T1-T8)
T10 (workspace)   依赖 T2 T4
T11 (smoke)       依赖 T1-T10 全
T12 (MEMORY)      依赖 T1+T9 完
```

每 task 自己 commit. 失败 task rollback 不影响下游 (除直接依赖).

---

## §Done Summary (append-only, post-execution)

(待 12 task 全过后填)

- Commit hashes: T1=... T2=... ...
- Estimate vs actual: <est>hr / <actual>hr (±%)
- Surprises: ...
- V2 backlog (从 self-review "未覆盖" + 11.3 "TODO daemon 自动化"): ...
