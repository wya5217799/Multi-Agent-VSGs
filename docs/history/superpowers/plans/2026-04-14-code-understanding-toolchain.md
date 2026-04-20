# Code Understanding Toolchain — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为仓库建立可重复使用的代码理解工具链，覆盖模块依赖可视化、架构边界执行、结构化代码搜索三个维度。

**前置共识（Codex + Opus 对齐结论）：**
- 仓库本质是"2 scenario × 3 backend 的多模块科研仿真平台 + 显式双控制线"
- 工具必须优先覆盖 Python 依赖关系和架构边界；`.slx` 内部靠仓库自带 MCP 工具
- 最终工具组合：**pydeps + import-linter + ast-grep**（aider 为交互理解备选）

**Tech Stack:** pydeps, import-linter, ast-grep, GraphViz, pytest (架构测试)

---

## Scope

本计划 **不做**：
- 不改动任何生产代码
- 不引入运行时监控（W&B / MLflow / Langfuse）
- 不处理 `.slx` 内部结构分析
- 不替代仓库已有的 contract.py / harness_reference.py

本计划 **做**：
- 安装并配置 3 个工具
- 生成可交付的架构可视化产物
- 将架构约束固化为可执行的 CI 规则
- 建立结构化搜索的常用 pattern 库

---

## Phase 1: pydeps — 模块依赖可视化（30 min）

### 1.1 安装
- [ ] `pip install pydeps` (当前 Python 环境)
- [ ] 安装 GraphViz 并确认 `dot` 在 PATH 上：`dot -V`
- [ ] 验证：`pydeps --version`

### 1.2 生成分层依赖图

输出到 `docs/architecture/` 目录。每张图聚焦一个层。

- [ ] **Engine 层**（双控制线 + Simulink 原语）：
  ```bash
  pydeps engine --only engine --max-module-depth 2 \
    --cluster --rankdir LR --noshow \
    -o docs/architecture/deps_engine.svg
  ```
  **验证要点**：`training_tasks` 和 `modeling_tasks` 之间不应有箭头

- [ ] **Env 层**（三后端独立性）：
  ```bash
  pydeps env --only env --max-module-depth 3 \
    --cluster --rankdir LR --noshow \
    -o docs/architecture/deps_env.svg
  ```
  **验证要点**：`env.andes`、`env.ode`、`env.simulink` 三个子包之间不应有交叉箭头

- [ ] **Scenarios 层**（2 scenario × 3 backend 的组织）：
  ```bash
  pydeps scenarios --only scenarios --max-module-depth 3 \
    --cluster --rankdir LR --noshow \
    -o docs/architecture/deps_scenarios.svg
  ```

- [ ] **全局概览**（深度 2，排除 tests/plotting）：
  ```bash
  pydeps . --max-module-depth 2 \
    --exclude tests plotting _archive docs scripts tools \
    --cluster --rankdir LR --noshow \
    -o docs/architecture/deps_overview.svg
  ```

- [ ] 检查有无循环依赖：`pydeps . --show-cycles`

### 1.3 交付物
- `docs/architecture/deps_engine.svg`
- `docs/architecture/deps_env.svg`
- `docs/architecture/deps_scenarios.svg`
- `docs/architecture/deps_overview.svg`

---

## Phase 2: import-linter — 架构约束执行（45 min）

### 2.1 安装
- [ ] `pip install import-linter`
- [ ] 验证：`lint-imports --version`

### 2.2 编写 `.importlinter` 配置

在项目根目录创建 `.importlinter`，按真实架构边界定义 contract：

- [ ] 创建 `.importlinter` 文件，内容如下：

```ini
[importlinter]
root_packages =
    agents
    env
    engine
    scenarios
    utils
    plotting

# ─── Contract 1: 双控制线隔离 ───
# training_tasks 是只读分析层，不得碰模型修复代码
# 这是 training_tasks.py:4 的硬编码规则的机械化检查
[importlinter:contract:training-modeling-isolation]
name = Training Control must not import Model Control
type = forbidden
source_modules =
    engine.training_tasks
forbidden_modules =
    engine.modeling_tasks
    engine.harness_repair
    engine.harness_tasks

# ─── Contract 2: modeling 不反向依赖 training ───
[importlinter:contract:modeling-training-isolation]
name = Model Control must not import Training Control
type = forbidden
source_modules =
    engine.modeling_tasks
forbidden_modules =
    engine.training_tasks

# ─── Contract 3: 三后端独立性 ───
# andes/ode/simulink 是三个平行的执行模式，互不依赖
[importlinter:contract:backend-independence]
name = Environment backends are independent
type = independence
modules =
    env.andes
    env.ode
    env.simulink

# ─── Contract 4: agents 不反向依赖 engine ───
# agents 是纯 RL 算法层（torch/numpy），不应知道 Simulink/MATLAB 的存在
[importlinter:contract:agents-no-engine]
name = Agents must not import engine
type = forbidden
source_modules =
    agents
forbidden_modules =
    engine

# ─── Contract 5: 生产代码不导入 tests ───
[importlinter:contract:no-prod-imports-tests]
name = Production code must not import tests
type = forbidden
source_modules =
    agents
    env
    engine
    scenarios
    utils
forbidden_modules =
    tests
```

