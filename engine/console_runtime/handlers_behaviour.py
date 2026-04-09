"""Behaviour-related console command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from engine.behaviours import (
    get_behaviour_info,
    get_behaviour_param_defs,
    reload_behaviour_modules,
)
from engine.console_runtime.handlers_entity import resolve_entity_reference
from engine.console_runtime.utils import (
    format_param_value,
    param_kind_from_def,
    parse_value_for_kind,
    suggest_param_name,
)

if TYPE_CHECKING:
    import arcade

    SpriteType = arcade.Sprite
else:
    SpriteType = Any


# ---------------------------------------------------------------------------
# Dispatch-compatible handlers  (controller, args) -> bool
# ---------------------------------------------------------------------------

def handle_beh(controller: Any, args: list[str]) -> bool:
    """Top-level ``beh`` command."""
    usage = (
        "Usage: beh list [ref] | beh get <ref> <behaviour> <param> | "
        "beh set <ref> <behaviour> <param> <value>"
    )
    if not args:
        _beh_list_all(controller)
        return True

    action = args[0].lower()
    if action == "list":
        if len(args) >= 2:
            _beh_list_entity(controller, args[1])
        else:
            _beh_list_all(controller)
        return True

    if action == "get":
        if len(args) < 4:
            controller.log("Usage: beh get <ref> <behaviour> <param>")
            return True
        _beh_get(controller, args[1], args[2], args[3])
        return True

    if action == "set":
        if len(args) < 5:
            controller.log("Usage: beh set <ref> <behaviour> <param> <value>")
            return True
        ref = args[1]
        behaviour_ref = args[2]
        param = args[3]
        value = " ".join(args[4:])
        entity_beh_set(controller, ref, behaviour_ref, param, value)
        return True

    controller.log(usage)
    return True


def handle_behaviours(controller: Any, _args: list[str]) -> bool:
    """``behaviours`` — list registered behaviours."""
    from engine.behaviours import list_behaviours

    controller.log("Registered Behaviours:")
    for name in list_behaviours():
        controller.log(f"  - {name}")
    return True


def handle_behaviour_detail(controller: Any, args: list[str]) -> bool:
    """``behaviour <name>`` — show detail for a single behaviour."""
    if not args:
        controller.log("Usage: behaviour <name>")
        return True
    name = args[0]
    info = get_behaviour_info(name)
    if not info:
        controller.log(f"Behaviour '{name}' not found")
        return True
    controller.log(f"Behaviour: {name}")
    controller.log(f"  Description: {info.description or '<none>'}")
    controller.log("  Params:")
    for field in info.config_fields:
        fname = field.get("name")
        ftype = field.get("type")
        fdefault = field.get("default")
        controller.log(f"    - {fname} ({ftype}) default={fdefault}")
    return True


def handle_reload_behaviours(controller: Any, _args: list[str]) -> bool:
    """``reload_behaviours`` — hot-reload behaviour modules."""
    try:
        reloaded = reload_behaviour_modules()
    except Exception as exc:  # noqa: BLE001  # REASON: behaviour hot-reload failures should be reported without breaking the console command loop
        controller.window.scene_controller._hot_reload_log(f"Behaviour reload failed: {exc}")
        return True
    controller.window.scene_controller._hot_reload_log(
        f"Reloaded {reloaded} behaviour module(s). Run `reload_scene` to apply new logic."
    )
    return True


# ---------------------------------------------------------------------------
# ``entity beh`` sub-commands (called from handlers_entity)
# ---------------------------------------------------------------------------

def entity_beh_command(controller: Any, args: list[str]) -> None:
    """Dispatch ``entity beh <action> ...``."""
    usage = (
        "Usage: entity beh list <ref> | entity beh set <ref> <behaviour> <field> <value> | "
        "entity beh reload <ref>"
    )
    if not args:
        controller.log(usage)
        return

    action = args[0].lower()
    if action == "list":
        if len(args) < 2:
            controller.log("Usage: entity beh list <ref>")
            return
        _entity_beh_list(controller, args[1])
        return

    if action == "set":
        if len(args) < 5:
            controller.log("Usage: entity beh set <ref> <behaviour> <field> <value>")
            return
        ref = args[1]
        behaviour_ref = args[2]
        field_name = args[3]
        raw_value = " ".join(args[4:])
        entity_beh_set(controller, ref, behaviour_ref, field_name, raw_value)
        return

    if action == "reload":
        if len(args) < 2:
            controller.log("Usage: entity beh reload <ref>")
            return
        _entity_beh_reload(controller, args[1])
        return

    controller.log(usage)


# ---------------------------------------------------------------------------
# Shared implementation used by both ``beh set`` and ``entity beh set``
# ---------------------------------------------------------------------------

def entity_beh_set(
    controller: Any,
    ref: str,
    behaviour_ref: str,
    field_name: str,
    raw_value: str,
) -> None:
    """Set a behaviour parameter on an entity."""
    sprite, index, _ = resolve_entity_reference(controller, ref)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{ref}'")
        return

    behaviour_name, behaviour_index = _resolve_sprite_behaviour(sprite, behaviour_ref)
    if behaviour_name is None or behaviour_index is None:
        controller.log(f"No behaviour '{behaviour_ref}' on entity [{index}]")
        return

    param_defs = get_behaviour_param_defs(behaviour_name)
    spec = param_defs.get(field_name)
    info = get_behaviour_info(behaviour_name)
    info_fields: dict[str, dict[str, Any]] = {}
    if info is not None:
        info_fields = {
            str(field.get("name")): field
            for field in info.config_fields
            if isinstance(field, dict) and field.get("name")
        }
    if spec is None and field_name not in info_fields:
        suggestion = suggest_param_name(
            field_name,
            list(param_defs.keys()) + list(info_fields.keys()),
        )
        warning = (
            f"Warning: behaviour '{behaviour_name}' does not declare a param named '{field_name}'"
        )
        if suggestion:
            warning += f" (did you mean '{suggestion}'?)"
        controller.log(warning)

    value = _coerce_behaviour_field_input(behaviour_name, field_name, raw_value)
    value_repr = format_param_value(value)
    if spec is not None:
        kind_detail = f" [{param_kind_from_def(spec.type)}]"
    elif field_name in info_fields:
        field_spec = info_fields[field_name]
        field_type = str(field_spec.get("type", "string"))
        kind_detail = f" [{field_type}]"
    else:
        kind_detail = ""

    entity_data = controller.window.scene_controller._ensure_entity_data_dict(sprite)
    config_root = controller.window.scene_controller._ensure_behaviour_config_root(entity_data)
    behaviour_config = config_root.setdefault(behaviour_name, {})
    behaviour_config[field_name] = value
    entity_data["behaviour_config"] = config_root

    entries = controller.window.scene_controller._get_behaviour_configs_for_sprite(sprite)
    if 0 <= behaviour_index < len(entries):
        params_bucket = entries[behaviour_index].setdefault("params", {})
        if isinstance(params_bucket, dict):
            params_bucket[field_name] = value
        entity_data["behaviours"] = entries
        setattr(sprite, "mesh_behaviour_configs", entries)

    entity_data[field_name] = value

    updated_runtime = _apply_behaviour_runtime_update(
        sprite,
        behaviour_index,
        field_name,
        value,
    )

    if updated_runtime:
        controller.log(
            f"Entity [{index}] behaviour '{behaviour_name}' field '{field_name}' set to {value_repr}{kind_detail}"
        )
    else:
        controller.log(
            f"Updated config for behaviour '{behaviour_name}' field '{field_name}' = {value_repr}{kind_detail}. "
            "Use 'entity beh reload' to apply runtime changes if needed",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_sprite_behaviour(
    sprite: SpriteType,
    reference: str,
) -> tuple[str | None, int | None]:
    behaviours = [
        str(name)
        for name in getattr(sprite, "mesh_behaviours", [])
        if isinstance(name, str)
    ]
    if not behaviours:
        return None, None

    try:
        idx = int(reference)
    except (TypeError, ValueError):
        idx = None

    if idx is not None and 0 <= idx < len(behaviours):
        return behaviours[idx], idx

    lowered = reference.strip().lower()
    for position, name in enumerate(behaviours):
        if name.lower() == lowered:
            return name, position

    return None, None


def _beh_list_all(controller: Any) -> None:
    sprites = list(controller.window.scene_controller.all_sprites)
    if not sprites:
        controller.log("No entities loaded")
        return
    controller.log("Behaviour parameters:")
    for idx, sprite in enumerate(sprites):
        behaviours = getattr(sprite, "mesh_behaviours", [])
        if not behaviours:
            continue
        label = getattr(sprite, "mesh_name", None) or "<unnamed>"
        controller.log(f"  [{idx}] {label}:")
        _print_behaviour_params(controller, sprite, behaviours)


def _beh_list_entity(controller: Any, ref: str) -> None:
    sprite, index, _ = resolve_entity_reference(controller, ref)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{ref}'")
        return
    behaviours = getattr(sprite, "mesh_behaviours", [])
    if not behaviours:
        controller.log(f"Entity [{index}] has no behaviours")
        return
    label = getattr(sprite, "mesh_name", None) or "<unnamed>"
    controller.log(f"Behaviours for [{index}] {label}:")
    _print_behaviour_params(controller, sprite, behaviours)


def _beh_get(controller: Any, ref: str, behaviour_ref: str, field: str) -> None:
    sprite, index, _ = resolve_entity_reference(controller, ref)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{ref}'")
        return
    behaviour_name, _ = _resolve_sprite_behaviour(sprite, behaviour_ref)
    if behaviour_name is None:
        controller.log(f"No behaviour '{behaviour_ref}' on entity [{index}]")
        return
    entity_data = controller.window.scene_controller._ensure_entity_data_dict(sprite)
    config_root = controller.window.scene_controller._ensure_behaviour_config_root(entity_data)
    behaviour_config = config_root.get(behaviour_name, {})
    if not isinstance(behaviour_config, dict):
        behaviour_config = {}

    param_defs = get_behaviour_param_defs(behaviour_name)
    spec = param_defs.get(field)
    explicit = field in behaviour_config

    if explicit:
        value = behaviour_config[field]
        state = "set"
    elif spec is not None:
        value = spec.default
        state = "default"
    else:
        value = "<unset>"
        state = "unset"

    value_repr = format_param_value(value)
    if spec is not None:
        kind = param_kind_from_def(spec.type)
        detail = f"[{kind}; {state}]"
    elif explicit:
        detail = "[custom]"
    else:
        detail = "[unknown]"

    controller.log(
        f"Entity [{index}] behaviour '{behaviour_name}' param '{field}' = {value_repr} {detail}"
    )


def _entity_beh_list(controller: Any, ref: str) -> None:
    sprite, index, _ = resolve_entity_reference(controller, ref)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{ref}'")
        return

    behaviours = [str(name) for name in getattr(sprite, "mesh_behaviours", []) if name]
    if not behaviours:
        controller.log(f"Entity [{index}] has no behaviours")
        return

    entity_data = controller.window.scene_controller._ensure_entity_data_dict(sprite)
    controller.window.scene_controller._ensure_behaviour_config_root(entity_data)
    label = getattr(sprite, "mesh_name", None) or "<unnamed>"
    controller.log(f"Behaviours for [{index}] {label}:")
    _print_behaviour_params(controller, sprite, behaviours)


def _entity_beh_reload(controller: Any, ref: str) -> None:
    sprite, index, _ = resolve_entity_reference(controller, ref)
    if sprite is None or index is None:
        controller.log(f"No entity found for '{ref}'")
        return
    controller.window.scene_controller._rebuild_behaviours_for_sprite(sprite)
    controller.log(f"Reloaded behaviours for entity [{index}]")


def _print_behaviour_params(
    controller: Any,
    sprite: SpriteType,
    behaviours: Sequence[str],
) -> None:
    entity_data = controller.window.scene_controller._ensure_entity_data_dict(sprite)
    config_root = controller.window.scene_controller._ensure_behaviour_config_root(entity_data)
    for index, behaviour_name in enumerate(behaviours):
        overrides = config_root.get(behaviour_name)
        if not isinstance(overrides, dict):
            overrides = {}
        lines = _describe_behaviour_params(behaviour_name, overrides)
        header = f"    - [{index}] {behaviour_name}"
        if lines:
            controller.log(f"{header}:")
            for line in lines:
                controller.log(f"        {line}")
        else:
            controller.log(f"{header}: <no params>")


def _describe_behaviour_params(
    behaviour_name: str,
    overrides: dict[str, Any],
) -> list[str]:
    param_defs = get_behaviour_param_defs(behaviour_name)
    lines: list[str] = []

    for name in sorted(param_defs.keys()):
        spec = param_defs[name]
        explicit = name in overrides
        value = overrides[name] if explicit else spec.default
        kind = param_kind_from_def(spec.type)
        state = "set" if explicit else "default"
        value_repr = format_param_value(value)
        lines.append(f"{name} = {value_repr} [{kind}; {state}]")

    custom_names = sorted(name for name in overrides.keys() if name not in param_defs)
    for name in custom_names:
        value_repr = format_param_value(overrides[name])
        lines.append(f"{name} = {value_repr} [custom]")

    return lines


def _coerce_behaviour_field_input(
    behaviour_name: str,
    field_name: str,
    raw_value: str,
) -> Any:
    param_defs = get_behaviour_param_defs(behaviour_name)
    spec = param_defs.get(field_name)
    if spec is not None:
        expected = param_kind_from_def(spec.type)
    else:
        info = get_behaviour_info(behaviour_name)
        expected = "string"
        if info is not None:
            for field in info.config_fields:
                if field.get("name") == field_name:
                    expected = str(field.get("type", "string")).lower()
                    break

    return parse_value_for_kind(expected, raw_value)


def _apply_behaviour_runtime_update(
    sprite: SpriteType,
    behaviour_index: int,
    field_name: str,
    value: Any,
) -> bool:
    runtime_behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
    if not isinstance(runtime_behaviours, list):
        return False
    if not (0 <= behaviour_index < len(runtime_behaviours)):
        return False

    behaviour = runtime_behaviours[behaviour_index]
    updated = False
    config = getattr(behaviour, "config", None)
    if isinstance(config, dict):
        config[field_name] = value
        updated = True

    if hasattr(behaviour, field_name):
        setattr(behaviour, field_name, value)
        updated = True

    hook = getattr(behaviour, "on_config_updated", None)
    if callable(hook):
        try:
            hook(field_name, value)
            updated = True
        except Exception as exc:  # noqa: BLE001  # REASON: runtime config hooks are optional and should not block config updates when they fail
            # Can't call controller.log here (no controller ref), but the caller
            # will report success/failure based on return value.
            _ = exc
    return updated
