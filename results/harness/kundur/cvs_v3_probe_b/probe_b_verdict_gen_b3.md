# Probe B sign-pair experiment verdict

**Generated:** probe_b_pos_gen_b3.json vs probe_b_neg_gen_b3.json

## Falsification matrix

| Hypothesis | Status | Evidence |
|---|---|---|
| **H1** within-run distinct sha256 (4 agents) | PASS (4 distinct) | see hash list below |
| **H1b** cross-run no aliased hash | PASS (no shared hash) | see hash list |
| **H2** at least 1 agent responds to mag sign (>1e-3 Hz) | PASS (dispatch firing) | see (|nadir_diff|+|peak_diff|) below |
| **H3** r_f_local distinct across agents within run | PASS | see r_f_local_eta1 below |
| **H4** more than 1 agent responds (gradient non-degenerate) | PASS (multiple agents excited) | see agents_responding count below |

## Raw evidence

```
pos_hashes = ['081f12be240fe3fd', '85d8b5cf0666f92c', '96f8672a546308f6', 'd3fa1c249eb97bff']
neg_hashes = ['ae0715eb01e84c38', 'a92c8eab3dbd397b', 'e82fd58f4ba454eb', '9cb48ede1fdf261e']
pos_nadir = [-0.004361280604414652, -0.0005390959532447503, -0.17509047355473428, -0.02713633019809647]  pos_peak = [0.004133189207644605, 0.0006189101408704545, 0.1700036659290527, 0.024747032720651152]
neg_nadir = [-0.0043620809212718825, -0.0005432558176754476, -0.1610309833419643, -0.01731291832934856]  neg_peak = [0.004132752212437918, 0.0006169917551090975, 0.16351524163501496, 0.017273082129576345]
per-agent (|nadir_diff|+|peak_diff|) = [1.2373120639175283e-06, 6.078250192054213e-06, 0.020547914506807707, 0.017297362459822718]
agents_responding (|diff| > 1e-3 Hz) = 2/4
pos_r_f_local_eta1 = [-2.421368002704577e-06, -5.698675300183291e-05, -5.812515049097203e-05, -5.739039887023544e-05]
neg_r_f_local_eta1 = [-1.002682860841846e-06, -6.065205324155776e-05, -5.8714348158224764e-05, -5.975491514510727e-05]
```

## Verdict

**STOP-VERDICT: PASS** — measurement layer separated AND multiple 
agents respond. Network coupling distributes the disturbance 
across the 4 ESS as expected.