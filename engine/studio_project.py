"""The project the Studio edits: the world file plus open scene documents, with undo.

Documents are plain dicts and every change goes through engine.project_ops, so this
module never draws, never touches a running game, and can be tested headless. Undo
stores whole-document snapshots: scenes are small, and snapshots cannot drift out of
sync the way per-command inverse logic did in the old editor.

The game has one player. Rooms hold only where it starts (``prefab_id: "player"``); its
definition is the project's ``player`` prefab. ``scene()`` hands rooms out with the player
filled in, so every operation edits it like any object, and storing a room splits it again:
a change to the player in one room is a change to the player in every room.
"""

from __future__ import annotations

import copy
import json
import os
import pickle
import posixpath
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator

from engine import project_ops as ops
from engine.json_io import read_json, write_json_atomic
from engine.project_save import SaveError, refused, save_documents
from engine.project_scaffold import ensure_starter_files

Doc = dict[str, Any]
UNDO_LIMIT = 100



def _copy(doc: Any) -> Any:
    """A deep copy of a project document (JSON data): a pickle round trip, several times faster than deepcopy for a
    room holding thousands of scattered things; deepcopy if something in it won't pickle."""
    try:
        return pickle.loads(pickle.dumps(doc, protocol=pickle.HIGHEST_PROTOCOL))
    except (pickle.PicklingError, TypeError, AttributeError):
        return copy.deepcopy(doc)


def _norm(rel: str) -> str:
    """A project-relative path compared as the file system does (Windows: case-insensitive, either slash)."""
    return posixpath.normpath(str(rel).replace("\\", "/")).casefold()


def _older_sheet(target: Path, source: Path) -> bool:
    """Whether the project's ``target`` is an older copy of Mesh's sheet ``source``: narrower, and pixel for pixel
    Mesh's as far as it goes (Milestone 23B's campfire added cells after 20E's: a sheet a creator changed is kept)."""
    if target.suffix != ".png":
        return False
    from PIL import Image, ImageChops  # noqa: PLC0415

    try:
        with Image.open(target) as old, Image.open(source) as new:
            if old.width >= new.width or old.height != new.height:
                return False
            box = (0, 0, old.width, old.height)
            return ImageChops.difference(old.convert("RGBA"), new.convert("RGBA").crop(box)).getbbox() is None
    except OSError:
        return False


@dataclass(frozen=True)
class _State:
    world: Doc
    scenes: dict[str, Doc]
    current: str
    dirty: frozenset[str]
    world_dirty: bool
    player: Doc | None
    player_dirty: bool


