from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

_MISSING = object()

DEFAULT_OVERRIDE_IGNORE: set[str] = {
    "prefab_id",
    "variant_id",
    "id",
    "x",
    "y",
    "layer",
    "rotation",
    "scale",
    "mesh_name",
    "name",
}


@dataclass(frozen=True)
class FieldOverride:
    field_path: str
    base_value: Any
    override_value: Any


def _path(parts: Iterable[str]) -> str:
    return ".".join(parts)


def _iter_behaviour_overrides(
    entity_cfg: dict[str, Any],
    base_cfg: dict[str, Any],
) -> list[FieldOverride]:
    overrides: list[FieldOverride] = []
    for behaviour_name, params in entity_cfg.items():
        if not isinstance(behaviour_name, str):
            continue
        if not isinstance(params, dict):
            continue
        base_params = base_cfg.get(behaviour_name, {})
        if not isinstance(base_params, dict):
            base_params = {}
        for param_name, value in params.items():
            if not isinstance(param_name, str):
                continue
            base_value = base_params.get(param_name, _MISSING)
            if base_value is _MISSING or value != base_value:
                overrides.append(
                    FieldOverride(
                        field_path=_path(("behaviour_config", behaviour_name, param_name)),
                        base_value=None if base_value is _MISSING else base_value,
                        override_value=value,
                    )
                )
    return overrides


def compute_prefab_overrides(
    entity: dict[str, Any],
    prefab_base: dict[str, Any],
    *,
    ignore_fields: set[str] | None = None,
) -> list[FieldOverride]:
    ignore = DEFAULT_OVERRIDE_IGNORE if ignore_fields is None else set(ignore_fields)
    overrides: list[FieldOverride] = []

    base_entity = prefab_base or {}
    if not isinstance(base_entity, dict):
        base_entity = {}

    entity_cfg = entity.get("behaviour_config")
    base_cfg = base_entity.get("behaviour_config")
    if isinstance(entity_cfg, dict) and isinstance(base_cfg, dict):
        overrides.extend(_iter_behaviour_overrides(entity_cfg, base_cfg))
    elif isinstance(entity_cfg, dict):
        overrides.extend(_iter_behaviour_overrides(entity_cfg, {}))

    for key, value in entity.items():
        if key in ignore or key == "behaviour_config":
            continue
        base_value = base_entity.get(key, _MISSING)
        if base_value is _MISSING or value != base_value:
            overrides.append(
                FieldOverride(
                    field_path=_path((str(key),)),
                    base_value=None if base_value is _MISSING else base_value,
                    override_value=value,
                )
            )

    overrides.sort(key=lambda o: o.field_path)
    return overrides


def reset_prefab_override(
    entity: dict[str, Any],
    prefab_base: dict[str, Any],
    field_path: str,
    *,
    ignore_fields: set[str] | None = None,
) -> bool:
    ignore = DEFAULT_OVERRIDE_IGNORE if ignore_fields is None else set(ignore_fields)
    if not isinstance(field_path, str) or not field_path:
        return False

    base_entity = prefab_base or {}
    if not isinstance(base_entity, dict):
        base_entity = {}

    parts = field_path.split(".")
    if not parts:
        return False

    if parts[0] == "behaviour_config" and len(parts) >= 3:
        behaviour_name = parts[1]
        param_name = parts[2]
        entity_cfg = entity.get("behaviour_config")
        if not isinstance(entity_cfg, dict):
            return False
        params = entity_cfg.get(behaviour_name)
        if not isinstance(params, dict) or param_name not in params:
            return False
        base_cfg = base_entity.get("behaviour_config")
        base_value = _MISSING
        if isinstance(base_cfg, dict):
            base_params = base_cfg.get(behaviour_name)
            if isinstance(base_params, dict):
                base_value = base_params.get(param_name, _MISSING)
        if base_value is _MISSING:
            params.pop(param_name, None)
            if not params:
                entity_cfg.pop(behaviour_name, None)
        else:
            params[param_name] = base_value
        return True

    key = parts[0]
    if key in ignore:
        return False
    if key not in entity:
        return False
    base_value = base_entity.get(key, _MISSING)
    if base_value is _MISSING:
        entity.pop(key, None)
    else:
        entity[key] = base_value
    return True


def reset_all_prefab_overrides(
    entity: dict[str, Any],
    prefab_base: dict[str, Any],
    *,
    ignore_fields: set[str] | None = None,
) -> int:
    overrides = compute_prefab_overrides(entity, prefab_base, ignore_fields=ignore_fields)
    count = 0
    for override in overrides:
        if reset_prefab_override(entity, prefab_base, override.field_path, ignore_fields=ignore_fields):
            count += 1
    return count
