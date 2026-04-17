# Spec: Simulink 开发工作流优化 — Simscape 查询库与结构化 MCP 工具

**日期:** 2026-03-31
**状态:** 待实施
**目标:** 消除 Simscape 开发中的三类 token 消耗（端口试探 45%、输出噪声 30%、静默失败诊断 25%）

---

## 1. 问题背景

### 1.1 历史失败模式（来自 sim_kundur_failure_analysis.md）

| 失败类别 | 历史案例 | Token 代价 |
|----------|----------|-----------|
| A. 端口映射试探 | 808-830：18 轮试探，9 分钟，每轮 ~1800 tokens | ~32k tokens |
| B. 静默失败诊断 | H vs mH 单位错误，无警告，靠 P_e≈0 倒推 | ~10k tokens/次 |
| C. 输出噪声 | evaluate_matlab_code 返回完整 MATLAB stdout | ~500-2000 tokens/次，每次必发生 |

### 1.2 根本原因

Claude 使用 `mcp__matlab__evaluate_matlab_code`（MATLAB MCP server 原生工具）探索 Simscape 模型，该工具返回未过滤的 MATLAB stdout，且 Simscape 对不合理参数不做 sanity check。`mcp_simulink_tools.py` 已经提供结构化工具，但覆盖的场景不够（不含端口查询、连接验证、参数单位检查）。

---

## 2. 设计目标

1. 查询任意 Simscape block 的端口结构 → 1 次调用，返回 JSON，不试探
2. 验证两个端口是否可连接 → 1 次调用，安全（不修改目标模型）
3. 构建完成后自动检测参数异常 → 主动捕获 H vs mH 类静默错误
4. Claude 有明确的工具使用规程，不退化回 `evaluate_matlab_code` 探索

---

## 3. 整体架构

### 3.1 三条工作路径（取代 evaluate_matlab_code 做所有事）

```
探索路径：inspect_block / check_connection (新 MCP 工具)
          → simscape_query.m → 结构化 JSON → <200 tokens

构建路径：build_model (已有 run_matlab_file 包装)
          → 完整构建脚本 → 只返回最后 20 行 + Error 行

诊断路径：run_sanity_check (新 MCP 工具)
          → simscape_sanity.m → pass/fail 表格 → <200 tokens
```

### 3.2 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `vsg_helpers/simscape_query.m` | 新增 | Simscape 结构化查询：端口、参数、连接验证、网络状态 |
| `vsg_helpers/simscape_sanity.m` | 新增 | 参数合理性检查：单位量级、P_e vs P_ref |
| `engine/mcp_simulink_tools.py` | 修改 | 新增 4 个 MCP 工具，遵循现有 session.call() 模式 |
| `CLAUDE.md` | 修改 | 新增 Simulink 建模三步规程 |

---

## 4. MATLAB 查询库：simscape_query.m

### 4.1 接口

```matlab
result = simscape_query(action, model_name, varargin)
```

返回值始终是可被 `session.call()` 序列化的 struct。

### 4.2 四个 action

#### `'ports'` — 查询 block 端口结构

```matlab
result = simscape_query('ports', mdl, block_path)
```

返回：
```
result.block_path    % 完整路径
result.ports(i).name        % 'LConn1', 'RConn1', ...
result.ports(i).side        % 'left' | 'right'
result.ports(i).port_type   % 'connection' | 'inport' | 'outport'
result.ports(i).handle      % 数字句柄
result.port_count           % 总端口数
```

实现要点：`get_param(block, 'PortHandles')` → 分 PortConnectivity 取每个句柄的属性

**解决的历史问题：** 808-830 全部 18 轮试探

#### `'params'` — 查询 block 关键参数

```matlab
result = simscape_query('params', mdl, block_path)
```

返回：所有 DialogParameters 的名称+当前值，以及基于 block 类型的单位 hint（见 4.3）

实现要点：`get_param(block, 'DialogParameters')` → fieldnames → 逐个 `get_param`，附加 UNIT_HINTS 映射表

**解决的历史问题：** 参数单位黑箱（H vs mH 类 bug 预防）

#### `'connect_test'` — 验证连接可行性（不修改目标模型）

```matlab
result = simscape_query('connect_test', mdl, b1_path, p1_name, b2_path, p2_name)
```

实现：临时模型 + try/catch

