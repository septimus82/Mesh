from __future__ import annotations

from pathlib import Path
import re


EDITOR_CONTROLLER_PATH = Path("engine/editor_controller.py")
EDITOR_DIR = Path("engine/editor")
BASELINE_NONEMPTY_LINES = 1142
DRAW_OVERLAY_MAX_LINES = 331


def _read_editor_controller_text() -> str:
    return EDITOR_CONTROLLER_PATH.read_text(encoding="utf-8")


def test_editor_controller_line_count_does_not_increase() -> None:
    text = _read_editor_controller_text()
    nonempty = [line for line in text.splitlines() if line.strip()]
    assert len(nonempty) <= BASELINE_NONEMPTY_LINES


def test_editor_controller_does_not_import_extracted_overlays() -> None:
    """Ensure editor_controller doesn't import overlay modules directly.
    
    Attribute assignments (self.X_overlay = None) for wiring purposes are allowed.
    Only actual imports of these overlay modules are forbidden.
    """
    text = _read_editor_controller_text()
    forbidden_imports = (
        "from engine.editor.keybinds_overlay",
        "import keybinds_overlay",
        "from engine.editor.confirm_modal_overlay",
        "import confirm_modal_overlay",
        "from engine.editor.project_explorer_context_menu_overlay",
        "import project_explorer_context_menu_overlay",
        "from engine.editor.problems_panel_overlay",
        "import problems_panel_overlay",
    )
    for token in forbidden_imports:
        assert token not in text


def test_editor_controller_does_not_reference_dock_tab_fields() -> None:
    text = _read_editor_controller_text()
    forbidden = (
        "_left_dock_tab",
        "_right_dock_tab",
    )
    for token in forbidden:
        assert token not in text


def test_no_direct_dock_tab_access() -> None:
    forbidden = (
        ".dock.left_tab",
        ".dock.right_tab",
    )
    for path in Path("engine").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                raise AssertionError(f"Direct dock tab access found in {path}: {token}")


def test_editor_focus_model_uses_dock_focus_helper() -> None:
    text = Path("engine/editor/editor_focus_model.py").read_text(encoding="utf-8")
    assert "derive_focus_from_dock" in text


def test_editor_controller_does_not_define_provider_builders() -> None:
    text = _read_editor_controller_text()
    patterns = (
        r"def _build_.*provider",
        r"def _get_.*provider_payload",
    )
    for pattern in patterns:
        assert re.search(pattern, text) is None


def test_editor_controller_does_not_define_modal_flags() -> None:
    text = _read_editor_controller_text()
    forbidden = (
        "command_palette_active",
        "_context_menu_open",
        "keybinds_open",
    )
    for token in forbidden:
        assert token not in text


def test_draw_overlay_delegates_to_panels() -> None:
    text = _read_editor_controller_text()
    assert "self.overlay.draw_overlay" in text
    overlay_text = Path("engine/editor/editor_overlay_controller.py").read_text(encoding="utf-8")
    assert "panels.draw_panels" in overlay_text
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith("    def draw_overlay"):
            start = idx
            break
    assert start is not None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("    def "):
            end = idx
            break
    assert (end - start) <= DRAW_OVERLAY_MAX_LINES


def test_no_modal_flag_strings_anywhere() -> None:
    """Ensure modal flag patterns are not used as attribute reads in editor modules.
    
    Function/method definitions containing these strings are allowed.
    Attribute assignments to these names are allowed (e.g., self.xxx = ...).
    """
    forbidden_attrs = (
        "command_palette_active",
        "keybinds_open",
        "confirm_modal_open",
    )
    # Files that are allowed to read these flags
    allowed = {
        Path("engine/editor/editor_panels_controller.py"),  # Defines query methods
        Path("engine/editor/editor_session_controller.py"),
    }
    import re
    for path in EDITOR_DIR.rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for attr in forbidden_attrs:
            # Match attribute reads like .command_palette_active or ["command_palette_active"]
            # but not function definitions or assignments
            read_pattern = rf'(?<!["\'])\.{attr}\b|getattr\([^)]*["\']{attr}'
            if re.search(read_pattern, text):
                raise AssertionError(f"{attr} attribute read found in {path}")


