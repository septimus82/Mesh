"""Small read-only Creator Mode overlay renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.common import _draw_rectangle_filled

from .creator_overlay import CreatorOverlayModel, build_creator_overlay_model


@dataclass(frozen=True, slots=True)
class CreatorOverlayDrawCommand:
    """Renderer command prepared without requiring Arcade GL."""

    kind: str
    region: str
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    color: tuple[int, ...] = (255, 255, 255)
    font_size: int = 12


def build_creator_overlay_draw_commands(
    model: CreatorOverlayModel,
    width: int | float,
    height: int | float,
) -> tuple[CreatorOverlayDrawCommand, ...]:
    """Build simple screen-space draw commands for the visible overlay."""

    if not model.active:
        return ()

    win_w = max(320.0, float(width or 1280))
    win_h = max(240.0, float(height or 720))
    commands: list[CreatorOverlayDrawCommand] = []

    top_h = 42.0
    left_w = 180.0
    right_w = min(360.0, max(260.0, win_w * 0.28))
    bottom_h = 92.0
    pad = 14.0

    commands.extend(
        (
            _rect("top", win_w / 2.0, win_h - top_h / 2.0, win_w, top_h, (16, 18, 22, 218)),
            _rect(
                "left",
                left_w / 2.0,
                (win_h - top_h - bottom_h) / 2.0 + bottom_h,
                left_w,
                win_h - top_h - bottom_h,
                (18, 21, 26, 206),
            ),
            _rect(
                "right",
                win_w - right_w / 2.0,
                (win_h - top_h - bottom_h) / 2.0 + bottom_h,
                right_w,
                win_h - top_h - bottom_h,
                (18, 21, 26, 206),
            ),
            _rect("bottom", win_w / 2.0, bottom_h / 2.0, win_w, bottom_h, (16, 18, 22, 218)),
        )
    )

    commands.append(_text(model.title, "top", pad, win_h - 14.0, 16, (255, 255, 255)))
    commands.append(_text("Read-only preview", "top", pad, win_h - 32.0, 10, (190, 198, 208)))
    commands.append(
        _text(" | ".join(model.top_actions), "top", 210.0, win_h - 24.0, 12, (220, 225, 232))
    )

    y = win_h - top_h - 22.0
    commands.append(_text("Tools", "left", pad, y, 12, (230, 234, 240)))
    for tool in model.left_tools:
        y -= 22.0
        commands.append(_text(tool, "left", pad + 8.0, y, 12, (214, 220, 228)))

    right_x = win_w - right_w + pad
    y = win_h - top_h - 22.0
    selected_title = model.selected_title or "No selection"
    commands.append(
        _text(model.selected_kind or "Thing", "right", right_x, y, 13, (255, 255, 255))
    )
    y -= 20.0
    commands.append(_text(selected_title, "right", right_x, y, 12, (220, 225, 232)))
    y -= 22.0
    commands.append(_text(model.selected_summary, "right", right_x, y, 11, (190, 198, 208)))
    y -= 26.0
    for label, value, missing in model.inspector_fields[:10]:
        color = (160, 166, 176) if missing else (220, 225, 232)
        commands.append(_text(f"{label}: {value}", "right", right_x, y, 11, color))
        y -= 18.0

    bottom_lines = model.warnings or ("No problems shown in Creator Mode.",)
    commands.append(_text(model.bottom_title, "bottom", pad, bottom_h - 24.0, 12, (230, 234, 240)))
    y = bottom_h - 46.0
    for line in bottom_lines[:3]:
        color = (238, 190, 120) if model.warnings else (190, 198, 208)
        commands.append(_text(str(line), "bottom", pad + 8.0, y, 11, color))
        y -= 18.0

    return tuple(commands)


def draw_creator_overlay(editor: Any) -> None:
    """Draw the read-only Creator Mode overlay if active."""

    snapshot_getter = getattr(editor, "creator_mode_snapshot", None)
    if not callable(snapshot_getter):
        return
    snapshot = snapshot_getter()
    model = build_creator_overlay_model(snapshot)
    if not model.active:
        return

    window = getattr(editor, "window", None)
    width = getattr(window, "width", 1280)
    height = getattr(window, "height", 720)
    _draw_commands(build_creator_overlay_draw_commands(model, width, height))


def _draw_commands(commands: tuple[CreatorOverlayDrawCommand, ...]) -> None:
    for command in commands:
        if command.kind == "rect":
            _draw_rectangle_filled(
                command.x,
                command.y,
                command.width,
                command.height,
                command.color,
            )
            continue
        if command.kind == "text":
            optional_arcade.arcade.draw_text(
                command.text,
                command.x,
                command.y,
                command.color,
                command.font_size,
                anchor_x="left",
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )


def _rect(
    region: str,
    x: float,
    y: float,
    width: float,
    height: float,
    color: tuple[int, ...],
) -> CreatorOverlayDrawCommand:
    return CreatorOverlayDrawCommand(
        kind="rect",
        region=region,
        x=x,
        y=y,
        width=width,
        height=height,
        color=color,
    )


def _text(
    text: str,
    region: str,
    x: float,
    y: float,
    font_size: int,
    color: tuple[int, ...],
) -> CreatorOverlayDrawCommand:
    return CreatorOverlayDrawCommand(
        kind="text",
        region=region,
        text=text,
        x=x,
        y=y,
        font_size=font_size,
        color=color,
    )
