"""Policy test: no non-daemon threads may be started during representative imports.

This test ensures that importing common engine modules in a test environment
does NOT start any non-daemon threads. Non-daemon threads prevent clean process
exit and can cause pytest hangs if they block indefinitely.

This is a regression test to catch any module that spawns background threads
at import time instead of deferring to runtime "enter editor/game loop".

IMPORTANT: This test runs in a subprocess to avoid polluting the test suite's
thread state and to get a clean baseline.
"""
from __future__ import annotations

import textwrap

import pytest

from tests.subprocess_tools import run_python_code


# Same representative modules as test_no_tkinter_imports_policy
_REPRESENTATIVE_MODULES: tuple[str, ...] = (
    # Core engine modules
    "engine",
    "engine.config",
    "engine.constants",
    "engine.events",
    # Runtime modules
    "engine.tooling_runtime",
    "engine.tooling_runtime.clipboard",
    "engine.input_runtime",
    # Editor modules
    "engine.editor",
    "engine.editor.clipboard_capabilities_model",
    "engine.editor.editor_actions",
    "engine.editor.shortcut_resolver_model",
    "engine.editor.menu_bar_model",
    "engine.editor.problems_controller",
    # Tooling shim
    "engine.tooling",
    "engine.tooling.clipboard",
)


def _run_thread_check_subprocess() -> tuple[int, str, str]:
    """Run thread check in subprocess to get clean baseline.

    Returns (return_code, stdout, stderr).
    """
    import os
    modules_list = repr(list(_REPRESENTATIVE_MODULES))
    code = textwrap.dedent(f"""
        import sys
        import threading
        import importlib

        # Capture baseline threads before any imports
        baseline_threads = set(t.ident for t in threading.enumerate())
        baseline_names = {{t.ident: t.name for t in threading.enumerate()}}

        # Import representative modules
        modules = {modules_list}
        for mod in modules:
            try:
                importlib.import_module(mod)
            except ImportError:
                pass

        # Check for new non-daemon threads
        new_non_daemon = []
        for t in threading.enumerate():
            if t.ident not in baseline_threads:
                if t.is_alive() and not t.daemon:
                    # Try to get info about the thread
                    target = getattr(t, '_target', None)
                    target_info = ""
                    if target:
                        target_info = f" target={{target.__module__}}.{{target.__name__}}"
                    new_non_daemon.append(f"  - {{t.name}} (ident={{t.ident}}, daemon={{t.daemon}}){{target_info}}")

        if new_non_daemon:
            print("FAIL: Non-daemon threads started during import:")
            for info in new_non_daemon:
                print(info)
            print()
            print("Non-daemon threads prevent clean process exit and can cause pytest hangs.")
            print("Fix: Either set daemon=True or defer thread start to runtime.")
            sys.exit(1)

        print("PASS: No non-daemon threads started during import")
    """)

    return run_python_code(
        code,
        timeout_s=30,
        cwd=str(__file__).rsplit("tests", 1)[0].rstrip("\\/"),  # Project root
        env={
            **{k: v for k, v in os.environ.items()},
            "PYTEST_CURRENT_TEST": "subprocess_test",
        },
    )


class TestNoNonDaemonThreadsPolicy:
    """Policy tests ensuring no non-daemon threads are started at import time."""

    def test_representative_imports_do_not_start_non_daemon_threads(self) -> None:
        """Importing representative engine modules must not start non-daemon threads.

        Non-daemon threads prevent clean process exit. If a non-daemon thread
        blocks (e.g., waiting for I/O or a lock), pytest will hang indefinitely.

        All background threads started at import time must be daemon threads,
        or better yet, thread creation should be deferred to runtime.
        """
        returncode, stdout, stderr = _run_thread_check_subprocess()
        assert returncode == 0, (
            f"Non-daemon threads were started during representative imports.\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}\n"
            f"Fix: Set daemon=True on background threads or defer thread start to runtime."
        )
