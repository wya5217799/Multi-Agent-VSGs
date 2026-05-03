# Option G — Day 0.5 alt (c') Phase 1 Feasibility Audit

**Date:** 2026-04-30
**Plan:** `quality_reports/plans/2026-04-30_option_g_switch_rbank_phasor_first_then_discrete.md`
**Spec:** plan §0.5 "Day 0.5: alt (c') Phase 1 feasibility check at Bus 14/15"

---

## 1. Audit checklist (per plan §0.5)

### Check 1: `load_defs` has no Bus 14 / Bus 15 entries

`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` lines 126-129:

```matlab
load_defs = {
    'Load7',  7,  967e6,  100e6;     % bus, P (W), Q_inductive (var)
    'Load9',  9, 1767e6,  100e6;
};
```

✓ **PASS** — `load_defs` contains only Load7 + Load9. `Load14` /
`Load15` not present anywhere in the build script.

### Check 2: SG capacity headroom for +248 MW

Per IC `kundur_ic_cvs_v3.json`:
- `sg_pm0_sys_pu = [7.000, 7.000, 7.190]`
- `vsg_pm0_pu = [0.250, 0.250, 0.250, 0.250]` (4 ESS)
- `p_load_total_sys_pu = -29.82` ⇒ total load 2982 MW
  = 967 + 1767 + **248** ⇒ Bus 14 LS1 already accounted for in the IC.
- `p_ess_total_sys_pu = +1.00` ⇒ 4 × 0.25 sys-pu (ESS group injecting
  100 MW combined to balance the +248 MW load + losses).

Each SG capacity per paper Sec.IV-A = 7 GVA = 70 sys-pu (Sbase = 100 MVA).
Current dispatch ratio ≈ 7/70 = 10 %. Even adding the full +248 MW to
SG would put each at ≈ 7.83 sys-pu = 11 % capacity. ✓ abundant headroom.

✓ **PASS** — but with a critical *deviation* from the plan's
expectation; see §2 below.

---

## 2. Critical deviations from plan §0.5 / §1.3 / §3 expectations

### Deviation A: IC topology variant is already `ls1_preengaged`

`kundur_ic_cvs_v3.json` line 6:

```json
"topology_variant": "v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged",
```

The build script's assertion (line 39-40) rejects any IC that is not
this variant. The variant string explicitly says "ls1_preengaged" =
**Bus 14 LS1 248 MW already pre-engaged in NR**. This means the plan's
§3 "NR re-derive after build" step is *already done* — it was done
during the v3 IC creation. The plan was written assuming a "pre-Option-G
IC" that does *not* include Bus 14 LS1, but no such IC exists in the
project at the moment.

### Deviation B: ESS absorbs the +248 MW, not SG

Per IC, the +248 MW Bus 14 load is balanced by:
- Loss     : +0.371 sys-pu (37.1 MW)
- ESS group: +1.001 sys-pu (100.1 MW, 4 × +25 MW)
- SG dispatch: **unchanged** at 7+7+7.19 = 21.19 sys-pu
- Wind     : unchanged at 7+1 = 8 sys-pu

Plan §3.2 acceptance is:

> vsg_pm0_pu MUST be unchanged (< 1e-6) — ESS PV-bus assumption broken
> if changes
> sg_pm0_sys_pu SHOULD increase by ~+0.83 sys-pu / SG (split 248/3 MW),
> total +2.48 sys-pu across 3 SGs

This expectation is **inverted from the actual IC**. The IC sets
`q1_ess_dispatch = "(a) preserve paper dispatch; ESS group absorbs
surplus"`, which means **ESS** absorbs the +248 MW, NOT SG. This is a
design choice baked into `compute_kundur_cvs_v3_powerflow`, and it is
the correct paper-faithful behavior (paper Sec.IV-A: ESS group balances
the system to keep SG at paper-stated 7/7/7.19).

