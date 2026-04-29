"""Probe B analyzer: detect 4-agent measurement collapse from paper_eval JSON.

Reads a paper_eval metrics JSON containing the new (2026-04-30) per-agent
decomposition fields:

  - r_f_global_per_agent      list[N_agents] per scenario
  - max_abs_df_hz_per_agent   list[N_agents] per scenario

and computes the falsification statistic for each scenario:

  collapse_score = (max(per_agent) - min(per_agent)) / max(|per_agent|, eps)

If collapse_score is consistently ~ 0 across scenarios with non-trivial
disturbance magnitudes, the 4-agent measurements are collapsed (the
omega_ts_i signals are not electrically separated). If collapse_score >
~0.1 routinely, the per-agent measurements respond independently as
expected from the network mode-shape distribution.

Usage:
    python probes/kundur/analyze_per_agent_collapse.py <metrics.json>

Exits non-zero if collapse_score < 0.05 for >50% of non-trivial scenarios
(|magnitude_sys_pu| > 0.3) — a hard falsification of "per-agent
measurements are independent".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def analyze(path: Path) -> int:
    if not path.exists():
        print(f"ERROR: metrics file not found: {path}")
        return 2
    with path.open() as f:
        m = json.load(f)
    eps = m.get("per_episode_metrics", [])
    if not eps:
        print("ERROR: no per_episode_metrics in JSON")
        return 2

    if "r_f_global_per_agent" not in eps[0]:
        print("ERROR: this metrics file pre-dates Probe B (2026-04-30); "
              "re-run paper_eval with current evaluation/paper_eval.py")
        return 2

    print(f"=== Probe B: 4-agent collapse analysis  ({path.name}) ===")
    print(f"  policy_label: {m.get('policy_label', '?')}")
    print(f"  n_scenarios:  {m.get('n_scenarios', '?')}")
    print()

    n_collapsed = 0
    n_nontrivial = 0
    rows = []
    for e in eps:
        idx = e["scenario_idx"]
        mag = abs(e["magnitude_sys_pu"])
        rfa = e["r_f_global_per_agent"]
        dfa = e["max_abs_df_hz_per_agent"]
        if not rfa or not dfa:
            continue
        rf_range = max(rfa) - min(rfa)
        rf_max = max(abs(x) for x in rfa) or 1e-12
        rf_collapse_score = rf_range / rf_max
        df_range = max(dfa) - min(dfa)
        df_max = max(dfa) or 1e-12
        df_collapse_score = df_range / df_max
        is_nontrivial = mag > 0.3
        if is_nontrivial:
            n_nontrivial += 1
            if df_collapse_score < 0.05:
                n_collapsed += 1
        rows.append({
            "idx": idx,
            "mag": e["magnitude_sys_pu"],
            "rfa": rfa,
            "dfa": dfa,
            "rf_collapse": rf_collapse_score,
            "df_collapse": df_collapse_score,
        })

    # Print first 5 + worst 5 collapse-scoring scenarios
    print(f"  {'idx':>3} {'mag':>+7} {'r_f/agent':>40} {'rf_coll':>8} "
          f"{'df_max/agent (Hz)':>40} {'df_coll':>8}")
    for r in rows[:5]:
        rfs = " ".join(f"{x:+.3f}" for x in r["rfa"])
        dfs = " ".join(f"{x:.4f}" for x in r["dfa"])
        print(f"  {r['idx']:>3d} {r['mag']:>+7.3f} {rfs:>40} "
              f"{r['rf_collapse']:>8.4f} {dfs:>40} {r['df_collapse']:>8.4f}")
    print()
    rows_by_collapse = sorted(rows, key=lambda r: r["df_collapse"])
    print(f"  --- 5 most collapsed scenarios (df_collapse_score ascending) ---")
    for r in rows_by_collapse[:5]:
        rfs = " ".join(f"{x:+.3f}" for x in r["rfa"])
        dfs = " ".join(f"{x:.4f}" for x in r["dfa"])
        print(f"  {r['idx']:>3d} {r['mag']:>+7.3f} {rfs:>40} "
              f"{r['rf_collapse']:>8.4f} {dfs:>40} {r['df_collapse']:>8.4f}")
    print()

    print(f"  non-trivial scenarios (|mag| > 0.3):              {n_nontrivial}")
    print(f"  collapsed (df_collapse_score < 0.05):              {n_collapsed}")
    print(f"  collapsed fraction:                                 "
          f"{n_collapsed/max(n_nontrivial,1)*100:.1f}%")
    print()

    # Falsification verdict
    if n_collapsed / max(n_nontrivial, 1) > 0.5:
        print("VERDICT: PROVEN COLLAPSE — >50% of non-trivial scenarios show "
              "df_collapse_score < 0.05. Per-agent omega measurements are "
              "NOT electrically separated. Mode-shape distribution is broken.")
        return 1
    elif n_collapsed / max(n_nontrivial, 1) > 0.2:
        print("VERDICT: SUSPECT — 20-50% of scenarios show collapse. "
              "Investigate which scenarios collapse vs which respond.")
        return 1
    else:
        print("VERDICT: PASS — per-agent measurements show expected variance.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python analyze_per_agent_collapse.py <metrics.json>")
        sys.exit(2)
    sys.exit(analyze(Path(sys.argv[1])))
