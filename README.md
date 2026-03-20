# Multi-Agent Deep Reinforcement Learning for VSG Control

Reproduction of **Yang et al.**, "A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent Deep Reinforcement Learning for Multiple Paralleled VSGs", *IEEE Transactions on Power Systems*, Vol.38, No.6, Nov 2023.

## Overview

This project reproduces all 18 figures (Fig 4-21) from the paper using:
- **ODE simplified model**: Kron-reduced swing equation for fast prototyping
- **ANDES full simulation**: Kundur two-area system with GENCLS-based VSGs (requires WSL)

### Key Results

| Experiment | Finding | Status |
|-----------|---------|--------|
| Distributed MADRL vs Centralized DRL (N=8) | Centralized collapses (-2929) while distributed stays stable (-551) | Reproduced |
| MADRL vs Adaptive Inertia vs No Control | MADRL (-0.10) > Adaptive (-0.50) > No control (-1.03) | Reproduced |
| Communication failure robustness (30%) | Only 8.6% performance degradation | Reproduced |
| Communication delay robustness (0.2s) | Only 2.3% performance degradation | Reproduced |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Quick validation (~10 min)
python run_all.py --quick

# Full reproduction (~4-5 hours)
python run_all.py

# With ANDES simulation (requires WSL + andes_venv)
python run_all.py --andes
```

## Project Structure

```
train.py                   # ODE main training (2000 episodes)
evaluate.py                # ODE evaluation → Fig 4-13
train_scalability.py       # Scalability: distributed vs centralized → Fig 14-15
generate_fig16.py          # Scalability analysis → Fig 16
train_new_england.py       # New England 8-VSG system → Fig 17-21
train_andes.py             # ANDES training (WSL only)
evaluate_andes.py          # ANDES evaluation → Fig 4-13 (ANDES)
run_all.py                 # One-click runner for all experiments
generate_summary.py        # Generate results summary table
config.py                  # Global configuration

env/
  power_system.py          # ODE frequency dynamics (swing equation)
  multi_vsg_env.py         # Multi-agent ODE environment
  andes_vsg_env.py         # ANDES environment (WSL only)
  network_topology.py      # Laplacian matrix & communication graph

agents/
  sac.py                   # SAC agent
  networks.py              # Actor-Critic networks (4x128)
  ma_manager.py            # Distributed multi-agent manager
  centralized_sac.py       # Centralized SAC for scalability comparison
  replay_buffer.py         # Experience replay buffer

results/figures/           # All generated figures (29 PNGs)
```

## Algorithm

- **Multi-Agent SAC** with independent learners
- Each agent: 4-layer x 128 hidden units (Actor + Twin Critic)
- Observation: local frequency + 2-neighbor info via communication graph
- Action: virtual inertia adjustment (ΔH) + virtual droop adjustment (ΔD)
- Reward: frequency synchronization penalty (Eq. 14-18 in paper)

## Figures

### ODE Model (Fig 4-13)
- **Fig 4**: Training curves (5 subplots: total + 4 agents)
- **Fig 5**: Cumulative reward comparison (MADRL / Adaptive / No control)
- **Fig 6-9**: Load step response (with/without control)
- **Fig 10-11**: Communication failure test
- **Fig 12-13**: Communication delay test

### Scalability (Fig 14-16)
- **Fig 14**: Training curves for N=2, 4, 8 (distributed vs centralized)
- **Fig 15**: Cumulative reward comparison
- **Fig 16**: Scalability analysis (dimension / performance)

### New England System (Fig 17-21)
- **Fig 17**: Training curves (8 agents, 2000 episodes)
- **Fig 18**: Frequency without control
- **Fig 19**: Cumulative reward (MADRL / Adaptive inertia / No control)
- **Fig 20**: System dynamics with proposed control (4 subplots)
- **Fig 21**: Short-circuit fault response

### ANDES Full Simulation
- ANDES versions of Fig 4-13 with Kundur two-area system

## Requirements

- Python 3.10+
- PyTorch 2.0+
- NumPy, Matplotlib, SciPy
- (Optional) WSL + ANDES 2.0.0 for full simulation

## Reference

```bibtex
@article{yang2023distributed,
  title={A Distributed Dynamic Inertia-Droop Control Strategy Based on Multi-Agent
         Deep Reinforcement Learning for Multiple Paralleled VSGs},
  author={Yang, Jingyu and others},
  journal={IEEE Transactions on Power Systems},
  volume={38},
  number={6},
  year={2023}
}
```
