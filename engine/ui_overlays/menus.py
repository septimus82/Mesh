"""Menu and modal UI overlays — backward-compatible re-export shim.

All classes have been split into individual modules for maintainability:
- help_overlay.py          → HelpOverlay
- settings_overlay.py      → SettingsOverlay
- main_menu_overlay.py     → MainMenuOverlay, get_menu_legend
- demo_complete_overlay.py → DemoCompleteOverlay, maybe_trigger_demo_complete_endcap
- dialogue_box.py          → DialogueBox
- shop_panel.py            → ShopPanel
- character_panel.py       → CharacterPanel
- game_over_screen.py      → GameOverScreen
- pause_menu.py            → PauseMenu

Import from the individual modules for new code. This file re-exports them
for backward compatibility.
"""

from __future__ import annotations

# Re-export all public symbols so existing ``from .menus import X`` still works.
from .help_overlay import HelpOverlay as HelpOverlay
from .settings_overlay import SettingsOverlay as SettingsOverlay
from .main_menu_overlay import (
    MainMenuOverlay as MainMenuOverlay,
    get_menu_legend as get_menu_legend,
)
from .demo_complete_overlay import (
    DEMO_COMPLETE_ENDCAP_SECONDS as DEMO_COMPLETE_ENDCAP_SECONDS,
    DemoCompleteOverlay as DemoCompleteOverlay,
    maybe_trigger_demo_complete_endcap as maybe_trigger_demo_complete_endcap,
)
from .dialogue_box import DialogueBox as DialogueBox
from .shop_panel import ShopPanel as ShopPanel
from .character_panel import CharacterPanel as CharacterPanel
from .game_over_screen import GameOverScreen as GameOverScreen
from .pause_menu import PauseMenu as PauseMenu

__all__ = [
    "CharacterPanel",
    "DEMO_COMPLETE_ENDCAP_SECONDS",
    "DemoCompleteOverlay",
    "DialogueBox",
    "GameOverScreen",
    "HelpOverlay",
    "MainMenuOverlay",
    "PauseMenu",
    "SettingsOverlay",
    "ShopPanel",
    "get_menu_legend",
    "maybe_trigger_demo_complete_endcap",
]
