from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.paths import resolve_path

PERF_SCENE_CAPTURE_SCHEMA_VERSION = 1
PERF_COMPARE_SCHEMA_VERSION = 1


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected object JSON: {path.as_posix()}")
    return raw


def load_perf_scene_set(path: Path) -> list[dict[str, str]]:
    payload = _load_json(path)
    scenes_raw = payload.get("scenes")
    if not isinstance(scenes_raw, list):
        raise ValueError("perf scene set must define list 'scenes'")
    scenes: list[dict[str, str]] = []
    for entry in scenes_raw:
        if not isinstance(entry, dict):
            continue
        scene_id = str(entry.get("id", "")).strip()
        scene_path = str(entry.get("path", "")).strip()
        if not scene_id or not scene_path:
            continue
        scenes.append({"id": scene_id, "path": scene_path})
    scenes.sort(key=lambda item: item["id"])
    return scenes


def _entity_tags(entity: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    tag_value = entity.get("tag")
    if isinstance(tag_value, str) and tag_value.strip():
        tags.add(tag_value.strip().lower())
    tags_value = entity.get("tags")
    if isinstance(tags_value, list):
        for tag in tags_value:
            if isinstance(tag, str) and tag.strip():
                tags.add(tag.strip().lower())
    return tags


def _entity_is_renderable(entity: dict[str, Any], tags: set[str]) -> bool:
    if {"system", "trigger", "spawn_point"} & tags:
        return False
    prefab_id = str(entity.get("prefab_id", "")).strip().lower()
    if prefab_id in {"", "trigger_zone"}:
        return False
    if any(key in entity for key in ("sprite", "texture", "animation", "prefab_id")):
        return True
    return bool(tags - {"system", "trigger", "spawn_point"})


def _entity_has_collider(entity: dict[str, Any], tags: set[str]) -> bool:
    if {"enemy", "player", "hazard"} & tags:
        return True
    if "trigger" in tags:
        return True
    for key in ("radius", "collision_radius", "width", "height"):
        value = entity.get(key)
        if isinstance(value, (int, float)) and float(value) > 0.0:
            return True
    return False


def _entity_has_audio(entity: dict[str, Any], tags: set[str]) -> bool:
    if {"audio", "ambient_audio"} & tags:
        return True
    return any("audio" in str(key).lower() for key in entity.keys())


def compute_scene_counters(scene_payload: dict[str, Any], *, ticks: int) -> dict[str, int]:
    entities_raw = scene_payload.get("entities")
    entities = entities_raw if isinstance(entities_raw, list) else []
    entity_count = 0
    active_entity_count = 0
    trigger_zone_count = 0
    collider_candidate_count = 0
    renderable_entity_count = 0
    audio_entity_count = 0

    for item in entities:
        if not isinstance(item, dict):
            continue
        entity_count += 1
        tags = _entity_tags(item)
        if "system" not in tags:
            active_entity_count += 1
        if "trigger" in tags:
            trigger_zone_count += 1
        if _entity_has_collider(item, tags):
            collider_candidate_count += 1
        if _entity_is_renderable(item, tags):
            renderable_entity_count += 1
        if _entity_has_audio(item, tags):
            audio_entity_count += 1

    ticks_value = max(1, int(ticks))
    return {
        "entity_count": int(entity_count),
        "active_entity_count": int(active_entity_count),
        "trigger_zone_count": int(trigger_zone_count),
        "collider_candidate_count": int(collider_candidate_count),
        "renderable_entity_count": int(renderable_entity_count),
        "audio_entity_count": int(audio_entity_count),
        "entity_update_calls": int(active_entity_count * ticks_value),
        "collision_overlap_checks": int((collider_candidate_count + trigger_zone_count) * ticks_value),
        "draw_batches": int(renderable_entity_count * ticks_value),
        "audio_updates": int(audio_entity_count * ticks_value),
    }


def run_perf_scene_capture(
    *,
    scene_set_path: Path,
    ticks: int,
) -> dict[str, Any]:
    scenes = load_perf_scene_set(scene_set_path)
    scene_rows: list[dict[str, Any]] = []
    for entry in scenes:
        scene_id = entry["id"]
        scene_path = entry["path"]
        resolved = resolve_path(scene_path)
        payload = _load_json(resolved)
        counters = compute_scene_counters(payload, ticks=ticks)
        scene_rows.append(
            {
                "id": scene_id,
                "path": scene_path,
                "name": str(payload.get("name", "") or ""),
                "counters": dict(sorted(counters.items())),
            }
        )

    metric_names = sorted({name for row in scene_rows for name in row["counters"].keys()})
    totals: dict[str, int] = {}
    for metric in metric_names:
        totals[metric] = int(sum(int(row["counters"].get(metric, 0)) for row in scene_rows))

    return {
        "schema_version": PERF_SCENE_CAPTURE_SCHEMA_VERSION,
        "mode": "scene_counter_capture",
        "ticks": int(max(1, int(ticks))),
        "scene_set": scene_set_path.as_posix(),
        "metric_names": metric_names,
        "scenes": sorted(scene_rows, key=lambda row: str(row.get("id", ""))),
        "totals": dict(sorted(totals.items())),
    }


def load_perf_baseline(path: Path) -> dict[str, Any]:
    return _load_json(path)


def _metric_increase_allowed(
    tolerances: dict[str, Any],
    metric_name: str,
) -> int:
    default_entry = tolerances.get("__default__", {})
    metric_entry = tolerances.get(metric_name, {})
    if not isinstance(default_entry, dict):
        default_entry = {}
    if not isinstance(metric_entry, dict):
        metric_entry = {}
    raw = metric_entry.get("increase_allowed", default_entry.get("increase_allowed", 0))
    return max(0, int(raw if isinstance(raw, (int, float)) else 0))


def compare_perf_run_to_baseline(
    *,
    run_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
) -> dict[str, Any]:
    run_scene_rows = run_payload.get("scenes")
    baseline_scene_rows = baseline_payload.get("scenes")
    if not isinstance(run_scene_rows, list) or not isinstance(baseline_scene_rows, list):
        raise ValueError("both run and baseline payloads must contain list 'scenes'")

    tolerances_raw = baseline_payload.get("tolerances", {})
    tolerances = tolerances_raw if isinstance(tolerances_raw, dict) else {}

    run_by_id = {
        str(item.get("id", "")): item
        for item in run_scene_rows
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    baseline_by_id = {
        str(item.get("id", "")): item
        for item in baseline_scene_rows
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }

    regressions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for scene_id in sorted(baseline_by_id.keys()):
        baseline_row = baseline_by_id[scene_id]
        run_row = run_by_id.get(scene_id)
        if run_row is None:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "perf.baseline.scene_missing",
                    "message": f"scene '{scene_id}' missing from perf run payload",
                    "source": "engine.tooling.perf_baselines",
                    "location": scene_id,
                }
            )
            continue
        baseline_counters = baseline_row.get("counters", {})
        run_counters = run_row.get("counters", {})
        if not isinstance(baseline_counters, dict) or not isinstance(run_counters, dict):
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "perf.baseline.invalid_counters",
                    "message": f"invalid counters structure for scene '{scene_id}'",
                    "source": "engine.tooling.perf_baselines",
                    "location": scene_id,
                }
            )
            continue
        for metric_name in sorted(baseline_counters.keys()):
            baseline_value_raw = baseline_counters.get(metric_name, 0)
            run_value_raw = run_counters.get(metric_name, 0)
            baseline_value = int(baseline_value_raw if isinstance(baseline_value_raw, (int, float)) else 0)
            run_value = int(run_value_raw if isinstance(run_value_raw, (int, float)) else 0)
            increase_allowed = _metric_increase_allowed(tolerances, metric_name)
            if run_value > baseline_value + increase_allowed:
                delta = run_value - baseline_value
                regressions.append(
                    {
                        "scene_id": scene_id,
                        "metric": metric_name,
                        "baseline": baseline_value,
                        "current": run_value,
                        "increase_allowed": increase_allowed,
                        "delta": delta,
                    }
                )
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": f"perf.baseline.regression.{metric_name}",
                        "message": (
                            f"{scene_id}: {metric_name} regressed "
                            f"(baseline={baseline_value}, current={run_value}, delta={delta})"
                        ),
                        "source": "engine.tooling.perf_baselines",
                        "location": scene_id,
                        "context": {
                            "metric": metric_name,
                            "baseline": baseline_value,
                            "current": run_value,
                            "increase_allowed": increase_allowed,
                        },
                    }
                )

    regressions.sort(key=lambda row: (str(row.get("scene_id", "")), str(row.get("metric", ""))))
    diagnostics.sort(key=lambda row: (str(row.get("code", "")), str(row.get("location", ""))))
    return {
        "schema_version": PERF_COMPARE_SCHEMA_VERSION,
        "ok": len(regressions) == 0 and len(
            [d for d in diagnostics if str(d.get("severity", "")) == "error"]
        )
        == 0,
        "regressions": regressions,
        "diagnostics": diagnostics,
        "scene_count": int(len(baseline_by_id)),
        "checked_scene_ids": sorted(baseline_by_id.keys()),
        "tolerances": tolerances,
    }


__all__ = [
    "PERF_COMPARE_SCHEMA_VERSION",
    "PERF_SCENE_CAPTURE_SCHEMA_VERSION",
    "compare_perf_run_to_baseline",
    "compute_scene_counters",
    "load_perf_baseline",
    "load_perf_scene_set",
    "run_perf_scene_capture",
]
