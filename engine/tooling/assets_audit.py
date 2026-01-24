from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.behaviours.particle_emitter import validate_particle_emitter_config
from engine.fx_presets import FxPresetRegistry, collect_presets_and_errors
from engine.paths import reset_path_caches, resolve_path, set_content_roots
from engine.prefabs import get_prefab_manager
from engine.tooling.content_contract import (
    find_particle_emitters,
    _build_prefab_index,
    _resolve_prefab_ref,
)
from engine.tooling_runtime.pack_manifest import load_all_manifests, resolve_pack_order
from engine.particles_core import normalize_rect


@dataclass(frozen=True)
class AssetAuditError:
    kind: str
    path: str
    json_path: str
    asset: str
    message: str


@dataclass(frozen=True)
class AssetReference:
    referer_pack: str | None
    source_path: str
    json_path: str
    asset_path: str
    absolute_path: Path


def run_asset_audit(
    *,
    repo_root: Path,
    out_path: Path | None = None,
    pack_id: str | None = None,
    strict: bool = False,
    with_orphans: bool = False,
    with_duplicates: bool = False,
    with_ownership: bool = True,
    warn_duplicates: bool = True,
    fail_missing: bool = True,
    fail_orphans: bool = False,
    fail_duplicates: bool = False,
    write_report: bool = True,
) -> tuple[int, dict[str, Any]]:
    resolved_root = repo_root.resolve()
    set_content_roots([resolved_root])
    try:
        report = _audit_assets(
            repo_root=resolved_root,
            pack_id=pack_id,
            strict=strict,
            with_orphans=with_orphans,
            with_duplicates=with_duplicates,
            with_ownership=with_ownership,
            warn_duplicates=warn_duplicates,
            fail_missing=fail_missing,
            fail_orphans=fail_orphans,
            fail_duplicates=fail_duplicates,
        )
        if write_report and out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            from engine.persistence_io import write_json_atomic

            write_json_atomic(out_path, report, indent=2, sort_keys=True, trailing_newline=True)
        if report["summary"]["error_count"]:
            exit_code = 2
        elif report["summary"]["warning_count"] and strict:
            exit_code = 1
        else:
            exit_code = 0
        return exit_code, report
    finally:
        reset_path_caches()


