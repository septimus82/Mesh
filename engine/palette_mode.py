from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import json
from pathlib import Path
import logging

from engine.stamps import iter_stamp_paths
from engine.brushes import iter_brush_paths
from engine.tooling_runtime.stamp_report import compute_scene_stamp_report
from engine.tooling_runtime.brush_report import compute_scene_brush_report
from engine.tilemap_edit import TilemapDims, ensure_tiles_array, set_tile, get_layer_by_id
from engine.paths import resolve_path
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


logger = logging.getLogger(__name__)

@dataclass
class PaletteItem:
    pack_id: str
    id: str
    path: str
    type: str # "stamp" or "brush"

@dataclass
class PaletteState:
    enabled: bool = False
    mode: str = "STAMPS" # "STAMPS" or "BRUSHES"
    selected_index: int = 0
    preview_on: bool = False
    
    stamps: list[PaletteItem] = field(default_factory=list)
    brushes: list[PaletteItem] = field(default_factory=list)

    last_saved_path: str = ""
    last_saved_type: str = ""  # "stamp" or "brush"
    last_saved_display: str = ""
    
    last_warnings: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        self.refresh_lists()
        
    def reset(self):
        self.enabled = False
        self.mode = "STAMPS"
        self.selected_index = 0
        self.preview_on = False
        self.last_warnings = []
        self.last_saved_path = ""
        self.last_saved_type = ""
        self.last_saved_display = ""
        
    def refresh_lists(self):
        # Load stamps
        self.stamps = []
        for path in iter_stamp_paths():
            # path is relative like packs/core/stamps/foo.json
            parts = path.split("/")
            if len(parts) >= 4 and parts[0] == "packs" and parts[2] == "stamps":
                pack_id = parts[1]
                stem = Path(path).stem
                self.stamps.append(PaletteItem(pack_id, stem, path, "stamp"))
        self.stamps.sort(key=lambda x: (x.pack_id, x.id))
        
        # Load brushes
        self.brushes = []
        for path in iter_brush_paths():
            parts = path.split("/")
            if len(parts) >= 4 and parts[0] == "packs" and parts[2] == "brushes":
                pack_id = parts[1]
                stem = Path(path).stem
                self.brushes.append(PaletteItem(pack_id, stem, path, "brush"))
        self.brushes.sort(key=lambda x: (x.pack_id, x.id))

    def hot_add_item(self, *, rel_path: str) -> PaletteItem | None:
        path_norm = str(rel_path).replace("\\", "/")
        parts = [p for p in path_norm.split("/") if p]
        if len(parts) < 4 or parts[0] != "packs":
            return None
        pack_id = parts[1]
        kind = parts[2]
        if kind not in {"stamps", "brushes"}:
            return None
        item_type = "stamp" if kind == "stamps" else "brush"
        asset_id = Path(path_norm).stem
        item = PaletteItem(pack_id=pack_id, id=asset_id, path=path_norm, type=item_type)

        if item_type == "stamp":
            bucket = self.stamps
        else:
            bucket = self.brushes

        if any(existing.path == item.path for existing in bucket):
            # Already present; still update last_saved.
            self._set_last_saved(item)
            if self.enabled:
                self._snap_selection_to(item)
            return item

        bucket.append(item)
        bucket.sort(key=lambda x: (x.pack_id, x.id))
        self._set_last_saved(item)
        if self.enabled:
            self._snap_selection_to(item)
        return item

    def _snap_selection_to(self, item: PaletteItem) -> None:
        target_mode = "STAMPS" if item.type == "stamp" else "BRUSHES"
        self.mode = target_mode
        items = self.current_list
        for idx, candidate in enumerate(items):
            if candidate.path == item.path:
                self.selected_index = idx
                return
        self.selected_index = 0

    def _set_last_saved(self, item: PaletteItem) -> None:
        self.last_saved_path = str(item.path)
        self.last_saved_type = str(item.type)
        self.last_saved_display = f"{item.pack_id}/{('stamps' if item.type == 'stamp' else 'brushes')}/{item.id}.json"

    @property
    def current_list(self) -> list[PaletteItem]:
        return self.stamps if self.mode == "STAMPS" else self.brushes

    @property
    def selected_item(self) -> Optional[PaletteItem]:
        items = self.current_list
        if not items:
            return None
        if 0 <= self.selected_index < len(items):
            return items[self.selected_index]
        return None

_STATE = PaletteState()

def get_state() -> PaletteState:
    return _STATE

def toggle_palette():
    _STATE.enabled = not _STATE.enabled

def toggle_mode():
    _STATE.mode = "BRUSHES" if _STATE.mode == "STAMPS" else "STAMPS"
    _STATE.selected_index = 0

def move_selection(delta: int):
    items = _STATE.current_list
    if not items:
        return
    _STATE.selected_index = (_STATE.selected_index + delta) % len(items)

def toggle_preview():
    _STATE.preview_on = not _STATE.preview_on

