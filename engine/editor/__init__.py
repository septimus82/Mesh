"""Editor package - extracted modules from editor_controller.py."""

from __future__ import annotations

# Re-export state classes and constants for convenience
from .state import (
    ENTITY_PANEL_FIELDS,
    ENTITY_PANEL_FOCUS_INSPECTOR,
    ENTITY_PANEL_FOCUS_OUTLINER,
    SCENE_SWITCHER_RECENT_LIMIT,
    TOOL_MODE_MOVE,
    TOOL_MODE_PATH,
    TOOL_MODE_ZONE,
    EditorDirtyState,
    EditorPlaySession,
)

from .prefab_palette_panel import (
    apply_entity_panel_tag_delta,
    filter_prefab_palette_items,
    normalize_entity_panel_tags,
    palette_tag_frequencies,
    parse_palette_filter,
)

from .dialogue_panel import (
    apply_dialogue_edit_to_root,
    build_dialogue_nodes_list,
    collect_dialogue_warnings,
    entity_has_dialogue,
    get_dialogue_edit_value,
    get_entity_dialogue_config,
    next_dialogue_field,
    prev_dialogue_field,
)

from .animation_panel import (
    apply_animator_runtime,
    cycle_animation_mode,
    entity_has_animator,
    get_animation_names,
    get_animator_config,
    next_animation_field,
    prev_animation_field,
)

from .scene_opening import (
    apply_scene_switcher_filter,
    build_scene_browser_lines,
    build_scene_switcher_lines,
    build_scene_switcher_rows,
    clamp_scene_selection_index,
    compute_scene_browser_hit_index,
    compute_scene_browser_layout,
    compute_scene_window,
    open_scene_by_id,
)

from .entity_panels import (
    build_inspector_lines,
    build_outliner_lines,
    clamp_entity_panels_index,
    compute_outliner_scroll_window,
    filter_entity_panels_items,
    format_entity_field_value,
    get_entity_numeric_value,
    resolve_entity_panels_id,
)

from .asset_browser_panel import (
    ASSET_BROWSER_KINDS,
    build_asset_browser_lines,
    clamp_asset_selection_index,
    compute_asset_browser_window,
    cycle_asset_browser_kind,
    filter_assets_for_browser,
    move_asset_selection,
    resolve_asset_activation,
)

from .editor_shell_layout import (
    BOTTOM_BAR_HEIGHT,
    DOCK_MAX_W,
    DOCK_MIN_W,
    DOCK_WIDTH,
    SPLITTER_W,
    TAB_HEADER_HEIGHT,
    TAB_PADDING,
    TOP_BAR_HEIGHT,
    TOP_BAR_BUTTON_H,
    TOP_BAR_BUTTON_MARGIN,
    TOP_BAR_BUTTON_RIGHT_OFFSET,
    TOP_BAR_BUTTON_W,
    VIEWPORT_MIN_W,
    DockSizing,
    DockTabRects,
    DockTabState,
    EditorShellLayout,
    Rect,
    TopBarControls,
    clamp_dock_width,
    clamp_rects_to_window,
    compute_dock_tab_rects,
    compute_editor_shell_layout,
    compute_top_bar_controls,
    get_dock_tab_options,
    hit_test_dock_tab,
    hit_test_splitter,
    hit_test_top_bar_controls,
    resolve_effective_dock_widths,
)

from .editor_transform_ops import (
    MoveEntityCommand,
    MoveEntitiesCommand,
    apply_move_command,
    apply_group_move_command,
    apply_snap_to_xy,
    compute_dragged_xy,
    create_move_command_from_drag,
    create_group_move_command_from_drag,
    invert_move_command,
    invert_group_move_command,
    resolve_entity_id_for_sprite,
)

from .editor_multiselect_ops import (
    clear_selection,
    get_primary_id,
    is_entity_selected,
    select_single,
    toggle_selection,
)

from .menu_bar_model import (
    MENU_BAR_HEIGHT,
    MenuBarLayout,
    MenuGroup,
    MenuItem,
    MenuRect,
    build_menu_groups,
    compute_menu_bar_layout,
    get_dropdown_bounds,
    hit_test_menu_bar,
    hit_test_menu_item,
    hit_test_menu_title,
)

from .context_menu_model import (
    CONTEXT_MENU_WIDTH,
    ContextMenuItem,
    ContextMenuLayout,
    ContextMenuRect,
    build_context_menu_items,
    compute_context_menu_layout,
    hit_test_context_menu,
    hit_test_context_menu_bounds,
)

from .editor_clipboard_ops import (
    clone_entity_payload,
    collect_existing_entity_ids,
    generate_copy_entity_id,
    get_entity_id_from_data,
)

from .inspector_components_model import (
    COMPONENT_SECTIONS,
    NUMERIC_STEP_NORMAL,
    NUMERIC_STEP_SHIFT,
    ComponentRow,
    ComponentSection,
    InspectorCursor,
    apply_inspector_edit,
    build_inspector_sections,
    clamp_inspector_cursor,
    format_field_value,
    get_cursor_row,
    move_cursor,
    toggle_section,
)

from .editor_cursor_model import (
    CursorHintResult,
    build_cursor_hint,
)

from .panel_search_model import (
    format_search_bar_text,
)

from .undo_history_model import (
    UndoEntry,
    build_undo_history_entries,
    clamp_history_cursor,
    compute_history_window,
    filter_undo_history_entries,
    resolve_jump_delta,
)