```matlab
tmp_name = ['tmp_conntest_' num2str(randi(1e6))];
new_system(tmp_name);
% b1_path / b2_path 是相对于模型根的路径，如 'VSG_ES1/CVS_ES1'
add_block([mdl '/' b1_path], [tmp_name '/B1']);
add_block([mdl '/' b2_path], [tmp_name '/B2']);
try
    add_line(tmp_name, ['B1/' p1_name], ['B2/' p2_name]);
    result.ok = true;
    result.reason = '';
catch e
    result.ok = false;
    result.reason = e.message;
end
close_system(tmp_name, 0);  % 不保存，直接丢弃
```

返回：`result.ok` (bool) + `result.reason` (Simscape 报错原文)

**注意：** `b1_path` / `b2_path` 是相对于模型根的路径，例如 `'VSG_ES1/CVS_ES1'`（不含模型名前缀）。函数内部拼接为 `[mdl '/' b1_path]` 后传给 `add_block`。

**解决的历史问题：** 连接失败后不再盲目换端口

#### `'network'` — 检查模型网络连通性

```matlab
result = simscape_query('network', mdl)
```

返回：
```
result.unconnected_ports(i).block   % block 路径
result.unconnected_ports(i).port    % 端口名
result.unconnected_count            % 未连接端口总数
result.isolated_blocks{}            % 孤立 block 列表（无任何连接）
```

实现：`find_system` 遍历所有 block → `get_param('PortHandles')` → 检查每个端口是否有连接线

性能备注：16-bus 模型约 100+ blocks，遍历估计 <5s，可接受。

### 4.3 单位 Hint 映射表（内嵌于 simscape_query.m）

匹配方式：用 `get_param(block, 'ReferenceBlock')` 取 block 的库路径，对以下关键词做 `contains()` 检查：

| ReferenceBlock 含 | 参数名 | 单位 | 来源验证 |
|-------------------|--------|------|---------|
| `'RLC'` | `'L'` | **H**（亨利，不是 mH） | build script line 515 |
| `'Transmission Line'` | `'L'`（mH/km）、`'length'`（km） | mH/km | build script line 927 |
| `'Wye-Connected Load'` | `'P'` / `'Qpos'` | W / var | build script line 971-972 |
| `'Controlled Voltage Source'` | — | 无 L 参数 | — |

注：
- TL 电感存储为 mH/km（`L_km_H * 1000`），sanity check 时读 `'L'`（mH/km）× `'length'`（km）得总电感（mH）
- TL 电容参数名是 `'Cl'`（nF/km），不是 `'C'`
- PortHandles 端口 side 判断：`PortHandles.LConn` = left，`PortHandles.RConn` = right（已验证）

此表在 `simscape_query('params', ...)` 返回时为每个参数附加 `unit_hint` 字段，让 Claude 看到参数时就知道单位。

---

## 5. 参数合理性检查：simscape_sanity.m

### 5.1 接口

```matlab
report = simscape_sanity(mdl, expected)
% expected: struct，含 Vbase_kV, fn_Hz, P_vsg_pu_nominal
```

### 5.2 检查项

| 检查项 | 方法 | 失败条件 |
|--------|------|----------|
| RLC 电感量级 | 读参数 `'L'`（H） | < 0.001 H 或 > 5 H（Kundur L_gen ≈ 0.505 H） |
| TL 电感量级 | 读 `'L'`（mH/km）× `'length'`（km）= 总感抗（mH） | 总 L < 0.01 mH 或 > 500 mH |
| R/X 比值 | R（Ω）/ (2π·fn·L（H）) | < 0.001 或 > 20（正常 0.01-1.0） |
| 全部物理端口已连接 | `simscape_query('network', ...)` | unconnected_count > 0 |
| Solver Configuration 存在 | `find_system` 按 BlockType | 缺少则 Simscape 无法运行 |
| Electrical Reference 存在 | 同上 | 缺少则仿真崩溃 |

**注：** P_e vs P_ref 比值检查需要仿真结果，**不在此函数内**。在首次短时仿真（0.1s）后，由 Python 侧或 `evaluate_common.py` 读 ToWorkspace 数据验证。

### 5.3 输出格式

```
report.passed        % bool
report.checks(i).name      % 检查项名称
report.checks(i).passed    % bool
report.checks(i).detail    % 具体值 + 期望范围
```

---

## 6. Python MCP 工具层：mcp_simulink_tools.py 新增函数

遵循现有模式：`session.call("函数名", args...)` → 返回 Python dict。

### 6.1 四个新函数

