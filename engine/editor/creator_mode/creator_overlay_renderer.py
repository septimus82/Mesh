"""Small read-only Creator Mode overlay renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.common import _draw_rectangle_filled

from .creator_overlay import CreatorOverlayModel, build_creator_overlay_model

DOOR_STAGE_PROPOSAL_ACTION_ID = "door.stage_proposal"
STAGE_PROPOSAL_LABEL = "Stage Proposal"
_GLYPH_WIDTH_RATIO = 0.58
_ACTION_LINE_HEIGHT = 17.0

MAX_TITLE_CHARS = 42
MAX_ACTIONS_CHARS = 72
MAX_TOOL_CHARS = 24
MAX_SUMMARY_CHARS = 58
MAX_FIELD_CHARS = 64
MAX_WARNING_CHARS = 92
MAX_PANEL_CHARS = 68
MAX_RENDERED_FIELDS = 8
MAX_RENDERED_WARNINGS = 2
MAX_RENDERED_PANEL_LINES = 16
MAX_RENDERED_PROPOSAL_ROWS = 3


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
    missing: bool = False
    action_id: str = ""
    hit_left: float = 0.0
    hit_right: float = 0.0
    hit_top: float = 0.0
    hit_bottom: float = 0.0


def hit_test_creator_overlay_click(
    commands: tuple[CreatorOverlayDrawCommand, ...],
    x: float,
    y: float,
) -> str | None:
    """Return the action id for a screen-space click, or None."""

    px = float(x)
    py = float(y)
    for command in commands:
        if not command.action_id:
            continue
        if (
            command.hit_left <= px <= command.hit_right
            and command.hit_bottom <= py <= command.hit_top
        ):
            return command.action_id
    return None


def truncate_creator_overlay_text(text: object, max_chars: int) -> str:
    """Clamp overlay text to one line with an ellipsis."""

    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    limit = max(1, int(max_chars))
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


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

    top_h = min(42.0, max(34.0, win_h * 0.18))
    bottom_h = min(166.0, max(96.0, win_h * 0.23))
    pad = min(14.0, max(8.0, win_w * 0.03))
    side_gap = 8.0
    left_w = min(180.0, max(96.0, win_w * 0.28))
    max_right_w = max(112.0, win_w - left_w - side_gap)
    right_w = min(360.0, max(112.0, win_w * 0.34), max_right_w)
    center_h = max(1.0, win_h - top_h - bottom_h)

    commands.extend(
        (
            _rect("top", win_w / 2.0, win_h - top_h / 2.0, win_w, top_h, (16, 18, 22, 218)),
            _rect(
                "left",
                left_w / 2.0,
                center_h / 2.0 + bottom_h,
                left_w,
                center_h,
                (18, 21, 26, 206),
            ),
            _rect(
                "right",
                win_w - right_w / 2.0,
                center_h / 2.0 + bottom_h,
                right_w,
                center_h,
                (18, 21, 26, 206),
            ),
            _rect("bottom", win_w / 2.0, bottom_h / 2.0, win_w, bottom_h, (16, 18, 22, 218)),
        )
    )

    commands.append(_text(model.title, "top", pad, win_h - 14.0, 16, (255, 255, 255), MAX_TITLE_CHARS))
    commands.append(_text("Read-only preview", "top", pad, win_h - 32.0, 10, (190, 198, 208)))
    commands.append(
        _text(
            " | ".join(model.top_actions),
            "top",
            min(210.0, left_w + pad),
            win_h - 24.0,
            12,
            (220, 225, 232),
            MAX_ACTIONS_CHARS,
        )
    )

    y = win_h - top_h - 22.0
    commands.append(_text("Tools", "left", pad, y, 12, (230, 234, 240)))
    for tool in model.left_tools:
        y -= 22.0
        if y <= bottom_h + 6.0:
            break
        commands.append(_text(tool, "left", pad + 8.0, y, 12, (214, 220, 228), MAX_TOOL_CHARS))

    right_x = win_w - right_w + pad
    y = win_h - top_h - 22.0
    selected_title = model.selected_title or "No selection"
    commands.append(
        _text(model.selected_kind or "Thing", "right", right_x, y, 13, (255, 255, 255), MAX_TITLE_CHARS)
    )
    y -= 20.0
    commands.append(_text(selected_title, "right", right_x, y, 12, (220, 225, 232), MAX_TITLE_CHARS))
    y -= 22.0
    commands.append(_text(model.selected_summary, "right", right_x, y, 11, (190, 198, 208), MAX_SUMMARY_CHARS))
    y -= 26.0
    for label, value, missing in model.inspector_fields[:MAX_RENDERED_FIELDS]:
        if y <= bottom_h + 6.0:
            break
        color = (160, 166, 176) if missing else (220, 225, 232)
        commands.append(
            _text(
                f"{label}: {value}",
                "right",
                right_x,
                y,
                11,
                color,
                MAX_FIELD_CHARS,
                missing=bool(missing),
            )
        )
        y -= 18.0

    if model.door_panel is not None and y > bottom_h + 24.0:
        y -= 6.0
        commands.extend(_door_panel_text_commands(model, right_x, y, bottom_h))

    bottom_lines = model.warnings or ("No problems shown in Creator Mode.",)
    commands.append(_text(model.bottom_title, "bottom", pad, bottom_h - 24.0, 12, (230, 234, 240)))
    status_color = (190, 198, 208) if model.proposal_status.available else (160, 166, 176)
    commands.append(
        _text(
            model.proposal_status.summary,
            "bottom",
            pad + 8.0,
            bottom_h - 42.0,
            11,
            status_color,
            MAX_WARNING_CHARS,
        )
    )
    y = bottom_h - 60.0
    readiness_by_id = {
        row.proposal_id: row for row in model.proposal_accept_readiness.rows
    }
    for row in model.proposal_status.rows[:MAX_RENDERED_PROPOSAL_ROWS]:
        if y <= 4.0:
            break
        commands.append(
            _text(
                f"{row.proposal_id} - {row.summary}",
                "bottom",
                pad + 8.0,
                y,
                10,
                (190, 198, 208),
                MAX_WARNING_CHARS,
            )
        )
        y -= 15.0
        readiness_row = readiness_by_id.get(row.proposal_id)
        if readiness_row is not None and y > 4.0:
            commands.append(
                _text(
                    _proposal_review_line(readiness_row),
                    "bottom",
                    pad + 18.0,
                    y,
                    10,
                    (160, 166, 176),
                    MAX_WARNING_CHARS,
                )
            )
            y -= 15.0
    hidden_count = max(0, model.proposal_status.pending_count - MAX_RENDERED_PROPOSAL_ROWS)
    if hidden_count and y > 4.0:
        commands.append(
            _text(
                f"...and {hidden_count} more",
                "bottom",
                pad + 8.0,
                y,
                10,
                (160, 166, 176),
                MAX_WARNING_CHARS,
            )
        )
        y -= 15.0

    for line in bottom_lines[:MAX_RENDERED_WARNINGS]:
        if y <= 4.0:
            break
        color = (238, 190, 120) if model.warnings else (190, 198, 208)
        commands.append(_text(str(line), "bottom", pad + 8.0, y, 11, color, MAX_WARNING_CHARS))
        y -= 18.0

    return tuple(commands)


def _proposal_review_line(row: Any) -> str:
    return (
        "Review: "
        f"{_review_action_text(row.accept_action)} / "
        f"{_review_action_text(row.reject_action)}"
    )


def _review_action_text(action: Any) -> str:
    state = "ready" if bool(getattr(action, "enabled", False)) else "disabled"
    text = f"{getattr(action, 'label', '')} {state}".strip()
    reason = str(getattr(action, "reason", "") or "").strip()
    if reason:
        return f"{text} - {reason}"
    return text


def _door_panel_text_commands(
    model: CreatorOverlayModel,
    x: float,
    start_y: float,
    bottom_h: float,
) -> tuple[CreatorOverlayDrawCommand, ...]:
    panel = model.door_panel
    if panel is None:
        return ()

    commands: list[CreatorOverlayDrawCommand] = []
    y = start_y
    rendered = 0

    def add(
        text: object,
        font_size: int = 11,
        color: tuple[int, ...] = (220, 225, 232),
        *,
        action_id: str = "",
    ) -> None:
        nonlocal y, rendered
        if rendered >= MAX_RENDERED_PANEL_LINES or y <= bottom_h + 6.0:
            return
        line_text = str(text)
        if action_id:
            commands.append(
                _clickable_text(
                    line_text,
                    "right",
                    x,
                    y,
                    font_size,
                    color,
                    MAX_PANEL_CHARS,
                    action_id=action_id,
                )
            )
        else:
            commands.append(_text(line_text, "right", x, y, font_size, color, MAX_PANEL_CHARS))
        y -= _ACTION_LINE_HEIGHT
        rendered += 1

    add(panel.title, 12, (255, 255, 255))
    add(panel.summary, 10, (190, 198, 208))
    for section in panel.sections:
        add(section.title, 11, (230, 234, 240))
        for line in section.lines:
            add(f"- {line.text}", 10, _severity_color(line.severity))
    for action in panel.actions:
        state = "Ready" if action.enabled else "Disabled"
        detail = f"[{state}] {action.label}"
        if action.reason:
            detail = f"{detail} - {action.reason}"
        clickable_id = ""
        if action.enabled and action.label == STAGE_PROPOSAL_LABEL:
            clickable_id = DOOR_STAGE_PROPOSAL_ACTION_ID
        add(
            detail,
            10,
            (170, 218, 154) if action.enabled else (160, 166, 176),
            action_id=clickable_id,
        )
    if model.last_action_message:
        color = (170, 218, 154) if model.last_action_ok else (245, 145, 145)
        add(model.last_action_message, 10, color)
    return tuple(commands)


def _severity_color(severity: str) -> tuple[int, ...]:
    if severity == "error":
        return (245, 145, 145)
    if severity == "warning":
        return (238, 190, 120)
    return (220, 225, 232)


def draw_creator_overlay(editor: Any) -> None:
    """Draw the read-only Creator Mode overlay if active."""

    snapshot_getter = getattr(editor, "creator_mode_snapshot", None)
    if not callable(snapshot_getter):
        return
    try:
        snapshot = snapshot_getter()
        model = build_creator_overlay_model(snapshot)
    except (AttributeError, TypeError, ValueError):
        return
    if not model.active:
        return

    window = getattr(editor, "window", None)
    width = getattr(window, "width", 1280)
    height = getattr(window, "height", 720)
    try:
        commands = build_creator_overlay_draw_commands(model, width, height)
    except (AttributeError, TypeError, ValueError):
        return
    try:
        _draw_commands(commands)
    except Exception:
        return


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
    max_chars: int = 120,
    *,
    missing: bool = False,
) -> CreatorOverlayDrawCommand:
    return CreatorOverlayDrawCommand(
        kind="text",
        region=region,
        text=truncate_creator_overlay_text(text, max_chars),
        x=x,
        y=y,
        font_size=font_size,
        color=color,
        missing=missing,
    )


def _clickable_text(
    text: str,
    region: str,
    x: float,
    y: float,
    font_size: int,
    color: tuple[int, ...],
    max_chars: int,
    *,
    action_id: str,
) -> CreatorOverlayDrawCommand:
    display = truncate_creator_overlay_text(text, max_chars)
    width = max(8.0, len(display) * float(font_size) * _GLYPH_WIDTH_RATIO)
    top = float(y)
    bottom = top - _ACTION_LINE_HEIGHT
    return CreatorOverlayDrawCommand(
        kind="text",
        region=region,
        text=display,
        x=x,
        y=y,
        font_size=font_size,
        color=color,
        action_id=action_id,
        hit_left=float(x),
        hit_right=float(x) + width,
        hit_top=top,
        hit_bottom=bottom,
    )
