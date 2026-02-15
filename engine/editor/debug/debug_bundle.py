"""Deterministic debug bundle capture for editor tooling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from engine.combat_constants import (
    canonicalize_combat_event_name,
    is_combat_damage_event,
    is_combat_death_event,
)
from engine.hud_model import build_hud_view_model, merge_event_histories
from engine.persistence_io import dumps_json_deterministic
from engine.save_runtime.io import get_save_runtime_diagnostics_snapshot

from engine.editor.behaviour_inspector import build_entity_behaviour_summary
from .cutscene_debug_model import CutsceneDebugViewModel, build_cutscene_debug_view_model
from .debug_panels_state import (
    get_cutscene_events,
    get_cutscene_state,
    get_quest_diagnostics,
    get_quest_inspector_state,
)
from .event_monitor_model import build_event_log_view_model_from_settings
from .quest_debug_model import QuestDebugViewModel, build_quest_debug_view_model


@dataclass(frozen=True, slots=True)
class DebugBundle:
    """Snapshot of debug-relevant state for deterministic inspection."""

    world: dict[str, Any]
    lighting: dict[str, Any]
    render: dict[str, Any] | None
    quests: dict[str, Any]
    cutscene: dict[str, Any]
    events: dict[str, Any]
    hud: dict[str, Any]
    selected_entity: dict[str, Any]
    created_at: str | None = None
    engine_version: str | None = None

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "deterministic": bool(deterministic),
        }
        if self.engine_version:
            meta["engine_version"] = self.engine_version
        if not deterministic and self.created_at:
            meta["created_at"] = self.created_at
        return {
            "meta": meta,
            "world": self.world,
            "lighting": self.lighting,
            "render": self.render,
            "quests": self.quests,
            "cutscene": self.cutscene,
            "events": self.events,
            "hud": self.hud,
            "selected_entity": self.selected_entity,
        }

    def to_json(self, *, deterministic: bool = False) -> str:
        return dumps_json_deterministic(self.to_dict(deterministic=deterministic))


def build_debug_bundle(
    window: Any | None,
    editor: Any | None = None,
    *,
    deterministic: bool = False,
) -> DebugBundle:
    """Build a DebugBundle from available subsystems (safe in headless contexts)."""
    created_at = None if deterministic else datetime.now(timezone.utc).isoformat()
    engine_version = _safe_engine_version()

    quest_state = get_quest_inspector_state(window) if window is not None else None
    quest_diags = get_quest_diagnostics(window) if window is not None else []
    quest_vm = build_quest_debug_view_model(quest_state, quest_diags)

    cutscene_state, cutscene_commands = get_cutscene_state(window) if window is not None else (None, [])
    cutscene_vm = build_cutscene_debug_view_model(
        cutscene_state,
        cutscene_commands,
        recent_events=get_cutscene_events(window) if window is not None else [],
    )

    event_vm = build_event_log_view_model_from_settings(
        getattr(window, "gameplay_event_bus", None) if window is not None else None,
        getattr(editor, "workspace_data", None) if editor is not None else None,
    )

    return DebugBundle(
        world=_build_world_snapshot(window),
        lighting=_build_lighting_snapshot(window),
        render=_build_render_snapshot(window),
        quests=_build_quest_snapshot(quest_vm, quest_state),
        cutscene=_build_cutscene_snapshot(cutscene_vm, cutscene_state, cutscene_commands),
        events=_build_event_snapshot(event_vm, window),
        hud=_build_hud_snapshot(window),
        selected_entity=_build_selected_entity_snapshot(editor),
        created_at=created_at,
        engine_version=engine_version,
    )


def _safe_engine_version() -> str | None:
    try:
        from engine.version import ENGINE_VERSION

        return str(ENGINE_VERSION)
    except Exception:
        return None


def _build_world_snapshot(window: Any | None) -> dict[str, Any]:
    current = ""
    frame = None
    if window is not None:
        try:
            from engine.save_runtime.digest import compute_world_digest_from_scene  # noqa: PLC0415

            scene_controller = getattr(window, "scene_controller", None)
            quest_manager = getattr(window, "quest_manager", None)
            if quest_manager is None:
                quest_manager = getattr(getattr(window, "game_state_controller", None), "quests", None)
            if scene_controller is not None:
                current = compute_world_digest_from_scene(scene_controller, quest_manager, frame=0)
        except Exception:
            current = ""

    recent = _collect_recent_digests(window)

    snapshot: dict[str, Any] = {
        "current": current,
        "recent": [{"frame": frame_id, "digest": digest} for frame_id, digest in recent],
        "save_runtime_diagnostics": _build_save_runtime_diagnostics_summary(),
    }
    if frame is not None:
        snapshot["frame"] = frame
    return snapshot


def _build_save_runtime_diagnostics_summary(*, max_items: int = 5) -> dict[str, Any]:
    snapshot = get_save_runtime_diagnostics_snapshot()
    if not isinstance(snapshot, dict):
        return {
            "last_save_attempt": {"kind": None, "path": None, "ok": None, "counts": {}, "diagnostics": []},
            "last_load_attempt": {"kind": None, "path": None, "ok": None, "counts": {}, "diagnostics": []},
        }

    out: dict[str, Any] = {}
    for key in ("last_save_attempt", "last_load_attempt"):
        attempt = snapshot.get(key, {})
        if not isinstance(attempt, dict):
            out[key] = {"kind": None, "path": None, "ok": None, "counts": {}, "diagnostics": []}
            continue
        diagnostics_block = attempt.get("diagnostics", {})
        counts: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        if isinstance(diagnostics_block, dict):
            raw_counts = diagnostics_block.get("counts", {})
            if isinstance(raw_counts, dict):
                counts = {str(k): raw_counts[k] for k in sorted(raw_counts.keys())}
            raw_rows = diagnostics_block.get("diagnostics", [])
            if isinstance(raw_rows, list):
                for row in raw_rows[: max(0, int(max_items))]:
                    if not isinstance(row, dict):
                        continue
                    rows.append({str(k): row[k] for k in sorted(row.keys())})
        out[key] = {
            "kind": attempt.get("kind"),
            "path": attempt.get("path"),
            "ok": attempt.get("ok"),
            "counts": counts,
            "diagnostics": rows,
        }
    return out


def _collect_recent_digests(window: Any | None) -> list[tuple[int, str]]:
    candidates = []
    if window is not None:
        candidates.extend(
            [
                getattr(window, "world_digest_tracker", None),
                getattr(window, "digest_tracker", None),
                getattr(getattr(window, "game_state_controller", None), "digest_tracker", None),
            ]
        )
    for tracker in candidates:
        digests = getattr(tracker, "digests", None) if tracker is not None else None
        if isinstance(digests, dict):
            items: list[tuple[int, str]] = []
            for key, value in digests.items():
                try:
                    frame = int(key)
                except (TypeError, ValueError):
                    continue
                digest = str(value or "")
                items.append((frame, digest))
            items.sort(key=lambda item: item[0])
            return items
    return []


def _build_lighting_snapshot(window: Any | None) -> dict[str, Any]:
    plan_digest = ""
    cache_flags: dict[str, Any] = {
        "layer_dirty": None,
        "shadows_dirty": None,
    }
    if window is None:
        return {"plan_digest": plan_digest, "cache_flags": cache_flags}

    lighting = getattr(window, "lighting", None)
    if lighting is None:
        return {"plan_digest": plan_digest, "cache_flags": cache_flags}

    cache_state = getattr(lighting, "_cache_state", None)
    if cache_state is None:
        cache_state = getattr(lighting, "cache_state", None)

    if cache_state is not None:
        cache_flags["layer_dirty"] = bool(getattr(cache_state, "layer_dirty", False))
        cache_flags["shadows_dirty"] = bool(getattr(cache_state, "shadows_dirty", False))

    try:
        from engine.lighting import build_lighting_plan_from_dicts  # noqa: PLC0415

        lights_data = list(getattr(lighting, "_static_configs", []) or [])
        occluders_data = list(getattr(lighting, "_static_occluders", []) or [])
        ambient_color = getattr(lighting, "ambient_color", None)
        shadows_mode = str(getattr(lighting, "shadows_mode", "none") or "none")

        plan = build_lighting_plan_from_dicts(
            lights_data=lights_data,
            occluders_data=occluders_data,
            ambient_color=ambient_color,
            shadows_mode=shadows_mode,
        )
        plan_digest = plan.digest()
    except Exception:
        plan_digest = ""

    return {
        "plan_digest": plan_digest,
        "cache_flags": cache_flags,
    }


def _build_render_snapshot(window: Any | None) -> dict[str, Any] | None:
    if window is None:
        return None
    scene_controller = getattr(window, "scene_controller", None)
    if scene_controller is None:
        return None
    try:
        from engine.render_plan import build_render_plan_from_sprites  # noqa: PLC0415

        sprites = list(getattr(scene_controller, "all_sprites", []) or [])
        sort_mode = str(getattr(scene_controller, "_render_sort_mode", "y_sort") or "y_sort")
        plan = build_render_plan_from_sprites(sprites, scene_id=str(scene_controller.current_scene_path or ""), sort_mode=sort_mode)
        return {
            "plan_digest": plan.digest(),
            "call_count": len(plan),
            "scene_id": plan.scene_id,
        }
    except Exception:
        return None


def _build_quest_snapshot(
    quest_vm: QuestDebugViewModel,
    inspector_state: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "inspector_state": _normalize_quest_inspector_state(inspector_state),
        "diagnostics": [
            {
                "quest_id": diag.quest_id,
                "step_id": diag.step_id,
                "event_type": diag.event_type,
                "matched": bool(diag.matched),
                "reason": diag.reason,
            }
            for diag in quest_vm.diagnostics
        ],
    }


def _normalize_quest_inspector_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    quests_raw = state.get("quests")
    quests: list[dict[str, Any]] = []
    if isinstance(quests_raw, list):
        for entry in quests_raw:
            if not isinstance(entry, dict):
                continue
            quest_id = str(entry.get("id", "") or "")
            if not quest_id:
                continue
            current = entry.get("current_stage")
            current_stage = None
            if isinstance(current, dict):
                current_stage = {
                    "id": str(current.get("id", "")),
                    "title": str(current.get("title", "")),
                    "text": str(current.get("text", "")),
                    "has_complete_trigger": bool(current.get("has_complete_trigger", False)),
                    "has_requirements": bool(current.get("has_requirements", False)),
                }
            completed = entry.get("completed_stages", [])
            completed_list = sorted({str(v) for v in completed if str(v).strip()})
            requires = entry.get("requires_flags", [])
            requires_list = sorted({str(v) for v in requires if str(v).strip()})
            blocks = entry.get("blocks_flags", [])
            blocks_list = sorted({str(v) for v in blocks if str(v).strip()})
            progress_pct = entry.get("progress_pct", 0.0)
            try:
                progress_pct = round(float(progress_pct), 6)
            except (TypeError, ValueError):
                progress_pct = 0.0
            quests.append(
                {
                    "id": quest_id,
                    "title": str(entry.get("title", quest_id)),
                    "status": str(entry.get("status", "inactive")),
                    "progress": str(entry.get("progress", "")),
                    "progress_pct": progress_pct,
                    "current_stage": current_stage,
                    "awaiting_stage": str(entry.get("awaiting_stage", "") or "") or None,
                    "completed_stages": completed_list,
                    "requires_flags": requires_list,
                    "blocks_flags": blocks_list,
                }
            )
    quests.sort(key=lambda q: q["id"].lower())
    return {
        "total_quests": int(state.get("total_quests", len(quests)) or 0),
        "active_count": int(state.get("active_count", 0) or 0),
        "completed_count": int(state.get("completed_count", 0) or 0),
        "inactive_count": int(state.get("inactive_count", 0) or 0),
        "quests": quests,
    }


def _build_cutscene_snapshot(
    cutscene_vm: CutsceneDebugViewModel,
    inspector_state: dict[str, Any] | None,
    command_list: list[dict[str, Any]],
) -> dict[str, Any]:
    commands = _normalize_command_list(command_list)
    state = _normalize_dict(inspector_state) if isinstance(inspector_state, dict) else None
    return {
        "inspector_state": state,
        "summary": {
            "is_running": bool(cutscene_vm.is_running),
            "script_id": cutscene_vm.script_id,
            "command_index": int(cutscene_vm.command_index),
            "command_count": int(cutscene_vm.command_count),
            "current_command": cutscene_vm.current_command,
            "current_label": cutscene_vm.current_label,
            "wait_remaining": round(float(cutscene_vm.wait_remaining), 6),
        },
        "commands": commands,
        "recent_events": [
            {
                "sequence": int(event.sequence),
                "event_type": event.event_type,
                "payload_preview": event.payload_preview,
            }
            for event in cutscene_vm.recent_events
        ],
    }


def _normalize_command_list(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for entry in commands or []:
        if not isinstance(entry, dict):
            continue
        idx_raw = entry.get("index", 0)
        try:
            idx_val = int(idx_raw if idx_raw is not None else 0)
        except (TypeError, ValueError):
            idx_val = 0
        cleaned.append(
            {
                "index": idx_val,
                "type": str(entry.get("type", "")),
                "duration": entry.get("duration"),
                "event_type": entry.get("event_type") or entry.get("event"),
                "name": entry.get("name"),
                "target": entry.get("target"),
            }
        )
    cleaned.sort(key=lambda c: c.get("index", 0))
    return cleaned


def _normalize_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {k: _normalize_value(v) for k, v in sorted(value.items())}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _normalize_dict(value)
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    return value


def _build_event_snapshot(event_vm, window: Any | None) -> dict[str, Any]:
    rows = []
    for row in event_vm.rows:
        rows.append(
            {
                "sequence": int(row.sequence),
                "event_type": row.event_type,
                "source_entity": row.source_entity,
                "source_behaviour": row.source_behaviour,
                "payload_preview": row.payload_preview,
            }
        )
    combat_summary = _build_combat_event_summary(window)
    return {
        "event_type_filter": event_vm.event_type_filter,
        "entity_id_filter": event_vm.entity_id,
        "limit": int(event_vm.limit),
        "total_events": int(event_vm.total_events),
        "filtered_count": len(rows),
        "rows": rows,
        "combat_summary": combat_summary,
    }


def _build_hud_snapshot(window: Any | None) -> dict[str, Any]:
    player = getattr(window, "player", None) if window is not None else None
    gameplay_history = _collect_gameplay_history(window)
    mesh_history = _collect_mesh_history(window)
    merged_history = merge_event_histories(gameplay_history, mesh_history)
    view_model = build_hud_view_model(
        player,
        merged_history,
        now_frame_or_time=float(_infer_hud_frame(window)),
    )
    return {
        "health": {
            "hp": view_model.health_state.hp,
            "max_hp": view_model.health_state.max_hp,
            "dead": bool(view_model.health_state.dead),
            "last_damage_time": view_model.health_state.last_damage_time,
            "last_damage_amount": view_model.health_state.last_damage_amount,
        },
        "feed": [
            {
                "event_type": row.event_type,
                "source": row.source,
                "target": row.target,
                "amount": row.amount,
                "seq": int(row.seq),
            }
            for row in view_model.recent_feed_rows
        ],
    }


def _build_combat_event_summary(window: Any | None, *, limit: int = 10) -> dict[str, Any]:
    events = _collect_gameplay_history(window)
    if not events:
        return {
            "damage_event_count": 0,
            "death_event_count": 0,
            "damage_taken": {},
            "damage_dealt": {},
            "recent": [],
        }

    damage_taken: dict[str, float] = {}
    damage_dealt: dict[str, float] = {}
    recent: list[dict[str, Any]] = []
    damage_event_count = 0
    death_event_count = 0

    for event in events:
        event_type = canonicalize_combat_event_name(str(event.get("event_type", "")))
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if is_combat_damage_event(event_type):
            damage_event_count += 1
            amount = _coerce_float(payload.get("amount"))
            source = _coerce_str(payload.get("source") or payload.get("attacker") or event.get("source_entity"))
            target = _coerce_str(payload.get("target") or payload.get("name") or payload.get("entity"))
            if source:
                damage_dealt[source] = round(damage_dealt.get(source, 0.0) + amount, 6)
            if target:
                damage_taken[target] = round(damage_taken.get(target, 0.0) + amount, 6)
            recent.append(
                {
                    "event_type": event_type,
                    "source": source or None,
                    "target": target or None,
                    "amount": round(amount, 6),
                }
            )
        elif is_combat_death_event(event_type):
            death_event_count += 1
            target = _coerce_str(payload.get("name") or payload.get("entity") or payload.get("target"))
            source = _coerce_str(payload.get("source") or payload.get("attacker"))
            recent.append(
                {
                    "event_type": event_type,
                    "source": source or None,
                    "target": target or None,
                    "amount": 0.0,
                }
            )

    recent = recent[-max(0, int(limit)) :]
    return {
        "damage_event_count": int(damage_event_count),
        "death_event_count": int(death_event_count),
        "damage_taken": {k: damage_taken[k] for k in sorted(damage_taken)},
        "damage_dealt": {k: damage_dealt[k] for k in sorted(damage_dealt)},
        "recent": recent,
    }


def _collect_gameplay_history(window: Any | None, *, limit: int = 200) -> list[dict[str, Any]]:
    if window is None:
        return []
    bus = getattr(window, "gameplay_event_bus", None)
    getter = getattr(bus, "get_history", None) if bus is not None else None
    if not callable(getter):
        return []
    try:
        history = list(getter(limit))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for index, event in enumerate(history):
        payload = getattr(event, "payload", {})
        rows.append(
            {
                "event_type": str(getattr(event, "event_type", "") or ""),
                "payload": dict(payload) if isinstance(payload, dict) else {},
                "source_entity": str(getattr(event, "source_entity", "") or ""),
                "sequence": int(getattr(event, "sequence", index)),
            }
        )
    rows.sort(key=lambda item: int(item.get("sequence", 0)))
    return rows


def _collect_mesh_history(window: Any | None, *, limit: int = 200) -> list[dict[str, Any]]:
    if window is None:
        return []
    bus = getattr(window, "event_bus", None)
    getter = getattr(bus, "get_recent_events", None) if bus is not None else None
    if not callable(getter):
        return []
    try:
        recent = list(getter(limit))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for index, event in enumerate(recent):
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        rows.append(
            {
                "event_type": str(event.get("name", "") or ""),
                "payload": dict(payload),
                "source_entity": str(payload.get("source", "") or ""),
            }
        )
    return rows


def _infer_hud_frame(window: Any | None) -> int:
    if window is None:
        return 0
    for key in ("frame_count", "_frame_count", "_mesh_frame_count", "_mesh_update_index"):
        value = getattr(window, key, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return 0


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_selected_entity_snapshot(editor: Any | None) -> dict[str, Any]:
    if editor is None:
        return {"entity_id": None, "behaviours": []}
    entity = getattr(editor, "selected_entity", None)
    entity_id = None
    if entity is not None:
        from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415

        entity_id = selected_entity_id(editor)
    if entity is None:
        return {"entity_id": entity_id, "behaviours": []}

    sections = build_entity_behaviour_summary(entity)
    section_rows: list[dict[str, Any]] = []
    for section in sections:
        rows = []
        for row in section.rows:
            rows.append(
                {
                    "kind": row.kind,
                    "key": row.key,
                    "label": row.label,
                    "value": row.value,
                    "value_type": row.value_type,
                }
            )
        section_rows.append(
            {
                "behaviour_name": section.behaviour_name,
                "behaviour_type": section.behaviour_type,
                "entity_id": section.entity_id,
                "is_expanded": bool(section.is_expanded),
                "rows": rows,
            }
        )
    section_rows.sort(key=lambda s: (s["behaviour_type"], s["behaviour_name"]))

    return {
        "entity_id": entity_id,
        "behaviours": section_rows,
    }
