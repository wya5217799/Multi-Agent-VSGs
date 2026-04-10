# Training Diagnostics Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight training diagnostics layer that records physics summaries correctly, exports monitor data, and produces a 2×2 post-training diagnostic plot — without changing the Simulink IPC path or adding online visualization overhead.

**Architecture:** Three independent changes wired together: (1) fix + extend `training_log.json` to include a `physics_summary` list; (2) add monitor export calls at training end; (3) new `utils/training_viz.py` that reads both data sources and outputs a single diagnostic PNG. The plot function accepts an optional `compare_paths` list for future multi-run support but only implements single-run in this phase.

**Tech Stack:** Python 3.10+, numpy, matplotlib (already project deps). No new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `scenarios/kundur/train_simulink.py` | Track per-step physics summary; call monitor.export_csv at end |
| Modify | `scenarios/new_england/train_simulink.py` | Same as Kundur |
| Create | `utils/training_viz.py` | Read training_log.json + optional monitor CSV; output diagnostic PNG |
| Modify | `tests/test_fixes.py` | Add tests for physics summary correctness and viz smoke test |

---

## Task 1: Fix physics summary recording in Kundur training loop

**Problem being solved:** `max_freq_deviation_hz` currently records only the *last step* of each episode (via `last_info`). If peak deviation occurs at step 5 (just after disturbance), step 50 shows near-zero and the value is meaningless. Also `settled`, `mean_freq_dev_hz`, `max_power_swing` are never recorded at all.

**Files:**
- Modify: `scenarios/kundur/train_simulink.py:180-270`

- [ ] **Step 1.1: Write failing tests for physics summary**

Add to `tests/test_fixes.py`:

```python
# ---------------------------------------------------------------------------
# T6: physics_summary correctness in training_log.json
# ---------------------------------------------------------------------------

def test_physics_summary_records_episode_max_not_last_step():
    """max_freq_dev_hz must be the max over all steps, not the last-step value."""
    import json, tempfile, os
    from unittest.mock import MagicMock, patch
    import numpy as np

    # Simulate a log produced by the fixed training loop
    # Episode has peak freq dev at step 5, near-zero at step 50
    fake_log = {
        "episode_rewards": [-500.0],
        "eval_rewards": [],
        "critic_losses": [0.5],
        "policy_losses": [0.3],
        "alphas": [0.2],
        "physics_summary": [
            {
                "max_freq_dev_hz": 0.45,   # must reflect step-5 peak, not step-50 ~0
                "mean_freq_dev_hz": 0.12,
                "settled": True,
                "max_power_swing": 0.08,
            }
        ],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fake_log, f)
        path = f.name

    try:
        with open(path) as f:
            data = json.load(f)
        ps = data["physics_summary"][0]
        assert ps["max_freq_dev_hz"] == 0.45, "must be episode max, not last-step value"
        assert ps["mean_freq_dev_hz"] == 0.12
        assert ps["settled"] is True
        assert "max_power_swing" in ps
    finally:
        os.unlink(path)


def test_physics_summary_settled_false_when_frequency_not_restored():
    """settled=False when last-10-steps freq dev exceeds 0.1 Hz."""
    # Simulate episode where freq dev stays high at end (0.3 Hz final)
    # last 10 steps all above 0.1 Hz → settled must be False
    tail_freq_devs = [0.35, 0.32, 0.30, 0.28, 0.29, 0.31, 0.27, 0.26, 0.28, 0.25]
    settled = all(d < 0.1 for d in tail_freq_devs)
    assert settled is False, "should not be settled when final freq dev > 0.1 Hz"


def test_physics_summary_settled_true_when_frequency_restored():
    """settled=True when last-10-steps freq dev all below 0.1 Hz."""
    tail_freq_devs = [0.08, 0.07, 0.05, 0.04, 0.03, 0.04, 0.05, 0.06, 0.04, 0.03]
    settled = all(d < 0.1 for d in tail_freq_devs)
    assert settled is True
```

- [ ] **Step 1.2: Run tests to verify they fail (or pass structurally)**

```bash
cd "C:/Users/27443/Desktop/Multi-Agent  VSGs"
python -m pytest tests/test_fixes.py::test_physics_summary_records_episode_max_not_last_step tests/test_fixes.py::test_physics_summary_settled_false_when_frequency_not_restored tests/test_fixes.py::test_physics_summary_settled_true_when_frequency_restored -v
```

