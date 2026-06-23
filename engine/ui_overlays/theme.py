"""Editor overlay design tokens.

The consolidation phase keeps these values byte-identical to the existing
overlay constants. Visual retuning belongs in a later, explicit slice.
"""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int, int]
RgbColor = tuple[int, int, int]


@dataclass(frozen=True)
class EditorTheme:
    transparent: Color
    text_primary: Color
    text_dim: Color
    text_header: Color
    selected_row_bg: Color
    action_text: Color
    error_text: Color
    warning_text: Color
    panel_bg: Color
    panel_border: Color
    chrome_bg: Color
    chrome_border: Color
    input_bg: Color
    input_bg_focused: Color
    input_border: Color
    input_border_focused: Color
    severity_info_bg: RgbColor
    severity_info_border: RgbColor
    severity_info_text: RgbColor
    severity_warning_bg: RgbColor
    severity_warning_border: RgbColor
    severity_warning_text: RgbColor
    severity_error_bg: RgbColor
    severity_error_border: RgbColor
    severity_error_text: RgbColor


EDITOR_THEME = EditorTheme(
    transparent=(0, 0, 0, 0),
    text_primary=(220, 220, 230, 255),
    text_dim=(150, 150, 160, 255),
    text_header=(200, 210, 230, 255),
    selected_row_bg=(90, 140, 200, 140),
    action_text=(100, 200, 255, 255),
    error_text=(255, 120, 120, 255),
    warning_text=(255, 200, 60, 255),
    panel_bg=(35, 35, 40, 250),
    panel_border=(60, 60, 70, 255),
    chrome_bg=(30, 30, 35, 255),
    chrome_border=(60, 60, 70, 255),
    input_bg=(22, 22, 28, 190),
    input_bg_focused=(30, 30, 36, 220),
    input_border=(90, 90, 100, 140),
    input_border_focused=(100, 200, 255, 180),
    severity_info_bg=(32, 36, 44),
    severity_info_border=(150, 190, 255),
    severity_info_text=(255, 255, 255),
    severity_warning_bg=(64, 44, 20),
    severity_warning_border=(255, 191, 92),
    severity_warning_text=(255, 244, 224),
    severity_error_bg=(72, 24, 24),
    severity_error_border=(255, 110, 110),
    severity_error_text=(255, 255, 255),
)
