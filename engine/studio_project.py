"""The project the Studio edits: the world file plus open scene documents, with undo.

Documents are plain dicts and every change goes through engine.project_ops, so this
module never draws, never touches a running game, and can be tested headless. Undo
stores whole-document snapshots: scenes are small, and snapshots cannot drift out of
sync the way per-command inverse logic did in the old editor.
"""

from __future__ import annotations

import copy
import json
import posixpath
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

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
        self._seen_on_disk: dict[str, float] = {world_file: (self.root / world_file).stat().st_mtime}
        self.last_save_backups: list[str] = []
        self.scenes: dict[str, Doc] = {}
        self.dirty: set[str] = set()
        self.world_dirty = False
        rooms = ops.world_rooms(self.world)
        if not rooms:
            raise ValueError(f"{world_file} lists no rooms")
        self.current: str = str(self.world.get("start_scene") or rooms[0][0])
        self._undo: list[_State] = []
        self._redo: list[_State] = []
        self.revision = 0  # goes up with every change, undo and redo: what an AI's view is "as of"
        self.writes_files = True  # False for a dry run: nothing touches the disk
        self._tx_depth = 0
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
            if path.is_file():
                self._seen_on_disk[self.path(key)] = path.stat().st_mtime
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
        if self._tx_depth:
            return  # the transaction records once, at its end
        self._undo.append(before)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.revision += 1

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group several edits into one undo step; any exception puts everything back."""
        before = self._snapshot()
        self._tx_depth += 1
        try:
            yield
        except BaseException:
            self._tx_depth -= 1
            self._restore(before)
            raise
        self._tx_depth -= 1
        if not self._tx_depth and (self.scenes != before.scenes or self.world != before.world):
            self._record(before)

    def all_documents(self) -> Doc:
        """``{"world": ..., "rooms": {key: room}}`` with every room loaded: a whole-project view."""
        return {"world": self.world, "rooms": {key: self.scene(key) for key, _label, _path in self.rooms()}}

    def clone(self) -> "Project":
        """A copy to try changes on (a dry run): same documents, no undo history, writes nothing."""
        copy_ = Project.__new__(Project)
        copy_.root, copy_.world_file = self.root, self.world_file
        copy_.world, copy_.scenes = copy.deepcopy(self.world), copy.deepcopy(self.scenes)
        copy_.dirty, copy_.world_dirty, copy_.current = set(self.dirty), self.world_dirty, self.current
        copy_._undo, copy_._redo, copy_.revision, copy_.writes_files, copy_._tx_depth = [], [], self.revision, False, 0
        return copy_

    def load_documents(self, docs: Doc) -> None:
        """Replace the documents with ``docs`` (from ``all_documents``), for a clone made at another revision."""
        self.world, self.scenes = copy.deepcopy(docs["world"]), copy.deepcopy(docs["rooms"])

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
        scene, map_path, skeleton = ops.add_map(scene, path, width=20, height=15, ground=ops.STARTER_FLOOR,
                                                border=ops.STARTER_WALL, tilesets=self.project_tilesets())
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
        scene, map_path, skeleton = ops.add_map(self.scene(key), self.path(key), width=width, height=height,
                                                tilesets=self.project_tilesets())
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self.scenes[key] = scene
        self.dirty.add(key)

    def _write_map_file(self, map_path: str, skeleton: Doc) -> None:
        # The map file holds only the size, tileset and empty layers (the painted tiles live
        # in the room document), so it is written straight away: the Studio and play-tests
        # load it from disk even before the room is saved.
        if not self.writes_files:
            return
        ensure_starter_files(self.root)
        target = self.root / map_path
        if not target.is_file():
            write_json_atomic(target, skeleton)

    # --- tilesets -------------------------------------------------------------------------
    def map_path(self, key: str | None = None) -> str | None:
        """Project-relative path of a room's map file, or None if the room has no map."""
        tilemap = self.scene(key).get("tilemap")
        if not isinstance(tilemap, dict) or not tilemap.get("path"):
            return None
        scene_dir = posixpath.dirname(self.path(key or self.current).replace("\\", "/"))
        return posixpath.normpath(posixpath.join(scene_dir, str(tilemap["path"]).replace("\\", "/")))

    def _read_json(self, rel: str) -> Doc | None:
        try:
            data = json.loads((self.root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def project_tilesets(self) -> list[tuple[str, int]]:
        """The tilesets new maps reference, with their first tile ids: the start room's, else the starter's."""
        start_map = self.map_path(self.start_key())
        doc = self._read_json(start_map) if start_map else None
        found = ops.map_tilesets(doc, start_map) if doc and start_map else []
        return found or [(ops.TILESET_SOURCE, 1)]

    def room_tilesets(self, key: str | None = None) -> list[Doc]:
        """The tilesets a room's map can paint with, in palette order.

        Each: ``{name, source, firstgid, image, columns, rows, count, tile, hints}``; ``hints``
        maps a local tile id to the ``{label, layer}`` its tileset suggests (the starter's do).
        """
        ensure_starter_files(self.root)
        map_rel = self.map_path(key)
        map_doc = self._read_json(map_rel) if map_rel else None
        out = []
        for source, firstgid in ops.map_tilesets(map_doc, map_rel) if map_doc and map_rel else []:
            data = self._read_json(source)
            if not data or not data.get("image"):
                continue
            tile = int(data.get("tilewidth") or ops.TILE_SIZE)
            columns = int(data.get("columns") or max(1, int(data.get("imagewidth", tile)) // tile))
            count = int(data.get("tilecount") or 0)
            hints = {}
            for entry in data.get("tiles") or []:
                props = {p.get("name"): p.get("value") for p in entry.get("properties") or [] if isinstance(p, dict)}
                layer = props.get("layer")
                hints[int(entry["id"])] = {"label": str(props.get("label") or ""),
                                           "layer": layer if layer in (ops.GROUND, ops.WALLS, ops.OVERHEAD) else None}
            image = (self.root / posixpath.dirname(source) / str(data["image"])).resolve()
            out.append({"name": str(data.get("name") or posixpath.splitext(posixpath.basename(source))[0]),
                        "source": source, "firstgid": firstgid, "image": str(image), "columns": columns,
                        "rows": -(-count // columns), "count": count, "tile": tile, "hints": hints})
        return out

    def import_tileset(self, image_path: Path | str, tile_size: int, name: str) -> Doc:
        """Copy an image into the project as a tileset every room can paint with.

        The image is cut to whole tiles and, if its tiles aren't the map's size, scaled so
        they are: tiles always line up with the grid. Transparency is kept. Writes
        ``assets/tilesets/<name>.png`` and ``.json`` and adds the tileset to every room's
        map file straight away (map files hold no painted tiles and an unused tileset is
        harmless, so importing isn't part of undo). Returns ``{name, source, count, scaled}``.
        """
        from PIL import Image  # noqa: PLC0415

        source = Path(str(image_path).strip().strip('"'))
        if not source.is_file():
            raise ops.OpError(f"There is no file at {source}.")
        if not 8 <= int(tile_size) <= 256:
            raise ops.OpError("The tile size must be between 8 and 256 pixels.")
        try:
            with Image.open(source) as img:
                image = img.convert("RGBA")
        except (OSError, ValueError) as exc:
            raise ops.OpError(f"{source.name} isn't an image Mesh can read.") from exc
        columns, rows = image.width // tile_size, image.height // tile_size
        if columns < 1 or rows < 1:
            raise ops.OpError(f"The image ({image.width}x{image.height}) is smaller than one {tile_size} px tile.")
        if columns * rows > 4096:
            raise ops.OpError("That's more than 4096 tiles; split the image into smaller tilesets.")
        image = image.crop((0, 0, columns * tile_size, rows * tile_size))
        size = (columns * ops.TILE_SIZE, rows * ops.TILE_SIZE)
        if tile_size != ops.TILE_SIZE:
            image = image.resize(size, Image.Resampling.NEAREST if tile_size < ops.TILE_SIZE else Image.Resampling.LANCZOS)
        label = (name or source.stem).strip() or "Tileset"
        slug = ops.slug(label)
        folder = posixpath.dirname(ops.TILESET_SOURCE)
        candidate, n = slug, 2
        while (self.root / folder / f"{candidate}.json").exists() or (self.root / folder / f"{candidate}.png").exists():
            candidate, n = f"{slug}_{n}", n + 1
        document = ops.tileset_document(label, f"{candidate}.png", *size)
        (self.root / folder).mkdir(parents=True, exist_ok=True)
        image.save(self.root / folder / f"{candidate}.png")
        rel = f"{folder}/{candidate}.json"
        write_json_atomic(self.root / rel, document)
        self._add_tileset_to_maps(rel)
        return {"name": label, "source": rel, "count": document["tilecount"], "scaled": tile_size != ops.TILE_SIZE}

    IMAGE_TYPES = (".png", ".gif", ".bmp", ".jpg", ".jpeg", ".webp")

    def import_sprite(self, image_path: Path | str) -> str:
        """Copy a picture into ``assets/sprites/`` (as PNG, transparency kept) and return its
        project-relative path. An image already inside the project is used where it is."""
        from PIL import Image  # noqa: PLC0415

        source = Path(str(image_path).strip().strip('"'))
        if not source.is_file():
            raise ops.OpError(f"There is no file at {source}.")
        try:
            inside = source.resolve().relative_to(self.root.resolve())
        except ValueError:
            inside = None
        if inside is not None:
            return inside.as_posix()
        try:
            with Image.open(source) as img:
                image = img.convert("RGBA")
        except (OSError, ValueError) as exc:
            raise ops.OpError(f"{source.name} isn't an image Mesh can read.") from exc
        folder = self.root / "assets" / "sprites"
        folder.mkdir(parents=True, exist_ok=True)
        stem, n = ops.slug(source.stem) or "sprite", 2
        candidate = stem
        while (folder / f"{candidate}.png").exists():
            candidate, n = f"{stem}_{n}", n + 1
        image.save(folder / f"{candidate}.png")
        return f"assets/sprites/{candidate}.png"

    def images(self) -> list[str]:
        """Every picture under ``assets/`` (tilesets aside), project-relative, sprites first."""
        assets = self.root / "assets"
        found = [p for p in assets.rglob("*") if p.suffix.lower() in self.IMAGE_TYPES and "tilesets" not in p.parts
                 and "templates" not in p.parts] if assets.is_dir() else []
        rel = [p.relative_to(self.root).as_posix() for p in found]
        return sorted(rel, key=lambda r: (not r.startswith("assets/sprites/"), r.lower()))

    def _add_tileset_to_maps(self, tileset_rel: str) -> None:
        counts: dict[str, int] = {}
        for key, _label, _path in self.rooms():
            map_rel = self.map_path(key)
            map_doc = self._read_json(map_rel) if map_rel else None
            if map_rel is None or map_doc is None:
                continue
            for src, _gid in ops.map_tilesets(map_doc, map_rel):
                if src not in counts:
                    counts[src] = int((self._read_json(src) or {}).get("tilecount") or 0)
            updated = ops.with_tileset(map_doc, map_rel, tileset_rel, counts)
            if updated != map_doc:
                write_json_atomic(self.root / map_rel, updated)

    def link_rooms(self, key_a: str, at_a: tuple[float, float], key_b: str, at_b: tuple[float, float]) -> None:
        """Connect two rooms with a door in each (at ``at_a`` in room ``key_a``, ``at_b`` in ``key_b``), each with its arrival spot."""
        before = self._snapshot()
        a, b = ops.link_rooms(self.scene(key_a), key_a, self.label(key_a), at_a, self.scene(key_b), key_b, self.label(key_b), at_b)
        self._record(before)
        self.scenes[key_a], self.scenes[key_b] = a, b
        self.dirty.update((key_a, key_b))

    def _keep_outside_change(self, rel: str) -> None:
        """Before overwriting a file something else changed since it was opened, keep that version."""
        target = self.root / rel
        seen = self._seen_on_disk.get(rel)
        if seen is not None and target.is_file() and target.stat().st_mtime != seen:
            backup = target.with_name(target.name + ".outside-change.bak")
            backup.write_bytes(target.read_bytes())
            self.last_save_backups.append(backup.relative_to(self.root).as_posix())

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self.revision += 1
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self.revision += 1
        return True

    def save(self) -> list[str]:
        """Write every changed room and the world file. Returns the paths written."""
        written: list[str] = []
        self.last_save_backups = []
        targets = [(self.path(key), self.scenes[key]) for key in sorted(self.dirty)]
        if self.world_dirty:
            targets.append((self.world_file, self.world))
        for rel, doc in targets:
            self._keep_outside_change(rel)
            write_json_atomic(self.root / rel, doc)
            self._seen_on_disk[rel] = (self.root / rel).stat().st_mtime
            written.append(rel)
        self.dirty.clear()
        self.world_dirty = False
        return written
