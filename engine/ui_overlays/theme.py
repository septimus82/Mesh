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
    header_muted: Color
    selected_row_bg: Color
    action_text: Color
    error_text: Color
    warning_text: Color
    panel_bg: Color
    panel_border: Color
    panel_strong_bg: Color
    panel_strong_border: Color
    chrome_bg: Color
    chrome_border: Color
    chrome_accent: Color
    chrome_accent_bright: Color
    chrome_text: Color
    chrome_dim: Color
    chrome_separator: Color
    shell_bg: Color
    shell_bg_alt: Color
    menubar_bg: Color
    context_shadow: Color
    scrim_dim: Color
    scrim_dim_soft: Color
    scrim_dim_medium: Color
    black: RgbColor
    undo_selected: Color
    inspector_bg: Color
    inspector_border: Color
    inspector_selected: Color
    inspector_accent: Color
    inspector_dim: Color
    inspector_text_soft: Color
    inspector_text: Color
    input_bg: Color
    input_bg_focused: Color
    input_border: Color
    input_border_focused: Color
    field_border_idle: Color
    field_border_focus: Color
    text_dim_soft: Color
    accent_warm: Color
    tree_bg: Color
    tree_selected_bg: Color
    tree_accent: Color
    severity_info_bg: RgbColor
    severity_info_border: RgbColor
    severity_info_text: RgbColor
    browser_border: RgbColor
    browser_accent: RgbColor
    browser_white: RgbColor
    status_ok: RgbColor
    browser_text_dim: RgbColor
    browser_text: RgbColor
    browser_muted: RgbColor
    status_error: RgbColor
    status_warn: RgbColor
    overlay_white_soft: Color
    overlay_white: Color
    severity_warning_bg: RgbColor
    severity_warning_border: RgbColor
    severity_warning_text: RgbColor
    severity_error_bg: RgbColor
    severity_error_border: RgbColor
    severity_error_text: RgbColor


EDITOR_THEME = EditorTheme(
    transparent=(0, 0, 0, 0),
    text_primary=(224, 226, 233, 255),
    text_dim=(150, 152, 162, 255),
    text_header=(196, 206, 224, 255),
    header_muted=(196, 206, 224, 255),
    selected_row_bg=(70, 110, 170, 150),
    action_text=(94, 196, 255, 255),
    error_text=(255, 110, 110, 255),
    warning_text=(255, 196, 92, 255),
    panel_bg=(28, 30, 36, 250),
    panel_border=(58, 60, 68, 255),
    panel_strong_bg=(22, 23, 28, 220),
    panel_strong_border=(80, 84, 94, 255),
    chrome_bg=(34, 36, 42, 255),
    chrome_border=(58, 60, 68, 255),
    chrome_accent=(94, 196, 255, 255),
    chrome_accent_bright=(94, 196, 255, 255),
    chrome_text=(224, 226, 233, 255),
    chrome_dim=(150, 152, 162, 255),
    chrome_separator=(80, 84, 94, 255),
    shell_bg=(38, 40, 47, 255),
    shell_bg_alt=(42, 44, 52, 255),
    menubar_bg=(34, 36, 42, 255),
    context_shadow=(0, 0, 0, 120),
    scrim_dim=(0, 0, 0, 180),
    scrim_dim_soft=(0, 0, 0, 120),
    scrim_dim_medium=(0, 0, 0, 180),
    black=(0, 0, 0),
    undo_selected=(70, 110, 170, 80),
    inspector_bg=(38, 40, 47, 255),
    inspector_border=(80, 84, 94, 255),
    inspector_selected=(70, 110, 170, 180),
    inspector_accent=(94, 196, 255, 255),
    inspector_dim=(150, 152, 162, 255),
    inspector_text_soft=(150, 152, 162, 255),
    inspector_text=(224, 226, 233, 255),
    input_bg=(18, 20, 25, 190),
    input_bg_focused=(24, 27, 33, 220),
    input_border=(58, 60, 68, 140),
    input_border_focused=(94, 196, 255, 180),
    field_border_idle=(58, 60, 68, 120),
    field_border_focus=(94, 196, 255, 180),
    text_dim_soft=(150, 152, 162, 200),
    accent_warm=(255, 196, 92, 255),
    tree_bg=(34, 36, 42, 255),
    tree_selected_bg=(70, 110, 170, 128),
    tree_accent=(94, 196, 255, 255),
    severity_info_bg=(22, 32, 42),
    severity_info_border=(94, 196, 255),
    severity_info_text=(224, 226, 233),
    browser_border=(80, 84, 94),
    browser_accent=(94, 196, 255),
    browser_white=(224, 226, 233),
    status_ok=(120, 210, 120),
    browser_text_dim=(150, 152, 162),
    browser_text=(224, 226, 233),
    browser_muted=(150, 152, 162),
    status_error=(255, 110, 110),
    status_warn=(255, 196, 92),
    overlay_white_soft=(255, 255, 255, 40),
    overlay_white=(255, 255, 255, 50),
    severity_warning_bg=(46, 36, 20),
    severity_warning_border=(255, 196, 92),
    severity_warning_text=(224, 226, 233),
    severity_error_bg=(50, 24, 28),
    severity_error_border=(255, 110, 110),
    severity_error_text=(224, 226, 233),
)
