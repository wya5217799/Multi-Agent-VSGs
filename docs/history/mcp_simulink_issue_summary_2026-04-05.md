# Simulink MCP 报错汇总

日期: 2026-04-05  
工作区: `C:\Users\27443\Desktop\Multi-Agent  VSGs`  
场景: `sim_ne39` / `NE39bus_v2.slx` / `kundur_vsg.slx`

## 结论

当前 Simulink MCP 不是“整体不可用”，而是“部分工具可用、部分工具在模型级查询时不稳定”，主要问题集中在：

1. 工具间的模型加载/路径引导不一致。
2. 多个工具把底层 MATLAB 异常吞成 `Unknown exception`。
3. 某些工具对 `sps_lib` / Specialized Power Systems 库支持不完整。
4. 个别参数接口存在易误用点，失败时提示不足。

可用能力：

- `simulink_load_model`
- `simulink_loaded_models`
- 顶层 `simulink_get_block_tree`

不稳定或失败能力：

- `simulink_preflight`
- `simulink_query_params`
- `simulink_describe_block_ports`
- `simulink_get_block_tree` 的子系统根路径模式
- `simulink_run_script`（涉及 `get_param` / 子系统查询时）

## 问题 1: 工具间 bootstrap path 不一致

### 现象

`simulink_load_model('NE39bus_v2')` 可以成功加载模型，但后续部分工具再次执行 `load_system('NE39bus_v2')` 时直接报：

`MATLAB call failed: load_system('NE39bus_v2') — Unknown exception`

### 复现

失败工具示例：

- `simulink_query_params(model_name='NE39bus_v2', ...)`
- `simulink_describe_block_ports(model_name='NE39bus_v2', block_path='NE39bus_v2/VSG_ES1')`

### 期望

只要模型已经通过 `simulink_load_model` 成功加载，后续同会话工具应能稳定访问该模型。

### 实际

后续工具内部再次 `load_system(model_name)` 时会失败，并且报错被压成 `Unknown exception`。

### 已确认根因

从本地代码看，`simulink_load_model()` 会：

- 解析 `.slx` 真正路径
- 自动 `addpath` 到对应 `simulink_models/`、场景目录、`matlab_scripts/`
- 再调用 `load_system(full_path)`

但其他很多工具只做：

- `session.call("load_system", model_name, nargout=0)`

它们没有走同样的 bootstrap 流程。

### 旁证

直接走仓库自带 Python bridge 时，只要先手动：

- `addpath('...\\scenarios\\new_england\\simulink_models')`
- `load_system('NE39bus_v2')`

后续 `get_param('NE39bus_v2/VSrc_ES1', 'BlockType')` 就可以正常工作。

### 影响

这会导致“加载模型成功，但多数查询工具不可继续使用”的假正常状态。

### 建议修复

所有依赖 `model_name` 的工具统一复用 `_resolve_model_load_target()` + `_collect_model_bootstrap_paths()` 逻辑，而不是只在 `simulink_load_model()` 里做一次。

## 问题 2: 多个工具吞掉底层 MATLAB 异常，只剩 `Unknown exception`

### 现象

以下调用都只返回 `Unknown exception`，无法看到真实 MATLAB 错误：

- `simulink_run_script("disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','BlockType')])")`
- `simulink_get_block_tree(model_name='NE39bus_v2', root_path='NE39bus_v2/VSrc_ES1', ...)`
- `simulink_preflight(lib_name='sps_lib', block_display_name='Controlled Voltage Source')`

### 期望

至少应透传原始 MATLAB 异常消息，例如：

- 找不到块
- 参数名不存在
- 库未加载
- 返回类型不匹配

### 实际

MCP 侧只显示：

`MATLAB call failed: ... — Unknown exception`

### 旁证

同样的查询改用本地 Python bridge 直接调用 `MatlabSession.call('get_param', ...)` 时，真实异常能够正常返回。例如：

- `load_system('NE39bus_v2')` 缺路径时会明确报“找不到系统或文件”
- `get_param('kundur_vsg/CVS_ES1','Amplitude')` 会明确报该 mask 没有这个参数

### 影响

工具一旦失败，几乎无法判断是：

