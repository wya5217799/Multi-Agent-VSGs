# 2026-04-11 导航层保鲜机制

## 背景

仓库导航层（CLAUDE.md / AGENTS.md / MEMORY.md / 私有记忆 MEMORY.md）长期存在失真问题。
根因不是某几个文件写错了，而是整个导航层没有和代码演进建立同步机制。

### 诊断结果

**两个导航平面重叠且无同步协议：**

| 平面 | 文件 | 职责 |
|------|------|------|
| Repo 平面 | `CLAUDE.md` + `AGENTS.md` + repo `MEMORY.md` + `docs/` | 仓库导航 |
| Private 平面 | `~/.claude/.../memory/MEMORY.md` + 29 个记忆文件 | Claude 会话状态 |

**已确认的 5 类问题：**

| ID | 问题 | 严重度 |
|----|------|--------|
| C1 | 引用完整性无校验（CLAUDE.md 有死链） | 高 — 误导 agent |
| C2 | 私有 MEMORY.md 复制了 CLAUDE.md 的 Scenario Router 表 | 中 — 双写漂移 |
| C3 | `simulink_base.md` / `simulink_debug.md` 只在私有记忆里，非 Claude agent 无法访问 | 中 — 跨 agent 不可用 |
| C4 | CLAUDE.md 路径表纯手维护，重构后无人同步 | 中 — 静默累积 |
| C5 | 代码变更不触发导航更新提醒 | 低 — 长期漂移 |

### 关键发现

**标准开源 link checker（lychee / markdown-link-check / linkcheckmd）都不能解决核心问题**：
- 本项目导航文件大量使用 `` `path/to/file.py` `` 反引号路径格式
- 所有现成工具只识别 `[text](path)` 标准 Markdown 链接
- 必须自写主检查器

## 决策

### 工具定位

- **`scripts/lint_nav.py`** = 主检查器（自写，覆盖反引号路径 + 标准链接）
- **lychee** = 可选附加检查器（兜底标准链接 / 外链，不是核心依赖）

### 不引入的工具

| 工具 | 原因 |
|------|------|
| pre-commit 框架 | 独立研究者项目，只有 1-2 个 hook，直接 pytest 更轻 |
| MkDocs / mkdocstrings | 文档读者是 AI agent，不需要站点 |
| markdownlint-cli2 | 需要 Node，格式 lint 对 agent 手册价值低 |
| CODEOWNERS | 独立开发者，无 review routing 需求 |
| Vale | 措辞管控对一人项目过度 |
| Drift / driftcheck | 太新太重，不成熟 |

### 能力分层

| 层 | 能力 | 实现方式 |
|----|------|----------|
| 机械正确性 | 反引号路径 + 标准链接存在性校验 | `scripts/lint_nav.py`（自写） |
| 机械正确性 | 路径逃逸检测（防 `../` 误 pass） | `scripts/lint_nav.py` 内置 |
| 机械正确性 | 标准 Markdown 链接 + 外链校验 | lychee（可选附加） |
| 语义正确性 | scenario registry / harness 一致性 | `lint_nav.py` Phase 2 扩展 |
| 自动生成 | 路径表从代码 derive | `scripts/gen_nav_table.py`（Phase 2） |
| 架构收口 | 消除双层重复、知识库归位 | 一次性手动整理 |

## 实施计划

### Phase 1：止血 + 防回归 ✅ 已完成

| 步骤 | 内容 | 状态 |
|------|------|------|
| S1 | 写 `scripts/lint_nav.py` — 扫描反引号路径 + 标准链接，验证存在性 | ✅ 完成 |
| S2 | 修复 CLAUDE.md 3 处死链 | ✅ 完成 |
| S3 | 写 `tests/test_nav_integrity.py` — pytest 集成 | ✅ 完成 |
| Review | code-reviewer 审查，合入 2 项修复（路径逃逸检测 + 无文件时 fail） | ✅ 完成 |

**交付物：**
- `scripts/lint_nav.py` — 主检查器（~160 行）
- `tests/test_nav_integrity.py` — pytest 集成（~25 行）
- `CLAUDE.md` — 删除 `feedback_token_circuit_breaker.md` 引用、删除 `feedback_action_mapping.md` 引用、补全 `ne39_simulink_env.py` 路径

**验证：** `pytest tests/test_nav_integrity.py` → PASSED

### Phase 2：架构整理（一次性，无需工具） ✅ 已完成