Expected: T6 structural tests pass (they test logic in isolation, not the training script itself). Proceed regardless.

- [ ] **Step 1.3: Modify training loop to accumulate physics per step**

In `scenarios/kundur/train_simulink.py`, find the episode loop setup block (around line 182) and add tracking variables:

```python
        # --- physics summary accumulators (add after existing ep_components setup) ---
        ep_max_freq_dev = 0.0          # max over all steps (fix for last_info bug)
        ep_sum_freq_dev = 0.0          # for mean calculation
        ep_step_count_actual = 0       # actual steps taken (may break early)
        ep_tail_freq_devs: list[float] = []   # last 10 steps for settled check
        ep_max_power_swing = 0.0       # max(P_es) - min(P_es) over episode
        ep_P_es_min = np.full(env.N_ESS, np.inf)
        ep_P_es_max = np.full(env.N_ESS, -np.inf)
```

- [ ] **Step 1.4: Accumulate physics inside the step loop**

Inside the `for step in range(...)` loop, after `last_info = info` (around line 204), add:

```python
            # --- accumulate physics summary ---
            step_freq_dev = info.get("max_freq_dev_hz", info.get("max_freq_deviation_hz", 0.0))
            ep_max_freq_dev = max(ep_max_freq_dev, step_freq_dev)
            ep_sum_freq_dev += step_freq_dev
            ep_step_count_actual += 1
            # track tail for settled check
            ep_tail_freq_devs.append(step_freq_dev)
            if len(ep_tail_freq_devs) > 10:
                ep_tail_freq_devs.pop(0)
            # track power swing
            p_es = info.get("P_es", None)
            if p_es is not None:
                p_arr = np.asarray(p_es)
                ep_P_es_min = np.minimum(ep_P_es_min, p_arr)
                ep_P_es_max = np.maximum(ep_P_es_max, p_arr)
```

- [ ] **Step 1.5: Compute and store physics_summary after the step loop**

After `mean_reward = ep_reward.mean()` (around line 234), add:

```python
        # --- compute episode physics summary ---
        ep_mean_freq_dev = ep_sum_freq_dev / max(ep_step_count_actual, 1)
        ep_settled = bool(ep_tail_freq_devs and all(d < 0.1 for d in ep_tail_freq_devs))
        ep_power_swing = float(np.max(ep_P_es_max - ep_P_es_min)) if ep_step_count_actual > 0 else 0.0
        log["physics_summary"].append({
            "max_freq_dev_hz": float(ep_max_freq_dev),
            "mean_freq_dev_hz": float(ep_mean_freq_dev),
            "settled": ep_settled,
            "max_power_swing": float(ep_power_swing),
        })
```

- [ ] **Step 1.6: Add `physics_summary` key to the log init dict**

Find where `log = {...}` is defined (around line 155, the `_EMPTY_LOG` structure or inline dict). Add:

```python
        log.setdefault("physics_summary", [])
```

(After loading or creating the log dict, before the training loop.)

- [ ] **Step 1.7: Add monitor export calls at training end**

After `json.dump(log, f, indent=2)` at the end of `train()` (around line 314), add:

```python
    # Export monitor data for training_viz
    monitor.export_csv(os.path.join(args.log_dir, "monitor_data.csv"))
    monitor.save_checkpoint(os.path.join(args.log_dir, "monitor_state.json"))
    print(f"Monitor data exported to {args.log_dir}/")
```

Note: `args.log_dir` is the directory containing `training_log.json`. Verify the exact attribute name in `parse_args()` — it may be `args.log_file`'s parent. Use:

```python
    log_dir = os.path.dirname(args.log_file)
    monitor.export_csv(os.path.join(log_dir, "monitor_data.csv"))
    monitor.save_checkpoint(os.path.join(log_dir, "monitor_state.json"))
```

- [ ] **Step 1.8: Commit**

```bash
git add scenarios/kundur/train_simulink.py tests/test_fixes.py
git commit -m "fix(kundur): record episode-max freq dev + physics_summary in training log"
```

---

## Task 2: Mirror same changes in NE39 training loop

**Files:**
- Modify: `scenarios/new_england/train_simulink.py` (same changes as Task 1)