def _audit_assets(
    *,
    repo_root: Path,
    pack_id: str | None,
    strict: bool,
    with_orphans: bool,
    with_duplicates: bool,
    with_ownership: bool,
    warn_duplicates: bool,
    fail_missing: bool,
    fail_orphans: bool,
    fail_duplicates: bool,
) -> dict[str, Any]:
    manifests, _manifest_errors = load_all_manifests(pack_id=pack_id)
    pack_order, _dep_errors = resolve_pack_order(manifests)
    pack_roots = [manifest.root for manifest in pack_order]
    if pack_roots:
        set_content_roots(pack_roots)

    fx_registry = FxPresetRegistry.from_pack_roots(pack_roots, pack_order)
    prefab_index, prefab_index_errors = _build_prefab_index(pack_order, repo_root)
    prefab_manager = get_prefab_manager()
    prefab_manager.load(force=True)

    errors: list[AssetAuditError] = []
    warnings: list[AssetAuditError] = []
    references: list[AssetReference] = []
    files_scanned = 0

    for err in prefab_index_errors:
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=err.file_path,
                json_path=err.json_path,
                asset="",
                message=err.message,
            )
        )

    files_to_scan: dict[str, Path] = {}
    for root in pack_roots:
        files_to_scan.update(_collect_dir_json(root / "scenes", repo_root))
        files_to_scan.update(_collect_dir_json(root / "worlds", repo_root))
        prefabs_path = root / "data" / "prefabs.json"
        if prefabs_path.exists():
            files_to_scan[_display_path(prefabs_path, repo_root)] = prefabs_path
        presets_path = root / "fx" / "presets.json"
        if presets_path.exists():
            files_to_scan[_display_path(presets_path, repo_root)] = presets_path

    base_prefabs = repo_root / "assets" / "prefabs.json"
    if base_prefabs.exists():
        files_to_scan[_display_path(base_prefabs, repo_root)] = base_prefabs

    for rel_path in sorted(files_to_scan.keys()):
        path = files_to_scan[rel_path]
        if path.name == "presets.json":
            files_scanned += 1
            _scan_fx_presets(
                path,
                repo_root=repo_root,
                fx_registry=fx_registry,
                references=references,
                errors=errors,
            )
            continue
        if path.name == "prefabs.json":
            files_scanned += 1
            continue
        files_scanned += 1
        _scan_scene_or_world(
            path,
            repo_root=repo_root,
            fx_registry=fx_registry,
            pack_order=pack_order,
            prefab_index=prefab_index,
            prefab_manager=prefab_manager,
            references=references,
            errors=errors,
        )

    _scan_prefabs(
        repo_root=repo_root,
        prefab_manager=prefab_manager,
        fx_registry=fx_registry,
        references=references,
        errors=errors,
    )

    pack_deps, pack_meta = _build_pack_dependency_map(pack_order)
    pack_audit_config = _load_pack_audit_config(pack_order, repo_root)
    if with_ownership:
        _enforce_pack_ownership(
            references=references,
            pack_deps=pack_deps,
            pack_meta=pack_meta,
            pack_audit_config=pack_audit_config,
            repo_root=repo_root,
            errors=errors,
        )

    orphan_entries: list[dict[str, Any]] = []
    asset_files: list[Path] = []
    if with_orphans or with_duplicates:
        asset_files = _collect_asset_files(pack_order, repo_root)
    if with_orphans:
        referenced_paths = {ref.absolute_path for ref in references}
        orphan_entries = _detect_orphans(
            asset_files,
            referenced_paths=referenced_paths,
            pack_audit_config=pack_audit_config,
            repo_root=repo_root,
        )

    duplicate_entries: list[dict[str, Any]] = []
    duplicate_warnings: list[AssetAuditError] = []
    if with_duplicates:
        duplicate_entries, duplicate_warnings = _detect_duplicates(
            asset_files,
            referenced_paths={ref.absolute_path for ref in references},
            repo_root=repo_root,
            warn_duplicates=warn_duplicates,
        )
        if not fail_duplicates:
            warnings.extend(duplicate_warnings)

    if fail_orphans and orphan_entries:
        for orphan in orphan_entries:
            orphan_path = str(orphan.get("path") or "")
            errors.append(
                AssetAuditError(
                    kind="orphaned_asset",
                    path=orphan_path,
                    json_path="/",
                    asset="",
                    message="orphaned asset detected",
                )
            )

    if fail_duplicates and duplicate_entries:
        for entry in duplicate_entries:
            dup_paths = entry.get("paths") if isinstance(entry, dict) else None
            first_path = dup_paths[0] if isinstance(dup_paths, list) and dup_paths else ""
            asset = ""
            if isinstance(entry, dict):
                asset = str(entry.get("hash") or entry.get("basename") or "")
            errors.append(
                AssetAuditError(
                    kind=str(entry.get("kind") if isinstance(entry, dict) else "duplicate"),
                    path=first_path,
                    json_path="/",
                    asset=asset,
                    message="duplicate asset detected",
                )
            )

    missing_file_entries = [e for e in errors if e.kind == "missing_file"]
    missing_files = len(missing_file_entries)
    if not fail_missing and missing_file_entries:
        for error_entry in list(errors):
            if error_entry.kind == "missing_file":
                errors.remove(error_entry)
                warnings.append(error_entry)

    errors = sorted(errors, key=lambda e: (e.path, e.json_path, e.asset, e.kind))
    warnings = sorted(warnings, key=lambda e: (e.path, e.json_path, e.asset, e.kind))

    missing_files = missing_files
    invalid_values = sum(1 for e in errors if e.kind in {"invalid_value", "bad_rect"})
    report: dict[str, Any] = {
        "schema_version": 1,
        "repo_root": repo_root.as_posix(),
        "packs_scanned": len(pack_roots),
        "files_scanned": files_scanned,
        "errors": [e.__dict__ for e in errors],
        "warnings": [w.__dict__ for w in warnings],
        "orphans": orphan_entries,
        "duplicates": duplicate_entries,
        "summary": {
            "ok": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "missing_files": missing_files,
            "invalid_values": invalid_values,
            "cross_pack_refs": sum(1 for e in errors if e.kind == "cross_pack_reference"),
            "orphan_count": len(orphan_entries),
            "duplicate_groups": len(duplicate_entries),
        },
    }
    if strict and (errors or warnings):
        report["summary"]["ok"] = False
    return report


