"""Keybinds UI overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_lrtb_rectangle_filled,
    _draw_rectangle_outline,
)
from ..text_draw import TextCache
from ..ui_text_cache import UiTextCache, draw_text
from .keybinds_provider import get_keybinds_ui_data

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class KeybindsOverlay(UIElement):
    """
    Renders the Keybinds UI modal.
    
    Reads data efficiently via keybinds_provider.
    Stateless rendering loop.
    """
    def __init__(self, window: GameWindow, visible: bool = False):
        super().__init__(window)
        self.visible = visible
        self._ui_cache = UiTextCache(getattr(window, "text_cache", TextCache()))
        
        # Internal logical scroll state
        # The provider returns a clamped/target scroll, we smooth towards it
        self._current_scroll_y = 0.0

    def draw(self) -> None:
        if not self.visible:
            return

        KEYBINDS_PALETTE_WIDTH = 800
        KEYBINDS_PALETTE_HEIGHT = 600
        PANEL_PAD = 14
        ROW_HEIGHT = 24
        HEADER_HEIGHT = 50
        FOOTER_HEIGHT = 30
        
        # Center on screen
        win_w, win_h = self.window.width, self.window.height
        cx, cy = win_w / 2, win_h / 2
        
        left = cx - KEYBINDS_PALETTE_WIDTH / 2
        right = cx + KEYBINDS_PALETTE_WIDTH / 2
        top = cy + KEYBINDS_PALETTE_HEIGHT / 2
        bottom = cy - KEYBINDS_PALETTE_HEIGHT / 2
        
        # Draw Modal Background (shadow + crisp border)
        _draw_lrtb_rectangle_filled(
            left + 2, right + 2, top - 2, bottom - 2,
            (0, 0, 0, 120)
        )
        _draw_lrtb_rectangle_filled(
            left, right, top, bottom,
            optional_arcade.arcade.color.BLACK + (245,)  # Almost opaque
        )
        _draw_rectangle_outline(
            left, right, top, bottom,
            optional_arcade.arcade.color.GRAY, 2
        )

        try:
            editor = getattr(self.window, "editor_controller", None)
            if not editor: return
            
            # Fetch data from provider
            # We pass our current scroll and viewport info.
            # Row height constant = 24
            
            LIST_AREA_HEIGHT = KEYBINDS_PALETTE_HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT
            DETAIL_WIDTH = 250
            LIST_WIDTH = KEYBINDS_PALETTE_WIDTH - DETAIL_WIDTH
            
            data = get_keybinds_ui_data(
                editor.keybinds, 
                viewport_height=int(LIST_AREA_HEIGHT),
                row_height=ROW_HEIGHT,
                current_scroll_y=self._current_scroll_y
            )
            
            # Update smooth scroll from provider suggestion
            # For v1, snap to target for determinism
            target_scroll = data.get("scroll_y", 0.0)
            self._current_scroll_y = target_scroll 
            
            # --- 1. Search Header ---
            search_box_top = top - PANEL_PAD
            search_box_bottom = top - PANEL_PAD - 30
            search_box_left = left + PANEL_PAD
            search_box_right = right - PANEL_PAD
            
            query = data.get("query", "")
            
            _draw_lrtb_rectangle_filled(
                search_box_left, search_box_right, search_box_top, search_box_bottom,
                optional_arcade.arcade.color.DARK_SLATE_GRAY
            )
            # Placeholder or Query
            if not query:
                draw_text(
                    self._ui_cache,
                    text="Search keybindings...",
                    x=search_box_left + 10,
                    y=search_box_bottom + 8,
                    color=optional_arcade.arcade.color.GRAY,
                    font_size=12,
                )
            else:
                draw_text(
                    self._ui_cache,
                    text=f"> {query}",
                    x=search_box_left + 10,
                    y=search_box_bottom + 8,
                    color=optional_arcade.arcade.color.WHITE,
                    font_size=12,
                )

            # Recoding banner if active
            if data.get("recording"):
                # Conflict Warning State
                pending_conflicts = data.get("pending_conflicts", ())
                banner_color = optional_arcade.arcade.color.DARK_RED
                if pending_conflicts:
                    banner_color = optional_arcade.arcade.color.RED

                _draw_lrtb_rectangle_filled(
                    search_box_left, search_box_right, search_box_top, search_box_bottom,
                    banner_color
                )
                _draw_lrtb_rectangle_outline(
                    search_box_left, search_box_right, search_box_top, search_box_bottom,
                    optional_arcade.arcade.color.BLACK, 1
                )
                
                rec_target = data.get("recording_target")
                pending_sc = data.get("pending_record_shortcut")
                
                rec_text = "Recording..."
                if rec_target:
                    rec_text = f"Recording for {rec_target[1]}..."
                
                if pending_sc:
                    rec_text += f" Input: {pending_sc}"
                    
                if pending_conflicts:
                    c_names = ", ".join([c[1] for c in pending_conflicts])
                    rec_text += f" !! CONFLICTS: {c_names} !!"
                
                draw_text(
                    self._ui_cache,
                    text=rec_text,
                    x=search_box_left + 10,
                    y=search_box_bottom + 8,
                    color=optional_arcade.arcade.color.WHITE,
                    font_size=12,
                    bold=True,
                )

            # --- 2. List Area ---
            list_top = search_box_bottom - 10
            list_bottom = bottom + FOOTER_HEIGHT
            list_left = left + PANEL_PAD
            list_right = left + LIST_WIDTH
            
            # Draw rows
            rows = data.get("rows_visible", [])
            start_y = list_top # Top of first potential row (if scroll=0)
            
            # Start Y for *rendered* rows needs to account for relative position within slice?
            # slice_visible_rows returns a slice.
            # We must map slice index to screen Y.
            # Y = list_top - ((i * H) - (scroll % H))?
            # Actually provider gives us rows that fit in viewport.
            # We just stack them from top?
            # No, if we scroll smoothly, we need offset.
            # But here `slice_visible_rows` logic assumes snapping or we just draw the returned rows from top.
            # `keybinds_provider` returns `rows_visible` which are the rows to draw.
            
            # Simple list render:
            current_y = list_top - ROW_HEIGHT
            label_left = list_left + 8
            # Reserve a thin gutter for the scrollbar
            scrollbar_w = 4
            scrollbar_gap = 6
            shortcut_right = list_right - (scrollbar_w + scrollbar_gap)
            label_gutter = 8
            approx_char_w = max(1.0, 10 * 0.6)
            
            for row in rows:
                row_idx = row["index"]
                is_selected = row["is_selected"]
                
                # Selection highlighting
                if is_selected:
                    bg_color = optional_arcade.arcade.color.DARK_BLUE
                    if row["has_conflict"]:
                        bg_color = optional_arcade.arcade.color.DARK_RED
                    elif row["has_override"]:
                        bg_color = optional_arcade.arcade.color.TEAL
                        
                    _draw_lrtb_rectangle_filled(
                        list_left, list_right, 
                        current_y + ROW_HEIGHT, current_y,
                        bg_color
                    )
                # Recording row emphasis (static marker)
                if row.get("is_recording"):
                    draw_text(
                        self._ui_cache,
                        text="REC",
                        x=list_left + 2,
                        y=current_y + 6,
                        color=optional_arcade.arcade.color.YELLOW,
                        font_size=9,
                        bold=True,
                    )
                
                # Text Color
                text_color = optional_arcade.arcade.color.WHITE
                if row["has_conflict"]:
                    text_color = optional_arcade.arcade.color.RED
                elif row["has_override"]:
                    text_color = (optional_arcade.arcade.color.CYAN[0], optional_arcade.arcade.color.CYAN[1], optional_arcade.arcade.color.CYAN[2], 200)
                
                # Columns: Title | Shortcut | Scope
                # Title
                label_text = str(row["title"])
                sc_text = row["shortcut"] or ""
                max_label_w = max(0.0, (shortcut_right - label_gutter) - label_left)
                max_label_chars = int(max_label_w / approx_char_w) if max_label_w > 0 else 0
                if max_label_chars > 0 and len(label_text) > max_label_chars:
                    if max_label_chars >= 3:
                        label_text = label_text[: max(0, max_label_chars - 3)] + "..."
                    else:
                        label_text = label_text[:max_label_chars]
                draw_text(
                    self._ui_cache,
                    text=label_text,
                    x=label_left,
                    y=current_y + 6,
                    color=text_color,
                    font_size=10,
                )
                
                # Shortcut (Right aligned in col 1 or center?)
                # Let's put Shortcut at right of list area
                draw_text(
                    self._ui_cache,
                    text=sc_text,
                    x=shortcut_right,
                    y=current_y + 6,
                    color=text_color,
                    font_size=10,
                    align="right",
                )
                if row["has_conflict"]:
                    conflict_marker = "!"
                    draw_text(
                        self._ui_cache,
                        text=conflict_marker,
                        x=list_right - 2,
                        y=current_y + 6,
                        color=optional_arcade.arcade.color.RED,
                        font_size=10,
                        anchor_x="right",
                        anchor_y="baseline",
                    )
                
                current_y -= ROW_HEIGHT
                
                if current_y < list_bottom:
                    break

            # --- Scrollbar (render-only) ---
            total_rows = int(data.get("rows_total", 0) or 0)
            visible_count = len(rows)
            start_index = int(data.get("start_index", 0) or 0)
            viewport_h = list_top - list_bottom
            if total_rows > 0 and visible_count > 0 and total_rows > visible_count and viewport_h > 0:
                track_left = list_right - scrollbar_w
                track_right = list_right - 1
                track_top = list_top
                track_bottom = list_bottom
                _draw_lrtb_rectangle_filled(
                    track_left, track_right, track_top, track_bottom,
                    optional_arcade.arcade.color.DARK_SLATE_GRAY
                )
                ratio = max(0.0, min(1.0, start_index / max(1, (total_rows - visible_count))))
                thumb_h = max(10.0, viewport_h * (visible_count / total_rows))
                usable_h = max(1.0, viewport_h - thumb_h)
                thumb_top = track_top - (ratio * usable_h)
                thumb_bottom = thumb_top - thumb_h
                _draw_lrtb_rectangle_filled(
                    track_left, track_right, thumb_top, thumb_bottom,
                    optional_arcade.arcade.color.GRAY
                )

            # --- 3. Detail/Side Panel ---
            detail_left = list_right + 10
            detail_right = right - PANEL_PAD
            detail_top = list_top
            
            # Divider
            _draw_lrtb_rectangle_outline(
               list_right, list_right, detail_top, list_bottom, 
               optional_arcade.arcade.color.GRAY, 1 
            )
            
            selected_item = data.get("selected_item")
            if selected_item:
                dy = detail_top - 20
                line_h = 18
                
                # Title
                draw_text(
                    self._ui_cache,
                    text=selected_item["title"],
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.WHITE,
                    font_size=12,
                    bold=True,
                    width=DETAIL_WIDTH - 20,
                    multiline=True,
                )
                dy -= 40
                
                # ID
                draw_text(
                    self._ui_cache,
                    text="Action ID:",
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.GRAY,
                    font_size=10,
                )
                draw_text(
                    self._ui_cache,
                    text=selected_item["action_id"],
                    x=detail_left + 60,
                    y=dy,
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=10,
                )
                dy -= line_h
                
                # Scope
                draw_text(
                    self._ui_cache,
                    text="Scope:",
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.GRAY,
                    font_size=10,
                )
                draw_text(
                    self._ui_cache,
                    text=selected_item["scope"],
                    x=detail_left + 60,
                    y=dy,
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=10,
                )
                dy -= line_h * 2
                
                # Shortcuts
                draw_text(
                    self._ui_cache,
                    text="Effective:",
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.WHITE,
                    font_size=10,
                )
                draw_text(
                    self._ui_cache,
                    text=selected_item["effective"] or "(None)",
                    x=detail_left + 60,
                    y=dy,
                    color=optional_arcade.arcade.color.YELLOW,
                    font_size=10,
                )
                dy -= line_h
                
                draw_text(
                    self._ui_cache,
                    text="Default:",
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.GRAY,
                    font_size=10,
                )
                draw_text(
                    self._ui_cache,
                    text=selected_item["default"] or "(None)",
                    x=detail_left + 60,
                    y=dy,
                    color=optional_arcade.arcade.color.GRAY,
                    font_size=10,
                )
                dy -= line_h * 2
                
                # Conflicts
                conflicts = selected_item["conflicts"]
                if conflicts:
                    draw_text(
                        self._ui_cache,
                        text="Conflicts:",
                        x=detail_left,
                        y=dy,
                        color=optional_arcade.arcade.color.RED,
                        font_size=10,
                        bold=True,
                    )
                    dy -= line_h
                    for c_id in conflicts:
                         draw_text(
                             self._ui_cache,
                             text=str(c_id),
                             x=detail_left + 10,
                             y=dy,
                             color=optional_arcade.arcade.color.RED,
                             font_size=9,
                         )
                         dy -= line_h

            # --- 4. Footer / Hints ---
            footer_top = bottom + FOOTER_HEIGHT
            
            hint_text = data.get("hint_text", "")
            if data.get("recording"):
                hint_text = "Press a shortcut... Esc: Cancel"
            
            draw_text(
                self._ui_cache,
                text=hint_text,
                x=left + PANEL_PAD,
                y=bottom + 8,
                color=optional_arcade.arcade.color.GRAY,
                font_size=10,
            )
            
            # Filter Status
            scope_f = data.get("scope_filter", "all")
            conf_f = data.get("show_conflicts_only", False)
            filter_text = f"Scope: {scope_f.upper()}"
            if conf_f:
                filter_text += " | CONFLICTS ONLY"
            
            draw_text(
                self._ui_cache,
                text=filter_text,
                x=right - PANEL_PAD,
                y=bottom + 8,
                color=optional_arcade.arcade.color.YELLOW if conf_f else optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=10,
                align="right",
            )

            # Optional row position hint (render-only)
            total_rows = int(data.get("rows_total", 0) or 0)
            selected_index = int(data.get("selected_index", -1))
            if total_rows > 0 and selected_index >= 0:
                count_text = f"{selected_index + 1} / {total_rows}"
                draw_text(
                    self._ui_cache,
                    text=count_text,
                    x=list_right - 6,
                    y=bottom + 8,
                    color=optional_arcade.arcade.color.LIGHT_GRAY,
                    font_size=10,
                    align="right",
                )

        except Exception as e:
            # Fallback for errors during draw
            print(f"KeybindsOverlay Error: {e}")
