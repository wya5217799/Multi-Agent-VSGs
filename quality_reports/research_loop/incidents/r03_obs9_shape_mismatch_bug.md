# Incident — R03 obs9 smoke fail, root = SAC actor 用 class attr OBS_DIM=7 init

**Date**: 2026-05-07
**Round**: R03
**Severity**: med (smoke 失败但容易修)

## 现象
`r03_INCLUDE_OWN_ACTION_OBS_smoke` exit 非 0:
```
ValueError: could not broadcast input array from shape (9,) into shape (7,)
File "agents/replay_buffer.py", line 24, in add: self.obs[self.ptr] = obs
```

## Root cause
我的 R03 patch (`base_env.py`) 在 `__init__` 把 `self.OBS_DIM = 7+2 = 9` (instance attr).
但 `train_andes.py:108` 用 **类属性** `AndesMultiVSGEnv.OBS_DIM` (= 7) 初始化 SACAgent:
```python
obs_dim = AndesMultiVSGEnv.OBS_DIM   # 类属性 = 7, 不读 env var INCLUDE_OWN_ACTION_OBS
agent = SACAgent(obs_dim=obs_dim, ...)
```
ReplayBuffer 用 obs_dim=7 分配 → env 返 obs (9,) → `self.obs[self.ptr] = obs` shape mismatch.

## 修复 (R04 #1 优先级低复杂度)
```python
# train_andes.py 改用 env 实例属性
env_tmp = AndesMultiVSGEnv()      # 临时构造拿 instance OBS_DIM
obs_dim = env_tmp.OBS_DIM         # 读 instance, 已经被 INCLUDE_OWN_ACTION_OBS env var 改过
env_tmp.close()
```
或更简单:
```python
import os
include_own_action = bool(int(os.environ.get("INCLUDE_OWN_ACTION_OBS", "0")))
obs_dim = AndesMultiVSGEnv.OBS_DIM + (2 if include_own_action else 0)
```

## 影响
INCLUDE_OWN_ACTION_OBS 完全没测过. 不知 SAC 是否能利用 last action 改善 collapse.
R04 修后跑 1 seed × 50ep smoke 重测.

## Lesson
class attr vs instance attr 在 monkey-patch / env-var override 时要小心.
我加 patch 时只改 instance, train_andes 还用类属性 → 失败.
未来 OBS_DIM 改动必同时:
1. base_env `__init__` 设 instance attr
2. train_andes 读 env var (不读类属性)
3. eval driver 同上
