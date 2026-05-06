"""state.json 读写 + 文件锁 (daemon + AI 共用).

ram 字段含 ANDES throughput 实测默认 (per spec §11.5):
- per_run_estimate_gb=1.5 (实测 ~800 MB + safety)
- cpu_threads_per_run=4 (OMP=4 必须, BLAS oversub 防御)
- wsl_total_cpu=32 (~/.wslconfig patched)
- omp_env_defaults: daemon 启训练时注入
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import time
from pathlib import Path
from typing import Iterator

from scripts.research_loop.check_state import check_state_dict


def _utc_now_z() -> str:
    """ISO 8601 UTC w/ 'Z' suffix. 避开 utcnow() 3.12 deprecation."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def default_empty_state() -> dict:
    """起步空 state, 通过 schema 检查."""
    return {
        "version": "1.0",
        "round_idx": 0,
        "started_at_utc": _utc_now_z(),
        "budget": {
            "rounds_used": 0, "rounds_cap": 20,
            "wall_hr_used": 0.0, "wall_hr_cap": 72,
            "tokens_used": 0, "tokens_cap": 800000,
        },
        "ram": {
            "free_gb_min_hard": 4,
            "per_run_estimate_gb": 1.5,
            "cpu_threads_per_run": 4,
            "wsl_total_cpu": 32,
            "omp_env_defaults": {
                "OMP_NUM_THREADS": "4",
                "MKL_NUM_THREADS": "4",
            },
        },
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
    """读 state.json, 校验 schema. UTF-8 显式 (跨平台一致)."""
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        state = json.load(f)
    check_state_dict(state)
    return state


def write_state(path: Path | str, state: dict) -> None:
    """写 state.json (写前校验, atomic rename, 失败清残).

    UTF-8 显式 (json ensure_ascii=False 写中文). 失败时 unlink .tmp,
    防止半写文件污染下一轮.
    """
    check_state_dict(state)
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        with contextlib.suppress(FileNotFoundError, OSError):
            tmp.unlink()
        raise


def _is_pid_alive(pid: int) -> bool:
    """POSIX: signal 0 不实发, 仅检 pid 是否在."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程在但属别用户
    return True


def _try_clear_stale_lock(lock_path: Path) -> bool:
    """读 lock 内 PID, 死了就删. 返 True 若清掉 stale."""
    try:
        with open(lock_path, encoding="utf-8") as f:
            pid_str = f.read().strip()
        pid = int(pid_str)
    except (FileNotFoundError, ValueError):
        return False
    if _is_pid_alive(pid):
        return False
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return False


@contextlib.contextmanager
def with_state_lock(path: Path | str, timeout_s: float = 30.0) -> Iterator[None]:
    """简文件锁: 创建 <path>.lock 写 PID, 写完删除. POSIX-only.

    Crash recovery: 若上次 holder 进程已死 (PID 不存在), 自动清 stale lock
    再重试. 防 daemon OOM-kill 后无限阻塞.

    daemon + AI 都通过它互斥. 不用 fcntl.flock 因 cross-platform 复杂.
    """
    p = Path(path)
    lock = p.with_suffix(p.suffix + ".lock")
    deadline = time.time() + timeout_s
    stale_check_done = False
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            # 第一次冲突时尝试清 stale (PID 死的). 清掉立刻重试.
            if not stale_check_done:
                stale_check_done = True
                if _try_clear_stale_lock(lock):
                    continue
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
