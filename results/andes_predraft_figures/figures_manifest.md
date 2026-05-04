# Predraft Figures Manifest

Generated: 2026-05-04
Output directory: `results/andes_predraft_figures/`
Script: `scenarios/kundur/_predraft_figures.py` (initial); `scenarios/kundur/_regen_fig1_fig3.py` (fig1/fig3 regen 2026-05-04)

## Fig 1: `fig1_agent_share_3seeds.png` (alias `fig1_agent_share_5seeds.png`)

**REGENERATED 2026-05-04 with paper-faithful comm_fail_prob=0.1 data (5 seeds)**

**Caption (publication-ready):** Per-agent ablation share for agents a0–a3 across five independent seeds (seeds 42–46, comm_fail_prob=0.1). Agent a1 (ES2@Bus16) consistently dominates with mean 64.0% (range 54.6–74.7%); a2 (ES3@Bus14) contributes 6–22%.

**Cite in:** §III-C or §IV-B (agent specialisation discussion)

**Source files (all comm_fail_prob=0.1):**
- `results/harness/kundur/agent_state/agent_state_phase4_seed42_commfail01.json` (a1=68.3%)
- `results/harness/kundur/agent_state/agent_state_phase4_seed43_commfail01.json` (a1=54.6%)
- `results/harness/kundur/agent_state/agent_state_phase4_seed44_commfail01.json` (a1=74.7%)
- `results/harness/kundur/agent_state/agent_state_phase4ext_seed45_final.json` (a1=66.4%)
- `results/harness/kundur/agent_state/agent_state_phase4ext_seed46_final.json` (a1=56.2%)

## Fig 2: `fig2_ckpt_trajectory_seed42.png`

**Caption (publication-ready):** Ablation share trajectories for seed 42 across training checkpoints (ep 100–500). Agent a1 locks dominance at ep 100 (56.6%) and remains above 50% throughout, indicating early specialisation.

**Cite in:** §IV-B (convergence / early lock analysis)

**Source files:**
- `results/andes_ckpt_trajectory_phase4_seed42/trajectory.json`

## Fig 3: `fig3_cum_rf_comparison.png`

**REGENERATED 2026-05-04 with paper-grade data + bootstrap 95% CI bands (comm_fail_prob=0.1)**

**Caption (publication-ready):** Cumulative frequency reward total over 50 fixed test scenarios (comm_fail_prob=0.1). n=5 DDIC mean −1.186, bootstrap 95% CI [−1.39, −0.98]; adaptive K=10/400 total −1.060, CI [−1.32, −0.82]. Point estimates are statistically TIED (CIs overlap). Error bars show 95% bootstrap CI.

**Cite in:** §IV-C (main results / comparison table)

**Source files:**
- `results/andes_eval_paper_grade/per_seed_summary.json`
- `results/andes_eval_paper_grade/n5_aggregate.json`

## Fig 4: `fig4_paper_scenarios_ls1_ls2.png`

**Caption (publication-ready):** Cumulative frequency reward on paper-specific load-step scenarios (LS1 = Bus14 −2.48 pu, LS2 = Bus15 +1.88 pu). DDIC seed44 improves over no-control and adaptive; paper reference values are 5–7× larger due to backend and scaling differences.

**Cite in:** §IV-C (paper alignment / scenario comparison)

**Source files:**
- `results/andes_eval_paper_specific/summary.md`
- `results/andes_eval_paper_specific/adaptive_K10_K400_load_step_1.json`
- `results/andes_eval_paper_specific/adaptive_K10_K400_load_step_2.json`
- `results/andes_eval_paper_specific/ddic_phase4_seed44_load_step_1.json`
- `results/andes_eval_paper_specific/ddic_phase4_seed44_load_step_2.json`
- `results/andes_eval_paper_specific/no_control_load_step_1.json`

## Fig 5: `fig5_worst_eps_scatter.png`

**Caption (publication-ready):** Maximum frequency deviation vs disturbance magnitude for the five worst episodes (seed 42, Phase 4). PQ_Bus14 high-magnitude disturbances (1.5–1.95 pu) form the dominant failure cluster.

**Cite in:** §IV-D (failure analysis / robustness)

**Source files:**
- `results/andes_worst_eps_trace/action_traces.json`
- `results/harness/kundur/agent_state/agent_state_phase4_seed42_final.json`
