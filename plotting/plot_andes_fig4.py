"""
复现论文 Fig 4: Training performance — ANDES Kundur 版.
数据源: results/andes_models_fixed/training_log.json + train.log
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json, re
import numpy as np
from plotting.paper_style import plot_training_curves, save_fig

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_JSON = os.path.join(BASE, 'results', 'andes_models_fixed', 'training_log.json')
TRAIN_LOG = os.path.join(BASE, 'results', 'andes_kundur_train.log')
SAVE_DIR = os.path.join(BASE, 'results', 'figures_paper_style')


def parse_component_ratios(log_path):
    """从训练日志解析每10 episode的 r_f/r_h/r_d 占比."""
    eps, rf, rh, rd = [], [], [], []
    with open(log_path) as f:
        for line in f:
            m = re.search(
                r'Ep (\d+) \| Reward: [-\d.]+ \(r_f: ([\d.]+)%, r_h: ([\d.]+)%, r_d: ([\d.]+)%',
                line)
            if m:
                eps.append(int(m.group(1)))
                rf.append(float(m.group(2)) / 100.0)
                rh.append(float(m.group(3)) / 100.0)
                rd.append(float(m.group(4)) / 100.0)
    return np.array(eps), np.array(rf), np.array(rh), np.array(rd)


def main():
    with open(LOG_JSON) as f:
        data = json.load(f)

    total = np.array(data['total_rewards'])
    agents = [np.array(data['episode_rewards'][str(i)]) for i in range(4)]

    # 解析分项奖励比例 → 插值到所有 episode
    mon_eps, rf, rh, rd = parse_component_ratios(TRAIN_LOG)
    all_eps = np.arange(len(total))
    rf_all = np.interp(all_eps, mon_eps, rf)
    rh_all = np.interp(all_eps, mon_eps, rh)
    rd_all = np.interp(all_eps, mon_eps, rd)

    fig = plot_training_curves(
        total, agents,
        freq_rewards=total * rf_all,
        inertia_rewards=total * rh_all,
        droop_rewards=total * rd_all,
        n_agents=4, window=50,
    )
    save_fig(fig, SAVE_DIR, 'fig4_andes_kundur.png')


if __name__ == '__main__':
    main()
