"""Y4 — 4-engine concurrent MATLAB license smoke (P2 spec M7 gate).

Spawns N subprocesses in parallel, each starting its own matlab.engine,
and collects exit codes + cold-start times. N/N PASS = GATE-LIC PASS for
that N. Resolves spec §3 M7 BLOCKED.

Usage::

    python probes/kundur/spike/test_y4_license_smoke.py [N]

Default N=4. Exit 0 on PASS, 1 on FAIL.
"""
from __future__ import annotations

import subprocess
import sys
import time

WORKER_SCRIPT = """
import sys, time
t0 = time.perf_counter()
try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
    cold_s = time.perf_counter() - t0
    result = eng.eval('1+2', nargout=1)
    eng.exit()
    print(f'engine_{idx}_ready cold_start={cold_s:.2f}s eval=1+2={result}')
    sys.exit(0)
except Exception as e:
    elapsed = time.perf_counter() - t0
    print(f'engine_{idx}_FAILED elapsed={elapsed:.2f}s reason={type(e).__name__}: {e}')
    sys.exit(1)
""".strip()


def main(n_workers: int = 4, timeout_s: float = 120.0) -> int:
    print(f"[Y4] launching {n_workers} concurrent matlab.engine workers ...")
    procs = []
    t_launch = time.perf_counter()
    for idx in range(n_workers):
        script = WORKER_SCRIPT.replace("{idx}", str(idx))
        p = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        procs.append((idx, p))

    results = []
    for idx, p in procs:
        try:
            stdout, _ = p.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout = "TIMEOUT"
        results.append((idx, p.returncode, stdout))

    total_wall = time.perf_counter() - t_launch
    n_pass = sum(1 for _, ec, _ in results if ec == 0)

    print(f"[Y4] total_wall={total_wall:.1f}s, n_pass={n_pass}/{n_workers}")
    for idx, ec, out in results:
        first_line = (
            out.strip().splitlines()[0] if out.strip() else "(no output)"
        )
        print(f"  worker_{idx}: exit_code={ec} stdout={first_line!r}")

    if n_pass == n_workers:
        print(f"[Y4] VERDICT=GATE_LIC_PASS — {n_workers} concurrent engines OK")
        return 0
    print(
        f"[Y4] VERDICT=GATE_LIC_FAIL — only {n_pass}/{n_workers} engines started"
    )
    return 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    sys.exit(main(n_workers=n))
