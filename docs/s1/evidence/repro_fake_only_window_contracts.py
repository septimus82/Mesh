"""S1-0 part B section 1: features that read a window attribute only test doubles have (real hidden GameWindow).

Each check uses the real window and the production function or overlay; nothing is patched.

A. PlayerHUD._draw_stats (called by PlayerHUD.draw every frame) reads ``window.player``. The real window has no
   ``player`` (the player is found through scene_controller._find_player_sprite()). So the HUD's health / level panel
   never builds, even for a player with Health. Tests pass a fake window with ``player=...``.
B. Console ``quest`` / ``quest active`` call ``get_all_quests()`` items' ``.title`` and ``get_quests_by_state()``, which
   exist only on the lightweight engine.quest_manager.QuestManager. The game uses engine.quests.QuestManager.
C. The plugin API's PluginContext.console / .asset_manager read ``window.console`` / ``window.asset_manager``; the real
   names are console_controller / assets.
D. Debug panels read ``window.quest_runner`` / ``window.cutscene_runner``; the real ones are quest_manager /
   cutscene_controller.
E. MenuBarOverlay / ContextMenuOverlay (registered on every window) draw only when ``window.editor_mode_controller``
   exists; the real one is editor_controller.

Exits 1 when any of A-C reproduces (D and E are dev/legacy-editor only and are reported, not counted).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hidden_game import HERO, hidden_game, scene  # noqa: E402

hero = dict(HERO, behaviours=["PlayerController", "Health"], behaviour_config={"Health": {"max_hp": 30, "hp": 30}})
defects = []

with hidden_game({"Yard": scene("Yard", hero)}) as (window, _paths, _tmp):
    window.on_update(1 / 60)
    player = window.scene_controller._find_player_sprite()
    print("player sprite found by the scene:", getattr(player, "mesh_name", None), "| window has 'player':",
          hasattr(window, "player"))

    # A
    hud = window.player_hud
    hud._draw_stats()
    vm = hud.get_hud_view_model()
    print("A) HUD view model after _draw_stats:", vm)
    if vm is None and player is not None:
        defects.append("A: the HUD health/level panel never builds (window.player missing)")

    # B
    console = window.console_controller
    for command in ("quest", "quest active"):
        before = len(console.lines)
        try:
            console.execute_command(command)
            outcome = "ok: " + " | ".join(str(x) for x in console.lines[before:])[:160]
        except Exception as exc:  # noqa: BLE001
            outcome = f"raised {type(exc).__name__}: {exc}"
            defects.append(f"B: console '{command}' raised {type(exc).__name__}")
        print(f"B) console {command!r}: {outcome}")
    qm = window.game_state_controller.quests
    print("B) game_state_controller.quests is window.quest_manager:", qm is window.quest_manager, "|",
          type(qm).__module__, "| has get_quests_by_state:", hasattr(qm, "get_quests_by_state"))

    # C
    from engine.plugin_system import PluginContext

    ctx = PluginContext(window)
    print(f"C) PluginContext.console={ctx.console!r} (window.console_controller exists: "
          f"{hasattr(window, 'console_controller')}) | asset_manager={ctx.asset_manager!r} "
          f"(window.assets exists: {hasattr(window, 'assets')})")
    if ctx.console is None and ctx.asset_manager is None:
        defects.append("C: the plugin context's console and asset_manager are always None")

    # D
    from engine.editor.debug.debug_panels_state import get_cutscene_state, get_quest_diagnostics

    print(f"D) debug quest diagnostics: {get_quest_diagnostics(window)!r} | cutscene state: "
          f"{get_cutscene_state(window)!r} (real: quest_manager={type(window.quest_manager).__name__}, "
          f"cutscene_controller={type(window.cutscene_controller).__name__})")

    # E
    print("E) window has editor_mode_controller:", hasattr(window, "editor_mode_controller"),
          "| editor_controller:", type(window.editor_controller).__name__,
          "| menu_bar_overlay registered:", hasattr(window, "menu_bar_overlay"))

if defects:
    print("DEFECT REPRODUCED:", "; ".join(defects))
    sys.exit(1)
print("not reproduced")
