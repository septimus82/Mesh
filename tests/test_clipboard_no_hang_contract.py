"""Regression test for clipboard hang prevention.

This test verifies that clipboard operations do NOT touch tkinter when
running in test/CI/web/headless environments. Previously, tkinter.update()
would hang indefinitely in headless environments.

The test monkeypatches tkinter to raise an error if accessed, ensuring
the clipboard code correctly skips tkinter when it should.
"""
from __future__ import annotations

import sys
from typing import Any

import pytest

from tests._typing import as_any


class TkinterAccessError(Exception):
    """Raised if tkinter is accessed when it shouldn't be."""


class _ForbiddenTkinterModule:
    """A fake tkinter module that raises on any attribute access."""

    def __getattr__(self, name: str) -> Any:
        raise TkinterAccessError(
            f"tkinter.{name} was accessed but should have been skipped"
        )

    def Tk(self) -> Any:  # noqa: N802
        raise TkinterAccessError("tkinter.Tk() was called but should have been skipped")


class TestClipboardCapabilitiesModel:
    """Tests for the clipboard_capabilities_model module."""

    def test_should_attempt_clipboard_returns_false_for_web(self) -> None:
        """Web environments have no clipboard access."""
        from engine.editor.clipboard_capabilities_model import should_attempt_clipboard

        result = should_attempt_clipboard({}, is_web=True)
        assert result is False

    def test_should_attempt_clipboard_returns_false_for_headless(self) -> None:
        """Headless environments have no display for tkinter."""
        from engine.editor.clipboard_capabilities_model import should_attempt_clipboard

        result = should_attempt_clipboard({}, is_headless=True)
        assert result is False

    def test_should_attempt_clipboard_returns_false_for_pytest(self) -> None:
        """Test environments should not touch system clipboard."""
        from engine.editor.clipboard_capabilities_model import should_attempt_clipboard

        result = should_attempt_clipboard({"PYTEST_CURRENT_TEST": "test_foo.py"})
        assert result is False

    def test_should_attempt_clipboard_returns_false_for_ci(self) -> None:
        """CI environments should not touch system clipboard."""
        from engine.editor.clipboard_capabilities_model import should_attempt_clipboard

        for ci_var in ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "TRAVIS"]:
            result = should_attempt_clipboard({ci_var: "true"})
            assert result is False, f"should_attempt_clipboard should return False for {ci_var}"

    def test_should_attempt_clipboard_returns_true_for_clean_env(self) -> None:
        """Normal interactive environments should allow clipboard."""
        from engine.editor.clipboard_capabilities_model import should_attempt_clipboard

        result = should_attempt_clipboard({})
        assert result is True

    def test_is_ci_environment_detects_ci_vars(self) -> None:
        """is_ci_environment should detect CI environment variables."""
        from engine.editor.clipboard_capabilities_model import is_ci_environment

        assert is_ci_environment({}) is False
        assert is_ci_environment({"CI": "true"}) is True
        assert is_ci_environment({"GITHUB_ACTIONS": "true"}) is True

    def test_is_test_environment_detects_test_vars(self) -> None:
        """is_test_environment should detect test environment variables."""
        from engine.editor.clipboard_capabilities_model import is_test_environment

        assert is_test_environment({}) is False
        assert is_test_environment({"PYTEST_CURRENT_TEST": "test.py"}) is True


