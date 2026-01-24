"""Contract tests for editor_cursor_apply module.

Tests cursor application helper in a headless-safe way.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine import optional_arcade
from engine.editor.editor_cursor_apply import apply_editor_cursor


@dataclass
class StubWindow:
    calls: int = 0
    last_cursor: object | None = None

    def set_mouse_cursor(self, cursor: object) -> None:
        self.calls += 1
        self.last_cursor = cursor


class TestApplyEditorCursor:
    def test_caches_repeated_kind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine import arcade_fallback as arcade_stub

        monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
        window = StubWindow()

        apply_editor_cursor(window, "pointer")
        apply_editor_cursor(window, "pointer")

        assert window.calls == 1
        assert window.last_cursor == arcade_stub.SystemMouseCursor.HAND

    def test_unknown_kind_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine import arcade_fallback as arcade_stub

        monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
        window = StubWindow()

        apply_editor_cursor(window, "unknown")

        assert window.calls == 1
        assert window.last_cursor == arcade_stub.SystemMouseCursor.DEFAULT
