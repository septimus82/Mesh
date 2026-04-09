from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from engine.game import GameWindow
    from engine.ui import UIElement


def _register_default_overlay(
    window: "GameWindow",
    attr_name: str,
    overlay: "UIElement",
) -> None:
    setattr(window, attr_name, overlay)
    window.register_ui_element(overlay)


def init_default_overlays(
    window: "GameWindow",
    *,
    PlayerHUD: type["UIElement"],
    GameOverScreen: type["UIElement"],
    PauseMenu: type["UIElement"],
    HelpOverlay: type["UIElement"],
    InspectorOverlay: type["UIElement"],
    GoldenSliceVariantPickerOverlay: type["UIElement"],
    GoldenSliceDemoHUDStripOverlay: type["UIElement"],
    DevBrowserOverlay: type["UIElement"],
) -> None:
    _register_default_overlay(window, "player_hud", PlayerHUD(window))
    _register_default_overlay(window, "game_over_screen", GameOverScreen(window))
    _register_default_overlay(window, "pause_menu", PauseMenu(window))
    _register_default_overlay(window, "help_overlay", HelpOverlay(window))
    _register_default_overlay(window, "inspector_overlay", InspectorOverlay(window))
    _register_default_overlay(
        window,
        "variant_picker_overlay",
        GoldenSliceVariantPickerOverlay(window),
    )
    _register_default_overlay(
        window,
        "golden_slice_demo_hud",
        GoldenSliceDemoHUDStripOverlay(window),
    )
    _register_default_overlay(window, "dev_browser_overlay", DevBrowserOverlay(window))
