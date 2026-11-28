from __future__ import annotations

import math
from typing import Any

REWARD_AMOUNT_KEYS = ("gold", "xp")
REWARD_KEYS = frozenset({"set_flags", "inc_counters", *REWARD_AMOUNT_KEYS})


def quest_entries(quests_root: Any) -> list[dict[str, Any]]:
    """Raw quest dicts from a quests.json ``"quests"`` value (list or dict form), same id rule as the loader.

    Dict form ``{"<key>": {...}}``: an entry without its own "id" gets the key as id; an inner "id" wins.
    List entries are returned as they are. Non-dict entries are skipped.
    """
    if isinstance(quests_root, dict):
        rows = [
            {**raw, "id": key} if not str(raw.get("id", "")).strip() else raw
            for key, raw in quests_root.items()
            if isinstance(raw, dict)
        ]
        return rows
    if isinstance(quests_root, list):
        return [raw for raw in quests_root if isinstance(raw, dict)]
    return []


def normalize_quest(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    quest_id = str(data.get("id", "")).strip()
    if not quest_id:
        return None
    title = str(data.get("title") or quest_id).strip()
    description = str(data.get("description") or "").strip()
    start_toast = str(data.get("start_toast") or "").strip() or None
    complete_toast = str(data.get("complete_toast") or "").strip() or None
    requires_flags_raw = data.get("requires_flags")
    blocks_flags_raw = data.get("blocks_flags")
    requires_flags = (
        [flag.strip() for flag in requires_flags_raw if isinstance(flag, str) and flag.strip()]
        if isinstance(requires_flags_raw, list)
        else []
    )
    blocks_flags = (
        [flag.strip() for flag in blocks_flags_raw if isinstance(flag, str) and flag.strip()]
        if isinstance(blocks_flags_raw, list)
        else []
    )
    # Tri-state: True / False (explicit) / None (absent: legacy implicit start when the first stage has no trigger).
    auto_start = bool(data["auto_start"]) if "auto_start" in data else None
    stages = normalize_stages(data.get("stages"))
    if not stages:
        print(f"[Mesh][Quests] Quest '{quest_id}' has no stages; skipping")
        return None
    reward = normalize_reward(data.get("reward"))
    quest = {
        "id": quest_id,
        "title": title,
        "description": description,
        "start_toast": start_toast,
        "complete_toast": complete_toast,
        "requires_flags": requires_flags,
        "blocks_flags": blocks_flags,
        "auto_start": auto_start,
        "stages": stages,
        "stage_lookup": {stage["id"]: stage for stage in stages},
        "reward": reward,
    }
    return quest


def normalize_stages(root: Any) -> list[dict[str, Any]]:
    candidates: list[Any]
    if isinstance(root, dict):
        candidates = list(root.values())
    elif isinstance(root, list):
        candidates = root
    else:
        return []
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(candidates):
        if not isinstance(entry, dict):
            continue
        stage_id = str(entry.get("id") or f"stage_{index}").strip()
        if not stage_id:
            continue
        title = str(entry.get("title") or stage_id).strip()
        text = str(
            entry.get("text")
            or entry.get("description")
            or entry.get("log_text")
            or title,
        ).strip()
        start_trigger = normalize_event_trigger(
            entry.get("start_on_event")
            or entry.get("start_event")
            or entry.get("start_on"),
        )
        complete_trigger = normalize_event_trigger(
            entry.get("complete_on")
            or entry.get("complete_event")
            or entry.get("complete_when"),
        )
        requirements = normalize_requirements(
            entry.get("requirements")
            or entry.get("reqs")
            or entry.get("conditions"),
        )
        # Preserve emit_events_on_complete for QuestRunner
        emit_events = entry.get("emit_events_on_complete", [])
        if not isinstance(emit_events, list):
            emit_events = []
        normalized.append(
            {
                "id": stage_id,
                "title": title,
                "text": text,
                "index": index,
                "start_event": start_trigger,
                "complete_event": complete_trigger,
                "requirements": requirements,
                "emit_events_on_complete": emit_events,
            },
        )
    return normalized

def normalize_event_trigger(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        event_type = value.strip()
        if not event_type:
            return None
        return {"type": event_type, "payload": {}}
    if not isinstance(value, dict):
        return None
    event_type = str(value.get("type") or value.get("event") or "").strip()
    if not event_type:
        return None
    trigger: dict[str, Any] = {"type": event_type}
    payload = value.get("payload")
    if isinstance(payload, dict):
        trigger["payload"] = dict(payload)
    payload_field = str(value.get("payload_field") or "").strip()
    if payload_field:
        trigger["payload_field"] = payload_field
        if "payload_value" in value:
            trigger["payload_value"] = value.get("payload_value")
    for key, val in value.items():
        if key in {"type", "event", "payload", "payload_field", "payload_value"}:
            continue
        if key.startswith("payload_"):
            continue
        trigger.setdefault("payload", {})[key] = val
    return trigger


def normalize_requirements(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    flags = {}
    for key, value in (data.get("flags") or {}).items():
        name = str(key or "").strip()
        if name:
            flags[name] = bool(value)
    counters = {}
    for key, value in (data.get("counters") or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            counters[name] = float(value)
        except (TypeError, ValueError):
            continue
    return {"flags": flags, "counters": counters}


def normalize_reward(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"set_flags": {}, "inc_counters": {}}
    set_flags = {}
    for key, value in (data.get("set_flags") or {}).items():
        name = str(key or "").strip()
        if name:
            set_flags[name] = bool(value)
    inc_counters = {}
    for key, value in (data.get("inc_counters") or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            inc_counters[name] = float(value)
        except (TypeError, ValueError):
            continue
    reward: dict[str, Any] = {"set_flags": set_flags, "inc_counters": inc_counters}
    # gold / xp: paid by complete_quest (#755: they were validated, then dropped here). Kept only when present,
    # so a reward without them normalizes as before.
    for key in REWARD_AMOUNT_KEYS:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            reward[key] = value
        else:
            print(f"[Mesh][Quests] Ignoring reward.{key} {value!r}: it must be a finite number of 0 or more")
    unknown = sorted(str(key) for key in data if key not in REWARD_KEYS)
    if unknown:
        print(f"[Mesh][Quests] Ignoring unknown reward field(s) {unknown}; supported: {sorted(REWARD_KEYS)}")
    return reward