def _collect_dir_json(root: Path, repo_root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.exists():
        return files
    for path in root.rglob("*.json"):
        if path.is_file():
            files[_display_path(path, repo_root)] = path
    return files


def _scan_scene_or_world(
    path: Path,
    *,
    repo_root: Path,
    fx_registry: FxPresetRegistry,
    pack_order: list[Any],
    prefab_index: Any,
    prefab_manager: Any,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    payload = _load_json(path, repo_root, errors)
    if payload is None:
        return
    context_pack_id = _infer_pack_id(path, repo_root)

    entities = payload.get("entities") if isinstance(payload, dict) else None
    if isinstance(entities, list):
        for idx, entity in enumerate(entities):
            if not isinstance(entity, dict):
                continue
            entity_path = f"/entities/{idx}"
            prefab_key = _prefab_key(entity)
            prefab_ref = entity.get(prefab_key) if prefab_key else None
            resolved_entity = entity

            if prefab_key:
                prefab_ref_str = _coerce_str(prefab_ref)
                if prefab_ref_str is None:
                    errors.append(
                        AssetAuditError(
                            kind="invalid_value",
                            path=_display_path(path, repo_root),
                            json_path=f"{entity_path}/{prefab_key}",
                            asset="",
                            message="prefab reference must be a non-empty string",
                        )
                    )
                else:
                    _resolve_prefab_reference(
                        prefab_ref_str,
                        context_pack_id=context_pack_id,
                        pack_order=pack_order,
                        prefab_index=prefab_index,
                        repo_root=repo_root,
                        file_path=path,
                        json_path=f"{entity_path}/{prefab_key}",
                        errors=errors,
                    )
                    resolved_entity = _resolve_entity_with_prefab(prefab_manager, entity, prefab_ref_str)

            _validate_entity_sprite(
                entity,
                resolved_entity,
                file_path=path,
                repo_root=repo_root,
                json_path=entity_path,
                prefab_json_key=prefab_key,
                references=references,
                errors=errors,
            )

            _validate_emitters_for_entity(
                resolved_entity,
                entity_prefix=entity_path,
                context_pack_id=context_pack_id,
                file_path=path,
                repo_root=repo_root,
                fx_registry=fx_registry,
                references=references,
                errors=errors,
            )
    else:
        _validate_emitters_for_entity(
            payload,
            entity_prefix="",
            context_pack_id=context_pack_id,
            file_path=path,
            repo_root=repo_root,
            fx_registry=fx_registry,
            references=references,
            errors=errors,
        )

    tilemap = payload.get("tilemap") if isinstance(payload, dict) else None
    if isinstance(tilemap, dict):
        _scan_tilemap_reference(
            tilemap,
            scene_path=path,
            repo_root=repo_root,
            references=references,
            errors=errors,
        )


def _scan_prefabs(
    *,
    repo_root: Path,
    prefab_manager: Any,
    fx_registry: FxPresetRegistry,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    sources = prefab_manager.prefab_sources
    for prefab_id in sorted(prefab_manager.prefabs.keys()):
        resolved = prefab_manager.get_prefab(prefab_id)
        if not isinstance(resolved, dict):
            continue
        entity = resolved.get("entity")
        if not isinstance(entity, dict):
            continue
        source_path = sources.get(prefab_id) or "assets/prefabs.json"
        file_path = repo_root / source_path if not Path(source_path).is_absolute() else Path(source_path)
        json_prefix = f"/prefabs/{prefab_id}/entity"
        _validate_entity_sprite(
            entity,
            entity,
            file_path=file_path,
            repo_root=repo_root,
            json_path=json_prefix,
            prefab_json_key=None,
            force_resolved=True,
            references=references,
            errors=errors,
        )
        _validate_emitters_for_entity(
            entity,
            entity_prefix=json_prefix,
            context_pack_id=_infer_pack_id(file_path, repo_root),
            file_path=file_path,
            repo_root=repo_root,
            fx_registry=fx_registry,
            references=references,
            errors=errors,
        )


def _scan_fx_presets(
    path: Path,
    *,
    repo_root: Path,
    fx_registry: FxPresetRegistry,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    pack_id = _infer_pack_id(path, repo_root)
    records, load_errors = collect_presets_and_errors([path.parent.parent], None)
    for err in load_errors:
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(path, repo_root),
                json_path="/",
                asset="",
                message=err.message,
            )
        )
    for record in records:
        if pack_id is not None and record.pack_id != pack_id:
            continue
        json_base = f"/presets/{record.preset_name}"
        _validate_emitter_config(
            record.preset_dict,
            json_path=json_base,
            file_path=record.file_path,
            repo_root=repo_root,
            fx_registry=fx_registry,
            context_pack_id=record.pack_id,
            allow_preset=False,
            references=references,
            errors=errors,
        )


def _scan_tilemap_reference(
    tilemap: dict[str, Any],
    *,
    scene_path: Path,
    repo_root: Path,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    raw_path = tilemap.get("resolved_path") or tilemap.get("path")
    json_path = "/tilemap/resolved_path" if tilemap.get("resolved_path") else "/tilemap/path"
    path_text = _coerce_str(raw_path)
    if path_text is None:
        return
    scene_dir = scene_path.parent
    candidates = _tilemap_candidates(path_text, scene_dir)
    tilemap_path = next((p for p in candidates if p.exists()), candidates[-1])
    if not tilemap_path.exists():
        errors.append(
            AssetAuditError(
                kind="missing_file",
                path=_display_path(scene_path, repo_root),
                json_path=json_path,
                asset=path_text,
                message=f"tilemap '{path_text}' not found",
            )
        )
        return
    _record_reference(
        references,
        referer_pack=_infer_pack_id(scene_path, repo_root),
        source_path=_display_path(scene_path, repo_root),
        json_path=json_path,
        asset_path=path_text,
        absolute_path=tilemap_path,
        repo_root=repo_root,
    )
    payload = _load_json(tilemap_path, repo_root, errors)
    if payload is None:
        return
    tilesets = payload.get("tilesets") if isinstance(payload, dict) else None
    if not isinstance(tilesets, list):
        return
    for idx, entry in enumerate(tilesets):
        if not isinstance(entry, dict):
            continue
        source = _coerce_str(entry.get("source"))
        if source is not None:
            tileset_path = (tilemap_path.parent / source).resolve()
            if not tileset_path.exists():
                errors.append(
                    AssetAuditError(
                        kind="unknown_tileset",
                        path=_display_path(tilemap_path, repo_root),
                        json_path=f"/tilesets/{idx}/source",
                        asset=source,
                        message=f"tileset '{source}' not found",
                    )
                )
                continue
            _record_reference(
                references,
                referer_pack=_infer_pack_id(tilemap_path, repo_root),
                source_path=_display_path(tilemap_path, repo_root),
                json_path=f"/tilesets/{idx}/source",
                asset_path=source,
                absolute_path=tileset_path,
                repo_root=repo_root,
            )
            _scan_tileset_file(
                tileset_path,
                tilemap_path=tilemap_path,
                json_path=f"/tilesets/{idx}/source",
                repo_root=repo_root,
                references=references,
                errors=errors,
            )
            continue
        image = _coerce_str(entry.get("image"))
        if image is None:
            continue
        resolved = (tilemap_path.parent / image).resolve()
        _record_reference(
            references,
            referer_pack=_infer_pack_id(tilemap_path, repo_root),
            source_path=_display_path(tilemap_path, repo_root),
            json_path=f"/tilesets/{idx}/image",
            asset_path=image,
            absolute_path=resolved,
            repo_root=repo_root,
        )
        if not resolved.exists():
            errors.append(
                AssetAuditError(
                    kind="missing_file",
                    path=_display_path(tilemap_path, repo_root),
                    json_path=f"/tilesets/{idx}/image",
                    asset=image,
                    message=f"tileset image '{image}' not found",
                )
            )


def _scan_tileset_file(
    tileset_path: Path,
    *,
    tilemap_path: Path,
    json_path: str,
    repo_root: Path,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    suffix = tileset_path.suffix.lower()
    if suffix == ".tsx":
        try:
            tree = ET.parse(tileset_path)
            root = tree.getroot()
        except Exception as exc:  # noqa: BLE001
            errors.append(
                AssetAuditError(
                    kind="invalid_value",
                    path=_display_path(tilemap_path, repo_root),
                    json_path=json_path,
                    asset=tileset_path.as_posix(),
                    message=f"failed to parse tileset: {exc}",
                )
            )
            return
        image_node = root.find("image")
        image_source = image_node.get("source") if image_node is not None else None
        if not isinstance(image_source, str) or not image_source.strip():
            errors.append(
                AssetAuditError(
                    kind="invalid_value",
                    path=_display_path(tilemap_path, repo_root),
                    json_path=json_path,
                    asset=tileset_path.as_posix(),
                    message="tileset image source missing",
                )
            )
            return
        resolved = (tileset_path.parent / image_source).resolve()
        _record_reference(
            references,
            referer_pack=_infer_pack_id(tilemap_path, repo_root),
            source_path=_display_path(tilemap_path, repo_root),
            json_path=json_path,
            asset_path=image_source,
            absolute_path=resolved,
            repo_root=repo_root,
        )
        if not resolved.exists():
            errors.append(
                AssetAuditError(
                    kind="missing_file",
                    path=_display_path(tilemap_path, repo_root),
                    json_path=json_path,
                    asset=image_source,
                    message=f"tileset image '{image_source}' not found",
                )
            )
        return
    payload = _load_json(tileset_path, repo_root, errors)
    if payload is None:
        return
    image_path = _coerce_str(payload.get("image")) if isinstance(payload, dict) else None
    if image_path is None:
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(tilemap_path, repo_root),
                json_path=json_path,
                asset=tileset_path.as_posix(),
                message="tileset image missing",
            )
        )
        return
    resolved = (tileset_path.parent / image_path).resolve()
    _record_reference(
        references,
        referer_pack=_infer_pack_id(tilemap_path, repo_root),
        source_path=_display_path(tilemap_path, repo_root),
        json_path=json_path,
        asset_path=image_path,
        absolute_path=resolved,
        repo_root=repo_root,
    )
    if not resolved.exists():
        errors.append(
            AssetAuditError(
                kind="missing_file",
                path=_display_path(tilemap_path, repo_root),
                json_path=json_path,
                asset=image_path,
                message=f"tileset image '{image_path}' not found",
            )
        )


def _validate_entity_sprite(
    entity: dict[str, Any],
    resolved: dict[str, Any],
    *,
    file_path: Path,
    repo_root: Path,
    json_path: str,
    prefab_json_key: str | None,
    force_resolved: bool = False,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    if "sprite" in entity:
        raw = entity.get("sprite")
        _validate_sprite_value(
            raw,
            file_path=file_path,
            repo_root=repo_root,
            json_path=f"{json_path}/sprite",
            references=references,
            errors=errors,
        )
        return
    sprite = resolved.get("sprite")
    if sprite is None:
        return
    if prefab_json_key is None and not force_resolved:
        return
    if prefab_json_key is not None:
        target_path = f"{json_path}/{prefab_json_key}"
    else:
        target_path = f"{json_path}/sprite"
    _validate_sprite_value(
        sprite,
        file_path=file_path,
        repo_root=repo_root,
        json_path=target_path,
        references=references,
        errors=errors,
    )


def _validate_sprite_value(
    value: Any,
    *,
    file_path: Path,
    repo_root: Path,
    json_path: str,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    if value is None:
        return
    sprite_path = _coerce_str(value)
    if sprite_path is None:
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=json_path,
                asset="",
                message="sprite must be a non-empty string",
            )
        )
        return
    resolved = _resolve_asset_path(sprite_path, repo_root)
    _record_reference(
        references,
        referer_pack=_infer_pack_id(file_path, repo_root),
        source_path=_display_path(file_path, repo_root),
        json_path=json_path,
        asset_path=sprite_path,
        absolute_path=resolved,
        repo_root=repo_root,
    )
    if not resolved.exists():
        errors.append(
            AssetAuditError(
                kind="missing_file",
                path=_display_path(file_path, repo_root),
                json_path=json_path,
                asset=sprite_path,
                message=f"sprite '{sprite_path}' not found",
            )
        )


def _validate_emitters_for_entity(
    payload: Any,
    *,
    entity_prefix: str,
    context_pack_id: str | None,
    file_path: Path,
    repo_root: Path,
    fx_registry: FxPresetRegistry,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    records = find_particle_emitters(payload)
    for record in records:
        merged_path = f"{entity_prefix}{record.json_path}" if entity_prefix else record.json_path
        _validate_emitter_config(
            record.cfg,
            json_path=merged_path,
            file_path=file_path,
            repo_root=repo_root,
            fx_registry=fx_registry,
            context_pack_id=context_pack_id,
            allow_preset=True,
            references=references,
            errors=errors,
        )


def _validate_emitter_config(
    cfg: Any,
    *,
    json_path: str,
    file_path: Path,
    repo_root: Path,
    fx_registry: FxPresetRegistry,
    context_pack_id: str | None,
    allow_preset: bool,
    references: list[AssetReference],
    errors: list[AssetAuditError],
) -> None:
    if not isinstance(cfg, dict):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=json_path,
                asset="",
                message="ParticleEmitter config must be an object",
            )
        )
        return
    inline = dict(cfg)
    merged = dict(inline)
    if allow_preset:
        preset_name = _coerce_str(inline.get("preset"))
        if preset_name is not None:
            try:
                preset_cfg = fx_registry.resolve(preset_name, context_pack_id=context_pack_id)
            except ValueError as exc:
                errors.append(
                    AssetAuditError(
                        kind="unknown_preset",
                        path=_display_path(file_path, repo_root),
                        json_path=f"{json_path}/preset",
                        asset=preset_name,
                        message=str(exc),
                    )
                )
                preset_cfg = {}
            merged = dict(preset_cfg)
            for key, value in inline.items():
                if key == "preset":
                    continue
                merged[key] = value

    for issue in validate_particle_emitter_config(merged, allow_preset=False):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=json_path,
                asset="",
                message=issue,
            )
        )

    _validate_emitter_rect_inputs(
        merged,
        file_path=file_path,
        repo_root=repo_root,
        json_path=json_path,
        errors=errors,
    )

    sprite_path = _coerce_str(merged.get("sprite")) or _coerce_str(merged.get("sprite_path"))
    if sprite_path is not None:
        resolved = _resolve_asset_path(sprite_path, repo_root)
        _record_reference(
            references,
            referer_pack=context_pack_id or _infer_pack_id(file_path, repo_root),
            source_path=_display_path(file_path, repo_root),
            json_path=f"{json_path}/sprite",
            asset_path=sprite_path,
            absolute_path=resolved,
            repo_root=repo_root,
        )
        if not resolved.exists():
            errors.append(
                AssetAuditError(
                    kind="missing_file",
                    path=_display_path(file_path, repo_root),
                    json_path=f"{json_path}/sprite",
                    asset=sprite_path,
                    message=f"sprite '{sprite_path}' not found",
                )
            )


