"""Standalone settings overlay (keyboard-only keybinding editor)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..text_draw import TextCache, draw_text_cached
from .widgets import DrawInstruction, Label, LayoutResult, Padding, Panel, Rect, Slider, Toggle, VStack, Widget

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class SettingsOverlay(UIElement):
    """
    Minimal settings UI (keyboard-only).

    - ESC: open/close
    - Up/Down: navigate
    """

    _ACTIONS: tuple[str, ...] = (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "interact",
        "attack",
    )
    _SLIDER_LABEL_FONT_SIZE = 12.0
    _SLIDER_LABEL_BAR_GAP = 2.0
    _SLIDER_KNOB_HEIGHT = 10.0

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._paused_before_open: bool = False
        self._selection_index: int = 0
        self._capture_action: str | None = None
        self._dirty: bool = False
        self._text_cache = TextCache()

        from ..settings import load_settings, resolve_settings_path  # noqa: PLC0415

        self._settings_path = resolve_settings_path()
        self.settings = load_settings(self._settings_path)

        self._rows: list[tuple[str, str]] = []
        self._master_slider = Slider(label="Master Volume", value=self._current_master_volume(), step=0.01, height=28.0)
        self._music_slider = Slider(label="Music Volume", value=float(self.settings.music_volume), step=0.01, height=28.0)
        self._sfx_slider = Slider(label="SFX Volume", value=float(self.settings.sfx_volume), step=0.01, height=28.0)
        self._audio_panel = Panel(
            children=[
                VStack(
                    children=[
                        Label(text="Audio", font_size=12, height=20.0, anchor_x="left"),
                        self._master_slider,
                        self._music_slider,
                        self._sfx_slider,
                    ],
                    spacing=6.0,
                    align="stretch",
                )
            ],
            padding=Padding.uniform(8.0),
            bg_style_token="settings_audio",
        )
        self._rumble_toggle = Toggle(label="Rumble Enabled", value=self._current_rumble_enabled(), height=22.0)
        self._rumble_slider = Slider(label="Rumble Strength", value=self._current_rumble_strength(), step=0.01, height=28.0)
        self._input_panel = Panel(
            children=[
                VStack(
                    children=[
                        self._rumble_toggle,
                        self._rumble_slider,
                    ],
                    spacing=6.0,
                    align="stretch",
                )
            ],
            padding=Padding.uniform(8.0),
            bg_style_token="settings_input",
        )
        self._keybinds_panel = Panel(
            children=[],
            padding=Padding.uniform(8.0),
            bg_style_token="settings_keybinds",
        )
        self._overview_panel = Panel(
            children=[],
            padding=Padding.uniform(0.0),
            bg_style_token="settings_overview",
        )
        self._options_panel = Panel(
            children=[],
            padding=Padding.uniform(0.0),
            bg_style_token="settings_options",
        )
        self._rebuild_rows()

    def _panel_rect(self) -> Rect:
        width = min(680.0, max(440.0, self.window.width - 80.0))
        height = min(520.0, max(280.0, self.window.height - 140.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height
        return Rect(x=left, y=bottom, width=(right - left), height=(top - bottom))

    def _audio_panel_bounds(self, panel_rect: Rect) -> Rect:
        return Rect(
            x=panel_rect.left + 20.0,
            y=panel_rect.bottom + 166.0,
            width=max(80.0, panel_rect.width - 40.0),
            height=142.0,
        )

    def _input_panel_bounds(self, panel_rect: Rect) -> Rect:
        return Rect(
            x=panel_rect.left + 20.0,
            y=panel_rect.bottom + 70.0,
            width=max(80.0, panel_rect.width - 40.0),
            height=72.0,
        )

    def _keybinds_panel_bounds(self, panel_rect: Rect) -> Rect:
        return Rect(
            x=panel_rect.left + 20.0,
            y=panel_rect.bottom + 320.0,
            width=max(80.0, panel_rect.width - 40.0),
            height=174.0,
        )

    def _overview_panel_bounds(self, panel_rect: Rect) -> Rect:
        return Rect(
            x=panel_rect.left + 20.0,
            y=panel_rect.bottom + 233.0,
            width=max(80.0, panel_rect.width - 40.0),
            height=51.0,
        )

    def _options_panel_bounds(self, panel_rect: Rect) -> Rect:
        return Rect(
            x=panel_rect.left + 20.0,
            y=panel_rect.bottom + 148.0,
            width=max(80.0, panel_rect.width - 40.0),
            height=85.0,
        )

    def _current_rumble_enabled(self) -> bool:
        cfg = getattr(self.window, "engine_config", None)
        input_cfg = getattr(cfg, "input", None) if cfg is not None else None
        if isinstance(input_cfg, dict):
            try:
                return bool(input_cfg.get("rumble_enabled", False))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-002", "rumble enabled parse", once=True)
                return False
        input_controller = getattr(self.window, "input_controller", None)
        manager = getattr(input_controller, "manager", None) if input_controller is not None else None
        get_enabled = getattr(manager, "is_rumble_enabled", None) if manager is not None else None
        if callable(get_enabled):
            try:
                return bool(get_enabled())
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-003", "rumble enabled call", once=True)
                return False
        return False

    def _current_master_volume(self) -> float:
        cfg = getattr(self.window, "engine_config", None)
        if cfg is not None:
            try:
                return max(0.0, min(1.0, float(getattr(cfg, "master_volume", 1.0))))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-004", "master volume config", once=True)
                return 1.0
        audio = getattr(self.window, "audio", None)
        if audio is not None:
            try:
                return max(0.0, min(1.0, float(getattr(audio, "master_volume", 1.0))))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-005", "master volume audio", once=True)
                return 1.0
        return 1.0

    def _current_rumble_strength(self) -> float:
        cfg = getattr(self.window, "engine_config", None)
        input_cfg = getattr(cfg, "input", None) if cfg is not None else None
        if isinstance(input_cfg, dict):
            try:
                return max(0.0, min(1.0, float(input_cfg.get("rumble_strength", 1.0))))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-006", "rumble strength parse", once=True)
                return 1.0
        input_controller = getattr(self.window, "input_controller", None)
        manager = getattr(input_controller, "manager", None) if input_controller is not None else None
        get_strength = getattr(manager, "get_rumble_strength", None) if manager is not None else None
        if callable(get_strength):
            try:
                strength_val = get_strength()
                return max(0.0, min(1.0, float(cast(float, strength_val))))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-007", "rumble strength call", once=True)
                return 1.0
        return 1.0

    def _layout_audio_section(self) -> LayoutResult:
        panel_rect = self._panel_rect()
        bounds = self._audio_panel_bounds(panel_rect)
        self._master_slider.value = self._current_master_volume()
        self._music_slider.value = float(self.settings.music_volume)
        self._sfx_slider.value = float(self.settings.sfx_volume)
        return self._separate_slider_label_bars(
            self._layout_labeled_section(
                self._audio_panel,
                bounds,
                title="Audio",
                rows=(self._master_slider, self._music_slider, self._sfx_slider),
                title_height=20.0,
                spacing=6.0,
            )
        )

    def _layout_master_slider(self) -> Rect:
        self._layout_audio_section()
        rect = self._master_slider.last_rect
        if isinstance(rect, Rect):
            return rect
        bounds = self._audio_panel_bounds(self._panel_rect())
        self._master_slider.layout(bounds)
        rect = self._master_slider.last_rect
        return rect if isinstance(rect, Rect) else bounds

    def _layout_music_slider(self) -> Rect:
        self._layout_audio_section()
        rect = self._music_slider.last_rect
        if isinstance(rect, Rect):
            return rect
        bounds = self._audio_panel_bounds(self._panel_rect())
        self._music_slider.layout(bounds)
        rect = self._music_slider.last_rect
        return rect if isinstance(rect, Rect) else bounds

    def _layout_sfx_slider(self) -> Rect:
        self._layout_audio_section()
        rect = self._sfx_slider.last_rect
        if isinstance(rect, Rect):
            return rect
        bounds = self._audio_panel_bounds(self._panel_rect())
        self._sfx_slider.layout(bounds)
        rect = self._sfx_slider.last_rect
        return rect if isinstance(rect, Rect) else bounds

    def _layout_rumble_slider(self) -> Rect:
        self._layout_input_section()
        rect = self._rumble_slider.last_rect
        if isinstance(rect, Rect):
            return rect
        bounds = self._input_panel_bounds(self._panel_rect())
        self._rumble_slider.layout(bounds)
        rect = self._rumble_slider.last_rect
        return rect if isinstance(rect, Rect) else bounds

    def _layout_rumble_toggle(self) -> Rect:
        self._layout_input_section()
        rect = self._rumble_toggle.last_rect
        if isinstance(rect, Rect):
            return rect
        panel_rect = self._panel_rect()
        bounds = self._input_panel_bounds(panel_rect)
        self._rumble_toggle.layout(bounds)
        rect = self._rumble_toggle.last_rect
        return rect if isinstance(rect, Rect) else bounds

    def _layout_input_section(self) -> LayoutResult:
        panel_rect = self._panel_rect()
        bounds = self._input_panel_bounds(panel_rect)
        self._rumble_toggle.value = self._current_rumble_enabled()
        self._rumble_slider.value = self._current_rumble_strength()
        return self._separate_slider_label_bars(
            self._layout_labeled_section(
                self._input_panel,
                bounds,
                title="",
                rows=(self._rumble_toggle, self._rumble_slider),
                spacing=6.0,
            )
        )

    def _separate_slider_label_bars(self, layout: LayoutResult) -> LayoutResult:
        instructions: list[DrawInstruction] = []
        label_bottom: float | None = None
        for instruction in layout.instructions:
            kind = str(instruction.kind or "")
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            if kind == "slider_label_text":
                label_bottom = float(payload.get("y", 0.0)) - self._SLIDER_LABEL_FONT_SIZE
            if kind in ("slider_track", "slider_fill", "slider_knob") and label_bottom is not None:
                rect = payload.get("rect")
                if isinstance(rect, Rect):
                    height = min(rect.height, self._SLIDER_KNOB_HEIGHT) if kind == "slider_knob" else rect.height
                    top = label_bottom - self._SLIDER_LABEL_BAR_GAP
                    payload = {**payload, "rect": Rect(rect.x, min(rect.y, top - height), rect.width, height)}
                    instruction = DrawInstruction(kind=kind, payload=payload)
            instructions.append(instruction)
        return LayoutResult(rect=layout.rect, instructions=instructions, children=layout.children)

    def _layout_labeled_section(
        self,
        panel: Panel,
        bounds: Rect,
        *,
        title: str,
        rows: Sequence[Widget],
        title_height: float = 18.0,
        spacing: float = 4.0,
    ) -> LayoutResult:
        section_rows: list[Widget] = []
        if str(title).strip():
            section_rows.append(Label(text=title, font_size=12, height=title_height, anchor_x="left"))
        section_rows.extend(rows)
        panel.children = [VStack(children=section_rows, spacing=spacing, align="stretch")]
        return panel.layout(bounds)

    def _layout_keybinds_section(self) -> LayoutResult:
        panel_rect = self._panel_rect()
        bounds = self._keybinds_panel_bounds(panel_rect)
        rows: list[Label] = []
        for idx, action in enumerate(self._ACTIONS):
            code = self.settings.keybinds.get(action)
            if code is None:
                manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
                get_bindings = getattr(manager, "get_bindings", None) if manager is not None else None
                bindings = get_bindings() if callable(get_bindings) else {}
                codes = bindings.get(action, []) if isinstance(bindings, dict) else []
                code = int(codes[0]) if codes else None
            suffix = f": {self._key_name(code)}"
            if self._capture_action == action:
                suffix = ": [press a key...]"
            prefix = ">" if idx == self._selection_index else " "
            rows.append(Label(text=f"{prefix} Keybind: {action}{suffix}", font_size=11, height=16.0, anchor_x="left"))
        return self._layout_labeled_section(self._keybinds_panel, bounds, title="Keybinds", rows=rows)

    def _layout_overview_section(self, rows: Sequence[str]) -> LayoutResult:
        panel_rect = self._panel_rect()
        bounds = self._overview_panel_bounds(panel_rect)
        labels = [Label(text=str(row), font_size=14, height=17.0, anchor_x="left") for row in rows]
        return self._layout_labeled_section(
            self._overview_panel,
            bounds,
            title="",
            rows=labels,
            spacing=0.0,
        )

    def _layout_options_section(self, rows: Sequence[str]) -> LayoutResult:
        panel_rect = self._panel_rect()
        bounds = self._options_panel_bounds(panel_rect)
        labels = [Label(text=str(row), font_size=14, height=17.0, anchor_x="left") for row in rows]
        return self._layout_labeled_section(
            self._options_panel,
            bounds,
            title="",
            rows=labels,
            spacing=0.0,
        )

    def _commit_sfx_slider(self) -> None:
        self.settings.sfx_volume = max(0.0, min(1.0, float(self._sfx_slider.value)))
        self.apply()
        self._dirty = True

    def _commit_master_slider(self) -> None:
        volume = max(0.0, min(1.0, float(self._master_slider.value)))
        cfg = getattr(self.window, "engine_config", None)
        if cfg is not None:
            try:
                setattr(cfg, "master_volume", volume)
            except Exception:
                _log_swallow("SETT-001", "engine/ui_overlays/settings_overlay.py pass-only blanket swallow")
                pass
        audio = getattr(self.window, "audio", None)
        setter = getattr(audio, "set_master_volume", None) if audio is not None else None
        if callable(setter):
            setter(volume)
        self._dirty = True

    def _commit_music_slider(self) -> None:
        self.settings.music_volume = max(0.0, min(1.0, float(self._music_slider.value)))
        self.apply()
        self._dirty = True

    def _commit_rumble_toggle(self) -> None:
        enabled = bool(self._rumble_toggle.value)
        strength = self._current_rumble_strength()
        cfg = getattr(self.window, "engine_config", None)
        input_cfg = getattr(cfg, "input", None) if cfg is not None else None
        if isinstance(input_cfg, dict):
            input_cfg["rumble_enabled"] = enabled
        elif cfg is not None:
            setattr(cfg, "input", {"rumble_enabled": enabled, "rumble_strength": strength})

        input_controller = getattr(self.window, "input_controller", None)
        manager = getattr(input_controller, "manager", None) if input_controller is not None else None
        setter = getattr(manager, "set_rumble_config", None) if manager is not None else None
        if callable(setter):
            setter(enabled=enabled, strength=strength)

    def _commit_rumble_slider(self) -> None:
        strength = max(0.0, min(1.0, float(self._rumble_slider.value)))
        cfg = getattr(self.window, "engine_config", None)
        input_cfg = getattr(cfg, "input", None) if cfg is not None else None
        if isinstance(input_cfg, dict):
            input_cfg["rumble_strength"] = strength
        elif cfg is not None:
            setattr(cfg, "input", {"rumble_enabled": False, "rumble_strength": strength})
            input_cfg = getattr(cfg, "input", None)

        enabled = False
        if isinstance(input_cfg, dict):
            try:
                enabled = bool(input_cfg.get("rumble_enabled", False))
            except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
                _log_swallow("SETT-008", "rumble enabled read", once=True)
                enabled = False

        input_controller = getattr(self.window, "input_controller", None)
        manager = getattr(input_controller, "manager", None) if input_controller is not None else None
        setter = getattr(manager, "set_rumble_config", None) if manager is not None else None
        if callable(setter):
            setter(enabled=enabled, strength=strength)

    def _rebuild_rows(self) -> None:
        self._rows = [(f"Keybind: {action}", action) for action in self._ACTIONS]
        self._rows.extend(
            [
                ("Audio: SFX Volume", "sfx_volume"),
                ("Audio: Music Volume", "music_volume"),
                ("Input: Rumble Enabled", "rumble_enabled"),
                ("Input: Rumble Strength", "rumble_strength"),
                ("Save & Close", "close"),
            ]
        )

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def toggle(self) -> bool:
        if self.visible:
            self.close()
        else:
            self.open()
        return self.visible

    def open(self) -> None:
        self.visible = True
        self._paused_before_open = bool(getattr(self.window, "paused", False))
        setattr(self.window, "paused", True)
        self._selection_index = 0
        self._capture_action = None
        self._dirty = False

    def close(self) -> None:
        self.visible = False
        self._capture_action = None
        if not self._paused_before_open:
            setattr(self.window, "paused", False)
        self._paused_before_open = False
        if self._dirty:
            self.save()
        self._dirty = False

    def save(self) -> None:
        from ..settings import save_settings  # noqa: PLC0415

        save_settings(self._settings_path, self.settings)

    def apply(self) -> None:
        from ..settings import apply_settings  # noqa: PLC0415

        apply_settings(self.window, self.settings)

    def _key_name(self, code: int | None) -> str:
        if code is None:
            return "-"
        try:
            return str(optional_arcade.arcade.key.key_string(int(code)))
        except Exception:  # noqa: BLE001  # REASON: settings overlay fallback isolation
            _log_swallow("SETT-009", "key name lookup", once=True)
            return str(code)

    def get_lines(self) -> list[str]:
        from ..settings import resolve_settings_path  # noqa: PLC0415

        rows: list[str] = ["Settings (ESC)"]
        rows.append(f"path: {resolve_settings_path(self._settings_path).as_posix()}")
        rows.append("")
        for idx, (label, key) in enumerate(self._rows):
            prefix = ">" if idx == self._selection_index else " "
            suffix = ""
            if key in self._ACTIONS:
                code = self.settings.keybinds.get(key)
                if code is None:
                    manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
                    get_bindings = getattr(manager, "get_bindings", None) if manager is not None else None
                    bindings = get_bindings() if callable(get_bindings) else {}
                    codes = bindings.get(key, []) if isinstance(bindings, dict) else []
                    code = int(codes[0]) if codes else None
                suffix = f": {self._key_name(code)}"
                if self._capture_action == key:
                    suffix = ": [press a key...]"
            elif key == "sfx_volume":
                suffix = f": {int(round(float(self.settings.sfx_volume) * 100.0)):d}%"
            elif key == "music_volume":
                suffix = f": {int(round(float(self.settings.music_volume) * 100.0)):d}%"
            elif key == "rumble_enabled":
                suffix = ": on" if self._current_rumble_enabled() else ": off"
            elif key == "rumble_strength":
                suffix = f": {int(round(self._current_rumble_strength() * 100.0)):d}%"
            rows.append(f"{prefix} {label}{suffix}")
        return rows

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False

        if self._capture_action is not None:
            if key == optional_arcade.arcade.key.ESCAPE:
                self._capture_action = None
                return True

            action = self._capture_action
            self._capture_action = None
            self.settings.keybinds[str(action)] = int(key)
            self.apply()
            self._dirty = True
            return True
        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True

        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self._selection_index = (self._selection_index - 1) % len(self._rows)
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self._selection_index = (self._selection_index + 1) % len(self._rows)
            return True

        _, row_key = self._rows[self._selection_index]
        arcade_key = optional_arcade.arcade.key
        if row_key in ("sfx_volume", "music_volume", "rumble_strength") and key in (arcade_key.LEFT, arcade_key.RIGHT, arcade_key.MINUS, arcade_key.EQUAL):
            delta = 0.05 if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL) else -0.05
            if row_key == "sfx_volume":
                self.settings.sfx_volume = max(0.0, min(1.0, float(self.settings.sfx_volume) + delta))
                self.apply()
                self._dirty = True
            elif row_key == "rumble_strength":
                self._rumble_slider.value = max(0.0, min(1.0, self._current_rumble_strength() + delta))
                self._commit_rumble_slider()
            else:
                self.settings.music_volume = max(0.0, min(1.0, float(self.settings.music_volume) + delta))
                self.apply()
                self._dirty = True
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            if row_key in self._ACTIONS:
                self._capture_action = str(row_key)
                return True
            if row_key == "close":
                self.close()
                return True

        return True

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return False
        self._layout_input_section()
        toggle_handled = self._rumble_toggle.on_mouse_press(float(x), float(y))
        if toggle_handled:
            self._commit_rumble_toggle()
            return True
        rumble_handled = self._rumble_slider.on_mouse_press(float(x), float(y))
        if rumble_handled:
            self._commit_rumble_slider()
            return True
        self._layout_audio_section()
        master_handled = self._master_slider.on_mouse_press(float(x), float(y))
        if master_handled:
            self._commit_master_slider()
            return True
        music_handled = self._music_slider.on_mouse_press(float(x), float(y))
        if music_handled:
            self._commit_music_slider()
            return True
        self._layout_sfx_slider()
        handled = self._sfx_slider.on_mouse_press(float(x), float(y))
        if not handled:
            return False
        self._commit_sfx_slider()
        return True

    def on_mouse_drag(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int = 0,
    ) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if int(buttons) == 0:
            return False
        master_changed = self._master_slider.on_mouse_drag(float(x), float(y))
        if master_changed:
            self._commit_master_slider()
        music_changed = self._music_slider.on_mouse_drag(float(x), float(y))
        if music_changed:
            self._commit_music_slider()
        rumble_changed = self._rumble_slider.on_mouse_drag(float(x), float(y))
        if rumble_changed:
            self._commit_rumble_slider()
        changed = self._sfx_slider.on_mouse_drag(float(x), float(y))
        if changed:
            self._commit_sfx_slider()
        return bool(master_changed or music_changed or rumble_changed or changed)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return False
        master_released = self._master_slider.on_mouse_release(float(x), float(y))
        music_released = self._music_slider.on_mouse_release(float(x), float(y))
        rumble_released = self._rumble_slider.on_mouse_release(float(x), float(y))
        sfx_released = self._sfx_slider.on_mouse_release(float(x), float(y))
        return bool(master_released or music_released or rumble_released or sfx_released)

    def draw(self) -> None:
        if not self.visible:
            return

        lines = self.get_lines()
        overview_lines = lines[:3]
        options_lines = lines[3 + len(self._ACTIONS):]
        panel_rect = self._panel_rect()
        left = panel_rect.left
        right = panel_rect.right
        bottom = panel_rect.bottom
        top = panel_rect.top
        width = panel_rect.width
        height = panel_rect.height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 210),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        overview_layout = self._layout_overview_section(overview_lines)
        options_layout = self._layout_options_section(options_lines)
        keybinds_layout = self._layout_keybinds_section()
        audio_layout = self._layout_audio_section()
        input_layout = self._layout_input_section()
        _diagnostic_instruction_ids = {
            id(instr) for instr in (*overview_layout.instructions, *options_layout.instructions)
        }
        for instruction in (
            *overview_layout.instructions,
            *options_layout.instructions,
            *keybinds_layout.instructions,
            *audio_layout.instructions,
            *input_layout.instructions,
        ):
            kind = str(instruction.kind or "")
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            if kind == "text" and id(instruction) in _diagnostic_instruction_ids:
                continue
            if kind == "panel_bg":
                if str(payload.get("style_token", "")) in ("settings_overview", "settings_options"):
                    continue
                rect_obj = payload.get("rect")
                if not isinstance(rect_obj, Rect):
                    continue
                rect_typed = cast(Rect, rect_obj)  # Explicit cast for Pylance
                _draw_rectangle_filled(
                    center_x=rect_typed.center_x,
                    center_y=rect_typed.center_y,
                    width=rect_typed.width,
                    height=rect_typed.height,
                    color=(22, 24, 30, 180),
                )
            elif kind in ("slider_track", "slider_fill", "slider_knob"):
                rect_obj = payload.get("rect")
                if not isinstance(rect_obj, Rect):
                    continue
                rect_typed = cast(Rect, rect_obj)  # Explicit cast for Pylance
                if kind == "slider_track":
                    color = (70, 70, 80, 220)
                elif kind == "slider_fill":
                    color = (120, 180, 255, 230)
                else:
                    color = (255, 220, 120, 230) if bool(payload.get("dragging", False)) else (220, 220, 230, 230)
                _draw_rectangle_filled(
                    center_x=rect_typed.center_x,
                    center_y=rect_typed.center_y,
                    width=rect_typed.width,
                    height=rect_typed.height,
                    color=color,
                )
            elif kind in ("text", "slider_label_text", "slider_value_text"):
                draw_text_cached(
                    str(payload.get("text") or ""),
                    float(payload.get("x", 0.0)),
                    float(payload.get("y", 0.0)),
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=int(payload.get("font_size", 12)),
                    anchor_x=str(payload.get("anchor_x", "left")),
                    anchor_y=str(payload.get("anchor_y", "center")),
                    font_name=("Consolas", "Courier New", "Courier"),
                    cache=self._text_cache,
                )
            elif kind == "toggle_text":
                draw_text_cached(
                    str(payload.get("text") or ""),
                    float(payload.get("x", 0.0)),
                    float(payload.get("y", 0.0)),
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=12,
                    anchor_x=str(payload.get("anchor_x", "left")),
                    anchor_y=str(payload.get("anchor_y", "center")),
                    font_name=("Consolas", "Courier New", "Courier"),
                    cache=self._text_cache,
                )
