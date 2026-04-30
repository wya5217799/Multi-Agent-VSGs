# Probe E sign-pair verdict — Option E CCS at Bus 7

**Generated:** probe_e_pos_b7.json vs probe_e_neg_b7.json
**Bus:** 7
**|mag|:** 0.500 sys-pu
**Thresholds:** PASS >= 0.050 Hz, ABORT < 0.010 Hz

## Falsification matrix

| Hypothesis | Status | Evidence |
|---|---|---|
| H_E_strong (>= 1 agent diff >= 0.050 Hz) | FAIL | max diff = 0.0007 Hz |
| H_E_marginal (>= 1 agent diff in [0.010, 0.050)) | N/A | see per-agent diffs below |
| H_E_abort (all agents diff < 0.010) | PASS (-> abort Option E) | max diff = 0.0007 Hz |

## Raw evidence

```
bus = 7, |mag| = 0.500
pos_nadir = [-0.0043795850969585715, -0.0005412925298875493, -0.0017719759389744905, -0.007983726020116544]
neg_nadir = [-0.004673330636123518, -0.0005412560654949328, -0.0017719731590259968, -0.007983701506819596]
pos_peak = [0.004296040219553543, 0.0006179925981730783, 0.002388788176410639, 0.009147893355920811]
neg_peak = [0.003901638073655622, 0.0006179421532692686, 0.002388784225637597, 0.009147853051028054]
per-agent (|nadir_diff|+|peak_diff|) = ['0.0007', '0.0000', '0.0000', '0.0000'] Hz
agents PASS (>= 0.050 Hz) = 0/4
agents MARGINAL ([0.010, 0.050) Hz) = 0/4
agents under noise floor (< 0.010 Hz) = 4/4
```

## Verdict

**STOP-VERDICT: ABORT** — All 4 agents have diff < 0.010 Hz (max = 0.0007). CCS at Bus 7 produces noise-floor signal even at the paper-Fig.3 load center. Option E ABORT — either electrical attenuation (admittance) or Phasor solver phase mismatch is killing the disturbance. F4 v3 +18% remains the project ceiling under current architecture.