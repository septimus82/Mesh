from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Tuple

from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.swallowed_exceptions import _log_swallow

log = logging.getLogger(__name__)
logger = log


@dataclass(frozen=True)
class DoctorCheckSpec:
    id: str
    title: str
    enabled_predicate_name: str
    run_check_name: str
    severity: Literal["error", "warn", "info"]
    order: int


@dataclass(frozen=True)
class _Entry:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass
class DoctorContext:
    repo_root: Path
    fix: bool
    strict: bool
    packs: Iterable[str] | None
    errors: list[_Entry]
    warnings: list[_Entry]
    fixes: list[_Entry]
    parsed_json: dict[Path, Any]
    known_scene_ids: dict[str, Path]
    scene_paths: list[Path]
    world_paths: list[Path]
    missing_prefab_assets: list[dict[str, str]]
    missing_prefab_assets_warnings: list[dict[str, str]]
    cache_stats: dict[str, int]


def _single_line(text: str) -> str:
    raw = str(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(raw.split())


def _normalize_path_for_json(path: Path | str, *, repo_root: Path) -> str:
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_absolute():
        p = repo_root / p
    try:
        p = p.resolve()
    except Exception:
        _log_swallow("DARG-001", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        pass
    try:
        return p.relative_to(repo_root.resolve()).as_posix()
    except Exception:
        _log_swallow("DARG-002", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        return p.as_posix()


def _is_missing_text(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    return value.strip() == ""


def _norm_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cooked = value.strip().lower()
    return cooked or None


def _behaves_as_path(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    if v.endswith(".json"):
        return True
    return ("/" in v) or ("\\" in v)


def _discover_scene_paths(repo_root: Path) -> list[Path]:
    paths: set[Path] = set()

    scenes_dir = repo_root / "scenes"
    if scenes_dir.exists():
        for p in scenes_dir.glob("*.json"):
            if p.is_file():
                paths.add(p)

    packs_dir = repo_root / "packs"
    if packs_dir.exists():
        for scenes_folder in sorted(
            [p for p in packs_dir.rglob("scenes") if p.is_dir()], key=lambda x: x.as_posix()
        ):
            for p in scenes_folder.rglob("*.json"):
                if p.is_file():
                    paths.add(p)

    return sorted(paths, key=lambda p: _normalize_path_for_json(p, repo_root=repo_root))


def _discover_world_paths(repo_root: Path) -> list[Path]:
    worlds_dir = repo_root / "worlds"
    if not worlds_dir.exists():
        return []
    return sorted([p for p in worlds_dir.glob("*.json") if p.is_file()], key=lambda p: p.as_posix())


def _try_read_json(path: Path) -> tuple[bool, Any | None, str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return True, json.load(handle), ""
    except Exception as exc:  # noqa: BLE001  # REASON: asset doctor records any registry JSON read failure as a per-file diagnostic instead of aborting the full audit
        _log_swallow("DARG-003", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        return False, None, _single_line(f"{type(exc).__name__}: {exc}")


def _load_image_cache(path: Path) -> tuple[dict[str, dict[str, int]], bool]:
    if not path.exists():
        return {}, False
    try:
        raw_cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: invalid image cache data should be ignored with a warning so doctor-assets can rebuild cache-backed diagnostics deterministically
        _log_swallow("DARG-004", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        log.warning("[Assets] image size cache invalid: %s", exc)
        return {}, True
    if not isinstance(raw_cache, dict):
        return {}, True
    cache: dict[str, dict[str, int]] = {}
    for key, value in raw_cache.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        w_val = value.get("w")
        h_val = value.get("h")
        if isinstance(w_val, int) and isinstance(h_val, int):
            cache[key] = {"w": int(w_val), "h": int(h_val)}
    return cache, False


def _write_image_cache_atomic(path: Path, payload: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    data = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            _log_swallow("DARG-005", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
            pass
    os.replace(tmp_path, path)


def _maybe_fix_trailing_newline(path: Path, *, payload: Any, fixes: list[_Entry], repo_root: Path) -> None:
    if path.suffix.lower() != ".json":
        return
    try:
        raw_bytes = path.read_bytes()
    except Exception:
        _log_swallow("DARG-006", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        return
    if raw_bytes.endswith(b"\n"):
        return

    canonical = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=False).encode("utf-8")
    if canonical != raw_bytes:
        return

    write_json_atomic(path, payload, indent=2, sort_keys=True, trailing_newline=True)
    fixes.append(
        _Entry(
            code="json.trailing_newline.added",
            path=_normalize_path_for_json(path, repo_root=repo_root),
            message="added trailing newline",
        )
    )


def _issue_severity(ctx: DoctorContext) -> str:
    return "error" if ctx.strict else "warning"


def _add_issue(ctx: DoctorContext, severity: str, code: str, path: Path | str, message: str) -> None:
    entry = _Entry(code=code, path=_normalize_path_for_json(path, repo_root=ctx.repo_root), message=_single_line(message))
    if severity == "error":
        ctx.errors.append(entry)
    else:
        ctx.warnings.append(entry)


def _add_fix(ctx: DoctorContext, code: str, path: Path | str, message: str) -> None:
    ctx.fixes.append(
        _Entry(code=code, path=_normalize_path_for_json(path, repo_root=ctx.repo_root), message=_single_line(message))
    )


def enabled_always(_ctx: DoctorContext) -> bool:
    return True


def enabled_fix(ctx: DoctorContext) -> bool:
    return ctx.fix


def run_required_files(ctx: DoctorContext) -> None:
    config_path = ctx.repo_root / "config.json"
    if not config_path.is_file():
        _add_issue(
            ctx,
            "error",
            "required.config_json.missing",
            "config.json",
            "missing required file config.json at repo root",
        )

    quests_path = ctx.repo_root / "assets" / "data" / "quests.json"
    if not quests_path.is_file():
        _add_issue(
            ctx,
            "error",
            "required.quests_json.missing",
            quests_path,
            "missing required file assets/data/quests.json",
        )

    events_path = ctx.repo_root / "assets" / "data" / "events.json"
    if not events_path.is_file():
        _add_issue(
            ctx,
            "error",
            "required.events_json.missing",
            events_path,
            "missing required file assets/data/events.json",
        )


def run_scene_json_validation(ctx: DoctorContext) -> None:
    for scene_path in ctx.scene_paths:
        ok, payload, err = _try_read_json(scene_path)
        if not ok:
            _add_issue(ctx, _issue_severity(ctx), "scene.json.invalid", scene_path, err)
            continue
        ctx.parsed_json[scene_path] = payload


def run_world_cross_refs(ctx: DoctorContext) -> None:
    for world_path in ctx.world_paths:
        ok, world_payload, err = _try_read_json(world_path)
        if not ok:
            _add_issue(ctx, _issue_severity(ctx), "world.json.invalid", world_path, err)
            continue
        ctx.parsed_json[world_path] = world_payload
        if not isinstance(world_payload, dict):
            _add_issue(ctx, "error", "world.schema.invalid", world_path, "world file must be a JSON object")
            continue

        scenes = world_payload.get("scenes")
        if not isinstance(scenes, dict):
            _add_issue(ctx, "error", "world.scenes.invalid", world_path, "world.scenes must be an object mapping scene ids")
            continue

        for raw_id, entry in scenes.items():
            scene_id = _norm_key(raw_id)
            if scene_id is None or scene_id in ctx.known_scene_ids:
                continue
            path = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(path, str) and path.strip():
                ctx.known_scene_ids[scene_id] = (ctx.repo_root / path).resolve()

        start_scene = world_payload.get("start_scene")
        start_norm = _norm_key(start_scene)
        if start_norm is not None and start_norm not in {(_norm_key(k) or "") for k in scenes.keys()}:
            _add_issue(
                ctx,
                "error",
                "world.start_scene.unknown",
                world_path,
                f"start_scene refers to unknown scene id: {start_norm}",
            )

        for scene_id in sorted(scenes.keys(), key=lambda s: (str(s).strip().lower(), str(s))):
            entry = scenes.get(scene_id)
            if not isinstance(entry, dict):
                _add_issue(
                    ctx,
                    "error",
                    "world.scene.entry.invalid",
                    world_path,
                    f"world.scenes[{scene_id!r}] must be an object",
                )
                continue
            scene_ref = entry.get("path")
            if _is_missing_text(scene_ref):
                _add_issue(
                    ctx,
                    "error",
                    "world.scene.path.required",
                    world_path,
                    f"world.scenes[{scene_id!r}].path is required",
                )
                continue
            scene_file = ctx.repo_root / str(scene_ref)
            if not scene_file.exists():
                _add_issue(
                    ctx,
                    "error",
                    "world.scene.file.missing",
                    str(scene_ref),
                    f"referenced by {_normalize_path_for_json(world_path, repo_root=ctx.repo_root)} (scene id {scene_id!r})",
                )


def run_scene_entity_checks(ctx: DoctorContext) -> None:
    for scene_path in ctx.scene_paths:
        payload = ctx.parsed_json.get(scene_path)
        if payload is None or not isinstance(payload, dict):
            continue

        entities = payload.get("entities")
        if not isinstance(entities, list):
            continue

        changed = False
        for idx, entity in enumerate(entities):
            if not isinstance(entity, dict):
                continue
            behaviours = entity.get("behaviours")
            if not isinstance(behaviours, list):
                behaviours = []

            behaviour_config = entity.get("behaviour_config")
            if not isinstance(behaviour_config, dict):
                behaviour_config = {}

            if "TriggerZone" in behaviours:
                cfg = behaviour_config.get("TriggerZone")
                if not isinstance(cfg, dict):
                    cfg = {}
                zone_id = cfg.get("zone_id")
                if _is_missing_text(zone_id):
                    fixed_here = False
                    if ctx.fix:
                        entity_id = entity.get("id")
                        if isinstance(entity_id, str) and entity_id.strip():
                            cfg = dict(cfg)
                            cfg["zone_id"] = entity_id.strip()
                            behaviour_config = dict(behaviour_config)
                            behaviour_config["TriggerZone"] = cfg
                            entity["behaviour_config"] = behaviour_config
                            changed = True
                            fixed_here = True
                            _add_fix(
                                ctx,
                                "trigger_zone.zone_id.autofix",
                                scene_path,
                                f"set TriggerZone.zone_id from entity.id for entity {entity_id.strip()!r}",
                            )

                    if not fixed_here:
                        severity = "error" if ctx.strict else "warning"
                        _add_issue(
                            ctx,
                            severity,
                            "trigger_zone.zone_id.required",
                            scene_path,
                            f"TriggerZone missing zone_id (entity index {idx})",
                        )

            if "SceneTransition" in behaviours:
                cfg = behaviour_config.get("SceneTransition")
                if not isinstance(cfg, dict):
                    cfg = {}
                target_scene = cfg.get("target_scene")
                if _is_missing_text(target_scene):
                    _add_issue(
                        ctx,
                        "error",
                        "scene_transition.target_scene.required",
                        scene_path,
                        f"SceneTransition missing target_scene (entity index {idx})",
                    )
                else:
                    target_str = str(target_scene)
                    if _behaves_as_path(target_str):
                        target_path = ctx.repo_root / target_str
                        if not target_path.exists():
                            _add_issue(
                                ctx,
                                "warning",
                                "scene_transition.target_scene.missing",
                                target_str,
                                f"referenced by {_normalize_path_for_json(scene_path, repo_root=ctx.repo_root)} (entity index {idx})",
                            )
                        else:
                            ok, target_payload, err = _try_read_json(target_path)
                            if not ok:
                                _add_issue(
                                    ctx,
                                    _issue_severity(ctx),
                                    "scene_transition.target_scene.invalid_json",
                                    target_path,
                                    f"referenced by {_normalize_path_for_json(scene_path, repo_root=ctx.repo_root)} (entity index {idx}): {err}",
                                )
                            else:
                                ctx.parsed_json[target_path] = target_payload
                    else:
                        target_id = _norm_key(target_str)
                        if target_id is not None and target_id not in ctx.known_scene_ids:
                            _add_issue(
                                ctx,
                                "warning",
                                "scene_transition.target_scene.unknown_id",
                                scene_path,
                                f"SceneTransition target_scene id not found in any world: {target_id} (entity index {idx})",
                            )

            for field in ("collision_poly", "occluder_poly"):
                points = entity.get(field)
                if not isinstance(points, list):
                    continue
                try:
                    from engine.geometry_tools import sanitize_poly  # noqa: PLC0415

                    sanitized = sanitize_poly(points)
                except Exception:  # noqa: BLE001  # REASON: invalid scene occluder polygons should degrade to an empty sanitized result so doctor-assets can keep auditing the scene
                    _log_swallow("DARG-007", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                    sanitized = []
                if sanitized:
                    continue
                entity_id = entity.get("id") or entity.get("name") or entity.get("mesh_name") or f"index {idx}"
                prefab = entity.get("prefab_id")
                prefab_label = f" prefab={prefab!r}" if isinstance(prefab, str) and prefab else ""
                _add_issue(
                    ctx,
                    "warning",
                    f"entity.{field}.invalid",
                    scene_path,
                    f"{field} invalid/degenerate for entity {entity_id!r}{prefab_label} (index {idx})",
                )

        if changed:
            write_json_atomic(scene_path, payload, indent=2, sort_keys=True, trailing_newline=True)


def run_duplicate_ids(ctx: DoctorContext) -> None:
    quests_path = ctx.repo_root / "assets" / "data" / "quests.json"
    events_path = ctx.repo_root / "assets" / "data" / "events.json"

    if quests_path.is_file():
        ok, quests_payload, err = _try_read_json(quests_path)
        if not ok:
            _add_issue(ctx, _issue_severity(ctx), "quests.json.invalid", quests_path, err)
        else:
            ctx.parsed_json[quests_path] = quests_payload
            quest_ids: list[str] = []
            if isinstance(quests_payload, list):
                for item in quests_payload:
                    if isinstance(item, dict):
                        qid = _norm_key(item.get("id"))
                        if qid is not None:
                            quest_ids.append(qid)
            elif isinstance(quests_payload, dict):
                if isinstance(quests_payload.get("quests"), list):
                    for item in quests_payload.get("quests", []):
                        if isinstance(item, dict):
                            qid = _norm_key(item.get("id"))
                            if qid is not None:
                                quest_ids.append(qid)
                else:
                    for key in quests_payload.keys():
                        qid = _norm_key(key)
                        if qid is not None:
                            quest_ids.append(qid)
            counts: dict[str, int] = {}
            for qid in quest_ids:
                counts[qid] = counts.get(qid, 0) + 1
            for qid in sorted([k for k, v in counts.items() if v > 1]):
                _add_issue(ctx, "error", "quests.id.duplicate", quests_path, f"duplicate quest id: {qid}")

    if events_path.is_file():
        ok, events_payload, err = _try_read_json(events_path)
        if not ok:
            _add_issue(ctx, _issue_severity(ctx), "events.json.invalid", events_path, err)
        else:
            ctx.parsed_json[events_path] = events_payload
            event_names: list[str] = []
            if isinstance(events_payload, list):
                for item in events_payload:
                    if isinstance(item, dict):
                        name = _norm_key(item.get("name"))
                        if name is not None:
                            event_names.append(name)
            elif isinstance(events_payload, dict):
                for key in events_payload.keys():
                    name = _norm_key(key)
                    if name is not None:
                        event_names.append(name)
            counts = {}
            for name in event_names:
                counts[name] = counts.get(name, 0) + 1
            for name in sorted([k for k, v in counts.items() if v > 1]):
                _add_issue(ctx, "error", "events.name.duplicate", events_path, f"duplicate event name: {name}")


def run_trailing_newline_fixes(ctx: DoctorContext) -> None:
    for path in sorted(ctx.parsed_json.keys(), key=lambda p: _normalize_path_for_json(p, repo_root=ctx.repo_root)):
        _maybe_fix_trailing_newline(path, payload=ctx.parsed_json[path], fixes=ctx.fixes, repo_root=ctx.repo_root)


def run_prefab_asset_checks(ctx: DoctorContext) -> None:
    missing_prefab_assets: list[dict[str, str]] = []
    missing_prefab_assets_warnings: list[dict[str, str]] = []
    pack_scope = sorted({str(p).strip() for p in (ctx.packs or []) if str(p).strip()})
    pack_sources = {f"packs/{name}/data/prefabs.json" for name in pack_scope}
    cache_stats = {"hits": 0, "misses": 0, "entries": 0}

    try:
        from engine.prefabs import get_prefab_manager
        from engine.paths import resolve_path

        prefab_manager = get_prefab_manager()
        prefab_manager.load(force=True)
        image_cache_path = ctx.repo_root / ".mesh" / "cache" / "image_sizes.json"
        image_cache, cache_corrupted = _load_image_cache(image_cache_path)
        cache_dirty = False
        cache_hits = 0
        cache_misses = 0
        cache_entries_written = 0

        def _normalize_asset_path(path_value: str | Path) -> str:
            return _normalize_path_for_json(path_value, repo_root=ctx.repo_root)

        def check_asset(prefab_id: str, source: str, field: str, path_value: object) -> Path | None:
            if not isinstance(path_value, str):
                return None
            path_text = path_value.strip()
            if not path_text:
                return None
            try:
                resolved = resolve_path(path_text)
            except Exception:
                _log_swallow("DARG-008", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                resolved = None
            if resolved is None or not resolved.exists():
                missing_prefab_assets.append(
                    {
                        "prefab_id": prefab_id,
                        "source": source,
                        "field": field,
                        "path": _normalize_asset_path(path_text),
                    }
                )
                return None
            return resolved

        def warn_prefab_asset(
            prefab_id: str,
            source: str,
            field: str,
            path_value: str | Path,
            warning: str,
        ) -> None:
            missing_prefab_assets_warnings.append(
                {
                    "prefab_id": prefab_id,
                    "source": source,
                    "field": field,
                    "path": _normalize_asset_path(path_value),
                    "warning": _single_line(warning),
                }
            )

        def _get_image_size(path: Path) -> tuple[int, int] | None:
            nonlocal cache_dirty, cache_hits, cache_misses, cache_entries_written
            key = None
            try:
                stat = path.stat()
                rel = _normalize_asset_path(path)
                key = f"{rel}|{stat.st_mtime_ns}|{stat.st_size}"
            except Exception:
                _log_swallow("DARG-009", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                key = None
            if key and key in image_cache:
                cached = image_cache.get(key, {})
                w_cached = cached.get("w")
                h_cached = cached.get("h")
                if isinstance(w_cached, int) and isinstance(h_cached, int) and w_cached > 0 and h_cached > 0:
                    cache_hits += 1
                    return w_cached, h_cached
            if key:
                cache_misses += 1

            Image: Any
            try:
                from PIL import Image as PilImage
                Image = PilImage
            except Exception:
                _log_swallow("DARG-010", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                Image = None
            if Image is not None:
                try:
                    with Image.open(path) as img:
                        width = int(img.width)
                        height = int(img.height)
                        if key and width > 0 and height > 0:
                            if key not in image_cache:
                                cache_entries_written += 1
                            image_cache[key] = {"w": width, "h": height}
                            cache_dirty = True
                        return width, height
                except Exception:
                    _log_swallow("DARG-011", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                    pass
            try:
                raw = path.read_bytes()
            except Exception:
                _log_swallow("DARG-012", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                return None
            signature = b"\x89PNG\r\n\x1a\n"
            if len(raw) < 24 or not raw.startswith(signature):
                return None
            if raw[12:16] != b"IHDR":
                return None
            width = int.from_bytes(raw[16:20], "big")
            height = int.from_bytes(raw[20:24], "big")
            if width <= 0 or height <= 0:
                return None
            if key and width > 0 and height > 0:
                if key not in image_cache:
                    cache_entries_written += 1
                image_cache[key] = {"w": width, "h": height}
                cache_dirty = True
            return width, height

        for prefab_id in sorted(prefab_manager.prefabs.keys()):
            resolved = prefab_manager.get_prefab(prefab_id)
            if not isinstance(resolved, dict):
                continue
            entity = resolved.get("entity")
            if not isinstance(entity, dict):
                continue
            source = prefab_manager.prefab_sources.get(prefab_id, "unknown")
            if not isinstance(source, str) or not source.strip():
                source = "unknown"
            if pack_sources and source not in pack_sources:
                continue

            for field in ("collision_poly", "occluder_poly"):
                points = entity.get(field)
                if not isinstance(points, list):
                    continue
                try:
                    from engine.geometry_tools import sanitize_poly  # noqa: PLC0415

                    sanitized = sanitize_poly(points)
                except Exception:  # noqa: BLE001  # REASON: invalid prefab occluder polygons should degrade to an empty sanitized result so doctor-assets can keep auditing prefab assets
                    _log_swallow("DARG-013", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                    sanitized = []
                if sanitized:
                    continue
                _add_issue(
                    ctx,
                    "warning",
                    f"prefab.{field}.invalid",
                    source,
                    f"{field} invalid/degenerate for prefab '{prefab_id}'",
                )

            check_asset(prefab_id, source, "entity.sprite", entity.get("sprite"))
            sprite_sheet = entity.get("sprite_sheet")
            if isinstance(sprite_sheet, dict):
                image_path = check_asset(
                    prefab_id,
                    source,
                    "entity.sprite_sheet.image",
                    sprite_sheet.get("image"),
                )
                if image_path is not None:
                    size = _get_image_size(image_path)
                    if size is None:
                        continue
                    img_w, img_h = size
                    fw_raw = sprite_sheet.get("frame_width", sprite_sheet.get("frame_w"))
                    fh_raw = sprite_sheet.get("frame_height", sprite_sheet.get("frame_h"))
                    if fw_raw is None or fh_raw is None:
                        continue
                    try:
                        fw = int(fw_raw)
                        fh = int(fh_raw)
                    except (TypeError, ValueError):
                        warn_prefab_asset(
                            prefab_id,
                            source,
                            "entity.sprite_sheet",
                            image_path,
                            "invalid frame dimensions",
                        )
                        continue
                    if fw <= 0 or fh <= 0:
                        warn_prefab_asset(
                            prefab_id,
                            source,
                            "entity.sprite_sheet",
                            image_path,
                            "frame dimensions must be positive",
                        )
                        continue
                    if fw > img_w or fh > img_h:
                        warn_prefab_asset(
                            prefab_id,
                            source,
                            "entity.sprite_sheet",
                            image_path,
                            f"image size not divisible by frame size ({img_w}x{img_h} % {fw}x{fh})",
                        )
                        continue
                    if (img_w % fw) != 0 or (img_h % fh) != 0:
                        warn_prefab_asset(
                            prefab_id,
                            source,
                            "entity.sprite_sheet",
                            image_path,
                            f"image size not divisible by frame size ({img_w}x{img_h} % {fw}x{fh})",
                        )
        if cache_dirty or cache_corrupted:
            try:
                _write_image_cache_atomic(image_cache_path, image_cache)
            except Exception:
                _log_swallow("DARG-014", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
                pass
        cache_stats = {"hits": cache_hits, "misses": cache_misses, "entries": cache_entries_written}
    except Exception:
        _log_swallow("DARG-015", "engine.tooling_runtime.doctor_assets_registry blanket exception fallback")
        missing_prefab_assets = []
        missing_prefab_assets_warnings = []
        cache_stats = {"hits": 0, "misses": 0, "entries": 0}

    ctx.missing_prefab_assets = missing_prefab_assets
    ctx.missing_prefab_assets_warnings = missing_prefab_assets_warnings
    ctx.cache_stats = cache_stats


DEFAULT_DOCTOR_CHECKS: tuple[DoctorCheckSpec, ...] = (
    DoctorCheckSpec(
        id="required_files",
        title="Required files",
        enabled_predicate_name="enabled_always",
        run_check_name="run_required_files",
        severity="error",
        order=10,
    ),
    DoctorCheckSpec(
        id="scene_jsons",
        title="Scene JSON parse",
        enabled_predicate_name="enabled_always",
        run_check_name="run_scene_json_validation",
        severity="warn",
        order=20,
    ),
    DoctorCheckSpec(
        id="world_cross_refs",
        title="World cross references",
        enabled_predicate_name="enabled_always",
        run_check_name="run_world_cross_refs",
        severity="warn",
        order=30,
    ),
    DoctorCheckSpec(
        id="scene_entity_checks",
        title="Scene entity checks",
        enabled_predicate_name="enabled_always",
        run_check_name="run_scene_entity_checks",
        severity="warn",
        order=40,
    ),
    DoctorCheckSpec(
        id="duplicate_ids",
        title="Duplicate IDs",
        enabled_predicate_name="enabled_always",
        run_check_name="run_duplicate_ids",
        severity="error",
        order=50,
    ),
    DoctorCheckSpec(
        id="trailing_newlines",
        title="Trailing newline fixes",
        enabled_predicate_name="enabled_fix",
        run_check_name="run_trailing_newline_fixes",
        severity="info",
        order=60,
    ),
    DoctorCheckSpec(
        id="prefab_assets",
        title="Prefab assets",
        enabled_predicate_name="enabled_always",
        run_check_name="run_prefab_asset_checks",
        severity="warn",
        order=70,
    ),
)


def build_doctor_checks() -> tuple[
    tuple[DoctorCheckSpec, Callable[[DoctorContext], bool], Callable[[DoctorContext], None]], ...
]:
    predicate_map: dict[str, Callable[[DoctorContext], bool]] = {
        "enabled_always": enabled_always,
        "enabled_fix": enabled_fix,
    }
    runner_map: dict[str, Callable[[DoctorContext], None]] = {
        "run_required_files": run_required_files,
        "run_scene_json_validation": run_scene_json_validation,
        "run_world_cross_refs": run_world_cross_refs,
        "run_scene_entity_checks": run_scene_entity_checks,
        "run_duplicate_ids": run_duplicate_ids,
        "run_trailing_newline_fixes": run_trailing_newline_fixes,
        "run_prefab_asset_checks": run_prefab_asset_checks,
    }
    ordered = tuple(sorted(DEFAULT_DOCTOR_CHECKS, key=lambda s: (s.order, s.id)))
    resolved: list[
        tuple[DoctorCheckSpec, Callable[[DoctorContext], bool], Callable[[DoctorContext], None]]
    ] = []
    for spec in ordered:
        pred = predicate_map.get(spec.enabled_predicate_name)
        runner = runner_map.get(spec.run_check_name)
        if pred is None or runner is None:
            raise KeyError(f"Doctor check spec unresolved: {spec.id}")
        resolved.append((spec, pred, runner))
    return tuple(resolved)


def build_doctor_context(*, repo_root: Path, fix: bool, strict: bool, packs: Iterable[str] | None) -> DoctorContext:
    repo_root = Path(repo_root).resolve()
    return DoctorContext(
        repo_root=repo_root,
        fix=fix,
        strict=strict,
        packs=packs,
        errors=[],
        warnings=[],
        fixes=[],
        parsed_json={},
        known_scene_ids={},
        scene_paths=_discover_scene_paths(repo_root),
        world_paths=_discover_world_paths(repo_root),
        missing_prefab_assets=[],
        missing_prefab_assets_warnings=[],
        cache_stats={"hits": 0, "misses": 0, "entries": 0},
    )


def finalize_doctor_payload(ctx: DoctorContext) -> dict[str, Any]:
    missing_prefab_assets_sorted = sorted(
        ctx.missing_prefab_assets,
        key=lambda d: (d.get("prefab_id", ""), d.get("field", ""), d.get("path", ""), d.get("source", "")),
    )
    missing_prefab_assets_warnings_sorted = sorted(
        ctx.missing_prefab_assets_warnings,
        key=lambda d: (d.get("prefab_id", ""), d.get("field", ""), d.get("path", ""), d.get("source", "")),
    )

    errors_sorted = sorted([e.to_dict() for e in ctx.errors], key=lambda d: (d["path"], d["code"], d["message"]))
    warnings_sorted = sorted([e.to_dict() for e in ctx.warnings], key=lambda d: (d["path"], d["code"], d["message"]))
    fixes_sorted = sorted([e.to_dict() for e in ctx.fixes], key=lambda d: (d["path"], d["code"], d["message"]))

    ok_flag = len(errors_sorted) == 0 and len(missing_prefab_assets_sorted) == 0
    return {
        "ok": ok_flag,
        "errors": errors_sorted,
        "warnings": warnings_sorted,
        "fixes": fixes_sorted,
        "missing_prefab_assets": missing_prefab_assets_sorted,
        "missing_prefab_assets_warnings": missing_prefab_assets_warnings_sorted,
        "cache": ctx.cache_stats,
    }
