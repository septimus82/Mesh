from typing import List, Optional
import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow
from engine.ui_overlays.common import draw_panel_bg, draw_outline_centered
from engine.ui_text_cache import UiTextCache, draw_text
from engine.text_draw import TextCache

class ConfirmModalOverlay:
    def __init__(self, window: optional_arcade.arcade.Window):
        self.window = window
        self._ui_cache = UiTextCache(getattr(window, "text_cache", TextCache()))

    def draw(self, title: str, message_lines: List[str], prompt_confirm: str = "ENTER: Confirm", prompt_cancel: str = "ESC: Cancel") -> None:
        """Draw a centered modal with message lines."""
        viewport_width = self.window.width
        viewport_height = self.window.height
        
        # Dimensions
        panel_w = 600
        line_height = 20
        # Title + padding + lines + padding + prompt + padding
        content_height = 40 + (len(message_lines) * line_height) + 40
        panel_h = max(200, content_height)
        
        cx, cy = viewport_width // 2, viewport_height // 2
        
        # Background
        draw_panel_bg(cx - panel_w//2, cy - panel_h//2, panel_w, panel_h)
        draw_outline_centered(cx, cy, panel_w, panel_h, (100, 100, 100))
        
        # Title
        draw_text(
            self._ui_cache,
            text=title,
            x=cx,
            y=cy + panel_h // 2 - 25,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
            anchor_x="center",
            bold=True,
        )
        
        # Content
        start_y = cy + panel_h//2 - 60
        for i, line in enumerate(message_lines):
            color = optional_arcade.arcade.color.LIGHT_GRAY
            if line.startswith("!"): # Warning/Alert
                color = optional_arcade.arcade.color.YELLOW
            elif line.startswith("+"): # Add
                color = optional_arcade.arcade.color.GREEN
            elif line.startswith("-"): # Remove
                color = optional_arcade.arcade.color.RED
                
            draw_text(
                self._ui_cache,
                text=line,
                x=cx - panel_w // 2 + 20,
                y=start_y - (i * line_height),
                color=color,
                font_size=12,
                anchor_x="left",
            )

        # Scroll indicator (render-only, uses existing controller fields if present)
        try:
            editor = getattr(self.window, "editor_controller", None)
            confirm = getattr(editor, "confirm_modal", None) if editor is not None else None
            total_lines = len(getattr(confirm, "_all_message_lines", [])) if confirm is not None else 0
            start_index = int(getattr(confirm, "scroll_y", 0)) if confirm is not None else 0
            visible_count = len(message_lines)
            if total_lines > visible_count and visible_count > 0:
                list_top = start_y + (line_height * 0.5)
                list_bottom = start_y - (visible_count * line_height) + (line_height * 0.5)
                track_left = cx + panel_w // 2 - 10
                track_right = track_left + 3
                track_top = list_top
                track_bottom = list_bottom
                optional_arcade.arcade.draw_lrtb_rectangle_filled(track_left, track_right, track_top, track_bottom, (90, 90, 100, 140))
                track_h = max(1.0, track_top - track_bottom)
                ratio = max(0.0, min(1.0, start_index / max(1, (total_lines - visible_count))))
                thumb_h = max(10.0, track_h * (visible_count / total_lines))
                usable_h = max(1.0, track_h - thumb_h)
                thumb_top = track_top - (ratio * usable_h)
                thumb_bottom = thumb_top - thumb_h
                optional_arcade.arcade.draw_lrtb_rectangle_filled(track_left, track_right, thumb_top, thumb_bottom, (150, 150, 160, 200))
        except Exception:
            _log_swallow("CONF-001", "engine/ui_overlays/confirm_modal_overlay.py pass-only blanket swallow")
            pass
            
        # Prompts (Bottom)
        draw_text(
            self._ui_cache,
            text=f"{prompt_confirm}   |   {prompt_cancel}",
            x=cx,
            y=cy - panel_h // 2 + 15,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_x="center",
        )

        # Optional footer hint: Lines a-b / N
        try:
            editor = getattr(self.window, "editor_controller", None)
            confirm = getattr(editor, "confirm_modal", None) if editor is not None else None
            total_lines = len(getattr(confirm, "_all_message_lines", [])) if confirm is not None else 0
            start_index = int(getattr(confirm, "scroll_y", 0)) if confirm is not None else 0
            visible_count = len(message_lines)
            if total_lines > 0 and visible_count > 0:
                line_a = start_index + 1
                line_b = min(total_lines, start_index + visible_count)
                hint = f"Lines {line_a}-{line_b} / {total_lines}"
                draw_text(
                    self._ui_cache,
                    text=hint,
                    x=cx + panel_w // 2 - 12,
                    y=cy - panel_h // 2 + 15,
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=10,
                    anchor_x="right",
                )
        except Exception:
            _log_swallow("CONF-002", "engine/ui_overlays/confirm_modal_overlay.py pass-only blanket swallow")
            pass