### 2.3 首次运行并修复

- [ ] 运行 `lint-imports`，记录所有违规
- [ ] 对每个违规判断：是真实架构问题还是 contract 定义过严
- [ ] 调整 contract 或修复代码（优先调整 contract，不改生产代码）
- [ ] 达到 `lint-imports` 全绿

### 2.4 接入 pre-commit（可选）

- [ ] 在 `.pre-commit-config.yaml` 中添加 import-linter hook：
  ```yaml
  - repo: local
    hooks:
      - id: import-linter
        name: import-linter
        entry: lint-imports
        language: system
        pass_filenames: false
        types: [python]
  ```

### 2.5 交付物
- `.importlinter` 配置文件
- `lint-imports` 全绿的截图或日志
- （可选）pre-commit hook 配置

---

## Phase 3: ast-grep — 结构化代码搜索（30 min）

### 3.1 安装
- [ ] `pip install ast-grep-cli` 或 `cargo install ast-grep`（二选一）
- [ ] 验证：`ast-grep --version` 或 `sg --version`

### 3.2 建立常用 pattern 库

创建 `tools/ast-grep-patterns.md`，收录针对本仓库的高频搜索模式：

- [ ] 创建 pattern 文件，包含以下 patterns：

**调用链切面（"谁在碰 MATLAB？"）：**
```bash
# 所有直接调用 session.call() 的位置
sg run -p '$OBJ.call($$$)' -l python engine/ env/

# 所有调用 SimulinkBridge 的位置
sg run -p 'SimulinkBridge($$$)' -l python .
```

**接口一致性（"所有 step() 实现"）：**
```bash
# 所有 def step 实现
sg run -p 'def step(self, $$$): $$$' -l python env/ engine/

# 所有 def reset 实现
sg run -p 'def reset(self, $$$): $$$' -l python env/

# 所有 def _compute_rewards 实现
sg run -p 'def _compute_rewards(self, $$$): $$$' -l python env/
```

**配置追踪（"谁从 config 读常量？"）：**
```bash
# 从 config 导入的所有位置
sg run -p 'from config import $$$' -l python .

# 从 scenario config 导入的所有位置
sg run -p 'from scenarios.$SCENARIO.$MODULE import $$$' -l python .
```

**双控制线验证（"有没有越界？"）：**
```bash
# training_tasks 里有没有 import modeling 相关
sg run -p 'from engine.modeling_tasks import $$$' -l python engine/training_tasks.py

# modeling_tasks 里有没有 import training 相关
sg run -p 'from engine.training_tasks import $$$' -l python engine/modeling_tasks.py
```

**Artifact 写入点（"谁在写 run 结果？"）：**
```bash
# 所有 json.dump / json.dumps 调用
sg run -p 'json.dump($$$)' -l python .
sg run -p 'json.dumps($$$)' -l python .
```

### 3.3 验证 patterns

- [ ] 逐条运行上述 patterns，确认输出合理
- [ ] 删除误报率高的 pattern，保留精准的

### 3.4 交付物
- `tools/ast-grep-patterns.md`（常用 pattern 速查表）

---

## Phase 4: 可选 — pyan3 纯 Python 调用链（15 min）

> 仅当需要可视化纯 Python 内部调用链时执行（如 agent 训练链路）。
> 对跨语言路径（Python→MATLAB）无效。

- [ ] `pip install pyan3`
- [ ] 生成 agent 训练链路调用图：
  ```bash
  pyan3 agents/*.py utils/monitor.py utils/training_callback.py \
    --uses --colored --grouped --annotated \
    --dot -o docs/architecture/callgraph_agents.dot
  dot -Tsvg docs/architecture/callgraph_agents.dot \
    -o docs/architecture/callgraph_agents.svg
  ```
- [ ] 生成 harness 内部调用图：
  ```bash
  pyan3 engine/harness_*.py engine/modeling_tasks.py \
    engine/smoke_tasks.py engine/task_state.py engine/task_primitives.py \
    --uses --colored --grouped \
    --dot -o docs/architecture/callgraph_harness.dot
  dot -Tsvg docs/architecture/callgraph_harness.dot \
    -o docs/architecture/callgraph_harness.svg
  ```

---

## 完成标准

| 检查项 | 标准 |
|--------|------|
| pydeps 产出 | 4 张 SVG 在 `docs/architecture/`，无循环依赖 |
| import-linter | `lint-imports` 全绿（0 violations） |
| ast-grep | pattern 库建好，至少 8 个 pattern 验证通过 |
| 无生产代码变更 | `git diff --stat` 只含配置文件和文档 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| pydeps 需要包可 import（MATLAB 不可用时 engine 层可能失败） | 用 `--only` 限制扫描范围，或设 `PYTHONDONTWRITEBYTECODE=1` |
| import-linter 首次运行发现意外违规 | 先调 contract 再改代码；记录所有"合理但意外"的依赖 |
| ast-grep 对 Python 3.12+ 语法支持 | 验证 tree-sitter-python 版本；如有问题回退到 `sg` 二进制 |
| GraphViz 在 Windows 上 PATH 问题 | 用 `choco install graphviz` 或手动添加 bin 到 PATH |
