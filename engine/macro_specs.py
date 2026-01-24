from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BuiltinMacroSpec:
    macro_id: str
    required_keys: tuple[str, ...]
    allowed_keys: tuple[str, ...]


BUILTIN_MACROS: tuple[BuiltinMacroSpec, ...] = (
    BuiltinMacroSpec(
        macro_id="macro.objective_zone",
        required_keys=("anchor", "zone_id", "set_flag", "radius"),
        allowed_keys=(
            "anchor",
            "zone_id",
            "set_flag",
            "radius",
            "toast",
            "toast_seconds",
            "require_flags",
            "forbid_flags",
        ),
    ),
    BuiltinMacroSpec(
        macro_id="macro.door_transition",
        required_keys=("anchor", "target_scene", "spawn_id"),
        allowed_keys=("anchor", "target_scene", "spawn_id", "require_flags", "forbid_flags"),
    ),
    BuiltinMacroSpec(
        macro_id="macro.dialogue_choice_flag",
        required_keys=("speaker_id", "choice_id", "choice_text", "set_flag"),
        allowed_keys=("speaker_id", "choice_id", "choice_text", "set_flag", "toast"),
    ),
)


def get_builtin_macro_spec(macro_id: str) -> BuiltinMacroSpec | None:
    wanted = str(macro_id or "").strip()
    if not wanted:
        return None
    for spec in BUILTIN_MACROS:
        if spec.macro_id == wanted:
            return spec
    return None


def list_builtin_macro_ids() -> tuple[str, ...]:
    return tuple(sorted({spec.macro_id for spec in BUILTIN_MACROS if spec.macro_id}))


def normalize_macro_id(value: Any) -> str:
    return str(value or "").strip()
