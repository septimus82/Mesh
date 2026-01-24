"""Deterministically add missing entity IDs (and TriggerZone.zone_id) to scene JSON.

This is a mechanical content rewrite intended to make `--schema-strict` validation pass
without changing gameplay behavior.

Rules:
- Only adds/repairs missing/blank fields: entity.id and TriggerZone.zone_id.
- IDs are deterministic based on (scene filename slug, kind/mesh, x/y/w/h).
- Collisions within a scene are resolved deterministically with _2, _3, ... suffixes.
- Entity list ordering is preserved.
- Writes via atomic JSON writer with sorted keys and trailing newline.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.persistence_io import read_json, write_json_atomic


_SAFE_CHARS_RE = re.compile(r"[^a-zA-Z0-9_]+")
_COLLAPSE_UNDERSCORES_RE = re.compile(r"_+")


def _slugify(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = raw.replace("\\", "/")
    raw = _SAFE_CHARS_RE.sub("_", raw)
    raw = _COLLAPSE_UNDERSCORES_RE.sub("_", raw)
    raw = raw.strip("_")
    return raw or "unnamed"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _num_token(value: object | None) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "0"

    # Prefer a compact, stable representation.
    # - ints remain ints
    # - floats like 240.0 become "240"
    # - floats like 20.5 become "20.5"
    if isinstance(value, int):
        text = str(value)
    else:
        text = format(float(value), "g")

    # Normalize to safe chars.
    # Keep sign information and decimals:
    # - "-" becomes leading "m"
    # - "." becomes "p"
    if text.startswith("-"):
        text = "m" + text[1:]
    text = text.replace(".", "p")
    text = re.sub(r"[^0-9a-zA-Z_]+", "_", text)
    text = _COLLAPSE_UNDERSCORES_RE.sub("_", text)
    return text.strip("_") or "0"


def _non_empty_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entity_kind_or_mesh(entity: dict[str, Any]) -> str:
    # Prefer semantic identity over tag-like fields.
    return (
        _non_empty_str(entity.get("name"))
        or _non_empty_str(entity.get("mesh_name"))
        or _non_empty_str(entity.get("type"))
        or _non_empty_str(entity.get("tag"))
        or "entity"
    )


def _entity_wh(entity: dict[str, Any]) -> tuple[object | None, object | None]:
    # Support a few common conventions.
    for key_w, key_h in (("w", "h"), ("width", "height")):
        if key_w in entity or key_h in entity:
            return entity.get(key_w), entity.get(key_h)

    hitbox = entity.get("hitbox")
    if isinstance(hitbox, dict):
        return hitbox.get("w") or hitbox.get("width"), hitbox.get("h") or hitbox.get("height")

    return None, None


def generate_entity_id(
    *,
    scene_slug: str,
    entity: dict[str, Any],
    used_ids: set[str],
) -> str:
    """Generate a deterministic unique ID for an entity within a scene."""

    kind = _slugify(_entity_kind_or_mesh(entity))
    x = _num_token(entity.get("x"))
    y = _num_token(entity.get("y"))
    w_raw, h_raw = _entity_wh(entity)
    w = _num_token(w_raw)
    h = _num_token(h_raw)

    base = "_".join([
        _slugify(scene_slug),
        kind,
        x,
        y,
        w,
        h,
    ])
    base = _slugify(base)

    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1

    return candidate


def _has_trigger_zone(entity: dict[str, Any]) -> bool:
    behaviours = entity.get("behaviours")
    if isinstance(behaviours, list):
        for item in behaviours:
            if item == "TriggerZone":
                return True
            if isinstance(item, dict) and _non_empty_str(item.get("type")) == "TriggerZone":
                return True

    bcfg = entity.get("behaviour_config")
    if isinstance(bcfg, dict) and isinstance(bcfg.get("TriggerZone"), dict):
        return True

    return False


def _ensure_trigger_zone_zone_id(entity: dict[str, Any]) -> bool:
    """Ensure behaviour_config.TriggerZone.zone_id exists when TriggerZone is present.

    Returns True if modified.
    """

    if not _has_trigger_zone(entity):
        return False

    bcfg = entity.get("behaviour_config")
    if not isinstance(bcfg, dict):
        return False

    tz_cfg = bcfg.get("TriggerZone")
    if not isinstance(tz_cfg, dict):
        return False

    if _non_empty_str(tz_cfg.get("zone_id")) is not None:
        return False

    ent_id = _non_empty_str(entity.get("id"))
    if ent_id is None:
        return False

    tz_cfg["zone_id"] = ent_id
    return True


@dataclass(frozen=True)
class FixCounts:
    scenes_touched: int = 0
    ids_added: int = 0
    zone_ids_added: int = 0

    def __add__(self, other: "FixCounts") -> "FixCounts":
        return FixCounts(
            scenes_touched=self.scenes_touched + other.scenes_touched,
            ids_added=self.ids_added + other.ids_added,
            zone_ids_added=self.zone_ids_added + other.zone_ids_added,
        )


def fix_scene_payload(path: Path, payload: Any) -> tuple[Any, FixCounts, bool]:
    """Return (updated_payload, counts, changed)."""

    if not isinstance(payload, dict):
        return payload, FixCounts(), False

    entities = payload.get("entities")
    if not isinstance(entities, list):
        return payload, FixCounts(), False

    scene_slug = _slugify(path.stem)

    used_ids: set[str] = set()
    for entity in entities:
        if isinstance(entity, dict):
            existing = _non_empty_str(entity.get("id"))
            if existing is not None:
                used_ids.add(existing)

    ids_added = 0
    zone_ids_added = 0
    changed = False

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        entity_id = _non_empty_str(entity.get("id"))
        if entity_id is None:
            new_id = generate_entity_id(scene_slug=scene_slug, entity=entity, used_ids=used_ids)
            entity["id"] = new_id
            used_ids.add(new_id)
            ids_added += 1
            changed = True

        if _ensure_trigger_zone_zone_id(entity):
            zone_ids_added += 1
            changed = True

    counts = FixCounts(
        scenes_touched=1 if changed else 0,
        ids_added=ids_added,
        zone_ids_added=zone_ids_added,
    )
    return payload, counts, changed


def _iter_scene_paths(workspace_root: Path, patterns: Iterable[str]) -> list[Path]:
    # Deterministic ordering (by POSIX string) and de-dup.
    paths: dict[str, Path] = {}

    for raw in patterns:
        pattern = (raw or "").strip()
        if not pattern:
            continue

        explicit = Path(pattern)
        if explicit.is_absolute() and explicit.exists() and explicit.is_file():
            paths[explicit.as_posix()] = explicit
            continue

        explicit_rel = (workspace_root / explicit).resolve()
        if explicit_rel.exists() and explicit_rel.is_file():
            paths[explicit_rel.as_posix()] = explicit_rel
            continue

        for match in workspace_root.glob(pattern):
            if match.is_file() and match.suffix.lower() == ".json":
                paths[match.resolve().as_posix()] = match.resolve()

    return [paths[k] for k in sorted(paths.keys())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministically add missing entity IDs in scene JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change but do not write files",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Glob(s) or file path(s) to scenes. Default targets shipped scenes.",
    )
    args = parser.parse_args(argv)

    workspace_root = Path(".").resolve()

    patterns: list[str]
    if args.paths is None or len(args.paths) == 0:
        patterns = ["scenes/*.json", "packs/**/scenes/*.json"]
    else:
        patterns = list(args.paths)

    scene_paths = _iter_scene_paths(workspace_root, patterns)
    if not scene_paths:
        print(f"[Mesh][SchemaFixIds] No scene files matched patterns: {patterns}")
        return 2

    total = FixCounts()

    for path in scene_paths:
        payload = read_json(path)
        updated, counts, changed = fix_scene_payload(path, payload)
        total = total + counts

        if changed:
            print(
                f"[Mesh][SchemaFixIds] {'DRY-RUN ' if args.dry_run else ''}update {path}: "
                f"+{counts.ids_added} ids, +{counts.zone_ids_added} zone_ids"
            )
            if not args.dry_run:
                write_json_atomic(path, updated, indent=2, sort_keys=True, trailing_newline=True)

    print(
        f"[Mesh][SchemaFixIds] Done. Scenes touched={total.scenes_touched}, "
        f"ids_added={total.ids_added}, zone_ids_added={total.zone_ids_added}"
    )

    return 0
