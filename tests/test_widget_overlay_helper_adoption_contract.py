from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays.keybinds_overlay import KeybindsOverlay
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


_HELPER_NAMES = (
    "apply_text_input",
    "apply_backspace",
    "apply_nav_key",
    "apply_enter",
    "apply_mouse_scroll",
    "apply_mouse_press",
)

_CONTROLLER_PATHS = (
    Path("engine/editor/editor_search_controller.py"),
    Path("engine/editor/editor_scene_browse_controller.py"),
    Path("engine/editor/editor_keybinds_controller.py"),
    Path("engine/editor/editor_asset_browser_controller.py"),
)


def test_migrated_controllers_reference_shared_widget_overlay_helpers() -> None:
    for path in _CONTROLLER_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "widget_overlay_helpers" in source
        for helper_name in _HELPER_NAMES:
            assert helper_name in source, f"{path}: missing helper reference {helper_name}"


@pytest.mark.parametrize(
    ("overlay_type", "method_names", "has_reset"),
    [
        (
            FindEverythingOverlay,
            (
                "toggle_focus",
                "append_text",
                "backspace",
                "handle_navigation_key",
                "on_key_enter",
                "on_mouse_scroll",
                "on_mouse_press",
            ),
            False,
        ),
        (
            SceneBrowserOverlay,
            (
                "toggle_focus",
                "append_text",
                "backspace",
                "handle_navigation_key",
                "on_key_enter",
                "on_mouse_scroll",
                "on_mouse_press",
            ),
            False,
        ),
        (
            KeybindsOverlay,
            (
                "reset_for_open",
                "reset_for_close",
                "toggle_focus",
                "append_text",
                "backspace",
                "handle_navigation_key",
                "on_key_enter",
                "on_mouse_scroll",
                "on_mouse_press",
            ),
            True,
        ),
        (
            AssetBrowserOverlay,
            (
                "reset_for_open",
                "reset_for_close",
                "toggle_focus",
                "append_text",
                "backspace",
                "handle_navigation_key",
                "on_key_enter",
                "on_mouse_scroll",
                "on_mouse_press",
            ),
            True,
        ),
    ],
)
def test_migrated_overlays_keep_focus_surface_and_public_methods(
    overlay_type: type[object],
    method_names: tuple[str, ...],
    has_reset: bool,
) -> None:
    window = SimpleNamespace(
        width=1280,
        height=720,
        text_cache=None,
        editor_controller=SimpleNamespace(),
    )
    overlay = as_any(overlay_type)(as_any(window))
    if has_reset:
        getattr(overlay, "reset_for_open")()

    assert hasattr(overlay, "_focus_target")
    focus_before = getattr(overlay, "_focus_target")
    toggled = getattr(overlay, "toggle_focus")()
    assert toggled is True
    focus_after = getattr(overlay, "_focus_target")
    assert focus_before != focus_after
    assert focus_after in {"input", "results"}

    for method_name in method_names:
        method = getattr(overlay, method_name, None)
        assert callable(method), f"{overlay_type.__name__} missing callable method: {method_name}"
