from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.editor_modal_state_query import is_dock_shell_active

pytestmark = [pytest.mark.fast]


def test_dock_shell_inactive_without_editor_controller() -> None:
    window = SimpleNamespace(editor_controller=None, editor_shell_overlay=object())

    assert is_dock_shell_active(window) is False


def test_dock_shell_inactive_when_controller_inactive() -> None:
    window = SimpleNamespace(editor_controller=SimpleNamespace(active=False), editor_shell_overlay=object())

    assert is_dock_shell_active(window) is False


def test_dock_shell_inactive_without_shell_overlay() -> None:
    window = SimpleNamespace(editor_controller=SimpleNamespace(active=True), editor_shell_overlay=None)

    assert is_dock_shell_active(window) is False


def test_dock_shell_active_with_active_controller_and_shell_overlay() -> None:
    window = SimpleNamespace(editor_controller=SimpleNamespace(active=True), editor_shell_overlay=object())

    assert is_dock_shell_active(window) is True
