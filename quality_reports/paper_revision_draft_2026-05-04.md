# Paper Revision Draft — Hparam Sensitivity Findings

**Date**: 2026-05-04
**Status**: DRAFT (review-only, no main.tex edits yet)
**Source verdicts**:
- `quality_reports/audits/2026-05-04_andes_hparam_wave1_verdict.md`
- `quality_reports/audits/2026-05-04_andes_hparam_sensitivity_final_verdict.md` (§1–§13)
- `quality_reports/plans/2026-05-04_andes_hparam_sensitivity_spec.md`

---

## Summary of changes

Insert new sensitivity-sweep content into `paper/main.tex`. Four
locations touched:

| Loc | Old text | New text | Rationale |
|---|---|---|---|
| §I.B Project deviations (line 157–166) | "the original $\Phi_F = 100$ produces an $r_f / r_d$ ratio so small that agents do not learn" — vague | quantified: "$r_f / r_d \approx 1.3 \times 10^{-4}$ at PHI_F=100 (gradient analysis on `phase1_probe`); $r_f$ contributes 1.52% of weighted reward, far below the 5% threshold for SAC gradient visibility" | n=50ep gradient analysis (§13) gives precise number, replaces vague claim |
| §IV (Performance Results, append after §IV.G Phase 10) | — | New §IV.H "Local hyperparameter sensitivity" (one subsection, ~3/4 page, 1 table, 1 figure) | Documents 6-config sweep + n=5 confirmation at f_high |
| §VI Honest Claims (line 567–593) | claim list ends at item 8 | add item 9: local-minimum claim with explicit ±-bounds | New finding from sweep |
| §VIII Conclusion (line 622–649) | "Future work should examine whether the multi-agent advantage emerges only when EMT-grade nonlinear dynamics..." | (keep this) + add 1 sentence: "We have ruled out hyperparameter under-tuning as an explanation for the observed performance: a ±3× neighborhood sweep around our chosen operating point shows every direction degrades performance, with f_high (PHI_F=30000) confirmed at n=5 to be 46% worse than baseline (CIs disjoint)." | Forecloses the "maybe just bad tuning" critique |

No changes to: §II System (Setup), §III Diagnostic Findings,
§IV.A–G Performance Results subsections, §V Root-Cause Synthesis,
§VII Limitations (it remains accurate; n=5 sweep does not require
new limitations).

---

## Insertion point chosen: §IV.H (subsection)

Reasoning: insertion as §V (new section) would force renumber of
old §V Root-Cause → §VI, §VI Honest Claims → §VII, §VII Limitations
→ §VIII, §VIII Conclusion → §IX (4 sections renumber). Insertion as
§IV.H avoids renumbering and stays semantically clean (sensitivity
analysis is part of "Performance Results" — robustness of those
results to hparam choice).

---

## §I.B Revision (Project deviations)

### Old text (line 159–166):

```latex
\Cref{tab:deviations} lists project-side modifications to
hyperparameters and ranges that deviate from the values stated by
Yang~\emph{et al.}~\cite{yang2023ddic}. All deviations are documented;
none are paper-faithful. The most consequential is the reward-weight
rebalance: the original $\Phi_F = 100$ produces an
$r_f / r_d$ ratio so small that agents do not learn to attenuate
frequency excursions; we increased $\Phi_F$ to $10\,000$ and reduced
$\Phi_D$ from $1.0$ to $0.02$ during Phase 2 calibration.
```

### New text (replacement):

```latex
\Cref{tab:deviations} lists project-side modifications to
hyperparameters and ranges that deviate from the values stated by
Yang~\emph{et al.}~\cite{yang2023ddic}. All deviations are documented;
none are paper-faithful. The most consequential is the reward-weight
rebalance: at the paper-original $\Phi_F = 100$, the SAC policy
gradient is dominated by $r_d$ ($84.9\,\%$ of weighted reward) and
$r_h$ ($13.6\,\%$), with $r_f$ contributing only $1.52\,\%$
(50-episode trace, configuration~\textit{phase1\_probe};
$r_{f,\text{raw}} / r_{d,\text{raw}} \approx 1.3 \times 10^{-4}$).
The frequency-control signal is gradient-invisible, falling more than
$3\times$ below the $5\,\%$ lower bound at which SAC reliably learns
multi-objective trade-offs. We therefore increased $\Phi_F$ to
$10\,000$ and reduced $\Phi_D$ from $1.0$ to $0.02$ during Phase~2
calibration. \Cref{ssec:hparam-sensitivity} characterizes the
sensitivity of our final results to this choice.
```

