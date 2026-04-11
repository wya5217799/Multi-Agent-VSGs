"""
快速测试: NE 环境 M0=12 + substep=5 的 TDS 崩溃率
只跑 NE, 只统计结果, 抑制 ANDES warning
"""
import importlib.util
import os, sys, time, warnings, logging
import numpy as np
import pytest

# 抑制所有 ANDES 输出
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("andes") is None,
    reason="ANDES is optional in this Windows workspace; NE quick test runs where andes is installed.",
)

# 重定向 stdout 来抑制 ANDES 的 print 输出
import io
from contextlib import redirect_stdout

if importlib.util.find_spec("andes") is not None:
    from env.andes.andes_ne_env import AndesNEEnv


def run_test(n_episodes=10, max_steps=15):
    """NE 环境随机动作测试."""
    env = AndesNEEnv(random_disturbance=True, comm_fail_prob=0.0)
    N = env.N_AGENTS
    rng = np.random.default_rng(42)

    crashes = 0
    results = []
    t0 = time.time()

    for ep in range(n_episodes):
        # 抑制 ANDES setup 输出
        f = io.StringIO()
        try:
            with redirect_stdout(f):
                obs = env.reset()
        except Exception as e:
            crashes += 1
            results.append((ep, 0, "RESET_FAIL"))
            continue

        ep_steps = 0
        ep_status = "OK"
        for step in range(max_steps):
            actions = {i: rng.uniform(-1, 1, size=2) for i in range(N)}
            try:
                with redirect_stdout(f):
                    obs, rewards, done, info = env.step(actions)
                ep_steps += 1
                if info.get('tds_failed', False):
                    ep_status = f"TDS_FAIL@step{step}"
                    crashes += 1
                    break
                if done:
                    break
            except Exception as e:
                ep_status = f"EXCEPTION@step{step}"
                crashes += 1
                break

        elapsed = time.time() - t0
        results.append((ep, ep_steps, ep_status))

        # 只输出到 stderr (不被 ANDES stdout 淹没)
        sys.stderr.write(f"EP {ep:2d}: {ep_status:20s} steps={ep_steps:2d}  "
                        f"[{elapsed:.0f}s]\n")
        sys.stderr.flush()

    elapsed = time.time() - t0
    env.close()
    return crashes, n_episodes, results, elapsed


if __name__ == "__main__":
    sys.stderr.write("=" * 50 + "\n")
    sys.stderr.write(f"NE M0={AndesNEEnv.VSG_M0}, SUBSTEPS={AndesNEEnv.N_SUBSTEPS}\n")
    sys.stderr.write(f"scale_M={AndesNEEnv._SCALE_M}, "
                     f"M_range=[{AndesNEEnv.VSG_M0 + AndesNEEnv.DM_MIN:.1f}, "
                     f"{AndesNEEnv.VSG_M0 + AndesNEEnv.DM_MAX:.1f}]\n")
    sys.stderr.write("=" * 50 + "\n")

    crashes, total, results, elapsed = run_test(n_episodes=10, max_steps=15)

    sys.stderr.write(f"\n{'='*50}\n")
    sys.stderr.write(f"RESULT: {crashes}/{total} crashed "
                     f"({crashes/total*100:.0f}%), {elapsed:.0f}s\n")
    sys.stderr.write(f"{'='*50}\n")