class Project:
    def __init__(self, root: Path, world_file: str) -> None:
        self.root = Path(root)
        self.world_file = world_file
        self.world: Doc = json.loads((self.root / world_file).read_text(encoding="utf-8"))
        self._seen_on_disk: dict[str, float] = {world_file: (self.root / world_file).stat().st_mtime}
        self.last_save_backups: list[str] = []
        self.last_save_report: Doc | None = None  # (the last save's outcome: engine.project_save.report)
        self.scenes: dict[str, Doc] = {}
        self.dirty: set[str] = set()
        self.world_dirty = False
        rooms = ops.world_rooms(self.world)
        if not rooms:
            raise ValueError(f"{world_file} lists no rooms")
        self.current: str = ops.start_room(self.world) or rooms[0][0]  # (a world naming no room of its own: its first)
        self._undo: list[_State] = []
        self._redo: list[_State] = []
        self.revision = 0  # goes up with every change, undo and redo: what an AI's view is "as of"
        self.writes_files = True  # False for a dry run: nothing touches the disk
        self._tx_depth = 0
        self._views: dict[str, tuple[Doc, Doc | None, Doc]] = {}  # room -> (stored, player, expanded) cache
        self.player: Doc | None = self._read_player()  # the shared player's definition (None: rooms have their own)
        self.player_dirty = False
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
        """The room a new game starts in (``ops.start_room``), else the first room (a world naming none of its own)."""
        return ops.start_room(self.world) or self.rooms()[0][0]

    def set_start_room(self, key: str) -> None:
        """A new game starts in room ``key`` (Milestone 23D): the world's ``start_scene``, one undo step; the room being
        edited stays the one being edited. An OpError (no such room) changes nothing."""
        world = ops.set_start_room(self.world, key)
        if world == self.world:
            return
        before = self._snapshot()
        self._record(before)
        self.world, self.world_dirty = world, True

    def scene(self, key: str | None = None) -> Doc:
        """A room as editors see it: the shared player filled in (don't change it in place)."""
        key = key or self.current
        stored = self._room(key)
        view = self._views.get(key)
        if view is None or view[0] is not stored or view[1] is not self.player:
            view = (stored, self.player, ops.expand_players(stored, self.player))
            self._views[key] = view
        return view[2]

    def _room(self, key: str) -> Doc:
        """A room as stored: the shared player is a reference."""
        if key not in self.scenes:
            path = self.root / self.path(key)
            raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"name": self.label(key), "entities": []}
            if path.is_file():
                self._seen_on_disk[self.path(key)] = path.stat().st_mtime
            self.scenes[key] = ops.ensure_entity_ids(raw, key)
        return self.scenes[key]

    def _store(self, key: str, doc: Doc, player_ids: list[str]) -> None:
        """Keep an edited room, the shared player split back out of it (its definition may have changed)."""
        stored, definition = ops.split_players(doc, player_ids, self.player)
        self.scenes[key] = stored
        self.dirty.add(key)
        if definition is not None and definition != self.player:
            self.player, self.player_dirty = definition, True

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty) or self.world_dirty or self.player_dirty

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def player_template(self) -> Doc | None:
        """What a new room gets so you can walk around in it: a reference to the shared player (or, in a
        project whose rooms still have their own, a copy of the start room's)."""
        for entity in ops.entities(self._room(self.start_key())):
            if entity.get("prefab_id") == ops.PLAYER_PREFAB:
                return ops.thin_player(entity)
            if entity.get("tag") == "player":
                return entity
        return None

    def documents(self) -> dict[Path, Doc]:
        """Absolute path -> document for every room the Studio has open (for play-testing). Rooms refer to
        the shared player; ``player_prefab()`` is its definition for the runtime's prefab manager."""
        return {self.root / self.path(key): doc for key, doc in self.scenes.items()}

    def is_shared_player(self, entity_id: str | None, key: str | None = None) -> bool:
        """Whether that object in the room is the game's one player."""
        return bool(entity_id) and entity_id in ops.shared_player_ids(self._room(key or self.current))

    def player_prefab(self) -> Doc | None:
        """The shared player as an ``assets/prefabs.json`` entry (None if rooms still have their own)."""
        return ops.player_prefab_entry(self.player) if self.player is not None else None

    # --- the shared player --------------------------------------------------------------------
    PREFABS = "assets/prefabs.json"

    def _read_prefabs(self) -> list[Doc]:
        """The prefab list, to read the shared player from: none if the file is missing or can't be read (the project
        still opens). Saving uses ``_prefab_catalogue``, which never takes an unreadable file for an empty one."""
        try:
            return self._prefab_catalogue()
        except ops.OpError:
            return []

    def _prefab_catalogue(self) -> list[Any]:
        """``assets/prefabs.json`` as it is, to save the shared player into: [] only when there is no such file (a new
        or older project starts one). A file that is there but can't be read, isn't JSON or isn't a list is never
        taken for an empty one (saving would replace every prefab in it): ops.OpError, before anything is written."""
        path = self.root / self.PREFABS
        try:
            path.stat()
        except FileNotFoundError:
            return []
        except OSError as err:
            raise ops.OpError(self._unreadable_prefabs(f"it can't be read: {err}")) from err
        try:
            data = read_json(path)
        except OSError as err:  # (no permission, locked, a folder...)
            raise ops.OpError(self._unreadable_prefabs(f"it can't be read: {err}")) from err
        except ValueError as err:  # (not JSON, or not UTF-8 text)
            raise ops.OpError(self._unreadable_prefabs(f"it isn't valid JSON: {err}")) from err
        if not isinstance(data, list):
            raise ops.OpError(self._unreadable_prefabs(f"it holds {type(data).__name__}, not a list of prefabs"))
        return data

    def _unreadable_prefabs(self, why: str) -> str:
        return (f"{self.PREFABS} isn't a prefab list Studio can read ({why}), so the player wasn't saved and nothing "
                "was written: saving would have replaced the other prefabs in it. Fix or restore that file, then save "
                "again; your changes are kept until then.")

    def _read_player(self) -> Doc | None:
        entry = next((p for p in self._read_prefabs() if isinstance(p, dict) and p.get("id") == ops.PLAYER_PREFAB), None)
        if entry is not None and (self.root / self.PREFABS).is_file():
            self._seen_on_disk[self.PREFABS] = (self.root / self.PREFABS).stat().st_mtime
        return copy.deepcopy(entry["entity"]) if entry and isinstance(entry.get("entity"), dict) else None

    def own_players(self) -> dict[str, Doc]:
        """Rooms that still have their own full player (projects made before the player was shared)."""
        found = {key: ops.legacy_player(self._room(key)) for key, _label, _path in self.rooms()}
        return {key: entity for key, entity in found.items() if entity is not None}

    def player_differences(self, source: str | None = None) -> dict[str, list[str]]:
        """How each room's own player differs from ``source``'s (default: the start room's), in words."""
        players = self.own_players()
        source = self._player_source(players, source)
        return ops.player_differences(players, source) if source else {}

    def _player_source(self, players: dict[str, Doc], source: str | None) -> str | None:
        if source in players:
            return source
        return self.start_key() if self.start_key() in players else next(iter(players), None)

    def share_player(self, source: str | None = None) -> dict[str, list[str]]:
        """Give every room one player: ``source``'s (default: the start room's) becomes the game's player
        and each room keeps only where its player starts. One undo step. Returns what was different in
        the other rooms' players (and is now replaced), so it can be reported."""
        players = self.own_players()
        source = self._player_source(players, source)
        if source is None:
            return {}
        differences = ops.player_differences(players, source)
        before = self._snapshot()
        for key, entity in players.items():
            room = self._room(key)
            self.scenes[key] = {**room, "entities": [ops.thin_player(e) if e is entity else e for e in ops.entities(room)]}
            self.dirty.add(key)
        self.player, self.player_dirty = ops.player_definition(players[source]), True
        self._record(before)
        return differences

    # --- editing ----------------------------------------------------------------------------
    def _snapshot(self) -> _State:
        return _State(_copy(self.world), _copy(self.scenes), self.current, frozenset(self.dirty),
                      self.world_dirty, _copy(self.player), self.player_dirty)

    def _restore(self, state: _State) -> None:
        self.world = _copy(state.world)
        self.scenes = _copy(state.scenes)
        self.current = state.current
        self.dirty = set(state.dirty)
        self.world_dirty = state.world_dirty
        self.player = _copy(state.player)
        self.player_dirty = state.player_dirty

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
        if not self._tx_depth and (self.scenes != before.scenes or self.world != before.world
                                   or self.player != before.player):
            self._record(before)

    def all_documents(self) -> Doc:
        """``{"world": ..., "rooms": {key: room}, "player": ...}`` with every room loaded: a whole-project
        view (rooms as stored; ``player`` is the shared player's definition, or None)."""
        return {"world": self.world, "rooms": {key: self._room(key) for key, _label, _path in self.rooms()},
                "player": self.player}

    def clone(self) -> "Project":
        """A copy to try changes on (a dry run): same documents, no undo history, writes nothing."""
        copy_ = Project.__new__(Project)
        copy_.root, copy_.world_file = self.root, self.world_file
        copy_.world, copy_.scenes = copy.deepcopy(self.world), copy.deepcopy(self.scenes)
        copy_.dirty, copy_.world_dirty, copy_.current = set(self.dirty), self.world_dirty, self.current
        copy_.player, copy_.player_dirty, copy_._views = copy.deepcopy(self.player), self.player_dirty, {}
        copy_._undo, copy_._redo, copy_.revision, copy_.writes_files, copy_._tx_depth = [], [], self.revision, False, 0
        copy_._seen_on_disk = dict(self._seen_on_disk)  # (a room loaded first in the copy records when it was read)
        return copy_

    def load_documents(self, docs: Doc) -> None:
        """Replace the documents with ``docs`` (from ``all_documents``), for a clone made at another revision."""
        self.world, self.scenes = copy.deepcopy(docs["world"]), copy.deepcopy(docs["rooms"])
        if "player" in docs:
            self.player = copy.deepcopy(docs["player"])

    def edit_scene(self, change: Callable[[Doc], Doc], key: str | None = None) -> None:
        """Replace one room with ``change(room)``. An OpError leaves everything untouched."""
        key = key or self.current
        before = self._snapshot()
        player_ids = ops.shared_player_ids(self._room(key))
        updated = change(self.scene(key))
        self._record(before)
        self._store(key, updated, player_ids)

    def add_room(self, label: str) -> str:
        """A new room with its own player and a ready-to-paint map: wood floor, stone-wall border."""
        before = self._snapshot()
        world, scene, key, path = ops.new_room(self.world, label, self.scenes_dir(), self.player_template())
        scene, map_path, skeleton = ops.add_map(scene, path, width=20, height=15, ground=ops.STARTER_FLOOR,
                                                border=ops.STARTER_WALL, tilesets=self.project_tilesets())
        self._claim_room_files(label, path, map_path)
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self.world, self.world_dirty = world, True
        self.scenes[key] = scene
        self.dirty.add(key)
        return key

    def add_hd2d_room(self, label: str, width_m: Any, depth_m: Any, *, outdoor: bool = True) -> tuple[str, bool]:
        """A new HD-2D room ``width_m`` x ``depth_m`` m (Milestone 22A: ``project_ops.make_hd2d_room``, the HD-2D
        template's own recipe): grass ground, a camera framed for it, the default sun. A project without the HD-2D
        starter kit (a 2D project's first HD-2D room) gets it first, as the HD-2D template installs it: that is
        written straight away (like importing a model), the room itself is one undo step. Returns ``(key, whether
        the kit was installed now)``."""
        world, scene, key, path = ops.new_room(self.world, label, self.scenes_dir(), self.player_template())
        scene, map_path, skeleton = ops.make_hd2d_room(scene, path, width_m, depth_m, outdoor=outdoor,
                                                       tilesets=self.project_tilesets())
        self._claim_room_files(label, path, map_path)  # (before the kit: a refused room installs nothing)
        installed = self.ensure_hd2d_kit()
        before = self._snapshot()
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self.world, self.world_dirty = world, True
        self.scenes[key] = scene
        self.dirty.add(key)
        return key, installed

    def _claim_room_files(self, label: str, *paths: str) -> None:
        """F15: a new room's files (its scene and map) must be its own: nothing on disk there yet (a file, a folder or a
        link this project's rooms don't list, made by hand or by another tool) and no other room's. Mesh never takes
        one over: OpError naming it, before anything is changed or written. ``save`` checks the scene again."""
        listed = {_norm(p): lbl for _k, lbl, p in self.rooms()}
        for rel in paths:
            other = listed.get(_norm(rel))
            target = self.root / rel
            if other is None and not os.path.lexists(target):
                continue
            if other is not None:
                taken = f"{rel} is already the file of the room '{other}'"
            else:
                what = "a link" if target.is_symlink() else "a folder" if target.is_dir() else "a file"
                taken = f"There is already {what} at {rel} that isn't one of this project's rooms"
            raise ops.OpError(f"{taken}, so the room '{label}' wasn't added and nothing was changed: Mesh never takes "
                              f"over a file it didn't make. Give the room another name, or move {rel} out of the way "
                              "first.")

    def ensure_hd2d_kit(self) -> bool:
        """The HD-2D starter kit in the project (its models, ground textures and scatter decoration), copied from Mesh
        as the HD-2D template does; True if anything was copied now. Never overwrites a file the project has."""
        import shutil  # noqa: PLC0415

        from engine.hd2d import catalog  # noqa: PLC0415
        from engine.hd2d.starter_village import GROUND_TEXTURES, KIT, SCATTER_KIT  # noqa: PLC0415
        from engine.repo_root import bundled_dir, bundled_file  # noqa: PLC0415

        if not self.writes_files:
            return False
        copied = False
        kit_ids = {str(m.get("id")) for m in json.loads((bundled_dir(KIT) / "catalog.json").read_text(
            encoding="utf-8")).get("models", [])}
        have = {str(m.get("id")) for m in (self._read_json(catalog.CATALOG) or {}).get("models", [])
                if isinstance(m, dict)}
        if not kit_ids & have:
            try:
                catalog.install_kit(self.root, bundled_dir(KIT))
                copied = True
            except catalog.CatalogError as exc:
                raise ops.OpError(f"Mesh couldn't add its HD-2D starter kit to this project: {exc}") from exc
        for rel in (*GROUND_TEXTURES, *SCATTER_KIT):
            target, source = self.root / rel, bundled_file(rel)
            if source is not None and (not target.is_file() or _older_sheet(target, source)):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                copied = True
        return copied

    def add_map(self, key: str | None = None) -> None:
        """Give a room without a map an empty one that covers its objects."""
        key = key or self.current
        width, height = ops.map_size_for(self.scene(key))
        before = self._snapshot()
        player_ids = ops.shared_player_ids(self._room(key))
        scene, map_path, skeleton = ops.add_map(self.scene(key), self.path(key), width=width, height=height,
                                                tilesets=self.project_tilesets())
        self._write_map_file(map_path, skeleton)
        self._record(before)
        self._store(key, scene, player_ids)

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

    # --- sounds (Milestone 21B: copied in straight away, like pictures; not part of undo) ----------------------------
    def sounds(self) -> list[str]:
        """Every sound file under ``assets/`` (.wav, .ogg, .mp3), project-relative, ambience first."""
        from engine.sound_emitters import SOUND_FILES  # noqa: PLC0415

        assets = self.root / "assets"
        found = [p for p in assets.rglob("*") if p.suffix.lower() in SOUND_FILES] if assets.is_dir() else []
        rel = [p.relative_to(self.root).as_posix() for p in found]
        return sorted(rel, key=lambda r: (not r.startswith("assets/ambience/"), r.lower()))

    def music_files(self) -> list[str]:
        """Every sound file under ``assets/`` (.wav, .ogg, .mp3), project-relative, ``assets/music/`` first (Milestone
        23D: a room's soundtrack; other sounds can be music too)."""
        return sorted(self.sounds(), key=lambda r: (not r.startswith("assets/music/"), r.lower()))

    def import_sound(self, sound_path: Path | str, folder_name: str = "ambience") -> str:
        """Copy a sound file into ``assets/ambience/`` (or ``assets/<folder_name>/``: "music" for a room's
        soundtrack) and return its project-relative path, after checking this computer can play it
        (``sound_emitters.sound_problem``). One already in the project is used where it is; one with the same name
        and the same bytes is not copied again; one with the same name and other bytes is copied under a new name
        (``_2``...): a file already there is never replaced."""
        import shutil  # noqa: PLC0415

        from engine.sound_emitters import sound_problem  # noqa: PLC0415

        source = Path(str(sound_path).strip().strip('"'))
        problem = sound_problem(source)
        if problem:
            raise ops.OpError(problem)
        try:
            inside = source.resolve().relative_to(self.root.resolve())
        except ValueError:
            inside = None
        if inside is not None:
            return inside.as_posix()
        if folder_name not in ("ambience", "music"):
            raise ValueError(f"sounds are imported into assets/ambience or assets/music, not {folder_name!r}")
        folder = self.root / "assets" / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        stem, suffix, n = ops.slug(source.stem) or "sound", source.suffix.lower(), 2
        candidate = stem
        while (folder / f"{candidate}{suffix}").exists():
            if (folder / f"{candidate}{suffix}").read_bytes() == source.read_bytes():
                return f"assets/{folder_name}/{candidate}{suffix}"  # already copied in
            candidate, n = f"{stem}_{n}", n + 1
        shutil.copyfile(source, folder / f"{candidate}{suffix}")
        return f"assets/{folder_name}/{candidate}{suffix}"

    # --- HD-2D models (engine.hd2d.catalog: copied in straight away, like pictures; not part of undo) ----------
    def model_assets(self) -> list[Any]:
        """The project's Blender models: the catalogue's, then any other .glb, as ``ModelAsset``s."""
        from engine.hd2d import catalog  # noqa: PLC0415

        listed: list[Any] = self._catalog_call(catalog.assets, self.root)
        return listed

    def import_model(self, source: Path | str, **fields: Any) -> Any:
        """Copy a Blender .glb into ``assets/models/`` with its preview and catalogue entry (``name``, ``category``,
        ``notes``, ``license``, ``pixels``). Returns the ``ModelAsset``; raises OpError and writes nothing if refused."""
        from engine.hd2d import catalog  # noqa: PLC0415

        return self._catalog_call(catalog.import_model, self.root, source, **fields)

    def plan_reimport(self, ref: str, source: Path | str | None = None) -> Any:
        """What reimporting model ``ref`` would change, judged against every room as edited now. Writes nothing."""
        from engine.hd2d import catalog  # noqa: PLC0415

        return self._catalog_call(catalog.plan_reimport, self.root, ref, source, rooms=self.all_documents()["rooms"])

    def reimport_model(self, ref: str, source: Path | str | None = None) -> Any:
        """Replace model ``ref``'s file with a new export; every placed copy keeps its id and place."""
        from engine.hd2d import catalog  # noqa: PLC0415

        return self._catalog_call(catalog.reimport_model, self.root, ref, source, rooms=self.all_documents()["rooms"])

    def set_model_properties(self, ref: str, **fields: Any) -> Any:
        from engine.hd2d import catalog  # noqa: PLC0415

        return self._catalog_call(catalog.set_properties, self.root, ref, **fields)

    @staticmethod
    def _catalog_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        from engine.hd2d.catalog import CatalogError  # noqa: PLC0415

        try:
            return func(*args, **kwargs)
        except CatalogError as err:
            raise ops.OpError(str(err)) from err

    def images(self) -> list[str]:
        """Every picture under ``assets/`` (tilesets aside), project-relative, sprites first. Model previews are the
        model browser's, not pictures to give objects."""
        assets = self.root / "assets"
        found = [p for p in assets.rglob("*") if p.suffix.lower() in self.IMAGE_TYPES and "tilesets" not in p.parts
                 and "templates" not in p.parts and "models" not in p.parts] if assets.is_dir() else []
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
        ids_a, ids_b = ops.shared_player_ids(self._room(key_a)), ops.shared_player_ids(self._room(key_b))
        a, b = ops.link_rooms(self.scene(key_a), key_a, self.label(key_a), at_a, self.scene(key_b), key_b, self.label(key_b), at_b)
        self._record(before)
        self._store(key_a, a, ids_a)
        self._store(key_b, b, ids_b)

    def _map_file_at_size(self, key: str) -> tuple[str, Doc] | None:
        """An HD-2D room grown in Studio (``ops.expand_hd2d_room``): its map file (the map's size, tilesets and empty
        layers; the tiles live in the room) at the room's size, to be saved with it; None when they already agree.
        A map file with tiles of its own is never resized: OpError, and nothing is saved."""
        scene = self.scenes[key]
        info, rel = ops.map_info(scene), self.map_path(key)
        if not isinstance((scene.get("settings") or {}).get("hd2d"), dict) or info is None or rel is None:
            return None
        doc = self._read_json(rel)
        if doc is None:  # missing or unreadable: never rebuilt (its tilesets are only in it), never passed over
            saved = self._read_json(self.path(key))  # ... unless the room's size is what was saved with it before
            saved_info = ops.map_info(saved) if saved is not None else None
            if saved_info is not None and (saved_info["width"], saved_info["height"]) == (info["width"], info["height"]):
                return None
            state = "can't be read" if (self.root / rel).exists() else "is missing"
            raise ops.OpError(f"{rel} {state}, so it can't be kept at the room's {info['width']} x {info['height']} "
                              "tiles; nothing was saved. Put the map file back (or undo the change of size) and save "
                              "again.")
        if (doc.get("width"), doc.get("height")) == (info["width"], info["height"]):
            return None
        layers = doc.get("layers")
        if doc.get("infinite") or not isinstance(layers, list) or not all(
                isinstance(layer, dict) and layer.get("type") == "tilelayer" and not any(layer.get("data") or [])
                for layer in layers):
            raise ops.OpError(f"{rel} has tiles or objects of its own, so it isn't resized to the room's "
                              f"{info['width']} x {info['height']} tiles; nothing was saved.")
        w, h = info["width"], info["height"]
        resized = {**doc, "width": w, "height": h,
                   "layers": [{**layer, "width": w, "height": h, "data": [0] * (w * h)} for layer in layers]}
        return rel, resized

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
        """Write every changed room, the world file and the shared player as one save (``engine.project_save``): all
        of them or none. Returns the paths written. A save that fails raises SaveError (an ops.OpError) with a report
        of what happened to each file; nothing here changes then (the edits stay unsaved, undo as it was).
        ``last_save_report`` holds the outcome either way, ``last_save_backups`` outside changes kept beside files."""
        self.last_save_backups, self.last_save_report = [], None
        rooms = sorted(self.dirty)
        planned = [(self.path(key), "room") for key in rooms]
        if self.world_dirty:
            planned.append((self.world_file, "world"))
        try:  # an HD-2D room's map file at the room's size first: checked before anything is written
            maps = [m for m in (self._map_file_at_size(key) for key in rooms) if m is not None]
        except ops.OpError as err:
            raise self._refused(refused("map_file_conflict", str(err), planned, self.root)) from err
        documents: list[tuple[str, str, Any]] = [(rel, "map", doc) for rel, doc in maps]
        documents += [(self.path(key), "room", self.scenes[key]) for key in rooms]
        if self.world_dirty:
            documents.append((self.world_file, "world", self.world))
        if self.player_dirty and self.player is not None:
            # The shared player is one entry of the project's prefab list: every other entry stays as it was.
            # (an unreadable or malformed file refuses the save here, before anything is written: H1-F2)
            try:
                catalogue = self._prefab_catalogue()
            except ops.OpError as err:
                involved = [(rel, kind) for rel, kind, _doc in documents] + [(self.PREFABS, "prefabs")]
                raise self._refused(refused("prefab_catalogue_unreadable", str(err), involved, self.root)) from err
            prefabs = [p for p in catalogue if not (isinstance(p, dict) and p.get("id") == ops.PLAYER_PREFAB)]
            documents.append((self.PREFABS, "prefabs", [ops.player_prefab_entry(self.player), *prefabs]))
        try:
            # A room file this project never read or wrote (a new room's, or a listed room's missing file) is created by
            # this save: never over something another tool put there meanwhile (F15).
            fresh = {self.path(key) for key in rooms if self.path(key) not in self._seen_on_disk}
            outcome = save_documents(self.root, documents, self._seen_on_disk, fresh)
        except SaveError as err:
            self._refused(err)
            raise
        self.last_save_report, self.last_save_backups = outcome, list(outcome["outside_change_backups"])
        # Undo or redo past this save comes back to rooms other than what was just written: they are to save again.
        saved, world, player = frozenset(self.dirty), self.world_dirty, self.player_dirty
        self._undo, self._redo = [[replace(s, dirty=s.dirty | saved, world_dirty=s.world_dirty or world,
                                           player_dirty=s.player_dirty or player) for s in stack]
                                  for stack in (self._undo, self._redo)]
        self.dirty.clear()
        self.world_dirty = False
        self.player_dirty = False
        return [doc["path"] for doc in outcome["documents"]]

    def _refused(self, err: SaveError) -> SaveError:
        """A failed save, recorded: the edits stay as they are, unsaved (dirty, undo and revision untouched)."""
        self.last_save_report, self.last_save_backups = err.report, list(err.report["outside_change_backups"])
        return err
