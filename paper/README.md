# IEEE-format Reproduction Paper

LaTeX source for the manuscript:

> **An Honest Reproduction of Multi-Agent SAC for Virtual Synchronous
> Generator Inertia and Damping Control: Evidence That the Multi-Agent
> Framework Is Decorative on a Phasor-Based Backend**

## Files

| File | Purpose |
|---|---|
| `main.tex` | Main manuscript (IEEEtran journal class) |
| `refs.bib` | Bibliography (Yang 2023, ANDES, SAC, VSG references) |
| `figures/` | 5 PNGs copied from `results/andes_predraft_figures/` |
| `Makefile` | Build automation |

## Build

```bash
cd paper
make           # produces main.pdf
make view      # open PDF
make clean     # remove build artifacts
```

Requires `pdflatex` + `bibtex`. Tested with TeX Live 2023.

## Source narrative

The paper is condensed from:

- **Predraft**: `quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft.md` (505 lines)
- **9 audit docs**: `quality_reports/audits/2026-05-04_*.md`
- **Numeric sources**: `results/andes_eval_paper_grade/n5_aggregate.json`, `results/phase9_shared_3seed_reeval_summary.json`, `results/andes_warmstart_seed*/eval_paper_grade.json`, `results/harness/kundur/agent_state/agent_state_phase4_seed{42,43,44}_commfail01.json`

All numbers in the paper are traceable to one of these source files;
see `[FACT]` tags in the predraft.

## Key contributions

1. **Honest reproduction** of Yang \emph{et al.} TPWRS 2023 DDIC on
   ANDES Kundur 4-bus
2. **3 same-class evaluation bug fixes** (`comm_fail_prob` mismatch
   between training and eval, inflating headline numbers ~6\%)
3. **DECORATIVE\_CONFIRMED**: shared-parameter SAC matches DDIC at
   1/5 budget --- multi-agent framework is decorative on this system
4. **WARMSTART\_WORSE null result**: shared-policy init redistributes
   dominance without improving the mean --- imbalance is structural
5. **Statistical TIED at n=5**: bootstrap CIs overlap;
   adaptive baseline indistinguishable from DDIC

## Status

Pre-submission draft. Ready for circulation; final formatting pass
(IEEE conference vs.\ journal class, page-count adjustment) to be
done before submission.
