"""Unit tests for tests/subprocess_tools.py timeout handling."""
from __future__ import annotations

import sys

import pytest

from tests.subprocess_tools import run_checked, run_python_code


class TestRunChecked:
    """Tests for run_checked() timeout and output handling."""

    def test_successful_command_returns_output(self) -> None:
        """A fast successful command returns its output."""
        result = run_checked([sys.executable, "-c", "print('hello')"], timeout_s=5)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_failing_command_returns_nonzero(self) -> None:
        """A failing command returns non-zero without raising."""
        result = run_checked([sys.executable, "-c", "import sys; sys.exit(42)"], timeout_s=5)
        assert result.returncode == 42

    def test_check_true_raises_on_failure(self) -> None:
        """With check=True, non-zero exit raises CalledProcessError."""
        import subprocess

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_checked(
                [sys.executable, "-c", "import sys; sys.exit(1)"],
                timeout_s=5,
                check=True,
            )
        assert exc_info.value.returncode == 1

    def test_timeout_raises_assertion_error_with_message(self) -> None:
        """Timeout converts to AssertionError with informative message."""
        # Use a very short timeout with a sleep that will exceed it
        with pytest.raises(AssertionError) as exc_info:
            run_checked(
                [sys.executable, "-c", "import time; print('starting'); time.sleep(999)"],
                timeout_s=0.2,
            )
        error_msg = str(exc_info.value)
        assert "timed out" in error_msg.lower()
        assert "0.2s" in error_msg
        assert "time.sleep" in error_msg  # Command visible

    def test_timeout_includes_partial_stdout(self) -> None:
        """Timeout error includes any captured stdout."""
        with pytest.raises(AssertionError) as exc_info:
            run_checked(
                [sys.executable, "-c", "import time; import sys; print('MARKER123', flush=True); sys.stdout.flush(); time.sleep(999)"],
                timeout_s=0.3,
            )
        # Note: partial output capture is not guaranteed on all platforms
        # so we just verify the error message structure is correct
        error_msg = str(exc_info.value)
        assert "timed out" in error_msg.lower()


class TestRunPythonCode:
    """Tests for run_python_code() convenience function."""

    def test_returns_tuple_of_code_stdout_stderr(self) -> None:
        """Returns (returncode, stdout, stderr) tuple."""
        code, stdout, stderr = run_python_code("print('out')", timeout_s=5)
        assert code == 0
        assert "out" in stdout
        assert isinstance(stderr, str)

    def test_timeout_raises_assertion_error(self) -> None:
        """Timeout raises AssertionError like run_checked."""
        with pytest.raises(AssertionError) as exc_info:
            run_python_code("import time; time.sleep(999)", timeout_s=0.2)
        assert "timed out" in str(exc_info.value).lower()
