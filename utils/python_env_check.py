"""
Runtime Python interpreter guard.

Call check_python_env(expected_exe) at the top of any script that must run
in a specific Python environment (e.g. andes_env for MATLAB Engine support).
Exits immediately with a clear message if the wrong interpreter is used.
"""
import os
import sys


def check_python_env(expected_exe: str) -> None:
    """Exit with a clear error if sys.executable does not match expected_exe.

    Comparison is case-insensitive (Windows paths).
    """
    actual = os.path.normcase(sys.executable)
    expected = os.path.normcase(expected_exe)
    if actual != expected:
        sys.exit(
            f"[WRONG PYTHON] This script must run with:\n"
            f"  {expected_exe}\n"
            f"Got:\n"
            f"  {sys.executable}\n"
            f"Run via the correct interpreter or activate andes_env."
        )