def _validate_emitter_rect_inputs(
    config: dict[str, Any],
    *,
    file_path: Path,
    repo_root: Path,
    json_path: str,
    errors: list[AssetAuditError],
) -> None:
    if "rect" in config:
        rect = normalize_rect(config.get("rect"))
        if rect is None:
            errors.append(
                AssetAuditError(
                    kind="bad_rect",
                    path=_display_path(file_path, repo_root),
                    json_path=f"{json_path}/rect",
                    asset="",
                    message="rect must be [x,y,w,h] with non-negative x/y and positive w/h",
                )
            )
    if "frame" in config and not _is_non_negative_int(config.get("frame")):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=f"{json_path}/frame",
                asset="",
                message="frame must be a non-negative integer",
            )
        )
    if "frame_xy" in config and not _is_non_negative_pair(config.get("frame_xy")):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=f"{json_path}/frame_xy",
                asset="",
                message="frame_xy must be [col,row] with non-negative integers",
            )
        )
    if "frame_size" in config and not _is_positive_pair(config.get("frame_size")):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(file_path, repo_root),
                json_path=f"{json_path}/frame_size",
                asset="",
                message="frame_size must be [w,h] with positive integers",
            )
        )


def _resolve_prefab_reference(
    prefab_ref: str,
    *,
    context_pack_id: str | None,
    pack_order: list[Any],
    prefab_index: Any,
    repo_root: Path,
    file_path: Path,
    json_path: str,
    errors: list[AssetAuditError],
) -> None:
    _pack_id, err = _resolve_prefab_ref(
        prefab_ref,
        context_pack_id=context_pack_id,
        pack_order=pack_order,
        prefab_index=prefab_index,
    )
    if err is not None:
        errors.append(
            AssetAuditError(
                kind="unknown_prefab",
                path=_display_path(file_path, repo_root),
                json_path=json_path,
                asset=prefab_ref,
                message=err,
            )
        )


