from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from engine.repo_root import find_repo_root


def discover_scene_paths(repo_root: Path) -> list[Path]:
    """Discover scene JSON files deterministically (no engine load)."""
    root = Path(repo_root).resolve()
    candidates: list[Path] = []

    scenes_dir = root / "scenes"
    if scenes_dir.exists():
        candidates.extend([p for p in scenes_dir.glob("*.json") if p.is_file()])

    packs_dir = root / "packs"
    if packs_dir.exists():
        candidates.extend([p for p in packs_dir.glob("**/scenes/*.json") if p.is_file()])

    def _rel_posix(p: Path) -> str:
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            return p.as_posix()

    candidates.sort(key=_rel_posix)
    return candidates


def discover_world_paths(repo_root: Path) -> list[Path]:
    """Discover world JSON files deterministically (no engine load)."""
    root = Path(repo_root).resolve()
    worlds_dir = root / "worlds"
    if not worlds_dir.exists():
        return []

    candidates = [p for p in worlds_dir.glob("*.json") if p.is_file()]

    def _rel_posix(p: Path) -> str:
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            return p.as_posix()

    candidates.sort(key=_rel_posix)
    return candidates


def _repo_root_or_cwd() -> Path:
    return find_repo_root() or Path.cwd().resolve()


def _norm_key(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.lower()


def _entity_behaviours(entity: dict[str, Any]) -> list[str]:
    raw = entity.get("behaviours")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            t = item.strip()
            if t:
                out.append(t)
        elif isinstance(item, dict):
            kind = item.get("type")
            if isinstance(kind, str) and kind.strip():
                out.append(kind.strip())
    return out


def _extract_trigger_zone_id(entity: dict[str, Any]) -> str | None:
    bcfg = entity.get("behaviour_config")
    if not isinstance(bcfg, dict):
        return None
    tz = bcfg.get("TriggerZone")
    if not isinstance(tz, dict):
        return None
    zone_id = tz.get("zone_id")
    if not isinstance(zone_id, str):
        return None
    zone_id = zone_id.strip()
    return zone_id or None


def _mesh_name_candidate(entity: dict[str, Any]) -> str | None:
    name = entity.get("mesh_name") or entity.get("name") or entity.get("prefab_id")
    if not isinstance(name, str):
        return None
    name = name.strip()
    return name or None


def _safe_read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("JSON root is not an object")
    return raw


def analyze_scene(path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or _repo_root_or_cwd()).resolve()
    rel = path.resolve()
    try:
        rel_str = rel.relative_to(root).as_posix()
    except Exception:
        rel_str = rel.as_posix()

    raw = _safe_read_json(rel)
    entities = raw.get("entities")
    entities = entities if isinstance(entities, list) else []
    entity_dicts = [e for e in entities if isinstance(e, dict)]

    trigger_zone_count = 0
    transition_count = 0

    id_unique: set[str] = set()
    id_missing = 0
    id_dup_occurrences = 0

    zone_unique: set[str] = set()
    zone_missing = 0
    zone_dup_occurrences = 0

    mesh_unique: set[str] = set()
    mesh_missing = 0
    mesh_dup_occurrences = 0

    for entity in entity_dicts:
        behaviours = _entity_behaviours(entity)
        bcfg = entity.get("behaviour_config")
        bcfg = bcfg if isinstance(bcfg, dict) else {}

        has_trigger = ("TriggerZone" in behaviours) or ("TriggerZone" in bcfg)
        has_transition = ("SceneTransition" in behaviours) or ("SceneTransition" in bcfg)
        if has_trigger:
            trigger_zone_count += 1
        if has_transition:
            transition_count += 1

        entity_id = entity.get("id")
        entity_id = entity_id.strip() if isinstance(entity_id, str) else ""
        if not entity_id:
            id_missing += 1
        else:
            k = _norm_key(entity_id)
            if k is not None:
                if k in id_unique:
                    id_dup_occurrences += 1
                else:
                    id_unique.add(k)

        if has_trigger:
            zid = _extract_trigger_zone_id(entity)
            if not zid:
                zone_missing += 1
            else:
                k = _norm_key(zid)
                if k is not None:
                    if k in zone_unique:
                        zone_dup_occurrences += 1
                    else:
                        zone_unique.add(k)

        mesh = _mesh_name_candidate(entity)
        if not mesh:
            mesh_missing += 1
        else:
            k = _norm_key(mesh)
            if k is not None:
                if k in mesh_unique:
                    mesh_dup_occurrences += 1
                else:
                    mesh_unique.add(k)

    issues: list[str] = []
    if id_missing:
        issues.append("entity.id.required")
    if zone_missing:
        issues.append("trigger_zone.zone_id.required")
    if id_dup_occurrences:
        issues.append("entity.id.duplicate")
    if zone_dup_occurrences:
        issues.append("trigger_zone.zone_id.duplicate")

    return {
        "path": rel_str,
        "basename": os.path.basename(rel_str),
        "entity_count": len(entity_dicts),
        "trigger_zone_count": trigger_zone_count,
        "transition_count": transition_count,
        "id": {"unique": len(id_unique), "missing": id_missing, "duplicates": id_dup_occurrences},
        "zone_id": {"unique": len(zone_unique), "missing": zone_missing, "duplicates": zone_dup_occurrences},
        "mesh_name": {"unique": len(mesh_unique), "missing": mesh_missing, "duplicates": mesh_dup_occurrences},
        "issues": issues,
    }


def analyze_world(path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or _repo_root_or_cwd()).resolve()
    full = path.resolve()
    try:
        rel_str = full.relative_to(root).as_posix()
    except Exception:
        rel_str = full.as_posix()

    raw = _safe_read_json(full)
    world_id = raw.get("id")
    world_id = world_id.strip() if isinstance(world_id, str) and world_id.strip() else None

    scenes = raw.get("scenes")
    scenes = scenes if isinstance(scenes, dict) else {}
    scene_ids = [str(k) for k in scenes.keys()]
    scene_ids_sorted = sorted(scene_ids)

    start_scene = raw.get("start_scene")
    start_scene = start_scene.strip() if isinstance(start_scene, str) and start_scene.strip() else None

    start_scene_ok: bool | None
    issues: list[str] = []
    if start_scene is None:
        start_scene_ok = None
        issues.append("world.start_scene.required")
    else:
        start_scene_ok = start_scene in scenes
        if not start_scene_ok:
            issues.append("world.start_scene.unknown")

    sample = scene_ids_sorted[:8]
    links = raw.get("links")
    link_count = len(links) if isinstance(links, list) else 0

    _ = link_count  # informational only (not required in CLI output spec)

    return {
        "path": rel_str,
        "basename": os.path.basename(rel_str),
        "world_id": world_id,
        "scene_count": len(scene_ids_sorted),
        "start_scene": start_scene,
        "start_scene_ok": start_scene_ok,
        "scene_ids_sample": sample,
        "issues": issues,
    }


def list_scenes(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or _repo_root_or_cwd()).resolve()
    scenes = [analyze_scene(p, repo_root=root) for p in discover_scene_paths(root)]
    issues_count = sum(len(s.get("issues") or []) for s in scenes)
    return {"ok": True, "scenes": scenes, "summary": {"scene_count": len(scenes), "issues_count": issues_count}}


def list_worlds(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or _repo_root_or_cwd()).resolve()
    worlds = [analyze_world(p, repo_root=root) for p in discover_world_paths(root)]
    issues_count = sum(len(w.get("issues") or []) for w in worlds)
    return {"ok": True, "worlds": worlds, "summary": {"world_count": len(worlds), "issues_count": issues_count}}


def list_encounter_presets(*, repo_root: Path | None = None) -> dict[str, Any]:
    from engine.encounter_presets import load_encounter_presets
    from engine.paths import resolve_path

    root = Path(repo_root or _repo_root_or_cwd()).resolve()
    presets_path = root / "packs" / "core_regions" / "data" / "encounter_presets.json"
    if not presets_path.exists():
        presets_path = resolve_path("packs/core_regions/data/encounter_presets.json")

    if not presets_path.exists():
        return {
            "ok": False,
            "presets": [],
            "issues": [
                {
                    "level": "ERROR",
                    "message": "packs/core_regions/data/encounter_presets.json: not found",
                }
            ],
            "summary": {"preset_count": 0, "issue_count": 1},
        }

    presets, issues = load_encounter_presets(presets_path, strict_unknown_keys=False)

    preset_ids = sorted(presets.keys())
    out_presets = [{"id": pid} for pid in preset_ids]
    out_issues = [{"level": i.level, "message": i.message} for i in issues]
    ok = not any(i["level"] == "ERROR" for i in out_issues)

    return {
        "ok": ok,
        "presets": out_presets,
        "issues": out_issues,
        "summary": {"preset_count": len(out_presets), "issue_count": len(out_issues)},
    }
