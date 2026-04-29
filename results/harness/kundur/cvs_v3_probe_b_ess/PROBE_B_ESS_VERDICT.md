# Probe B-ESS verdict — single-ESS direct Pm injection

**Goal:** verify whether each ES{i}'s swing-eq Pm input channel is
electrically responsive when injected directly (bypassing network mode-shape).
Specifically: is ES2's silence under SG-side a network artifact or build bug?

## Per-agent direct-injection response

| target | own_diff (Hz) | own_responds? | others_max (Hz) | verdict |
|---:|---:|---|---:|---|
| ES1 | 0.1134 | YES | 0.0000 | ES1 swing-eq LIVE |
| ES2 | 0.0377 | YES | 0.0000 | ES2 swing-eq LIVE |
| ES3 | 0.0428 | YES | 0.0021 | ES3 swing-eq LIVE |
| ES4 | 0.0383 | YES | 0.0057 | ES4 swing-eq LIVE |

## Implication for Option F design

**ES2 swing-eq is LIVE** under direct injection. ES2 silence under
SG-side (G1/G2/G3) is a NETWORK TOPOLOGY effect, not a build bug.

Option F can include ES2 in multi-point dispatch via
`EssPmStepProxy(target_indices=(0, 1, 2, 3))` etc. ES2 will receive a
non-zero r_f signal in scenarios where target_indices includes 1.