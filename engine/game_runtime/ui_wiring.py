from __future__ import annotations

from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from engine.ui import UIElement


class _HasUIOverlays(Protocol):
    player_hud: "UIElement"
    game_over_screen: "UIElement"
    pause_menu: "UIElement"
    help_overlay: "UIElement"
    inspector_overlay: "UIElement"
    variant_picker_overlay: "UIElement"
    golden_slice_demo_hud: "UIElement"
    dev_browser_overlay: "UIElement"

    def register_ui_element(self, element: "UIElement") -> None: ...


class _OverlayFactory(Protocol):
    def __call__(self, window: _HasUIOverlays) -> "UIElement": ...


def init_default_overlays(
    window: _HasUIOverlays,
    *,
    PlayerHUD: _OverlayFactory,
    GameOverScreen: _OverlayFactory,
    PauseMenu: _OverlayFactory,
    HelpOverlay: _OverlayFactory,
    InspectorOverlay: _OverlayFactory,
    GoldenSliceVariantPickerOverlay: _OverlayFactory,
    GoldenSliceDemoHUDStripOverlay: _OverlayFactory,
    DevBrowserOverlay: _OverlayFactory,
) -> None:
    window.player_hud = PlayerHUD(window)
    window.game_over_screen = GameOverScreen(window)
    window.pause_menu = PauseMenu(window)
    window.help_overlay = HelpOverlay(window)
    window.inspector_overlay = InspectorOverlay(window)
    window.variant_picker_overlay = GoldenSliceVariantPickerOverlay(window)
    window.golden_slice_demo_hud = GoldenSliceDemoHUDStripOverlay(window)
    window.dev_browser_overlay = DevBrowserOverlay(window)

    window.register_ui_element(window.player_hud)
    window.register_ui_element(window.game_over_screen)
    window.register_ui_element(window.pause_menu)
    window.register_ui_element(window.help_overlay)
    window.register_ui_element(window.inspector_overlay)
    window.register_ui_element(window.variant_picker_overlay)
    window.register_ui_element(window.golden_slice_demo_hud)
    window.register_ui_element(window.dev_browser_overlay)
