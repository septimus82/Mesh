"""Milestone 22B: Mesh Studio's Ctrl+S while a field is being edited, and its scrolling left panel, checked in hidden
windows with Studio's own input events (clicks, typing, key presses, the mouse wheel).

    py -3.13 tooling/studio_workflow_polish.py ctrl_s OUT     a fresh starter project with an HD-2D room: a camera field
                                                             and a sound emitter's field typed into, Ctrl+S pressed
                                                             without leaving the field; closed and reopened; invalid
                                                             text and Ctrl+S; Esc; undo
    py -3.13 tooling/studio_workflow_polish.py left OUT       a starter project with 14 rooms and 30 objects: the left
                                                             panel at 1280 x 720 and 640 x 480 in an HD-2D and a 2D
                                                             room: scrolled with the wheel, every tool reached, what
                                                             is out of view not clickable, the 3D view not zoomed,
                                                             the right panel and the 2D palette scrolled on their own
    py -3.13 tooling/studio_workflow_polish.py navigation OUT a refused value with another box's valid one waiting,
                                                             then Ctrl+S; a refused value, then another object
                                                             clicked on the map, another panel, another room, undo

The player's settings file is OUT's own; nothing is played aloud (the project's master volume is 0)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
from hd2d_room_studio import SCENES, _silent, _write  # noqa: E402

LEFT_X = 100  # over the left panel
BLANK = "   "  # a name Studio refuses ("A name can't be empty.")


def _project(out: Path, *, rooms: int = 0, objects: int = 0) -> Path:
    """A fresh starter project, with an HD-2D room "Meadow" (40 x 30 m) and ``rooms`` more 2D rooms, ``objects``
    more objects in its list; saved."""
    from engine.studio_project import Project

    project = out / "game"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    if objects:
        path = project / "assets/prefabs.json"
        prefabs = json.loads(path.read_text(encoding="utf-8"))
        base = next(p for p in prefabs if isinstance(p, dict) and p.get("id") != "player")
        prefabs += [{**base, "id": f"extra_{i:02d}", "display_name": f"Extra object {i:02d}"} for i in range(objects)]
        path.write_text(json.dumps(prefabs, indent=1), encoding="utf-8")
    p = Project.open(project, "packs/core_regions/worlds/main.json")
    assert p is not None, "a Studio project"
    p.add_hd2d_room("Meadow", 40, 30)
    for i in range(rooms):
        p.add_room(f"Room {i + 1:02d}")
    if rooms:  # a tall tileset (8 x 16 tiles): more than the palette shows, to scroll
        from PIL import Image  # noqa: PLC0415

        tall = out / "tall_tiles.png"
        image = Image.new("RGBA", (256, 512))
        for i in range(128):
            image.paste((40 + i, 200 - i, 90 + (i * 7) % 120, 255), (i % 8 * 32, i // 8 * 32, i % 8 * 32 + 32, i // 8 * 32 + 32))
        image.save(tall)
        p.import_tileset(tall, 32, "Tall")
    p.save()
    return project


def _left_buttons(d: Any) -> list[Any]:
    return [w for w in d.studio.ui.walk_widgets() if isinstance(getattr(w, "text", None), str)
            and hasattr(w, "on_click") and w.rect.left < 230 and w.rect.top < d.window.height - 44]


def _ctrl(d: Any, symbol: int) -> None:
    k = d.arcade.key
    d.window.dispatch_event("on_key_press", symbol, k.MOD_CTRL)
    d.window.dispatch_event("on_key_release", symbol, k.MOD_CTRL)
    d.frame()


def _type_only(d: Any, key: str, text: str) -> None:
    """Click the field, select what is in it and type: no Enter, the field stays focused."""
    d.frame()  # (laid out: a panel just rebuilt has its fields at 0, 0 until drawn)
    field = d.studio._focusable[key]
    r = field.rect
    assert field.parent is not None and r.bottom > 0, f"the field {key!r} isn't on screen ({r})"
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    _ctrl(d, d.arcade.key.A)
    d.window.dispatch_event("on_text", text)
    d.frame()


def _state(d: Any, key: str | None = None) -> dict[str, Any]:
    studio = d.studio
    cam = studio.hd2d.camera
    field = studio._focusable.get(key) if key else None
    return {"message": studio.message, "message_ok": studio.message_ok, "unsaved": sorted(studio.project.dirty),
            "field_text": getattr(field, "text", None), "field_focused": bool(getattr(field, "active", False)),
            "view": [round(v, 4) for v in (*cam.target, cam.distance, cam.yaw, cam.pitch)]}


def _on_disk(project: Path, entity_id: str) -> dict[str, Any]:
    """The object as the saved room file has it: its name and its sound's volume (None: not in the file)."""
    entity = next((e for e in _room_file(project, "meadow")["entities"] if e.get("id") == entity_id), None)
    if entity is None:
        return {"in_file": False}
    return {"in_file": True, "name": entity.get("name"),
            "volume": ((entity.get("behaviour_config") or {}).get("SoundEmitter") or {}).get("volume")}


