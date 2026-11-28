"""S1-0 part B section 4: two save systems; the legacy main menu's "Continue" reads the one the game never writes.

* SaveManager (engine/save_manager.py, slots under the save folder): what F5 / F9, the pause menu and the console use.
  Every real GameWindow has one, so the F5 handler (capture_key_router_handlers_global._handle_savegame_save) always
  takes the SaveManager branch.
* engine/savegame.py SaveGameV1 at saves/save_1.json (CWD-relative): written ONLY by that handler's fallback branch
  when the window has no save_manager, i.e. only under test doubles.
* The legacy main menu (engine/ui_overlays/main_menu_overlay.py _has_continue / _handle_continue) offers and loads
  "Continue" from savegame.py's save_1.json.

Repro (real hidden GameWindow): quick-save through the real F5 handler, then ask the real MainMenuOverlay whether it
offers Continue. The process CWD is the checkout (the hidden-game helper's rule), so save_1.json is looked up there;
the script reports whether such a file exists first and writes nothing outside its temp folder.

Exits 1 when a quick save exists but Continue is not offered.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, hidden_game, scene  # noqa: E402

with hidden_game({"Yard": scene("Yard", HERO)}) as (window, _paths, tmp):
    from engine.input_runtime.capture_key_router_handlers_global import _handle_savegame_save
    from engine.savegame import resolve_savegame_path
    from engine.ui_overlays.main_menu_overlay import MainMenuOverlay

    os.environ.pop("PYTEST_CURRENT_TEST", None)
    legacy_path = resolve_savegame_path()
    print("savegame.py path (CWD-relative):", legacy_path.as_posix(), "| exists before:", legacy_path.exists())
    _handle_savegame_save(window)  # the F5 handler
    slots = sorted(p.name for p in (tmp / "saves").glob("*.json"))
    print("SaveManager slots after F5:", slots)
    menu = MainMenuOverlay(window)
    offered = menu._has_continue()
    print("legacy main menu offers Continue:", offered, "| items:", [label for label, _ in menu._items()][:3])
    defect = bool(slots) and not offered and not legacy_path.exists()

if defect:
    print("DEFECT REPRODUCED: a quick save exists but the main menu's Continue looks only at savegame.py's save_1.json")
    sys.exit(1)
print("not reproduced")
