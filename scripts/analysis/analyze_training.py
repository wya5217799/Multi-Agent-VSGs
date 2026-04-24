"""
训练结果分析脚本

用法:
    python scripts/analysis/analyze_training.py sim_kundur
    python scripts/analysis/analyze_training.py sim_ne39
    python scripts/analysis/analyze_training.py sim_kundur --log-file results/sim_kundur/logs/training_log.json

输出: results/<scenario>/logs/analysis.png
"""
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# ── 数据加载 ──────────────────────────────────────────────────────────────────

def load_json_log(path: str) -> dict | None:
    """加载 training_log.json，返回 dict 或 None。"""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        # 旧格式（每集一个 dict）
        return {
            'episode_rewards': [e.get('episode_reward', e.get('reward')) for e in data],
            'alphas': [e.get('alpha') for e in data],
            'critic_losses': [e.get('critic_loss') for e in data],
            'physics_summary': [e.get('physics_summary', {}) for e in data],
        }
    return data  # 新格式（dict of lists）


def load_monitor_csv(path: str) -> dict | None:
    """加载 monitor_data.csv，返回 dict of lists 或 None。"""
    if not os.path.exists(path):
        return None
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: _try_float(v) for k, v in row.items()})
    if not rows:
        return None
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}


def parse_console_log(path: str) -> dict:
    """从 console log 解析实时 episode 数据。"""
    result = {'episodes': [], 'rewards': [], 'avg10': [], 'alphas': [], 'times': []}
    if not os.path.exists(path):
        return result
    ep_pat = re.compile(
        r'\[Ep\s+(\d+)/\d+\]\s+R=([-\d.]+)\s+\|\s+Avg10=([-\d.]+)\s+\|\s+Alpha=([\d.]+)'
    )
    time_pat = re.compile(r'Time=([\d.]+)s')
    with open(path, errors='replace') as f:
        for line in f:
            m = ep_pat.search(line)
            if m:
                result['episodes'].append(int(m.group(1)))
                result['rewards'].append(float(m.group(2)))
                result['avg10'].append(float(m.group(3)))
                result['alphas'].append(float(m.group(4)))
                tm = time_pat.search(line)
                result['times'].append(float(tm.group(1)) if tm else None)
    return result