def _room_file(project: Path, room: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((project / SCENES / f"{room}.json").read_text(encoding="utf-8"))
    return data


def _press_left(d: Any, text: str) -> None:
    """Click a left-panel button, scrolling the left panel (down, then up) with the wheel as a person would."""
    for direction in (-1, 1):
        for _ in range(40):
            for w in _left_buttons(d):
                if w.text == text and w.rect.bottom >= 0:
                    d.click(w.rect.left + w.rect.width / 2, w.rect.bottom + w.rect.height / 2)
                    return
            before = getattr(d.studio, "left_scroll", None)
            d.window.dispatch_event("on_mouse_scroll", LEFT_X, d.window.height / 2, 0, direction)
            d.frame()
            if getattr(d.studio, "left_scroll", None) == before:
                break
    raise AssertionError(f"no left-panel button {text!r} reachable")


def ctrl_s(out: Path) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project = _project(out)
    report: dict[str, Any] = {}
    k = None
    d = StudioDriver(project)
    try:
        k = d.arcade.key
        _press_left(d, "Meadow")
        d.button("Camera and sun...")
        view_before = _state(d)["view"]
        _type_only(d, "cam_pitch", "38")
        typed = _state(d, "cam_pitch")
        saves: list[int] = []
        project_save = d.studio.project.save

        def counted() -> list[str]:
            saves.append(1)
            written: list[str] = project_save()
            return written

        d.studio.project.save = counted  # (counts the files written: Ctrl+S saves once)
        _ctrl(d, k.S)
        d.studio.project.save = project_save
        typed["project_saves_on_ctrl_s"] = len(saves)
        report["camera"] = {"typed": typed, "after_ctrl_s": _state(d, "cam_pitch"), "view_before": view_before,
                            "on_disk_pitch": _room_file(project, "meadow")["settings"]["hd2d"]["camera"]["pitch"]}
        d.frame(20)  # time for any held key to move the view
        report["camera"]["view_after_frames"] = _state(d)["view"]
        # a sound emitter (set up through Studio's own edit path), then its inspector field
        d.studio._edit(lambda s: ops.paste_entity(s, "meadow", {"name": "Brook"}, 640.0, 480.0)[0], "A brook.")
        brook = next(e["id"] for e in ops.entities(d.studio.project.scene()) if e.get("name") == "Brook")
        d.studio._edit(lambda s: ops.set_sound_emitter(s, brook, volume=0.8), "A sound.")
        d.studio.select(brook)
        d.frame(2)
        d.button("Save")
        report["brook_saved"] = _on_disk(project, brook)
        _type_only(d, "sound_volume", "35")
        _ctrl(d, k.S)
        report["sound"] = {"after_ctrl_s": _state(d, "sound_volume"), "on_disk": _on_disk(project, brook)}
        # invalid text, with another change waiting to be saved
        d.studio._edit(lambda s: ops.rename_entity(s, brook, "Stream"), "Renamed.")
        _type_only(d, "sound_volume", "loud")
        _ctrl(d, k.S)
        report["invalid"] = {"after_ctrl_s": _state(d, "sound_volume"), "on_disk": _on_disk(project, brook)}
        d.window.dispatch_event("on_key_press", k.ESCAPE, 0)
        d.window.dispatch_event("on_key_release", k.ESCAPE, 0)
        d.frame()
        report["after_escape"] = _state(d, "sound_volume")
        _ctrl(d, k.S)
        report["saved_after_escape"] = {"state": _state(d, "sound_volume"), "on_disk": _on_disk(project, brook)}
        d.button("Undo")
        report["undo_after"] = {"name": ops.find_entity(d.studio.project.scene(), brook).get("name"),
                                "unsaved": sorted(d.studio.project.dirty)}
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        _press_left(d, "Meadow")
        report["reopened"] = {"pitch": ops.hd2d_camera_of(d.studio.project.scene())["pitch"],
                              "objects": [e.get("name") for e in ops.entities(d.studio.project.scene())]}
    finally:
        d.close()
    return report


def _resize(d: Any, w: int, h: int) -> None:
    d.window.set_size(w, h)
    d.window.dispatch_event("on_resize", w, h)
    d.frame(3)


def left(out: Path) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    project = _project(out, rooms=14, objects=30)
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        for size in ((1280, 720), (640, 480)):
            _resize(d, *size)
            _press_left(d, "Meadow")
            name = f"{size[0]}x{size[1]}"
            buttons = _left_buttons(d)
            hidden = [w for w in buttons if w.rect.bottom < 0]
            entry: dict[str, Any] = {"left_buttons_in_ui": len(buttons), "below_the_window": [w.text for w in hidden][:6],
                                     "below_count": len(hidden)}
            d.picture(pics / f"left_{name}_top.png")
            last = "Extra object 29"
            target = next((w for w in buttons if w.text == last), None)
            if target is not None and target.rect.bottom < 0:  # in the UI though out of the window: clicked there?
                d.click(target.rect.left + target.rect.width / 2, target.rect.bottom + target.rect.height / 2)
                armed = d.studio.place_prefab
                entry["clicked_below_the_window"] = (armed or {}).get("id") if isinstance(armed, dict) else armed
                d.window.dispatch_event("on_key_press", d.arcade.key.ESCAPE, 0)
                d.window.dispatch_event("on_key_release", d.arcade.key.ESCAPE, 0)
                d.frame()
            entry["last_object_in_ui_before_scrolling"] = d.has_button(last)
            d.click(LEFT_X, -20)  # below the window, where it would be if it were laid out there
            armed = d.studio.place_prefab
            entry["click_below_the_window_armed"] = (armed or {}).get("id") if isinstance(armed, dict) else armed
            view, right = _state(d)["view"], d.studio.panel_scroll
            d.window.dispatch_event("on_mouse_scroll", LEFT_X, d.window.height / 2, 0, -3)
            d.frame()
            entry["wheel_over_left"] = {"left_scroll": getattr(d.studio, "left_scroll", None),
                                        "view_unchanged": _state(d)["view"] == view,
                                        "right_scroll_unchanged": d.studio.panel_scroll == right}
            try:
                _press_left(d, last)
                armed = d.studio.place_prefab
                entry["reached_last_object"] = (armed or {}).get("id") if isinstance(armed, dict) else armed
                d.picture(pics / f"left_{name}_scrolled.png")
                d.window.dispatch_event("on_key_press", d.arcade.key.ESCAPE, 0)
                d.window.dispatch_event("on_key_release", d.arcade.key.ESCAPE, 0)
                d.frame()
            except AssertionError as err:
                entry["reached_last_object"] = f"not reachable: {err}"
            report[name] = entry
        _resize(d, 1280, 720)
        report["tooltip_scrolled_out"] = _tooltip_check(d)
        report["palette_2d"] = _palette_check(d)
    finally:
        d.close()
    return report


def _tooltip_check(d: Any) -> dict[str, Any]:
    """A 3D view button's tooltip: shown over it, not over where it was once it is scrolled out of the panel."""
    def turn_left() -> Any:
        return next((w for w in d.studio.ui.walk_widgets() if getattr(w, "text", None) == "Turn left"), None)

    assert d._scroll_panels(turn_left), "Turn left"
    d.frame()
    r = turn_left().rect
    at = (r.left + r.width / 2, r.bottom + r.height / 2)
    shown = d.studio.hd2d.tooltip(*at)
    for _ in range(20):
        if turn_left() is None:
            break
        d.window.dispatch_event("on_mouse_scroll", LEFT_X, d.window.height / 2, 0, -1)
        d.frame()
    return {"over_it": shown, "scrolled_out": turn_left() is None, "over_where_it_was": d.studio.hd2d.tooltip(*at)}


def _palette_check(d: Any) -> dict[str, Any]:
    """A 2D room: the wheel over the tile palette scrolls the palette, elsewhere over the panel the panel."""
    _press_left(d, "Start")
    while d.studio.tilesets[d.studio.sheet]["name"] != "Tall":
        d.button(d.studio.tilesets[d.studio.sheet]["name"], prefix=True)  # the tileset button: the next tileset
    assert d._scroll_panels(lambda: d.studio._sheet_space is not None), "the palette"
    d.frame()
    tileset, _px, cols, rows = d.studio._sheet_geometry()
    space = d.studio._sheet_space.rect
    before = (list(d.studio.sheet_scroll), d.studio.left_scroll)
    d.window.dispatch_event("on_mouse_scroll", space.left + 10, space.top - 10, 0, -1)
    d.frame()
    over_palette = (list(d.studio.sheet_scroll), d.studio.left_scroll)
    d.window.dispatch_event("on_mouse_scroll", LEFT_X, d.window.height - 80, 0, 1)  # over the rooms: up
    d.frame()
    return {"palette_rows": [rows, tileset["rows"]], "before": before, "wheel_over_palette": over_palette,
            "wheel_over_rooms": (list(d.studio.sheet_scroll), d.studio.left_scroll)}


def _put_back(d: Any, key: str) -> None:
    """Click the box and press Esc: a refused value put back."""
    d.frame()
    field = d.studio._focusable[key]
    r = field.rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    d.window.dispatch_event("on_key_press", d.arcade.key.ESCAPE, 0)
    d.window.dispatch_event("on_key_release", d.arcade.key.ESCAPE, 0)
    d.frame()


def _click_object(d: Any, entity_id: str) -> None:
    """Click an object where it is on the 2D map."""
    entity = next(e for e in d.studio.project.scene()["entities"] if e.get("id") == entity_id)
    d.studio._apply_camera()
    x, y, *_ = d.window.camera.project((float(entity["x"]), float(entity["y"])))
    d.click(float(x), float(y))


def _scale_typed(d: Any) -> dict[str, Any]:
    """Where Studio is, what it says, and whether the refused blank name is still to be seen in its box."""
    studio = d.studio
    return {"room": studio.project.current, "panel": studio.panel, "selected": studio.selected,
            "message": studio.message, "message_ok": studio.message_ok, "unsaved": sorted(studio.project.dirty),
            "blank_name_in_its_box": any(f.text == BLANK for f, _, _ in studio._fields)}


def navigation(out: Path) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project = _project(out)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        k = d.arcade.key
        # two boxes waiting: the first refused, the second fine (an HD-2D room's sound emitter)
        _press_left(d, "Meadow")
        d.studio._edit(lambda s: ops.paste_entity(s, "meadow", {"name": "Brook"}, 640.0, 480.0)[0], "A brook.")
        brook = next(e["id"] for e in ops.entities(d.studio.project.scene()) if e.get("name") == "Brook")
        d.studio._edit(lambda s: ops.set_sound_emitter(s, brook, volume=0.8, radius=64), "A sound.")
        d.studio.select(brook)
        d.button("Save")
        _type_only(d, "sound_volume", "loud")
        _type_only(d, "sound_radius", "3")
        _ctrl(d, k.S)
        on_disk = _on_disk(project, brook)
        report["two_boxes"] = {"after_ctrl_s": _state(d, "sound_volume"), "on_disk": on_disk,
                               "radius_now": ops.sound_emitter_of(ops.find_entity(d.studio.project.scene(), brook))}
        _put_back(d, "sound_volume")
        d.button("Save")
        # a refused value, then leaving it: another object, another panel, another room, undo
        _press_left(d, "Start")
        _press_left(d, "Sign")  # a second object, placed with the Objects list and a click on the map
        d.studio._apply_camera()
        x, y, *_ = d.window.camera.project((224.0, 256.0))
        d.click(float(x), float(y))
        others = [e["id"] for e in d.studio.project.scene()["entities"] if e.get("tag") != "player"
                  and e.get("prefab_id") != "player"]
        a, b = others[0], others[1]
        d.button("Save")
        for leave in ("another object", "another panel", "another room", "undo"):
            _click_object(d, a)
            d.frame(2)
            before = {"selected": d.studio.selected}
            _type_only(d, "name", BLANK)
            if leave == "another object":
                _click_object(d, b)
            elif leave == "another panel":
                d.button("Lighting")
            elif leave == "another room":
                _press_left(d, "Meadow")
            else:
                d.studio._edit(lambda s: ops.rename_entity(s, a, "Renamed"), "Renamed.")  # (something to undo)
                _type_only(d, "name", BLANK)
                d.button("Undo")
            d.frame(2)
            left = _scale_typed(d)
            d.button("Save")
            report[leave] = {"before": before, "after": left, "save": _scale_typed(d)}
            # the box put back (click it, Esc), then where it was, for the next case
            if "name" in d.studio._focusable and d.studio._focusable["name"].text == BLANK:
                _put_back(d, "name")
                report[leave]["put_back"] = _scale_typed(d)
            if d.studio.project.current != "start":
                _press_left(d, "Start")
            if d.studio.panel != "inspect":
                d.button("Lighting")  # (toggles back)
        # a valid value waiting, then another object: taken, and Studio goes there as before
        _click_object(d, a)
        d.frame(2)
        _type_only(d, "name", "Guide Two")
        _click_object(d, b)
        d.frame(2)
        report["valid_then_another_object"] = {**_scale_typed(d),
                                               "name_of_first": ops.find_entity(d.studio.project.scene(), a).get("name")}
    finally:
        d.close()
    return report


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = {"ctrl_s": lambda: ctrl_s(out), "left": lambda: left(out), "navigation": lambda: navigation(out)}[phase]()
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:8000])


if __name__ == "__main__":
    main()
