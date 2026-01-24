from __future__ import annotations

from typing import Any, Iterable


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
    auto_start = bool(data.get("auto_start", False))
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
        normalized.append(
            {
                "id": stage_id,
                "title": title,
                "text": text,
                "index": index,
                "start_event": start_trigger,
                "complete_event": complete_trigger,
                "requirements": requirements,
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
    return {"set_flags": set_flags, "inc_counters": inc_counters}