class TestClipboardNoHangRegression:
    """Regression tests ensuring clipboard never hangs in test environments.

    These tests would have hung before the fix because tkinter.update()
    blocks indefinitely when there's no display.
    """

    def test_try_copy_to_clipboard_does_not_import_tkinter_in_test_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tkinter is never imported when PYTEST_CURRENT_TEST is set.

        This is a regression test for the hang that occurred at ~76% of the
        test suite when test_problems_copy_location_with_target called
        try_copy_to_clipboard, which called tkinter.update() and hung.
        """
        # Ensure PYTEST_CURRENT_TEST is set (pytest sets this automatically)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_clipboard_no_hang_contract.py")

        # Remove tkinter from sys.modules if it's already imported
        tkinter_modules = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
        original_modules = {k: sys.modules.pop(k) for k in tkinter_modules}

        # Install a forbidden tkinter module that raises on access
        forbidden = _ForbiddenTkinterModule()
        monkeypatch.setitem(sys.modules, "tkinter", forbidden)

        try:
            # Force reimport of clipboard module to pick up our fake tkinter
            # We need to test fresh import behavior
            import importlib

            from engine.tooling_runtime import clipboard

            importlib.reload(clipboard)

            # This should NOT raise TkinterAccessError because tkinter should be skipped
            result = clipboard.try_copy_to_clipboard("test text")

            # Result should be False (clipboard skipped) and no TkinterAccessError
            assert result is False
        finally:
            # Restore original tkinter modules
            sys.modules.pop("tkinter", None)
            for k, v in original_modules.items():
                sys.modules[k] = v

    def test_try_copy_to_clipboard_does_not_import_tkinter_in_ci_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tkinter is never imported when CI is set."""
        # Clear PYTEST_CURRENT_TEST and set CI instead
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("CI", "true")

        # Remove tkinter from sys.modules
        tkinter_modules = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
        original_modules = {k: sys.modules.pop(k) for k in tkinter_modules}

        forbidden = _ForbiddenTkinterModule()
        monkeypatch.setitem(sys.modules, "tkinter", forbidden)

        try:
            import importlib

            from engine.tooling_runtime import clipboard

            importlib.reload(clipboard)

            result = clipboard.try_copy_to_clipboard("test text")
            assert result is False
        finally:
            sys.modules.pop("tkinter", None)
            for k, v in original_modules.items():
                sys.modules[k] = v

    def test_try_copy_to_clipboard_does_not_import_tkinter_when_web(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tkinter is never imported when is_web=True."""
        # Clear env vars that would skip clipboard
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("CI", raising=False)

        tkinter_modules = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
        original_modules = {k: sys.modules.pop(k) for k in tkinter_modules}

        forbidden = _ForbiddenTkinterModule()
        monkeypatch.setitem(sys.modules, "tkinter", forbidden)

        try:
            import importlib

            from engine.tooling_runtime import clipboard

            importlib.reload(clipboard)

            # Explicitly pass is_web=True
            result = clipboard.try_copy_to_clipboard("test text", is_web=True)
            assert result is False
        finally:
            sys.modules.pop("tkinter", None)
            for k, v in original_modules.items():
                sys.modules[k] = v

    def test_try_copy_to_clipboard_does_not_import_tkinter_when_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tkinter is never imported when is_headless=True."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("CI", raising=False)

        tkinter_modules = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
        original_modules = {k: sys.modules.pop(k) for k in tkinter_modules}

        forbidden = _ForbiddenTkinterModule()
        monkeypatch.setitem(sys.modules, "tkinter", forbidden)

        try:
            import importlib

            from engine.tooling_runtime import clipboard

            importlib.reload(clipboard)

            result = clipboard.try_copy_to_clipboard("test text", is_headless=True)
            assert result is False
        finally:
            sys.modules.pop("tkinter", None)
            for k, v in original_modules.items():
                sys.modules[k] = v

    def test_try_copy_to_clipboard_returns_false_for_empty_text(self) -> None:
        """Empty text should return False without touching tkinter."""
        from engine.tooling_runtime.clipboard import try_copy_to_clipboard

        assert try_copy_to_clipboard("") is False
        assert try_copy_to_clipboard(as_any(None)) is False


class TestClipboardToolingModule:
    """Tests for the tooling clipboard module (mirrors tooling_runtime)."""

    def test_tooling_clipboard_skips_in_test_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tooling/clipboard.py also skips in test environments."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test.py")

        tkinter_modules = [k for k in sys.modules if k == "tkinter" or k.startswith("tkinter.")]
        original_modules = {k: sys.modules.pop(k) for k in tkinter_modules}

        forbidden = _ForbiddenTkinterModule()
        monkeypatch.setitem(sys.modules, "tkinter", forbidden)

        try:
            import importlib

            from engine.tooling import clipboard

            importlib.reload(clipboard)

            result = clipboard.try_copy_to_clipboard("test text")
            assert result is False
        finally:
            sys.modules.pop("tkinter", None)
            for k, v in original_modules.items():
                sys.modules[k] = v
