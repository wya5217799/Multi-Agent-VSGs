"""GPU variant of training-curve smoke.

Monkey-patches SACAgent default device='cuda' before invoking
_phase9_curve_smoke.main(). Used to run an n=2 corroboration in
parallel with the CPU curve smoke, putting the otherwise-idle GPU
to use.

Note: §3.4 verdict found GPU training ~4% slower than CPU on this
workload (256-256 net), but the wall-time impact is small and using
GPU consumes a different resource pool, so running CPU+GPU in
parallel doubles throughput for this experiment.
"""
from __future__ import annotations

import os
import sys

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

if not torch.cuda.is_available():
    raise SystemExit("CUDA unavailable — abort GPU curve smoke")

# Monkey-patch SACAgent.__init__ default device to 'cuda'
import agents.sac as _sac_mod  # noqa: E402

_orig_init = _sac_mod.SACAgent.__init__


def _gpu_init(self, *args, **kwargs):
    if "device" not in kwargs:
        kwargs["device"] = "cuda"
    return _orig_init(self, *args, **kwargs)


_sac_mod.SACAgent.__init__ = _gpu_init
print(f"[GPU curve] Patched SACAgent default device → cuda ({torch.cuda.get_device_name(0)})")
print(f"[GPU curve] CUDA mem total: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

# Now run main()
from scenarios.kundur._phase9_curve_smoke import main  # noqa: E402

main()
