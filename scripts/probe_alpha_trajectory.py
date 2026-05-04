"""
Alpha trajectory probe — DDIC Phase 4, 5 seeds (read-only).
Produces: results/andes_alpha_trajectory_5seed.png
         quality_reports/audits/2026-05-04_andes_alpha_trajectory_probe.md
"""
import json
import os
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEEDS = [42, 43, 44, 45, 46]
BASE = "results"
RESULTS_DIR = BASE

# ── 1. Load alpha per seed ──────────────────────────────────────────────────
def load_alpha(seed):
    """Return array shape (n_episodes, n_agents) of mean-alpha-per-episode."""
    path = os.path.join(BASE, f"andes_phase4_noPHIabs_seed{seed}", "monitor_checkpoint.json")
    with open(path) as f:
        data = json.load(f)
    sac = data["_sac_losses"]
    # each episode: list of n_agent dicts with 'alpha' key
    rows = []
    for ep_agents in sac:
        agent_alphas = [ag["alpha"] for ag in ep_agents if "alpha" in ag]
        if agent_alphas:
            rows.append(np.mean(agent_alphas))
    return np.array(rows)  # shape (n_eps,)


def load_alpha_per_agent(seed):
    """Return dict: agent_idx -> array(n_episodes)."""
    path = os.path.join(BASE, f"andes_phase4_noPHIabs_seed{seed}", "monitor_checkpoint.json")
    with open(path) as f:
        data = json.load(f)
    sac = data["_sac_losses"]
    n_agents = len(sac[0]) if sac else 4
    per_agent = {i: [] for i in range(n_agents)}
    for ep_agents in sac:
        for i, ag in enumerate(ep_agents):
            if "alpha" in ag:
                per_agent[i].append(ag["alpha"])
    return {i: np.array(v) for i, v in per_agent.items()}


def load_cum_rf(seed):
    """Return cum_rf_total from the Tier A eval results (50 test episodes).
    Values from quality_reports/audits/2026-05-04_andes_tier_a_n5_verdict.md [FACT].
    training_log.json episode_rewards stores per-agent-index totals, not per-component.
    """
    tier_a_values = {42: -1.1910, 43: -1.3641, 44: -0.9143, 45: -1.5234, 46: -0.9385}
    return tier_a_values.get(seed)


# ── 2. Collect data ─────────────────────────────────────────────────────────
alpha_mean = {}       # seed -> array(n_eps) of mean-across-agents alpha
for seed in SEEDS:
    alpha_mean[seed] = load_alpha(seed)

# Load cum_rf from training_log
cum_rf = {}
for seed in SEEDS:
    cum_rf[seed] = load_cum_rf(seed)

print("cum_rf per seed:", {s: f"{v:.1f}" if v is not None else "N/A" for s, v in cum_rf.items()})
print("alpha array lengths:", {s: len(alpha_mean[s]) for s in SEEDS})

# ── 3. Summary stats ─────────────────────────────────────────────────────────
WINDOW = 50
final_alpha = {}
alpha_osc = {}
for seed in SEEDS:
    arr = alpha_mean[seed]
    tail = arr[-WINDOW:] if len(arr) >= WINDOW else arr
    final_alpha[seed] = float(np.mean(tail))
    alpha_osc[seed] = float(np.std(tail))  # oscillation in last 50ep

fa_vals = np.array(list(final_alpha.values()))
cross_mean = float(np.mean(fa_vals))
cross_std  = float(np.std(fa_vals))
cross_cv   = cross_std / cross_mean if cross_mean != 0 else 0.0

print("\nFinal alpha (last 50ep mean):")
for seed in SEEDS:
    print(f"  seed{seed}: alpha={final_alpha[seed]:.4f}  osc_std={alpha_osc[seed]:.4f}  cum_rf={cum_rf.get(seed, 'N/A')}")
print(f"\nCross-seed: mean={cross_mean:.4f}  std={cross_std:.4f}  CV={cross_cv:.3f}")

