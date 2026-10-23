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
from functools import partial
from pathlib import Path
from typing import Any, Callable

import engine.optional_arcade as optional_arcade
from engine import behaviour_guide
from engine import project_ops as ops
from engine.action_runtime.registry import dispatch_action
from engine.prefabs import get_prefab_manager
from engine.route_check import route_problems
from engine.scene_loader import document_key
from engine.studio_ai import Proposal, StudioAIHost
from engine.studio_inspector import InspectorMixin, Rows, row_height
from engine.studio_project import Project
from engine.studio_ui import (
    C_BG,
    C_ERROR,
    C_MUTED,
    C_OK,
    C_PANEL,
    C_SELECT,
    C_SPAWN,
    C_TEXT,
    S_ACTIVE,
    S_BUTTON,
    S_DANGER,
    S_MENU,
    S_PLAY,
    FirstClicks,
    TextField,
    ask_path,
    field_clipboard,
    gui,
)
from engine.world_controller import WorldController

TOP_H, STATUS_H, LEFT_W, RIGHT_W = 44, 26, 230, 330
GRID = 16
PAN_SPEED = 600.0
MAX_PICKER_ROWS = 10
SHEET_W = LEFT_W - 20  # the tile palette's width

LAYER_BUTTONS = ((ops.GROUND, "Ground"), (ops.WALLS, "Walls"), (ops.OVERHEAD, "Above"))
LAYER_NAME = {ops.GROUND: "the ground", ops.WALLS: "walls (they block movement)",
              ops.OVERHEAD: "the layer above characters (roofs, treetops; never blocks)"}
# Always in the Objects list: an object to dress up yourself, and a zone to walk into.
BUILT_IN_OBJECTS: list[dict[str, Any]] = [{"id": "object", "display_name": "Empty object", "built_in": "blank"},
                                          {"id": "zone", "display_name": "Trigger zone", "built_in": "zone"}]
SHAPE_HELP = {"brush": "Click or drag on the map.", "rect": "Drag a rectangle on the map.",
              "fill": "Click an area to fill it."}


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


def _guess_tile_size(width: int, height: int) -> int:
    return next((t for t in (32, 16, 48, 24, 64) if width % t == 0 and height % t == 0), 32)


def _colour_name(value: Any) -> str:
    rgb = ops.rgb(value)
    return next((name for name, hex_ in ops.LIGHT_COLOURS.items() if ops.rgb(hex_) == rgb), "custom")


