from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path


def _non_empty_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _key(value: object | None) -> str | None:
    """Normalize lookup keys to preserve legacy spawn matching behavior.

    Historically, spawn lookups were case-insensitive and whitespace-tolerant.
    """

    text = _non_empty_str(value)
    if text is None:
        return None
    return text.lower()


def _extract_zone_id(entity_data: dict[str, Any]) -> str | None:
    bcfg = entity_data.get("behaviour_config")
    if not isinstance(bcfg, dict):
        return None
    tz_cfg = bcfg.get("TriggerZone")
    if not isinstance(tz_cfg, dict):
        return None
    return _non_empty_str(tz_cfg.get("zone_id"))


@dataclass(slots=True)
class SceneIndex:
    """Deterministic per-scene multi-key index for entity lookups.

    Defensive behavior:
    - Missing/blank keys are ignored.
    - Duplicates keep the first occurrence (by build order) and are recorded.

    This should be built once per scene load and re-used.
    """

    by_id: Dict[str, Any]
    by_zone_id: Dict[str, Any]
    by_mesh_name: Dict[str, List[Any]]
    duplicate_ids: List[str]
    duplicate_zone_ids: List[str]
    duplicate_mesh_names: List[str]

    @classmethod
    def empty(cls) -> "SceneIndex":
        return cls(
            by_id={},
            by_zone_id={},
            by_mesh_name={},
            duplicate_ids=[],
            duplicate_zone_ids=[],
            duplicate_mesh_names=[],
        )

    @classmethod
    def build_from_sprites(cls, sprites: Iterable[Any]) -> "SceneIndex":
        idx = cls.empty()

        for sprite in sprites:
            entity_data = getattr(sprite, "mesh_entity_data", None)
            if not isinstance(entity_data, dict):
                entity_data = None

            # id
            if entity_data is not None:
                entity_id = _key(entity_data.get("id"))
                if entity_id is not None:
                    if entity_id in idx.by_id:
                        idx.duplicate_ids.append(entity_id)
                    else:
                        idx.by_id[entity_id] = sprite

            # zone_id (TriggerZone)
            if entity_data is not None:
                zone_id_raw = _extract_zone_id(entity_data)
                zone_id = _key(zone_id_raw)
                if zone_id is not None:
                    if zone_id in idx.by_zone_id:
                        idx.duplicate_zone_ids.append(zone_id)
                    else:
                        idx.by_zone_id[zone_id] = sprite

            # mesh_name
            mesh_name = _key(getattr(sprite, "mesh_name", None))
            if mesh_name is not None:
                bucket = idx.by_mesh_name.setdefault(mesh_name, [])
                bucket.append(sprite)
                if len(bucket) > 1:
                    idx.duplicate_mesh_names.append(mesh_name)

        return idx

    def get_by_id(self, entity_id: str) -> Any | None:
        key = _key(entity_id)
        if key is None:
            return None
        return self.by_id.get(key)

    def get_by_zone_id(self, zone_id: str) -> Any | None:
        key = _key(zone_id)
        if key is None:
            return None
        return self.by_zone_id.get(key)

    def get_first_by_mesh_name(self, mesh_name: str) -> Any | None:
        key = _key(mesh_name)
        if key is None:
            return None
        bucket = self.by_mesh_name.get(key)
        if not bucket:
            return None
        return bucket[0]


@dataclass(frozen=True, slots=True)
class SceneListing:
    path: str
    display_name: str


@dataclass(frozen=True, slots=True)
class SceneRow:
    scene_id: str
    display_name: str
    pack_name: str
    is_recent: bool


def _fallback_scene_display_name(scene_path: Path) -> str:
    stem = scene_path.stem
    if not stem:
        return "Scene"
    label = stem.replace("_", " ").replace("-", " ").strip()
    return label or stem


