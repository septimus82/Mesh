from __future__ import annotations

import os
from typing import Any

from engine.persistence_io import SAVE_FORMAT_VERSION


def dump_state(window: Any, *, flags_sample_limit: int = 10) -> dict[str, Any]:
    """Return a deterministic debug snapshot of key runtime state.

    Intended for debugging and tests; output is stable when the underlying state is stable.
    """
    preset_id = os.environ.get("MESH_ACTIVE_PRESET") or None

    engine_cfg = getattr(window, "engine_config", None)
    world_file = getattr(engine_cfg, "world_file", None) if engine_cfg is not None else None

    world_controller = getattr(window, "world_controller", None)
    world_id = getattr(world_controller, "id", None) if world_controller is not None else None

    scene_controller = getattr(window, "scene_controller", None)
    scene_path = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None

    gs_controller = getattr(window, "game_state_controller", None)
    state = getattr(gs_controller, "state", None) if gs_controller is not None else None

    counters = getattr(state, "counters", {}) if state is not None else {}
    flags = getattr(state, "flags", {}) if state is not None else {}

    gold_raw = counters.get("gold", 0) if isinstance(counters, dict) else 0
    try:
        gold = int(gold_raw)
    except (TypeError, ValueError):
        gold = 0

    flags_true: list[str] = []
    if isinstance(flags, dict):
        flags_true = sorted(str(k) for k, v in flags.items() if bool(v) and str(k).strip())

    last_zone_id = None
    if gs_controller is not None and hasattr(gs_controller, "get_var"):
        try:
            last_zone_id = gs_controller.get_var("last_zone_id", None)
        except Exception:
            last_zone_id = None
    last_zone_id = str(last_zone_id).strip() if last_zone_id is not None else None
    if last_zone_id == "":
        last_zone_id = None

    active_quest_ids: list[str] = []

    # Prefer runtime QuestManager (engine/quests.py) if present.
    qm = getattr(window, "quest_manager", None)
    if qm is not None and hasattr(qm, "list_active_quests"):
        try:
            entries = qm.list_active_quests()
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    status = str(entry.get("status", "")).strip().lower()
                    if status != "active":
                        continue
                    qid = str(entry.get("id", "")).strip()
                    if qid:
                        active_quest_ids.append(qid)
        except Exception:
            active_quest_ids = []
    else:
        # Fallback to lightweight quest tracker embedded in GameStateController.
        quests = getattr(gs_controller, "quests", None)
        if quests is not None and hasattr(quests, "list_active_quests"):
            try:
                entries = quests.list_active_quests()
                if isinstance(entries, list):
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        status = str(entry.get("status", "")).strip().lower()
                        if status != "active":
                            continue
                        qid = str(entry.get("id", "")).strip()
                        if qid:
                            active_quest_ids.append(qid)
            except Exception:
                active_quest_ids = []

    active_quest_ids = sorted(set(active_quest_ids))

    sample_limit = max(0, int(flags_sample_limit))
    flags_sample = flags_true[:sample_limit]

    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "preset_id": preset_id,
        "world_file": str(world_file) if world_file else None,
        "world_id": str(world_id) if world_id else None,
        "scene_path": str(scene_path) if scene_path else None,
        "gold": gold,
        "flags_count": len(flags_true),
        "flags_sample": flags_sample,
        "last_zone_id": last_zone_id,
        "active_quest_ids": active_quest_ids,
    }
