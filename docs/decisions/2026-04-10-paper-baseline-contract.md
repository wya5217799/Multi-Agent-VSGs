# Paper Baseline Contract — Yang et al. TPWRS 2023

**Date:** 2026-04-10  
**Scope:** Defines the implementation choices that constitute "faithful reproduction"  
**Status:** Active — governs all Simulink and ANDES reward modifications

---

## Question 1 — Which backend is the primary target?

**Decision:** Simulink (Kundur + NE39) is the primary reproduction target.  
ANDES is the reference backend for sanity-checking reward behavior without MATLAB overhead.

**Rationale:** The paper's Fig. 4–13 training curves are generated from a time-domain
power system simulator, not a reduced ODE. Simulink is the closest available equivalent.

---

## Question 2 — Reward formula (paper vs engineering)

**Decision:** Implement paper's Eq. 14–18 strictly.

### r_f (Eq. 15–16) — Relative synchronization penalty

```
ω̄_i  = mean(Δω_i, Δω_{j∈N_i_active})          # local group average, Hz
r_f_i = -(Δω_i - ω̄_i)²
        - Σ_{j∈N_i} (Δω_j - ω̄_i)² · η_j       # η_j = comm success mask
```

**Why relative, not absolute:**  
The paper's core claim is oscillation suppression (inter-area sync), not frequency
restoration. The relative formula rewards agents for having *the same* frequency
deviation as their neighbors — even if all are off-nominal. This is intentional: UFLS
and governor response handle nominal restoration; the RL agent handles sync.

### r_h, r_d (Eq. 17–18) — Mean control effort penalty

```
ΔH̄   = mean_i(ΔH_i) = mean_i(delta_M_i / 2)   # mean inertia adjustment
ΔD̄   = mean_i(ΔD_i) = mean_i(delta_D_i)        # mean damping adjustment
r_h  = -(ΔH̄)²
r_d  = -(ΔD̄)²
```

**Why (mean(Δ))² not mean(Δ²):**  
The paper penalizes collective average effort, not the variance of individual actions.
`mean(Δ²) = mean(Δ)² + var(Δ)` — the old formula over-penalizes heterogeneous actions.

### Total per-agent reward

```
r_i = φ_f · r_f_i + φ_h · r_h + φ_d · r_d
    = φ_f · r_f_i - φ_h · (ΔH̄)² - φ_d · (ΔD̄)²
```

**Weights used:**
- Kundur: φ_f = 100, φ_h = 1, φ_d = 1  (unchanged)
- NE39:   φ_f = 200, φ_h = 1, φ_d = 1  (unchanged)

**What is NOT in this baseline:**  
The `PHI_ABS * (-Δω_i²)` absolute frequency penalty present in the ANDES backend
is an engineering addition beyond the paper. It is intentionally excluded from the
Simulink baseline. If ablation suggests it helps, it can be re-added as a labeled
extension with its own weight `φ_abs`.

---

## Question 3 — Buffer strategy

**Decision:** Accumulate buffer across episodes (do NOT clear per episode).

**Paper contradiction:** Algorithm 1 line 16 says "Clear buffer D_i", but Table I
specifies buffer_size=10000, batch_size=256, M=50 (steps/episode). Sampling 256
from 50 is mathematically impossible if the buffer is cleared each episode. The
pseudocode is inconsistent with the hyperparameter table. We treat the table as
authoritative.

**Engineering rationale:** Standard off-policy SAC is designed for experience reuse.
Clearing the buffer each episode converts SAC into an on-policy-style algorithm with
poor sample efficiency. This is an explicit deviation with documented justification.

**Buffer sizes in use:**
- Simulink Kundur: 100 000  (config_simulink.py; aligned with NE39)
- Simulink NE39:  100 000

**Minimum ablation commitment:** Before finalizing any paper results, run one
comparison: 2000-episode Kundur training with `CLEAR_BUFFER_PER_EPISODE=True`
vs `False`. Record both training curves.

---

## Question 4 — Parameter sharing vs independent agents

**Decision:** Keep current split:
- Simulink path: parameter-sharing SAC (`sac_agent_standalone.py`, CTDE paradigm)  
- ANDES/ODE path: independent per-agent SAC (`agents/ma_manager.py`)

**Note:** The paper describes independent agents. The Simulink path deviates.
This is flagged as a known gap; architectural unification is deferred until
reward alignment is validated.

---

## Modification log

| Date | File | Change |
|------|------|--------|
| 2026-04-10 | `kundur_simulink_env.py` | r_f: absolute → relative sync; r_h/r_d: mean(a²) → (mean(ΔH̄))² |
| 2026-04-10 | `ne39_simulink_env.py` | same as above |
