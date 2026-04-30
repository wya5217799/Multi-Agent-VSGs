# Probe E sign-pair verdict — Option E CCS at Bus 9

**Generated:** probe_e_pos_b9.json vs probe_e_neg_b9.json
**Bus:** 9
**|mag|:** 0.500 sys-pu
**Thresholds:** PASS >= 0.050 Hz, ABORT < 0.010 Hz

## Falsification matrix

| Hypothesis | Status | Evidence |
|---|---|---|
| H_E_strong (>= 1 agent diff >= 0.050 Hz) | FAIL | max diff = 0.0013 Hz |
| H_E_marginal (>= 1 agent diff in [0.010, 0.050)) | N/A | see per-agent diffs below |
| H_E_abort (all agents diff < 0.010) | PASS (-> abort Option E) | max diff = 0.0013 Hz |

## Raw evidence

```
bus = 9, |mag| = 0.500
pos_nadir = [-0.0043616822412384515, -0.0005412981967933828, -0.0017542653621305249, -0.008293319969276958]
neg_nadir = [-0.004361685480847033, -0.0005412497853019005, -0.0017894133883922247, -0.007672708880979151]
pos_peak = [0.00413311505534919, 0.0006179989844978806, 0.002375884447336496, 0.009472966873902422]
neg_peak = [0.0041331111084952354, 0.0006179348482238112, 0.002401304183796693, 0.008820264782072318]
per-agent (|nadir_diff|+|peak_diff|) = ['0.0000', '0.0000', '0.0001', '0.0013'] Hz
agents PASS (>= 0.050 Hz) = 0/4
agents MARGINAL ([0.010, 0.050) Hz) = 0/4
agents under noise floor (< 0.010 Hz) = 4/4
```

## Verdict

**STOP-VERDICT: ABORT** — All 4 agents have diff < 0.010 Hz (max = 0.0013). CCS at Bus 9 produces noise-floor signal even at the paper-Fig.3 load center. Option E ABORT — either electrical attenuation (admittance) or Phasor solver phase mismatch is killing the disturbance. F4 v3 +18% remains the project ceiling under current architecture.