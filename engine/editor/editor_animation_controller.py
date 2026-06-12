from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import engine.optional_arcade as optional_arcade
from engine.editor.animation_panel import (
    apply_animator_runtime as _apply_animator_runtime_impl,
)
from engine.editor.animation_panel import (
    entity_has_animator as _entity_has_animator_impl,
)
from engine.editor.animation_panel import (
    get_animator_config as _get_animator_config_impl,
)
from engine.logging_tools import get_logger
from engine.ui_overlays.common import draw_panel_bg

logger = get_logger(__name__)


class EditorAnimationController:
    """Encapsulates animation panel orchestration and edits."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def toggle_animation_panel(self) -> None:
        if not self.entity_has_animator(self._editor.selected_entity):
            logger.info("[Editor] Animation panel unavailable: select an entity with Animator")
            return
        self._editor.animation_active = not self._editor.animation_active
        self._editor.animation_editing = False
        self._editor.animation_edit_buffer = ""
        if self._editor.animation_active:
            inspector = getattr(self._editor, "inspector", None)
            if inspector is not None:
                inspector.set_inspector_active(False)
            self._editor.palette_active = False
            self._editor.hierarchy_active = False
            self._editor.dialogue_panel_active = False
            self.refresh_animation_cache()
            logger.info("[Editor] Animation panel OPEN")
        else:
            self.close_animation_panel()

    def close_animation_panel(self) -> None:
        self._editor.animation_active = False
        self._editor.animation_editing = False
        self._editor.animation_edit_buffer = ""

    def entity_has_animator(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return _entity_has_animator_impl(sprite)

    def refresh_animation_cache(self) -> None:
        self._editor.animation_selected_index = 0
        config = self.get_animator_config(self._editor.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        if isinstance(animations, dict):
            self._editor._cached_animation_names = sorted(animations.keys())
        else:
            self._editor._cached_animation_names = []

    def get_animator_config(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> Dict[str, Any]:
        return _get_animator_config_impl(self._editor.window.scene_controller, sprite)

    def set_animator_config(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        entity_name = getattr(sprite, "mesh_name", "")
        self._editor._update_param_internal(
            "Animator",
            "animations",
            animator_cfg.get("animations", {}),
            entity_name,
        )
        if "animation_frame_rate" in animator_cfg:
            self._editor._update_param_internal(
                "Animator",
                "animation_frame_rate",
                animator_cfg.get("animation_frame_rate", 8.0),
                entity_name,
            )
        if "animation_state" in animator_cfg:
            self._editor._update_param_internal(
                "Animator",
                "animation_state",
                animator_cfg.get("animation_state", ""),
                entity_name,
            )
        animations = animator_cfg.get("animations", {})
        if isinstance(animations, dict):
            self._editor._cached_animation_names = sorted(animations.keys())
        self.apply_animator_runtime(sprite, animator_cfg)

    def apply_animator_runtime(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        _apply_animator_runtime_impl(
            sprite,
            animator_cfg,
            self._editor._cached_animation_names,
            self._editor.animation_selected_index,
        )

    def handle_animation_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.animation_active:
            return False

        if self._editor.animation_editing:
            if key == optional_arcade.arcade.key.ENTER:
                self.commit_animation_edit()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self._editor.animation_editing = False
                self._editor.animation_edit_buffer = ""
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.animation_edit_buffer = self._editor.animation_edit_buffer[:-1]
                return True
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self.close_animation_panel()
            return True

        config = self.get_animator_config(self._editor.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        names = sorted(animations.keys()) if isinstance(animations, dict) else []
        if not names:
            return False

        if key == optional_arcade.arcade.key.UP:
            self._editor.animation_selected_index = max(0, self._editor.animation_selected_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self._editor.animation_selected_index = min(len(names) - 1, self._editor.animation_selected_index + 1)
            return True

        clip_name = names[self._editor.animation_selected_index]
        clip_cfg = animations.get(clip_name, {})
        if not isinstance(clip_cfg, dict):
            clip_cfg = {}

        if key == optional_arcade.arcade.key.TAB:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                self._editor.animation_field_focus = self.prev_animation_field(
                    self._editor.animation_field_focus
                )
            else:
                self._editor.animation_field_focus = self.next_animation_field(
                    self._editor.animation_field_focus
                )
            return True

        if self._editor.animation_field_focus == "mode":
            if key in (
                optional_arcade.arcade.key.ENTER,
                optional_arcade.arcade.key.SPACE,
                optional_arcade.arcade.key.LEFT,
                optional_arcade.arcade.key.RIGHT,
            ):
                new_mode = self.cycle_mode(
                    clip_cfg.get("mode", "loop"),
                    key
                    in (
                        optional_arcade.arcade.key.RIGHT,
                        optional_arcade.arcade.key.ENTER,
                        optional_arcade.arcade.key.SPACE,
                    ),
                )
                self.apply_animation_change(names, animations, clip_name, "mode", new_mode)
                return True
        elif self._editor.animation_field_focus == "fps":
            delta = 0.0
            if key == optional_arcade.arcade.key.RIGHT:
                delta = 0.5
            elif key == optional_arcade.arcade.key.LEFT:
                delta = -0.5
            if delta != 0.0:
                if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                    delta *= 5
                current = float(clip_cfg.get("fps", config.get("animation_frame_rate", 8.0)))
                new_fps = max(0.1, round(current + delta, 2))
                self.apply_animation_change(names, animations, clip_name, "fps", new_fps)
                return True
        elif self._editor.animation_field_focus == "frames":
            if key == optional_arcade.arcade.key.ENTER:
                frames = clip_cfg.get("frames")
                if isinstance(frames, list):
                    rendered = ", ".join(str(f) for f in frames)
                else:
                    rendered = ""
                self._editor.animation_edit_buffer = rendered
                self._editor.animation_editing = True
                return True
        return False

    def next_animation_field(self, current: str) -> str:
        fields = ["mode", "fps", "frames"]
        if current not in fields:
            return fields[0]
        idx = (fields.index(current) + 1) % len(fields)
        return fields[idx]

    def prev_animation_field(self, current: str) -> str:
        fields = ["mode", "fps", "frames"]
        if current not in fields:
            return fields[-1]
        idx = (fields.index(current) - 1) % len(fields)
        return fields[idx]

    def cycle_mode(self, current: str, forward: bool) -> str:
        modes = ["loop", "once", "ping-pong"]
        if current not in modes:
            current = "loop"
        idx = modes.index(current)
        idx = (idx + (1 if forward else -1)) % len(modes)
        return modes[idx]

    def commit_animation_edit(self) -> None:
        if not self._editor.selected_entity:
            self._editor.animation_editing = False
            self._editor.animation_edit_buffer = ""
            return
        config = self.get_animator_config(self._editor.selected_entity)
        animations = config.get("animations", {})
        if not isinstance(animations, dict):
            self._editor.animation_editing = False
            self._editor.animation_edit_buffer = ""
            return
        names = sorted(animations.keys())
        if not names:
            self._editor.animation_editing = False
            self._editor.animation_edit_buffer = ""
            return
        clip_name = names[self._editor.animation_selected_index]
        clip_cfg = dict(animations.get(clip_name, {}))
        frames = [entry.strip() for entry in self._editor.animation_edit_buffer.split(",") if entry.strip()]
        clip_cfg["frames"] = frames
        animations[clip_name] = clip_cfg
        before = self.get_animator_config(self._editor.selected_entity)
        config["animations"] = animations
        self.set_animator_config(self._editor.selected_entity, config)
        self._editor._push_command({
            "type": "EditAnimation",
            "entity_name": getattr(self._editor.selected_entity, "mesh_name", ""),
            "before": before,
            "after": copy.deepcopy(config),
        })
        self._editor.animation_editing = False
        self._editor.animation_edit_buffer = ""
        self.refresh_animation_cache()

    def apply_animation_change(
        self,
        names: List[str],
        animations: Dict[str, Any],
        clip_name: str,
        field: str,
        new_value: Any,
    ) -> None:
        if not self._editor.selected_entity:
            return
        before = self.get_animator_config(self._editor.selected_entity)
        clip_cfg = dict(animations.get(clip_name, {}))
        clip_cfg[field] = new_value
        animations[clip_name] = clip_cfg
        config = self.get_animator_config(self._editor.selected_entity)
        config["animations"] = animations
        self.set_animator_config(self._editor.selected_entity, config)
        self._editor._push_command({
            "type": "EditAnimation",
            "entity_name": getattr(self._editor.selected_entity, "mesh_name", ""),
            "before": before,
            "after": copy.deepcopy(config),
        })
        self.refresh_animation_cache()

    def draw_animation_panel(self) -> None:
        lines: List[str] = ["ANIMATOR (A)", "--------------"]
        if self._editor.animation_editing:
            lines.append("Editing frames: type values comma-separated, ENTER to save, ESC to cancel")
        config = self.get_animator_config(self._editor.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        names = sorted(animations.keys()) if isinstance(animations, dict) else []
        animation_row_start = -1
        animation_row_count = 0
        if not names:
            lines.append("No animations configured on this entity.")
        else:
            self._editor.animation_selected_index = max(
                0,
                min(self._editor.animation_selected_index, len(names) - 1),
            )
            animation_row_start = len(lines)
            for idx, name in enumerate(names):
                clip_cfg = animations.get(name, {})
                prefix = "> " if idx == self._editor.animation_selected_index else "  "
                mode = clip_cfg.get("mode", "loop")
                fps = clip_cfg.get("fps", config.get("animation_frame_rate", 8.0))
                frames = clip_cfg.get("frames")
                frame_desc = ", ".join(str(f) for f in frames) if isinstance(frames, list) else "<frames?>"
                lines.append(f"{prefix}{name} | mode={mode} fps={fps} frames={frame_desc}")
            animation_row_count = len(names)
            lines.append("Fields: mode / fps / frames (TAB/LEFT/RIGHT to change focus)")
            lines.append(f"Active field: {self._editor.animation_field_focus}")
            lines.append("ENTER edits field; ESC closes panel")

        start_x = 320
        start_y = self._editor.window.height - 80
        panel_width = 520
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        animation_row_stop = animation_row_start + animation_row_count
        for i, line in enumerate(lines):
            if animation_row_start <= i < animation_row_stop:
                continue
            color = (
                optional_arcade.arcade.color.CYAN
                if line.startswith(">") or "Active field" in line
                else optional_arcade.arcade.color.WHITE
            )
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )
        if animation_row_count:
            self._draw_animation_row_list(
                lines[animation_row_start:animation_row_stop],
                start_x,
                start_y,
                panel_width,
                animation_row_start,
            )

    def _draw_animation_row_list(
        self,
        lines: List[str],
        start_x: float,
        start_y: float,
        width: float,
        first_row_index: int,
    ) -> None:
        # Animation rows are preformatted above; keep those strings intact
        # and migrate only the row-list render composition.
        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelRow
        from engine.ui.widgets import Rect

        line_height = 18.0
        top = float(start_y) - (float(first_row_index) * line_height) + (line_height / 2.0)
        rows_panel = EditorPanelBase(
            Rect(
                x=float(start_x),
                y=top - (line_height * float(len(lines))),
                width=float(width),
                height=line_height * float(len(lines)),
            ),
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        for line in lines:
            field = PanelField(
                label=line,
                value=None,
                label_color=self._animation_row_color(line),
                label_font_size=12,
            )
            rows_panel.add_row(PanelRow(content=field, height=line_height, padding_x=0.0))
        rows_panel.draw()

    def _animation_row_color(self, line: str) -> Any:
        if line.startswith(">"):
            return optional_arcade.arcade.color.CYAN
        return optional_arcade.arcade.color.WHITE

    def draw_animation_panel_if_active(self) -> None:
        if self._editor.animation_active:
            self.draw_animation_panel()