→ Plan §3.2 acceptance criteria are **mis-specified** for the actual
project NR convention. If the plan is executed literally, Step 3 will
fail every time — but for the *wrong reason* (NR projects to ESS, not
SG, by the build's deliberate dispatch convention).

### Deviation C: A dead `loadstep_defs` Series RLC R block already engages 248 MW at Bus 14

`build_kundur_cvs_v3.m` lines 154-157:

```matlab
loadstep_defs = {
    'LoadStep_bus14', 14, 'bus14';   % paper Bus 14 ≈ v3 ESS bus 14 (near ES3)
    'LoadStep_bus15', 15, 'bus15';   % paper Bus 15 ≈ v3 ESS bus 15 (near ES4)
};
```

Implementation lines 369-388 — a `Series RLC Branch` (R-only) per bus:

```matlab
add_block('powerlib/Elements/Series RLC Branch', [mdl '/' name], ...
    'BranchType', 'R', ...
    'Resistance', sprintf('Vbase_const^2 / max(LoadStep_amp_%s, 1e-3)', bus_label));
```

Default amps (build script lines 240-248 + 990-998):

```matlab
% Bus 14: amp_default = 248e6 (Task 2: LS1 pre-engaged)
% Bus 15: amp_default = 0.0   (LS2 not engaged at IC)
```

This is **the very block the Option G plan calls "compile-frozen
LoadStep R-block (D-T2 dead)"**. It **already contributes 248 MW load
at Bus 14 in the current model**. The IC was derived *with this R block
engaged*. So:

- Current model state: 248 MW absorbed at Bus 14 via Series RLC R
- Plan §1.1.1 wants to ADD a *new* Switch + R-bank with default state =
  closed (engaging another 248 MW at Bus 14)

→ If executed literally, Day 1 build will produce **2 × 248 MW = 496 MW
at Bus 14**, double-counting the load. The IC will become inconsistent
with the model topology, and NR will need re-derive against the new
double-loaded topology.

The plan §1.1.1 docstring **says** "replaces the compile-frozen LoadStep
R-block (D-T2 dead)", but the build edits in the plan only **add** —
they do not remove the old `loadstep_defs` block.

→ Plan §1.1 needs an explicit "delete old loadstep_defs build loop"
section before §1.1.1, or the new Switch + R-bank must use
`default_state='open'` at Bus 14 (which would contradict the alt (c')
Phase 1 design that hinges on Bus 14 closed-at-IC).

---

## 3. Resolution options (operator decision required)

### Option AA — Replace, not add (recommended)

Execute Day 1 with these *additional* edits to plan §1.1:

1. **Delete** existing `loadstep_defs` definition (lines 154-157) +
   build loop (lines 369-388 + 405-470 trip CCS, dependent) + runtime
   seeds (lines 240-248 + 990-998 + 1003-1006 trip-amp seeds) +
   register-loop (lines 885-897 + 892-897 trip register).
2. **Add** new `switch_r_load_defs` per plan §1.1.1, default state per
   plan §1.3 alt (c') Phase 1.
3. **NR re-derive UNNECESSARY** because the new R-bank closed-default at
   248 MW is electrically equivalent to the old Series RLC R at 248 MW
   (same resistance value, same bus, same wiring), so the existing IC
   `ls1_preengaged` is still valid.
4. Bus 15 IC stays at 0 MW load (LS2 default off in both old and new
   designs).

Cost: +0.5 day to plan §1.1 work (just deletes + replacements;
the deletes are mechanical because the old `loadstep_defs` is
self-contained).
Benefit: avoids double-count, avoids NR re-derive, avoids §3.2
mis-specified acceptance.

### Option BB — Add and re-derive

Keep the old `loadstep_defs` block AND add the new Switch + R-bank with
`default_state='open'` at Bus 14 (the new R-bank is dispatch-only, not
default-engaged). Then plan §3 NR re-derive runs *only* if Day 1 sim
shows the old block has somehow gone "live" (it won't — it's
compile-frozen).

Cost: 0 day extra (no deletes), but the model topology has a dead block
at Bus 14 and a new live block at Bus 14, both 248 MW capable. Risk:
confusing future readers; the dead block obscures intent.

This option also breaks the alt (c') Phase 1 design: the plan wanted
Bus 14 *closed at IC* in the new R-bank for paper-LS1 trip semantics.
With Option BB, Bus 14's IC-engaged 248 MW comes from the *old* Series
RLC R (compile-frozen, can't open at runtime), which means the paper-LS1
trip dispatch (open the breaker → R disengages) is **physically
impossible**; the breaker on the new R-bank only adds another 248 MW.

→ Option BB does not actually deliver paper-LS1 semantics. **Reject**.

### Option CC — Delete the old block; rely on R-bank as the only Bus 14 load

Same as Option AA but more aggressive: also delete the dead Trip CCS
chains at Bus 14/15 (lines 405-470), since they were Phase A++ dormant
patterns. Trim the build script of dead code while we're in there.

Cost: +1 day (more deletes + register-loop fix). Benefit: build script
becomes substantially cleaner (~80 lines removed); Day 0 §3
"prune dormant Bus 7/9 CCS chains" side-task can be folded in too.

---

## 4. Recommendation

**Adopt Option AA for Day 1**, with Option CC's CCS-chain deletes as a
*concurrent* cleanup pass (separate commit, after Option G build proves
green).

Rationale:
- Option AA is the minimum change required to make the plan's alt (c')
  Phase 1 design actually work (no double-count).
- Option CC's extra cleanup is "nice to have" and can land in a separate
  commit, reducing risk of the Day 1 commit doing too much.
- The Day 0 dry-run notes already flagged that pruning dead Bus 7/9 CCS
  chains *also* halves the future B-path cost, so doing the CCS prune
  is high-value but timing-flexible.

**Plan §3 acceptance criteria need updating** to reflect:
- vsg_pm0_pu CHANGES (ESS absorbs the +248 MW = 25 MW per ESS)
- sg_pm0_sys_pu UNCHANGED (paper dispatch preserved)
- aggregate residual ≈ 1e-13 (already there; closure already valid)

But **the actual NR re-derive is unnecessary under Option AA** — the IC
already represents the post-Option-G state. Step 3 becomes a *verify*
step (assert no change vs current IC), not a *re-derive* step.

---

## 5. SG capacity check (formal, per plan §0.5)

```
Each SG capacity (paper Sec.IV-A) = 7 GVA / 100 MVA = 70.0 sys-pu
Pre-Option-G dispatch (current IC) = [7.000, 7.000, 7.190] sys-pu
Each SG headroom ≈ 70 - 7 = 63 sys-pu (huge)
```

Even if the +248 MW were redirected fully to SG (it is not — ESS
absorbs it instead), each SG would only need +0.83 sys-pu, well under
capacity.

✓ **PASS** — feasibility-wise, alt (c') Phase 1 is well within SG
capacity. The ESS-absorption convention happens to be tighter (each ESS
is +0.25 sys-pu absorbing, vs ESS individual capacity 100 MVA = 1.0 sys-pu),
but still 75 % headroom per ESS.

---

## 6. Audit verdict

| precondition | plan expected | actual | status |
|---|---|---|---|
| `load_defs` no Bus 14/15 | yes | yes | ✓ |
| SG capacity for +248 MW | yes | yes (and abundant) | ✓ |
| IC at "pre-Option-G" state (no Bus 14 load) | implicit | **NO — IC is already `ls1_preengaged`** | ✗ but informative |
| New R-bank can be added without double-count | implicit | **NO unless old `loadstep_defs` is deleted** | ✗ requires plan §1.1 augmentation |
| Plan §3 NR re-derive expectation (SG absorbs +248 MW) | yes | NO (ESS absorbs) | ✗ plan §3.2 mis-specified |

**Overall:** alt (c') Phase 1 is **feasible** but plan **needs a small
augmentation to §1.1 (delete old loadstep_defs)** and a **rewrite of
§3.2 acceptance** before Day 1 starts. The augmentation is mechanical
(~30 min of plan editing) and does not change the plan's overall
strategy or risk profile.

**Recommendation to operator:** approve plan with these augmentations,
then proceed Day 1 with Option AA (delete-then-add).
