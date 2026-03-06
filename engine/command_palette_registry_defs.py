"""Static command palette registry definition tables and metadata.

This module intentionally contains lightweight pure data constants only.
"""
from __future__ import annotations

_ALIGN_SIMPLE_MAP: dict[str, tuple[str, str]] = {
    "left": ("x", "left"),
    "center": ("x", "center"),
    "right": ("x", "right"),
    "top": ("y", "top"),
    "middle": ("y", "middle"),
    "bottom": ("y", "bottom"),
}


_DISTRIBUTE_SIMPLE_MAP: dict[str, tuple[str, str]] = {
    "distribute_x_gap": ("x", "gap"),
    "distribute_x_center": ("x", "center"),
    "distribute_y_gap": ("y", "gap"),
    "distribute_y_center": ("y", "center"),
}


_SNAP_SIMPLE_MAP: dict[str, tuple[str, str]] = {
    "snap_nearest": ("xy", "nearest"),
    "snap_floor": ("xy", "floor"),
    "snap_ceil": ("xy", "ceil"),
    "snap_x_nearest": ("x", "nearest"),
    "snap_y_nearest": ("y", "nearest"),
}


_NUDGE_DIR_MAP: dict[str, tuple[float, float]] = {
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
}


_ROTATE_SIMPLE_MAP: dict[str, float] = {
    "cw": 90.0,
    "ccw": -90.0,
    "180": 180.0,
}


_PLANES_TOGGLE_REPEAT_MAP: dict[str, tuple[str, ...]] = {
    "x": ("x",),
    "y": ("y",),
    "both": ("x", "y"),
}


_PLANES_SELECT_MAP: dict[str, str] = {
    "prev": "prev",
    "next": "next",
}


_PLANES_MOVE_TO_MAP: dict[str, str] = {
    "top": "top",
    "bottom": "bottom",
    "last": "last",
}


MACRO_RUNNER_COMMAND_IDS: tuple[str, ...] = (
    "macro.objective_zone",
    "macro.door_transition",
    "macro.dialogue_choice_flag",
)


COMMAND_PALETTE_HELP_INTRO_LINES: tuple[str, ...] = (
    "keys: Up/Down navigate",
    "keys: Enter insert/execute",
    "keys: Ctrl+Up/Ctrl+Down prompt history",
    "keys: F1 toggle help",
)


COMMAND_HELP_METADATA: dict[str, dict[str, tuple[str, ...] | str]] = {
    "selection.align": {
        "description": "Align selected entities on an axis using a mode and reference anchor.",
        "examples": (
            "left",
            "axis=x|mode=center|reference=primary",
            "axis=y|mode=bottom|reference=primary",
        ),
        "arg_forms": (
            "token: left|center|right|top|middle|bottom",
            "kv: axis=<x|y>|mode=<...>|reference=<primary|group>",
        ),
    },
    "selection.distribute": {
        "description": "Distribute selected entities by gap or center along an axis.",
        "examples": (
            "distribute_x_gap",
            "axis=x|mode=gap|reference=group",
            "axis=y|mode=center|reference=group",
        ),
        "arg_forms": (
            "token: distribute_x_gap|distribute_x_center|distribute_y_gap|distribute_y_center",
            "kv: axis=<x|y>|mode=<gap|center>|reference=<group|primary>",
        ),
    },
    "selection.snap_to_grid": {
        "description": "Snap selected entities to a grid step with mode and axis control.",
        "examples": (
            "16",
            "step=16|axes=xy|mode=nearest",
            "step=32|axes=x|mode=floor",
        ),
        "arg_forms": (
            "token: snap_nearest|snap_floor|snap_ceil|snap_x_nearest|snap_y_nearest",
            "kv: step=<int>|axes=<x|y|xy>|mode=<nearest|floor|ceil>",
        ),
    },
    "selection.nudge": {
        "description": "Nudge selected entities with direction tokens or explicit deltas.",
        "examples": (
            "left x3",
            "right x3 step=16",
            "dx=1|dy=0|count=2|step=16",
        ),
        "arg_forms": (
            "token: <left|right|up|down> [x<count>] [step=<float>]",
            "kv: dx=<float>|dy=<float>|count=<int>|step=<float>",
        ),
    },
    "selection.rotate": {
        "description": "Rotate selected entities by degrees around a pivot.",
        "examples": (
            "cw",
            "180",
            "deg=90|about=group",
        ),
        "arg_forms": (
            "token: cw|ccw|180|<degrees>",
            "kv: deg=<float>|about=<self|group|primary>",
        ),
    },
}