- 路径问题
- MATLAB helper 问题
- 返回值类型转换问题
- 真正的 Simulink 建模错误

### 建议修复

在 MCP 封装层保留并返回底层 `MatlabCallError` 的完整 message，不要把 helper 层异常统一压成 `Unknown exception`。

## 问题 3: `simulink_get_block_tree` 仅顶层可用，子系统 root_path 模式失效

### 现象

成功：

- `simulink_get_block_tree(model_name='NE39bus_v2', max_depth=2)`

失败：

- `simulink_get_block_tree(model_name='NE39bus_v2', root_path='NE39bus_v2/VSrc_ES1', max_depth=4)`
- `simulink_get_block_tree(model_name='NE39bus_v2', root_path='NE39bus_v2/G2/WF2_Src', max_depth=4)`

### 期望

既然工具支持 `root_path`，应能对子系统局部展开树。

### 实际

子系统路径模式直接报 `Unknown exception`。

### 影响

无法对大模型做局部结构诊断，只能读顶层全树，信息密度低且容易溢出。

### 建议修复

检查 `vsg_get_block_tree` 对子系统路径的处理，尤其是：

- `getfullname` / `find_system` 是否接受该路径
- MATLAB struct/cell 返回是否在 Python 侧正确转换

## 问题 4: `simulink_preflight` 对 `sps_lib` 库块不可用

### 现象

失败调用：

- `simulink_preflight(lib_name='powerlib', block_display_name='Controlled Voltage Source')`
- `simulink_preflight(lib_name='sps_lib', block_display_name='Controlled Voltage Source')`

前者返回“not found”，后者直接 `Unknown exception`。

### 实际核实

通过本地 MATLAB 查询，真实存在的 SPS 单相可控源路径是：

- `sps_lib/Sources/Controlled Voltage Source`

并且该块确实有：

- 1 个 Simulink `Inport`
- 左右各 1 个电气连接端

### 影响

无法依赖 `simulink_preflight` 做 SPS 库块发现，尤其在需要确认端口/参数名时会卡住。

### 建议修复

补齐 `vsg_preflight` 对 `sps_lib` 这类 Specialized Power Systems 库的支持，并确认其对多行显示名、换行名称、mask block 的匹配方式。

## 问题 5: `simulink_query_params` 接口存在明显误用陷阱

### 现象

我第一次调用时传了：

- `param_names="ReferenceBlock,BlockType,MaskType,MaskNames,Ports,Position"`

返回结果是全部 `missing_params`。

### 已确认原因

Python 封装里 `_ParamNamesArg` 只会把字符串包装成单元素列表：

- `["ReferenceBlock,BlockType,..."]`

它不会按逗号拆分。

所以工具实际上在查一个并不存在的参数名。

### 这是否是 MCP bug

这是“接口设计缺陷/易误用点”，不完全算底层执行 bug，但当前错误提示不足，极易误判成模型或 MATLAB 问题。

### 建议修复

二选一：

1. 显式只接受数组，不接受字符串。
2. 如果传入字符串且包含逗号，自动 split 并 trim。

## 问题 6: `simulink_run_script` 在简单块查询场景下也不稳定

### 现象

简单脚本：

```matlab
disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','BlockType')])
```

通过 MCP `simulink_run_script` 调用时直接 `Unknown exception`。

但直接经 Python bridge 执行等价 `get_param` 可以成功，返回：

- `NE39bus_v2/VSrc_ES1 -> BlockType = SubSystem`
- `ReferenceBlock = spsThreePhaseSourceLib/Three-Phase Source`
- `MaskType = Three-Phase Source`

### 说明

问题更像是：

- `vsg_run_quiet` 的执行上下文
- 或 MATLAB Engine 返回值/异常在 MCP 层的封装

而不是模型本身不可查询。

### 建议修复

对 `simulink_run_script` 增加最小集成测试：

- 先 `addpath`
- 再 `load_system`
- 再跑单条 `get_param`

确认 helper 返回 message 而不是 `Unknown exception`。

## 非 MCP bug，但容易混淆的调查结论

以下现象本身不是 MCP 缺陷，单独列出避免误判：

### A. `powerlib` 不是 SPS 全部库根

