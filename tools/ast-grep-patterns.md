# ast-grep Pattern Library — Multi-Agent VSGs

> Structural code search patterns for this repository.
> Run all patterns with: `sg run -p '<pattern>' -l python <path>`
>
> No match = exit code 1 with no output (expected for "should be empty" checks).

---

## 1. 调用链切面：谁在碰 MATLAB？

```bash
# 所有直接调用 session.call() 的位置（L1→MATLAB IPC 边界）
sg run -p '$OBJ.call($$$)' -l python engine/ env/

# 所有 SimulinkBridge 实例化位置（谁在构造 L3 接口？）
sg run -p 'SimulinkBridge($$$)' -l python .
```

**预期产出（2026-04-14）：**
- `session.call()`: `engine/simulink_bridge.py` 多处（L1 边界全集中于此）
- `SimulinkBridge(...)`: 仅在 `tests/` 出现（生产代码通过 config 依赖注入）

---

## 2. 接口一致性：所有 step/reset/reward 实现

```bash
# 所有 def step 实现（env 接口检查）
sg run -p 'def step(self, $$$)' -l python env/ engine/

# 所有 def reset 实现
sg run -p 'def reset(self, $$$)' -l python env/

# 所有 def _compute_rewards 实现（奖励函数跨后端对比）
sg run -p 'def _compute_rewards(self, $$$)' -l python env/
```

**用途：** 确认三后端（andes/ode/simulink）的 step/reset 签名是否对齐。

---

## 3. 配置追踪：谁从 config 读常量？

```bash
# 从顶层 config.py 导入的所有位置
sg run -p 'from config import $$$' -l python .

# 从 scenario-level config_simulink 导入的所有位置
sg run -p 'from scenarios.$SCENARIO.$MODULE import $$$' -l python .

# 直接读 H_MIN/H_MAX/D_MIN/D_MAX 的位置（物理参数漂移检测）
sg run -p '$X.H_MIN' -l python .
sg run -p '$X.H_MAX' -l python .
```

---

## 4. 双控制线验证：有没有越界？

```bash
# training_tasks 里有没有 import modeling 相关（应无输出）
sg run -p 'from engine.modeling_tasks import $$$' -l python engine/training_tasks.py

# modeling_tasks 里有没有 import training 相关（应无输出）
sg run -p 'from engine.training_tasks import $$$' -l python engine/modeling_tasks.py

# agents/ 里有没有 import engine（应无输出）
sg run -p 'from engine import $$$' -l python agents/
sg run -p 'import engine' -l python agents/
```

**预期：** 所有命令均无输出（exit code 1）——架构边界清洁。
**若有输出则违反双控制线规则**，需同步更新 `.importlinter` contract。

---

## 5. Artifact 写入点：谁在写 run 结果？

```bash
# 所有 json.dump 调用（训练结果持久化位置）
sg run -p 'json.dump($$$)' -l python .

# 所有 json.dumps 调用
sg run -p 'json.dumps($$$)' -l python .

# torch.save 调用（模型权重写入位置）
sg run -p 'torch.save($$$)' -l python .
```

---

## 6. 奖励函数审计：reward 公式是否对齐论文？

```bash
# 所有 reward 相关变量赋值
sg run -p '$REWARD = $$$' -l python env/

# 协调惩罚项（r_h = mean(ΔH)²，不是 mean(ΔH²)）
sg run -p 'np.mean($X) ** 2' -l python env/
sg run -p 'np.mean($X ** 2)' -l python env/
```

**注意：** 根据 `feedback_reward_formula.md`，正确公式是 `(mean(ΔH))²`，
即 `np.mean(delta_h) ** 2`，而不是 `np.mean(delta_h ** 2)`。

---

## 7. MCP 工具注册：哪些函数被暴露给 Claude？

```bash
# MCP 工具注册点（mcp_server.py 用 add_tool 而非 @decorator）
sg run -p 'mcp.add_tool($$$)' -l python engine/

# harness_tasks 里的所有 async def（MCP 异步工具实现）
sg run -p 'async def $FUNC($$$)' -l python engine/

# 所有 TaskRecord 实例化（任务生命周期追踪）
sg run -p 'TaskRecord($$$)' -l python engine/
```

---

## 8. 启动路径检查：python 可执行路径

```bash
# 所有 subprocess 调用（训练子进程启动）
sg run -p 'subprocess.Popen($$$)' -l python .
sg run -p 'subprocess.run($$$)' -l python .

# 所有 sys.executable 引用（Python 路径传播）
sg run -p 'sys.executable' -l python .
```

**注意（`feedback_launch_env.md`）：** 必须用完整路径 `andes_env\python.exe`，
裸 `python` = 系统 Python 3.12 = 无 matlab.engine = 静默失败。

---

## 使用技巧

- **输出文件名只**：`sg run -p '<pattern>' -l python <path> --json | python -c "import sys,json; [print(m['file']) for m in json.load(sys.stdin)['matches']]"`
- **结合 grep**：管道到 `grep -n` 可加行号过滤
- **批量扫描**：将常用检查组合成 `tools/arch-check.sh`
- **CI 集成**：无匹配返回 exit 0，有匹配返回 exit 1 ——适合"禁止出现 X"类检查

---

*生成日期：2026-04-14 | pydeps 3.0.2 | ast-grep 0.42.1 | import-linter 2.11*
