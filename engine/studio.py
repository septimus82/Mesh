"""Mesh Studio: the visual editor for a project.

Layout: a top bar (play, save, undo), rooms and objects on the left, the inspector on
the right, the map in the middle. Click selects, drag moves, right-click opens actions.
Every change goes through engine.studio_project / engine.project_ops; after each change
the map is rebuilt from the document, so what you see is always what will be saved.

The Studio sits on top of the window's event stack. While editing it consumes every
event, so none of the game's (or the legacy editor's) input handling runs. While
play-testing it passes events through to the game, except F4, which stops the test.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Callable

import engine.optional_arcade as optional_arcade
from engine import project_ops as ops
from engine.scene_loader import document_key
from engine.studio_project import Project
from engine.world_controller import WorldController

gui = optional_arcade.gui()

TOP_H, STATUS_H, LEFT_W, RIGHT_W = 44, 26, 230, 330
GRID = 16
PAN_SPEED = 600.0
MAX_PICKER_ROWS = 10

C_BG = (30, 32, 38)
C_PANEL = (38, 41, 49)
C_TEXT = (220, 224, 232)
C_MUTED = (140, 146, 160)
C_ERROR = (255, 120, 110)
C_OK = (130, 210, 150)
C_SELECT = (90, 200, 255)
C_SPAWN = (120, 230, 140)


def _style(bg: tuple[int, int, int], fg: tuple[int, int, int] = C_TEXT) -> dict[str, Any]:
    base = gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=bg, border=None, border_width=0)
    return {
        "normal": base,
        "hover": gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=tuple(min(255, c + 22) for c in bg), border=None, border_width=0),
        "press": gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=tuple(max(0, c - 18) for c in bg), border=None, border_width=0),
        "disabled": gui.UIFlatButton.UIStyle(font_size=11, font_color=C_MUTED, bg=(48, 50, 58), border=None, border_width=0),
    }


S_BUTTON = _style((58, 63, 76))
S_ACTIVE = _style((48, 110, 170))
S_DANGER = _style((120, 52, 52))
S_PLAY = _style((44, 120, 70))
S_MENU = _style((52, 56, 68))


def _snap(value: float) -> float:
    return float(round(value / GRID) * GRID)


def _line_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Every cell on the straight line from ``a`` to ``b`` (inclusive): a fast drag leaves no gaps."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
    err, cells = dx + dy, []
    while True:
        cells.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return cells
        e2 = 2 * err
        if e2 >= dy:
            err, x0 = err + dy, x0 + sx
        if e2 <= dx:
            err, y0 = err + dx, y0 + sy


class _Field(gui.UIInputText):
    """Single-line text field whose caret lands at the end when you click into it.

    arcade.gui's own click handling leaves the caret at position 0, so clicking a
    field and typing would put the new text in front of the old.
    """

    def on_event(self, event: Any) -> bool | None:
        was_active = self.active
        handled = super().on_event(event)
        if self.active and not was_active:
            self.caret.position = len(self.text)
        return handled


class Studio:
    def __init__(self, window: Any, project: Project) -> None:
        self.window = window
        self.project = project
        self.mode = "edit"
        self.selected: str | None = None
        self.panel = "inspect"  # inspect | add_behaviour | new_room
        self.expanded: str | None = None
        self.picker_query = ""
        self.pending_door_at: tuple[float, float] | None = None
        self.place_prefab: dict[str, Any] | None = None
        self.drag: dict[str, Any] | None = None
        self.panning = False
        self.menu: tuple[float, float, list[tuple[str, Callable[[], None]]]] | None = None
        self.message, self.message_ok = "", True
        self.keys: set[int] = set()
        self.cam = [0.0, 0.0]
        self.zoom = 1.0
        self.mouse = (0.0, 0.0)
        self._fields: list[tuple[gui.UIInputText, str, Callable[[str], None]]] = []
        self._focus_after_build: str | None = None
        self._focusable: dict[str, gui.UIInputText] = {}
        self._labels: dict[str, optional_arcade.arcade.Text] = {}
        self.prefabs = self._load_prefabs()
        self.tool = "select"  # select | paint | erase
        self.brush: dict[str, Any] | None = None  # the tileset entry being painted: {gid, label, layer}
        self.stroke: dict[str, Any] | None = None  # a brush stroke in progress: {"cells": [...], "last": cell}
        self.tileset = project.tileset()
        self.tile_textures = self._load_tile_textures()
        self._palette_buttons: dict[int, Any] = {}

        self.ui = gui.UIManager(window)
        self.play_ui = gui.UIManager(window)
        window.push_handlers(self)
        self.ui.enable()
        self._reload(recenter=True)
        self._rebuild()
        self._say("Click an object to edit it. Right-click for actions. F4 plays your game.")

    # ==================================================================== document <-> map
    def _load_prefabs(self) -> list[dict[str, Any]]:
        path = self.project.root / "assets" / "prefabs.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [p for p in data if isinstance(p, dict) and isinstance(p.get("entity"), dict) and p.get("id")]

    def _load_tile_textures(self) -> dict[int, Any]:
        """Palette and preview textures, cut from the same tileset image the game loads."""
        from PIL import Image  # noqa: PLC0415

        ts = self.tileset
        image = Image.open(ts["image"]).convert("RGBA")
        columns = max(1, image.width // ts["tilewidth"])
        textures = {}
        for tile in ts["tiles"]:
            local = tile["gid"] - 1
            x, y = (local % columns) * ts["tilewidth"], (local // columns) * ts["tileheight"]
            crop = image.crop((x, y, x + ts["tilewidth"], y + ts["tileheight"]))
            textures[tile["gid"]] = optional_arcade.arcade.Texture(crop, hash=f"mesh-studio-tile-{ts['image']}-{local}")
        return textures

    def _install_documents(self) -> None:
        docs = self.window.scene_loader.documents
        docs.clear()
        for path, doc in self.project.documents().items():
            docs[document_key(path)] = doc
        self.window.world_controller = WorldController(copy.deepcopy(self.project.world))

    def _reload(self, recenter: bool = False) -> None:
        """Rebuild the map from the current room's document."""
        self._install_documents()
        self.window.load_scene(self.project.path(self.project.current))
        self.window.paused = True
        if recenter:
            self._center_on_room()
        self.window.set_caption(f"Mesh Studio - {self.project.label(self.project.current)}")

    def _center_on_room(self) -> None:
        """Frame the room: its whole map if it has one, otherwise its objects."""
        info = ops.map_info(self.project.scene())
        if info is not None:
            map_w, map_h = info["width"] * info["tilewidth"], info["height"] * info["tileheight"]
            self.cam = [map_w / 2, map_h / 2]
            left, right, bottom, top = self._map_rect()
            self.zoom = max(0.25, min(1.5, 0.95 * min((right - left) / map_w, (top - bottom) / map_h)))
            return
        points = [(float(e.get("x", 0)), float(e.get("y", 0))) for e in ops.entities(self.project.scene())]
        if points:
            xs, ys = zip(*points)
            self.cam = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
        else:
            self.cam = [0.0, 0.0]
        self.zoom = 1.0

    def _edit(self, change: Callable[[dict[str, Any]], dict[str, Any]], ok: str = "") -> bool:
        try:
            self.project.edit_scene(change)
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return False
        self._after_change(ok)
        return True

    def _after_change(self, ok: str = "") -> None:
        if self.selected and not self._entity(self.selected):
            self.selected = None
        self._reload()
        self._rebuild()
        if ok:
            self._say(ok)

    def _entity(self, entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id:
            return None
        try:
            return ops.find_entity(self.project.scene(), entity_id)
        except ops.OpError:
            return None

    # ==================================================================== geometry
    def _map_rect(self) -> tuple[float, float, float, float]:
        w, h = self.window.width, self.window.height
        return LEFT_W, w - RIGHT_W, STATUS_H, h - TOP_H

    def _in_map(self, x: float, y: float) -> bool:
        left, right, bottom, top = self._map_rect()
        return left <= x <= right and bottom <= y <= top

    def _apply_camera(self) -> None:
        left, right, bottom, top = self._map_rect()
        map_cx, map_cy = (left + right) / 2, (bottom + top) / 2
        scr_cx, scr_cy = self.window.width / 2, self.window.height / 2
        cam = self.window.camera
        cam.zoom = self.zoom
        cam.position = (self.cam[0] - (map_cx - scr_cx) / self.zoom, self.cam[1] - (map_cy - scr_cy) / self.zoom)

    def _to_world(self, x: float, y: float) -> tuple[float, float]:
        self._apply_camera()
        point = self.window.camera.unproject((x, y))
        return float(point[0]), float(point[1])

    def _sprites_by_id(self) -> dict[str, Any]:
        out = {}
        for sprite in self.window.scene_controller.all_sprites:
            data = getattr(sprite, "mesh_entity_data", None) or {}
            if data.get("id"):
                out[data["id"]] = sprite
        return out

    def _bounds(self, entity: dict[str, Any], sprite: Any) -> tuple[float, float, float, float]:
        if sprite is not None and entity.get("sprite") and getattr(sprite, "width", 0) > 2:
            return sprite.center_x, sprite.center_y, sprite.width, sprite.height
        return float(entity.get("x", 0)), float(entity.get("y", 0)), 32.0, 32.0

    def _entity_at(self, wx: float, wy: float) -> str | None:
        sprites = self._sprites_by_id()
        for entity in reversed(ops.entities(self.project.scene())):
            cx, cy, w, h = self._bounds(entity, sprites.get(entity.get("id")))
            if abs(wx - cx) <= w / 2 and abs(wy - cy) <= h / 2:
                return entity.get("id")
        return None

    # ==================================================================== actions
    def _say(self, text: str, ok: bool = True) -> None:
        self.message, self.message_ok = text, ok
        self._rebuild_status()

    def select(self, entity_id: str | None) -> None:
        self._flush_fields()
        if entity_id != self.selected:
            self.expanded = None
        self.selected = entity_id
        self.panel = "inspect"
        self._rebuild()

    def switch_room(self, key: str) -> None:
        self._flush_fields()
        self.project.current = key
        self.selected, self.place_prefab, self.panel, self.stroke = None, None, "inspect", None
        self._reload(recenter=True)
        self._rebuild()
        self._say(f"Editing {self.project.label(key)}.")

    def save(self) -> None:
        self._flush_fields()
        if not self.project.is_dirty:
            self._say("Nothing to save.")
            return
        try:
            written = self.project.save()
        except OSError as err:
            self._say(f"Couldn't save: {err}", ok=False)
            return
        self._rebuild()
        self._say(f"Saved {len(written)} file(s).")

    def undo(self) -> None:
        self._flush_fields()
        if self.project.undo():
            self._after_change("Undone.")
            self._reload(recenter=False)

    def redo(self) -> None:
        self._flush_fields()
        if self.project.redo():
            self._after_change("Redone.")

    def delete_selected(self) -> None:
        if self.selected:
            name = (self._entity(self.selected) or {}).get("name", "object")
            target = self.selected
            self.selected = None
            self._edit(lambda s: ops.remove_entity(s, target), f"Deleted {name}.")

    def arm_place(self, prefab: dict[str, Any]) -> None:
        self._flush_fields()
        self.place_prefab = None if self.place_prefab is prefab else prefab
        self._rebuild()
        if self.place_prefab:
            self._say(f"Click on the map to place {prefab.get('display_name', prefab['id'])}. Esc cancels.")

    # -------------------------------------------------------------------- map tools
    def use_select(self) -> None:
        self.tool, self.brush, self.stroke = "select", None, None
        self._rebuild()
        self._say("Select: click an object to edit it, drag to move it.")

    def pick_brush(self, tile: dict[str, Any]) -> None:
        self._flush_fields()
        self.place_prefab, self.stroke = None, None
        self.tool, self.brush = "paint", tile
        self._rebuild()
        kind = "blocks movement" if tile["layer"] == ops.WALLS else "walkable"
        self._say(f"Painting {tile['label']} ({kind}). Click or drag on the map. Esc goes back to Select.")

    def use_eraser(self) -> None:
        self._flush_fields()
        self.place_prefab, self.stroke = None, None
        self.tool, self.brush = "erase", None
        self._rebuild()
        self._say("Eraser: click or drag to remove tiles (walls and obstacles first, then the ground).")

    def add_map_here(self) -> None:
        try:
            self.project.add_map()
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return
        self._reload(recenter=True)
        self._rebuild()
        self._say("Added a map to this room. Pick a tile on the left and paint.")

    def _cell_under(self, x: float, y: float) -> tuple[int, int] | None:
        info = ops.map_info(self.project.scene())
        return ops.cell_at(info, *self._to_world(x, y)) if info is not None else None

    def _commit_stroke(self) -> None:
        """Apply the finished stroke as one edit, so one Undo takes back the whole stroke."""
        stroke, self.stroke = self.stroke, None
        if not stroke or not stroke["cells"]:
            return
        cells = list(dict.fromkeys(stroke["cells"]))
        if self.tool == "erase":
            self._edit(lambda s: ops.erase_tiles(s, cells), f"Erased {len(cells)} tile(s).")
        elif self.brush is not None:
            layer, gid = self.brush["layer"], self.brush["gid"]
            self._edit(lambda s: ops.paint_tiles(s, layer, cells, gid), f"Painted {len(cells)} tile(s).")

    def place_at(self, wx: float, wy: float) -> None:
        prefab, self.place_prefab = self.place_prefab, None
        created: list[str] = []

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, new_id = ops.place_prefab(scene, self.project.current, prefab, _snap(wx), _snap(wy))
            created.append(new_id)
            return out

        if self._edit(change, f"Placed {prefab.get('display_name', prefab['id'])}."):
            self.select(created[0])

    def add_behaviour(self, name: str) -> None:
        target = self.selected
        if target and self._edit(lambda s: ops.add_behaviour(s, target, name), f"Added {name}."):
            self.panel, self.expanded = "inspect", name
            self._rebuild()

    def remove_behaviour(self, name: str) -> None:
        target = self.selected
        if target:
            self._edit(lambda s: ops.remove_behaviour(s, target, name), f"Removed {name}.")

    def create_room(self, label: str) -> None:
        door_at, self.pending_door_at = self.pending_door_at, None
        origin = self.project.current
        try:
            key = self.project.add_room(label)
            if door_at is not None:
                # Inside the new room's wall border, with its arrival spot beside the player.
                self.project.link_rooms(origin, door_at, key, (256.0, 224.0))
        except ops.OpError as err:
            self.pending_door_at = door_at
            self._say(str(err), ok=False)
            return
        self.panel = "inspect"
        if door_at is not None:
            self._after_change(f"Created {label} with a door to it. Its door is next to its player.")
        else:
            self.switch_room(key)
            self._say(f"Created {label}. Add a door from another room to connect it.")

    def add_door_to(self, key: str, at: tuple[float, float]) -> None:
        target_scene = self.project.scene(key)
        player = next((e for e in ops.entities(target_scene) if e.get("tag") == "player"), None)
        # The far door goes above-right of that room's player, so its arrival spot (below the
        # door) lands at the player's height rather than off the map or in a wall.
        far = (float(player["x"]) + 128.0, float(player["y"]) + 96.0) if player else (256.0, 224.0)
        try:
            self.project.link_rooms(self.project.current, at, key, far)
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return
        self._after_change(f"Added a door to {self.project.label(key)}, and one back from it.")

    # ==================================================================== play-test
    def play(self) -> None:
        self._flush_fields()
        self.menu, self.place_prefab, self.drag = None, None, None
        self._install_documents()
        self.mode = "play"
        self.ui.disable()
        self.window.camera.zoom = 1.0
        self.window.load_scene(self.project.path(self.project.current))
        self.window.paused = False
        self._build_play_ui()
        self.play_ui.enable()
        self.window.set_caption(f"Mesh Studio - playing {self.project.label(self.project.current)} (F4 to stop)")

    def stop(self) -> None:
        self.play_ui.disable()
        self.play_ui.clear()
        self.mode = "edit"
        self.keys.clear()
        self.ui.enable()
        self._reload()  # the edited document, untouched by whatever happened in play
        self._rebuild()
        self._say("Back to editing. Nothing that happened while playing was saved into your rooms.")

    def _build_play_ui(self) -> None:
        self.play_ui.clear()
        root = self.play_ui.add(gui.UIAnchorLayout())
        stop = gui.UIFlatButton(text="Stop (F4)", width=120, height=30, style=S_DANGER)
        stop.on_click = lambda _e: self.stop()
        root.add(stop, anchor_x="center", anchor_y="top", align_y=-6)

    # ==================================================================== text fields
    def _field(self, text: str, commit: Callable[[str], None], *, width: int, key: str | None = None) -> gui.UIInputText:
        field = _Field(text=text, width=width, height=26, font_size=11, text_color=C_TEXT,
                                caret_color=C_TEXT, border_color=(90, 96, 112), border_width=1)
        field.with_background(color=(24, 26, 31))
        self._fields.append((field, text, commit))
        if key:
            self._focusable[key] = field
        return field

    def _flush_fields(self) -> None:
        pending = [(f.text, original, commit) for f, original, commit in self._fields if f.text != original]
        self._fields = [(f, f.text, c) for f, _, c in self._fields]
        for value, _original, commit in pending:
            commit(value)

    def _typing(self) -> bool:
        return any(f.active for f, _, _ in self._fields)

    # ==================================================================== UI construction
    def _button(self, text: str, action: Callable[[], None], *, width: int = 100, style: dict[str, Any] = S_BUTTON,
                disabled: bool = False) -> gui.UIFlatButton:
        button = gui.UIFlatButton(text=text, width=width, height=28, style=style)
        button.disabled = disabled

        def on_click(_event: Any) -> None:
            if button.disabled:
                return
            self.menu = None
            self._flush_fields()
            action()

        button.on_click = on_click
        return button

    def _label(self, text: str, *, color: tuple[int, int, int] = C_TEXT, size: int = 11, width: int | None = None,
               bold: bool = False) -> gui.UILabel:
        label = gui.UILabel(text=text, font_size=size, text_color=color, width=width, bold=bold,
                            multiline=width is not None)
        if width is not None:
            # Box layouts otherwise shrink labels to their text width (or, with a zero
            # minimum height, collapse them entirely).
            label.size_hint_min = (width, label.height)
        return label

    def _rebuild(self) -> None:
        if self.mode != "edit":
            return
        self.ui.clear()
        self._fields, self._focusable = [], {}
        root = self.ui.add(gui.UIAnchorLayout())
        root.add(self._top_bar(), anchor_x="left", anchor_y="top", align_x=8, align_y=-8)
        root.add(self._left_panel(), anchor_x="left", anchor_y="top", align_x=10, align_y=-(TOP_H + 10))
        root.add(self._right_panel(), anchor_x="right", anchor_y="top", align_x=-10, align_y=-(TOP_H + 10))
        self._status_label = self._label("", size=10)
        root.add(self._status_label, anchor_x="left", anchor_y="bottom", align_x=LEFT_W + 8, align_y=6)
        if self.menu is not None:
            self._add_menu(root)
        self._rebuild_status()
        if self._focus_after_build and self._focus_after_build in self._focusable:
            self._focusable[self._focus_after_build].activate()
        self._focus_after_build = None

    def _rebuild_status(self) -> None:
        label = getattr(self, "_status_label", None)
        if label is not None:
            label.text = self.message
            label.update_font(font_color=C_OK if self.message_ok else C_ERROR)
            label.fit_content()

    def _top_bar(self) -> gui.UIBoxLayout:
        bar = gui.UIBoxLayout(vertical=False, space_between=6)
        bar.add(self._button("Play (F4)", self.play, width=96, style=S_PLAY))
        bar.add(self._button("Save", self.save, width=70, disabled=not self.project.is_dirty))
        bar.add(self._button("Undo", self.undo, width=64, disabled=not self.project.can_undo()))
        bar.add(self._button("Redo", self.redo, width=64, disabled=not self.project.can_redo()))
        title = f"   {self.project.label(self.project.current)}" + ("   - unsaved changes" if self.project.is_dirty else "   - saved")
        bar.add(self._label(title, size=12, color=C_MUTED))
        return bar

    def _left_panel(self) -> gui.UIBoxLayout:
        width = LEFT_W - 20
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
        box.add(self._label("Rooms", bold=True, size=12))
        for key, label, _path in self.project.rooms():
            style = S_ACTIVE if key == self.project.current else S_BUTTON
            box.add(self._button(label, lambda k=key: self.switch_room(k), width=width, style=style))
        box.add(self._button("+ New room", self._open_new_room, width=width))
        box.add(gui.UISpace(height=10))
        box.add(self._map_section(width))
        box.add(gui.UISpace(height=10))
        box.add(self._label("Objects", bold=True, size=12))
        if not self.prefabs:
            box.add(self._label("This project has no objects in assets/prefabs.json.", color=C_MUTED, width=width))
        for prefab in self.prefabs:
            style = S_ACTIVE if prefab is self.place_prefab else S_BUTTON
            text = str(prefab.get("display_name") or prefab["id"])
            box.add(self._button(text, lambda p=prefab: self.arm_place(p), width=width, style=style))
        box.add(self._label("Click one, then click the map.", color=C_MUTED, size=10))
        return box

    def _map_section(self, width: int) -> gui.UIBoxLayout:
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
        box.add(self._label("Map", bold=True, size=12))
        self._palette_buttons = {}
        if ops.map_info(self.project.scene()) is None:
            box.add(self._label("This room has no map yet.", color=C_MUTED, width=width))
            box.add(self._button("Add a map", self.add_map_here, width=width, style=S_ACTIVE))
            return box
        tools = gui.UIBoxLayout(vertical=False, space_between=6)
        half = (width - 6) // 2
        tools.add(self._button("Select", self.use_select, width=half, style=S_ACTIVE if self.tool == "select" else S_BUTTON))
        tools.add(self._button("Eraser", self.use_eraser, width=half, style=S_ACTIVE if self.tool == "erase" else S_BUTTON))
        box.add(tools)
        for layer, title in ((ops.GROUND, "Ground"), (ops.WALLS, "Walls & obstacles (block)")):
            box.add(self._label(title, color=C_MUTED, size=10))
            tiles = [t for t in self.tileset["tiles"] if t["layer"] == layer]
            for start in range(0, len(tiles), 6):
                row = gui.UIBoxLayout(vertical=False, space_between=3)
                for tile in tiles[start:start + 6]:
                    texture = self.tile_textures[tile["gid"]]
                    button = gui.UITextureButton(texture=texture, texture_hovered=texture, texture_pressed=texture,
                                                 width=32, height=32)
                    button.on_click = lambda _e, t=tile: self._palette_click(t)
                    self._palette_buttons[tile["gid"]] = button
                    row.add(button)
                box.add(row)
        return box

    def _palette_click(self, tile: dict[str, Any]) -> None:
        self.menu = None
        self.pick_brush(tile)

    def _open_new_room(self, door_at: tuple[float, float] | None = None) -> None:
        self.pending_door_at = door_at
        self.panel = "new_room"
        self._focus_after_build = "room_name"
        self._rebuild()

    def _right_panel(self) -> gui.UIBoxLayout:
        width = RIGHT_W - 20
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
        if self.panel == "new_room":
            box.add(self._label("New room", bold=True, size=12))
            if self.pending_door_at is not None:
                box.add(self._label("A door to it will be placed where you right-clicked.", color=C_MUTED, width=width))
            name = self._field("", lambda v: None, width=width, key="room_name")
            box.add(self._label("Name", color=C_MUTED))
            box.add(name)
            row = gui.UIBoxLayout(vertical=False, space_between=6)
            row.add(self._button("Create", lambda: self.create_room(name.text), width=96, style=S_ACTIVE))
            row.add(self._button("Cancel", self._cancel_panel, width=80))
            box.add(row)
            return box

        entity = self._entity(self.selected)
        if entity is None:
            box.add(self._label("Nothing selected", bold=True, size=12))
            box.add(self._label("Click an object on the map to edit it, or drag it to move it. "
                                "Right-click an object or an empty spot for more actions.", color=C_MUTED, width=width))
            return box

        target = entity["id"]
        if self.panel == "add_behaviour":
            return self._behaviour_picker(box, width)

        box.add(self._label("Name", color=C_MUTED))
        box.add(self._field(str(entity.get("name") or ""), lambda v: self._edit(lambda s: ops.rename_entity(s, target, v), "Renamed."),
                            width=width, key="name"))
        if "Dialogue" in ops.entity_behaviours(entity) or entity.get("tag") == "npc":
            box.add(self._label("Says (Enter to apply)", color=C_MUTED))
            box.add(self._field(ops.dialogue_text(entity),
                                lambda v: self._edit(lambda s: ops.set_dialogue_text(s, target, v), "Dialogue updated."),
                                width=width, key="says"))
        box.add(self._label(f"Position  {entity.get('x', 0):.0f}, {entity.get('y', 0):.0f}", color=C_MUTED, size=10))
        box.add(gui.UISpace(height=6))
        box.add(self._label("Behaviours", bold=True, size=12))
        names = ops.entity_behaviours(entity)
        if not names:
            box.add(self._label("None yet.", color=C_MUTED))
        for name in names:
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            arrow = "v " if self.expanded == name else "> "
            row.add(self._button(arrow + name, lambda n=name: self._toggle_expand(n), width=width - 80,
                                 style=S_ACTIVE if self.expanded == name else S_BUTTON))
            row.add(self._button("Remove", lambda n=name: self.remove_behaviour(n), width=76, style=S_DANGER))
            box.add(row)
            if self.expanded == name:
                self._behaviour_fields(box, entity, name, width)
        box.add(gui.UISpace(height=6))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("+ Add behaviour", self._open_picker, width=150, style=S_ACTIVE))
        row.add(self._button("Delete object", self.delete_selected, width=120, style=S_DANGER))
        box.add(row)
        return box

    def _toggle_expand(self, name: str) -> None:
        self.expanded = None if self.expanded == name else name
        self._rebuild()

    def _behaviour_fields(self, box: gui.UIBoxLayout, entity: dict[str, Any], behaviour: str, width: int) -> None:
        target = entity["id"]
        config = (entity.get("behaviour_config") or {}).get(behaviour) or {}
        info = next((b for b in ops.behaviour_catalog() if b["name"] == behaviour), None)
        fields = info["fields"] if info else []
        if not fields:
            box.add(self._label("No settings.", color=C_MUTED))
        for spec in fields:
            name, kind = spec["name"], spec.get("type")
            value = config.get(name, spec.get("default"))
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label(name, color=C_MUTED, size=10, width=120))
            if kind == "bool":
                row.add(self._button("On" if value else "Off",
                                     lambda n=name, v=bool(value): self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, n, not v)),
                                     width=width - 128, style=S_ACTIVE if value else S_BUTTON))
            elif kind in ("int", "float", "string"):
                text = "" if value is None else str(value)
                row.add(self._field(text, lambda v, n=name: self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, n, v)),
                                    width=width - 128))
            else:
                count = len(value) if isinstance(value, (list, dict)) else 0
                row.add(self._label(f"{kind}: {count} item(s)", color=C_MUTED, size=10))
            box.add(row)

    def _open_picker(self) -> None:
        self.panel, self.picker_query = "add_behaviour", ""
        self._focus_after_build = "picker"
        self._rebuild()

    def _cancel_panel(self) -> None:
        self.panel, self.pending_door_at = "inspect", None
        self._rebuild()

    def _behaviour_picker(self, box: gui.UIBoxLayout, width: int) -> gui.UIBoxLayout:
        box.add(self._label("Add a behaviour", bold=True, size=12))
        search = self._field(self.picker_query, lambda v: None, width=width, key="picker")
        search.on_change = lambda _e: self._update_picker(search.text)
        box.add(search)
        self._picker_box = gui.UIBoxLayout(vertical=True, align="left", space_between=3)
        box.add(self._picker_box)
        self._fill_picker(width)
        box.add(self._button("Cancel", self._cancel_panel, width=80))
        return box

    def _update_picker(self, text: str) -> None:
        self.picker_query = text
        self._fill_picker(RIGHT_W - 20)

    def _fill_picker(self, width: int) -> None:
        self._picker_box.clear()
        have = set(ops.entity_behaviours(self._entity(self.selected) or {}))
        query = self.picker_query.strip().lower()
        matches = [b for b in ops.behaviour_catalog()
                   if b["name"] not in have and (not query or query in b["name"].lower() or query in b["description"].lower())]
        for item in matches[:MAX_PICKER_ROWS]:
            self._picker_box.add(self._button(item["name"], lambda n=item["name"]: self.add_behaviour(n), width=width))
        if len(matches) > MAX_PICKER_ROWS:
            self._picker_box.add(self._label(f"{len(matches) - MAX_PICKER_ROWS} more - type to narrow down.", color=C_MUTED, size=10))
        if not matches:
            self._picker_box.add(self._label("No behaviour matches.", color=C_MUTED))

    # ==================================================================== context menu
    def _open_menu(self, x: float, y: float, wx: float, wy: float) -> None:
        entity_id = self._entity_at(wx, wy)
        items: list[tuple[str, Callable[[], None]]] = []
        if entity_id:
            self.select(entity_id)
            entity = self._entity(entity_id) or {}
            items.append(("Rename", lambda: self._focus("name")))
            if "Dialogue" in ops.entity_behaviours(entity) or entity.get("tag") == "npc":
                items.append(("Edit what they say", lambda: self._focus("says")))
            items.append(("Add behaviour...", self._open_picker))
            items.append(("Delete", self.delete_selected))
        else:
            self.select(None)
            at = (_snap(wx), _snap(wy))
            for key, label, _ in self.project.rooms():
                if key != self.project.current:
                    items.append((f"Add door to {label}", lambda k=key: self.add_door_to(k, at)))
            items.append(("Add door to a new room...", lambda: self._open_new_room(door_at=at)))
            for prefab in self.prefabs:
                items.append((f"Place {prefab.get('display_name', prefab['id'])} here",
                              lambda p=prefab: (setattr(self, "place_prefab", p), self.place_at(*at))))
        self.menu = (x, y, items)
        self._rebuild()

    def _focus(self, key: str) -> None:
        self.panel = "inspect"
        self._focus_after_build = key
        self._rebuild()

    def _add_menu(self, root: gui.UIAnchorLayout) -> None:
        x, y, items = self.menu
        box = gui.UIBoxLayout(vertical=True, space_between=1)
        for text, action in items:
            box.add(self._button(text, action, width=220, style=S_MENU))
        height = len(items) * 29
        top = min(y, self.window.height - TOP_H)
        root.add(box, anchor_x="left", anchor_y="bottom", align_x=min(x, self.window.width - 230), align_y=max(STATUS_H, top - height))

    # ==================================================================== drawing
    def on_draw(self) -> bool:
        if self.mode == "play":
            type(self.window).on_draw(self.window)
            self.window.camera_controller.use_gui_camera()
            self.play_ui.draw()
            self._dump_layout()
            return True
        w = self.window
        # Same first step as the game's draw: match the GL viewport/projection to the
        # window, or everything (including optional_arcade.arcade.gui) renders at the wrong scale.
        w.camera_controller.sync_gui_camera_to_window()
        w.clear(color=C_BG)
        self._apply_camera()
        w.camera.use()
        w.scene_controller.draw()
        self._draw_world_overlay()
        w.camera_controller.use_gui_camera()
        self._draw_panels()
        self.ui.draw()
        if self.tool == "paint" and self.brush is not None:
            button = self._palette_buttons.get(self.brush["gid"])
            if button is not None:
                optional_arcade.arcade.draw_lrbt_rectangle_outline(
                    button.left - 2, button.right + 2, button.bottom - 2, button.top + 2, (255, 230, 120), 2)
        self._dump_layout()
        return True

    def _dump_layout(self) -> None:
        """Write what is on screen, and where, for automated GUI tests (MESH_STUDIO_LAYOUT=path)."""
        path = os.environ.get("MESH_STUDIO_LAYOUT")
        if not path:
            return
        self._dump_tick = getattr(self, "_dump_tick", 0) + 1
        if self._dump_tick % 10:
            return
        keys = {id(field): key for key, field in self._focusable.items()}
        by_gid = {t["gid"]: t for t in self.tileset["tiles"]}
        palette = {id(button): by_gid[gid] for gid, button in self._palette_buttons.items()}
        widgets = []
        for manager in (self.ui, self.play_ui):
            for widget in manager.walk_widgets():
                rect = [widget.left, widget.bottom, widget.width, widget.height]
                if isinstance(widget, gui.UIFlatButton):
                    widgets.append({"type": "button", "text": widget.text, "rect": rect, "disabled": widget.disabled})
                elif isinstance(widget, gui.UITextureButton) and id(widget) in palette:
                    tile = palette[id(widget)]
                    widgets.append({"type": "tile", "gid": tile["gid"], "text": tile["label"], "layer": tile["layer"],
                                    "rect": rect})
                elif isinstance(widget, gui.UIInputText):
                    widgets.append({"type": "field", "key": keys.get(id(widget)), "text": widget.text, "rect": rect,
                                    "active": widget.active})
        objects = []
        sprites = self._sprites_by_id() if self.mode == "edit" else {}
        if self.mode == "edit":
            self._apply_camera()  # in play the game's camera must not be touched
        for entity in ops.entities(self.project.scene()) if self.mode == "edit" else []:
            cx, cy, ew, eh = self._bounds(entity, sprites.get(entity.get("id")))
            x0, y0 = self.window.camera.project((cx - ew / 2, cy - eh / 2))[:2]
            x1, y1 = self.window.camera.project((cx + ew / 2, cy + eh / 2))[:2]
            objects.append({"id": entity.get("id"), "name": entity.get("name"), "tag": entity.get("tag"),
                            "x": entity.get("x"), "y": entity.get("y"), "rect": [x0, y0, x1 - x0, y1 - y0]})
        play = None
        if self.mode == "play":
            player = next((s for s in self.window.scene_controller.all_sprites
                           if (getattr(s, "mesh_entity_data", None) or {}).get("tag") == "player"), None)
            box = getattr(self.window.ui_controller, "dialogue_box", None)
            active = getattr(box, "is_active", False)
            active = active() if callable(active) else active
            entry = box.get_current_entry() if box is not None and active else None
            play = {"scene": self.window.scene_controller.current_scene_path,
                    "player": [player.center_x, player.center_y] if player is not None else None,
                    "dialogue": {"speaker": entry.get("speaker"), "text": entry.get("text")} if entry else None}
        map_state = None
        info = ops.map_info(self.project.scene())
        if info is not None and self.mode == "edit":
            corner = self.window.camera.project((0, 0))[:2]
            far = self.window.camera.project((info["width"] * info["tilewidth"], info["height"] * info["tileheight"]))[:2]
            map_state = {"width": info["width"], "height": info["height"], "tilewidth": info["tilewidth"],
                         "tileheight": info["tileheight"], "screen": [corner[0], corner[1], far[0], far[1]],
                         "layers": info["layers"]}
        state = {"tool": self.tool, "brush": self.brush["gid"] if self.brush else None, "map": map_state,
                 "zoom": self.zoom,
                 "mode": self.mode, "room": self.project.current, "selected": self.selected, "panel": self.panel,
                 "message": self.message, "ok": self.message_ok, "dirty": self.project.is_dirty,
                 "window": [self.window.width, self.window.height], "widgets": widgets, "objects": objects,
                 "play": play}
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            os.replace(tmp, path)
        except OSError:
            pass  # a test is reading the file right now; the next dump will land

    def _text(self, key: str, text: str, x: float, y: float, color: tuple[int, int, int], size: int = 10) -> None:
        label = self._labels.get(key)
        if label is None or label.text != text:
            label = self._labels[key] = optional_arcade.arcade.Text(text, x, y, color, size, anchor_x="center")
        label.x, label.y, label.color = x, y, color
        label.draw()

    def _draw_map_overlay(self) -> None:
        """Map border and grid, the stroke in progress, and the brush or eraser under the cursor."""
        info = ops.map_info(self.project.scene())
        if info is None:
            return
        a = optional_arcade.arcade
        tw, th, cols, rows = info["tilewidth"], info["tileheight"], info["width"], info["height"]
        map_w, map_h = cols * tw, rows * th
        painting = self.tool in ("paint", "erase")
        points: list[tuple[float, float]] = []
        for col in range(cols + 1):
            points += [(col * tw, 0), (col * tw, map_h)]
        for row in range(rows + 1):
            points += [(0, row * th), (map_w, row * th)]
        a.draw_lines(points, (255, 255, 255, 70 if painting else 26), 1)
        a.draw_lrbt_rectangle_outline(0, map_w, 0, map_h, (255, 255, 255, 120), 2)
        for col, row in dict.fromkeys(self.stroke["cells"] if self.stroke else []):
            self._draw_cell(info, col, row, hover=False)
        if painting and self.stroke is None and self._in_map(*self.mouse):
            cell = self._cell_under(*self.mouse)
            if cell is not None:
                self._draw_cell(info, *cell, hover=True)

    def _draw_cell(self, info: dict[str, Any], col: int, row: int, *, hover: bool) -> None:
        a = optional_arcade.arcade
        cx, cy = ops.cell_center(info, col, row)
        tw, th = info["tilewidth"], info["tileheight"]
        left, right, bottom, top = cx - tw / 2, cx + tw / 2, cy - th / 2, cy + th / 2
        if self.tool == "paint" and self.brush is not None:
            a.draw_texture_rect(self.tile_textures[self.brush["gid"]], a.XYWH(cx, cy, tw, th), alpha=170 if hover else 255)
            if hover:
                a.draw_lrbt_rectangle_outline(left, right, bottom, top, C_SELECT, 2)
        elif self.tool == "erase":
            a.draw_lrbt_rectangle_filled(left, right, bottom, top, (220, 60, 60, 90 if hover else 150))
            a.draw_lrbt_rectangle_outline(left, right, bottom, top, (255, 110, 110), 2)

    def _draw_world_overlay(self) -> None:
        self._draw_map_overlay()
        sprites = self._sprites_by_id()
        for entity in ops.entities(self.project.scene()):
            eid = entity.get("id")
            cx, cy, w, h = self._bounds(entity, sprites.get(eid))
            if entity.get("tag") == "spawn_point":
                optional_arcade.arcade.draw_circle_filled(cx, cy, 9, C_SPAWN)
                self._text(f"spawn:{eid}", str(entity.get("name") or "Arrival"), cx, cy - 24, C_SPAWN)
            elif entity.get("tag") == "door":
                self._text(f"door:{eid}", str(entity.get("name") or "Door"), cx, cy + h / 2 + 4, (240, 210, 140))
            if eid == self.selected:
                optional_arcade.arcade.draw_lrbt_rectangle_outline(cx - w / 2 - 3, cx + w / 2 + 3, cy - h / 2 - 3, cy + h / 2 + 3, C_SELECT, 2)
        if self.place_prefab is not None and self._in_map(*self.mouse):
            wx, wy = self._to_world(*self.mouse)
            optional_arcade.arcade.draw_lrbt_rectangle_outline(_snap(wx) - 32, _snap(wx) + 32, _snap(wy) - 32, _snap(wy) + 32, C_SELECT, 1)

    def _draw_panels(self) -> None:
        w, h = self.window.width, self.window.height
        optional_arcade.arcade.draw_lrbt_rectangle_filled(0, w, h - TOP_H, h, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(0, LEFT_W, 0, h - TOP_H, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(w - RIGHT_W, w, 0, h - TOP_H, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(LEFT_W, w - RIGHT_W, 0, STATUS_H, (26, 28, 33))

    # ==================================================================== input (edit mode)
    def on_update(self, delta_time: float) -> bool:
        if self.mode == "play":
            return False
        if not self._typing():
            k = optional_arcade.arcade.key
            dx = bool(self.keys & {k.RIGHT, k.D}) - bool(self.keys & {k.LEFT, k.A})
            dy = bool(self.keys & {k.UP, k.W}) - bool(self.keys & {k.DOWN, k.S})
            self.cam[0] += dx * PAN_SPEED * delta_time / self.zoom
            self.cam[1] += dy * PAN_SPEED * delta_time / self.zoom
        return True  # no gameplay runs while editing

    def on_key_press(self, symbol: int, modifiers: int) -> bool:
        if self.mode == "play":
            if symbol == optional_arcade.arcade.key.F4:
                self.stop()
                return True
            return False
        ctrl = bool(modifiers & optional_arcade.arcade.key.MOD_CTRL)
        if self._typing():
            if symbol in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.NUM_ENTER, optional_arcade.arcade.key.TAB):
                self._flush_fields()
            elif symbol == optional_arcade.arcade.key.ESCAPE:
                for field, _, _ in self._fields:
                    field.deactivate()
            return True
        self.keys.add(symbol)
        if symbol == optional_arcade.arcade.key.F4:
            self.play()
        elif ctrl and symbol == optional_arcade.arcade.key.S:
            self.keys.discard(symbol)
            self.save()
        elif ctrl and symbol == optional_arcade.arcade.key.Z:
            self.keys.discard(symbol)
            self.redo() if modifiers & optional_arcade.arcade.key.MOD_SHIFT else self.undo()
        elif ctrl and symbol == optional_arcade.arcade.key.Y:
            self.keys.discard(symbol)
            self.redo()
        elif symbol == optional_arcade.arcade.key.DELETE:
            self.delete_selected()
        elif symbol == optional_arcade.arcade.key.ESCAPE:
            self.menu, self.place_prefab, self.stroke = None, None, None
            if self.tool != "select":
                self.tool, self.brush = "select", None
                self._say("Select: click an object to edit it, drag to move it.")
            elif self.panel != "inspect":
                self.panel, self.pending_door_at = "inspect", None
            else:
                self.selected = None
            self._rebuild()
        return True

    def on_key_release(self, symbol: int, modifiers: int) -> bool:
        self.keys.discard(symbol)
        return self.mode == "edit"

    def on_text(self, text: str) -> bool:
        return self.mode == "edit"

    def on_text_motion(self, motion: int) -> bool:
        return self.mode == "edit"

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> bool:
        self.mouse = (x, y)
        return self.mode == "edit"

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        if self.mode == "play":
            return False
        if self._in_map(x, y):
            self.zoom = max(0.25, min(2.5, self.zoom * (1.1 ** scroll_y)))  # 0.25: fitted big maps
        return True

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        if self.mode == "play":
            return False
        if self.menu is not None:
            self.menu = None
            self._rebuild()
            return True
        if not self._in_map(x, y):
            return True
        self._flush_fields()
        for field, _, _ in self._fields:
            field.deactivate()
        wx, wy = self._to_world(x, y)
        if button == optional_arcade.arcade.MOUSE_BUTTON_MIDDLE:
            self.panning = True
        elif button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
            self._open_menu(x, y, wx, wy)
        elif button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            if self.tool in ("paint", "erase"):
                # Map tools never select or move objects, so painting can't drag an NPC away.
                cell = self._cell_under(x, y)
                if cell is not None:
                    self.stroke = {"cells": [cell], "last": cell}
                return True
            if self.place_prefab is not None:
                self.place_at(wx, wy)
                return True
            hit = self._entity_at(wx, wy)
            self.select(hit)
            if hit:
                entity = self._entity(hit) or {}
                self.drag = {"id": hit, "dx": float(entity.get("x", 0)) - wx, "dy": float(entity.get("y", 0)) - wy,
                             "moved": False, "to": (entity.get("x", 0), entity.get("y", 0))}
        return True

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        if self.mode == "play":
            return False
        self.mouse = (x, y)
        if self.panning:
            self.cam[0] -= dx / self.zoom
            self.cam[1] -= dy / self.zoom
        elif self.stroke is not None:
            cell = self._cell_under(x, y)
            if cell is not None:
                self.stroke["cells"].extend(_line_cells(self.stroke["last"], cell)[1:])
                self.stroke["last"] = cell
        elif self.drag is not None:
            wx, wy = self._to_world(x, y)
            to = (_snap(wx + self.drag["dx"]), _snap(wy + self.drag["dy"]))
            if to != self.drag["to"]:
                self.drag["to"], self.drag["moved"] = to, True
                sprite = self._sprites_by_id().get(self.drag["id"])
                if sprite is not None:
                    sprite.center_x, sprite.center_y = to
        return True

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        if self.mode == "play":
            return False
        self.panning = False
        if self.stroke is not None:
            self._commit_stroke()
            return True
        drag, self.drag = self.drag, None
        if drag is not None and drag["moved"]:
            target, (nx, ny) = drag["id"], drag["to"]
            self._edit(lambda s: ops.move_entity(s, target, nx, ny))
        return True


def open_studio(window: Any, root: Any, world_file: str | None, scene_path: str | None = None) -> Studio | None:
    """Attach the Studio to ``window`` if ``root`` is a Studio project (it has a world)."""
    project = Project.open(root, world_file)
    if project is None:
        return None
    if scene_path:
        wanted = str(scene_path).replace("\\", "/").lstrip("./")
        for key, _label, path in project.rooms():
            if path.replace("\\", "/").lstrip("./") == wanted:
                project.current = key
                project.scene(key)
    studio = Studio(window, project)
    window.studio = studio
    return studio
