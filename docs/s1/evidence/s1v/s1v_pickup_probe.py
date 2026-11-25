"""S1v: why did the first pickup in the exported adventure build do nothing? Press E at the potion 3 times."""
import importlib.util
import json
import runpy
import sys
from pathlib import Path

GAME, HIDDEN = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(GAME))
import pyglet  # noqa: E402

pyglet.options["audio"] = ("silent",)
spec = importlib.util.spec_from_file_location("hidden_windows", HIDDEN)
hw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw)
hw.no_activate()
import engine.optional_arcade as oa  # noqa: E402

_shown = oa.arcade.Window.__init__
oa.arcade.Window.__init__ = lambda self, *a, **k: _shown(self, *a, **{**k, "visible": False})
from engine.game import GameWindow  # noqa: E402

K = oa.arcade.key


def drive(window):
    window._allow_dispatch_event = True
    sc = window.scene_controller

    def step(n=1):
        for _ in range(n):
            window.dispatch_event("on_update", 1 / 60)
    step(5)
    from engine.inventory import get_or_create_inventory
    pot = next(s for s in sc.all_sprites if s.mesh_name == "Potion")
    h = sc._find_player_sprite()
    for approach in ("teleport_below", "teleport_below_walk_up"):
        h.center_x, h.center_y = pot.center_x, pot.center_y - 40
        step(3)
        if approach.endswith("walk_up"):
            window.dispatch_event("on_key_press", K.UP, 0); step(6); window.dispatch_event("on_key_release", K.UP, 0); step(2)
        for i in range(2):
            window.dispatch_event("on_key_press", K.E, 0); step(1); window.dispatch_event("on_key_release", K.E, 0); step(20)
            still = any(s.mesh_name == "Potion" for s in sc.all_sprites)
            print("S1V", json.dumps({"approach": approach, "press": i + 1, "player": [round(h.center_x), round(h.center_y)],
                                     "potion": [pot.center_x, pot.center_y], "potion_still_there": still,
                                     "potions": get_or_create_inventory(window.game_state_controller.state.values).get_count("healing_potion"),
                                     "dialogue_open": bool(getattr(window.ui_controller, "dialogue_box", None) and getattr(window.ui_controller.dialogue_box, "visible", False))}), flush=True)
            if not still:
                window.close()
                return
    window.close()


GameWindow.run = drive
try:
    runpy.run_path(str(GAME / "main.py"), run_name="__main__")
except SystemExit:
    pass
