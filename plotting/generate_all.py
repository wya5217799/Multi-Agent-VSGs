"""
One-click paper figure generation.

Usage:
    python -m plotting.generate_all                          # all scenarios → default dir
    python -m plotting.generate_all kundur                   # single scenario
    python -m plotting.generate_all --output-dir results/my  # custom output dir
    python -m plotting.generate_all --new                    # timestamped new folder
"""
import sys
import argparse
import numpy as np
from copy import copy
from datetime import datetime

from plotting.configs import SCENARIOS, IO_PRESETS, EvalConfig
from plotting.evaluate import (
    create_env, load_agents, load_training_log,
    run_evaluation, run_robustness_sweep,
)
from plotting.paper_style import (
    apply_ieee_style, plot_training_curves, plot_time_domain_2x2,
    plot_cumulative_reward, save_fig,
)


def generate_scenario_figures(scenario_name: str, output_dir: str = None):
    """Generate all paper figures for one scenario.

    Parameters
    ----------
    output_dir : str or None
        Override output directory. If None, uses IOConfig default.
    """
    scenario = SCENARIOS[scenario_name]
    io = copy(IO_PRESETS[scenario_name])
    if output_dir is not None:
        io.output_dir = output_dir
    eval_cfg = EvalConfig()
    apply_ieee_style()

    print(f'\n{"="*60}')
    print(f' Generating figures: {scenario_name}')
    print(f'{"="*60}')

    # Cache env and agents for entire scenario
    env = create_env(scenario)
    agents = load_agents(io.model_dir, scenario.n_agents)

    # 1. Training curves
    print('\n--- Training curves ---')
    log = load_training_log(io.training_log)
    fig = plot_training_curves(
        np.array(log["total_rewards"]),
        [np.array(a) for a in log.get("agent_rewards", [])],
    )
    save_fig(fig, io.output_dir, f"{io.fig_prefix}_training.png")

    # 2. Per-disturbance: no-control + RL time-domain plots
    all_results = {}
    for dist in scenario.disturbances:
        print(f'\n--- {dist.name} ---')
        no_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="no_ctrl", env=env)
        rl_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="rl", env=env, agents=agents)
        all_results[dist.name] = {"no_ctrl": no_ctrl, "rl": rl_ctrl}

        fig = plot_time_domain_2x2(no_ctrl.trajectory, n_agents=scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_no_ctrl.png")

        fig = plot_time_domain_2x2(rl_ctrl.trajectory, n_agents=scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_ctrl.png")

    # 3. Cumulative reward per disturbance
    for dist_name, results in all_results.items():
        print(f'\n--- Cumulative reward: {dist_name} ---')
        fig = plot_cumulative_reward(
            {k: v.trajectory.rewards.tolist() for k, v in results.items()}
        )
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist_name}_cumulative.png")

    # 4. Robustness sweep
    print('\n--- Robustness sweep ---')
    first_dist = scenario.disturbances[0]
    robustness = run_robustness_sweep(
        scenario, first_dist, eval_cfg, agents=agents,
        failure_rates=[0.1, 0.2, 0.3],
        delay_steps_list=[1, 2, 3],
    )
    for label, result in robustness.items():
        print(f'  {label}: cumulative_reward={result.cumulative_reward:.2f}')

    env.close()
    print(f'\nAll figures saved to {io.output_dir}')


def _parse_args():
    parser = argparse.ArgumentParser(description='Generate paper figures')
    parser.add_argument('scenarios', nargs='*', default=list(SCENARIOS.keys()),
                        help='Scenario names (default: all)')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='Custom output directory for all figures')
    parser.add_argument('--new', action='store_true',
                        help='Create a timestamped new folder under results/')
    return parser.parse_args()


def main():
    args = _parse_args()

    # Determine output directory
    output_dir = args.output_dir
    if args.new:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = f'results/figures_{timestamp}'
        print(f'Output directory: {output_dir}')

    for name in args.scenarios:
        if name not in SCENARIOS:
            print(f'Unknown scenario: {name}')
            continue
        if name not in IO_PRESETS:
            print(f'No IO preset for {name}, skipping')
            continue
        generate_scenario_figures(name, output_dir=output_dir)


if __name__ == "__main__":
    main()
