from __future__ import annotations

from typing import Any

from . import command_palette_registry_defs as _defs
from . import command_palette_registry_parse as _parse
from .command_palette_registry_selection import parse_float as _parse_float


_ALIGN_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._ALIGN_SIMPLE_MAP
_DISTRIBUTE_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._DISTRIBUTE_SIMPLE_MAP
_SNAP_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._SNAP_SIMPLE_MAP
_NUDGE_DIR_MAP: dict[str, tuple[float, float]] = _defs._NUDGE_DIR_MAP
_ROTATE_SIMPLE_MAP: dict[str, float] = _defs._ROTATE_SIMPLE_MAP
_PLANES_TOGGLE_REPEAT_MAP: dict[str, tuple[str, ...]] = _defs._PLANES_TOGGLE_REPEAT_MAP
_PLANES_SELECT_MAP: dict[str, str] = _defs._PLANES_SELECT_MAP
_PLANES_MOVE_TO_MAP: dict[str, str] = _defs._PLANES_MOVE_TO_MAP


def _parse_toast_and_seconds(arg: str | None) -> tuple[str, float | None] | None:
    return _parse.parse_toast_and_seconds(arg, parse_float=_parse_float)


def _parse_align_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_align_args(arg, simple_map=_ALIGN_SIMPLE_MAP)


def _parse_distribute_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_distribute_args(arg, simple_map=_DISTRIBUTE_SIMPLE_MAP)


def _parse_snap_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_snap_args(arg, simple_map=_SNAP_SIMPLE_MAP)


def _parse_nudge_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_nudge_args(arg, direction_map=_NUDGE_DIR_MAP)


def _parse_rotate_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_rotate_args(arg, simple_map=_ROTATE_SIMPLE_MAP)


def _parse_planes_toggle_repeat_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_planes_toggle_repeat_args(arg, axis_map=_PLANES_TOGGLE_REPEAT_MAP)


def _parse_planes_select_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_planes_select_args(arg, mode_map=_PLANES_SELECT_MAP)


def _parse_planes_move_to_args(arg: str | None) -> dict[str, Any]:
    return _parse.parse_planes_move_to_args(arg, mode_map=_PLANES_MOVE_TO_MAP)