之前假设 `Controlled Voltage Source` 在 `powerlib` 下，实际不对。  
SPS 单相可控源位于：

- `sps_lib/Sources/Controlled Voltage Source`

而 NE39 现有三相固定源来自：

- `spsThreePhaseSourceLib/Three-Phase Source`

所以：

- `find_system('powerlib', ...)` 没命中，并不自动说明工具坏了
- 也可能只是库根选错

### B. `find_system(0, ...)` 返回数值句柄

当搜索根对象是 `0` 时，MATLAB 可能返回 block handles，不是 cellstr 路径。  
如果脚本里直接写 `hits{i}`，会报：

`此类型的变量不支持使用花括号进行索引`

这是 MATLAB 返回类型特性，不是 MCP bug。

## 当前稳定 workaround

在 MCP 修好前，若必须继续做 Simulink 诊断，当前最稳的替代方案是仓库自带 Python bridge：

1. `from engine.matlab_session import MatlabSession`
2. 手动 `addpath(...)`
3. `load_system(model_name)`
4. 直接 `get_param(...)`

当前已通过该路径稳定拿到的关键信息包括：

- `NE39bus_v2/VSrc_ES1` 是 `spsThreePhaseSourceLib/Three-Phase Source`
- `NE39bus_v2/G2/WF2_Src` 也是同类固定三相源
- `VSG_ES1/delta` 当前唯一去向是 `Log_delta_ES1`
- `VSG_ES1/IntD` 初始条件当前为 `0`
- `kundur_vsg/CVS_ES1` 是 `ee_lib/Sources/Controlled Voltage Source (Three-Phase)`
- SPS 单相可控源实际存在于 `sps_lib/Sources/Controlled Voltage Source`

## 建议优先修复顺序

1. 统一所有工具的 model bootstrap 逻辑。
2. 保留底层 MATLAB 原始报错，去掉 `Unknown exception` 吞错。
3. 修复 `simulink_preflight` 对 `sps_lib` 的支持。
4. 修复 `simulink_get_block_tree(root_path=...)` 子系统模式。
5. 收紧或修正 `simulink_query_params.param_names` 接口。

## 建议回归用例

修完后建议至少跑下面这些最小回归：

1. `simulink_load_model('NE39bus_v2')`
2. `simulink_query_params(... block_paths=['NE39bus_v2/VSrc_ES1'], param_names=['ReferenceBlock','MaskType'])`
3. `simulink_get_block_tree(model_name='NE39bus_v2', root_path='NE39bus_v2/VSrc_ES1', max_depth=3)`
4. `simulink_preflight(lib_name='sps_lib', block_display_name='Controlled Voltage Source')`
5. `simulink_run_script("disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','ReferenceBlock')])")`

## Resolution Update (2026-04-05)

Resolved in repository code:

1. Model bootstrap is now centralized in `engine/mcp_simulink_tools.py`.
   Model-based facades no longer call `load_system(model_name)` directly.
   They resolve the `.slx` path, add scenario bootstrap paths, and then load once.
2. MATLAB engine error wrapping now preserves specific underlying messages instead of
   collapsing everything into `Unknown exception` when better detail is available.
3. `simulink_query_params` now splits comma-separated `param_names` strings.
4. `simulink_run_script` now auto-bootstrap known repository models referenced from
   inline MATLAB code or resolvable `.m` scripts before calling `vsg_run_quiet`.
5. `vsg_preflight` now uses variant-aware `find_system` queries and fallback matching
   on normalized block name / mask type, which avoids the variant warning that could
   corrupt MCP transport output.

Verification completed:

- `pytest tests/test_mcp_simulink_tools.py tests/test_matlab_session.py -q`
  => 74 passed
- Real MATLAB facade checks completed successfully for:
  - `simulink_load_model('NE39bus_v2')`
  - `simulink_query_params(... 'NE39bus_v2/VSrc_ES1' ...)`
  - `simulink_get_block_tree(root_path='NE39bus_v2/VSrc_ES1')`
  - `simulink_preflight('sps_lib', 'Controlled Voltage Source')`
  - `simulink_run_script("disp(['RESULT=' get_param('NE39bus_v2/VSrc_ES1','ReferenceBlock')])")`