def test_no_ui_layers_modal_reads_outside_panels() -> None:
    allowed = {
        Path("engine/editor/editor_panels_controller.py"),
        Path("engine/editor/editor_panels_query.py"),
        Path("engine/editor_ui_layer_stack_controller.py"),
        Path("engine/ui_layer_stack_model.py"),
    }
    patterns = (
        "ui_layers.is_visible",
        "ui_layers.dispatch_input",
        "ui_layers.dispatch_text",
        "active_modal_id",
    )
    for path in Path("engine").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if any(pat in text for pat in patterns):
            raise AssertionError(f"ui_layers modal read in {path}")


def test_editor_controller_instantiates_session_controller() -> None:
    text = _read_editor_controller_text()
    assert "EditorSessionController" in text


def test_no_legacy_session_flag_reads_in_focus_router_tooltips() -> None:
    banned = (
        "tile_paint_active",
        "entity_paint_active",
        "capture_mode_active",
        "authoring_selected_active",
    )
    files = (
        Path("engine/editor_runtime/editor_input_router.py"),
        Path("engine/editor/editor_focus_model.py"),
        Path("engine/editor_tooltips_model.py"),
        Path("engine/editor_runtime/hover_detection.py"),
        Path("engine/editor_hover_highlight_model.py"),
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token} found in {path}"


def test_no_session_fallback_patterns_in_readers() -> None:
    files = (
        Path("engine/editor_runtime/editor_input_router.py"),
        Path("engine/editor/editor_focus_model.py"),
        Path("engine/editor_tooltips_model.py"),
        Path("engine/editor_runtime/hover_detection.py"),
        Path("engine/editor_hover_highlight_model.py"),
    )
    patterns = (
        r"hasattr\([^,]+,\s*['\"]session['\"]",
        r"getattr\([^,]+,\s*['\"]session['\"]",
        r"_get_state\(",
        r"collected_state\[",
        r"\[['\"]session['\"]\]",
        r"state\.get\(['\"]session['\"]",
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert re.search(pattern, text) is None, f"session fallback found in {path}"


def test_readers_use_session_snapshot() -> None:
    files = (
        Path("engine/editor_runtime/editor_input_router.py"),
        Path("engine/editor/editor_focus_model.py"),
        Path("engine/editor_tooltips_model.py"),
        Path("engine/editor_runtime/hover_detection.py"),
        Path("engine/editor_hover_highlight_model.py"),
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "get_session_snapshot" in text:
            continue
        if "derive_focus_target_for_controller" in text:
            continue
        assert ".get_snapshot" in text, f"session snapshot not referenced in {path}"


def test_no_legacy_session_flag_reads_outside_session_modules() -> None:
    banned = (
        "tile_paint_active",
        "entity_paint_active",
        "capture_mode_active",
        "authoring_selected_active",
    )
    allowed = {
        Path("engine/editor/editor_session_controller.py"),
        Path("engine/editor/editor_session_model.py"),
        Path("engine/editor_controller.py"),
        Path("engine/editor/editor_tile_controller.py"),
        Path("engine/input_runtime/capture_key_router.py"),
        Path("engine/input_runtime/capture_key_router_handlers_entity_paint.py"),
        Path("engine/input_runtime/capture_key_router_handlers_palette.py"),
        Path("engine/input_runtime/capture_focus_query.py"),
        Path("engine/entity_select_mode.py"),
        Path("engine/tooling/authoring_snippets.py"),
    }
    for path in Path("engine").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token} found in {path}"


def test_collect_editor_state_only_in_focus_model() -> None:
    allowed = {
        Path("engine/editor/editor_focus_model.py"),
    }
    for path in Path("engine").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "collect_editor_state(" in text:
            raise AssertionError(f"collect_editor_state usage found in {path}")


def test_command_palette_state_access_only_in_allowed_modules() -> None:
    allowed = {
        Path("engine/editor/editor_search_controller.py"),
        Path("engine/editor/editor_command_palette_controller.py"),
        Path("engine/editor/editor_actions.py"),
        Path("engine/editor_runtime/editor_input_text_handlers.py"),
        Path("engine/ui_overlays/providers.py"),
        Path("engine/command_palette_controller.py"),
        Path("engine/game.py"),
        Path("engine/input_runtime/capture_runtime.py"),
    }
    tokens = ("command_palette_query", "command_palette_index")
    for path in Path("engine").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                raise AssertionError(f"{token} usage found in {path}")
