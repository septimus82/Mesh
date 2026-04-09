"""Contract tests for HD-2D preview indicator model.

Tests the pure formatting function and provider behavior.
"""

from __future__ import annotations

import pytest

from tests._typing import as_any


# =============================================================================
# Pure Model Tests - format_hd2d_preview_indicator_text
# =============================================================================


class TestFormatHd2dPreviewIndicatorText:
    """Tests for format_hd2d_preview_indicator_text."""

    def test_returns_formatted_text_for_valid_preset_id(self) -> None:
        """Valid preset ID returns properly formatted text."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("soft")

        assert result == "HD2D Preview: Soft (Esc cancel, Enter apply)"

    def test_capitalizes_preset_name(self) -> None:
        """Preset name is capitalized in output."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        assert "Soft" in format_hd2d_preview_indicator_text("soft")
        assert "Crisp" in format_hd2d_preview_indicator_text("crisp")
        assert "Noir" in format_hd2d_preview_indicator_text("noir")
        assert "Dreamy" in format_hd2d_preview_indicator_text("dreamy")

    def test_returns_empty_string_for_none(self) -> None:
        """None preset ID returns empty string."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text(None)

        assert result == ""

    def test_returns_empty_string_for_empty_string(self) -> None:
        """Empty preset ID returns empty string."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("")

        assert result == ""

    def test_returns_empty_string_for_whitespace_only(self) -> None:
        """Whitespace-only preset ID returns empty string."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("   ")

        assert result == ""

    def test_strips_whitespace_from_preset_id(self) -> None:
        """Preset ID with leading/trailing whitespace is trimmed."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("  soft  ")

        assert result == "HD2D Preview: Soft (Esc cancel, Enter apply)"

    def test_includes_escape_hint(self) -> None:
        """Output includes Esc cancel hint."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("soft")

        assert "Esc cancel" in result

    def test_includes_enter_hint(self) -> None:
        """Output includes Enter apply hint."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("soft")

        assert "Enter apply" in result

    def test_includes_hd2d_preview_prefix(self) -> None:
        """Output includes HD2D Preview prefix."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("soft")

        assert result.startswith("HD2D Preview:")

    def test_works_with_custom_preset_ids(self) -> None:
        """Works with arbitrary preset IDs, not just built-in ones."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        result = format_hd2d_preview_indicator_text("custom")

        assert result == "HD2D Preview: Custom (Esc cancel, Enter apply)"

    def test_returns_empty_for_non_string(self) -> None:
        """Non-string values return empty string."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        assert format_hd2d_preview_indicator_text(as_any(123)) == ""
        assert format_hd2d_preview_indicator_text(as_any([])) == ""
        assert format_hd2d_preview_indicator_text(as_any({})) == ""


# =============================================================================
# Provider Tests - hd2d_preview_indicator_provider
# =============================================================================


class TestHd2dPreviewIndicatorProvider:
    """Tests for hd2d_preview_indicator_provider."""

    def test_returns_visible_false_when_no_editor_controller(self) -> None:
        """Returns visible=False when window has no editor_controller."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeWindow:
            pass

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert result["visible"] is False
        assert result["preset_id"] is None

    def test_returns_visible_false_when_preview_not_active(self) -> None:
        """Returns visible=False when preview is not active."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = False
            _hd2d_preview_preset_id = None

        class FakeWindow:
            editor_controller = FakeEditor()

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert result["visible"] is False
        assert result["preset_id"] is None

    def test_returns_visible_true_when_preview_active(self) -> None:
        """Returns visible=True and preset_id when preview is active."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = "soft"

        class FakeWindow:
            editor_controller = FakeEditor()

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert result["visible"] is True
        assert result["preset_id"] == "soft"

    def test_returns_visible_false_when_active_but_no_preset_id(self) -> None:
        """Returns visible=False when active but preset_id is None."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = None

        class FakeWindow:
            editor_controller = FakeEditor()

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert result["visible"] is False
        assert result["preset_id"] is None

    def test_returns_visible_false_when_active_but_empty_preset_id(self) -> None:
        """Returns visible=False when active but preset_id is empty string."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = ""

        class FakeWindow:
            editor_controller = FakeEditor()

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert result["visible"] is False
        assert result["preset_id"] is None

    def test_preset_id_converted_to_string(self) -> None:
        """Preset ID is converted to string in output."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = "crisp"

        class FakeWindow:
            editor_controller = FakeEditor()

        result = hd2d_preview_indicator_provider(FakeWindow())

        assert isinstance(result["preset_id"], str)
        assert result["preset_id"] == "crisp"


# =============================================================================
# Overlay Class Tests - HD2DPreviewIndicatorOverlay
# =============================================================================


class TestHd2dPreviewIndicatorOverlay:
    """Tests for HD2DPreviewIndicatorOverlay class."""

    def test_class_exists(self) -> None:
        """Overlay class can be imported."""
        from engine.ui_overlays.debug import HD2DPreviewIndicatorOverlay

        assert HD2DPreviewIndicatorOverlay is not None

    def test_inherits_from_ui_element(self) -> None:
        """Overlay inherits from UIElement."""
        from engine.ui_overlays.common import UIElement
        from engine.ui_overlays.debug import HD2DPreviewIndicatorOverlay

        assert issubclass(HD2DPreviewIndicatorOverlay, UIElement)

    def test_has_draw_method(self) -> None:
        """Overlay has draw method."""
        from engine.ui_overlays.debug import HD2DPreviewIndicatorOverlay

        assert hasattr(HD2DPreviewIndicatorOverlay, "draw")
        assert callable(getattr(HD2DPreviewIndicatorOverlay, "draw"))

    def test_accepts_provider_kwarg(self) -> None:
        """Overlay constructor accepts provider kwarg."""
        from engine.ui_overlays.debug import HD2DPreviewIndicatorOverlay
        import inspect

        sig = inspect.signature(HD2DPreviewIndicatorOverlay.__init__)
        params = list(sig.parameters.keys())

        assert "provider" in params


# =============================================================================
# Integration Sanity Tests
# =============================================================================


class TestHd2dPreviewIndicatorIntegration:
    """Integration sanity tests."""

    def test_provider_and_formatter_work_together(self) -> None:
        """Provider output works with formatter."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = "dreamy"

        class FakeWindow:
            editor_controller = FakeEditor()

        payload = hd2d_preview_indicator_provider(FakeWindow())
        text = format_hd2d_preview_indicator_text(payload["preset_id"])

        assert payload["visible"] is True
        assert "Dreamy" in text
        assert "HD2D Preview:" in text

    def test_format_returns_empty_when_provider_says_not_visible(self) -> None:
        """When provider returns not visible, formatter returns empty for None."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        class FakeEditor:
            _hd2d_preview_active = False
            _hd2d_preview_preset_id = None

        class FakeWindow:
            editor_controller = FakeEditor()

        payload = hd2d_preview_indicator_provider(FakeWindow())
        text = format_hd2d_preview_indicator_text(payload["preset_id"])

        assert payload["visible"] is False
        assert text == ""

    def test_exported_from_engine_ui(self) -> None:
        """HD2DPreviewIndicatorOverlay is exported from engine.ui."""
        from engine.ui import HD2DPreviewIndicatorOverlay

        assert HD2DPreviewIndicatorOverlay is not None


# =============================================================================
# Side Effect Tests - No Dirty/Undo Changes
# =============================================================================


class TestHd2dPreviewIndicatorNoSideEffects:
    """Tests ensuring indicator doesn't cause side effects."""

    def test_formatter_is_pure_function(self) -> None:
        """Formatter is a pure function with no side effects."""
        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        # Call multiple times with same input
        result1 = format_hd2d_preview_indicator_text("soft")
        result2 = format_hd2d_preview_indicator_text("soft")
        result3 = format_hd2d_preview_indicator_text("soft")

        # Should always return same output
        assert result1 == result2 == result3

    def test_provider_does_not_modify_editor_state(self) -> None:
        """Provider reads state but doesn't modify it."""
        from engine.ui_overlays.providers import hd2d_preview_indicator_provider

        class FakeEditor:
            _hd2d_preview_active = True
            _hd2d_preview_preset_id = "noir"

        class FakeWindow:
            editor_controller = FakeEditor()

        window = FakeWindow()

        # Call provider multiple times
        hd2d_preview_indicator_provider(window)
        hd2d_preview_indicator_provider(window)
        hd2d_preview_indicator_provider(window)

        # State should be unchanged
        assert window.editor_controller._hd2d_preview_active is True
        assert window.editor_controller._hd2d_preview_preset_id == "noir"