# ── 4. Correlation final_alpha vs cum_rf ─────────────────────────────────────
fa_list  = [final_alpha[s] for s in SEEDS]
rf_list  = [cum_rf[s] for s in SEEDS if cum_rf[s] is not None]
seeds_ok = [s for s in SEEDS if cum_rf[s] is not None]

if len(seeds_ok) >= 3:
    fa_ok = [final_alpha[s] for s in seeds_ok]
    corr = np.corrcoef(fa_ok, rf_list)[0, 1]
else:
    corr = float("nan")
print(f"\nCorr(final_alpha, cum_rf) = {corr:.3f}")

# ── 5. Plot ──────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

ax = axes[0]
colors = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00"]
for i, seed in enumerate(SEEDS):
    arr = alpha_mean[seed]
    ep  = np.arange(len(arr))
    ax.plot(ep, arr, color=colors[i], alpha=0.85, lw=1.2, label=f"seed{seed}")
ax.set_xlabel("Episode")
ax.set_ylabel("Alpha (mean across agents)")
ax.set_title("SAC Entropy Temp (Alpha) Trajectory — 5 Seeds")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
ax.axhline(cross_mean, color="k", ls="--", lw=0.8, alpha=0.5, label=f"cross-seed mean={cross_mean:.3f}")

# scatter: final_alpha vs cum_rf
ax2 = axes[1]
if seeds_ok:
    fa_ok_arr = [final_alpha[s] for s in seeds_ok]
    rf_ok_arr = rf_list
    for i, s in enumerate(seeds_ok):
        ax2.scatter(final_alpha[s], cum_rf[s], color=colors[SEEDS.index(s)], s=80,
                    label=f"seed{s}", zorder=3)
        ax2.annotate(f"s{s}", (final_alpha[s], cum_rf[s]),
                     textcoords="offset points", xytext=(4, 4), fontsize=7)
    # fit line if 5 points
    if len(seeds_ok) == 5:
        m, b = np.polyfit(fa_ok_arr, rf_ok_arr, 1)
        xs = np.linspace(min(fa_ok_arr)*0.98, max(fa_ok_arr)*1.02, 50)
        ax2.plot(xs, m*xs + b, "k--", lw=0.8, alpha=0.6)
ax2.set_xlabel("Final Alpha (last 50ep mean)")
ax2.set_ylabel("Cum r_f (total training)")
ax2.set_title(f"Final Alpha vs Cum r_f  (r={corr:.2f})")
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)

plt.tight_layout()
out_png = "results/andes_alpha_trajectory_5seed.png"
plt.savefig(out_png, dpi=150)
print(f"\nPlot saved: {out_png}")

# ── 6. Verdict ───────────────────────────────────────────────────────────────
# ALPHA_HIGH_VARIANCE: CV > 0.30
# ALPHA_STABLE:        CV < 0.10
# ALPHA_NOT_CONVERGED: any seed osc > 50% of its final_alpha in last 50ep
# NO_CORRELATION:      |corr| < 0.3

verdicts = []
if cross_cv > 0.30:
    verdicts.append("ALPHA_HIGH_VARIANCE")
elif cross_cv < 0.10:
    verdicts.append("ALPHA_STABLE")
else:
    verdicts.append("ALPHA_MODERATE_VARIANCE")

for seed in SEEDS:
    ratio = alpha_osc[seed] / final_alpha[seed] if final_alpha[seed] != 0 else 0
    if ratio > 0.50:
        verdicts.append(f"ALPHA_NOT_CONVERGED(seed{seed})")

if not math.isnan(corr) and abs(corr) < 0.3:
    verdicts.append("NO_CORRELATION")

print("\nVerdicts:", verdicts)

# ── 7. Write audit markdown ──────────────────────────────────────────────────
os.makedirs("quality_reports/audits", exist_ok=True)
md_path = "quality_reports/audits/2026-05-04_andes_alpha_trajectory_probe.md"

