from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

import engine.optional_arcade as optional_arcade

from .common import (
    INSPECTOR_MAX_LINE_CHARS,
    INSPECTOR_MAX_LINES,
    INSPECTOR_MAX_LIST_ITEMS,
    UIElement,
    _draw_rectangle_filled,
    _safe_truncate,
)
from .theme import EDITOR_THEME

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _coerce_inspector_str(value: object | None, *, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _coerce_inspector_int(value: object | None, *, default: int = 0) -> int:
    if value is None:
        return int(default)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return int(default)


def _inspector_basename(value: object | None) -> str:
    text = _coerce_inspector_str(value)
    if text in ("-", ""):
        return "-"
    try:
        return os.path.basename(text) or text
    except Exception:
        return text


def _inspector_sorted_str_list(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return sorted(set(cleaned))


def _inspector_format_list(items: list[str], *, max_items: int = INSPECTOR_MAX_LIST_ITEMS) -> str:
    limit = max(0, int(max_items))
    if limit == 0 or not items:
        return "-"
    shown = items[:limit]
    suffix = ""
    if len(items) > len(shown):
        suffix = f" (+{len(items) - len(shown)})"
    return ",".join(shown) + suffix


def build_inspector_lines(dump: dict[str, Any]) -> list[str]:
    """Build deterministic, length-capped inspector text lines."""

    data: dict[str, Any] = dump if isinstance(dump, dict) else {}

    preset_id = _coerce_inspector_str(data.get("preset_id"))
    world_file = _inspector_basename(data.get("world_file"))
    scene_path = _coerce_inspector_str(data.get("scene_path"))
    gold = _coerce_inspector_int(data.get("gold"), default=0)

    flags_count = _coerce_inspector_int(data.get("flags_count"), default=0)
    flags_sample = _inspector_sorted_str_list(data.get("flags_sample"))
    flags_preview = _inspector_format_list(flags_sample, max_items=4)

    last_zone_id = _coerce_inspector_str(data.get("last_zone_id"))
    active_quest_ids = _inspector_sorted_str_list(data.get("active_quest_ids"))
    quests_preview = _inspector_format_list(active_quest_ids)

    raw_lines = [
        "Inspector",
        f"Preset: {preset_id} | World: {world_file}",
        f"Scene: {scene_path}",
        f"Gold: {gold}",
        f"Flags: {flags_count} [{flags_preview}]" if flags_count else "Flags: 0",
        f"Last zone: {last_zone_id}",
        f"Quests: {quests_preview}",
    ]

    capped = [_safe_truncate(line, INSPECTOR_MAX_LINE_CHARS) for line in raw_lines]
    return capped[:INSPECTOR_MAX_LINES]


class InspectorOverlay(UIElement):
    """Non-blocking, compact runtime Inspector panel."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.background_color = getattr(optional_arcade.arcade.color, "BLACK", EDITOR_THEME.black)
        self.text_color = getattr(optional_arcade.arcade.color, "WHITE", EDITOR_THEME.browser_white)
        self._lines: list[str] = []
        self._text = optional_arcade.arcade.Text(
            text="",
            x=window.width - 20,
            y=window.height - 20,
            color=self.text_color,
            anchor_x="right",
            anchor_y="top",
            font_size=12,
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        self._text.x = self.window.width - 20
        self._text.y = self.window.height - 20

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not self.visible:
            return
        try:
            from ..tooling_runtime.state_dump import dump_state

            snapshot = dump_state(self.window, flags_sample_limit=10)
        except Exception:
            snapshot = {}
        self._lines = build_inspector_lines(snapshot)

    def draw(self) -> None:
        if not self.visible:
            return

        lines = self._lines or ["Inspector", "<no data>"]
        text = "\n".join(lines[:INSPECTOR_MAX_LINES])
        self._text.text = text

        padding = 10
        width = max(260, self._text.content_width + padding * 2)
        height = self._text.content_height + padding * 2

        center_x = self.window.width - width / 2 - 10
        center_y = self.window.height - height / 2 - 10
        _draw_rectangle_filled(center_x, center_y, width, height, EDITOR_THEME.scrim_dim_medium)

        self._text.x = self.window.width - 20
        self._text.y = self.window.height - 20
        self._text.draw()
