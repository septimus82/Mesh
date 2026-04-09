"""Behaviour registry that maps string identifiers to implementations."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Type, TypeVar

from .base import Behaviour, ParamDef

_B = TypeVar("_B", bound=Behaviour)

_MISSING = object()
_ALLOWED_TYPES = {"float", "int", "bool", "string", "array", "object"}


@dataclass(slots=True)
class BehaviourInfo:
    """Describes a registered behaviour and its configuration surface."""

    name: str
    description: str
    config_fields: List[dict[str, Any]] = field(default_factory=list)


BEHAVIOUR_REGISTRY: Dict[str, Type[Behaviour]] = {}
_BEHAVIOUR_INFO: Dict[str, BehaviourInfo] = {}
_NAME_ALIASES: Dict[str, str] = {}
BEHAVIOUR_PARAM_DEFS: Dict[str, Dict[str, ParamDef]] = {}


def _default_for_type(kind: str) -> Any:
    if kind == "float":
        return 0.0
    if kind == "int":
        return 0
    if kind == "bool":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return ""


def _normalize_field_spec(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        name = entry.get("name")
        if not name:
            return None
        spec = dict(entry)
    elif isinstance(entry, (tuple, list)):
        if not entry:
            return None
        spec = {
            "name": entry[0],
            "description": entry[1] if len(entry) >= 2 else "",
        }
        if len(entry) >= 3:
            spec["type"] = entry[2]
        if len(entry) >= 4:
            spec["default"] = entry[3]
    else:
        spec = {"name": str(entry), "description": ""}

    name_value = str(spec.get("name", "")).strip()
    if not name_value:
        return None

    field_type = str(spec.get("type", "string")).strip().lower()
    if field_type not in _ALLOWED_TYPES:
        field_type = "string"
    spec["name"] = name_value
    spec["type"] = field_type
    if "description" in spec and spec["description"] is None:
        spec["description"] = ""
    if "default" not in spec:
        spec["default"] = _default_for_type(field_type)
    return spec


def normalize_config(
    schema: Iterable[dict[str, Any]] | None,
    provided: Optional[dict[str, Any]] = None,
    *,
    fill_defaults: bool = True,
) -> dict[str, Any]:
    """Coerce provided config against the schema, keeping unknown keys."""

    normalized: dict[str, Any] = {}
    incoming = dict(provided or {})
    incoming.pop("type", None)

    for field_def in schema or []:
        name = field_def.get("name")
        if not name:
            continue
        kind = str(field_def.get("type", "string")).lower()
        if kind not in _ALLOWED_TYPES:
            kind = "string"
        default = field_def.get("default", _default_for_type(kind))
        raw_value = incoming.pop(name, _MISSING)
        if raw_value is _MISSING:
            if not fill_defaults:
                continue
            value = default
        else:
            value = _coerce_field_value(raw_value, kind, default)
        normalized[name] = value

    for key, value in incoming.items():
        normalized[key] = value

    return normalized


def _coerce_field_value(value: Any, kind: str, default: Any) -> Any:
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)
    if kind == "bool":
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return bool(value)
    if kind == "array":
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            return [entry.strip() for entry in value.split(",") if entry.strip()]
        return list(default) if isinstance(default, list) else []
    if kind == "object":
        if isinstance(value, dict):
            return dict(value)
        return dict(default) if isinstance(default, dict) else {}
    if value is None:
        return default if default is not None else ""
    if isinstance(value, (dict, list, tuple)):
        return value
    return str(value)


def register_behaviour(
    name: str,
    *,
    description: str,
    config_fields: Iterable[Any] | None = None,
) -> Callable[[Type[_B]], Type[_B]]:
    """Decorator that registers a behaviour class along with metadata."""

    def decorator(cls: Type[_B]) -> Type[_B]:
        canonical = name.strip()
        BEHAVIOUR_REGISTRY[canonical] = cls
        _NAME_ALIASES[canonical.lower()] = canonical

        param_defs = _extract_param_defs(cls)
        BEHAVIOUR_PARAM_DEFS[canonical] = param_defs

        parsed_fields: list[dict[str, Any]] = []
        if config_fields:
            for entry in config_fields:
                spec = _normalize_field_spec(entry)
                if spec is not None:
                    parsed_fields.append(spec)
        elif param_defs:
            for field_name, param in param_defs.items():
                parsed_fields.append(_field_spec_from_param(field_name, param))

        info = BehaviourInfo(
            name=canonical,
            description=description.strip(),
            config_fields=parsed_fields,
        )
        _BEHAVIOUR_INFO[canonical] = info
        return cls

    return decorator


def register(name: str) -> Callable[[Type[_B]], Type[_B]]:
    """Legacy decorator retained for backwards compatibility."""

    return register_behaviour(name, description=f"{name} behaviour")


def create_behaviour(
    name: str | None,
    entity,
    window,
    *,
    config: Optional[dict[str, Any]] = None,
    fill_defaults: bool = True,
) -> Optional[Behaviour]:
    """Instantiate a registered behaviour class by name."""

    if not name:
        print("[Mesh][Behaviour] WARNING: Empty behaviour name encountered")
        return None

    canonical = _NAME_ALIASES.get(name.lower())
    if canonical is None:
        print(f"[Mesh][Behaviour] WARNING: Unknown behaviour '{name}'")
        return None

    cls = BEHAVIOUR_REGISTRY.get(canonical)
    if cls is None:
        print(f"[Mesh][Behaviour] WARNING: No implementation for '{canonical}'")
        return None

    info = _BEHAVIOUR_INFO.get(canonical)
    normalized_config = normalize_config(
        info.config_fields if info else [],
        config or {},
        fill_defaults=fill_defaults,
    )

    try:
        instance = cls(entity, window, **normalized_config)
    except TypeError as exc:
        print(
            f"[Mesh][Behaviour] INFO: '{canonical}' does not accept config kwargs,"
            f" falling back without them ({exc})",
        )
        try:
            instance = cls(entity, window)
        except Exception as inner_exc:  # noqa: BLE001  # REASON: legacy no-config fallback should report constructor failures without breaking scene load
            print(f"[Mesh][Behaviour] ERROR: Failed to instantiate '{canonical}': {inner_exc}")
            return None
    except Exception as exc:  # noqa: BLE001  # REASON: behaviour constructor failures should be reported without breaking scene load
        print(f"[Mesh][Behaviour] ERROR: Failed to instantiate '{canonical}': {exc}")
        return None

    if instance is not None:
        setattr(instance, "config", dict(normalized_config))
    return instance

def reset_behaviour_registry() -> None:
    """Clear all registry metadata prior to a full reload."""

    BEHAVIOUR_REGISTRY.clear()
    _BEHAVIOUR_INFO.clear()
    _NAME_ALIASES.clear()
    BEHAVIOUR_PARAM_DEFS.clear()


def reload_behaviour_modules() -> int:
    """Reload all behaviour modules and rebuild the registry."""

    try:
        behaviours_pkg = importlib.import_module("engine.behaviours")
    except ImportError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Failed to import behaviour package: {exc}") from exc

    module_prefix = behaviours_pkg.__name__ + "."
    module_names = [
        name
        for _, name, _ in pkgutil.walk_packages(behaviours_pkg.__path__, module_prefix)
        if not name.endswith(".__pycache__")
    ]

    reset_behaviour_registry()
    reloaded = 0
    for module_name in module_names:
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            reloaded += 1
        except Exception as exc:  # noqa: BLE001  # REASON: module reload failures should identify the bad behaviour module without hiding the reload loop failure
            raise RuntimeError(f"Failed to reload '{module_name}': {exc}") from exc

    try:
        importlib.reload(behaviours_pkg)
    except Exception as exc:  # noqa: BLE001  # REASON: package reload failures should surface with behaviour package context
        raise RuntimeError(f"Behaviour package reload failed: {exc}") from exc

    return reloaded


def list_behaviours() -> list[BehaviourInfo]:
    """Return a sorted list of registered behaviour metadata."""

    return sorted(_BEHAVIOUR_INFO.values(), key=lambda info: info.name.lower())


def get_behaviour_info(name: str | None) -> BehaviourInfo | None:
    """Retrieve metadata for a single behaviour, case-insensitive."""

    if not name:
        return None
    canonical = _NAME_ALIASES.get(name.lower())
    if canonical is None:
        return None
    return _BEHAVIOUR_INFO.get(canonical)


def get_behaviour_param_defs(name: str | None) -> dict[str, ParamDef]:
    """Return ParamDef entries for a behaviour, if available."""

    if not name:
        return {}
    canonical = _NAME_ALIASES.get(name.lower())
    if canonical is None:
        return {}
    return BEHAVIOUR_PARAM_DEFS.get(canonical, {})


def _extract_param_defs(cls: Type[Behaviour]) -> dict[str, ParamDef]:
    if not hasattr(cls, "param_defs"):
        return {}
    try:
        defs = cls.param_defs()
    except Exception:  # pragma: no cover - defensive
        return {}
    if not isinstance(defs, dict):
        return {}
    normalized: dict[str, ParamDef] = {}
    for name, definition in defs.items():
        if isinstance(definition, ParamDef):
            normalized[name] = definition
        elif isinstance(definition, dict):
            normalized[name] = ParamDef(
                type=definition.get("type", str),
                default=definition.get("default"),
                description=definition.get("description", ""),
            )
    return normalized


def _field_spec_from_param(name: str, param: ParamDef) -> dict[str, Any]:
    return {
        "name": name,
        "description": param.description,
        "type": _param_type_to_schema(param.type),
        "default": _default_for_param(param),
    }


def _param_type_to_schema(expected: type | str | None) -> str:
    if expected in {int, "int"}:
        return "int"
    if expected in {float, "float"}:
        return "float"
    if expected in {bool, "bool"}:
        return "bool"
    if expected in {list, tuple, "array"}:
        return "array"
    if expected in {dict, "object"}:
        return "object"
    return "string"


def _default_for_param(param: ParamDef) -> Any:
    default = param.default
    if isinstance(default, (dict, list, set)):
        return default.copy()
    return default
