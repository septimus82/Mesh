from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from engine.brushes import validate_brush as validate_brush_codes
from engine.paths import get_content_roots, resolve_path
from engine.persistence_io import write_json_atomic
from engine.prefabs import get_prefab_manager
from engine.stamps import validate_stamp as validate_stamp_issues

CapturePersistMode = Literal["stamp", "brush"]


@dataclass(frozen=True, slots=True)
class PersistResult:
    ok: bool
    path: str | None
    rel_path: str | None
    pack_id: str | None
    wrote: bool
    errors: list[str]


def resolve_capture_out_dir() -> Path:
    raw = os.environ.get("MESH_CAPTURE_OUT_DIR")
    if isinstance(raw, str) and raw.strip():
        p = Path(raw.strip())
        return p if p.is_absolute() else (Path.cwd() / p).resolve()
    return resolve_path("packs/core_regions").resolve()


def build_capture_out_path(mode: CapturePersistMode, asset_id: str) -> Path:
    out_dir = resolve_capture_out_dir()
    out_dir = out_dir / ("stamps" if mode == "stamp" else "brushes")
    return out_dir / f"{asset_id}.json"


def validate_stamp_payload(payload: dict[str, Any], *, rel_path: str) -> list[str]:
    manager = get_prefab_manager()
    manager.load()
    prefab_ids = set(manager.prefabs.keys())
    issues = validate_stamp_issues(payload, rel_path=str(rel_path), prefab_ids=prefab_ids)
    return [str(issue.code) for issue in issues]


def validate_brush_payload(payload: dict[str, Any]) -> list[str]:
    return list(validate_brush_codes(payload))


def _inject_capture_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    out = cast(dict[str, Any], json.loads(json.dumps(payload)))
    metadata = out.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        out["metadata"] = metadata
    metadata["source"] = "capture_mode"
    return out


def _normalize_rel_path(path: Path) -> tuple[str | None, str | None]:
    """Return (content_rel_path, pack_id) when path is under a configured content root."""
    p = path.resolve()
    for root in get_content_roots():
        try:
            rel = p.relative_to(Path(root).resolve()).as_posix()
        except Exception:
            continue
        parts = [x for x in rel.split("/") if x]
        pack_id = parts[1] if len(parts) >= 3 and parts[0] == "packs" else None
        return (rel, pack_id)
    return (None, None)


def persist_capture_payload(mode: CapturePersistMode, payload: dict[str, Any]) -> PersistResult:
    normalized = _inject_capture_metadata(payload)
    asset_id = str(normalized.get("id") or "").strip()
    if not asset_id:
        return PersistResult(ok=False, path=None, rel_path=None, pack_id=None, wrote=False, errors=["missing_id"])

    out_path = build_capture_out_path(mode, asset_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "stamp":
        errors = validate_stamp_payload(normalized, rel_path=str(out_path))
    else:
        errors = validate_brush_payload(normalized)
    if errors:
        rel, pack_id = _normalize_rel_path(out_path)
        return PersistResult(
            ok=False,
            path=str(out_path).replace("\\", "/"),
            rel_path=rel,
            pack_id=pack_id,
            wrote=False,
            errors=errors,
        )

    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        rel, pack_id = _normalize_rel_path(out_path)
        if existing == normalized:
            return PersistResult(ok=True, path=str(out_path).replace("\\", "/"), rel_path=rel, pack_id=pack_id, wrote=False, errors=[])
        return PersistResult(ok=False, path=str(out_path).replace("\\", "/"), rel_path=rel, pack_id=pack_id, wrote=False, errors=["exists_different"])

    write_json_atomic(out_path, normalized, indent=2, sort_keys=True, trailing_newline=True)
    rel, pack_id = _normalize_rel_path(out_path)
    return PersistResult(ok=True, path=str(out_path).replace("\\", "/"), rel_path=rel, pack_id=pack_id, wrote=True, errors=[])