with open(md_path, "w") as f:
    f.write("""# Andes Alpha Trajectory Probe — 5 Seeds DDIC Phase 4
**Date:** 2026-05-04
**Status:** COMPLETE
**Data source:** `results/andes_phase4_noPHIabs_seed{42..46}/monitor_checkpoint.json` [FACT — current HEAD files]

---

## 1. Was Alpha Logged?

**Yes.** Alpha is in `monitor_checkpoint.json → _sac_losses[ep][agent]["alpha"]`.
Not present in `training_log.json` (only aggregate rewards) or `monitor_data.csv` (only env metrics).

---

## 2. Per-Seed Final Alpha Table (last 50-episode mean)

| Seed | Final Alpha (mean) | Osc Std (last 50ep) | Cum r_f (total) |
|------|--------------------|---------------------|-----------------|
""")
    for seed in SEEDS:
        rf_str = f"{cum_rf[seed]:.4f}" if cum_rf[seed] is not None else "N/A"
        f.write(f"| {seed} | {final_alpha[seed]:.4f} | {alpha_osc[seed]:.4f} | {rf_str} |\n")

    f.write(f"""
---

## 3. Cross-Seed Statistics [CLAIM — derived from logged values]

| Metric | Value |
|--------|-------|
| Cross-seed mean final alpha | {cross_mean:.4f} |
| Cross-seed std final alpha | {cross_std:.4f} |
| Coefficient of variation (CV = std/mean) | {cross_cv:.3f} |
| Corr(final_alpha, cum_rf) | {corr:.3f} |

---

## 4. Plot

`results/andes_alpha_trajectory_5seed.png`

Left panel: episode-by-episode alpha trajectory for all 5 seeds.
Right panel: scatter of final alpha vs. cumulative r_f with linear fit.

---

## 5. Verdict [CLAIM]

**{' | '.join(verdicts)}**

Threshold definitions:
- ALPHA_HIGH_VARIANCE: cross-seed CV > 0.30
- ALPHA_STABLE: CV < 0.10
- ALPHA_MODERATE_VARIANCE: CV in [0.10, 0.30]
- ALPHA_NOT_CONVERGED(seedX): last-50ep std > 50% of mean alpha for that seed
- NO_CORRELATION: |corr(final_alpha, cum_rf)| < 0.3

---

## 6. Recommendation [CLAIM]

""")
    # Write recommendation text based on verdicts
    if "ALPHA_HIGH_VARIANCE" in verdicts:
        rec = (
            "Cross-seed CV > 0.30 → alpha IS a variance source. "
            "Consider fixing alpha (e.g., alpha=0.1 or alpha=0.2) to decouple "
            "exploration scale from seed randomness. "
            "Alternatively, lower target_entropy (e.g., -1.0 instead of -action_dim) "
            "to bias toward lower, more stable alpha. "
            f"Correlation with cum_rf = {corr:.2f}; "
        )
        if not math.isnan(corr) and abs(corr) >= 0.3:
            rec += "significant correlation suggests alpha level matters for performance — fix alpha first."
        else:
            rec += "weak correlation — alpha variance exists but performance link is unclear; fixing alpha reduces a confound."
    elif "ALPHA_STABLE" in verdicts:
        rec = (
            f"Cross-seed CV < 0.10 → alpha NOT the variance source (std={cross_std:.4f} on mean={cross_mean:.4f}). "
            "Look elsewhere for the root cause of std=0.265 in cum_rf_total: "
            "likely policy/value function initialization sensitivity, reward sparsity, or env stochasticity. "
            "No alpha tuning recommended at this stage."
        )
    else:
        rec = (
            f"Cross-seed CV = {cross_cv:.3f} (moderate, in [0.10, 0.30]). "
            "Alpha contributes some variance but is not the dominant source. "
            "Fixing alpha would reduce one confound but is unlikely to fully resolve std=0.265. "
            f"Corr(final_alpha, cum_rf) = {corr:.2f}; "
            "investigate policy initialization and reward variance in parallel."
        )
    f.write(rec + "\n")

print(f"Audit written: {md_path}")