```python
def simulink_inspect_ports(model_name: str, block_path: str) -> dict:
    """查询 block 端口结构。返回 ports 列表，每项含 name/side/port_type。"""
    session = MatlabSession.get()
    result = session.call("simscape_query", "ports", model_name, block_path)
    return _convert_query_result(result)

def simulink_inspect_params(model_name: str, block_path: str) -> dict:
    """查询 block 参数值和单位 hint。"""
    session = MatlabSession.get()
    result = session.call("simscape_query", "params", model_name, block_path)
    return _convert_query_result(result)

def simulink_check_connection(
    model_name: str,
    block1_path: str, port1: str,
    block2_path: str, port2: str
) -> dict:
    """验证两端口是否可连接（临时模型，不修改目标）。返回 ok(bool) + reason(str)。"""
    session = MatlabSession.get()
    result = session.call(
        "simscape_query", "connect_test",
        model_name, block1_path, port1, block2_path, port2
    )
    return {"ok": bool(result["ok"]), "reason": str(result.get("reason", ""))}

def simulink_run_sanity_check(model_name: str, vbase_kv: float = 230.0, fn_hz: float = 50.0) -> dict:
    """运行参数合理性检查。构建完成后必须调用。"""
    session = MatlabSession.get()
    expected = session.eval(
        f"struct('Vbase_kV', {vbase_kv}, 'fn_Hz', {fn_hz})", nargout=1
    )
    report = session.call("simscape_sanity", model_name, expected)
    return {
        "passed": bool(report["passed"]),
        "checks": _to_list(report.get("checks", [])),
    }
```

### 6.2 `_convert_query_result` 辅助函数

```python
def _convert_query_result(raw: Any) -> dict:
    """将 MATLAB struct 转为 Python dict，处理嵌套 cell array。"""
    if isinstance(raw, dict):
        return {k: _convert_query_result(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        return [_convert_query_result(x) for x in raw]
    return raw
```

---

## 7. 操作规程（写入 CLAUDE.md）

新增到 CLAUDE.md 的"常见修改点定位"表后：

```markdown
## Simulink 建模三步规程（防止 token 爆炸）

**加新 block 前：**
→ `simulink_inspect_ports(mdl, block_path)` 获取端口结构，不要试探

**add_line 前：**
→ `simulink_check_connection(mdl, b1, p1, b2, p2)` 验证连接合法性

**构建完成后（必须执行，不可跳过）：**
→ `simulink_run_sanity_check(mdl)` 主动检测参数异常

**禁止：** 用 `mcp__matlab__evaluate_matlab_code` 做端口枚举或参数探索
**允许：** 用 `mcp__matlab__evaluate_matlab_code` 执行有明确目的的单次操作（如修改一个参数）

**兜底约定：** 当必须用 `evaluate_matlab_code` 时，MATLAB 代码末尾加：
result_data = struct('key', value);
fprintf('%%%%RESULT_START%%%%\n');
disp(jsonencode(result_data));
fprintf('%%%%RESULT_END%%%%\n');
```

---

## 8. 预期效果

| 场景 | 实施前 | 实施后 |
|------|--------|--------|
| 查新 block 端口 | 18 轮试探 ~32k tokens | 1 次 `inspect_ports` ~150 tokens |
| H vs mH 类静默错误 | 靠 P_e≈0 倒推，~10k tokens | `sanity_check` 直接报 "L=1500H 超出范围" |
| 构建脚本输出噪声 | 500+ 行 stdout | 新工具返回结构化 dict，无噪声 |
| 连接失败重试 | 换端口盲试 | `check_connection` 提前告知原因 |

---

## 9. 实施顺序与依赖

```
Step 1: simscape_query.m （'ports' + 'params' + 'network'）
Step 2: simscape_sanity.m
Step 3: simscape_query.m 的 'connect_test' action（临时模型方案）
Step 4: mcp_simulink_tools.py 新增 4 个函数
Step 5: CLAUDE.md 更新规程
Step 6: 验证：用新工具重新查一个已知 block（CVS 或 RLC），对比结果与 sim_kundur_status.md 端口表
```

Step 1-3 可并行（都是 MATLAB 侧），Step 4 依赖 Step 1-3，Step 5-6 依赖 Step 4。

---

## 10. 不在本 spec 范围内

- MATPOWER load flow 初始化（独立 spec：2026-03-31-kundur-load-flow-design.md）
- Fast Restart / Accelerator Mode 训练优化（待端到端训练跑通后再设计）
- `mcp__matlab__evaluate_matlab_code` 的输出拦截（外部工具，无法修改）