__all__ = [
    # State
    "EditorDirtyState",
    "EditorPlaySession",
    "TOOL_MODE_MOVE",
    "TOOL_MODE_PATH",
    "TOOL_MODE_ZONE",
    "ENTITY_PANEL_FOCUS_OUTLINER",
    "ENTITY_PANEL_FOCUS_INSPECTOR",
    "ENTITY_PANEL_FIELDS",
    "SCENE_SWITCHER_RECENT_LIMIT",
    # Prefab palette
    "parse_palette_filter",
    "filter_prefab_palette_items",
    "palette_tag_frequencies",
    "normalize_entity_panel_tags",
    "apply_entity_panel_tag_delta",
    # Dialogue panel
    "get_entity_dialogue_config",
    "entity_has_dialogue",
    "build_dialogue_nodes_list",
    "collect_dialogue_warnings",
    "next_dialogue_field",
    "prev_dialogue_field",
    "get_dialogue_edit_value",
    "apply_dialogue_edit_to_root",
    # Animation panel
    "entity_has_animator",
    "get_animator_config",
    "get_animation_names",
    "apply_animator_runtime",
    "next_animation_field",
    "prev_animation_field",
    "cycle_animation_mode",
    # Scene opening
    "build_scene_switcher_rows",
    "apply_scene_switcher_filter",
    "clamp_scene_selection_index",
    "compute_scene_window",
    "compute_scene_browser_layout",
    "compute_scene_browser_hit_index",
    "build_scene_switcher_lines",
    "build_scene_browser_lines",
    "open_scene_by_id",
    # Entity panels
    "filter_entity_panels_items",
    "clamp_entity_panels_index",
    "resolve_entity_panels_id",
    "build_outliner_lines",
    "build_inspector_lines",
    "format_entity_field_value",
    "get_entity_numeric_value",
    "compute_outliner_scroll_window",
    # Asset browser panel
    "ASSET_BROWSER_KINDS",
    "filter_assets_for_browser",
    "clamp_asset_selection_index",
    "compute_asset_browser_window",
    "build_asset_browser_lines",
    "cycle_asset_browser_kind",
    "resolve_asset_activation",
    "move_asset_selection",
    # Editor shell layout
    "TOP_BAR_HEIGHT",
    "BOTTOM_BAR_HEIGHT",
    "DOCK_WIDTH",
    "DOCK_MIN_W",
    "DOCK_MAX_W",
    "VIEWPORT_MIN_W",
    "SPLITTER_W",
    "TAB_HEADER_HEIGHT",
    "TAB_PADDING",
    "TOP_BAR_BUTTON_W",
    "TOP_BAR_BUTTON_H",
    "TOP_BAR_BUTTON_MARGIN",
    "TOP_BAR_BUTTON_RIGHT_OFFSET",
    "Rect",
    "EditorShellLayout",
    "DockSizing",
    "DockTabState",
    "DockTabRects",
    "TopBarControls",
    "compute_editor_shell_layout",
    "clamp_dock_width",
    "clamp_rects_to_window",
    "get_dock_tab_options",
    "compute_dock_tab_rects",
    "compute_top_bar_controls",
    "hit_test_dock_tab",
    "hit_test_splitter",
    "hit_test_top_bar_controls",
    "resolve_effective_dock_widths",
    # Transform ops
    "MoveEntityCommand",
    "MoveEntitiesCommand",
    "compute_dragged_xy",
    "apply_snap_to_xy",
    "apply_move_command",
    "apply_group_move_command",
    "invert_move_command",
    "invert_group_move_command",
    "resolve_entity_id_for_sprite",
    "create_move_command_from_drag",
    "create_group_move_command_from_drag",
    # Multiselect ops
    "toggle_selection",
    "select_single",
    "get_primary_id",
    "is_entity_selected",
    "clear_selection",
    # Menu bar
    "MENU_BAR_HEIGHT",
    "MenuRect",
    "MenuItem",
    "MenuGroup",
    "MenuBarLayout",
    "build_menu_groups",
    "compute_menu_bar_layout",
    "hit_test_menu_title",
    "hit_test_menu_item",
    "hit_test_menu_bar",
    "get_dropdown_bounds",
    # Context menu
    "CONTEXT_MENU_WIDTH",
    "ContextMenuRect",
    "ContextMenuItem",
    "ContextMenuLayout",
    "build_context_menu_items",
    "compute_context_menu_layout",
    "hit_test_context_menu",
    "hit_test_context_menu_bounds",
    # Clipboard ops
    "generate_copy_entity_id",
    "clone_entity_payload",
    "get_entity_id_from_data",
    "collect_existing_entity_ids",
    # Inspector components model
    "COMPONENT_SECTIONS",
    "NUMERIC_STEP_NORMAL",
    "NUMERIC_STEP_SHIFT",
    "ComponentRow",
    "ComponentSection",
    "InspectorCursor",
    "build_inspector_sections",
    "toggle_section",
    "clamp_inspector_cursor",
    "get_cursor_row",
    "move_cursor",
    "apply_inspector_edit",
    "format_field_value",
    # Cursor hint model
    "CursorHintResult",
    "build_cursor_hint",
    # Panel search
    "format_search_bar_text",
    # Undo history
    "UndoEntry",
    "build_undo_history_entries",
    "clamp_history_cursor",
    "compute_history_window",
    "filter_undo_history_entries",
    "resolve_jump_delta",
]
