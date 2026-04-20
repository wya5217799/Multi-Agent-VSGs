# 测试结构清理计划
**来源**：5 轮 Claude vs Codex 独立评审，2026-04-15

---

## 背景结论

当前测试存在**真实的实现耦合**，集中在 adapter 层和任务编排层。
主要表现：锁死具体 MATLAB helper 函数名、subprocess 命令格式、PUBLIC_TOOLS 精确顺序。
**不是**全局性问题——contract test、算法边界测试、behavior test 大多健康，不应误伤。

---

## P0：小改动，立竿见影

### 1. `tests/test_mcp_server.py`
**问题**：line 53 断言 PUBLIC_TOOLS 精确顺序；line 59 断言精确数量 39。
新增任何工具就炸无关测试。

**改法**：
```python
# 删除
assert [tool.__name__ for tool in mcp_server.PUBLIC_TOOLS] == expected_names
assert len(mcp_server.PUBLIC_TOOLS) == 39

# 改成（与 line 106-113 的写法统一）
names = {tool.__name__ for tool in mcp_server.PUBLIC_TOOLS}
assert "simulink_load_model" in names
assert "simulink_query_params" in names
# ... 只列真正需要保证存在的工具
```

### 2. `tests/test_harness_tasks.py` — 合并两个重复的 deprecated smoke 测试
**问题**：line 216 和 line 250 测同一个废弃行为，逻辑几乎相同。

**改法**：保留一个，用 `@pytest.mark.parametrize` 或直接删掉 250，把两者差异合并进一个测试。

### 3. `tests/conftest.py` + `tests/test_env.py` — 去掉私有函数导入
**问题**：
- `conftest.py:6`：`from plotting.evaluate import ..., _get_zero_action`
- `test_env.py:13`：`from plotting.evaluate import _get_zero_action`

`_get_zero_action` 被重命名就会静默 ImportError。

**改法**：在 `conftest.py` 里 inline 一个局部 helper，或在 `plotting/evaluate.py` 加一个公开包装：
```python
def get_zero_action(env):
    return _get_zero_action(env)
```
然后两处改为导入公开版本。

---

## P1：有针对性的放宽，需要逐行判断

### 4. `tests/test_mcp_simulink_tools.py` — 拆分行为断言 vs. helper 名称断言

**保留不动（行为断言）**：
- `mock_eng.load_system.assert_called_once_with(str(expected_model), ...)` — 测的是"正确模型文件被加载"
- `addpath_paths contains expected_model_dir` — 测的是"正确目录进入 MATLAB 路径"
- `assert result["ok"] is True` 等返回值断言

**应该放宽（实现耦合）**：
- `mock_eng.vsg_bulk_get_params.assert_called_once_with(exact_name, exact_args, nargout=1, ...)` — line 355
- `mock_eng.vsg_describe_block_ports.assert_called_once_with(...)` — line 383
- `mock_eng.vsg_get_block_tree.assert_called_once_with("NE39bus_v2", "NE39bus_v2/VSG_ES1", 4.0, ...)` — line 415，连 float 精度都锁死
- `mock_eng.vsg_run_quiet.assert_called_once_with(code, nargout=1, background=True)` — line 454

**改法方向**：
```python
# 原来
mock_eng.vsg_bulk_get_params.assert_called_once_with(
    "NE39bus_v2", ["NE39bus_v2/VSrc_ES1"], ["ReferenceBlock"],
    nargout=1, stdout=ANY, stderr=ANY
)

# 改成（只验证结果，不验证哪个 helper 被调用）
assert result["items"][0]["params"]["ReferenceBlock"] == "spsThreePhaseSourceLib/..."
```
如果必须验证 helper 被调用，改成 `assert mock_eng.vsg_bulk_get_params.called`，不锁具体参数。

### 5. `tests/test_training_launch.py:245` — `_find_active_pid` 的 subprocess 格式测试

**问题**：line 257-277 测试 subprocess 命令里必须包含 `"kundur/train_simulink.py"`。
改用 psutil 查进程就全炸。这是实现耦合（≠ `_inspect_latest_run` 的算法边界测试）。

**改法**：把这几个测试上提到公开函数 `get_training_launch_status`，通过构造有/无对应进程的环境来测"active_pid 有没有被正确填充"，不再断言 subprocess 命令格式。

**注意**：`tests/test_training_launch.py:157`（`_inspect_latest_run`）的边界测试**保留不动**——
corrupt JSON、mtime 排序、空目录这类算法边界，通过公开 API 测会更难写、更难定位，直接测私有函数是合理的。

### 6. `tests/conftest.py` — 抽取假训练脚本 helper

**问题**：`test_harness_tasks.py:290-306` 和 `test_harness_tasks.py:393-406` 写了几乎相同的 fake training script。

**改法**：在 `conftest.py` 加一个 helper（不需要新建文件）：
```python
def make_fake_train_script(tmp_path, log_content=None):
    """写一个最小 fake training script，支持 --checkpoint-dir 和 --log-file。"""
    script = tmp_path / "scenarios" / "kundur" / "train_simulink.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    log_str = repr(log_content) if log_content else 'json.dumps({"ok": True})'
    script.write_text(
        "import argparse, pathlib, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--mode'); p.add_argument('--episodes', type=int)\n"
        "p.add_argument('--checkpoint-dir'); p.add_argument('--log-file')\n"
        "args = p.parse_args()\n"
        "pathlib.Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)\n"
        "(pathlib.Path(args.checkpoint_dir) / 'final.pt').write_text('ckpt')\n"
        "pathlib.Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)\n"
        f"pathlib.Path(args.log_file).write_text({log_str})\n",
        encoding="utf-8",
    )
    return script
```
两处调用改为 `make_fake_train_script(tmp_path)` / `make_fake_train_script(tmp_path, log_content=...)`。

---

## 不动的清单（容易误伤，不要碰）

| 文件/位置 | 原因 |
|-----------|------|
| `test_perf_warmup_fr.py:78-102`（warmup 传 do_recompile=True） | 行为测试，保护 FastRestart 性能回归 |
| `test_perf_warmup_fr.py:221`（close 后 _fr_compiled 复位） | 虽然直接断言私有字段，但保护"close 后重用不触发 IC 静默错误"这个安全不变量 |
| `test_matlab_session.py:159-168`（addpath 包含 vsg_helpers） | 行为测试，没有这个路径 MATLAB 找不到任何 .m 函数 |
| `test_training_launch.py:157-208`（_inspect_latest_run 边界） | 算法边界，直接测私有 helper 合理 |
| `test_harness_tasks.py:31`（scenario_status contract） | 公开 API 的 contract test，不是实现耦合 |
| `test_harness_tasks.py` vs `test_harness_flow_contract.py` | 部分重叠但不同层，不要合并整个文件 |
| `test_modeling_tasks.py`（3 个测试，49 行） | 模块可导入性 smoke，无明显伤害，不是优先项 |

---

## 执行顺序

```
P0.1  test_mcp_server.py       PUBLIC_TOOLS 断言改集合          ~30 min
P0.2  test_harness_tasks.py    合并 deprecated smoke 重复        ~15 min
P0.3  conftest.py/test_env.py  去掉 _get_zero_action 私有导入    ~20 min
P1.1  conftest.py              加 make_fake_train_script helper   ~30 min
P1.2  test_mcp_simulink_tools  放宽 vsg_* 函数名精确断言          ~2-3 h
P1.3  test_training_launch     _find_active_pid 上提到公开 API   ~1-2 h
```

P0 全部完成后跑一遍 `pytest`，确认没有误伤，再做 P1。
