"""The project the Studio edits: the world file plus open scene documents, with undo.

Documents are plain dicts and every change goes through engine.project_ops, so this
module never draws, never touches a running game, and can be tested headless. Undo
stores whole-document snapshots: scenes are small, and snapshots cannot drift out of
sync the way per-command inverse logic did in the old editor.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from engine import project_ops as ops
from engine.json_io import write_json_atomic
from engine.project_scaffold import ensure_starter_files

Doc = dict[str, Any]
UNDO_LIMIT = 100


@dataclass(frozen=True)
class _State:
    world: Doc
    scenes: dict[str, Doc]
    current: str
    dirty: frozenset[str]
    world_dirty: bool


class Project:
    def __init__(self, root: Path, world_file: str) -> None:
        self.root = Path(root)
        self.world_file = world_file
        self.world: Doc = json.loads((self.root / world_file).read_text(encoding="utf-8"))
        self.scenes: dict[str, Doc] = {}
        self.dirty: set[str] = set()
        self.world_dirty = False
        rooms = ops.world_rooms(self.world)
        if not rooms:
            raise ValueError(f"{world_file} lists no rooms")
        self.current: str = str(self.world.get("start_scene") or rooms[0][0])
        self._undo: list[_State] = []
        self._redo: list[_State] = []
        self.scene(self.current)

    @classmethod
    def open(cls, root: Path, world_file: str | None) -> "Project | None":
        """The project at ``root``, or None if it has no world file (not a Studio project)."""
        if not world_file or not (Path(root) / world_file).is_file():
            return None
        return cls(Path(root), world_file)

    # --- reading ----------------------------------------------------------------------------
    def rooms(self) -> list[tuple[str, str, str]]:
        return ops.world_rooms(self.world)

    def path(self, key: str) -> str:
        return str(self.world["scenes"][key]["path"])

    def label(self, key: str) -> str:
        return str(self.world["scenes"][key].get("label") or key)

    def scenes_dir(self) -> str:
        return str(Path(self.path(self.start_key())).parent.as_posix())

    def start_key(self) -> str:
        return str(self.world.get("start_scene") or self.rooms()[0][0])

    def scene(self, key: str | None = None) -> Doc:
        key = key or self.current
        if key not in self.scenes:
            path = self.root / self.path(key)
            raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"name": self.label(key), "entities": []}
            self.scenes[key] = ops.ensure_entity_ids(raw, key)
        return self.scenes[key]

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty) or self.world_dirty

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def player_template(self) -> Doc | None:
        """The start room's player, copied into new rooms so you can walk around in them."""
        for entity in ops.entities(self.scene(self.start_key())):
            if entity.get("tag") == "player":
                return entity
        return None

    def documents(self) -> dict[Path, Doc]:
        """Absolute path -> document for every room the Studio has open (for play-testing)."""
        return {self.root / self.path(key): doc for key, doc in self.scenes.items()}

    # --- editing ----------------------------------------------------------------------------
    def _snapshot(self) -> _State:
        return _State(copy.deepcopy(self.world), copy.deepcopy(self.scenes), self.current, frozenset(self.dirty), self.world_dirty)

    def _restore(self, state: _State) -> None:
        self.world = copy.deepcopy(state.world)
        self.scenes = copy.deepcopy(state.scenes)
        self.current = state.current
        self.dirty = set(state.dirty)
        self.world_dirty = state.world_dirty

    def _record(self, before: _State) -> None:
        self._undo.append(before)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def edit_scene(self, change: Callable[[Doc], Doc], key: str | None = None) -> None:
        """Replace one room with ``change(room)``. An OpError leaves everything untouched."""
        key = key or self.current
        before = self._snapshot()
        updated = change(self.scene(key))
        self._record(before)
        self.scenes[key] = updated
        self.dirty.add(key)

    def add_room(self, label: str) -> str:
        """A new room with its own player and a ready-to-paint map: wood floor, stone-wall border."""
        before = self._snapshot()
        world, scene, key, path = ops.new_room(self.world, label, self.scenes_dir(), self.player_template())
        scene, map_path, skeleton = ops.add_map(scene, path, width=20, height=15,
                                                ground=ops.STARTER_FLOOR, border=ops.STARTER_WALL)
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self.world, self.world_dirty = world, True
        self.scenes[key] = scene
        self.dirty.add(key)
        return key

    def add_map(self, key: str | None = None) -> None:
        """Give a room without a map an empty one that covers its objects."""
        key = key or self.current
        width, height = ops.map_size_for(self.scene(key))
        before = self._snapshot()
        scene, map_path, skeleton = ops.add_map(self.scene(key), self.path(key), width=width, height=height)
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self.scenes[key] = scene
        self.dirty.add(key)

    def _write_map_file(self, map_path: str, skeleton: Doc) -> None:
        # The map file holds only the size, tileset and empty layers (the painted tiles live
        # in the room document), so it is written straight away: the Studio and play-tests
        # load it from disk even before the room is saved.
        ensure_starter_files(self.root)
        target = self.root / map_path
        if not target.is_file():
            write_json_atomic(target, skeleton)

    def tileset(self) -> Doc:
        """The project's tileset: ``{image, tilewidth, tileheight, count, tiles: [{gid, label, layer}]}``."""
        ensure_starter_files(self.root)
        path = self.root / ops.TILESET_SOURCE
        data = json.loads(path.read_text(encoding="utf-8"))
        tiles = []
        for entry in data.get("tiles") or []:
            props = {p.get("name"): p.get("value") for p in entry.get("properties") or [] if isinstance(p, dict)}
            tiles.append({"gid": int(entry["id"]) + 1, "label": str(props.get("label") or f"Tile {entry['id']}"),
                          "layer": ops.WALLS if props.get("layer") == ops.WALLS else ops.GROUND})
        return {"image": str(path.parent / data["image"]), "tilewidth": int(data["tilewidth"]),
                "tileheight": int(data["tileheight"]), "count": int(data["tilecount"]), "tiles": tiles}

    def link_rooms(self, key_a: str, at_a: tuple[float, float], key_b: str, at_b: tuple[float, float]) -> None:
        before = self._snapshot()
        a, b = ops.link_rooms(self.scene(key_a), key_a, self.label(key_a), at_a, self.scene(key_b), key_b, self.label(key_b), at_b)
        self._record(before)
        self.scenes[key_a], self.scenes[key_b] = a, b
        self.dirty.update((key_a, key_b))

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def save(self) -> list[str]:
        """Write every changed room and the world file. Returns the paths written."""
        written: list[str] = []
        for key in sorted(self.dirty):
            write_json_atomic(self.root / self.path(key), self.scenes[key])
            written.append(self.path(key))
        if self.world_dirty:
            write_json_atomic(self.root / self.world_file, self.world)
            written.append(self.world_file)
        self.dirty.clear()
        self.world_dirty = False
        return written
