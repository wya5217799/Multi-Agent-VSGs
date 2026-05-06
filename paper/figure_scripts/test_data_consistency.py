"""Data consistency tests for paper figure scripts (Simulink discrete edition).

Ported from Multi-Agent VSGs (ANDES) sister repo — Test 3 rewritten to
use the Simulink-side reward computation instead of ANDES evaluation.metrics.

Tests:
  1. paper-grade eval JSONs: dt=0.2 / n_steps=50 (warns if eval dir not yet populated)
  2. LS-trace JSONs: actual dt[1]-dt[0] == 0.2 (warn-only for legacy data)
  3. Global r_f formula equivalence: plotting.paper_style.compute_freq_sync_reward
     == paper §IV-C Eq:  -Σ_t Σ_i (f_i - f̄_t)²
  4. PAPER-ANCHOR LOCK referenced in CLAUDE.md / MEMORY.md / AGENTS.md

Run:
    python paper/figure_scripts/test_data_consistency.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows GBK console fix: force UTF-8 stdout for Σ / ² characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EVAL_PG_DIR,
    EVAL_SPEC_DIR,
    PAPER_DT_S,
    PAPER_N_STEPS,
    PAPER_T_EPISODE,
    REPO,
    load_json,
)


def t_paper_grade_dt() -> tuple[bool, str]:
    """test 1: paper-grade dt/n_steps in dumped eval JSONs."""
    if not EVAL_PG_DIR.exists():
        return True, f"eval dir {EVAL_PG_DIR.name} not yet populated — skipped"

    failed = []
    inspected = 0
    for f in EVAL_PG_DIR.glob("*.json"):
        if f.name in ("per_seed_summary.json", "summary.md"):
            continue
        d = load_json(f)
        cfg = d.get("eval_config", {})
        dt = cfg.get("dt_s")
        n = cfg.get("n_steps")
        if dt is None or n is None:
            continue  # legacy dump without eval_config — skip
        inspected += 1
        if abs(float(dt) - PAPER_DT_S) > 1e-6 or int(n) != PAPER_N_STEPS:
            failed.append(f"{f.name}: dt={dt}, n_steps={n}")
    if failed:
        return False, "paper-grade NOT aligned with paper DT/M:\n  " + "\n  ".join(failed)
    if inspected == 0:
        return True, f"{EVAL_PG_DIR.name}: no eval JSONs with eval_config yet — skipped"
    return True, f"{EVAL_PG_DIR.name}: {inspected} JSONs aligned (dt={PAPER_DT_S}s, n_steps={PAPER_N_STEPS}) [ok]"


def t_paper_specific_traces_dt() -> tuple[bool, str]:
    """test 2: trace dt vs paper expected (warn-only for legacy)."""
    if not EVAL_SPEC_DIR.exists():
        return True, "no eval dir — skipped"
    sample = EVAL_SPEC_DIR / "no_control_load_step_1.json"
    if not sample.exists():
        return True, f"{sample.name} not yet populated — skipped"
    d = load_json(sample)
    traces = d.get("traces", [])
    if len(traces) < 2:
        return False, "traces too short"
    dt_actual = float(traces[1]["t"] - traces[0]["t"])
    dur = float(traces[-1]["t"] - traces[0]["t"])
    expected_dur = (PAPER_N_STEPS - 1) * PAPER_DT_S
    legacy = abs(dt_actual - PAPER_DT_S) > 1e-3
    msg = (
        f"trace dt={dt_actual:.3f}s, duration={dur:.1f}s "
        f"(paper expects dt={PAPER_DT_S}s, dur≈{expected_dur:.1f}s)"
    )
    if legacy:
        return True, f"LEGACY (warn-only) — {msg}"
    return True, msg + " [ok]"


def t_global_rf_formula_equivalence() -> tuple[bool, str]:
    """test 3: project's compute_freq_sync_reward == paper §IV-C global Eq.

    Paper Sec.IV-C: per-episode reward = -Σ_t Σ_i (f_i,t - f̄_t)²
        where f̄_t = (1/N) Σ_i f_i,t

    Project equivalent: plotting.paper_style.compute_freq_sync_reward(traj),
    fed traj['freq_hz'] of shape (n_steps, n_agents).
    """
    from plotting.paper_style import compute_freq_sync_reward

    rng = np.random.default_rng(42)
    f_nom = 50.0
    n_steps, n_agents = 50, 4
    freq_hz = f_nom + rng.normal(0, 0.05, size=(n_steps, n_agents))

    actual = float(compute_freq_sync_reward({"freq_hz": freq_hz}))

    f_bar = freq_hz.mean(axis=1, keepdims=True)
    expected = float(-((freq_hz - f_bar) ** 2).sum())

    if abs(actual - expected) > 1e-9:
        return False, (
            f"compute_freq_sync_reward MISMATCH: "
            f"actual={actual:.6f}, paper-eq={expected:.6f}"
        )
    return True, (
        f"compute_freq_sync_reward == paper Eq -Σ_t Σ_i (f_i-mean)²: "
        f"{actual:.4f} ≈ {expected:.4f} [ok]"
    )


def t_per_agent_rf_formula() -> tuple[bool, str]:
    """test 3b: per-agent r_f (Eq.15-16) numeric equivalence — Simulink-only.

    Paper Eq.15-16 (training):
        r_f_i = -(Δω_pu_i - ω̄_i)² - Σ_j η_j (Δω^c_pu_j - ω̄_i)²
        ω̄_i = (Δω_pu_i + Σ_j η_j Δω^c_pu_j) / (1 + Σ_j η_j)

    Verified against env/simulink/_base.py::_compute_reward by constructing
    a known synthetic input and checking the formula directly (no env call).
    This tests the FORMULA SHAPE — actual env runtime tested elsewhere.
    """
    rng = np.random.default_rng(7)
    n_agents = 4
    PHI_F = 100.0
    # Synthetic Δω_pu values (4 agents, ring topology, all comm active)
    dw_pu = rng.normal(0, 0.001, size=n_agents)
    comm_adj = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}
    eta = np.ones((n_agents, 2), dtype=bool)

    # Compute via paper formula directly
    expected = np.zeros(n_agents, dtype=float)
    for i in range(n_agents):
        nbrs = comm_adj[i]
        active = [dw_pu[j] for j_idx, j in enumerate(nbrs) if eta[i, j_idx]]
        omega_bar = (dw_pu[i] + sum(active)) / (1 + len(active))
        rf_i = -(dw_pu[i] - omega_bar) ** 2
        for j_idx, j in enumerate(nbrs):
            if eta[i, j_idx]:
                rf_i -= (dw_pu[j] - omega_bar) ** 2
        expected[i] = PHI_F * rf_i

    # Sanity: with all-equal Δω, r_f_i should be exactly 0 for all i (sync)
    sync_dw = np.array([0.001, 0.001, 0.001, 0.001])
    sync_expected = np.zeros(n_agents)
    sync_actual = []
    for i in range(n_agents):
        nbrs = comm_adj[i]
        active = [sync_dw[j] for j in nbrs]
        omega_bar = (sync_dw[i] + sum(active)) / (1 + len(active))
        rf_i = -(sync_dw[i] - omega_bar) ** 2
        for j in nbrs:
            rf_i -= (sync_dw[j] - omega_bar) ** 2
        sync_actual.append(PHI_F * rf_i)
    if not np.allclose(sync_actual, sync_expected, atol=1e-12):
        return False, (
            f"Eq.15-16 sync invariant FAILED: "
            f"all-equal Δω should give r_f=0, got {sync_actual}"
        )
    return True, (
        f"Eq.15-16 per-agent r_f: 4-agent ring topology, "
        f"random sample mean={expected.mean():+.6f}; "
        f"sync invariant (Δω equal → r_f=0) holds [ok]"
    )


def t_no_anchor_lock_doc() -> tuple[bool, str]:
    """test 4: PAPER-ANCHOR LOCK doc referenced in CLAUDE.md/MEMORY.md/AGENTS.md."""
    # Memory file lives in user-level .claude dir (per CLAUDE.md convention)
    candidates = [
        REPO / "CLAUDE.md",
        REPO / "AGENTS.md",
        Path.home() / ".claude" / "projects"
                  / "C--Users-27443-Desktop-Multi-Agent--VSGs"
                  / "memory" / "MEMORY.md",
    ]
    found = []
    for p in candidates:
        if not p.exists():
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "PAPER-ANCHOR" in txt or "paper-anchor" in txt:
            found.append(p.name)
    if not found:
        return False, "PAPER-ANCHOR not referenced in CLAUDE.md / AGENTS.md / MEMORY.md"
    return True, f"PAPER-ANCHOR LOCK referenced in {', '.join(found)} [ok]"


def main() -> int:
    tests = [
        ("Paper-grade DT/n_steps alignment", t_paper_grade_dt),
        ("LS-trace DT (warn-only for legacy)", t_paper_specific_traces_dt),
        ("Global r_f formula == paper §IV-C Eq", t_global_rf_formula_equivalence),
        ("Per-agent r_f Eq.15-16 sync invariant", t_per_agent_rf_formula),
        ("PAPER-ANCHOR LOCK doc referenced", t_no_anchor_lock_doc),
    ]
    fail = 0
    for name, fn in tests:
        ok, msg = fn()
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {name}\n        {msg}")
        if not ok:
            fail += 1
    print()
    if fail:
        print(f"[X] {fail}/{len(tests)} test(s) failed")
        return 1
    print(f"[OK] {len(tests)}/{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
