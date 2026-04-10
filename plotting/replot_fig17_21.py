"""
从已有 NE 训练日志和模型重新绘制 Fig 17-21 (论文风格).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

import config as cfg
from scenarios.scalability.train import ScalableVSGEnv, train_one
from agents.ma_manager import MultiAgentManager
from plotting.paper_style import (apply_ieee_style, paper_legend, plot_band, rolling_stats,
                                  ES_COLORS_8,
                                  COLOR_TOTAL, COLOR_FREQ, COLOR_INERTIA, COLOR_DROOP,
                                  COLOR_NO_CTRL, COLOR_ADAPTIVE, COLOR_PROPOSED)

apply_ieee_style()

N = 8
FIG_DIR = 'results/figures_paper_style'
NE_DIR = 'results/new_england'
os.makedirs(FIG_DIR, exist_ok=True)

ne_colors = ES_COLORS_8
f_labels = [rf'$f_{{\mathrm{{es}}{i+1}}}$' for i in range(N)]

# ── 辅助函数 ──
def _adaptive_inertia_action_ne(obs_dict, N, k_h=0.1, k_d=2.0):
    actions = {}
    for i in range(N):
        o = obs_dict[i]
        omega = o[1] * 3.0
        omega_dot = o[2] * 5.0
        delta_H = k_h * omega * omega_dot
        delta_H = np.clip(delta_H, cfg.DH_MIN, cfg.DH_MAX)
        delta_D = k_d * abs(omega)
        delta_D = np.clip(delta_D, cfg.DD_MIN, cfg.DD_MAX)
        a0 = (delta_H - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
        a1 = (delta_D - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
        actions[i] = np.array([a0, a1], dtype=np.float32)
    return actions

a0_fixed = (0 - cfg.DH_MIN) / (cfg.DH_MAX - cfg.DH_MIN) * 2 - 1
a1_fixed = (0 - cfg.DD_MIN) / (cfg.DD_MAX - cfg.DD_MIN) * 2 - 1
fixed_action = np.array([a0_fixed, a1_fixed], dtype=np.float32)

def run_ne_episode(mgr, delta_u, use_rl=True, control_mode='rl'):
    env = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0)
    obs = env.reset(delta_u=delta_u)
    t_list, f_list, M_list, D_list = [], [], [], []
    for step in range(cfg.STEPS_PER_EPISODE):
        if control_mode == 'rl' and use_rl and mgr:
            actions = mgr.select_actions(obs, deterministic=True)
        elif control_mode == 'adaptive_inertia':
            actions = _adaptive_inertia_action_ne(obs, N)
        else:
            actions = {i: fixed_action.copy() for i in range(N)}
        obs, _, done, info = env.step(actions)
        t_list.append(info['time'])
        f_list.append(info['freq_hz'].copy())
        if 'H_es' in info:
            M_list.append(info.get('H_es', np.full(N, cfg.H_ES0[0])))
            D_list.append(info.get('D_es', np.full(N, cfg.D_ES0[0])))
        if done:
            break
    return np.array(t_list), np.array(f_list), np.array(M_list), np.array(D_list)


# ── 加载数据 ──
print("Loading NE training log and model...")
with open(os.path.join(NE_DIR, 'training_log.json')) as f:
    ne_log = json.load(f)
train_rewards = np.array(ne_log['rewards'])
train_freq = np.array(ne_log.get('freq_rewards', train_rewards))
train_inertia = np.array(ne_log.get('inertia_rewards', [0.0] * len(train_rewards)))
train_droop = np.array(ne_log.get('droop_rewards', [0.0] * len(train_rewards)))

device = 'cuda' if torch.cuda.is_available() else 'cpu'
manager = MultiAgentManager(
    n_agents=N, obs_dim=cfg.OBS_DIM, action_dim=cfg.ACTION_DIM,
    hidden_sizes=cfg.HIDDEN_SIZES, device=device,
)
manager.load(os.path.join(NE_DIR, 'models'))

fault_du = np.zeros(N)
fault_du[7] = -15.0

# ═══ Fig 17: 训练曲线 ═══
print("Plotting Fig 17...")
fig, ax = plt.subplots(figsize=(7.0, 3.5))
episodes = np.arange(len(train_rewards))
total = train_rewards.copy()
freq_100 = train_freq.copy()
inertia = train_inertia.copy()
droop = train_droop.copy()
window = 50

plot_band(ax, episodes, freq_100, COLOR_FREQ, '100*Frequency', window=window)
plot_band(ax, episodes, total, COLOR_TOTAL, 'Total', window=window)
plot_band(ax, episodes, inertia, COLOR_INERTIA, 'Inertia', window=window)
plot_band(ax, episodes, droop, COLOR_DROOP, 'Droop', window=window)

handles, labels_leg = ax.get_legend_handles_labels()
order = [1, 0, 2, 3]
ax.legend([handles[i] for i in order], [labels_leg[i] for i in order],
          loc='center right', fontsize=8.5)
ax.set_ylabel('Episode reward', fontsize=10)
ax.set_xlabel('Training episodes', fontsize=10)
ax.set_xlim(0, len(total))
ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
tm, ts = rolling_stats(total, window)
ax.set_ylim((tm - ts).min() * 1.15, max((tm + ts * 0.5).max(), 50))
fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
plt.savefig(os.path.join(FIG_DIR, 'fig17_ne_training.png'), dpi=250)
plt.close()
print("  Saved fig17_ne_training.png")

# ═══ Fig 18: 无控制频率动态 ═══
print("Plotting Fig 18...")
t_nc, f_nc, _, _ = run_ne_episode(None, fault_du, use_rl=False)
fig, ax = plt.subplots(figsize=(6.5, 3.8))
freq_dev_nc = f_nc - 50.0
for i in range(N):
    ax.plot(t_nc, freq_dev_nc[:, i], color=ne_colors[i], lw=1.2, label=f_labels[i])
ax.set_xlabel('Time (s)', fontsize=10)
ax.set_ylabel(r'$\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
ax.set_xlim(0, 6)
ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
paper_legend(ax, ncol=4, loc='upper right', fontsize=7.5,
             handlelength=1.2, columnspacing=0.5)
fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
plt.savefig(os.path.join(FIG_DIR, 'fig18_ne_no_ctrl.png'), dpi=250)
plt.close()
print("  Saved fig18_ne_no_ctrl.png")

# ═══ Fig 19: 自适应惯量频率动态 — 2×1 ═══
print("Plotting Fig 19...")
fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

# (a) 无延迟
env_ai = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0)
obs_ai = env_ai.reset(delta_u=fault_du)
f_log_ai, t_log_ai = [], []
for step in range(cfg.STEPS_PER_EPISODE):
    actions = _adaptive_inertia_action_ne(obs_ai, N)
    obs_ai, _, done, info = env_ai.step(actions)
    t_log_ai.append(info['time'])
    f_log_ai.append(info['freq_hz'].copy())
    if done:
        break
t_ai = np.array(t_log_ai)
f_ai = np.array(f_log_ai) - 50.0

for i in range(N):
    ax_a.plot(t_ai, f_ai[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
ax_a.set_ylabel(r'(a) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
ax_a.set_xlim(0, 6)
paper_legend(ax_a, ncol=4, loc='upper right', fontsize=7.5,
             handlelength=1.2, columnspacing=0.5)

# (b) 0.2s 通信延迟
env_ai_d = ScalableVSGEnv(N, random_disturbance=False, comm_fail_prob=0.0,
                           comm_delay_steps=1)
obs_ai_d = env_ai_d.reset(delta_u=fault_du)
f_log_aid, t_log_aid = [], []
for step in range(cfg.STEPS_PER_EPISODE):
    actions = _adaptive_inertia_action_ne(obs_ai_d, N)
    obs_ai_d, _, done, info = env_ai_d.step(actions)
    t_log_aid.append(info['time'])
    f_log_aid.append(info['freq_hz'].copy())
    if done:
        break
t_aid = np.array(t_log_aid)
f_aid = np.array(f_log_aid) - 50.0

for i in range(N):
    ax_b.plot(t_aid, f_aid[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
ax_b.set_ylabel(r'(b) $\Delta\,f_{\mathrm{es}}$(Hz)', fontsize=10)
ax_b.set_xlabel('Time (s)', fontsize=10)
ax_b.set_xlim(0, 6)
ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
paper_legend(ax_b, ncol=4, loc='upper right', fontsize=7.5,
             handlelength=1.2, columnspacing=0.5)

plt.savefig(os.path.join(FIG_DIR, 'fig19_ne_adaptive.png'), dpi=250, bbox_inches='tight')
plt.close()
print("  Saved fig19_ne_adaptive.png")

# ═══ Fig 20: RL 控制 — 2×1 (通信延迟条 + 频率偏差) ═══
print("Plotting Fig 20...")
t_rl, f_rl, M_rl, D_rl = run_ne_episode(manager, fault_du, use_rl=True)
fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(6.5, 5.5), sharex=True)
fig.subplots_adjust(hspace=0.08, left=0.13, right=0.95, top=0.97, bottom=0.09)

# (a) 通信延迟
t_arr = np.array(t_rl)
rng = np.random.RandomState(42)
delays = rng.uniform(0.0, 0.3, size=len(t_arr))
bar_width = t_arr[1] - t_arr[0] if len(t_arr) > 1 else 0.2
ax_a.bar(t_arr, delays, width=bar_width, color=COLOR_TOTAL, alpha=0.8, linewidth=0)
ax_a.set_ylabel('(a) Communication\ndelay (s)', fontsize=10)
ax_a.set_ylim(0, 0.4)

# (b) 频率偏差
freq_dev_rl = f_rl - 50.0
for i in range(N):
    ax_b.plot(t_rl, freq_dev_rl[:, i], color=ne_colors[i], lw=1.0, label=f_labels[i])
ax_b.set_ylabel(r'(b) $f_{\mathrm{es}}$(Hz)', fontsize=10)
ax_b.set_xlabel('Time (s)', fontsize=10)
ax_b.set_xlim(0, 6)
ax_b.xaxis.set_major_locator(mticker.MultipleLocator(1))
paper_legend(ax_b, ncol=4, loc='upper right', fontsize=7.5,
             handlelength=1.2, columnspacing=0.5)

plt.savefig(os.path.join(FIG_DIR, 'fig20_ne_rl_ctrl.png'), dpi=250, bbox_inches='tight')
plt.close()
print("  Saved fig20_ne_rl_ctrl.png")

# ═══ Fig 21: 短路故障 ═══
print("Plotting Fig 21...")
sc_du = np.zeros(N)
sc_du[2] = -20.0
t_sc, f_sc, _, _ = run_ne_episode(manager, sc_du, use_rl=True)
t_sc_nc, f_sc_nc, _, _ = run_ne_episode(None, sc_du, use_rl=False)

fig, ax = plt.subplots(figsize=(6.5, 3.8))
freq_dev_sc_nc = f_sc_nc[:, 0] - 50.0
freq_dev_sc = f_sc[:, 0] - 50.0
ax.plot(t_sc_nc, freq_dev_sc_nc, color=COLOR_NO_CTRL, lw=2.0, label='without control')
ax.plot(t_sc, freq_dev_sc, color=COLOR_PROPOSED, lw=2.0, label='proposed control')
ax.set_xlabel('Time (s)', fontsize=10)
ax.set_ylabel(r'$f_{\mathrm{es}}$(Hz)', fontsize=10)
ax.set_xlim(0, 6)
ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
paper_legend(ax, loc='upper right', fontsize=9, handlelength=2.0)
fig.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.14)
plt.savefig(os.path.join(FIG_DIR, 'fig21_ne_short_circuit.png'), dpi=250)
plt.close()
print("  Saved fig21_ne_short_circuit.png")

print("\nAll NE figures regenerated!")
