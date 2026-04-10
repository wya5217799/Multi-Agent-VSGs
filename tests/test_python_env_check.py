"""
Tests for utils/python_env_check.py — runtime Python interpreter guard.

Purpose: training scripts must fail immediately with a clear message when
launched with the wrong Python interpreter (e.g. system Python 3.14 instead
of andes_env Python 3.11).
"""
import sys
import pytest

from utils.python_env_check import check_python_env


CORRECT_EXE = sys.executable  # whatever Python runs the test suite


class TestCheckPythonEnvWrongPath:
    def test_exits_when_executable_does_not_match(self):
        wrong_exe = r"C:\SomeOtherPython\python.exe"
        with pytest.raises(SystemExit) as exc_info:
            check_python_env(wrong_exe)
        assert exc_info.value.code != 0

    def test_exit_message_contains_expected_path(self):
        wrong_exe = r"C:\SomeOtherPython\python.exe"
        with pytest.raises(SystemExit) as exc_info:
            check_python_env(wrong_exe)
        msg = str(exc_info.value.code)
        assert wrong_exe in msg

    def test_exit_message_contains_actual_path(self):
        wrong_exe = r"C:\SomeOtherPython\python.exe"
        with pytest.raises(SystemExit) as exc_info:
            check_python_env(wrong_exe)
        msg = str(exc_info.value.code)
        assert sys.executable in msg


class TestCheckPythonEnvCorrectPath:
    def test_returns_none_when_executable_matches(self):
        result = check_python_env(CORRECT_EXE)
        assert result is None

    def test_case_insensitive_on_windows(self):
        # Windows paths are case-insensitive; both cases must pass
        upper_exe = CORRECT_EXE.upper()
        lower_exe = CORRECT_EXE.lower()
        check_python_env(upper_exe)   # must not raise
        check_python_env(lower_exe)   # must not raise