def apply_at(scene_payload: dict, tx: int, ty: int, layer_id: str = "ground") -> bool:
    item = _STATE.selected_item
    if not item:
        return False
    
    _STATE.last_warnings = []

    # Load item payload
    try:
        with open(resolve_path(item.path), "r", encoding="utf-8") as f:
            item_payload = json.load(f)
    except Exception as e:
        _log_swallow("PLMD-001", "engine/palette_mode.py blanket swallow", once=True)
        logger.error(f"Failed to load palette item {item.path}: {e}")
        return False

    if item.type == "stamp":
        return bool(_apply_stamp(scene_payload, item_payload, tx, ty))
    if item.type == "brush":
        return bool(_apply_brush(scene_payload, item_payload, tx, ty, layer_id))
    return False


def apply_last_saved_at(scene_payload: dict, tx: int, ty: int, layer_id: str = "ground") -> bool:
    path = str(getattr(_STATE, "last_saved_path", "") or "").strip()
    kind = str(getattr(_STATE, "last_saved_type", "") or "").strip()
    if not path or kind not in {"stamp", "brush"}:
        return False

    try:
        with open(resolve_path(path), "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:  # noqa: BLE001  # REASON: malformed saved stamp/brush payloads should log and skip only that persisted palette item
        _log_swallow("PLMD-002", "engine/palette_mode.py blanket swallow", once=True)
        logger.error(f"Failed to load last_saved item {path}: {e}")
        return False

    if kind == "stamp":
        _apply_stamp(scene_payload, payload, tx, ty)
        return True
    if kind == "brush":
        _apply_brush(scene_payload, payload, tx, ty, layer_id)
        return True
    return False

def _apply_stamp(scene_payload: dict, stamp_payload: dict, tx: int, ty: int) -> bool:
    try:
        report = compute_scene_stamp_report(
            scene_payload=scene_payload,
            stamp_payload=stamp_payload,
            origin_x=tx,
            origin_y=ty,
            id_prefix="rt", # "rt" or "paint" as per user request
            ignore_prefab_mismatch=True
        )
    except Exception as e:
        _log_swallow("PLMD-003", "engine/palette_mode.py blanket swallow", once=True)
        logger.error(f"Stamp report failed: {e}")
        return False

    if report.get("warnings"):
        _STATE.last_warnings.extend(report["warnings"])

    changed_any = bool(report.get("tile_changes") or []) or bool(report.get("entity_changes") or [])

    # Apply tile changes
    tilemap = scene_payload.get("tilemap", {})
    dims = TilemapDims(tilemap.get("width", 0), tilemap.get("height", 0))
    tile_layers = tilemap.get("tile_layers", [])
    
    for change in report.get("tile_changes", []):
        layer_id = change["layer_id"]
        x = change["x"]
        y = change["y"]
        after = change["after"]
        
        try:
            layer = get_layer_by_id(tile_layers, layer_id)
            tiles = ensure_tiles_array(layer, dims=dims)
            set_tile(tiles, dims=dims, x=x, y=y, tile=after)
        except Exception as e:
            _log_swallow("PLMD-004", "engine/palette_mode.py blanket swallow", once=True)
            logger.error(f"Failed to apply tile change: {e}")

    # Apply entity changes
    entities = scene_payload.get("entities", [])
    if not isinstance(entities, list):
        entities = []
        scene_payload["entities"] = entities
        
    for change in report.get("entity_changes", []):
        action = change["action"]
        entity_id = change["id"]
        
        if action == "add":
            entities.append({
                "id": entity_id,
                "prefab_id": change["prefab_id"],
                "x": change["x"],
                "y": change["y"]
            })
        elif action == "update":
            existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
            if existing:
                existing["x"] = change["x"]
                existing["y"] = change["y"]
                # prefab_id is already checked/matched

    return changed_any

def _apply_brush(scene_payload: dict, brush_payload: dict, tx: int, ty: int, layer_id: str) -> bool:
    try:
        report = compute_scene_brush_report(
            scene_payload=scene_payload,
            brush_payload=brush_payload,
            origin_x=tx,
            origin_y=ty,
            layer_id=layer_id,
            anchor="tl", # Default anchor
            clip=True # Default clip? User said "applies brush at cursor tx,ty onto current tile layer"
        )
    except Exception as e:
        _log_swallow("PLMD-005", "engine/palette_mode.py blanket swallow", once=True)
        logger.error(f"Brush report failed: {e}")
        return False

    changed_any = bool(report.get("tile_changes") or [])

    # Apply tile changes
    tilemap = scene_payload.get("tilemap", {})
    dims = TilemapDims(tilemap.get("width", 0), tilemap.get("height", 0))
    tile_layers = tilemap.get("tile_layers", [])
    
    for change in report.get("tile_changes", []):
        lid = change["layer_id"]
        x = change["x"]
        y = change["y"]
        after = change["after"]
        
        try:
            layer = get_layer_by_id(tile_layers, lid)
            tiles = ensure_tiles_array(layer, dims=dims)
            set_tile(tiles, dims=dims, x=x, y=y, tile=after)
        except Exception as e:
            _log_swallow("PLMD-006", "engine/palette_mode.py blanket swallow", once=True)
            logger.error(f"Failed to apply tile change: {e}")

    return changed_any
