from __future__ import annotations

import base64
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic

_SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR4nGP4/5+hHgAHggJ/P1g1/QAAAABJRU5ErkJggg=="
)


@dataclass(frozen=True)
class MissingSpriteReference:
    asset_path: str
    source_path: str
    json_path: str


def fix_missing_assets_from_audit(
    *,
    repo_root: Path,
    audit_path: Path,
    out_path: Path | None,
    mode: str = "stub",
    placeholder_path: Path | str = "assets/placeholder.png",
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit_path = audit_path.resolve() if audit_path.is_absolute() else (repo_root / audit_path).resolve()
    if out_path is not None and not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    placeholder_path = Path(placeholder_path)
    if not placeholder_path.is_absolute():
        placeholder_path = (repo_root / placeholder_path).resolve()

    report: dict[str, Any] = {
        "schema_version": 1,
        "repo_root": repo_root.as_posix(),
        "audit_path": _rel_path(audit_path, repo_root),
        "mode": mode,
        "created_files": [],
        "skipped_existing": [],
        "skipped_unsupported": [],
        "failures": [],
    }

    data = _load_json(audit_path, report)
    if data is None:
        _write_report(out_path, report)
        return report

    missing_refs = _extract_missing_sprite_refs(data)
    if mode == "rewrite":
        _rewrite_missing_refs(
            missing_refs,
            repo_root=repo_root,
            placeholder_value=_rel_path(placeholder_path, repo_root),
            report=report,
        )
        _write_report(out_path, report)
        return report

    placeholder_bytes = None
    if placeholder_path.exists():
        try:
            placeholder_bytes = placeholder_path.read_bytes()
        except Exception as exc:  # noqa: BLE001
            report["failures"].append(
                {
                    "path": _rel_path(placeholder_path, repo_root),
                    "error": f"placeholder_read_failed: {exc}",
                }
            )
    if placeholder_bytes is None:
        placeholder_bytes = base64.b64decode(_TINY_PNG_BASE64)

    created: list[str] = []
    skipped_existing: list[str] = []
    skipped_unsupported: list[str] = []

    for ref in _unique_missing_paths(missing_refs):
        rel_target = _normalize_repo_relative_path(ref.asset_path, repo_root)
        if rel_target is None:
            report["failures"].append(
                {
                    "path": ref.asset_path,
                    "error": "path_outside_repo_root",
                }
            )
            continue
        target_path = (repo_root / rel_target).resolve()
        if target_path.exists():
            skipped_existing.append(rel_target)
            continue
        ext = target_path.suffix.lower()
        if ext not in _SUPPORTED_IMAGE_EXTS:
            skipped_unsupported.append(rel_target)
            continue
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(placeholder_bytes)
            created.append(rel_target)
        except Exception as exc:  # noqa: BLE001
            report["failures"].append(
                {
                    "path": rel_target,
                    "error": f"write_failed: {exc}",
                }
            )

    report["created_files"] = sorted(created)
    report["skipped_existing"] = sorted(skipped_existing)
    report["skipped_unsupported"] = sorted(skipped_unsupported)

    _write_report(out_path, report)
    return report


def _load_json(path: Path, report: dict[str, Any]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report["failures"].append({"path": path.as_posix(), "error": f"audit_read_failed: {exc}"})
        return None
    if not isinstance(payload, dict):
        report["failures"].append({"path": path.as_posix(), "error": "audit_not_object"})
        return None
    return payload


def _extract_missing_sprite_refs(payload: dict[str, Any]) -> list[MissingSpriteReference]:
    refs: list[MissingSpriteReference] = []
    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        return refs
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") != "missing_file":
            continue
        json_path = entry.get("json_path")
        if not isinstance(json_path, str) or not json_path.endswith("/sprite"):
            continue
        asset = entry.get("asset")
        source_path = entry.get("path")
        if not isinstance(asset, str) or not isinstance(source_path, str):
            continue
        refs.append(MissingSpriteReference(asset_path=asset, source_path=source_path, json_path=json_path))
    return refs


def _unique_missing_paths(refs: list[MissingSpriteReference]) -> list[MissingSpriteReference]:
    seen: set[str] = set()
    unique: list[MissingSpriteReference] = []
    for ref in refs:
        key = ref.asset_path.replace("\\", "/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _normalize_repo_relative_path(path_text: str, repo_root: Path) -> str | None:
    raw = Path(path_text)
    if raw.is_absolute():
        try:
            rel = raw.resolve().relative_to(repo_root.resolve())
            return rel.as_posix()
        except Exception:
            return None
    cleaned = path_text.replace("\\", "/").lstrip("/")
    return cleaned


def _rewrite_missing_refs(
    refs: list[MissingSpriteReference],
    *,
    repo_root: Path,
    placeholder_value: str,
    report: dict[str, Any],
) -> None:
    grouped: dict[Path, list[MissingSpriteReference]] = {}
    for ref in refs:
        source = Path(ref.source_path)
        if not source.is_absolute():
            source = repo_root / source
        grouped.setdefault(source.resolve(), []).append(ref)

    rewritten: list[str] = []
    for path, items in sorted(grouped.items(), key=lambda kv: kv[0].as_posix()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            report["failures"].append({"path": _rel_path(path, repo_root), "error": f"read_failed: {exc}"})
            continue
        changed = False
        for ref in items:
            if _set_json_pointer(payload, ref.json_path, placeholder_value):
                changed = True
            else:
                report["failures"].append(
                    {
                        "path": _rel_path(path, repo_root),
                        "error": f"json_path_not_found: {ref.json_path}",
                    }
                )
        if changed:
            try:
                write_json_atomic(path, payload, indent=2, sort_keys=True, trailing_newline=True)
                rewritten.append(_rel_path(path, repo_root))
            except Exception as exc:  # noqa: BLE001
                report["failures"].append({"path": _rel_path(path, repo_root), "error": f"write_failed: {exc}"})
    report["rewritten_files"] = sorted(set(rewritten))


def _set_json_pointer(payload: Any, pointer: str, value: Any) -> bool:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False
    parts = [_unescape_pointer(p) for p in pointer.split("/")[1:]]
    current = payload
    for idx, part in enumerate(parts):
        is_last = idx == len(parts) - 1
        if isinstance(current, list):
            if not part.isdigit():
                return False
            offset = int(part)
            if offset < 0 or offset >= len(current):
                return False
            if is_last:
                current[offset] = value
                return True
            current = current[offset]
            continue
        if isinstance(current, dict):
            if part not in current:
                return False
            if is_last:
                current[part] = value
                return True
            current = current[part]
            continue
        return False
    return False


def _unescape_pointer(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


def _rel_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _write_report(out_path: Path | None, report: dict[str, Any]) -> None:
    if out_path is None:
        return
    out_path = out_path.resolve() if out_path.is_absolute() else out_path
    try:
        write_json_atomic(out_path, report, indent=2, sort_keys=True, trailing_newline=True)
    except Exception as exc:  # noqa: BLE001
        report.setdefault("failures", []).append({"path": out_path.as_posix(), "error": f"report_write_failed: {exc}"})