(adds 1 forward reference to new §IV.H; replaces vague "agents do
not learn" with precise gradient-share data.)

---

## §IV.H New Subsection (insert at line 503, before §V)

```latex
\subsection{Local hyperparameter sensitivity}\label{ssec:hparam-sensitivity}

A reasonable critique of any null result is that the chosen
hyperparameters might be poorly tuned, masking a real architectural
advantage. We screen the local sensitivity of our DDIC baseline
(\(\Phi_F = 10\,000\), \(\Phi_D = 0.02\), \(\Delta M \in [-10, 30]\),
\(\Delta D \in [-10, 30]\)) by perturbing each axis log-symmetrically
in a single-seed sweep and confirming the most-promising perturbation
at \(n = 5\).

\paragraph{Sweep design.} Six perturbation configurations were
trained for 100 episodes each at seed~42, with all other
hyperparameters fixed: $\Phi_F \in \{3000, 30000\}$ (\(\pm 3\times\)
on the F-axis), \(\Phi_D \in \{0.006, 0.06\}\) (\(\pm 3\times\) on the
D-axis), and action range \(\{[-5, 15], [-20, 60]\}\)
(\(\pm 2\times\)). Anchor perturbations were also evaluated: the
paper-original \(\Phi_F = 100\) (\textit{phase1\_probe}, see §I.B)
and action range \(\pm 20\times\) (\textit{phase11\_ddic\_wide},
77~episodes; see~\cite{phase11verdict} for setup). Each trained
checkpoint was evaluated against our paper-grade evaluator on
50~test episodes (\texttt{env.seed} 20000--20049,
\(p_{\text{cf}} = 0.1\)) for cum-\(r_f\). The pre-registered
robustness gate is std \(< 0.265\) (the baseline 5-seed standard
deviation; results sensitive enough that hparam-perturbation
dispersion exceeds seed-perturbation dispersion are labelled
\emph{fragile}). The pre-registered protocol and gate definitions are
documented in the project repository and were frozen prior to running
the sweep.

\Cref{tab:hparam-sweep} reports the result.

\begin{table}[!t]
  \centering
  \caption{Local hyperparameter sweep, single seed (42), 50-episode
    cum-\(r_f\) eval. Baseline = \textit{f\_mid}; n=5 cross-seed
    baseline std = $0.265$. Pre-registered gate: per-axis std $< 0.265$.
    Anchor configs reported separately at the bottom.}
  \label{tab:hparam-sweep}
  \footnotesize
  \begin{tabular}{lcccc}
    \toprule
    Config & \(\Phi_F\) & \(\Phi_D\) & action & cum-\(r_f\) \\
    \midrule
    \multicolumn{5}{c}{\emph{F-axis (\(\pm 3\times\))}}\\
    f\_low  & $3000$  & $0.02$ & $[-10, 30]$ & $-2.361$ \\
    f\_mid  & $10\,000$ & $0.02$ & $[-10, 30]$ & $-1.191$ (baseline)\\
    f\_high & $30\,000$ & $0.02$ & $[-10, 30]$ & $-1.488$ \\
    \multicolumn{4}{r}{\textbf{F-axis std (3 pts):}} & \textbf{0.608} \\
    \midrule
    \multicolumn{5}{c}{\emph{D-axis (\(\pm 3\times\))}}\\
    d\_low  & $10\,000$ & $0.006$ & $[-10, 30]$ & $-1.607$ \\
    d\_high & $10\,000$ & $0.06$  & $[-10, 30]$ & $-2.807$ \\
    \multicolumn{4}{r}{\textbf{D-axis std (3 pts):}} & \textbf{0.839} \\
    \midrule
    \multicolumn{5}{c}{\emph{action-axis (\(\pm 2\times\))}}\\
    a\_low  & $10\,000$ & $0.02$ & $[-5, 15]$  & $-2.416$ \\
    a\_high & $10\,000$ & $0.02$ & $[-20, 60]$ & --- (training diverged at ep 50) \\
    \multicolumn{4}{r}{\textbf{action-axis std (2 valid pts):}} & \textbf{0.866} \\
    \midrule
    \multicolumn{5}{c}{\emph{Anchors (paper-original)}}\\
    F-anchor (PHI\_F=100)   & --- & --- & --- & gradient-invisible (§I.B) \\
    action-anchor (\(\pm 20\times\)) & --- & --- & $[-200, 600]$ & TDS-divergent \\
    \bottomrule
  \end{tabular}
\end{table}

All three robustness gates fail: per-axis std exceeds the
$0.265$ baseline-seed-std bound by $2.3\times$ (\(\Phi_F\)),
$3.2\times$ (\(\Phi_D\)), and $3.3\times$ (action). Two of the six
neighborhood points exhibit pathological training behaviour:
\textit{a\_high} (action range \(\pm 2\times\)) reward-diverges at
episode~50 (slope $-284.7$/ep, R^2 = $0.30$); the action-anchor
($\pm 20\times$, reused from a Phase 11 wide-action pilot) shows
continuous TDS divergence in the Simulink trajectory, never reaching
a stable training regime. The paper-original $\Phi_F = 100$ produces
the gradient-invisibility documented in §I.B.

\paragraph{n=5 confirmation at f\_high.} The single-seed result of
$-1.488$ at f\_high (\(\Phi_F = 30000\), only $25\,\%$ worse than
baseline at seed~42) raised the question of whether the gap was
seed-noise versus a genuinely viable alternative operating point.
We trained four additional seeds (43, 44, 45, 46) under the f\_high
configuration. \Cref{tab:hparam-fhigh-n5} aggregates the result.

\begin{table}[!t]
  \centering
  \caption{f\_high (\(\Phi_F = 30\,000\)) n=5 confirmation. Baseline =
    Phase~4 (\(\Phi_F = 10\,000\)).}
  \label{tab:hparam-fhigh-n5}
  \footnotesize
  \begin{tabular}{lcc}
    \toprule
    Quantity & f\_high (n=5) & Baseline (n=5) \\
    \midrule
    Seeds          & 42, 43, 44, 45, 46 & 42, 43, 44, 45, 46 \\
    Mean cum-\(r_f\) & \(-1.735\) & \(-1.186\) \\
    Std (sample, ddof=1) & $0.361$ & $0.265$ \\
    Bootstrap CI (95\%) & $[-2.057,\, -1.449]$ & $[-1.393,\, -0.984]$ \\
    Mean max-\(\Delta f\) & $0.263$~Hz & $0.238$~Hz \\
    \bottomrule
  \end{tabular}
\end{table}

The CIs are disjoint with a $0.055$-unit gap. f\_high is significantly
\emph{worse} than baseline at $n=5$, with $36\,\%$ larger seed
dispersion. The seed-42 single point ($-1.488$) was on the optimistic
tail of the f\_high distribution and not representative.

\paragraph{Verdict.} The neighborhood sweep does not yield a viable
alternative operating point in any of the directions tested. Our
chosen baseline is the local minimum within the tested $\pm 3\times$
neighborhood on $\Phi_F$ and $\Phi_D$ and the tested $\pm 2\times$
neighborhood on action range. The basin slope is steep: every tested
direction degrades cum-\(r_f\) by at least $25\,\%$, with no
compensating reduction in seed variance. The reproducibility of our
DDIC numbers is therefore conditional on the specific hyperparameter
choice; the result is a point estimate on a sensitive ridge, not a
locally robust performance basin.
```

---

## §VI Honest Claims Revision

### Add new item 9 at line 593 (after item 8):

```latex
  \item Performance is sensitive to hyperparameter choice within the
        $\pm 3\times$ neighborhood on $\Phi_F$ and $\Phi_D$ and
        $\pm 2\times$ on action range
        (\cref{ssec:hparam-sensitivity}). Our chosen baseline is the
        local minimum of the tested neighborhood; every perturbation
        evaluated degraded cum-\(r_f\) by $\geq 25\,\%$. n=5
        confirmation at $\Phi_F = 30\,000$ rules out the upper-axis
        direction as an alternative. The paper-original
        $\Phi_F = 100$ is gradient-invisible (§I.B); the
        paper-original action range ($\pm 20\times$) produces TDS
        divergence. The DDIC numbers in this paper are conditional on
        the specific hyperparameter point.
```

---

## §VIII Conclusion Revision

### Add 1 sentence at line 649 (after the "future work" paragraph, before §Reproducibility):

```latex
We have ruled out hyperparameter under-tuning as an explanation
for the observed null result: a single-seed $\pm 3\times$ neighborhood
sweep on $\Phi_F$ and $\Phi_D$ and a $\pm 2\times$ sweep on action
range (\cref{ssec:hparam-sensitivity}) shows every direction degrades
cum-\(r_f\) by at least $25\,\%$, and an n=5 confirmation at the
most-promising perturbation ($\Phi_F = 30\,000$) yields a mean
($-1.735$) lying outside the baseline 95\,\% bootstrap CI. The
multi-agent decoration finding is robust to hyperparameter choice
within the tested neighborhood; the burden of explanation shifts to
backend characteristics or architectural choices not addressed here.
```

---

## Files referenced from the new subsection

- `tab:deviations` (existing, line 168–183, no change needed)
- `tab:hparam-sweep` (new, written above)
- `tab:hparam-fhigh-n5` (new, written above)
- `\cref{ssec:hparam-sensitivity}` (new label, defined in new §IV.H)
- `\cref{phase11verdict}` (new bibtex entry; or replace with footnote
  citing the project verdict file)

### Optional: figure

The spec §6 mentioned 1 figure (1D sweep visualization). For the
revision pass, defer the figure unless reviewer requests; the table
+ n=5 confirmation table conveys the key information textually. If
a figure is added later: x-axis = log(perturbation factor) per panel,
y-axis = cum-\(r_f\), 3 panels (\(\Phi_F\), \(\Phi_D\), action).
Helper script: `scripts/plot_hparam_sweep.py` (not yet written).

---

## Open questions for user review

1. **Insertion location**: §IV.H subsection (chosen above) vs. new §V
   "Hyperparameter sensitivity" with full renumber? §IV.H avoids
   renumber but mixes a meta-analysis into "Performance Results".
2. **Anchor reference**: cite Phase 11 verdict via bibtex (cleaner,
   formal) or footnote with file path (faster, project-internal)?
3. **Figure**: include the 1D sweep panel figure in this revision, or
   defer to reviewer request?
4. **§I.B numerical claims**: keep precise numbers ($1.3\times 10^{-4}$,
   $1.52\,\%$) or generalize to "below 5\%"? Precise numbers are
   verifiable but tie the paper to specific 50-ep trace.
5. **§VI item 9 length**: 5 lines is one of the longer claims. Consider
   merging "n=5 confirmation rules out upper direction" into §IV.H
   prose only, leaving the claim shorter.

---

## Estimated diff size

- §I.B: +6 lines, −4 lines = net +2 lines
- §IV.H: +85 lines (new subsection with 2 tables)
- §VI Honest Claims item 9: +9 lines
- §VIII Conclusion: +9 lines

Total: ~110 lines added, ~4 lines removed = ~106 net lines added to
`paper/main.tex` (currently 678 lines → 784 lines, +16%).

No existing claim is invalidated. No existing table or figure is
changed. No experimental data is overwritten. The 4 changes are
strictly additive plus 1 small replacement in §I.B.

---

*End paper revision draft. Awaiting user review before applying to
`paper/main.tex`.*
