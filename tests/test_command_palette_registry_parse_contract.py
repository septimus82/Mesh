from __future__ import annotations

import pytest

from engine import command_palette_registry_defs as defs
from engine import command_palette_registry_parse as parse

pytestmark = pytest.mark.fast


def test_parse_align_args_simple_token() -> None:
    result = parse.parse_align_args("left", simple_map=defs._ALIGN_SIMPLE_MAP)
    assert result == {"ok": True, "axis": "x", "mode": "left", "reference": "primary"}


def test_parse_align_args_key_value() -> None:
    result = parse.parse_align_args("axis=y|mode=middle|reference=group", simple_map=defs._ALIGN_SIMPLE_MAP)
    assert result == {"ok": True, "axis": "y", "mode": "middle", "reference": "group"}


def test_parse_align_args_unknown_token() -> None:
    result = parse.parse_align_args("bogus", simple_map=defs._ALIGN_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "unknown_align_token", "token": "bogus"}


def test_parse_align_args_invalid_params() -> None:
    result = parse.parse_align_args("axis=x", simple_map=defs._ALIGN_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "invalid_align_params"}


def test_parse_distribute_args_simple_token() -> None:
    result = parse.parse_distribute_args("distribute_x_gap", simple_map=defs._DISTRIBUTE_SIMPLE_MAP)
    assert result == {"ok": True, "axis": "x", "mode": "gap", "reference": "group"}


def test_parse_distribute_args_key_value() -> None:
    result = parse.parse_distribute_args("axis=y|mode=center|ref=primary", simple_map=defs._DISTRIBUTE_SIMPLE_MAP)
    assert result == {"ok": True, "axis": "y", "mode": "center", "reference": "primary"}


def test_parse_distribute_args_unknown_token() -> None:
    result = parse.parse_distribute_args("spread", simple_map=defs._DISTRIBUTE_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "unknown_distribute_token", "token": "spread"}


def test_parse_snap_args_simple_token() -> None:
    result = parse.parse_snap_args("snap_floor", simple_map=defs._SNAP_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "invalid_step"}


def test_parse_snap_args_numeric_step() -> None:
    result = parse.parse_snap_args("16", simple_map=defs._SNAP_SIMPLE_MAP)
    assert result == {"ok": True, "step": 16, "axes": "xy", "mode": "nearest"}


def test_parse_snap_args_key_value() -> None:
    result = parse.parse_snap_args("step=8|axes=x|mode=floor", simple_map=defs._SNAP_SIMPLE_MAP)
    assert result == {"ok": True, "step": 8, "axes": "x", "mode": "floor"}


def test_parse_snap_args_invalid_step_value() -> None:
    result = parse.parse_snap_args("step=abc|axes=xy", simple_map=defs._SNAP_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "invalid_step_value", "value": "step=abc"}


def test_parse_snap_args_unknown_token() -> None:
    result = parse.parse_snap_args("snap_now", simple_map=defs._SNAP_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "unknown_snap_token", "token": "snap_now"}


def test_parse_nudge_args_direction_defaults_step() -> None:
    result = parse.parse_nudge_args("right x3", direction_map=defs._NUDGE_DIR_MAP)
    assert result == {"ok": True, "dx": 1.0, "dy": 0.0, "count": 3, "step": 1.0}


def test_parse_nudge_args_key_value() -> None:
    result = parse.parse_nudge_args("dx=2|dy=-1|count=4|step=0.5", direction_map=defs._NUDGE_DIR_MAP)
    assert result == {"ok": True, "dx": 2.0, "dy": -1.0, "count": 4, "step": 0.5}


def test_parse_nudge_args_invalid_dx() -> None:
    result = parse.parse_nudge_args("dx=bad|dy=1|count=1|step=1", direction_map=defs._NUDGE_DIR_MAP)
    assert result == {"ok": False, "reason": "invalid_dx", "value": "dx=bad"}


def test_parse_nudge_args_unknown_token() -> None:
    result = parse.parse_nudge_args("spin", direction_map=defs._NUDGE_DIR_MAP)
    assert result == {"ok": False, "reason": "unknown_nudge_token", "token": "spin"}


def test_parse_rotate_args_simple_token() -> None:
    result = parse.parse_rotate_args("cw", simple_map=defs._ROTATE_SIMPLE_MAP)
    assert result == {"ok": True, "deg": 90.0, "about": "self"}


def test_parse_rotate_args_numeric() -> None:
    result = parse.parse_rotate_args("-45", simple_map=defs._ROTATE_SIMPLE_MAP)
    assert result == {"ok": True, "deg": -45.0, "about": "self"}


def test_parse_rotate_args_key_value() -> None:
    result = parse.parse_rotate_args("deg=180|about=group", simple_map=defs._ROTATE_SIMPLE_MAP)
    assert result == {"ok": True, "deg": 180.0, "about": "group"}


def test_parse_rotate_args_invalid_deg() -> None:
    result = parse.parse_rotate_args("deg=abc|about=group", simple_map=defs._ROTATE_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "invalid_deg", "value": "deg=abc"}


def test_parse_rotate_args_unknown_token() -> None:
    result = parse.parse_rotate_args("spin", simple_map=defs._ROTATE_SIMPLE_MAP)
    assert result == {"ok": False, "reason": "unknown_rotate_token", "token": "spin"}


def test_parse_toast_and_seconds_variants() -> None:
    parse_float = lambda s: float(s) if s.replace(".", "", 1).isdigit() else None
    assert parse.parse_toast_and_seconds("hello", parse_float=parse_float) == ("hello", None)
    assert parse.parse_toast_and_seconds("hello|1.5", parse_float=parse_float) == ("hello", 1.5)
    assert parse.parse_toast_and_seconds("hello|bad", parse_float=parse_float) is None


def test_registry_parse_wrappers_stable() -> None:
    import engine.command_palette_registry as registry

    assert registry._parse_align_args("left")["ok"] is True
    assert registry._parse_rotate_args("deg=bad|about=group")["reason"] == "invalid_deg"
