"""Policy test: tkinter must never be imported during test/headless imports.

This test ensures that importing common engine modules in a test environment
does NOT cause tkinter to be imported. tkinter.update() hangs indefinitely
without a display, so importing tkinter is forbidden in test/CI/headless.

This is a regression test for the hang that occurred when clipboard code
imported tkinter at module load time instead of deferring the import.

IMPORTANT: These tests run in subprocesses to avoid polluting the test suite's
sys.modules state. Removing modules from sys.modules breaks dataclass resolution
for subsequent tests.
"""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from tests.subprocess_tools import run_python_code

if TYPE_CHECKING:
    from collections.abc import Sequence


# Modules that should be safe to import without pulling in tkinter
_REPRESENTATIVE_MODULES: Sequence[str] = (
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


def _run_import_check_subprocess(code: str) -> tuple[int, str, str]:
    """Run Python code in a subprocess to check imports without polluting sys.modules.

    Returns (return_code, stdout, stderr).
    """
    import os
    return run_python_code(
        code,
        timeout_s=30,
        cwd=str(__file__).rsplit("tests", 1)[0].rstrip("\\/"),  # Project root
        env={**{k: v for k, v in os.environ.items()}, "PYTEST_CURRENT_TEST": "subprocess_test"},
    )


class TestNoTkinterImportsPolicy:
    """Policy tests ensuring tkinter is never imported in test environments.

    All tests run in subprocesses to avoid polluting sys.modules state.
    """

    def test_representative_imports_do_not_import_tkinter(self) -> None:
        """Importing representative engine modules must not import tkinter.

        This test verifies that in a test environment (PYTEST_CURRENT_TEST set),
        importing common engine modules does not cause tkinter to be loaded.
        tkinter.update() hangs without a display, so this is a critical policy.
        """
        modules_list = repr(list(_REPRESENTATIVE_MODULES))
        code = textwrap.dedent(f"""
            import sys
            import importlib

            modules = {modules_list}
            for mod in modules:
                try:
                    importlib.import_module(mod)
                except ImportError:
                    pass

            tkinter_imported = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
            if tkinter_imported:
                print(f"FAIL: tkinter imported: {{tkinter_imported}}")
                sys.exit(1)
            print("PASS")
        """)
        returncode, stdout, stderr = _run_import_check_subprocess(code)
        assert returncode == 0, (
            f"tkinter was imported by engine modules in test environment.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )

    def test_clipboard_import_does_not_import_tkinter(self) -> None:
        """Specifically test that clipboard module import doesn't import tkinter."""
        code = textwrap.dedent("""
            import sys
            import importlib

            importlib.import_module("engine.tooling_runtime.clipboard")

            if "tkinter" in sys.modules:
                print("FAIL: tkinter was imported")
                sys.exit(1)
            print("PASS")
        """)
        returncode, stdout, stderr = _run_import_check_subprocess(code)
        assert returncode == 0, (
            f"tkinter was imported when importing clipboard module.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )

    def test_clipboard_shim_does_not_import_tkinter(self) -> None:
        """Test that the tooling.clipboard shim doesn't import tkinter."""
        code = textwrap.dedent("""
            import sys
            import importlib

            importlib.import_module("engine.tooling.clipboard")

            if "tkinter" in sys.modules:
                print("FAIL: tkinter was imported")
                sys.exit(1)
            print("PASS")
        """)
        returncode, stdout, stderr = _run_import_check_subprocess(code)
        assert returncode == 0, (
            f"tkinter was imported when importing clipboard shim.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )

    def test_editor_controller_import_does_not_import_tkinter(self) -> None:
        """Test that importing editor_controller doesn't import tkinter.

        editor_controller uses clipboard but should not import tkinter at load time.
        """
        code = textwrap.dedent("""
            import sys
            import importlib

            importlib.import_module("engine.editor_controller")

            if "tkinter" in sys.modules:
                print("FAIL: tkinter was imported")
                sys.exit(1)
            print("PASS")
        """)
        returncode, stdout, stderr = _run_import_check_subprocess(code)
        assert returncode == 0, (
            f"tkinter was imported when importing editor_controller.\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
