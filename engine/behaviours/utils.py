from __future__ import annotations

from typing import Any, Dict, List, Optional

from .registry import get_behaviour_info

BEHAVIOUR_META_EXPLICIT = "__explicit_behaviour_keys__"

TRIGGER_ZONE_CANONICAL = {"trigger_zone", "triggerzone"}
HITBOX_CANONICAL = {"hitbox"}
TRIGGER_ZONE_CLASSNAMES = {"TriggerZoneBehaviour"}
HITBOX_CLASSNAMES = {"Hitbox"}
ZONE_TARGET_TRIGGER = "trigger"
ZONE_TARGET_HITBOX = "hitbox"

def format_param_value(value: Any) -> str:
    """Helper to format values for console output."""
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)

def format_behaviour_config_summary(config: Any) -> str:
    if not isinstance(config, dict) or not config:
        return ""
    parts = []
    for key in sorted(config):
        parts.append(f"{key}={format_param_value(config[key])}")
    return f"({', '.join(parts)})"

def normalize_behaviour_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str):
        behaviour_type = entry.strip()
        if not behaviour_type:
            return None
        return {"type": behaviour_type, "params": {}}

    if isinstance(entry, dict):
        behaviour_type = str(entry.get("type", "")).strip()
        if not behaviour_type:
            return None
        params_source = entry.get("params")
        params: dict[str, Any] = {}
        if isinstance(params_source, dict):
            params.update(params_source)
        for key, value in entry.items():
            if key in {"type", "params", BEHAVIOUR_META_EXPLICIT}:
                continue
            params.setdefault(key, value)
        return {"type": behaviour_type, "params": params}

    return None

def prepare_behaviour_configs(
    behaviours: list[Any],
    include_metadata: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in behaviours:
        normalized = normalize_behaviour_entry(entry)
        if normalized is not None:
            results.append(normalized)
    return results

def strip_behaviour_metadata(config: dict[str, Any]) -> dict[str, Any]:
    if BEHAVIOUR_META_EXPLICIT in config:
        copy = dict(config)
        copy.pop(BEHAVIOUR_META_EXPLICIT, None)
        return copy
    return config

def prune_optional_behaviour_defaults(config: dict[str, Any]) -> dict[str, Any]:
    # Placeholder for future optimization
    return config

def build_behaviour_config_map(
    entity_data: dict[str, Any],
    behaviours: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    existing = entity_data.get("behaviour_config")
    if isinstance(existing, dict):
        for key, value in existing.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, dict):
                merged[key] = dict(value)
            else:
                merged[key] = {}

    for entry in behaviours:
        behaviour_type = entry.get("type")
        if not isinstance(behaviour_type, str):
            continue
        params = entry.get("params")
        if isinstance(params, dict) and params:
            target = merged.setdefault(behaviour_type, {})
            target.update(params)

        info = get_behaviour_info(behaviour_type)
        if info and info.config_fields:
            for field in info.config_fields:
                field_name = field.get("name")
                if not field_name:
                    continue
                target = merged.get(behaviour_type)
                if isinstance(target, dict) and field_name in target:
                    continue
                if field_name in entity_data:
                    target = merged.setdefault(behaviour_type, {})
                    target[field_name] = entity_data[field_name]

    return merged

def ensure_behaviour_config_root(entity_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = entity_data.get("behaviour_config")
    if not isinstance(root, dict):
        root = {}
        entity_data["behaviour_config"] = root
        return root

    invalid_keys: list[Any] = []
    for key, value in root.items():
        if not isinstance(key, str):
            invalid_keys.append(key)
            continue
        if not isinstance(value, dict):
            root[key] = {}
    for key in invalid_keys:
        root.pop(key, None)
    return root

def is_trigger_behaviour(behaviour: Any) -> bool:
    behaviour_type = getattr(behaviour, "mesh_behaviour_type", None)
    canonical = str(behaviour_type or "").lower().replace("-", "_")
    class_name = behaviour.__class__.__name__
    return canonical in TRIGGER_ZONE_CANONICAL or class_name in TRIGGER_ZONE_CLASSNAMES

def is_hitbox_behaviour(behaviour: Any) -> bool:
    behaviour_type = getattr(behaviour, "mesh_behaviour_type", None)
    canonical = str(behaviour_type or "").lower().replace("-", "_")
    class_name = behaviour.__class__.__name__
    return canonical in HITBOX_CANONICAL or class_name in HITBOX_CLASSNAMES

def infer_zone_target_from_behaviour(behaviour: Any) -> str:
    if behaviour is None:
        return ZONE_TARGET_TRIGGER
    if is_hitbox_behaviour(behaviour):
        return ZONE_TARGET_HITBOX
    return ZONE_TARGET_TRIGGER

def describe_zone_behaviour(behaviour: Any) -> str:
    if behaviour is None:
        return "Zone"
    label = getattr(behaviour, "mesh_behaviour_type", None) or behaviour.__class__.__name__
    if label.endswith("Behaviour"):
        label = label[:-9]
    label = label.replace("_", " ").strip()
    return label or "Zone"

def parse_flag_list(text: str) -> list[str]:
    entries = []
    for chunk in str(text or "").split(","):
        cleaned = chunk.strip()
        if cleaned:
            entries.append(cleaned)
    return entries
