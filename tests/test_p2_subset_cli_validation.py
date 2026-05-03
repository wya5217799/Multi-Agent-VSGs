"""Unit tests for Module α CLI validation (no MATLAB required).

Tests subprocess invocation of the probe CLI to verify argument validation
rules introduced in Module α:
- ``--workers > 1`` + ``--phase 5`` → rejected with informative message.
- ``--workers > 1`` + ``--phase 6`` → rejected.
- ``--workers 1`` is always accepted (serial default).
"""
from __future__ import annotations

import subprocess
import sys


_PY = sys.executable
_MODULE = "probes.kundur.probe_state"


def _run(*extra_args: str) -> subprocess.CompletedProcess:
    """Run ``python -m probes.kundur.probe_state <extra_args>`` and capture output."""
    return subprocess.run(
        [_PY, "-m", _MODULE, *extra_args],
        capture_output=True,
        text=True,
    )


def test_workers_with_phase5_rejects():
    """--workers 2 --phase 5 must exit non-zero with 'out of P2 scope' in stderr."""
    result = _run("--workers", "2", "--phase", "5")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "out of P2 scope" in combined


def test_workers_with_phase6_rejects():
    """--workers 2 --phase 6 must exit non-zero."""
    result = _run("--workers", "2", "--phase", "6")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "out of P2 scope" in combined


def test_workers_zero_rejects():
    """--workers 0 must exit non-zero (must be >= 1)."""
    result = _run("--workers", "0", "--no-mcp")
    assert result.returncode != 0


def test_workers_1_with_phase5_accepted():
    """--workers 1 (default serial) with --phase 5 --no-mcp must not be rejected by workers validation.

    Note: --no-mcp drops phases 1/3/4/5/6 from the run, so the probe exits 0
    after running only phases 2 + verdict + report.  We just verify the workers
    validation does NOT fire (would be exit != 0 before phases start).
    """
    # --no-mcp drops phase 5 from the effective set; the important thing is
    # that the --workers 1 validation path does NOT raise SystemExit.
    result = _run("--workers", "1", "--phase", "5", "--no-mcp")
    # exit 0 expected: workers=1 validation passes, no MATLAB needed after --no-mcp
    assert result.returncode == 0
