"""Subprocess utilities for tests with guaranteed timeout protection.

All test subprocess invocations should use run_checked() to prevent
test suite hangs from runaway subprocesses.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# Default timeout for subprocess calls in tests (seconds)
DEFAULT_TIMEOUT_S = 60


def run_checked(
    args: list[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with guaranteed timeout and text output.

    This is a wrapper around subprocess.run() that:
    - Always applies a timeout (default 60s)
    - Always captures output as text
    - Converts TimeoutExpired into AssertionError with captured output

    Args:
        args: Command and arguments to run.
        timeout_s: Timeout in seconds. Default 60s.
        check: If True, raise CalledProcessError on non-zero exit.
        **kwargs: Additional arguments passed to subprocess.run().
            Note: text=True and capture_output=True are set by default
            but can be overridden.

    Returns:
        CompletedProcess with stdout/stderr as strings.

    Raises:
        AssertionError: If the subprocess times out, with partial output included.
        subprocess.CalledProcessError: If check=True and return code is non-zero.
    """
    # Set defaults for text mode and output capture
    kwargs.setdefault("text", True)
    kwargs.setdefault("capture_output", True)

    try:
        return subprocess.run(args, timeout=timeout_s, check=check, **kwargs)
    except subprocess.TimeoutExpired as e:
        # Build informative error message with any captured output
        stdout_part = ""
        stderr_part = ""
        if e.stdout:
            stdout_text = e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors="replace")
            stdout_part = f"\n--- STDOUT (partial) ---\n{stdout_text}"
        if e.stderr:
            stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="replace")
            stderr_part = f"\n--- STDERR (partial) ---\n{stderr_text}"

        cmd_str = " ".join(args) if isinstance(args, list) else str(args)
        raise AssertionError(
            f"Subprocess timed out after {timeout_s}s.\n"
            f"Command: {cmd_str}"
            f"{stdout_part}{stderr_part}\n"
            f"Likely cause: subprocess hung or did not terminate cleanly."
        ) from e


def run_python_code(
    code: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run Python code in a subprocess.

    Convenience wrapper for running python -c "code" with timeout protection.

    Args:
        code: Python code to execute.
        timeout_s: Timeout in seconds.
        cwd: Working directory for subprocess.
        env: Environment variables for subprocess.

    Returns:
        Tuple of (return_code, stdout, stderr).

    Raises:
        AssertionError: If the subprocess times out.
    """
    kwargs: dict[str, Any] = {}
    if cwd is not None:
        kwargs["cwd"] = cwd
    if env is not None:
        kwargs["env"] = env

    result = run_checked(
        [sys.executable, "-c", code],
        timeout_s=timeout_s,
        **kwargs,
    )
    return result.returncode, result.stdout, result.stderr
