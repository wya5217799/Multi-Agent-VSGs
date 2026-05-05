# Devil's Advocate Re-Review — Round 2

**Paper:** Wei, "Backend-Dependent Performance of Multi-Agent SAC for Virtual Synchronous Generator Inertia and Damping Control: A Reproduction Study on the ANDES Kundur Four-Bus System" (commit d4c0c6c)
**Reviewer role:** Devil's Advocate (Round 2 re-verification)
**Date:** 2026-05-05
**Final Severity:** CONCERNS RESOLVED
**Recommendation:** Accept (DA no longer blocks)

---

## Section 1: CRITICAL #1 Verification — Confounded Experimental Design

**Verdict: RESOLVED.**

The author rewrote section V.A (lines 693–765) into three explicit confounding hypotheses (backend linearity, reward-weight rescaling, action-range narrowing), each with its own paragraph stating the prediction and explicitly noting it cannot be tested with available data. The "Most defensible reading" paragraph (lines 758–765) correctly scopes the finding to "the joint backend–reward–range configuration tested here, with backend linearity being one plausible but unisolated contributor." Claim 4 (lines 823–833) attributes the ratio reversal to the joint effect of three uncontrolled factors. The title removes "Decorative" in favor of "Backend-Dependent Performance." The paper no longer makes a single-cause attribution claim.

The mention of "backend linearity" as "plausible" is appropriately hedged ("unisolated") and does not constitute a backdoor reinstatement of the old framing.

---

## Section 2: CRITICAL #2 Verification — n=3 Underpowered

**Verdict: RESOLVED.**

### Numerical verification against JSON

| Quantity | JSON value | Paper reports | Match? |
|---|---|---|---|
| Shared-param n=5 mean | −1.02765 | −1.028 | YES |
| Shared-param n=5 std | 0.13585 | 0.136 | YES |
| Bootstrap CI lo | −1.1250 | −1.125 | YES |
| Bootstrap CI hi | −0.9173 | −0.917 | YES |
| DDIC n=5 mean | −1.1863 | −1.186 | YES |
| DDIC n=5 std | 0.2649 | 0.265 | YES |
| DDIC CI | [−1.3932, −0.9841] | [−1.393, −0.984] | YES |
| Delta % | 13.37% | 13.4% | YES |
| Std reduction | 48.7% | 48% | YES |
| CI overlap | true | "overlapping" | YES |

All per-seed values are present in the JSON (seeds 42–46), each with individual CIs. The aggregate computation is correct. The paper text accurately reflects the raw data.

Section V.C Triangulation (lines 794–809) correctly states "matched n=5" and acknowledges the warmstart pilot remains at n=3 as "the smallest-sample piece of the triangulation." Section VI Limitations (lines 873–879) documents this residual.

---

## Section 3: New CRITICAL Issues — None Found

Two MINOR text bugs from incomplete revision propagation:

1. **Claim 5 (line 839):** Still says "at n=3" — should read "at n=5" to match Table V and section IV.G. Trivial copyedit.
2. **Conclusion (lines 961–962):** Calls for extending Phase 9 to n=5 as future work, despite this already being completed in the current revision. Stale text. Trivial copyedit.

Neither constitutes a substantive claim problem. Both are editorial oversights.

No new overclaiming detected. The "DECORATIVE_CONFIRMED at n=5" label is supported by the overlapping CIs at matched sample size. The direction of the trend (shared-param marginally better) is correctly labeled as a trend, not a claim.

Legacy figure tags [Legacy p_cf=0.0] are applied consistently to Figs 2, 4, 5 and absent from Figs 1, 3 (which use post-fix data).

---

## Section 4: Residual MAJOR Issues (M1–M4)

| Issue | Status | Notes |
|---|---|---|
| M1 ("1/5 budget" misleading) | **ADDRESSED** | Replaced with "1/4 network parameters" + explicit "gradient-update count is comparable" (line 504–507) |
| M2 (2D sensitivity sweep) | **Acknowledged** | Listed as limitation (lines 897–904); Tier-2 item not blocking |
| M3 (adaptive 5x5 K-grid) | **Acknowledged** | Listed as limitation (lines 892–896); Tier-2 item not blocking |
| M4 (incommensurable ratio) | **Partially addressed** | Text at lines 417–421 + full section V.A scope the comparison; table still shows the ratio but in context of surrounding caveats |

---

## Section 5: Final Verdict

**Both CRITICAL issues from round 1 are RESOLVED.**

- CRITICAL #1: section V.A rewrite + title change + Claim 4 rewrite successfully downgrade from single-cause attribution to joint-configuration-conditional finding.
- CRITICAL #2: Phase 9 extended to matched n=5 with verified JSON data. All numbers check out.

**No new CRITICAL issues introduced.** Two trivial text inconsistencies (stale "n=3" and stale "future work" reference) noted for copyediting.

**Per IRON RULE #4, the Devil's Advocate no longer blocks Accept.**

The paper now makes appropriately scoped claims, backed by matched-sample-size evidence, with explicit acknowledgment of confounding and limitations. The "architecturally redundant on the ANDES phasor-equilibrium backend" framing is defensible given the triangulation evidence at n=5.

**Recommended copyedits before final:**
1. Line 839: change "at n=3" to "at matched n=5 seeds"
2. Lines 961–962: remove or update the sentence calling for Phase 9 n=5 extension (already done)

---

*End DA re-review. Decision can proceed to Accept (with above copyedits as trivial condition).*
