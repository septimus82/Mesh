from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def can_activate_quest(flags: Mapping[str, bool] | Callable[[str, bool], bool], quest_def: dict[str, Any]) -> bool:
    requires_flags = quest_def.get("requires_flags", []) or []
    blocks_flags = quest_def.get("blocks_flags", []) or []

    def _get_flag(name: str) -> bool:
        if isinstance(flags, Mapping):
            return bool(flags.get(name, False))
        return bool(flags(name, False))

    for flag_name in requires_flags:
        if not _get_flag(flag_name):
            return False
    for flag_name in blocks_flags:
        if _get_flag(flag_name):
            return False
    return True