def _resolve_entity_with_prefab(prefab_manager: Any, entity: dict[str, Any], prefab_ref: str) -> dict[str, Any]:
    raw = _coerce_str(prefab_ref)
    if raw is None:
        return entity
    if ":" in raw:
        _, prefab_id = raw.split(":", 1)
        prefab_id = prefab_id.strip()
    else:
        prefab_id = raw
    resolved_entity = dict(entity)
    resolved_entity["prefab_id"] = prefab_id
    resolved = prefab_manager.resolve(resolved_entity)
    return resolved if isinstance(resolved, dict) else resolved_entity


def _load_json(path: Path, repo_root: Path, errors: list[AssetAuditError]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(path, repo_root),
                json_path="/",
                asset="",
                message=f"failed to parse JSON: {exc}",
            )
        )
        return None
    if not isinstance(payload, dict):
        errors.append(
            AssetAuditError(
                kind="invalid_value",
                path=_display_path(path, repo_root),
                json_path="/",
                asset="",
                message="JSON root must be an object",
            )
        )
        return None
    return payload


def _resolve_asset_path(asset_path: str, repo_root: Path) -> Path:
    candidate = Path(asset_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if candidate.exists():
        return candidate
    resolved = resolve_path(asset_path)
    return resolved


def _tilemap_candidates(value: str, scene_dir: Path) -> list[Path]:
    path = Path(value)
    if path.is_absolute():
        return [path]
    candidates: list[Path] = []
    candidates.append((scene_dir / path).resolve())
    candidates.append((Path.cwd() / path).resolve())
    return candidates


def _prefab_key(entity: dict[str, Any]) -> str | None:
    if "prefab_id" in entity:
        return "prefab_id"
    if "prefab" in entity:
        return "prefab"
    return None


def _coerce_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text else None


def _is_non_negative_int(value: Any) -> bool:
    try:
        return isinstance(value, int) and value >= 0
    except Exception:
        return False


def _is_non_negative_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    try:
        return int(value[0]) >= 0 and int(value[1]) >= 0
    except Exception:
        return False


def _is_positive_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    try:
        return int(value[0]) > 0 and int(value[1]) > 0
    except Exception:
        return False


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return rel.as_posix()
    except Exception:
        return path.as_posix()


def _infer_pack_id(path: Path, repo_root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        parts = rel.parts
    except Exception:
        parts = path.parts
    for idx, part in enumerate(parts):
        if part.lower() == "packs" and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _record_reference(
    references: list[AssetReference],
    *,
    referer_pack: str | None,
    source_path: str,
    json_path: str,
    asset_path: str,
    absolute_path: Path,
    repo_root: Path,
) -> None:
    normalized_asset = _normalize_asset_path(absolute_path, repo_root, asset_path)
    references.append(
        AssetReference(
            referer_pack=referer_pack,
            source_path=source_path,
            json_path=json_path,
            asset_path=normalized_asset,
            absolute_path=absolute_path,
        )
    )


def _normalize_asset_path(absolute_path: Path, repo_root: Path, fallback: str) -> str:
    try:
        rel = absolute_path.resolve().relative_to(repo_root.resolve())
        return rel.as_posix()
    except Exception:
        return fallback.replace("\\", "/")


def _build_pack_dependency_map(pack_order: list[Any]) -> tuple[dict[str, set[str]], dict[str, dict[str, Any]]]:
    mapping: dict[str, set[str]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for entry in pack_order:
        pack_id = getattr(entry, "id", None)
        deps = getattr(entry, "dependencies", [])
        implicit = getattr(entry, "implicit", False)
        if isinstance(entry, dict):
            pack_id = entry.get("id", pack_id)
            deps = entry.get("dependencies", deps)
            implicit = entry.get("implicit", implicit)
        if not isinstance(pack_id, str) or not pack_id.strip():
            continue
        dep_ids: set[str] = set()
        if isinstance(deps, list):
            for dep in deps:
                dep_id = getattr(dep, "id", None)
                if isinstance(dep, dict):
                    dep_id = dep.get("id", dep_id)
                if isinstance(dep_id, str) and dep_id.strip():
                    dep_ids.add(dep_id.strip())
        normalized_id = pack_id.strip()
        mapping[normalized_id] = dep_ids
        meta[normalized_id] = {"implicit": bool(implicit)}
    return mapping, meta


def _load_pack_audit_config(pack_order: list[Any], repo_root: Path) -> dict[str, dict[str, list[str]]]:
    config: dict[str, dict[str, list[str]]] = {}
    for entry in pack_order:
        pack_id = getattr(entry, "id", None)
        root = getattr(entry, "root", None)
        if isinstance(entry, dict):
            pack_id = entry.get("id", pack_id)
            root = entry.get("root", root)
        if not isinstance(pack_id, str) or not pack_id.strip() or root is None:
            continue
        root_path = root if isinstance(root, Path) else Path(str(root))
        manifest_path = root_path / "pack.json"
        allow_orphans: list[str] = []
        allow_external: list[str] = []
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                audit_cfg = payload.get("asset_audit") if isinstance(payload, dict) else None
                if isinstance(audit_cfg, dict):
                    allow_orphans = _coerce_glob_list(audit_cfg.get("allow_orphans"))
                    allow_external = _coerce_glob_list(audit_cfg.get("allow_external"))
            except Exception:
                allow_orphans = []
                allow_external = []
        config[pack_id.strip()] = {
            "allow_orphans": allow_orphans,
            "allow_external": allow_external,
            "root": [root_path.as_posix()],
        }
    return config


def _coerce_glob_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    patterns: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            patterns.append(item.strip())
    return patterns


def _enforce_pack_ownership(
    *,
    references: list[AssetReference],
    pack_deps: dict[str, set[str]],
    pack_meta: dict[str, dict[str, Any]],
    pack_audit_config: dict[str, dict[str, list[str]]],
    repo_root: Path,
    errors: list[AssetAuditError],
) -> None:
    for ref in references:
        referer_pack = ref.referer_pack
        if not referer_pack:
            continue
        if pack_meta.get(referer_pack, {}).get("implicit") is True:
            continue
        referenced_pack = _extract_pack_id_from_path(ref.asset_path)
        if referenced_pack is None:
            if not _is_external_allowed(ref, pack_audit_config, repo_root):
                errors.append(
                    AssetAuditError(
                        kind="cross_pack_reference",
                        path=ref.source_path,
                        json_path=ref.json_path,
                        asset=ref.asset_path,
                        message=(
                            f"pack '{referer_pack}' references external asset '{ref.asset_path}' "
                            "without allow_external"
                        ),
                    )
                )
            continue
        if referenced_pack == referer_pack:
            continue
        deps = pack_deps.get(referer_pack, set())
        if referenced_pack not in deps:
            errors.append(
                AssetAuditError(
                    kind="cross_pack_reference",
                    path=ref.source_path,
                    json_path=ref.json_path,
                    asset=ref.asset_path,
                    message=(
                        f"pack '{referer_pack}' references pack '{referenced_pack}' "
                        f"without dependency (deps={sorted(deps)})"
                    ),
                )
            )


def _extract_pack_id_from_path(path: str) -> str | None:
    parts = Path(path).as_posix().split("/")
    for idx, part in enumerate(parts):
        if part.lower() == "packs" and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _is_external_allowed(ref: AssetReference, pack_audit_config: dict[str, dict[str, list[str]]], repo_root: Path) -> bool:
    pack_id = ref.referer_pack
    if pack_id is None:
        return True
    cfg = pack_audit_config.get(pack_id, {})
    patterns = cfg.get("allow_external", [])
    if not patterns:
        return False
    pack_root = _pack_root_for_id(pack_id, repo_root)
    rel = _relative_to_pack(ref.absolute_path, pack_root)
    if rel is None:
        rel = ref.asset_path
    return _matches_any_glob(rel, patterns)


def _collect_asset_files(pack_order: list[Any], repo_root: Path) -> list[Path]:
    roots: list[Path] = []
    for entry in pack_order:
        root = getattr(entry, "root", None)
        if isinstance(entry, dict):
            root = entry.get("root", root)
        if root is None:
            continue
        root_path = root if isinstance(root, Path) else Path(str(root))
        roots.append(root_path)
    files: list[Path] = []
    for root in roots:
        for sub in ("assets", "fx", "tilesets", "audio"):
            candidate = root / sub
            if candidate.exists():
                files.extend(_walk_asset_files(candidate))
    files = sorted({f.resolve() for f in files})
    return list(files)


def _walk_asset_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_ignored_asset_path(path):
            continue
        if _is_supported_asset_file(path):
            files.append(path)
    return files


def _is_ignored_asset_path(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered in {".ds_store", "thumbs.db"}:
        return True
    if "__pycache__" in path.parts:
        return True
    return False


def _is_supported_asset_file(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".wav", ".ogg", ".mp3"}:
        return True
    if ext in {".tsx", ".tmj"}:
        return True
    return False


def _detect_orphans(
    asset_files: list[Path],
    *,
    referenced_paths: set[Path],
    pack_audit_config: dict[str, dict[str, list[str]]],
    repo_root: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    referenced = {p.resolve() for p in referenced_paths}
    for path in asset_files:
        if path.resolve() in referenced:
            continue
        pack_id = _extract_pack_id_from_path(_display_path(path, repo_root))
        if pack_id and _is_orphan_allowed(path, pack_id, pack_audit_config, repo_root):
            continue
        entries.append(
            {
                "pack": pack_id or "",
                "path": _display_path(path, repo_root),
                "size_bytes": path.stat().st_size,
            }
        )
    return sorted(entries, key=lambda e: (e.get("pack", ""), e.get("path", "")))


def _is_orphan_allowed(
    path: Path,
    pack_id: str,
    pack_audit_config: dict[str, dict[str, list[str]]],
    repo_root: Path,
) -> bool:
    cfg = pack_audit_config.get(pack_id, {})
    patterns = cfg.get("allow_orphans", [])
    if not patterns:
        return False
    pack_root = _pack_root_for_id(pack_id, repo_root)
    rel = _relative_to_pack(path, pack_root)
    if rel is None:
        rel = _display_path(path, repo_root)
    return _matches_any_glob(rel, patterns)


def _pack_root_for_id(pack_id: str, repo_root: Path) -> Path:
    return repo_root / "packs" / pack_id


def _relative_to_pack(path: Path, pack_root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(pack_root.resolve())
        return rel.as_posix()
    except Exception:
        return None


def _matches_any_glob(path: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch

    for pattern in patterns:
        if fnmatch(path, pattern):
            return True
    return False


def _detect_duplicates(
    asset_files: list[Path],
    *,
    referenced_paths: set[Path],
    repo_root: Path,
    warn_duplicates: bool,
) -> tuple[list[dict[str, Any]], list[AssetAuditError]]:
    files = sorted({p.resolve() for p in asset_files} | {p.resolve() for p in referenced_paths})
    duplicates: list[dict[str, Any]] = []
    warnings: list[AssetAuditError] = []

    hash_groups: dict[str, list[Path]] = {}
    for path in files:
        hash_value = _hash_file(path)
        if hash_value is None:
            continue
        hash_groups.setdefault(hash_value, []).append(path)
    for hash_value, paths in sorted(hash_groups.items(), key=lambda item: item[0]):
        if len(paths) < 2:
            continue
        dup_paths = sorted(_display_path(p, repo_root) for p in paths)
        duplicates.append(
            {
                "kind": "duplicate_content_hash",
                "hash": hash_value,
                "paths": dup_paths,
            }
        )
        if warn_duplicates:
            warnings.append(
                AssetAuditError(
                    kind="duplicate_content_hash",
                    path=dup_paths[0],
                    json_path="/",
                    asset=hash_value,
                    message=f"duplicate content hash across {len(dup_paths)} files",
                )
            )

    basename_groups: dict[str, list[Path]] = {}
    for path in files:
        basename_groups.setdefault(path.name.lower(), []).append(path)
    for basename, paths in sorted(basename_groups.items(), key=lambda item: item[0]):
        if len(paths) < 2:
            continue
        dup_paths = sorted(_display_path(p, repo_root) for p in paths)
        duplicates.append(
            {
                "kind": "duplicate_basename_collision",
                "basename": basename,
                "paths": dup_paths,
            }
        )
        if warn_duplicates:
            warnings.append(
                AssetAuditError(
                    kind="duplicate_basename_collision",
                    path=dup_paths[0],
                    json_path="/",
                    asset=basename,
                    message=f"duplicate basename across {len(dup_paths)} files",
                )
            )

    duplicates = sorted(
        duplicates,
        key=lambda e: (e.get("kind", ""), e.get("hash", ""), e.get("basename", ""), str(e.get("paths", ""))),
    )
    warnings = sorted(warnings, key=lambda e: (e.path, e.asset, e.kind))
    return duplicates, warnings


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    import hashlib

    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
    except Exception:
        return None
    return hasher.hexdigest()