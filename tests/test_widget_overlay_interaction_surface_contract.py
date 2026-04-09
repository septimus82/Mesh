from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays.keybinds_overlay import KeybindsOverlay
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


_REQUIRED_METHODS: tuple[str, ...] = (
    "reset_for_open",
    "reset_for_close",
    "toggle_focus",
    "append_text",
    "backspace",
    "handle_navigation_key",
    "on_key_enter",
    "on_mouse_scroll",
    "on_mouse_press",
)


@pytest.mark.parametrize(
    "overlay_type",
    (
        FindEverythingOverlay,
        SceneBrowserOverlay,
        KeybindsOverlay,
        AssetBrowserOverlay,
    ),
)
def test_widgetized_overlay_surface_methods_and_focus_compatibility(
    overlay_type: type[object],
) -> None:
    window = SimpleNamespace(
        width=1280,
        height=720,
        text_cache=None,
        editor_controller=SimpleNamespace(),
        input=None,
        input_controller=None,
    )
    overlay = as_any(overlay_type)(as_any(window))

    assert hasattr(overlay, "_focus_target")
    for method_name in _REQUIRED_METHODS:
        method = getattr(overlay, method_name, None)
        assert callable(method), f"{overlay_type.__name__}: missing callable {method_name}"


@pytest.mark.parametrize(
    "overlay_type",
    (
        FindEverythingOverlay,
        SceneBrowserOverlay,
        KeybindsOverlay,
        AssetBrowserOverlay,
    ),
)
def test_widgetized_overlay_focus_resets_deterministically_across_open_close_reopen(
    overlay_type: type[object],
) -> None:
    window = SimpleNamespace(
        width=1280,
        height=720,
        text_cache=None,
        editor_controller=SimpleNamespace(),
        input=None,
        input_controller=None,
    )
    overlay = as_any(overlay_type)(as_any(window))

    overlay.reset_for_open()
    assert overlay._focus_target == "input"

    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"

    overlay.reset_for_close()
    assert overlay._focus_target == "input"

    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"

    overlay.reset_for_open()
    assert overlay._focus_target == "input"