def _scene_display_name(scene_path: Path) -> str:
    try:
        raw = json.loads(scene_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        raw = None
    if isinstance(raw, dict):
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return _fallback_scene_display_name(scene_path)


def list_pack_scene_listings(packs_root: str | Path | None = None) -> list[SceneListing]:
    root = Path(packs_root) if packs_root is not None else resolve_path("packs")
    try:
        if not root.exists():
            return []
    except Exception:  # noqa: BLE001
        return []

    base_root = root.parent
    scene_paths: list[Path] = []
    for pack_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        scenes_dir = pack_dir / "scenes"
        if not scenes_dir.exists():
            continue
        for scene_file in scenes_dir.rglob("*.json"):
            if scene_file.is_file():
                scene_paths.append(scene_file)

    def _normalized_rel_path(path: Path) -> str:
        try:
            rel = path.relative_to(base_root)
        except Exception:
            rel = path
        return normalize_scene_path(str(rel))

    scene_paths.sort(key=lambda path: _normalized_rel_path(path).lower())
    listings: list[SceneListing] = []
    for scene_path in scene_paths:
        rel_path = _normalized_rel_path(scene_path)
        listings.append(SceneListing(path=rel_path, display_name=_scene_display_name(scene_path)))
    return listings


def list_pack_scene_options(packs_root: str | Path | None = None) -> list[tuple[str, str]]:
    return [(entry.path, entry.display_name) for entry in list_pack_scene_listings(packs_root=packs_root)]


def _pack_name_from_scene_id(scene_id: str) -> str:
    normalized = normalize_scene_path(scene_id)
    if not normalized:
        return ""
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2 and parts[0] == "packs":
        return parts[1]
    return ""


def build_scene_rows(filter_text: str, recent_scene_ids: Iterable[str]) -> list[SceneRow]:
    listings = list_pack_scene_listings()
    if not listings:
        return []

    options = [(entry.path, entry.display_name) for entry in listings]
    query = str(filter_text or "").strip()
    if query:
        from .command_palette import filter_options  # noqa: PLC0415

        filtered = filter_options(options, query)
    else:
        filtered = list(options)

    display_lookup = {entry.path: entry.display_name for entry in listings}
    recent_norm: list[str] = []
    recent_seen: set[str] = set()
    for scene_id in recent_scene_ids:
        normalized = normalize_scene_path(scene_id)
        if not normalized or normalized in recent_seen:
            continue
        recent_seen.add(normalized)
        recent_norm.append(normalized)

    recent_set = set(recent_norm)

    def _row(scene_id: str) -> SceneRow:
        display_name = display_lookup.get(scene_id) or scene_id
        pack_name = _pack_name_from_scene_id(scene_id)
        return SceneRow(
            scene_id=scene_id,
            display_name=display_name,
            pack_name=pack_name,
            is_recent=scene_id in recent_set,
        )

    filtered_rows = [_row(scene_id) for scene_id, _label in filtered]
    if not recent_norm:
        return filtered_rows

    row_by_id = {row.scene_id: row for row in filtered_rows}
    pinned = [row_by_id[scene_id] for scene_id in recent_norm if scene_id in row_by_id]
    rest = [row for row in filtered_rows if row.scene_id not in recent_set]
    return pinned + rest


def iter_known_scene_paths() -> list[str]:
    """
    Return a deterministic list of known scene paths (normalized to forward slashes).

    Preference order:
    - worlds/main_world.json scenes + progression_required_scene_paths
    """
    world_path = resolve_path("worlds/main_world.json")
    if not world_path.exists():
        return []
    try:
        raw = json.loads(world_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(raw, dict):
        return []

    paths: set[str] = set()

    scenes = raw.get("scenes")
    if isinstance(scenes, dict):
        for entry in scenes.values():
            if not isinstance(entry, dict):
                continue
            p = entry.get("path")
            if isinstance(p, str) and p.strip():
                paths.add(normalize_scene_path(p.strip()))

    required = raw.get("progression_required_scene_paths")
    if isinstance(required, list):
        for p in required:
            if isinstance(p, str) and p.strip():
                paths.add(normalize_scene_path(p.strip()))

    return sorted(paths)


def validate_scene_path_exists(path: str) -> bool:
    p = str(path or "").strip()
    if not p:
        return False
    resolved = resolve_path(p)
    try:
        return Path(resolved).exists()
    except Exception:  # noqa: BLE001
        return False