def find_latest_console_log(log_dir: str) -> str | None:
    """找最新的 train_simulink_run*.log 文件。"""
    logs = sorted(
        Path(log_dir).glob('train_simulink_run*.log'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # 过滤掉 .err 文件
    logs = [p for p in logs if not str(p).endswith('.err')]
    return str(logs[0]) if logs else None


def _try_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── 滚动均值 ──────────────────────────────────────────────────────────────────

def rolling_mean(data, window=10):
    """计算滚动平均，忽略 None。"""
    out = []
    for i in range(len(data)):
        chunk = [x for x in data[max(0, i - window + 1):i + 1] if x is not None]
        out.append(np.mean(chunk) if chunk else None)
    return out


# ── 崩溃检测 ──────────────────────────────────────────────────────────────────

def detect_collapse(rewards, alphas, sustained=20, reward_threshold=0.8):
    """
    检测训练崩溃点：连续 sustained 集奖励明显低于历史最佳 + alpha 突变。

    条件：从某集开始，后续 sustained 集的平均奖励 < 历史最佳 * reward_threshold，
    且 alpha 在该集发生突变（跳升 > 0.3）。
    返回崩溃的 episode index（1-based）或 None。
    """
    if not rewards or len(rewards) < sustained * 2:
        return None
    best_so_far = rewards[0]
    for i in range(1, len(rewards) - sustained):
        best_so_far = max(best_so_far, rewards[i])
        # alpha 突变检测
        alpha_jumped = (
            alphas and i < len(alphas) - 1
            and alphas[i] - alphas[i - 1] > 0.3
        )
        if not alpha_jumped:
            continue
        # 确认后续 sustained 集持续低迷
        post_avg = sum(rewards[i:i + sustained]) / sustained
        # 对于负奖励：best_so_far 是较大值（如 -2000），threshold 乘出来更负
        # post_avg < best_so_far * reward_threshold 表示明显变差
        if best_so_far < 0:
            if post_avg < best_so_far / reward_threshold:
                return i + 1  # 1-based
        else:
            if post_avg < best_so_far * reward_threshold:
                return i + 1
    return None


# ── 绘图 ──────────────────────────────────────────────────────────────────────

def plot_analysis(scenario: str, json_data: dict | None, csv_data: dict | None,
                  console_data: dict, output_path: str):
    """生成 3×2 分析图。"""
    # 合并数据源：优先 JSON，然后 CSV，最后 console log
    rewards = None
    alphas = None
    critics = None
    freq_devs = None
    ep_axis = None

    json_eps = len(json_data.get('episode_rewards', [])) if json_data else 0
    console_max_ep = max(console_data['episodes']) if console_data['episodes'] else 0

    # 若 console log 记录了比 JSON 更多的集数（即 JSON 是旧的），优先用 console
    use_console_primary = console_max_ep > json_eps + 10

    if json_data and json_eps > 0 and not use_console_primary:
        rewards = json_data['episode_rewards']
        alphas = json_data.get('alphas', [])
        critics = json_data.get('critic_losses', [])
        ep_axis = list(range(1, len(rewards) + 1))
        ps = json_data.get('physics_summary', [])
        if ps and isinstance(ps[0], dict):
            freq_devs = [p.get('max_freq_dev_hz') for p in ps]

    elif console_data['episodes']:
        rewards = console_data['rewards']
        alphas = console_data['alphas']
        ep_axis = console_data['episodes']

    if rewards is None:
        print(f"[analyze] 无数据可用: {scenario}")
        return

    # 探索崩溃点
    collapse_ep = detect_collapse(rewards, alphas or [])

    # CSV 里可能有 freq_dev
    if freq_devs is None and csv_data and 'max_freq_deviation_hz' in csv_data:
        freq_devs = csv_data['max_freq_deviation_hz']

    # ── 布局 ──
    n_panels = 5 if (critics and any(x is not None for x in critics)) else 4
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flatten()
    fig.suptitle(f'Training Analysis — {scenario}  ({len(rewards)} episodes)', fontsize=14)

    colors = {'reward': '#2196F3', 'avg': '#FF5722', 'alpha': '#9C27B0',
              'critic': '#4CAF50', 'freq': '#FF9800', 'collapse': '#F44336'}

    def draw_collapse(ax):
        if collapse_ep:
            ax.axvline(collapse_ep, color=colors['collapse'], linestyle='--',
                       alpha=0.7, linewidth=1.5, label=f'Collapse @ep{collapse_ep}')

    def ep_x(data):
        """生成与 data 等长的 episode x 轴。"""
        if ep_axis and len(ep_axis) == len(data):
            return ep_axis
        return list(range(1, len(data) + 1))

    # ── Panel 0: 奖励曲线 ──
    ax = axes[0]
    ax.plot(ep_x(rewards), rewards, color=colors['reward'], alpha=0.4, linewidth=0.8, label='Episode reward')
    rm = rolling_mean(rewards, 10)
    ax.plot(ep_x(rm), rm, color=colors['avg'], linewidth=2, label='Avg-10')
    draw_collapse(ax)
    ax.set_xlabel('Episode')
    ax.set_ylabel('Reward')
    ax.set_title('Episode Reward')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    best_r = max(rewards)
    best_i = rewards.index(best_r)
    ax.annotate(f'Best: {best_r:.0f}', xy=(ep_x(rewards)[best_i], best_r),
                xytext=(10, 10), textcoords='offset points',
                fontsize=8, color=colors['avg'],
                arrowprops=dict(arrowstyle='->', color=colors['avg']))

    # ── Panel 1: Alpha ──
    ax = axes[1]
    if alphas and len(alphas) > 0:
        ax.plot(ep_x(alphas), alphas, color=colors['alpha'], linewidth=1.2, label='Alpha')
        draw_collapse(ax)
        ax.set_xlabel('Episode')
        ax.set_ylabel('Alpha (entropy coeff)')
        ax.set_title('SAC Alpha (Entropy Coefficient)')
        ax.axhline(0.005, color='gray', linestyle=':', linewidth=1, label='alpha_min=0.005')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Alpha data not available', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color='gray')
        ax.set_title('SAC Alpha')

    # ── Panel 2: Critic Loss ──
    ax = axes[2]
    if critics and any(x is not None for x in critics):
        valid_critics = [(ep_x(critics)[i], v) for i, v in enumerate(critics) if v is not None]
        if valid_critics:
            xs, ys = zip(*valid_critics)
            ax.plot(xs, ys, color=colors['critic'], linewidth=1, alpha=0.7, label='Critic loss')
            rm_c = rolling_mean(critics, 10)
            ax.plot(ep_x(rm_c), rm_c, color='#1B5E20', linewidth=2, label='Avg-10')
            draw_collapse(ax)
        ax.set_xlabel('Episode')
        ax.set_ylabel('Critic Loss')
        ax.set_title('Critic Loss')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Critic loss not available', ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color='gray')
        ax.set_title('Critic Loss')

    # ── Panel 3: Frequency deviation ──
    ax = axes[3]
    if freq_devs and any(x is not None for x in freq_devs):
        valid_fd = [(ep_x(freq_devs)[i], v) for i, v in enumerate(freq_devs) if v is not None]
        if valid_fd:
            xs, ys = zip(*valid_fd)
            ax.plot(xs, ys, color=colors['freq'], linewidth=1, alpha=0.7, label='Max freq dev (Hz)')
            ax.axhline(2.0, color='red', linestyle='--', linewidth=1, label='±2Hz threshold')
            draw_collapse(ax)
        ax.set_xlabel('Episode')
        ax.set_ylabel('Hz')
        ax.set_title('Max Frequency Deviation')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Freq deviation not available\n(run with physics_summary enabled)',
                ha='center', va='center', transform=ax.transAxes, fontsize=10, color='gray')
        ax.set_title('Frequency Deviation')

    # ── Panel 4: 奖励分布（每100集） ──
    ax = axes[4]
    chunk = 100
    n_chunks = len(rewards) // chunk
    if n_chunks > 0:
        positions = [(i + 0.5) * chunk for i in range(n_chunks)]
        data_chunks = [rewards[i * chunk:(i + 1) * chunk] for i in range(n_chunks)]
        bp = ax.boxplot(data_chunks, positions=positions, widths=chunk * 0.6,
                        patch_artist=True, showfliers=False,
                        boxprops=dict(facecolor='#E3F2FD', alpha=0.8),
                        medianprops=dict(color=colors['avg'], linewidth=2))
        draw_collapse(ax)
        ax.set_xlabel('Episode')
        ax.set_ylabel('Reward')
        ax.set_title('Reward Distribution (per 100 ep)')
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, f'Too few episodes ({len(rewards)}) for distribution',
                ha='center', va='center', transform=ax.transAxes, fontsize=10, color='gray')
        ax.set_title('Reward Distribution')

    # ── Panel 5: 摘要文字 ──
    ax = axes[5]
    ax.axis('off')
    lines = [
        f'Scenario: {scenario}',
        f'Total episodes: {len(rewards)}',
        f'Best reward: {max(rewards):.0f} @ ep{rewards.index(max(rewards)) + 1}',
        f'Final avg-10: {np.mean(rewards[-10:]):.0f}',
    ]
    if alphas and len(alphas) > 0:
        lines.append(f'Final alpha: {alphas[-1]:.4f}')
    if critics and any(x is not None for x in critics):
        valid = [x for x in critics if x is not None]
        lines.append(f'Final critic loss: {valid[-1]:.2f}')
    if collapse_ep:
        lines.append(f'')
        lines.append(f'[!] Collapse detected @ ep{collapse_ep}')
        lines.append(f'  Reward after collapse: {np.mean(rewards[collapse_ep:collapse_ep+10]):.0f}')
    if console_data['episodes']:
        last_ep = console_data['episodes'][-1]
        lines.append(f'')
        lines.append(f'Console log (live): ep{last_ep}')
        if console_data['times'] and console_data['times'][-1]:
            elapsed = console_data['times'][-1]
            lines.append(f'  Elapsed: {elapsed/3600:.1f}h')

    ax.text(0.05, 0.95, '\n'.join(lines), transform=ax.transAxes,
            fontsize=11, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#F5F5F5', alpha=0.8))

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"[analyze] Saved: {output_path}")
    plt.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Analyze training results')
    parser.add_argument('scenario', choices=['sim_kundur', 'sim_ne39'],
                        help='Which scenario to analyze')
    parser.add_argument('--log-file', default=None,
                        help='Path to training_log.json (auto-detected if omitted)')
    parser.add_argument('--no-console', action='store_true',
                        help='Skip console log parsing')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, args.scenario)
    log_dir = os.path.join(results_dir, 'logs')

    json_path = args.log_file or os.path.join(log_dir, 'training_log.json')
    csv_path = os.path.join(log_dir, 'monitor_data.csv')
    output_path = os.path.join(log_dir, 'analysis.png')

    json_data = load_json_log(json_path)
    csv_data = load_monitor_csv(csv_path)

    console_data = {'episodes': [], 'rewards': [], 'avg10': [], 'alphas': [], 'times': []}
    if not args.no_console:
        console_log = find_latest_console_log(log_dir)
        if console_log:
            print(f"[analyze] Parsing console log: {os.path.basename(console_log)}")
            console_data = parse_console_log(console_log)

    if json_data:
        n = len(json_data.get('episode_rewards', []))
        print(f"[analyze] JSON log: {n} episodes")
    if csv_data:
        print(f"[analyze] Monitor CSV: {len(list(csv_data.values())[0])} rows")
    if console_data['episodes']:
        print(f"[analyze] Console log: {len(console_data['episodes'])} episodes "
              f"(latest: ep{console_data['episodes'][-1]})")

    plot_analysis(args.scenario, json_data, csv_data, console_data, output_path)

    # 打印关键摘要 — 使用与 plot_analysis 相同的数据源选择逻辑
    json_eps = len(json_data.get('episode_rewards', [])) if json_data else 0
    console_max_ep = max(console_data['episodes']) if console_data['episodes'] else 0
    use_console = console_max_ep > json_eps + 10

    if use_console and console_data['rewards']:
        rewards = console_data['rewards']
        alphas = console_data['alphas']
        critics = []
        ep_label = f"ep{console_data['episodes'][0]}-ep{console_data['episodes'][-1]} (console, every-10)"
    else:
        data = json_data or {}
        rewards = data.get('episode_rewards', console_data['rewards'])
        alphas = data.get('alphas', console_data['alphas'])
        critics = data.get('critic_losses', [])
        ep_label = f"{len(rewards)} episodes (JSON log)"

    if rewards:
        collapse = detect_collapse(rewards, alphas)
        print(f"\n{'='*50}")
        print(f"SUMMARY: {args.scenario}")
        print(f"{'='*50}")
        print(f"Source     : {ep_label}")
        print(f"Data pts   : {len(rewards)}")
        print(f"Best reward: {max(rewards):.0f} @ ep{rewards.index(max(rewards))+1}")
        print(f"Avg last 10: {np.mean(rewards[-10:]):.0f}")
        if alphas:
            print(f"Alpha final: {alphas[-1]:.4f}")
        if critics:
            valid = [x for x in critics if x is not None]
            if valid:
                print(f"Critic final: {valid[-1]:.2f}")
        if collapse:
            print(f"\n[!] COLLAPSE DETECTED @ ep{collapse}")
            pre  = np.mean(rewards[max(0, collapse-20):collapse])
            post = np.mean(rewards[collapse:collapse+20])
            print(f"   Reward before: {pre:.0f}  ->  after: {post:.0f}")


if __name__ == '__main__':
    main()
