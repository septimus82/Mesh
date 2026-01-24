from __future__ import annotations

import subprocess
import sys


def test_importing_actions_has_no_stdout_noise_and_exports_surface() -> None:
    script = r"""
import io
import sys

buf = io.StringIO()
sys.stdout = buf

import engine.actions as actions

out = buf.getvalue()
assert out == "", out
assert hasattr(actions, "ACTIONS")
assert hasattr(actions, "REQUIRED_ACTIONS")
assert hasattr(actions, "dispatch_action")
assert hasattr(actions, "validate_bound_actions")
assert hasattr(actions, "list_actions")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout == ""

