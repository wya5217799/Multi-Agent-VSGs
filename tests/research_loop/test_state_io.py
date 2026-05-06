"""state_io.py 锁 + 读写单测."""
import json
import os
import threading
import time
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


@pytest.mark.timeout(10)
def test_lock_blocks_concurrent_caller(tmp_path: Path):
    """Holder 持锁时 contender 必须等到 release 后才进."""
    p = tmp_path / "state.json"
    write_state(p, default_empty_state())
    results: list[str] = []
    barrier = threading.Barrier(2)

    def holder():
        with with_state_lock(p):
            barrier.wait()  # 通知 contender holder 已持锁
            time.sleep(0.3)
        results.append("holder_released")

    def contender():
        barrier.wait()  # 等 holder 拿到
        with with_state_lock(p, timeout_s=5.0):
            results.append("contender_acquired")

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=contender)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # holder release 必先于 contender acquire
    assert results == ["holder_released", "contender_acquired"]


@pytest.mark.timeout(5)
def test_lock_timeout_raises(tmp_path: Path):
    """Holder 不放, contender 超时 raise TimeoutError."""
    p = tmp_path / "state.json"
    write_state(p, default_empty_state())
    holder_done = threading.Event()
    contender_err: list[Exception] = []

    def holder():
        with with_state_lock(p):
            holder_done.wait(timeout=3.0)

    def contender():
        try:
            with with_state_lock(p, timeout_s=0.5):
                pass
        except TimeoutError as e:
            contender_err.append(e)

    t1 = threading.Thread(target=holder)
    t1.start()
    time.sleep(0.1)  # 确保 holder 拿到锁
    t2 = threading.Thread(target=contender)
    t2.start()
    t2.join()
    holder_done.set()
    t1.join()

    assert len(contender_err) == 1
    assert "held" in str(contender_err[0])


def test_stale_lock_recovered(tmp_path: Path):
    """死 PID 写在 lock 文件 → 自动清掉再 acquire."""
    p = tmp_path / "state.json"
    write_state(p, default_empty_state())
    lock = p.with_suffix(p.suffix + ".lock")
    # 写一个不可能存在的 PID (大于一般 max_pid)
    lock.write_text("9999999", encoding="utf-8")
    # 应该自动清并 acquire 成功
    with with_state_lock(p, timeout_s=2.0):
        pass


def test_write_state_failure_cleans_tmp(tmp_path: Path, monkeypatch):
    """write_state 中途 raise 时, .tmp 文件应被 unlink."""
    p = tmp_path / "state.json"
    tmp = p.with_suffix(p.suffix + ".tmp")
    s = default_empty_state()

    real_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="simulated"):
        write_state(p, s)

    assert not tmp.exists(), ".tmp 残留"
    assert not p.exists(), "目标文件不应被创建"
