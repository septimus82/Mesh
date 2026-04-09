from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload


@dataclass(slots=True)
class PersistResult:
    ok: bool
    path: str
    wrote: bool
    errors: list[str]


def validate_scene_payload(scene_payload: dict[str, Any]) -> list[str]:
    loader = SceneLoader()
    try:
        full = loader.apply_scene_defaults(scene_payload)
    except Exception:  # noqa: BLE001  # REASON: scene validation should fall back to the raw payload when default application fails on partial authoring data
        full = scene_payload
    report = loader.validate_scene(full, strict=False)
    errors = [str(e) for e in (report.errors or [])]
    errors.sort()
    return errors


def persist_scene_payload(
    scene_path: str,
    scene_payload: dict[str, Any],
    *,
    strict_no_overwrite: bool = False,
) -> PersistResult:
    scene_path_display = normalize_scene_path(scene_path)
    resolved = resolve_path(scene_path)

    if not isinstance(scene_payload, dict):
        return PersistResult(ok=False, path=scene_path_display, wrote=False, errors=["invalid_payload"])

    errors = validate_scene_payload(scene_payload)
    if errors:
        return PersistResult(ok=False, path=scene_path_display, wrote=False, errors=errors)

    compacted = compact_scene_payload(scene_payload)

    if resolved.exists():
        try:
            existing = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  # REASON: unreadable existing scene content should be treated as unknown so persist can still decide whether to overwrite deterministically
            existing = None
        if existing == compacted:
            return PersistResult(ok=True, path=scene_path_display, wrote=False, errors=[])
        if strict_no_overwrite:
            return PersistResult(ok=False, path=scene_path_display, wrote=False, errors=["exists_different"])

    write_json_atomic(Path(resolved), compacted, indent=2, sort_keys=True, trailing_newline=True)
    return PersistResult(ok=True, path=scene_path_display, wrote=True, errors=[])