class Studio(InspectorMixin):
    def __init__(self, window: Any, project: Project) -> None:
        self.window = window
        self.project = project
        self.mode = "edit"
        self.selected: str | None = None
        self.panel = "inspect"  # inspect | add_behaviour | new_room
        self.expanded: str | None = None
        self.picker_query = ""
        self.picker_category: str | None = None  # the category open in the behaviour picker
        self.more_settings: set[str] = set()  # behaviours whose "More settings" are open
        self.route: dict[str, str] | None = None  # the patrol route being edited: {entity, behaviour, setting}
        self.route_sel: int | None = None  # its selected point
        self.route_drag: dict[str, Any] | None = None  # a point being dragged
        self.pending_door_at: tuple[float, float] | None = None
        self.place_prefab: dict[str, Any] | None = None
        self.drag: dict[str, Any] | None = None
        self.panning = False
        self.menu: tuple[float, float, list[tuple[str, Callable[[], object]]]] | None = None
        self.message, self.message_ok = "", True
        self.keys: set[int] = set()
        self.cam = [0.0, 0.0]
        self.zoom = 1.0
        self.mouse = (0.0, 0.0)
        self._fields: list[tuple[gui.UIInputText, str, Callable[[str], object]]] = []
        self._focus_after_build: str | None = None
        self._focusable: dict[str, gui.UIInputText] = {}
        self._labels: dict[str, optional_arcade.arcade.Text] = {}
        self.prefabs = self._load_prefabs()
        self.tool = "select"  # select | paint | erase
        self.shape = "brush"  # brush | rect | fill: how painting and erasing apply
        self.layer = ops.GROUND  # the map layer painting and erasing work on
        self.brush: dict[str, Any] | None = None  # {"stamp": rows of gids, "label", "source", "region"}
        self.stroke: dict[str, Any] | None = None  # a brush stroke or rectangle in progress
        self.tilesets: list[dict[str, Any]] = []  # the current room's, in palette order
        self.sheet = 0  # the tileset the palette shows
        self.sheet_scroll = [0, 0]  # first visible (column, row) of the palette
        self.sheet_drag: list[tuple[int, int]] | None = None  # [start, end] palette cells while dragging
        self.clipboard: dict[str, Any] | None = None  # a copied object
        self.import_form = {"path": "", "name": "", "tile": "32"}
        self.modal: str | None = None  # "close": the Save / Discard / Cancel question
        self._closing = False  # set once the person chose to leave
        self.handle_drag: dict[str, Any] | None = None  # a collider, zone or light handle being dragged
        self.light: int | None = None  # the selected light (Lighting panel); lights are not objects
        self.play_flags_open = False
        self._play_flags_seen: Any = None
        self._init_inspector()
        self.ai = StudioAIHost(self)  # outside tools (AI over MCP, scripts) propose; the person decides
        if not os.environ.get("MESH_STUDIO_NO_AI_BRIDGE"):
            self.ai.start()
        self._tile_textures: dict[tuple[str, int], Any] = {}
        self._images: dict[str, Any] = {}
        self._sheet_space: Any = None
        self._import_space: Any = None

        self.ui = gui.UIManager(window)
        self.play_ui = gui.UIManager(window)
        window.push_handlers(self)
        self.ui.enable()
        self._first_clicks = FirstClicks("Studio")  # pyglet keeps only a weak reference to handlers
        window.push_handlers(self._first_clicks)
        self._reload(recenter=True)
        self._rebuild()
        self._say("Click an object to edit it. Right-click for actions. F4 plays your game.")
        self._check_player()

    def _check_player(self) -> None:
        """A project made before the player was shared has a player in every room. Identical ones become
        one player straight away (nothing is lost); different ones are the person's choice."""
        if self.project.player is not None or not self.project.own_players():
            return
        if not self.project.player_differences():
            self.project.share_player()
            self._after_change("Your rooms now share one player: change it once and every room follows. "
                               "(Undo puts it back.)")
        else:
            self.panel = "players"
            self._rebuild()
            self._say("This project's rooms each have their own player, and they differ: choose one on the right.")

    def share_player(self, key: str) -> None:
        replaced = self.project.share_player(key)
        self.panel = "inspect"
        lost = "; ".join(f"{self.project.label(k)}'s {', '.join(v)}" for k, v in replaced.items())
        self._after_change(f"Every room now uses {self.project.label(key)}'s player."
                           + (f" Replaced: {lost} (Undo puts them back)." if lost else ""))

    def keep_separate_players(self) -> None:
        self.panel = "inspect"
        self._rebuild()
        self._say("Each room keeps its own player. A player's inspector can still make them one.")

    # ==================================================================== document <-> map
    def _load_prefabs(self) -> list[dict[str, Any]]:
        path = self.project.root / "assets" / "prefabs.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        # The game's player is a prefab too, but there is one of it, in every room: it isn't placed.
        return [p for p in data if isinstance(p, dict) and isinstance(p.get("entity"), dict) and p.get("id")
                and p.get("id") != ops.PLAYER_PREFAB]

    def _image(self, path: str) -> Any:
        """A PIL image, loaded once (None if it can't be read)."""
        if path not in self._images:
            from PIL import Image  # noqa: PLC0415

            try:
                with Image.open(path) as img:
                    self._images[path] = img.convert("RGBA")
            except (OSError, ValueError):
                self._images[path] = None
        return self._images[path]

    def _tile_texture(self, tileset: dict[str, Any], local: int) -> Any:
        """A tile's texture, cut from the same image the game loads."""
        key = (tileset["image"], local)
        if key not in self._tile_textures:
            image, size = self._image(tileset["image"]), tileset["tile"]
            x, y = (local % tileset["columns"]) * size, (local // tileset["columns"]) * size
            self._tile_textures[key] = None if image is None else optional_arcade.arcade.Texture(
                image.crop((x, y, x + size, y + size)), hash=f"mesh-studio-tile-{tileset['image']}-{local}")
        return self._tile_textures[key]

    def _tileset_of(self, gid: int) -> dict[str, Any] | None:
        return next((t for t in self.tilesets if t["firstgid"] <= gid < t["firstgid"] + t["count"]), None)

    def _gid_texture(self, gid: int) -> Any:
        tileset = self._tileset_of(gid)
        return self._tile_texture(tileset, gid - tileset["firstgid"]) if tileset else None

    def _tile_label(self, tileset: dict[str, Any], local: int) -> str:
        hint = tileset["hints"].get(local) or {}
        return hint.get("label") or f"{tileset['name']} {local + 1}"

    def _install_documents(self) -> None:
        docs = self.window.scene_loader.documents
        docs.clear()
        for path, doc in self.project.documents().items():
            docs[document_key(path)] = doc
        player = self.project.player_prefab()
        if player is not None:  # rooms refer to the shared player: the runtime resolves it, unsaved changes included
            get_prefab_manager().put(player)
        self.window.world_controller = WorldController(copy.deepcopy(self.project.world))

    def _reload(self, recenter: bool = False) -> None:
        """Rebuild the map from the current room's document."""
        self._install_documents()
        self.window.load_scene(self.project.path(self.project.current))
        self.window.paused = True
        self.tilesets = self.project.room_tilesets()
        self.sheet = min(self.sheet, max(0, len(self.tilesets) - 1))
        self._fade_overhead()
        # Objects hidden by their "Show when" flags are still there to edit: show them see-through.
        for sprite in self.window.scene_controller.all_sprites:
            data = getattr(sprite, "mesh_entity_data", None) or {}
            if data.get("sprite") and not sprite.visible:
                sprite.visible, sprite.alpha = True, 110
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
        if os.environ.get("MESH_STUDIO_TRACE"):
            print(f"[Mesh][Studio] edit: {ok or '(no message)'}", flush=True)
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
        if self.light is not None and self.light >= len(ops.lights(self.project.scene())):
            self.light = None
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
            self.expanded, self.dlg_line, self.dlg_choice, self.clip_sel, self.panel_scroll = None, None, None, None, 0
            entity = self._entity(entity_id)
            # Open on what the object is about: people talk; other tabs stay as they were.
            if entity is not None and ("Dialogue" in ops.entity_behaviours(entity) or entity.get("tag") == "npc"):
                self.tab = "dialogue"
            elif self.tab == "dialogue":
                self.tab = "look"
        self.selected = entity_id
        self.panel = "inspect"
        self._rebuild()

    def switch_room(self, key: str) -> None:
        self._flush_fields()
        self.project.current = key
        self.selected, self.place_prefab, self.stroke, self.light = None, None, None, None
        self.panel = "lighting" if self.panel == "lighting" else "inspect"
        if self.tool == "light":
            self.tool = "select"
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
        if self.project.last_save_backups:
            self._say(f"Saved {len(written)} file(s). Something else had changed {', '.join(self.project.last_save_backups)} "
                      "since you opened it; that version is kept beside it (.outside-change.bak).", ok=False)
            return
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
        if self.panel == "lighting":
            if self.light is not None:
                self.delete_light()
            return
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
        self.tool, self.stroke = "select", None
        self._rebuild()
        self._say("Select: click an object to edit it, drag to move it.")

    def _fade_overhead(self) -> None:
        """Show the above-characters layer see-through unless you're working on it, so it hides nothing."""
        instance = getattr(self.window.scene_controller, "tilemap_instance", None)
        sprites = instance.layer_lookup.get(ops.OVERHEAD) if instance is not None else None
        for sprite in sprites or []:
            sprite.alpha = 255 if self.layer == ops.OVERHEAD or self.mode == "play" else 110

    def set_layer(self, layer: str) -> None:
        self.layer = layer
        self._fade_overhead()
        self._rebuild()
        self._say(f"Painting on {LAYER_NAME[layer]}.")

    def set_shape(self, shape: str) -> None:
        self._flush_fields()
        self.shape, self.stroke, self.place_prefab = shape, None, None
        if self.tool == "select":
            self.tool = "paint" if self.brush else "select"
        self._rebuild()
        if self.tool == "select":
            self._say("Pick a tile (or the Eraser) first.")
        else:
            self._say(f"{shape.capitalize() if shape != 'rect' else 'Rectangle'}: {SHAPE_HELP[shape]}")

    def cycle_tileset(self) -> None:
        if self.tilesets:
            self.sheet, self.sheet_scroll = (self.sheet + 1) % len(self.tilesets), [0, 0]
            self._rebuild()
            self._say(f"Tiles from {self.tilesets[self.sheet]['name']}.")

    def pick_brush(self, stamp: list[list[int]], label: str, layer: str | None = None,
                   source: str | None = None, region: tuple[int, int, int, int] | None = None) -> None:
        self._flush_fields()
        self.place_prefab, self.stroke = None, None
        self.tool, self.brush = "paint", {"stamp": stamp, "label": label, "source": source, "region": region}
        if layer:
            self.layer = layer
            self._fade_overhead()
        self._rebuild()
        size = f" ({len(stamp[0])}x{len(stamp)} tiles)" if len(stamp) > 1 or len(stamp[0]) > 1 else ""
        self._say(f"Painting {label}{size} on {LAYER_NAME[self.layer]}. {SHAPE_HELP[self.shape]} Esc goes back to Select.")

    def use_eraser(self) -> None:
        self._flush_fields()
        self.place_prefab, self.stroke = None, None
        self.tool = "erase"
        self._rebuild()
        self._say(f"Eraser on {LAYER_NAME[self.layer]}. {SHAPE_HELP[self.shape]}")

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
        """Apply the finished stroke, rectangle or fill as one edit, so one Undo takes all of it back."""
        stroke, self.stroke = self.stroke, None
        info = ops.map_info(self.project.scene())
        stamp = [[0]] if self.tool == "erase" else (self.brush or {}).get("stamp")
        if not stroke or not stroke["cells"] or not stamp or info is None:
            return
        cells, anchor, layer = self._stroke_cells(stroke), stroke["anchor"], self.layer
        cells = [(c, r) for c, r in dict.fromkeys(cells) if 0 <= c < info["width"] and 0 <= r < info["height"]]
        verb = "Erased" if self.tool == "erase" else "Painted"
        self._edit(lambda s: ops.paint_tiles(s, layer, cells, stamp, anchor), f"{verb} {len(cells)} tile(s).")

    def _stroke_cells(self, stroke: dict[str, Any]) -> list[tuple[int, int]]:
        """The cells a stroke covers: a brush stamp covers its whole size at each cell."""
        if self.shape != "brush" or self.tool == "erase" or not self.brush:
            return list(stroke["cells"])
        stamp = self.brush["stamp"]
        return [(c + dc, r + dr) for c, r in stroke["cells"] for dr in range(len(stamp)) for dc in range(len(stamp[0]))]

    def _cell_clamped(self, x: float, y: float) -> tuple[int, int] | None:
        """The map cell under a screen point, pulled onto the map if the point is outside it."""
        info = ops.map_info(self.project.scene())
        if info is None:
            return None
        wx, wy = self._to_world(x, y)
        col = int(wx // info["tilewidth"])
        row = int((info["height"] * info["tileheight"] - wy) // info["tileheight"])
        return min(max(col, 0), info["width"] - 1), min(max(row, 0), info["height"] - 1)

    def pick_from_map(self, cell: tuple[int, int]) -> None:
        """Eyedropper: paint with the top tile in a cell, on its layer."""
        info = ops.map_info(self.project.scene())
        if info is None:
            return
        index = cell[1] * info["width"] + cell[0]
        for layer in (ops.OVERHEAD, ops.WALLS, ops.GROUND):
            tiles = info["layers"].get(layer) or []
            gid = tiles[index] if index < len(tiles) else 0
            tileset = self._tileset_of(gid) if gid else None
            if tileset is not None:
                self.sheet = self.tilesets.index(tileset)
                local = gid - tileset["firstgid"]
                col, row = local % tileset["columns"], local // tileset["columns"]
                self.pick_brush([[gid]], self._tile_label(tileset, local), layer, tileset["source"], (col, row, col, row))
                return
        self._say("There's no tile there.", ok=False)

    # -------------------------------------------------------------------- tileset import
    def open_resize(self) -> None:
        self._flush_fields()
        self.panel, self.menu = "map_size", None
        self._focus_after_build = "map_width"
        self._rebuild()

    def resize_map(self, width: str, height: str) -> None:
        try:
            new_w, new_h = int(width), int(height)
        except ValueError:
            self._say("The size must be whole numbers of tiles.", ok=False)
            return
        if self._edit(lambda s: ops.resize_map(s, new_w, new_h),
                      f"The map is now {new_w} x {new_h} tiles. Undo puts it back."):
            self.panel = "inspect"
            self._reload(recenter=True)
            self._rebuild()

    def _resize_panel(self, box: gui.UIBoxLayout, width: int) -> gui.UIBoxLayout:
        info = ops.map_info(self.project.scene()) or {}
        box.add(self._label("Map size", bold=True, size=12))
        box.add(self._label("Tiles are added or removed at the top and right;", color=C_MUTED, size=10))
        box.add(self._label("everything else stays where it is.", color=C_MUTED, size=10))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._label("Width", color=C_MUTED))
        map_w = self._field(str(info.get("width", "")), lambda v: None, width=70, key="map_width")
        row.add(map_w)
        row.add(self._label("Height", color=C_MUTED))
        map_h = self._field(str(info.get("height", "")), lambda v: None, width=70, key="map_height")
        row.add(map_h)
        box.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Apply", lambda: self.resize_map(map_w.text, map_h.text), width=96, style=S_ACTIVE))
        row.add(self._button("Cancel", self._cancel_panel, width=80))
        box.add(row)
        return box

    def open_import(self) -> None:
        self._flush_fields()
        self.panel, self.menu = "import_tileset", None
        self._rebuild()
        self._say("Choose an image with Browse..., or paste its path and press Enter.")

    def browse_tileset(self) -> None:
        path = ask_path(folder=False, title="Import a tileset image", filetypes=[
            ("Images", "*.png *.gif *.bmp *.jpg *.jpeg *.webp"), ("All files", "*.*")])
        if path:
            self._set_import_path(path)

    def _set_import_path(self, path: str) -> None:
        form = self.import_form
        form["path"] = path.strip().strip('"')
        if not form["name"]:
            form["name"] = Path(form["path"]).stem.replace("_", " ").replace("-", " ").strip().title()
        image = self._image(form["path"]) if Path(form["path"]).is_file() else None
        if image is not None:
            form["tile"] = str(_guess_tile_size(*image.size))
        self._rebuild()

    def _set_import_tile(self, value: str) -> None:
        self.import_form["tile"] = value.strip()
        self._rebuild()

    def _import_check(self) -> tuple[str, bool, Any]:
        """``(what will happen, can import, image)`` for the import form as filled in."""
        form = self.import_form
        if not form["path"]:
            return "Choose a PNG of equal-sized tiles laid out in a grid.", False, None
        if not Path(form["path"]).is_file():
            return f"There is no file at {form['path']}.", False, None
        image = self._image(form["path"])
        if image is None:
            return "That file isn't an image Mesh can read.", False, None
        try:
            tile = int(form["tile"])
        except ValueError:
            return "The tile size must be a whole number of pixels.", False, image
        if not 8 <= tile <= 256:
            return "The tile size must be between 8 and 256 pixels.", False, image
        cols, rows = image.width // tile, image.height // tile
        if cols < 1 or rows < 1:
            return f"The image ({image.width}x{image.height}) is smaller than one {tile} px tile.", False, image
        # One short sentence per line: arcade's label wrapping can split words.
        text = f"{image.width}x{image.height} px: {cols} x {rows} = {cols * rows} tiles of {tile} px."
        if tile != ops.TILE_SIZE:
            text += f"\nScaled to {ops.TILE_SIZE} px to fit the map grid."
        if image.width % tile or image.height % tile:
            text += "\nThe red edge isn't a whole tile; it's left out."
        return text, True, image

    def import_tileset(self) -> None:
        self._flush_fields()
        form = self.import_form
        try:
            result = self.project.import_tileset(form["path"], int(form["tile"] or 0), form["name"])
        except ValueError as err:  # OpError, or a tile size that isn't a number
            self._say(str(err) if isinstance(err, ops.OpError) else "The tile size must be a whole number.", ok=False)
            return
        self.panel = "inspect"
        self.import_form = {"path": "", "name": "", "tile": "32"}
        self._reload()
        self.sheet = next((i for i, t in enumerate(self.tilesets) if t["source"] == result["source"]), self.sheet)
        self.sheet_scroll = [0, 0]
        self._rebuild()
        scaled = f", scaled to {ops.TILE_SIZE} px" if result["scaled"] else ""
        self._say(f"Imported {result['name']}: {result['count']} tiles{scaled}. Pick one and paint.")

    # -------------------------------------------------------------------- object clipboard
    def copy_selected(self) -> None:
        entity = self._entity(self.selected)
        if entity is None:
            self._say("Select an object to copy.", ok=False)
            return
        if entity.get("tag") == "player":
            self._say("A room has one player; the player can't be copied.", ok=False)
            return
        self.clipboard = copy.deepcopy(entity)
        self._say(f"Copied {entity.get('name', 'object')}. Ctrl+V pastes it at the mouse, in any room.")

    def paste_at(self, at: tuple[float, float]) -> None:
        clip, created = self.clipboard, []
        if clip is None:
            self._say("Nothing copied yet: select an object and press Ctrl+C.", ok=False)
            return

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, new_id = ops.paste_entity(scene, self.project.current, clip, *at)
            created.append(new_id)
            return out

        if self._edit(change, f"Pasted {clip.get('name', 'object')}."):
            self.select(created[0])

    def paste_here(self) -> None:
        if self._in_map(*self.mouse):
            wx, wy = self._to_world(*self.mouse)
            self.paste_at((_snap(wx), _snap(wy)))
        elif self.clipboard is not None:
            self.paste_at((float(self.clipboard.get("x", 0)) + 32, float(self.clipboard.get("y", 0)) - 32))

    def place_at(self, wx: float, wy: float) -> None:
        prefab, self.place_prefab = self.place_prefab, None
        created: list[str] = []

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            kind, at = prefab.get("built_in"), (_snap(wx), _snap(wy))
            if kind:
                out, new_id = ops.place_blank(scene, self.project.current, "Zone" if kind == "zone" else "Object", *at)
                if kind == "zone":
                    out = ops.set_trigger_zone(out, new_id, width=96, height=96)
            else:
                out, new_id = ops.place_prefab(scene, self.project.current, prefab, *at)
            created.append(new_id)
            return out

        hint = {"blank": " Give it a picture in Look.", "zone": " Drag its orange corner to size it."}.get(prefab.get("built_in"), "")
        if self._edit(change, f"Placed {prefab.get('display_name', prefab['id'])}.{hint}"):
            if prefab.get("built_in"):
                self.tab = "collision" if prefab["built_in"] == "zone" else "look"
            self.select(created[0])

    def add_behaviour(self, name: str) -> None:
        target = self.selected
        if target and self._edit(lambda s: ops.add_behaviour(s, target, name), f"Added: {behaviour_guide.guide(name).label}."):
            self.panel, self.expanded, self.tab = "inspect", name, "behaviours"
            self._rebuild()

    def remove_behaviour(self, name: str) -> None:
        target = self.selected
        if target:
            self._edit(lambda s: ops.remove_behaviour(s, target, name), f"Removed: {behaviour_guide.guide(name).label}.")

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
            self._after_change(f"Created {label}: walk into the new door here to go there. {label} has a door back "
                               "beside where the player starts in it.")
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
        state = getattr(self.window, "game_state_controller", None)
        if state is not None:
            state.replace_state({})  # every play-test is a new game: no flags left from the last one or a loaded save
        self.window.load_scene(self.project.path(self.project.current))
        self.window.paused = False
        self._fade_overhead()
        self._build_play_ui()
        self.play_ui.enable()
        self.window.set_caption(f"Mesh Studio - playing {self.project.label(self.project.current)} (F4 to stop)")

    def stop(self) -> None:
        self.play_ui.disable()
        self.play_ui.clear()
        self.mode = "edit"
        self.keys.clear()
        self.ui.enable()
        state = getattr(self.window, "game_state_controller", None)
        if state is not None:
            state.replace_state({})  # editing shows rooms as authored: nothing collected, no flags from play
        self._reload()  # the edited document, untouched by whatever happened in play
        self._rebuild()
        self._say("Back to editing. Nothing that happened while playing was saved into your rooms.")

    def _build_play_ui(self) -> None:
        self.play_ui.clear()
        root = self.play_ui.add(gui.UIAnchorLayout())
        bar = gui.UIBoxLayout(vertical=False, space_between=8)
        stop = gui.UIFlatButton(text="Stop (F4)", width=120, height=30, style=S_DANGER)
        stop.on_click = lambda _e: self.stop()
        bar.add(stop)
        flags = gui.UIFlatButton(text="Flags", width=80, height=30, style=S_ACTIVE if self.play_flags_open else S_BUTTON)
        flags.on_click = lambda _e: self._toggle_play_flags()
        bar.add(flags)
        menu = gui.UIFlatButton(text="Menu (Esc)", width=110, height=30, style=S_BUTTON)  # save, load, exit
        menu.on_click = lambda _e: dispatch_action(self.window, "pause_menu")
        bar.add(menu)
        root.add(bar, anchor_x="center", anchor_y="top", align_y=-6)
        if not self.play_flags_open:
            return
        state = getattr(self.window, "game_state", None)
        current = dict(getattr(state, "flags", None) or {})
        counters = dict(getattr(state, "counters", None) or {})
        box = gui.UIBoxLayout(vertical=True, space_between=3, align="left")
        box.add(self._label("Flags now (click to change)", bold=True, size=11))
        names = sorted(set(self._flag_uses()) | set(current))
        if not names:
            box.add(self._label("No flags in this game yet.", color=C_MUTED, size=10))
        for name in names[:18]:
            on = bool(current.get(name))
            button = gui.UIFlatButton(text=f"{name}: {'On' if on else 'Off'}", width=220, height=26, style=S_ACTIVE if on else S_BUTTON)
            button.on_click = lambda _e, n=name, v=on: self._set_play_flag(n, not v)
            box.add(button)
        for name, value in sorted(counters.items())[:8]:
            box.add(self._label(f"{name} = {float(value):g}", color=C_TEXT, size=10))
        box.with_padding(all=8).with_background(color=(30, 32, 38, 235))
        root.add(box, anchor_x="right", anchor_y="top", align_x=-8, align_y=-44)

    def _toggle_play_flags(self) -> None:
        self.play_flags_open = not self.play_flags_open
        self._build_play_ui()

    def _set_play_flag(self, name: str, value: bool) -> None:
        """Set or clear a flag while play-testing (to try a later part of the story)."""
        setter = getattr(self.window, "set_flag", None)
        if callable(setter):
            setter(name, value)
        self._build_play_ui()

    def _play_flags_changed(self) -> bool:
        state = getattr(self.window, "game_state", None)
        seen = (tuple(sorted((getattr(state, "flags", None) or {}).items())),
                tuple(sorted((getattr(state, "counters", None) or {}).items())))
        changed, self._play_flags_seen = seen != self._play_flags_seen, seen
        return changed

    # ==================================================================== text fields
    def _field(self, text: str, commit: Callable[[str], object], *, width: int, key: str | None = None) -> gui.UIInputText:
        field = TextField(text=text, width=width, height=26, font_size=11, text_color=C_TEXT,
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
    def _button(self, text: str, action: Callable[[], object], *, width: int = 100, style: dict[str, Any] = S_BUTTON,
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
        self._thumbs, self._anim_space = [], None
        root = self.ui.add(gui.UIAnchorLayout())
        root.add(self._top_bar(), anchor_x="left", anchor_y="top", align_x=8, align_y=-8)
        root.add(self._left_panel(), anchor_x="left", anchor_y="top", align_x=10, align_y=-(TOP_H + 10))
        root.add(self._right_panel(), anchor_x="right", anchor_y="top", align_x=-10, align_y=-(TOP_H + 10))
        self._status_label = self._label("", size=10)
        root.add(self._status_label, anchor_x="left", anchor_y="bottom", align_x=LEFT_W + 8, align_y=6)
        if self.menu is not None:
            self._add_menu(root)
        if self.modal == "close":
            self._add_close_question(root)
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
        bar.add(self._button("Flags", self.open_flags, width=64, style=S_ACTIVE if self.panel == "flags" else S_BUTTON))
        bar.add(self._button("Lighting", self.open_lighting, width=80, style=S_ACTIVE if self.panel == "lighting" else S_BUTTON))
        waiting = len(self.ai.pending())
        bar.add(self._button(f"AI ({waiting})" if waiting else "AI", self.open_ai, width=72,
                             style=S_ACTIVE if waiting or self.panel == "ai" else S_BUTTON))
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
        for prefab in self.prefabs + BUILT_IN_OBJECTS:
            style = S_ACTIVE if prefab is self.place_prefab else S_BUTTON
            text = str(prefab.get("display_name") or prefab["id"])
            box.add(self._button(text, lambda p=prefab: self.arm_place(p), width=width, style=style))
        box.add(self._label("Click one, then click the map.", color=C_MUTED, size=10))
        return box

    # ==================================================================== lighting
    def open_lighting(self) -> None:
        self._flush_fields()
        self.panel = "inspect" if self.panel == "lighting" else "lighting"
        self.light, self.place_prefab, self.selected = None, None, None
        if self.tool == "light" or self.panel == "lighting":
            self.tool = "select"
        self._rebuild()

    def _room_settings(self) -> dict[str, Any]:
        settings = self.project.scene().get("settings")
        return settings if isinstance(settings, dict) else {}

    def _lit(self) -> bool:
        return bool(getattr(getattr(self.window, "lighting", None), "enabled", False))

    def set_room_lighting(self, ok: str, **change: Any) -> None:
        # Switching a room's lighting on from a dark project default would show a black room: give it night light.
        if change.get("enabled") and "lighting_ambient_color" not in self._room_settings() and "ambient" not in change:
            change["ambient"] = "Night"
        self._edit(lambda s: ops.set_room_lighting(s, **change), ok)

    def _shift_ambient(self, factor: float) -> None:
        now = self._room_settings().get("lighting_ambient_color") or list(getattr(self.window.lighting, "ambient_color", (10, 10, 10)))
        value = [max(0, min(255, round(max(c, 4) * factor))) for c in ops.rgb(now)]
        self.set_room_lighting("Room light changed.", ambient=value)

    def arm_light(self) -> None:
        self._flush_fields()
        self.tool, self.place_prefab, self.light = "light", None, None
        self._rebuild()
        self._say("Click the map to place a light. Esc cancels.")

    def place_light(self, wx: float, wy: float) -> None:
        self.tool = "select"
        turn_on = not self._lit()

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, self.light = ops.add_light(scene, wx, wy)
            if turn_on:
                extra = {} if "lighting_ambient_color" in (out.get("settings") or {}) else {"ambient": "Night"}
                out = ops.set_room_lighting(out, enabled=True, **extra)
            return out

        self._edit(change, "Light placed" + (" and lighting turned on for this room" if turn_on else "")
                   + ". Drag its middle to move it, its edge handle to resize it.")

    def set_light(self, ok: str, **fields: Any) -> None:
        index = self.light
        if index is not None:
            self._edit(lambda s: ops.set_light(s, index, **fields), ok)

    def duplicate_light(self) -> None:
        index = self.light
        if index is None:
            return

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, self.light = ops.duplicate_light(scene, index)
            return out

        self._edit(change, "Light duplicated.")

    def delete_light(self) -> None:
        index, self.light = self.light, None
        if index is not None:
            self._edit(lambda s: ops.remove_light(s, index), "Light deleted.")

    def _light_handles(self) -> list[dict[str, Any]]:
        """The selected light's size handle first (it sits on the ring), then every light's middle."""
        out: list[dict[str, Any]] = []
        drag = self.handle_drag
        items = [dict(drag["cfg"]) if drag and drag.get("light") == i else light
                 for i, light in enumerate(ops.lights(self.project.scene()))]
        order = sorted(range(len(items)), key=lambda i: i != self.light)
        for i in order:
            light = items[i]
            if not isinstance(light, dict) or "x" not in light:
                continue
            x, y = float(light.get("x", 0)), float(light.get("y", 0))
            if i == self.light:
                out.append({"name": "light_size", "light": i, "x": x + float(light.get("radius", 100)), "y": y})
            out.append({"name": "light_move", "light": i, "x": x, "y": y})
        return out

    def _preview_lights(self) -> None:
        """Show a light being dragged straight away, without making an undo step per mouse move."""
        drag = self.handle_drag
        lighting = getattr(self.window, "lighting", None)
        if drag is None or lighting is None:
            return
        items = [dict(drag["cfg"]) if i == drag["light"] else light for i, light in enumerate(ops.lights(self.project.scene()))]
        lighting.configure_scene_lights(items)

    def _draw_lights(self) -> None:
        a = optional_arcade.arcade
        drag = self.handle_drag
        for i, light in enumerate(ops.lights(self.project.scene())):
            if not isinstance(light, dict) or "x" not in light:
                continue
            if drag and drag.get("light") == i:
                light = drag["cfg"]
            r, g, b = ops.rgb(light.get("color"))
            x, y, radius = float(light.get("x", 0)), float(light.get("y", 0)), float(light.get("radius", 100))
            chosen = i == self.light
            a.draw_circle_outline(x, y, radius, (r, g, b, 230 if chosen else 120), (3 if chosen else 1) / self.zoom)
            a.draw_circle_filled(x, y, 9 / self.zoom, (r, g, b))
            self._text(f"light:{i}", f"Light {i + 1}" + (" (flickers)" if light.get("flicker_enabled") else ""),
                       x, y + 14 / self.zoom, (255, 230, 150))

    def _lighting_panel(self, rows: Rows, width: int) -> None:
        settings, scene = self._room_settings(), self.project.scene()
        third, fifth = (width - 8) // 3, (width - 16) // 5
        rows.add(self._label("Lighting", bold=True, size=12))
        own = settings.get("lighting_enabled")
        state = "On: dark away from lights." if self._lit() else "Off: everything is fully lit."
        rows.add(self._label(state + ("" if own is not None else " (the project's setting)"), color=C_MUTED, size=9, width=width))
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for text, enabled, said in (("On", True, "Lighting on in this room."), ("Off", False, "Lighting off in this room."),
                                    ("As project", None, "Lighting follows the project.")):
            row.add(self._button(text, partial(self.set_room_lighting, said, enabled=enabled), width=third,
                                 style=S_ACTIVE if own is enabled else S_BUTTON))
        rows.add(row)
        rows.add(self._label("Room light (away from lamps)", color=C_MUTED, size=10))
        ambient = settings.get("lighting_ambient_color")
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for name, preset in ops.AMBIENT_PRESETS.items():
            row.add(self._button(name, partial(self.set_room_lighting, f"Room light: {name}.", ambient=name), width=fifth,
                                 style=S_ACTIVE if ambient == preset else S_BUTTON))
        rows.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._button("Darker", lambda: self._shift_ambient(0.7), width=third))
        row.add(self._button("Brighter", lambda: self._shift_ambient(1.4), width=third))
        row.add(self._button("Project's", lambda: self.set_room_lighting("Room light follows the project.", ambient=None),
                             width=third, style=S_ACTIVE if ambient is None else S_BUTTON))
        rows.add(row)
        shadows = settings.get("lighting_shadows_mode")
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for text, mode, said in (("Shadows on", "hard", "Shadows on."), ("Shadows off", "none", "Shadows off."),
                                 ("Project's", None, "Shadows follow the project.")):
            row.add(self._button(text, partial(self.set_room_lighting, said, shadows=mode), width=third,
                                 style=S_ACTIVE if shadows == mode else S_BUTTON))
        rows.add(row)
        if isinstance(scene.get("occluders"), list):
            rows.add(self._label(f"Shadows come from {len(scene['occluders'])} hand-drawn shape(s) made in the classic editor, "
                                 "not from the map's walls.", color=C_MUTED, size=9, width=width))
        else:
            rows.add(self._label("Walls on the map cast shadows from the first light.", color=C_MUTED, size=9, width=width))
        rows.add(gui.UISpace(height=6))
        items = ops.lights(scene)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._label(f"Lights ({len(items)})", bold=True, size=11, width=width - 110))
        row.add(self._button("+ Add light", self.arm_light, width=104, style=S_ACTIVE if self.tool == "light" else S_BUTTON))
        rows.add(row)
        for i, light in enumerate(items):
            if isinstance(light, dict):
                text = f"Light {i + 1}: {_colour_name(light.get('color'))}, size {float(light.get('radius', 0)):g}"
                rows.add(self._button(text, partial(self._select_light, i), width=width,
                                      style=S_ACTIVE if i == self.light else S_BUTTON))
        if self.light is not None and self.light < len(items):
            self._light_inspector(rows, items[self.light], width)
        rows.add(self._label("While this panel is open, clicks on the map work on lights.", color=C_MUTED, size=9, width=width))
        rows.add(self._button("Done", self.open_lighting, width=80))

    def _set_light_field(self, key: str, text: str) -> None:
        self.set_light("Changed.", **{key: text})

    def _select_light(self, index: int) -> None:
        self._flush_fields()
        self.light = None if self.light == index else index
        self._rebuild()

    def _light_inspector(self, rows: Rows, light: dict[str, Any], width: int) -> None:
        third = (width - 8) // 3
        rows.add(gui.UISpace(height=4))
        rows.add(self._label(f"Light {(self.light or 0) + 1}", bold=True, size=12))
        current = ops.rgb(light.get("color"))
        names = list(ops.LIGHT_COLOURS)
        for start in (0, 3):
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            for name in names[start:start + 3]:
                row.add(self._button(name, partial(self.set_light, f"{name} light.", color=name), width=third,
                                     style=S_ACTIVE if ops.rgb(ops.LIGHT_COLOURS[name]) == current else S_BUTTON))
            rows.add(row)
        radius = float(light.get("radius", 100))
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._button("Smaller", lambda: self.set_light("Smaller.", radius=max(8, round(radius * 0.8))), width=third))
        row.add(self._label(f"size {radius:g}", color=C_MUTED, size=10, width=third))
        row.add(self._button("Bigger", lambda: self.set_light("Bigger.", radius=min(4000, round(radius * 1.25))), width=third))
        rows.add(row)
        flicker = bool(light.get("flicker_enabled"))
        rows.add(self._toggle("Flicker", flicker, lambda on: self.set_light("Flickers." if on else "Steady.", flicker_enabled=on), width))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Duplicate", self.duplicate_light, width=(width - 6) // 2))
        row.add(self._button("Delete", self.delete_light, width=(width - 6) // 2))
        rows.add(row)
        more = self.expanded == "light_more"
        rows.add(self._button(("v " if more else "> ") + "More settings", lambda: self._toggle_expand("light_more"), width=width))
        if not more:
            return
        field_w = width - 122
        for label, key in (("X", "x"), ("Y", "y"), ("Size", "radius"), ("Flicker amount (0-1)", "flicker_amount"),
                           ("Flicker speed", "flicker_speed")):
            self._labeled(rows, label, self._field(f"{float(light.get(key) or 0):g}", partial(self._set_light_field, key),
                                                   width=field_w, key=f"light_{key}"), width)
        self._labeled(rows, "Colour (R, G, B)", self._field(", ".join(str(c) for c in current),
                      lambda v: self.set_light("Colour changed.", color=[p.strip() for p in v.split(",")]),
                      width=field_w, key="light_rgb"), width)

    def open_ai(self) -> None:
        self._flush_fields()
        self.panel, self.panel_scroll = ("inspect" if self.panel == "ai" else "ai"), 0
        self._rebuild()

    def on_ai_proposal(self, proposal: Proposal) -> None:
        self._say(f"{proposal.source} proposes: {proposal.title}. Open AI (top bar) to review it.")
        self._rebuild()

    def on_ai_decided(self, proposal: Proposal) -> None:
        self._rebuild()

    def accept_ai(self, proposal: Proposal) -> None:
        self._flush_fields()
        result = self.ai.accept(proposal)
        if not result.get("ok"):
            self._rebuild()
            self._say(proposal.message or f"Not applied: {result.get('reason')}", ok=False)
            return
        made = list(proposal.created.values())
        if made:
            self.selected = made[0]
        if not self.ai.pending():
            self.panel = "inspect"  # nothing else waiting: show what was made
        self._after_change(proposal.message)

    def reject_ai(self, proposal: Proposal) -> None:
        self._flush_fields()
        self.ai.reject_proposal(proposal)
        if not self.ai.pending():
            self.panel = "inspect"
        self._rebuild()
        self._say(proposal.message)

    def open_flags(self) -> None:
        self._flush_fields()
        self.panel, self.panel_scroll = ("inspect" if self.panel == "flags" else "flags"), 0
        self._rebuild()

    def _map_section(self, width: int) -> gui.UIBoxLayout:
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
        box.add(self._label("Map", bold=True, size=12))
        self._sheet_space = None
        if ops.map_info(self.project.scene()) is None:
            box.add(self._label("This room has no map yet.", color=C_MUTED, width=width))
            box.add(self._button("Add a map", self.add_map_here, width=width, style=S_ACTIVE))
            return box
        third, half = (width - 8) // 3, (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for layer, title in LAYER_BUTTONS:
            row.add(self._button(title, lambda la=layer: self.set_layer(la), width=third,
                                 style=S_ACTIVE if self.layer == layer else S_BUTTON))
        box.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Select", self.use_select, width=half, style=S_ACTIVE if self.tool == "select" else S_BUTTON))
        row.add(self._button("Eraser", self.use_eraser, width=half, style=S_ACTIVE if self.tool == "erase" else S_BUTTON))
        box.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for shape, title in (("brush", "Brush"), ("rect", "Rect"), ("fill", "Fill")):
            active = self.shape == shape and self.tool != "select"
            row.add(self._button(title, lambda sh=shape: self.set_shape(sh), width=third, style=S_ACTIVE if active else S_BUTTON))
        box.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        name = self.tilesets[self.sheet]["name"] if self.tilesets else "No tiles"
        row.add(self._button(name + ("  >" if len(self.tilesets) > 1 else ""), self.cycle_tileset,
                             width=width - 92, disabled=len(self.tilesets) < 2))
        row.add(self._button("Import...", self.open_import, width=86))
        box.add(row)
        info = ops.map_info(self.project.scene()) or {}
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._label(f"{info.get('width')} x {info.get('height')} tiles", color=C_MUTED, size=10, width=width - 92))
        row.add(self._button("Resize...", self.open_resize, width=86))
        box.add(row)
        geometry = self._sheet_geometry()
        if geometry is not None:
            tileset, px, cols, rows = geometry
            self._sheet_space = gui.UISpace(width=cols * px, height=rows * px)
            box.add(self._sheet_space)
            if cols < tileset["columns"] or rows < tileset["rows"]:
                box.add(self._label("Scroll over the tiles for more (Shift: sideways).", color=C_MUTED, size=9))
        return box

    def _sheet_geometry(self) -> tuple[dict[str, Any], int, int, int] | None:
        """``(tileset, tile size on screen, visible columns, visible rows)`` for the palette."""
        if not self.tilesets:
            return None
        tileset = self.tilesets[self.sheet]
        px = max(12, min(32, SHEET_W // max(1, tileset["columns"])))
        others = 18 + 32 * (len(self.project.rooms()) + 1) + 10 + 18 + 5 * 32 + 10 + 18 + 32 * (len(self.prefabs) + len(BUILT_IN_OBJECTS)) + 14
        room = self.window.height - TOP_H - STATUS_H - 30 - others - 14 * 4
        rows = max(2, min(tileset["rows"], int(min(200, room) // px)))
        return tileset, px, min(tileset["columns"], SHEET_W // px), rows

    def _sheet_cell(self, x: float, y: float, *, clamp: bool = False) -> tuple[int, int] | None:
        """The tileset (column, row) under a screen point on the palette."""
        space, geometry = self._sheet_space, self._sheet_geometry()
        if space is None or geometry is None:
            return None
        tileset, px, cols, rows = geometry
        col, row = int((x - space.left) // px), int((space.top - y) // px)
        if not (0 <= col < cols and 0 <= row < rows):
            if not clamp:
                return None
            col, row = min(max(col, 0), cols - 1), min(max(row, 0), rows - 1)
        return col + self.sheet_scroll[0], row + self.sheet_scroll[1]

    def _pick_from_sheet(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        tileset = self.tilesets[self.sheet]
        (c0, c1), (r0, r1) = sorted((a[0], b[0])), sorted((a[1], b[1]))
        stamp = [[tileset["firstgid"] + r * tileset["columns"] + c if r * tileset["columns"] + c < tileset["count"] else 0
                  for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]
        top_left = r0 * tileset["columns"] + c0
        if top_left >= tileset["count"]:
            return
        hint = tileset["hints"].get(top_left) or {}
        label = self._tile_label(tileset, top_left) if (c0, r0) == (c1, r1) else f"a {tileset['name']} stamp"
        self.menu = None
        self.pick_brush(stamp, label, hint.get("layer"), tileset["source"], (c0, r0, c1, r1))

    def _open_new_room(self, door_at: tuple[float, float] | None = None) -> None:
        self.pending_door_at = door_at
        self.panel = "new_room"
        self._focus_after_build = "room_name"
        self._rebuild()

    def _right_panel(self) -> gui.UIBoxLayout:
        width = RIGHT_W - 20
        rows = Rows()
        if self.panel == "new_room":
            rows.add(self._label("New room", bold=True, size=12))
            if self.pending_door_at is not None:
                rows.add(self._label("A door to it will be placed where you right-clicked.", color=C_MUTED, width=width))
            name = self._field("", lambda v: None, width=width, key="room_name")
            rows.add(self._label("Name", color=C_MUTED))
            rows.add(name)
            row = gui.UIBoxLayout(vertical=False, space_between=6)
            row.add(self._button("Create", lambda: self.create_room(name.text), width=96, style=S_ACTIVE))
            row.add(self._button("Cancel", self._cancel_panel, width=80))
            rows.add(row)
        elif self.panel == "map_size":
            self._resize_panel(rows, width)
        elif self.panel == "import_tileset":
            self._import_panel(rows, width)
        elif self.panel == "pick_image":
            self._picture_picker(rows, width)
        elif self.panel == "flags":
            self._flags_panel(rows, width)
        elif self.panel == "players":
            self._players_panel(rows, width)
        elif self.panel == "route":
            self._route_panel(rows, width)
        elif self.panel == "lighting":
            self._lighting_panel(rows, width)
        elif self.panel == "ai":
            self._ai_panel(rows, width)
        elif self.panel == "preview":
            self._preview_panel(rows, width)
        else:
            entity = self._entity(self.selected)
            if entity is None:
                rows.add(self._label("Nothing selected", bold=True, size=12))
                rows.add(self._label("Click an object on the map to edit it, or drag it to move it. "
                                     "Right-click an object or an empty spot for more actions.", color=C_MUTED, width=width))
            elif self.panel == "add_behaviour":
                self._behaviour_picker(rows, width)
            else:
                self._inspector(rows, entity, width)
        return self._scrolled(rows)

    def _menu_dump(self) -> dict[str, Any] | None:
        """The game menu (Esc) as it is on screen, for automated GUI tests: which page and where its items are."""
        menu = getattr(self.window, "pause_menu", None)
        if menu is None or not menu.visible:
            return None
        items = []
        for target in menu.layout_current_state().hit_targets:
            text = getattr(target.widget, "text", None)
            if text is None and isinstance(getattr(target.widget, "items", None), list):
                text = target.widget.items[target.index]
            r = target.rect
            items.append({"id": target.action_id, "text": text, "rect": [r.x, r.y, r.width, r.height]})
        return {"screen": menu.state, "items": items}

    def _toasts_now(self) -> list[str]:
        toasts = getattr(getattr(self.window, "player_hud", None), "_toast_manager", None)
        return list(toasts.get_active_toasts()) if toasts is not None else []

    def _scrolled(self, rows: Rows) -> gui.UIBoxLayout:
        """The rows that fit the panel, from ``panel_scroll`` on; the mouse wheel scrolls the rest in."""
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
        items = rows.items
        heights = [row_height(widget) + 4 for widget in items]
        room = self.window.height - TOP_H - STATUS_H - 24
        if self._scroll_to in rows.anchors:
            self.panel_scroll = max(0, rows.anchors[self._scroll_to] - 1)
        self._scroll_to = None
        if sum(heights) <= room:
            self.panel_scroll, self._panel_more = 0, (0, 0)
            for widget in items:
                box.add(widget)
            return box
        room -= 2 * 22  # the "more above / below" lines
        last_page = len(items)
        used = 0
        while last_page > 0 and used + heights[last_page - 1] <= room:
            last_page -= 1
            used += heights[last_page]
        start = min(max(0, self.panel_scroll), last_page)
        self.panel_scroll = start
        shown, used = [], 0
        for index in range(start, len(items)):
            if shown and used + heights[index] > room:
                break
            shown.append(index)
            used += heights[index]
        below = len(items) - (shown[-1] + 1 if shown else start)
        self._panel_more = (start, below)
        if start:
            box.add(self._label(f"^ {start} more above (scroll up)", color=C_MUTED, size=9))
        for index in shown:
            box.add(items[index])
        if below:
            box.add(self._label(f"v {below} more below (scroll down)", color=C_MUTED, size=9))
        return box

    def _toggle_expand(self, name: str) -> None:
        self.expanded = None if self.expanded == name else name
        self._rebuild()

    def _import_panel(self, box: gui.UIBoxLayout, width: int) -> gui.UIBoxLayout:
        form = self.import_form
        box.add(self._label("Import a tileset", bold=True, size=12))
        box.add(self._label("Image file (Enter to apply)", color=C_MUTED))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._field(form["path"], self._set_import_path, width=width - 92, key="tileset_path"))
        row.add(self._button("Browse...", self.browse_tileset, width=86))
        box.add(row)
        box.add(self._label("Name", color=C_MUTED))
        box.add(self._field(form["name"], lambda v: form.__setitem__("name", v.strip()), width=width, key="tileset_name"))
        box.add(self._label("Tile size in the image (px)", color=C_MUTED))
        box.add(self._field(form["tile"], self._set_import_tile, width=80, key="tile_size"))
        text, ok, image = self._import_check()
        for line in text.splitlines():
            box.add(self._label(line, color=C_MUTED if ok or not form["path"] else C_ERROR, size=10))
        self._import_space = None
        if image is not None:
            scale = min(width / image.width, 220 / image.height, 4.0)
            self._import_space = gui.UISpace(width=image.width * scale, height=image.height * scale)
            box.add(self._import_space)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Import", self.import_tileset, width=96, style=S_ACTIVE, disabled=not ok))
        row.add(self._button("Cancel", self._cancel_panel, width=80))
        box.add(row)
        return box

    def _behaviour_fields(self, box: gui.UIBoxLayout, entity: dict[str, Any], behaviour: str, width: int) -> None:
        """The behaviour's main settings, under the names the guide gives them; the rest behind More settings."""
        config = (entity.get("behaviour_config") or {}).get(behaviour) or {}
        info = next((b for b in ops.behaviour_catalog() if b["name"] == behaviour), None)
        basics, more = behaviour_guide.visible_fields(behaviour, info["fields"] if info else [])
        if not basics and not more:
            box.add(self._label("No settings.", color=C_MUTED))
        show_more = behaviour in self.more_settings
        for spec in basics + (more if show_more else []):
            self._setting_row(box, entity, behaviour, spec, config, width)
        if more:
            box.add(self._button(f"{'v' if show_more else '>'} More settings ({len(more)})",
                                 partial(self._toggle_more_settings, behaviour), width=width))

    def _toggle_more_settings(self, behaviour: str) -> None:
        self.more_settings ^= {behaviour}
        self._rebuild()

    def _setting_row(self, box: gui.UIBoxLayout, entity: dict[str, Any], behaviour: str, spec: dict[str, Any],
                     config: dict[str, Any], width: int) -> None:
        target = entity["id"]
        name, kind = spec["name"], spec.get("type")
        label = behaviour_guide.setting_label(behaviour, name)
        note = str(spec.get("description") or "")
        value = config.get(name, spec.get("default"))
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label(label, color=C_MUTED, size=10, width=120))
        if ops.is_point_list(spec) and all(isinstance(item, dict) for item in value or []):
            points = [p for p in value or [] if isinstance(p, dict)]
            row.add(self._button("Edit route on the map", partial(self.edit_route, target, behaviour, name),
                                 width=width - 128, style=S_ACTIVE))
            box.add(row)
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label(f"{len(points)} point(s), x,y", color=C_MUTED, size=9, width=120))
            row.add(self._field(ops.points_text(value),
                                lambda v: self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, name, v),
                                                             f"{label} changed."),
                                width=width - 128, key=f"points_{behaviour}_{name}"))
            note = "Click Edit route, then click the map to add points; or type x,y pairs."
        elif kind == "bool":
            row.add(self._button("On" if value else "Off",
                                 lambda: self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, name, not bool(value))),
                                 width=width - 128, style=S_ACTIVE if value else S_BUTTON))
        elif kind in ("int", "float", "string"):
            text = "" if value is None else str(value)
            row.add(self._field(text, lambda v: self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, name, v)),
                                width=width - 128))
        elif kind == "array" and all(isinstance(item, (str, int, float)) for item in value or []):
            # A list of names (flags, tags...) edits as comma-separated text.
            row.add(self._field(", ".join(str(item) for item in value or []),
                                lambda v: self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, name, v)),
                                width=width - 128))
        else:
            # Lists of objects and other structured settings: edited as checked text (JSON).
            row.add(self._field(json.dumps(value) if value is not None else "",
                                lambda v: self._set_structured(target, behaviour, name, v),
                                width=width - 128, key=f"param_{behaviour}_{name}"))
        box.add(row)
        if note:
            box.add(self._label(note, color=C_MUTED, size=9, width=width))

    # ==================================================================== patrol routes
    def edit_route(self, entity_id: str, behaviour: str, setting: str) -> None:
        self._flush_fields()
        self.route = {"entity": entity_id, "behaviour": behaviour, "setting": setting}
        self.route_sel, self.route_drag, self.place_prefab, self.tool = None, None, None, "select"
        self.panel = "route"
        self._rebuild()
        self._say("Click the map to add points in walking order. Drag a point to move it; click one and press "
                  "Delete to remove it.")

    def finish_route(self) -> None:
        self.route, self.route_sel, self.route_drag = None, None, None
        self.panel = "inspect"
        self._rebuild()
        self._say("Route done.")

    def _route_entity(self) -> dict[str, Any] | None:
        return self._entity(self.route["entity"]) if self.route else None

    def _route_points(self) -> list[tuple[float, float]]:
        entity = self._route_entity()
        if entity is None or self.route is None:
            return []
        config = (entity.get("behaviour_config") or {}).get(self.route["behaviour"]) or {}
        return [(float(p["x"]), float(p["y"])) for p in config.get(self.route["setting"]) or []
                if isinstance(p, dict) and "x" in p and "y" in p]

    def _live_route_points(self) -> list[tuple[float, float]]:
        points = self._route_points()
        drag = self.route_drag
        if drag is not None and drag["index"] < len(points):
            points[drag["index"]] = drag["to"]
        return points

    def _set_route(self, points: list[tuple[float, float]], ok: str) -> None:
        route = self.route
        if route is None:
            return
        value = [{"x": x, "y": y} for x, y in points]
        self._edit(lambda s: ops.set_behaviour_param(s, route["entity"], route["behaviour"], route["setting"], value), ok)

    def _route_problems(self) -> list[Any]:
        entity = self._route_entity()
        if entity is None:
            return []
        start = (float(entity.get("x", 0)), float(entity.get("y", 0)))
        return route_problems(self.project.scene(), start, self._live_route_points(), ignore=entity.get("id"))

    def _route_point_at(self, x: float, y: float) -> int | None:
        self._apply_camera()
        for index, point in enumerate(self._live_route_points()):
            sx, sy = self.window.camera.project(point)[:2]
            if abs(sx - x) <= 10 and abs(sy - y) <= 10:
                return index
        return None

    @staticmethod
    def _tile_centre(wx: float, wy: float) -> tuple[float, float]:
        tile = ops.TILE_SIZE
        return float((wx // tile) * tile + tile / 2), float((wy // tile) * tile + tile / 2)

    def remove_route_point(self) -> None:
        points, index = self._route_points(), self.route_sel
        if index is None or index >= len(points):
            return
        del points[index]
        self.route_sel = None
        self._set_route(points, f"Point {index + 1} removed.")

    def clear_route(self) -> None:
        self.route_sel = None
        self._set_route([], "Route cleared.")

    def _route_panel(self, rows: Rows, width: int) -> None:
        entity = self._route_entity()
        if entity is None or self.route is None:
            rows.add(self._label("That object is gone.", color=C_MUTED))
            rows.add(self._button("Done", self.finish_route, width=80))
            return
        info = behaviour_guide.guide(self.route["behaviour"])
        rows.add(self._label("Route", bold=True, size=12))
        rows.add(self._label(f"{entity.get('name') or 'Object'}: {info.label}", color=C_MUTED, size=10, width=width))
        rows.add(self._label("Click the map to add the next point. Drag a point to move it. Click a point, then "
                             "Delete (or the button) to remove it. It walks them in order, then back to the first.",
                             color=C_MUTED, size=9, width=width))
        points = self._route_points()
        problems = self._route_problems()
        rows.add(self._label(f"{len(points)} point(s)", size=11))
        if not points:
            rows.add(self._label("No points yet: click the map where it should walk.", color=(240, 200, 120), size=10, width=width))
        elif len(points) < 2:
            rows.add(self._label("Add at least one more point.", color=(240, 200, 120), size=10, width=width))
        elif not problems:
            rows.add(self._label("It can walk this route.", color=C_OK, size=10, width=width))
        for problem in problems:
            rows.add(self._label(problem.text, color=(240, 140, 120), size=10, width=width))
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button(f"Remove point {self.route_sel + 1}" if self.route_sel is not None else "Remove point",
                             self.remove_route_point, width=half, disabled=self.route_sel is None))
        row.add(self._button("Clear route", self.clear_route, width=half, disabled=not points))
        rows.add(row)
        rows.add(self._button("Done", self.finish_route, width=80, style=S_ACTIVE))

    def _draw_route(self) -> None:
        a = optional_arcade.arcade
        entity = self._route_entity()
        if entity is None:
            return
        points = self._live_route_points()
        problems = self._route_problems()
        bad_points = {p.point for p in problems if p.point is not None}
        bad_legs = {p.leg for p in problems if p.leg is not None}
        start = (float(entity.get("x", 0)), float(entity.get("y", 0)))
        legs: list[tuple[int | None, int]] = ([(None, 0)] if points else []) + [(i, i + 1) for i in range(len(points) - 1)]
        if len(points) > 2:
            legs.append((len(points) - 1, 0))
        for leg in legs:
            x0, y0 = start if leg[0] is None else points[leg[0]]
            x1, y1 = points[leg[1]]
            color = (240, 90, 80) if leg in bad_legs else ((255, 255, 255, 110) if leg[0] is None else (120, 220, 255))
            a.draw_line(x0, y0, x1, y1, color, (2 if leg[0] is None else 3) / self.zoom)
        for index, (x, y) in enumerate(points):
            color = (240, 90, 80) if index in bad_points else (255, 220, 90)
            a.draw_circle_filled(x, y, 9 / self.zoom, color)
            if index == self.route_sel:
                a.draw_circle_outline(x, y, 13 / self.zoom, (255, 255, 255), 2 / self.zoom)
            self._text(f"route:{index}", str(index + 1), x, y + 12 / self.zoom, (255, 255, 255), 11)

    def _set_structured(self, target: str, behaviour: str, name: str, text: str) -> None:
        try:
            value = json.loads(text) if text.strip() else None
        except ValueError as err:
            self._say(f"{name} isn't valid: {err.msg} (at character {err.pos + 1}). Nothing was changed.", ok=False)
            self._rebuild()
            return
        self._edit(lambda s: ops.set_behaviour_param(s, target, behaviour, name, value), f"{name} changed.")

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
        """Categories to open (Movement, Interaction...), or, while searching, everything that matches."""
        self._picker_box.clear()
        have = set(ops.entity_behaviours(self._entity(self.selected) or {}))
        catalog = [b for b in ops.behaviour_catalog() if b["name"] not in have]
        query = self.picker_query.strip()
        if query:
            matches = behaviour_guide.entries(catalog, query)
            for item in matches[:MAX_PICKER_ROWS]:
                self._picker_entry(item, width, show_category=True)
            if len(matches) > MAX_PICKER_ROWS:
                self._picker_box.add(self._label(f"{len(matches) - MAX_PICKER_ROWS} more: type more to narrow it down.",
                                                 color=C_MUTED, size=10))
            if not matches:
                self._picker_box.add(self._label("Nothing matches. Try other words, like walk, talk or light.", color=C_MUTED))
            return
        everything = behaviour_guide.entries(catalog, advanced=True)
        for category in behaviour_guide.CATEGORIES:
            inside = [e for e in everything if e["category"] == category]
            if not inside:
                continue
            is_open = self.picker_category == category
            self._picker_box.add(self._button(f"{'v' if is_open else '>'} {category} ({len(inside)})",
                                              partial(self._open_picker_category, category), width=width,
                                              style=S_ACTIVE if is_open else S_BUTTON))
            if is_open:
                for item in inside:
                    self._picker_entry(item, width)

    def _picker_entry(self, item: dict[str, Any], width: int, *, show_category: bool = False) -> None:
        self._picker_box.add(self._button(item["label"], partial(self.add_behaviour, item["name"]), width=width))
        where = f"{item['category']}: " if show_category else ""
        self._picker_box.add(self._label(f"{where}{item['summary']}", color=C_MUTED, size=9, width=width))

    def _open_picker_category(self, category: str) -> None:
        self.picker_category = None if self.picker_category == category else category
        self._fill_picker(RIGHT_W - 20)

    # ==================================================================== context menu
    def _open_menu(self, x: float, y: float, wx: float, wy: float) -> None:
        entity_id = self._entity_at(wx, wy)
        items: list[tuple[str, Callable[[], object]]] = []
        if entity_id:
            self.select(entity_id)
            entity = self._entity(entity_id) or {}
            items.append(("Rename", lambda: self._focus("name")))
            if "Dialogue" in ops.entity_behaviours(entity) or entity.get("tag") == "npc":
                items.append(("Edit what they say", lambda: (setattr(self, "tab", "dialogue"), self._focus("says"))))
            items.append(("Add behaviour...", self._open_picker))
            if entity.get("tag") != "player":
                items.append(("Copy", self.copy_selected))
            items.append(("Delete", self.delete_selected))
        else:
            self.select(None)
            at = (_snap(wx), _snap(wy))
            if self.clipboard is not None:
                items.append((f"Paste {self.clipboard.get('name', 'object')} here", lambda: self.paste_at(at)))
            cell = self._cell_under(x, y)
            if cell is not None:
                items.append(("Paint with this tile", lambda: self.pick_from_map(cell)))
            for key, label, _ in self.project.rooms():
                if key != self.project.current:
                    items.append((f"Add door to {label}", lambda k=key: self.add_door_to(k, at)))
            items.append(("Add door to a new room...", lambda: self._open_new_room(door_at=at)))
            for prefab in self.prefabs + BUILT_IN_OBJECTS:
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
        lighting = getattr(w, "lighting", None)
        if lighting is not None and lighting.enabled:  # the room as the game will light it, as the game draws it
            with lighting.begin():
                w.scene_controller.draw()
            w.camera_controller.use_gui_camera()
            lighting.end()
            w.camera.use()
        else:
            w.scene_controller.draw()
        self._draw_world_overlay()
        w.camera_controller.use_gui_camera()
        self._draw_panels()
        self.ui.draw()
        self._draw_sheet()
        self._draw_import_preview()
        self._draw_previews()
        self._dump_layout()
        return True

    def _dump_layout(self) -> None:
        """Write what is on screen, and where, for automated GUI tests (MESH_STUDIO_LAYOUT=path)."""
        path = os.environ.get("MESH_STUDIO_LAYOUT")
        if not path:
            return
        from engine.runtime_probe import runtime_snapshot  # noqa: PLC0415
        self._dump_tick = getattr(self, "_dump_tick", 0) + 1
        if self._dump_tick % 10:
            return
        keys = {id(field): key for key, field in self._focusable.items()}
        widgets = []
        for manager in (self.play_ui,) if self.mode == "play" else (self.ui,):  # only what's on screen
            for widget in manager.walk_widgets():
                rect = [widget.left, widget.bottom, widget.width, widget.height]
                if isinstance(widget, gui.UIFlatButton):
                    widgets.append({"type": "button", "text": widget.text, "rect": rect, "disabled": widget.disabled})
                elif isinstance(widget, gui.UIInputText):
                    widgets.append({"type": "field", "key": keys.get(id(widget)), "text": widget.text, "rect": rect,
                                    "active": widget.active})
                elif isinstance(widget, gui.UILabel):
                    widgets.append({"type": "label", "text": widget.text, "rect": rect})
        geometry = self._sheet_geometry() if self.mode == "edit" and self._sheet_space is not None else None
        if geometry is not None:
            tileset, px, cols, rows = geometry
            c0, r0 = self.sheet_scroll
            for r in range(rows):
                for c in range(cols):
                    local = (r0 + r) * tileset["columns"] + c0 + c
                    if c0 + c < tileset["columns"] and local < tileset["count"]:
                        hint = tileset["hints"].get(local) or {}
                        widgets.append({"type": "tile", "gid": tileset["firstgid"] + local, "text": self._tile_label(tileset, local),
                                        "layer": hint.get("layer"), "tileset": tileset["name"], "cell": [c0 + c, r0 + r],
                                        "rect": [self._sheet_space.left + c * px, self._sheet_space.top - (r + 1) * px, px, px]})
        if self._import_space is not None and self.panel == "import_tileset":
            sp = self._import_space
            widgets.append({"type": "preview", "rect": [sp.left, sp.bottom, sp.width, sp.height]})
        objects = []
        sprites = self._sprites_by_id() if self.mode == "edit" else {}
        if self.mode == "edit":
            self._apply_camera()  # in play the game's camera must not be touched
        for entity in ops.entities(self.project.scene()) if self.mode == "edit" else []:
            cx, cy, ew, eh = self._bounds(entity, sprites.get(entity.get("id")))
            x0, y0 = self.window.camera.project((cx - ew / 2, cy - eh / 2))[:2]
            x1, y1 = self.window.camera.project((cx + ew / 2, cy + eh / 2))[:2]
            objects.append({"id": entity.get("id"), "name": entity.get("name"), "tag": entity.get("tag"),
                            "x": entity.get("x"), "y": entity.get("y"), "rect": [x0, y0, x1 - x0, y1 - y0],
                            "sprite": entity.get("sprite"), "solid": bool(entity.get("solid")),
                            "behaviours": ops.entity_behaviours(entity)})
        handles = []
        for handle in self._handles() if self.mode == "edit" else []:
            hx, hy = self.window.camera.project((handle["x"], handle["y"]))[:2]
            handles.append({"name": handle["name"], "screen": [hx, hy], "world": [handle["x"], handle["y"]],
                            "light": handle.get("light")})
        play = None
        if self.mode == "play":
            player = next((s for s in self.window.scene_controller.all_sprites
                           if (getattr(s, "mesh_entity_data", None) or {}).get("tag") == "player"), None)
            box = getattr(self.window.ui_controller, "dialogue_box", None)
            active = getattr(box, "is_active", False)
            active = active() if callable(active) else active
            entry = box.get_current_entry() if box is not None and active else None
            flags = getattr(getattr(self.window, "game_state", None), "flags", None) or {}
            sprites_now = [{"name": (getattr(sp, "mesh_entity_data", None) or {}).get("name"), "visible": bool(sp.visible),
                            "alpha": int(getattr(sp, "alpha", 255)), "at": [sp.center_x, sp.center_y],
                            "angle": float(getattr(sp, "angle", 0.0) or 0.0), "size": [sp.width, sp.height],
                            "hp": next((float(b.hp) for b in getattr(sp, "mesh_behaviours_runtime", None) or []
                                        if type(b).__name__ == "Health"), None),
                            "solid": sp in (getattr(self.window.scene_controller, "solid_sprites", None) or [])}
                           for sp in self.window.scene_controller.all_sprites]
            play = {"scene": self.window.scene_controller.current_scene_path, "sprites": sprites_now,
                    "runtime": runtime_snapshot(self.window),
                    "flags": {name: bool(value) for name, value in dict(flags).items()},
                    "player": [player.center_x, player.center_y] if player is not None else None,
                    "player_screen": list(self.window.camera.project((player.center_x, player.center_y))[:2])
                    if player is not None else None,
                    "dialogue": {"speaker": entry.get("speaker"), "text": entry.get("text"),
                                 "choices": [{"text": str(c.get("text")), "disabled": bool(c.get("disabled"))} if isinstance(c, dict)
                                             else {"text": str(c), "disabled": False} for c in entry.get("choices") or []],
                                 "cursor": getattr(box, "_choice_index", None)}
                    if entry else None,
                    "menu": self._menu_dump(),
                    "toasts": self._toasts_now()}
        map_state = None
        info = ops.map_info(self.project.scene())
        if info is not None and self.mode == "edit":
            corner = self.window.camera.project((0, 0))[:2]
            far = self.window.camera.project((info["width"] * info["tilewidth"], info["height"] * info["tileheight"]))[:2]
            map_state = {"width": info["width"], "height": info["height"], "tilewidth": info["tilewidth"],
                         "tileheight": info["tileheight"], "screen": [corner[0], corner[1], far[0], far[1]],
                         "layers": info["layers"]}
        stamp = (self.brush or {}).get("stamp")
        state = {"tool": self.tool, "shape": self.shape, "layer": self.layer, "map": map_state, "zoom": self.zoom,
                 "brush": stamp[0][0] if stamp else None, "stamp": stamp,
                 "tilesets": [t["name"] for t in self.tilesets],
                 "sheet": self.tilesets[self.sheet]["name"] if self.tilesets else None,
                 "clipboard": (self.clipboard or {}).get("name"),
                 "mode": self.mode, "room": self.project.current, "selected": self.selected, "panel": self.panel,
                 "message": self.message, "ok": self.message_ok, "dirty": self.project.is_dirty,
                 "window": [self.window.width, self.window.height], "widgets": widgets, "objects": objects,
                 "play": play, "tab": self.tab, "panel_more": list(self._panel_more), "modal": self.modal,
                 "dlg_line": self.dlg_line, "dlg_choice": self.dlg_choice, "clip_sel": self.clip_sel, "handles": handles,
                 "preview": {"node": self.preview["node"], "flags": sorted(self.preview["flags"])} if self.preview else None,
                 "play_flags_open": self.play_flags_open, "tick": self._dump_tick,
                 "ai": [p.view() for p in self.ai.proposals], "revision": self.project.revision,
                 "dlg_order": list(ops.conversation(self._entity(self.selected) or {})["nodes"]) if self.selected else [],
                 "room_doc": self.project.scene() if self.mode == "edit" else None, "light": self.light,
                 "lighting": runtime_snapshot(self.window).get("lighting") if self.mode == "edit" else None,
                 "route": self._route_dump() if self.panel == "route" and self.mode == "edit" else None}
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            os.replace(tmp, path)
        except OSError:
            pass  # a test is reading the file right now; the next dump will land

    def _route_dump(self) -> dict[str, Any]:
        points = self._live_route_points()
        return {"points": [list(p) for p in points],
                "screen": [list(self.window.camera.project(p)[:2]) for p in points], "selected": self.route_sel,
                "problems": [{"kind": p.kind, "text": p.text, "point": p.point, "leg": p.leg} for p in self._route_problems()]}

    def _text(self, key: str, text: str, x: float, y: float, color: tuple[int, int, int], size: int = 10) -> None:
        label = self._labels.get(key)
        if label is None or label.text != text:
            label = self._labels[key] = optional_arcade.arcade.Text(text, x, y, color, size, anchor_x="center")
        label.x, label.y, label.color = x, y, color
        label.draw()

    def _draw_map_overlay(self) -> None:
        """Map border and grid, the stroke or rectangle in progress, and the brush or eraser under the cursor."""
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
        if self.stroke is not None and "start" in self.stroke:
            start, end = self.stroke["start"], self.stroke["end"]
            self._draw_cells(info, ops.rect_cells(start, end), (min(start[0], end[0]), min(start[1], end[1])), hover=False)
        elif self.stroke is not None:
            self._draw_cells(info, self._stroke_cells(self.stroke), self.stroke["anchor"], hover=False)
        elif painting and self._in_map(*self.mouse):
            cell = self._cell_under(*self.mouse)
            if cell is not None:
                hover = {"cells": [cell], "anchor": cell}
                cells = self._stroke_cells(hover) if self.shape == "brush" else [cell]
                self._draw_cells(info, cells, cell, hover=True)

    def _draw_cells(self, info: dict[str, Any], cells: list[tuple[int, int]], anchor: tuple[int, int], *, hover: bool) -> None:
        """Preview what painting or erasing ``cells`` will do, and outline the area."""
        if not cells:
            return
        a = optional_arcade.arcade
        tw, th = info["tilewidth"], info["tileheight"]
        stamp = (self.brush or {}).get("stamp") if self.tool == "paint" else None
        if len(cells) <= 4000:
            for col, row in dict.fromkeys(cells):
                cx, cy = ops.cell_center(info, col, row)
                if stamp:
                    line = stamp[(row - anchor[1]) % len(stamp)]
                    texture = self._gid_texture(line[(col - anchor[0]) % len(line)])
                    if texture is not None:
                        a.draw_texture_rect(texture, a.XYWH(cx, cy, tw, th), alpha=170 if hover else 230)
                elif self.tool == "erase":
                    a.draw_lrbt_rectangle_filled(cx - tw / 2, cx + tw / 2, cy - th / 2, cy + th / 2,
                                                 (220, 60, 60, 90 if hover else 150))
        cols = [c for c, _ in cells]
        rows = [r for _, r in cells]
        left, top = min(cols) * tw, (info["height"] - min(rows)) * th
        right, bottom = (max(cols) + 1) * tw, (info["height"] - max(rows) - 1) * th
        color = (255, 110, 110) if self.tool == "erase" else C_SELECT
        a.draw_lrbt_rectangle_outline(left, right, bottom, top, color, 2)

    def _draw_sheet(self) -> None:
        """The palette: the current tileset's tiles, with the brush (or the drag in progress) outlined."""
        space, geometry = self._sheet_space, self._sheet_geometry()
        if space is None or geometry is None:
            return
        a = optional_arcade.arcade
        tileset, px, cols, rows = geometry
        left, top = space.left, space.top
        a.draw_lrbt_rectangle_filled(left, left + cols * px, top - rows * px, top, (22, 24, 29))
        c0, r0 = self.sheet_scroll
        for r in range(rows):
            for c in range(cols):
                local = (r0 + r) * tileset["columns"] + c0 + c
                if c0 + c < tileset["columns"] and local < tileset["count"]:
                    texture = self._tile_texture(tileset, local)
                    if texture is not None:
                        a.draw_texture_rect(texture, a.XYWH(left + (c + 0.5) * px, top - (r + 0.5) * px, px, px))
        region = None
        if self.sheet_drag is not None:
            (x0, y0), (x1, y1) = self.sheet_drag
            region = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        elif self.brush and self.brush.get("source") == tileset["source"] and self.tool == "paint":
            region = self.brush["region"]
        if region is not None:
            x0, y0 = left + (region[0] - c0) * px, top - (region[1] - r0) * px
            x1, y1 = left + (region[2] - c0 + 1) * px, top - (region[3] - r0 + 1) * px
            l_, r_ = max(left, x0), min(left + cols * px, x1)
            b_, t_ = max(top - rows * px, y1), min(top, y0)
            if l_ < r_ and b_ < t_:  # only while the selection is (partly) scrolled into view
                a.draw_lrbt_rectangle_outline(l_ - 1, r_ + 1, b_ - 1, t_ + 1, (255, 230, 120), 2)

    def _draw_import_preview(self) -> None:
        """The image being imported, with its tile grid, so you can check the tile size before importing."""
        space = self._import_space
        if space is None or self.panel != "import_tileset":
            return
        text, ok, image = self._import_check()
        if image is None:
            return
        a = optional_arcade.arcade
        path = self.import_form["path"]
        key = ("import", path)
        if key not in self._tile_textures:
            self._tile_textures[key] = a.Texture(image, hash=f"mesh-studio-import-{path}-{os.path.getmtime(path)}")
        a.draw_texture_rect(self._tile_textures[key], a.LBWH(space.left, space.bottom, space.width, space.height))
        if not ok:
            return
        scale, tile = space.width / image.width, int(self.import_form["tile"])
        cols, rows = image.width // tile, image.height // tile
        points: list[tuple[float, float]] = []
        for col in range(cols + 1):
            x = space.left + col * tile * scale
            points += [(x, space.top), (x, space.top - rows * tile * scale)]
        for row in range(rows + 1):
            y = space.top - row * tile * scale
            points += [(space.left, y), (space.left + cols * tile * scale, y)]
        a.draw_lines(points, (255, 230, 120, 160), 1)
        if image.width % tile:
            a.draw_lrbt_rectangle_filled(space.left + cols * tile * scale, space.right, space.bottom, space.top, (220, 60, 60, 110))
        if image.height % tile:
            a.draw_lrbt_rectangle_filled(space.left, space.right, space.bottom, space.top - rows * tile * scale, (220, 60, 60, 110))

    def _draw_world_overlay(self) -> None:
        a = optional_arcade.arcade
        self._draw_map_overlay()
        sprites = self._sprites_by_id()
        showing_collision = self.tab == "collision" and self.panel == "inspect"
        for entity in ops.entities(self.project.scene()):
            eid = entity.get("id")
            cx, cy, w, h = self._bounds(entity, sprites.get(eid))
            zone = self._live_zone(entity)
            if zone is not None:
                x0, x1 = cx - zone["width"] / 2, cx + zone["width"] / 2
                y0, y1 = cy - zone["height"] / 2, cy + zone["height"] / 2
                a.draw_lrbt_rectangle_filled(x0, x1, y0, y1, (255, 150, 40, 45))
                a.draw_lrbt_rectangle_outline(x0, x1, y0, y1, (255, 160, 60), 2)
                self._text(f"zone:{eid}", f"Zone: {entity.get('name') or ''}", cx, y1 + 4, (255, 180, 90))
            elif not entity.get("sprite") and entity.get("tag") not in ("spawn_point", "door", "player"):
                # No picture: invisible in the game, but it must be findable here.
                a.draw_lrbt_rectangle_outline(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, (200, 200, 210, 140), 1)
                self._text(f"blank:{eid}", str(entity.get("name") or "Object"), cx, cy + h / 2 + 4, (200, 200, 210))
            if entity.get("tag") == "spawn_point":
                a.draw_circle_filled(cx, cy, 9, C_SPAWN)
                self._text(f"spawn:{eid}", str(entity.get("name") or "Arrival"), cx, cy - 24, C_SPAWN)
            elif entity.get("tag") == "door":
                # Walking into the picture takes the player through: show that area.
                a.draw_lrbt_rectangle_filled(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, (240, 210, 140, 40))
                a.draw_lrbt_rectangle_outline(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, (240, 210, 140), 1)
                self._text(f"door:{eid}", str(entity.get("name") or "Door"), cx, cy + h / 2 + 4, (240, 210, 140))
            if showing_collision or eid == self.selected:
                self._draw_collider(entity, float(entity.get("x", 0)), float(entity.get("y", 0)), w, h,
                                    bright=eid == self.selected)
            if eid == self.selected:
                a.draw_lrbt_rectangle_outline(cx - w / 2 - 3, cx + w / 2 + 3, cy - h / 2 - 3, cy + h / 2 + 3, C_SELECT, 2)
        if self.panel == "route" and self.mode == "edit":
            self._draw_route()
        if self.panel == "lighting" and self.mode == "edit":
            self._draw_lights()
        for handle in self._handles():
            color = {"zone": (255, 160, 60), "ligh": (255, 220, 90)}.get(handle["name"][:4], (90, 200, 255))
            size = 6 / self.zoom
            a.draw_lrbt_rectangle_filled(handle["x"] - size, handle["x"] + size, handle["y"] - size, handle["y"] + size, color)
            a.draw_lrbt_rectangle_outline(handle["x"] - size, handle["x"] + size, handle["y"] - size, handle["y"] + size, (20, 20, 20), 1)
        if self.place_prefab is not None and self._in_map(*self.mouse):
            wx, wy = self._to_world(*self.mouse)
            a.draw_lrbt_rectangle_outline(_snap(wx) - 32, _snap(wx) + 32, _snap(wy) - 32, _snap(wy) + 32, C_SELECT, 1)

    def _draw_collider(self, entity: dict[str, Any], x: float, y: float, w: float, h: float, *, bright: bool) -> None:
        a = optional_arcade.arcade
        collider = self._live_collider(entity)
        color = (90, 200, 255, 230) if bright else (90, 200, 255, 110)
        if collider["kind"] == "box":
            cx, cy = x + collider["offset_x"], y + collider["offset_y"]
            a.draw_lrbt_rectangle_outline(cx - collider["w"] / 2, cx + collider["w"] / 2, cy - collider["h"] / 2,
                                          cy + collider["h"] / 2, color, 2)
        elif collider["kind"] == "circle":
            a.draw_circle_outline(x + collider["offset_x"], y + collider["offset_y"], collider["r"], color, 2)
        elif entity.get("solid") and bright:
            a.draw_lrbt_rectangle_outline(x - w / 2, x + w / 2, y - h / 2, y + h / 2, color, 1)

    def _live_collider(self, entity: dict[str, Any]) -> dict[str, Any]:
        drag = self.handle_drag
        if drag is not None and drag.get("entity") == entity.get("id") and drag["name"].startswith("collider"):
            return drag["collider"]
        return ops.collider_of(entity, self._picture_size(entity))

    def _live_zone(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        drag = self.handle_drag
        if drag is not None and drag.get("entity") == entity.get("id") and drag["name"].startswith("zone"):
            return drag["zone"]
        return ops.trigger_zone(entity)

    def _handles(self) -> list[dict[str, Any]]:
        """Drag handles for the selected object's collider (Collision tab) and trigger zone, or for the room's
        lights while the Lighting panel is open, in world units."""
        if self.panel == "lighting":
            return self._light_handles() if self.mode == "edit" and self.tool == "select" else []
        entity = self._entity(self.selected)
        if entity is None or self.mode != "edit" or self.tool != "select" or self.panel != "inspect":
            return []
        x, y = float(entity.get("x", 0)), float(entity.get("y", 0))
        out: list[dict[str, Any]] = []
        collider = self._live_collider(entity)
        if self.tab == "collision" and collider["kind"] != "picture":
            cx, cy = x + collider["offset_x"], y + collider["offset_y"]
            corner = (cx + collider["w"] / 2, cy - collider["h"] / 2) if collider["kind"] == "box" else (cx + collider["r"], cy)
            out += [{"name": "collider_size", "x": corner[0], "y": corner[1]}, {"name": "collider_move", "x": cx, "y": cy}]
        zone = self._live_zone(entity)
        if zone is not None:
            out.append({"name": "zone_size", "x": x + zone["width"] / 2, "y": y - zone["height"] / 2})
        return out

    def _handle_at(self, x: float, y: float) -> dict[str, Any] | None:
        self._apply_camera()
        for handle in self._handles():
            sx, sy = self.window.camera.project((handle["x"], handle["y"]))[:2]
            if abs(sx - x) <= 9 and abs(sy - y) <= 9:
                return handle
        return None

    def _drag_handle(self, wx: float, wy: float) -> None:
        drag = self.handle_drag
        if drag is not None and "light" in drag:
            light = drag["cfg"]
            if drag["name"] == "light_move":
                light.update(x=float(round(wx)), y=float(round(wy)))
            else:
                light["radius"] = float(max(8, round(((wx - light["x"]) ** 2 + (wy - light["y"]) ** 2) ** 0.5)))
            self._preview_lights()
            return
        entity = self._entity(drag["entity"]) if drag else None
        if drag is None or entity is None:
            return
        x, y = float(entity.get("x", 0)), float(entity.get("y", 0))
        if drag["name"] == "zone_size":
            drag["zone"].update(width=max(8.0, round(2 * abs(wx - x))), height=max(8.0, round(2 * abs(wy - y))))
            return
        collider = drag["collider"]
        cx, cy = x + collider["offset_x"], y + collider["offset_y"]
        if drag["name"] == "collider_move":
            collider.update(offset_x=float(round(wx - x)), offset_y=float(round(wy - y)))
        elif collider["kind"] == "box":
            collider.update(w=max(4.0, round(2 * abs(wx - cx))), h=max(4.0, round(2 * abs(wy - cy))))
        else:
            collider["r"] = max(3.0, round(((wx - cx) ** 2 + (wy - cy) ** 2) ** 0.5))

    def _commit_handle(self) -> None:
        drag, self.handle_drag = self.handle_drag, None
        if drag is None or not drag.get("moved"):
            return
        if "light" in drag:
            index, light = drag["light"], drag["cfg"]
            if drag["name"] == "light_move":
                self._edit(lambda s: ops.set_light(s, index, x=light["x"], y=light["y"]), "Light moved.")
            else:
                self._edit(lambda s: ops.set_light(s, index, radius=light["radius"]), f"Light size {light['radius']:g}.")
            return
        target = drag["entity"]
        if drag["name"] == "zone_size":
            zone = drag["zone"]
            self._edit(lambda s: ops.set_trigger_zone(s, target, width=zone["width"], height=zone["height"], once=zone["once"],
                                                      start_conversation=zone["start_conversation"], set_flags=zone["set_flags"]),
                       f"Zone is {zone['width']:g} x {zone['height']:g}.")
            return
        c = drag["collider"]
        self._edit(lambda s: ops.set_collider(s, target, c["kind"], w=c.get("w", 32), h=c.get("h", 16), r=c.get("r", 12),
                                              offset_x=c["offset_x"], offset_y=c["offset_y"]), "Collider changed.")

    def _draw_panels(self) -> None:
        w, h = self.window.width, self.window.height
        optional_arcade.arcade.draw_lrbt_rectangle_filled(0, w, h - TOP_H, h, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(0, LEFT_W, 0, h - TOP_H, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(w - RIGHT_W, w, 0, h - TOP_H, C_PANEL)
        optional_arcade.arcade.draw_lrbt_rectangle_filled(LEFT_W, w - RIGHT_W, 0, STATUS_H, (26, 28, 33))

    # ==================================================================== input (edit mode)
    def on_update(self, delta_time: float) -> bool:
        self.ai.drain()  # proposals arrive on the bridge's thread; they're handled here, on this one
        if self.mode == "play":
            if self.play_flags_open and self._play_flags_changed():
                self._build_play_ui()  # the game changed a flag: show it
            return False
        if not self._typing():
            k = optional_arcade.arcade.key
            dx = bool(self.keys & {k.RIGHT, k.D}) - bool(self.keys & {k.LEFT, k.A})
            dy = bool(self.keys & {k.UP, k.W}) - bool(self.keys & {k.DOWN, k.S})
            self.cam[0] += dx * PAN_SPEED * delta_time / self.zoom
            self.cam[1] += dy * PAN_SPEED * delta_time / self.zoom
        lighting = getattr(self.window, "lighting", None)
        if lighting is not None:
            lighting.update(delta_time)  # flicker shows while editing; nothing else of the game runs
        return True  # no gameplay runs while editing

    def on_key_press(self, symbol: int, modifiers: int) -> bool:
        k = optional_arcade.arcade.key
        if self.mode == "play":
            if symbol == k.F4:
                self.stop()
                return True
            return False
        ctrl = bool(modifiers & k.MOD_CTRL)
        if self._typing():
            field = next(f for f, _, _ in self._fields if f.active)
            if ctrl and symbol in (k.A, k.C, k.X, k.V):
                field_clipboard(self.window, field, symbol)
            elif symbol in (k.ENTER, k.NUM_ENTER, k.TAB):
                self._flush_fields()
            elif symbol == k.ESCAPE:
                for other, _, _ in self._fields:
                    other.deactivate()
            return True
        self.keys.add(symbol)
        if symbol == k.F4:
            self.play()
        elif ctrl and symbol in (k.S, k.Z, k.Y, k.C, k.V):
            self.keys.discard(symbol)
            if symbol == k.S:
                self.save()
            elif symbol == k.Z:
                self.redo() if modifiers & k.MOD_SHIFT else self.undo()
            elif symbol == k.Y:
                self.redo()
            elif symbol == k.C:
                self.copy_selected()
            else:
                self.paste_here()
        elif k.A <= symbol <= k.Z and symbol not in (k.W, k.A, k.S, k.D) and self._fields:
            # Typing with no box chosen went nowhere (and W A S D moved the view): say how to type.
            self._say("To type, click a box first. (W A S D and the arrow keys move the view.)", ok=False)
        elif symbol == k.DELETE and self.panel == "route":
            self.remove_route_point()
        elif symbol == k.DELETE:
            self.delete_selected()
        elif symbol == k.ESCAPE and self.modal is not None:
            self._close_choice("cancel")
        elif symbol == k.ESCAPE and self.panel == "route":
            self.finish_route()
        elif symbol == k.ESCAPE:
            self.menu, self.place_prefab, self.stroke, self.sheet_drag = None, None, None, None
            if self.panel == "preview":
                self.preview = None
            if self.tool != "select":
                self.tool = "select"
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

    def on_close(self) -> bool:
        """Closing with unsaved changes asks: Save, Discard or Cancel."""
        if self._closing or not self.project.is_dirty:
            self.ai.stop()
            return False
        if self.mode == "play":
            self.stop()
        self._flush_fields()
        self.menu, self.modal = None, "close"
        self._rebuild()
        self._say("You have unsaved changes.", ok=False)
        return True

    def _add_close_question(self, root: gui.UIAnchorLayout) -> None:
        box = gui.UIBoxLayout(vertical=True, space_between=10)
        box.add(self._label("Save your changes before closing?", bold=True, size=13))
        box.add(self._label("Discard closes without saving; Cancel goes back to editing.", color=C_MUTED, size=10))
        row = gui.UIBoxLayout(vertical=False, space_between=8)
        row.add(self._button("Save", lambda: self._close_choice("save"), width=110, style=S_ACTIVE))
        row.add(self._button("Discard", lambda: self._close_choice("discard"), width=110, style=S_DANGER))
        row.add(self._button("Cancel", lambda: self._close_choice("cancel"), width=110))
        box.add(row)
        box.with_padding(all=18).with_background(color=(46, 50, 60, 250))
        root.add(box, anchor_x="center", anchor_y="center")

    def _close_choice(self, choice: str) -> None:
        self.modal = None
        if choice == "cancel":
            self._rebuild()
            self._say("Carry on editing.")
            return
        if choice == "save":
            self.save()
            if self.project.is_dirty:
                return  # saving failed; the message says why, and nothing is lost
        self._closing = True
        self.ai.stop()
        self.window.close()

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
        if x >= self.window.width - RIGHT_W and self.modal is None:
            more_above, more_below = self._panel_more
            if (scroll_y > 0 and more_above) or (scroll_y < 0 and more_below):
                self._flush_fields()
                self.panel_scroll = max(0, self.panel_scroll - int(scroll_y) * 2)
                self._rebuild()
            return True
        geometry = self._sheet_geometry()
        if self._sheet_cell(x, y) is not None and geometry is not None:
            tileset, _px, cols, rows = geometry
            k = optional_arcade.arcade.key
            sideways = bool(self.keys & {k.LSHIFT, k.RSHIFT}) or scroll_x
            axis, limit = (0, tileset["columns"] - cols) if sideways else (1, tileset["rows"] - rows)
            step = -(scroll_x or scroll_y) if sideways else -scroll_y
            self.sheet_scroll[axis] = int(min(max(self.sheet_scroll[axis] + step, 0), max(0, limit)))
            return True
        if self._in_map(x, y):
            self.zoom = max(0.25, min(2.5, self.zoom * (1.1 ** scroll_y)))  # 0.25: fitted big maps
        return True

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        if self.mode == "play":
            return False
        if self.modal is not None:
            return True  # answer the question first
        if self.menu is not None:
            self.menu = None
            self._rebuild()
            return True
        if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            cell = self._sheet_cell(x, y)
            if cell is not None:
                self.sheet_drag = [cell, cell]
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
            if self.panel == "route" and self.route is not None:
                index = self._route_point_at(x, y)
                if index is not None:  # pick it up (a click without moving just selects it)
                    self.route_sel = index
                    self.route_drag = {"index": index, "to": self._live_route_points()[index], "moved": False}
                    self._rebuild()
                else:
                    points = self._route_points() + [self._tile_centre(wx, wy)]
                    self.route_sel = len(points) - 1
                    self._set_route(points, f"Point {len(points)} added.")
                return True
            if self.tool in ("paint", "erase"):
                # Map tools never select or move objects, so painting can't drag an NPC away.
                cell = self._cell_under(x, y)
                if cell is None:
                    return True
                if self.shape == "fill":
                    self.stroke = {"cells": ops.fill_cells(self.project.scene(), self.layer, cell), "anchor": cell}
                    self._commit_stroke()
                elif self.shape == "rect":
                    self.stroke = {"start": cell, "end": cell, "anchor": cell, "cells": []}
                else:
                    self.stroke = {"cells": [cell], "last": cell, "anchor": cell}
                return True
            if self.place_prefab is not None:
                self.place_at(wx, wy)
                return True
            if self.tool == "light":
                self.place_light(wx, wy)
                return True
            handle = self._handle_at(x, y)
            if handle is not None and "light" in handle:
                self.light = handle["light"]
                self.handle_drag = {"name": handle["name"], "light": self.light, "moved": False,
                                    "cfg": dict(ops.lights(self.project.scene())[self.light])}
                self._rebuild()
                return True
            if self.panel == "lighting":  # while lighting, the map's clicks are about lights only
                if self.light is not None:
                    self.light = None
                    self._rebuild()
                return True
            if handle is not None:
                entity = self._entity(self.selected) or {}
                self.handle_drag = {"name": handle["name"], "entity": self.selected, "moved": False,
                                    "collider": dict(ops.collider_of(entity, self._picture_size(entity))), "zone": dict(ops.trigger_zone(entity) or {})}
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
        elif self.sheet_drag is not None:
            self.sheet_drag[1] = self._sheet_cell(x, y, clamp=True) or self.sheet_drag[1]
        elif self.stroke is not None and "start" in self.stroke:
            self.stroke["end"] = self._cell_clamped(x, y) or self.stroke["end"]
        elif self.stroke is not None:
            cell = self._cell_under(x, y)
            if cell is not None:
                self.stroke["cells"].extend(_line_cells(self.stroke["last"], cell)[1:])
                self.stroke["last"] = cell
        elif self.route_drag is not None:
            to = self._tile_centre(*self._to_world(x, y))
            if to != self.route_drag["to"]:
                self.route_drag.update(to=to, moved=True)
        elif self.handle_drag is not None:
            self.handle_drag["moved"] = True
            self._drag_handle(*self._to_world(x, y))
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
        if self.sheet_drag is not None:
            drag, self.sheet_drag = self.sheet_drag, None
            self._pick_from_sheet(*drag)
            return True
        if self.stroke is not None:
            if "start" in self.stroke:
                start, end = self.stroke["start"], self.stroke["end"]
                self.stroke["cells"] = ops.rect_cells(start, end)
                self.stroke["anchor"] = (min(start[0], end[0]), min(start[1], end[1]))
            self._commit_stroke()
            return True
        if self.route_drag is not None:
            moving, self.route_drag = self.route_drag, None
            if moving["moved"]:
                points = self._route_points()
                points[moving["index"]] = moving["to"]
                self._set_route(points, f"Point {moving['index'] + 1} moved.")
            return True
        if self.handle_drag is not None:
            self._commit_handle()
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
