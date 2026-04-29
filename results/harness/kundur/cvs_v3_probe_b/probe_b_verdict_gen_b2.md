# Probe B sign-pair experiment verdict

**Generated:** probe_b_pos_gen_b2.json vs probe_b_neg_gen_b2.json

## Falsification matrix

| Hypothesis | Status | Evidence |
|---|---|---|
| **H1** within-run distinct sha256 (4 agents) | PASS (4 distinct) | see hash list below |
| **H1b** cross-run no aliased hash | PASS (no shared hash) | see hash list |
| **H2** at least 1 agent responds to mag sign (>1e-3 Hz) | PASS (dispatch firing) | see (|nadir_diff|+|peak_diff|) below |
| **H3** r_f_local distinct across agents within run | PASS | see r_f_local_eta1 below |
| **H4** more than 1 agent responds (gradient non-degenerate) | FAIL (single-agent gradient — DEGENERATE) | see agents_responding count below |

## Raw evidence

```
pos_hashes = ['f5f878e865ca6fca', 'fcd6d753f3eb73ab', '286de958a8c0fd61', 'ff8f4d9240368721']
neg_hashes = ['f0651ebb6b676351', '10873e3906dc369c', '3a388e6c0a65c523', '6122cb50ca74c8e5']
pos_nadir = [-0.08472932356543006, -0.0005410371258063318, -0.001772163511454261, -0.007984111412889794]  pos_peak = [0.15773689678497682, 0.000618652446293666, 0.0023896917773491566, 0.009148838722905506]
neg_nadir = [-0.14902925167176728, -0.0005420688203749968, -0.0017714734153240208, -0.007983633888236641]  neg_peak = [0.12536901260727928, 0.0006172035518225982, 0.0023876671223388435, 0.0091465895623144]
per-agent (|nadir_diff|+|peak_diff|) = [0.09666781228403476, 2.4805890397328056e-06, 2.7147511405534175e-06, 2.7266852442586753e-06]
agents_responding (|diff| > 1e-3 Hz) = 1/4
pos_r_f_local_eta1 = [-2.6091124991246287e-05, -2.5541900834475542e-05, -2.1275229567489058e-07, -2.585708813854925e-05]
neg_r_f_local_eta1 = [-2.5666906480126274e-05, -2.558249322615197e-05, -2.127823577608802e-07, -2.5973348514474208e-05]
```

## Verdict

**STOP-VERDICT: MEASUREMENT_OK_GRADIENT_DEGENERATE** — measurement 
layer is sound (4 distinct sha256 traces, sign-asymmetric per-agent 
response, distinct r_f_local). However, only 1 agent shows non-
trivial response (>1e-3 Hz) to the disturbance; the other 3 see 
noise-floor signal. This confirms the audit R5 hypothesis: r_f 
gradient is concentrated in 1/4 agents per scenario. 3/4 agents 
have effectively zero learning signal under single-point 
disturbance protocol.

Implications:
- The earlier loadstep_metrics.json bit-identicality WAS a 
  disturbance-protocol artifact (frozen R-block), not measurement 
  collapse. Measurement layer is exonerated.
- But the 3-of-4 agents see no signal even under live SG-side 
  disturbance. RL improvement claim under this protocol is 
  bounded by the 1 agent that DOES see signal (typically the 
  electrically-nearest ESS to the perturbed gen).
- Multi-point disturbance (Option F = SG-side + multi-point ESS 
  Pm-step) or true network LoadStep (Option E = CCS at Bus 7/9) 
  remain the only known protocols that would excite >1 agent.