from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.paths import get_content_roots, resolve_path
from engine.tooling_runtime.pack_manifest import PackManifest


@dataclass(frozen=True)
class AssetEntry:
    path: str
    sha256: str
    size: int
    pack_id: str
    kind: str


def build_asset_registry(
    manifests: list[PackManifest],
    *,
    include_unused: bool = False,
) -> dict[str, Any]:
    roots = get_content_roots()
    pack_roots = [(m.root, m.id) for m in manifests]
    packs_payload = [
        {
            "id": m.id,
            "version": m.version,
            "path": _format_path(m.root, roots),
        }
        for m in manifests
    ]

    assets: dict[str, AssetEntry] = {}
    missing: list[dict[str, Any]] = []
    referenced_paths: set[str] = set()

    hash_cache: dict[str, tuple[str, int]] = {}

    for manifest in manifests:
        for source_path in _iter_json_files(manifest.root):
            if source_path.name == "pack.json":
                continue
            try:
                payload = json.loads(source_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            refs = _extract_asset_refs(payload)
            if not refs:
                continue
            for ref in refs:
                resolved = _resolve_asset_ref(manifest.root, ref)
                if resolved is None or not resolved.exists():
                    missing.append(
                        {
                            "ref": ref,
                            "expected_path": _format_path(manifest.root / ref, roots),
                            "pack_id": manifest.id,
                            "source": _format_path(source_path, roots),
                        }
                    )
                    continue
                rel_path = _format_path(resolved, roots)
                referenced_paths.add(rel_path)
                if rel_path not in assets:
                    sha256, size = _hash_file(resolved, hash_cache)
                    assets[rel_path] = AssetEntry(
                        path=rel_path,
                        sha256=sha256,
                        size=size,
                        pack_id=_pack_id_for_path(resolved, pack_roots),
                        kind=_guess_kind(rel_path),
                    )

    unused: list[dict[str, Any]] = []
    if include_unused:
        for manifest in manifests:
            assets_dir = manifest.root / "assets"
            if not assets_dir.exists():
                continue
            for file_path in sorted([p for p in assets_dir.rglob("*") if p.is_file()], key=lambda p: p.as_posix()):
                rel_path = _format_path(file_path, roots)
                if rel_path in referenced_paths:
                    continue
                unused.append({"path": rel_path, "pack_id": manifest.id})

    assets_list = sorted(assets.values(), key=lambda entry: entry.path)
    missing.sort(key=lambda entry: (entry["pack_id"], entry["source"], entry["ref"]))
    unused.sort(key=lambda entry: (entry["pack_id"], entry["path"]))

    return {
        "schema_version": 1,
        "packs": packs_payload,
        "assets": [
            {
                "path": entry.path,
                "sha256": entry.sha256,
                "size": entry.size,
                "pack_id": entry.pack_id,
                "kind": entry.kind,
            }
            for entry in assets_list
        ],
        "missing": missing,
        "unused": unused,
    }


def _iter_json_files(root: Path) -> Iterable[Path]:
    return sorted([p for p in root.rglob("*.json") if p.is_file()], key=lambda p: p.as_posix())


def _extract_asset_refs(payload: Any) -> list[str]:
    refs: list[str] = []
    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        if _looks_like_asset_path(value):
            refs.append(value)
    return refs


def _walk_values(payload: Any) -> Iterable[Any]:
    if isinstance(payload, dict):
        for value in payload.values():
            yield from _walk_values(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_values(item)
    else:
        yield payload


def _looks_like_asset_path(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if "://" in text:
        return False
    path = text.split("?")[0]
    ext = Path(path).suffix.lower()
    return ext in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".wav",
        ".ogg",
        ".mp3",
        ".json",
        ".tmx",
    }


def _resolve_asset_ref(pack_root: Path, ref: str) -> Path | None:
    raw = ref.split("?")[0].strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    pack_candidate = pack_root / candidate
    if pack_candidate.exists():
        return pack_candidate
    return resolve_path(raw)


def _format_path(path: Path, roots: list[Path]) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for root in roots:
        try:
            root_resolved = root.resolve()
        except Exception:
            root_resolved = root
        try:
            rel = resolved.relative_to(root_resolved)
        except Exception:
            continue
        return rel.as_posix()
    return path.as_posix()


def _pack_id_for_path(path: Path, pack_roots: list[tuple[Path, str]]) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for root, pack_id in sorted(pack_roots, key=lambda item: len(item[0].as_posix()), reverse=True):
        try:
            root_resolved = root.resolve()
        except Exception:
            root_resolved = root
        try:
            resolved.relative_to(root_resolved)
        except Exception:
            continue
        return pack_id
    return "unknown"


def _hash_file(path: Path, cache: dict[str, tuple[str, int]]) -> tuple[str, int]:
    key = path.as_posix()
    cached = cache.get(key)
    if cached is not None:
        return cached
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    cache[key] = (sha, size)
    return sha, size


def _guess_kind(path_str: str) -> str:
    ext = Path(path_str).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif"}:
        return "image"
    if ext in {".wav", ".ogg", ".mp3"}:
        return "audio"
    if ext in {".json", ".tmx"}:
        return "json"
    return "other"