- [ ] **Step 2.1: Apply identical physics summary accumulator changes**

Repeat Steps 1.3–1.7 verbatim in `scenarios/new_england/train_simulink.py`.

Key differences to watch for in NE39:
- `env.N_ESS = 8` (not 4)
- `STEPS_PER_EPISODE` may differ — use `int(env.T_EPISODE / env.DT)` same as Kundur
- The `info` key for freq dev: verify it uses `max_freq_deviation_hz` (same as Kundur — confirmed in `ne39_simulink_env.py:342`)
- Log init: find the equivalent `_EMPTY_LOG` dict or inline log creation

- [ ] **Step 2.2: Run existing test suite to confirm no regressions**

```bash
python -m pytest tests/test_fixes.py -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass (47 tests, 4 skipped).

- [ ] **Step 2.3: Commit**

```bash
git add scenarios/new_england/train_simulink.py
git commit -m "fix(ne39): record episode-max freq dev + physics_summary in training log"
```

---

## Task 3: Create `utils/training_viz.py`

**Problem being solved:** After training, the only way to see results is manually running paper plotting scripts that require ANDES environment setup. Need a standalone script that reads `training_log.json` (+ optional `monitor_data.csv`) and produces a diagnostic PNG with zero environment setup.

**Files:**
- Create: `utils/training_viz.py`

- [ ] **Step 3.1: Write failing smoke test**

Add to `tests/test_fixes.py`:

```python
# ---------------------------------------------------------------------------
# T7: training_viz smoke test
# ---------------------------------------------------------------------------

def test_training_viz_produces_png_from_log(tmp_path):
    """plot_training_summary() must produce a PNG without error given minimal log."""
    import json
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from utils.training_viz import plot_training_summary

    # Minimal valid training_log.json
    log = {
        "episode_rewards": [-500.0 + i * 0.5 for i in range(100)],
        "eval_rewards": [{"episode": 50, "reward": -480.0}, {"episode": 100, "reward": -450.0}],
        "critic_losses": [1.0 - i * 0.005 for i in range(100)],
        "policy_losses": [0.8 - i * 0.004 for i in range(100)],
        "alphas": [0.3 - i * 0.001 for i in range(100)],
        "physics_summary": [
            {"max_freq_dev_hz": 0.3 + (i % 10) * 0.01, "mean_freq_dev_hz": 0.1,
             "settled": i > 50, "max_power_swing": 0.05}
            for i in range(100)
        ],
    }
    log_path = tmp_path / "training_log.json"
    log_path.write_text(json.dumps(log))
    out_path = tmp_path / "summary.png"

    plot_training_summary(str(log_path), save_path=str(out_path))

    assert out_path.exists(), "PNG must be created"
    assert out_path.stat().st_size > 1000, "PNG must not be empty"