| 步骤 | 内容 | 状态 |
|------|------|------|
| S4 | 知识库迁入仓库：从私有记忆复制 `simulink_base.md` / `simulink_debug.md` 到 `docs/knowledge/`，更新 CLAUDE.md 引用路径，从 `lint_nav.py` 白名单中移除 | ✅ 完成 |
| S5 | 消除双层路由表：私有 MEMORY.md 删除 Scenario Router 表，替换为一行 "→ 见 CLAUDE.md 后端×拓扑表" | ✅ 完成 |

**S4 细节：**
1. 创建 `docs/knowledge/` 目录
2. 从 `~/.claude/projects/C--Users-27443-Desktop-Multi-Agent--VSGs/memory/` 复制：
   - `simulink_base.md` → `docs/knowledge/simulink_base.md`
   - `simulink_debug.md` → `docs/knowledge/simulink_debug.md`
3. 更新 CLAUDE.md：
   - `simulink_base.md` → `docs/knowledge/simulink_base.md`（3 处）
   - `simulink_debug.md` → `docs/knowledge/simulink_debug.md`（2 处）
4. 更新 `lint_nav.py` PRIVATE_MEMORY_FILES：移除这两个文件
5. 更新私有 MEMORY.md 中的索引链接（指向仓库路径或删除重复条目）
6. 运行 `pytest tests/test_nav_integrity.py` 验证

**S5 细节：**
1. 编辑 `~/.claude/projects/.../memory/MEMORY.md`
2. 删除第 3-11 行的 Scenario Router 表
3. 替换为：`> 场景路由表见 CLAUDE.md "后端 × 拓扑 → 关键文件" 部分，此处不再重复。`
4. 私有 MEMORY.md 的 Scenario Status 部分保留（这是会话状态，不重复）

### Phase 3：保鲜机制 ✅ 已完成

| 步骤 | 内容 | 状态 |
|------|------|------|
| S6 | 安装 lychee + `.lychee.toml` + `tests/test_lychee_links.py` pytest wrapper | ✅ 完成 |
| S7 | `scripts/gen_nav_table.py` — 扫描代码自动生成路径表，输出 diff | ✅ 完成 |
| S8 | `lint_nav.py` 扩展：校验 CLAUDE.md scenario 表 vs harness_reference.json | ✅ 完成 |

**S6 细节（lychee 附加检查器）：**
```toml
# .lychee.toml
exclude_path = ["_archive", "node_modules", ".git", ".pytest_cache"]
include_fragments = true
no_progress = true
# 只检查本地文件，不检查远程 URL（避免网络依赖）
exclude = ["^https?://"]
```

**S7 细节（路径表半自动生成）：**
- 扫描 `scenarios/*/train_*.py` 提取训练脚本
- 扫描 `env/*/` 下的 `*_env.py` 提取环境类
- 扫描 `scenarios/*/config*.py` 提取配置文件
- 输出与 CLAUDE.md 中路径表的 diff
- 人工确认后更新（不自动覆写）

## lint_nav.py 设计要点

**扫描目标：** `CLAUDE.md`、`AGENTS.md`、`MEMORY.md`（repo 根目录）

**两种引用格式：**
1. 反引号路径：`` `env/simulink/foo.py` `` — 用正则 + 启发式过滤
2. 标准链接：`[text](path)` — 用正则，跳过 URL 和锚点

**启发式过滤（_is_path_like）：**
- 排除含 `(=→+,{[>` 的表达式（函数调用、赋值等）
- 排除含 `*` 的 glob 模式
- 排除含空格的描述文本
- 排除全大写 `/` 分隔的变量列表（如 `H_MIN/H_MAX/D_MIN/D_MAX`）
- `::` 后缀剥离（如 `base_env.py::_compute_rewards()`）

**安全措施：**
- 路径包含检查：`../` 逃逸 repo 边界的引用报错
- 代码块跳过：``` 围栏内的内容不检查
- 私有记忆白名单：PRIVATE_MEMORY_FILES 中的文件名跳过

**当前白名单（Phase 2 后会缩小）：**
```
simulink_debug.md, simulink_base.md,
sim_kundur_status.md, sim_ne39_status.md,
andes_kundur_status.md, andes_ne39_status.md
```

## 相关提交

- Phase 1-3 实现：待提交（当前在工作区，未 commit）

## Phase 3 交付物

- `.lychee.toml` — lychee 配置（排除 _archive、跳过远程 URL）
- `tests/test_lychee_links.py` — pytest wrapper（lychee 未安装时自动 skip）
- `scripts/gen_nav_table.py` — 从代码自动生成场景路径表，与 CLAUDE.md 比对输出 diff
- `scripts/lint_nav.py` — 新增 `check_harness_consistency()` 校验 harness_reference.json 一致性

## 相关文档

- [Harness architecture](2026-04-05-harness-architecture.md)
- [Project memory system](2026-04-06-project-memory-system.md)
