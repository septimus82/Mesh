"""S1v #654: a talking merchant (the template's Guide, which has Dialogue) given Shopkeeper (+ optionally Interactable).

usage: py -3.13 s1v_talking_merchant.py author PROJECT        (Studio ops, in-process)
       py -3.13 s1v_talking_merchant.py play PROJECT HIDDEN   (main.py, hidden window)
"""
import json
import sys
from pathlib import Path

MODE, ROOT = sys.argv[1], Path(sys.argv[2])
STOCK = [{"item_id": "healing_potion", "price": 5, "quantity": 3}]

if MODE == "author":
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.studio_project import Project

    world = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["world_file"]
    held = project_ownership.acquire(ROOT, project_ownership.STUDIO)
    try:
        proj = Project.open(ROOT, world)
        key = proj.current
        guide = next(e["id"] for e in proj.scene(key)["entities"] if e.get("name") == "Guide")
        proj.edit_scene(lambda s: ops.add_behaviour(s, guide, "Vendor"))
        proj.edit_scene(lambda s: ops.set_behaviour_param(s, guide, "Vendor", "stock", STOCK))
        proj.edit_scene(lambda s: ops.add_behaviour(s, guide, "Interactable"))
        proj.edit_scene(lambda s: ops.set_behaviour_param(s, guide, "Interactable", "interact_event", "open_shop"))
        prefab = next((p for p in proj._read_prefabs() if str(p.get("id")).lower() == "person"), None)
        box = {}

        def put(s):
            if prefab is not None:
                s2, eid = ops.place_prefab(s, key, prefab, 128, 700)
            else:
                s2, eid = ops.place_blank(s, key, "Trader", 128, 700)
            box["id"] = eid
            return s2
        proj.edit_scene(put)
        proj.edit_scene(lambda s: ops.add_behaviour(s, box["id"], "Vendor"))
        proj.edit_scene(lambda s: ops.set_behaviour_param(s, box["id"], "Vendor", "stock", STOCK))
        proj.save(owner=held)
        doc = proj.scene(key)
        print("authored:", [(e.get("name"), e.get("behaviours")) for e in doc["entities"] if e["id"] in (guide, box["id"])])
    finally:
        held.release()
    sys.exit(0)

import importlib.util  # noqa: E402
import runpy  # noqa: E402

import pyglet  # noqa: E402

pyglet.options["audio"] = ("silent",)
spec = importlib.util.spec_from_file_location("hidden_windows", sys.argv[3])
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

    def press(k):
        window.dispatch_event("on_key_press", k, 0); step(1); window.dispatch_event("on_key_release", k, 0); step(20)
    step(5)
    box = window.ui_controller.dialogue_box
    for name in ("Guide", "Person", "MerchantPlain"):
        t = next(s for s in sc.all_sprites if s.mesh_name == name)
        h = sc._find_player_sprite()
        h.center_x, h.center_y = t.center_x, t.center_y - 40
        step(3)
        seen = []
        for i in range(4):
            press(K.E)
            seen.append({"press": i + 1, "shop": bool(window.ui_controller.shop_panel.visible),
                         "line": ((box.get_current_entry() or {}).get("text", "")[:30] if box is not None else None), "dlg_active": bool(getattr(window, "dialogue_active", False) or getattr(getattr(window, "dialogue_controller", None), "active", False))})
            if window.ui_controller.shop_panel.visible:
                break
        print("S1V", json.dumps({"merchant": name, "behaviours": [type(b).__name__ for b in t.mesh_behaviours_runtime], "presses": seen}), flush=True)
        if window.ui_controller.shop_panel.visible:
            window.ui_controller.shop_panel.close(); step(30)
        while box is not None and getattr(box, "visible", False):
            press(K.E)
    window.close()


GameWindow.run = drive
try:
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
except SystemExit:
    pass