def test_training_viz_works_without_physics_summary(tmp_path):
    """plot_training_summary() must not crash if physics_summary key is absent (old logs)."""
    import json, sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from utils.training_viz import plot_training_summary

    log = {
        "episode_rewards": [-500.0 + i for i in range(50)],
        "eval_rewards": [],
        "critic_losses": [1.0] * 50,
        "policy_losses": [0.8] * 50,
        "alphas": [0.2] * 50,
        # no physics_summary key
    }
    log_path = tmp_path / "training_log.json"
    log_path.write_text(json.dumps(log))
    out_path = tmp_path / "summary.png"

    plot_training_summary(str(log_path), save_path=str(out_path))
    assert out_path.exists()
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_fixes.py::test_training_viz_produces_png_from_log tests/test_fixes.py::test_training_viz_works_without_physics_summary -v
```

Expected: `ImportError: No module named 'utils.training_viz'`

- [ ] **Step 3.3: Implement `utils/training_viz.py`**

```python
"""Training diagnostics visualizer for Multi-Agent VSG training runs.

Usage:
    python -m utils.training_viz results/sim_kundur/logs/training_log.json
    python -m utils.training_viz results/sim_kundur/logs/training_log.json -o summary.png

Reads:
    training_log.json  — episode_rewards, eval_rewards, critic_losses, policy_losses,
                         alphas, physics_summary (optional)
    monitor_data.csv   — reward components, action stats (optional, auto-detected
                         if present in same directory as training_log.json)

Produces:
    2×2 PNG diagnostic figure (+ optional 5th subplot if physics_summary present)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# Re-use project colour palette and helpers
try:
    from plotting.paper_style import (
        rolling_stats, COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
        apply_ieee_style, save_fig,
    )
    _HAS_PAPER_STYLE = True
except ImportError:
    _HAS_PAPER_STYLE = False

# Fallback colours when paper_style is unavailable
_C_TOTAL   = COLOR_TOTAL   if _HAS_PAPER_STYLE else "#8B3A3A"
_C_FREQ    = COLOR_FREQ    if _HAS_PAPER_STYLE else "#D2691E"
_C_INERTIA = COLOR_INERTIA if _HAS_PAPER_STYLE else "#2E8B57"
_C_DROOP   = COLOR_DROOP   if _HAS_PAPER_STYLE else "#6A0DAD"
_C_EVAL    = "#2171B5"
_C_SETTLED = "#2CA02C"
_C_UNSETTLED = "#D62728"

_WINDOW = 50  # rolling average window


def _rolling(data: list[float], window: int = _WINDOW):
    if _HAS_PAPER_STYLE:
        return rolling_stats(np.array(data), window)
    arr = np.array(data)
    n = len(arr)
    mean = np.convolve(arr, np.ones(window) / window, mode="same")
    std = np.array([np.std(arr[max(0, i - window // 2):min(n, i + window // 2 + 1)])
                    for i in range(n)])
    return mean, std


def _load_log(log_path: str) -> dict:
    with open(log_path) as f:
        return json.load(f)


def _load_monitor_csv(log_path: str) -> Optional[dict]:
    """Auto-detect and load monitor_data.csv from same dir as training_log.json."""
    csv_path = Path(log_path).parent / "monitor_data.csv"
    if not csv_path.exists():
        return None
    try:
        import csv
        rows = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return None
        # Parse into lists
        result: dict[str, list] = {k: [] for k in rows[0]}
        for row in rows:
            for k, v in row.items():
                try:
                    result[k].append(float(v))
                except ValueError:
                    result[k].append(v)
        return result
    except Exception:
        return None


def plot_training_summary(
    log_path: str,
    save_path: Optional[str] = None,
    compare_paths: Optional[list[str]] = None,  # reserved, not implemented
    show: bool = False,
) -> str:
    """Generate 2×2 (+ optional physics row) diagnostic PNG.

    Args:
        log_path: Path to training_log.json
        save_path: Output PNG path. Defaults to <log_dir>/training_summary.png
        compare_paths: Reserved for future multi-run comparison. Not implemented.
        show: If True, call plt.show() (blocks; for interactive use only).

    Returns:
        Path to saved PNG.
    """
    if _HAS_PAPER_STYLE:
        apply_ieee_style()

    log = _load_log(log_path)
    mon = _load_monitor_csv(log_path)

    rewards = log.get("episode_rewards", [])
    eval_rewards = log.get("eval_rewards", [])
    critic_losses = log.get("critic_losses", [])
    policy_losses = log.get("policy_losses", [])
    alphas = log.get("alphas", [])
    physics = log.get("physics_summary", [])

    n_ep = len(rewards)
    episodes = np.arange(n_ep)

    has_physics = len(physics) == n_ep and n_ep > 0
    has_components = mon is not None and "r_f" in mon and len(mon["r_f"]) > 0
    has_action_stats = mon is not None and "action_std_agent_0" in mon

    # Layout: 2 rows × 2 cols, plus optional 3rd row for physics
    n_rows = 3 if has_physics else 2
    fig = plt.figure(figsize=(12, 4 * n_rows))
    gs = gridspec.GridSpec(n_rows, 2, figure=fig, hspace=0.45, wspace=0.35)

    # ── (a) Episode reward ────────────────────────────────────────────
    ax_r = fig.add_subplot(gs[0, 0])
    ax_r.scatter(episodes, rewards, s=2, alpha=0.25, color=_C_TOTAL, label="_nolegend_")
    if n_ep >= _WINDOW:
        mean_r, std_r = _rolling(rewards)
        ax_r.fill_between(episodes, mean_r - std_r, mean_r + std_r,
                           color=_C_TOTAL, alpha=0.15)
        ax_r.plot(episodes, mean_r, color=_C_TOTAL, lw=1.6, label=f"Reward (avg{_WINDOW})")
    if eval_rewards:
        eval_ep = [e["episode"] for e in eval_rewards]
        eval_val = [e["reward"] for e in eval_rewards]
        ax_r.scatter(eval_ep, eval_val, s=30, color=_C_EVAL, zorder=5,
                     marker="^", label="Eval reward")
        best_idx = int(np.argmax(eval_val))
        ax_r.annotate(f"best\n{eval_val[best_idx]:.0f}",
                      xy=(eval_ep[best_idx], eval_val[best_idx]),
                      xytext=(8, 8), textcoords="offset points", fontsize=7,
                      color=_C_EVAL)
    ax_r.set_xlabel("Episode")
    ax_r.set_ylabel("Mean reward")
    ax_r.set_title("(a) Episode Reward")
    ax_r.legend(fontsize=7)

    # ── (b) Reward components ─────────────────────────────────────────
    ax_c = fig.add_subplot(gs[0, 1])
    if has_components:
        comp_ep = np.arange(len(mon["r_f"]))
        for key, color, label in [
            ("r_f", _C_FREQ,    r"$r_f$ (freq sync)"),
            ("r_h", _C_INERTIA, r"$r_h$ (inertia cost)"),
            ("r_d", _C_DROOP,   r"$r_d$ (damping cost)"),
        ]:
            vals = [abs(v) for v in mon.get(key, [])]
            if vals and len(vals) == len(comp_ep):
                mean_v, _ = _rolling(vals, min(_WINDOW, len(vals)))
                ax_c.plot(comp_ep, mean_v, color=color, lw=1.4, label=label)
        ax_c.set_xlabel("Episode")
        ax_c.set_ylabel("|reward component|")
        ax_c.set_title("(b) Reward Components")
        ax_c.legend(fontsize=7)
    else:
        ax_c.text(0.5, 0.5, "No monitor_data.csv\n(run with monitor export enabled)",
                  ha="center", va="center", transform=ax_c.transAxes, fontsize=9,
                  color="gray")
        ax_c.set_title("(b) Reward Components — No Data")

    # ── (c) SAC loss & alpha ──────────────────────────────────────────
    ax_l = fig.add_subplot(gs[1, 0])
    if critic_losses:
        c_ep = np.arange(len(critic_losses))
        mean_cl, _ = _rolling(critic_losses, min(_WINDOW, len(critic_losses)))
        ax_l.plot(c_ep, mean_cl, color=_C_FREQ, lw=1.4, label="Critic loss")
    if alphas:
        ax_a = ax_l.twinx()
        a_ep = np.arange(len(alphas))
        mean_al, _ = _rolling(alphas, min(_WINDOW, len(alphas)))
        ax_a.plot(a_ep, mean_al, color=_C_INERTIA, lw=1.2, ls="--", label="Alpha (entropy)")
        ax_a.set_ylabel("Alpha", color=_C_INERTIA, fontsize=8)
        ax_a.tick_params(axis="y", labelcolor=_C_INERTIA, labelsize=7)
        ax_a.legend(fontsize=7, loc="upper right")
    ax_l.set_xlabel("Episode")
    ax_l.set_ylabel("Critic loss", fontsize=8)
    ax_l.set_title("(c) SAC Loss & Entropy")
    ax_l.legend(fontsize=7, loc="upper left")

    # ── (d) Action statistics ─────────────────────────────────────────
    ax_act = fig.add_subplot(gs[1, 1])
    if has_action_stats:
        act_ep = np.arange(len(mon["action_std_agent_0"]))
        # Mean std across agents
        std_keys = [k for k in mon if k.startswith("action_std_agent_")]
        if std_keys:
            stds = np.mean([mon[k] for k in std_keys], axis=0)
            mean_std, _ = _rolling(stds.tolist(), min(_WINDOW, len(stds)))
            ax_act.plot(act_ep, mean_std, color=_C_TOTAL, lw=1.4, label="Action std (mean agents)")
        if "saturation_ratio" in mon:
            ax_sat = ax_act.twinx()
            sat = mon["saturation_ratio"]
            mean_sat, _ = _rolling(sat, min(_WINDOW, len(sat)))
            ax_sat.plot(act_ep, mean_sat, color=_C_DROOP, lw=1.0, ls=":", label="Saturation ratio")
            ax_sat.set_ylabel("Saturation ratio", color=_C_DROOP, fontsize=8)
            ax_sat.tick_params(axis="y", labelcolor=_C_DROOP, labelsize=7)
            ax_sat.set_ylim(0, 1)
            ax_sat.legend(fontsize=7, loc="upper right")
        ax_act.set_xlabel("Episode")
        ax_act.set_ylabel("Action std")
        ax_act.set_title("(d) Action Statistics")
        ax_act.legend(fontsize=7, loc="upper left")
    else:
        ax_act.text(0.5, 0.5, "No monitor_data.csv",
                    ha="center", va="center", transform=ax_act.transAxes,
                    fontsize=9, color="gray")
        ax_act.set_title("(d) Action Statistics — No Data")

    # ── (e) Physics summary (optional 3rd row, spans both columns) ────
    if has_physics:
        ax_ph = fig.add_subplot(gs[2, :])
        phys_ep = np.arange(len(physics))
        max_f = [p["max_freq_dev_hz"] for p in physics]
        mean_f = [p["mean_freq_dev_hz"] for p in physics]
        settled = [p["settled"] for p in physics]

        mean_mf, _ = _rolling(max_f, min(_WINDOW, len(max_f)))
        mean_af, _ = _rolling(mean_f, min(_WINDOW, len(mean_f)))

        ax_ph.plot(phys_ep, mean_mf, color=_C_FREQ, lw=1.4, label=r"Max $\Delta f$ (Hz)")
        ax_ph.plot(phys_ep, mean_af, color=_C_INERTIA, lw=1.0, ls="--",
                   label=r"Mean $\Delta f$ (Hz)")
        ax_ph.axhline(0.1, color="gray", lw=0.8, ls=":", label="0.1 Hz settled threshold")

        # Mark unsettled episodes
        unsettled_ep = [i for i, s in enumerate(settled) if not s]
        if unsettled_ep:
            unsettled_f = [max_f[i] for i in unsettled_ep]
            ax_ph.scatter(unsettled_ep, unsettled_f, s=4, color=_C_UNSETTLED,
                          alpha=0.4, label="Not settled", zorder=3)

        # Settled rate annotation
        settled_rate = sum(settled) / max(len(settled), 1)
        ax_ph.set_title(f"(e) Frequency Deviation  —  settled rate: {settled_rate:.1%}")
        ax_ph.set_xlabel("Episode")
        ax_ph.set_ylabel(r"$\Delta f$ (Hz)")
        ax_ph.legend(fontsize=7, ncol=4)

    # Title
    run_name = Path(log_path).parent.parent.name  # e.g. "sim_kundur"
    fig.suptitle(f"Training Diagnostics — {run_name}  ({n_ep} episodes)", fontsize=11)

    # Save
    if save_path is None:
        save_path = str(Path(log_path).parent.parent / "training_summary.png")
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    print(f"[training_viz] Saved: {save_path}")
    return save_path


# ── CLI entry point ──────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="Generate training diagnostic plot")
    p.add_argument("log_path", help="Path to training_log.json")
    p.add_argument("-o", "--output", default=None, help="Output PNG path")
    p.add_argument("--show", action="store_true", help="Display plot interactively")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    out = plot_training_summary(args.log_path, save_path=args.output, show=args.show)
    print(f"Done: {out}")
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_fixes.py::test_training_viz_produces_png_from_log tests/test_fixes.py::test_training_viz_works_without_physics_summary -v
```

Expected: both PASS.

- [ ] **Step 3.5: Smoke-test against real sim_kundur data**

```bash
python -m utils.training_viz results/sim_kundur/logs/training_log.json -o results/sim_kundur/training_summary.png
```

Expected output:
```
[training_viz] Saved: results/sim_kundur/training_summary.png
Done: results/sim_kundur/training_summary.png
```

Open the PNG. Verify: 2 rows × 2 subplots visible, reward curve shows scatter + moving avg, loss subplot shows critic loss. Panels (b) and (d) show "No Data" (expected — monitor_data.csv not yet produced for old run).

- [ ] **Step 3.6: Run full test suite**

```bash
python -m pytest tests/test_fixes.py -v --tb=short 2>&1 | tail -25
```

Expected: all previously passing tests still pass + new T6/T7 tests pass.

- [ ] **Step 3.7: Commit**

```bash
git add utils/training_viz.py tests/test_fixes.py
git commit -m "feat(viz): add training_viz.py — post-training 2x2 diagnostic plot"
```

---

## Task 4: Verify end-to-end with existing sim_kundur log

**Files:**
- Read-only: `results/sim_kundur/logs/training_log.json`

- [ ] **Step 4.1: Verify old log is backward-compatible**

```bash
python -c "
import json
with open('results/sim_kundur/logs/training_log.json') as f:
    log = json.load(f)
print('Keys:', list(log.keys()))
print('Episodes:', len(log['episode_rewards']))
print('Has physics_summary:', 'physics_summary' in log)
"
```

Expected: `Has physics_summary: False` — old logs don't have it, and `plot_training_summary` must handle this gracefully (test T7 already covers this).

- [ ] **Step 4.2: Generate diagnostic for existing sim_kundur run**

```bash
python -m utils.training_viz results/sim_kundur/logs/training_log.json
```

Expected: `results/sim_kundur/training_summary.png` created. Review it — reward should show convergence trend over 1000 episodes, loss should be stable or decreasing.

- [ ] **Step 4.3: Commit PNG to results (optional, for reference)**

```bash
git add results/sim_kundur/training_summary.png
git commit -m "docs(results): add sim_kundur training diagnostic summary"
```

---

## Won't Do (this phase)

These are documented here so future agents don't re-implement them:

| Item | Reason | Status |
|------|--------|--------|
| Online/real-time plot updates | Simulink IPC step takes 50-200ms; matplotlib refresh in main thread would add 100ms+ overhead; monitor terminal output sufficient during training | Never for training loop |
| TensorBoard integration | `monitor.export_tensorboard()` already exists at `utils/monitor.py:793` — call it manually when needed | Available on demand |
| W&B / MLflow | Single-person project, no cloud needed | Won't do |
| Full waveform storage (omega[t], P_es[t] per step) | 800K floats/1000ep, no consumption tooling, zero-value until evaluation phase | Evaluation phase only |
| RoCoF time series in training | Derivable from freq time series; no new information vs max_freq_dev | Evaluation phase only |
| Voltage deviation | Requires Simulink model changes (new output ports + bridge update) — separate task | Simulink model task |
| Cross-environment adapter layer | JSON log format already identical across ANDES/Simulink; no adapter needed | Not needed |
| Multi-run comparison (`compare_paths`) | `plot_training_summary()` signature already reserves this parameter; implement after 3+ runs with different hyperparameters | Trigger: manual 3+ runs |
| Config dict-ification for Optuna | Not needed until manual tuning reveals sensitive parameters | Trigger: 3+ manual runs |

---

## Later (deferred)

### L1: Multi-run comparison in training_viz
**Trigger:** You've run ≥3 training experiments with different hyperparameters and want to compare reward curves.
**Why not now:** Only one completed Simulink run (sim_kundur). Nothing to compare.
**Implementation:** `plot_training_summary(log_path, compare_paths=[path2, path3])` — overlay reward moving-avg curves from each run. Signature already reserved.

### L2: Physics summary for ANDES training loops
**Trigger:** You resume ANDES training or run new ANDES experiments.
**Why not now:** ANDES model files deleted 2026-04-06. No active ANDES training.
**Implementation:** Repeat Task 1 changes in `scenarios/kundur/train_andes.py` and `scenarios/new_england/train_andes.py`. JSON log structure identical — no format changes needed.

### L3: Evaluation-phase full waveform recording
**Trigger:** Training converges and you want to analyze time-domain response quality.
**Why not now:** `evaluate()` function already returns enough info for reward; full waveform analysis belongs in `plotting/evaluate.py`, not training infrastructure.
**Implementation:** In `evaluate()`, collect `omega_trajectory` and `P_es_trajectory` lists, return them in eval result. Use existing `plotting/plot_andes_eval.py` patterns.

### L4: Precise settling time calculation
**Trigger:** You want to report settling time as a performance metric (e.g., for paper).
**Why not now:** Requires ±2% band algorithm + full frequency time series. Overkill during training.
**Implementation:** Post-processing function in `plotting/evaluate.py`: given `freq_hz[t]`, find first t where `|Δf| < threshold` for all remaining steps.
