"""Problems panel overlay for editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_tb_rectangle_outline
from .widgets import Rect, ScrollList

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


PROBLEMS_TEXT_COLOR = (220, 220, 230, 255)
PROBLEMS_DIM_COLOR = (150, 150, 160, 255)
PROBLEMS_SELECTED_BG = (90, 140, 200, 140)
PROBLEMS_HEADER_COLOR = (180, 200, 220, 255)


class ProblemsPanelOverlay(UIElement):
    """Editor-only overlay that draws the Problems panel."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)

    def draw(self) -> None:
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import compute_editor_shell_layout
        from ..editor.panel_search_model import format_search_bar_text
        from ..editor.scene_lint_model import (
            PROBLEMS_LINE_HEIGHT,
            compute_problems_panel_layout,
        )

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_tab != "Problems":
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)

        left_w, right_w = get_effective_dock_widths(controller, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock
        panel = compute_problems_panel_layout(dock)

        # Use Stateless Provider
        from .providers import problems_panel_provider

        viewport_h = int(panel.list_rect.height)
        data = problems_panel_provider(self.window, viewport_h, PROBLEMS_LINE_HEIGHT)

        rows = data.get("rows", [])
        start_idx = data.get("start_index", 0)
        total_count = data.get("total_count", 0)
        selected_index = data.get("selected_index", 0)
        _scroll_y = data.get("scroll_y", 0)
        query = data.get("query", "")
        preview_open = data.get("preview_open", False)
        severity_counts = data.get("severity_counts", {}) if isinstance(data.get("severity_counts"), dict) else {}
        error_count = int(severity_counts.get("error", 0) or 0)
        warning_count = int(severity_counts.get("warning", 0) or 0)
        info_count = int(severity_counts.get("info", 0) or 0)
        has_new_errors = bool(data.get("has_new_errors", False))

        search = getattr(controller, "search", None)
        search_focused = bool(search is not None and search.is_panel_search_focused("problems"))

        # Panel framing (use dock bounds for backdrop)
        _draw_rectangle_filled(
            dock.left,
            dock.right,
            dock.bottom,
            dock.top,
            (18, 18, 22, 220),
        )
        _draw_tb_rectangle_outline(
            dock.left,
            dock.right,
            dock.top,
            dock.bottom,
            (100, 100, 110, 255),
            1,
        )

        # Header
        draw_text_cached(
            f"Problems ({total_count})",
            panel.header_rect.left,
            panel.header_rect.center_y,
            color=PROBLEMS_HEADER_COLOR,
            font_size=11,
            anchor_y="center",
            cache=self._text_cache,
        )
        counts_text = f"E:{error_count} W:{warning_count} I:{info_count}"
        if has_new_errors and error_count > 0:
            counts_text = f"{counts_text} *new*"
        draw_text_cached(
            counts_text,
            panel.header_rect.right - 4,
            panel.header_rect.center_y,
            color=PROBLEMS_DIM_COLOR,
            font_size=10,
            anchor_x="right",
            anchor_y="center",
            cache=self._text_cache,
        )
        draw_text_cached(
            "Scan",
            panel.scan_rect.center_x,
            panel.scan_rect.center_y,
            color=PROBLEMS_TEXT_COLOR,
            font_size=11,
            anchor_x="center",
            anchor_y="center",
            cache=self._text_cache,
        )
        draw_text_cached(
            "Fix All Safe",
            panel.fix_all_rect.center_x,
            panel.fix_all_rect.center_y,
            color=PROBLEMS_TEXT_COLOR,
            font_size=11,
            anchor_x="center",
            anchor_y="center",
            cache=self._text_cache,
        )

        # Search line
        search_line = format_search_bar_text(query, search_focused)
        draw_text_cached(
            search_line,
            panel.search_rect.left,
            panel.search_rect.bottom + 2,
            color=PROBLEMS_TEXT_COLOR,
            font_size=11,
            cache=self._text_cache,
        )

        if not rows and total_count == 0:
            draw_text_cached(
                "No problems",
                panel.list_rect.left,
                panel.list_rect.top - PROBLEMS_LINE_HEIGHT + 2,
                color=PROBLEMS_DIM_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
        else:
            scroll_list = _build_problems_rows_scrolllist(
                rows=rows,
                panel_list_rect=Rect(
                    x=float(panel.list_rect.left),
                    y=float(panel.list_rect.bottom),
                    width=float(panel.list_rect.right - panel.list_rect.left),
                    height=float(panel.list_rect.top - panel.list_rect.bottom),
                ),
                row_height=PROBLEMS_LINE_HEIGHT,
            )
            left_pad = 6
            right_gutter = 120
            approx_char_w = max(1.0, 11 * 0.6)
            from ..editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelRow

            rows_panel = EditorPanelBase(
                Rect(
                    x=float(panel.list_rect.left),
                    y=float(panel.list_rect.bottom),
                    width=float(panel.list_rect.right - panel.list_rect.left),
                    height=float(panel.list_rect.top - panel.list_rect.bottom),
                ),
                panel_bg=(0, 0, 0, 0),
                panel_border=(0, 0, 0, 0),
                item_spacing=0.0,
                inner_padding_x=0.0,
                inner_padding_y=0.0,
            )
            for row_index, label, _row_rect, _is_selected in scroll_list.visible_rows:
                issue = rows[row_index]
                idx = start_idx + int(row_index)

                max_label_w = max(0.0, (panel.list_rect.right - right_gutter) - (panel.list_rect.left + left_pad))
                max_label_chars = int(max_label_w / approx_char_w) if max_label_w > 0 else 0
                if max_label_chars > 0 and len(label) > max_label_chars:
                    if max_label_chars >= 3:
                        label = label[: max(0, max_label_chars - 3)] + "..."
                    else:
                        label = label[:max_label_chars]

                # Right-side metadata (severity / location)
                severity = str(getattr(issue, "severity", "") or "")
                entity_id = str(getattr(issue, "entity_id", "") or "")
                if not entity_id:
                    entity_id = str(getattr(issue, "scene_id", "") or "")
                meta = severity
                if entity_id:
                    meta = f"{severity} | {entity_id}" if severity else entity_id
                row = PanelRow(
                    PanelField(
                        label,
                        meta if meta else None,
                        label_color=PROBLEMS_TEXT_COLOR if issue.fixable else PROBLEMS_DIM_COLOR,
                        value_color=PROBLEMS_DIM_COLOR,
                    ),
                    height=18.0,
                    padding_x=6.0,
                    selected_bg=PROBLEMS_SELECTED_BG,
                )
                row.set_selected(idx == int(selected_index))
                rows_panel.add_row(row)
            rows_panel.draw()

            # Scrollbar (render-only, if payload provides scroll context)
            visible_count = len(rows)
            if total_count and visible_count and total_count > visible_count:
                try:
                    total_n = int(total_count)
                    visible_n = int(visible_count)
                    start_n = int(start_idx)
                except Exception:
                    total_n = 0
                    visible_n = 0
                    start_n = 0
                if total_n > 0 and visible_n > 0 and total_n > visible_n:
                    track_left = panel.list_rect.right - 3
                    track_right = panel.list_rect.right - 1
                    track_top = panel.list_rect.top
                    track_bottom = panel.list_rect.bottom
                    _draw_rectangle_filled(
                        track_left, track_right, track_bottom, track_top, (90, 90, 100, 140)
                    )
                    track_h = max(1.0, track_top - track_bottom)
                    ratio = max(0.0, min(1.0, start_n / max(1, (total_n - visible_n))))
                    thumb_h = max(10.0, track_h * (visible_n / total_n))
                    usable_h = max(1.0, track_h - thumb_h)
                    thumb_top = track_top - (ratio * usable_h)
                    thumb_bottom = thumb_top - thumb_h
                    _draw_rectangle_filled(
                        track_left, track_right, thumb_bottom, thumb_top, (150, 150, 160, 200)
                    )

        # Detail area / Preview
        detail_y = panel.detail_rect.top - PROBLEMS_LINE_HEIGHT + 2
        issue = None
        if selected_index >= start_idx and selected_index < start_idx + len(rows):
            issue = rows[selected_index - start_idx]

        detail_lines = build_problems_preview_lines(issue, preview_open)

        for line in detail_lines:
            draw_text_cached(
                line,
                panel.detail_rect.left,
                detail_y,
                color=PROBLEMS_DIM_COLOR,
                font_size=10,
                cache=self._text_cache,
            )
            detail_y -= PROBLEMS_LINE_HEIGHT

        # Optional footer hint: Issues a-b / N
        if total_count and rows:
            try:
                total_n = int(total_count)
                start_n = int(start_idx)
                visible_n = len(rows)
            except Exception:
                total_n = 0
                start_n = 0
                visible_n = 0
            if total_n > 0 and visible_n > 0:
                a = start_n + 1
                b = min(total_n, start_n + visible_n)
                hint = f"Issues {a}-{b} / {total_n}"
                draw_text_cached(
                    hint,
                    panel.list_rect.right - 6,
                    panel.detail_rect.bottom + 2,
                    color=PROBLEMS_DIM_COLOR,
                    font_size=10,
                    anchor_x="right",
                    cache=self._text_cache,
                )


def _format_fix_desc(issue: Any) -> str:
    if not getattr(issue, "fixable", False):
        return "None"
    fix_kind = getattr(issue, "fix_kind", None)
    mapping = {
        "rename_id": "Rename duplicate ids",
        "assign_id": "Assign missing id",
        "clear_prefab": "Clear prefab reference",
        "clear_asset": "Remove missing asset",
        "sanitize_transform": "Clamp invalid transform",
    }
    return mapping.get(str(fix_kind), "Apply fix")


def format_problem_row_label(issue: Any) -> str:
    from ..editor.scene_lint_model import format_issue_risk_tag, format_issue_severity_tag

    diag_code = str(getattr(issue, "meta", {}).get("diagnostic_code", "") or "")
    severity_tag = format_issue_severity_tag(issue)
    if diag_code:
        kind = diag_code
        return f"{severity_tag} {kind}: {getattr(issue, 'message', '')}"
    else:
        tag = f"{severity_tag} {format_issue_risk_tag(issue)}"
        kind = getattr(issue, "kind", "")
    message = getattr(issue, "message", "")
    return f"{tag} {kind}: {message}"


def _build_problems_rows_scrolllist(
    rows: list[Any],
    panel_list_rect: Rect,
    row_height: float,
) -> ScrollList:
    labels = [format_problem_row_label(issue) for issue in rows]
    scroll = ScrollList(
        items=labels,
        row_height=max(1, int(row_height)),
        selected_index=0,
        scroll_offset=0.0,
    )
    scroll.layout(panel_list_rect)
    return scroll


def build_problems_preview_lines(issue: Any, preview_open: bool) -> list[str]:
    if not preview_open:
        return [
            "Enter Preview | Ctrl+Enter Apply | Shift+Enter Apply+Next | Esc Back",
            "A Preview | X Apply | B Back",
        ]
    if issue is None:
        return [
            "Enter Preview | Ctrl+Enter Apply | Shift+Enter Apply+Next | Esc Back",
            "A Preview | X Apply | B Back",
        ]
    if _is_structured_diagnostic_issue(issue):
        meta = getattr(issue, "meta", {}) if isinstance(getattr(issue, "meta", {}), dict) else {}
        source = str(meta.get("diagnostic_source", "") or "")
        location = str(meta.get("diagnostic_location", "") or "")
        hint = str(meta.get("diagnostic_hint", "") or "")
        code = str(meta.get("diagnostic_code", "") or getattr(issue, "kind", ""))
        details = [
            f"Code: {code}",
            f"Message: {getattr(issue, 'message', '')}",
        ]
        if source:
            details.append(f"Source: {source}")
        if location:
            details.append(f"Location: {location}")
        if hint:
            details.append(f"Hint: {hint}")
        details.extend(
            [
                "Fix: None (read-only diagnostic)",
                "Keys: Enter/Ctrl+Enter jump when location is supported | Esc Back",
            ]
        )
        return details
    fix_desc = _format_fix_desc(issue)
    risk_line = _format_risk_line(issue)
    manual_suffix = " (manual)" if _is_risky(issue) else ""
    return [
        f"Rule: {getattr(issue, 'issue_id', '')}",
        f"Message: {getattr(issue, 'message', '')}",
        f"Location: entity={getattr(issue, 'entity_id', '') or ''} scene={getattr(issue, 'scene_id', '') or ''}",
        risk_line,
        f"Fix: {fix_desc}",
        f"Keys: Ctrl+Enter Apply{manual_suffix} | Shift+Enter Apply+Next | Esc Back | Pad: X Apply{manual_suffix} | B Back",
    ]


def _format_risk_line(issue: Any) -> str:
    if _is_risky(issue):
        return "Risk: RISKY (skipped by Fix All Safe)"
    return "Risk: SAFE"


def _is_risky(issue: Any) -> bool:
    risk = str(getattr(issue, "risk", "safe") or "safe").strip().lower()
    return risk == "risky"


def _is_structured_diagnostic_issue(issue: Any) -> bool:
    meta = getattr(issue, "meta", None)
    if not isinstance(meta, dict):
        return False
    return bool(str(meta.get("diagnostic_code", "") or "").strip())
