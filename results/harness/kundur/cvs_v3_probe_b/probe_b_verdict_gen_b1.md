# Probe B sign-pair experiment verdict

**Generated:** probe_b_pos_gen_b1.json vs probe_b_neg_gen_b1.json

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
pos_hashes = ['46ffa4a6a9d5dd9e', '747faebbf21c1763', '3806358b383170d3', '3387942af833c8c6']
neg_hashes = ['5be68cd3d25f21e9', '3b761f14ca59ac8a', '9fcf293916c8a851', '3d1fbf9236d29feb']
pos_nadir = [-0.11182158306828338, -0.0005411956764400649, -0.001771892530411101, -0.007983892469959342]  pos_peak = [0.1440365665746346, 0.0006185036033889979, 0.002389570622551851, 0.009148727545305047]
neg_nadir = [-0.13954485956799156, -0.0005419931178585191, -0.0017718103187625012, -0.007984178062342417]  neg_peak = [0.1097949452689373, 0.000617359744148338, 0.002387782553836537, 0.009146692015415958]
per-agent (|nadir_diff|+|peak_diff|) = [0.06196489780540548, 1.9413006591140203e-06, 1.870280363913679e-06, 2.321122272164189e-06]
agents_responding (|diff| > 1e-3 Hz) = 1/4
pos_r_f_local_eta1 = [-2.0586125260002622e-05, -2.0202194543125516e-05, -2.1275448057399314e-07, -2.0576437794039144e-05]
neg_r_f_local_eta1 = [-2.0552870974732812e-05, -2.092620277367792e-05, -2.1278311066551025e-07, -2.074524844729611e-05]
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