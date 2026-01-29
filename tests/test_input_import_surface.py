from __future__ import annotations

import sys

from tests.subprocess_tools import run_checked


def test_importing_input_controller_has_no_side_effects_and_exports_surface() -> None:
    script = r"""
import builtins
import io
import os
import sys

import arcade  # noqa: F401

buf = io.StringIO()
sys.stdout = buf

def guarded_open(*_a, **_k):
    raise AssertionError("builtins.open should not run at import time")

def guarded_replace(*_a, **_k):
    raise AssertionError("os.replace should not run at import time")

builtins.open = guarded_open
os.replace = guarded_replace

import engine.input_controller as mod

out = buf.getvalue()
assert out == "", out
assert hasattr(mod, "InputController")
"""

    proc = run_checked(
        [sys.executable, "-c", script],
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout == ""
