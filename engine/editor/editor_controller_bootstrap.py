from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.asset_index import AssetRow

from ..behaviours.utils import ZONE_TARGET_TRIGGER
from ..editor_entity_ops import EntitySummary
from ..editor_light_occluder_ops import COOKIE_PRESETS, LIGHT_COLOR_PRESETS
from .editor_align_controller import EditorAlignController
from .editor_animation_controller import EditorAnimationController
from .editor_asset_browser_controller import EditorAssetBrowserController
from .editor_clipboard_controller import EditorClipboardController
from .editor_command_dispatch_controller import EditorCommandDispatchController
from .editor_cursor_controller import EditorCursorController
from .editor_debug_overlay_controller import EditorDebugOverlayController
from .editor_debug_panels_controller import EditorDebugPanelsController
from .editor_dialogue_controller import EditorDialogueController
from .editor_dock_controller import EditorDockController
from .editor_draw_controller import EditorDrawController
from .editor_duplicate_controller import EditorDuplicateController
from .editor_entity_ops_controller import EditorEntityOpsController
from .editor_entity_panels_controller import EditorEntityPanelsController
from .editor_file_ops_controller import EditorFileOpsController
from .editor_find_actions_controller import EditorFindActionsController
from .editor_hd2d_controller import EditorHd2dController
from .editor_hierarchy_controller import EditorHierarchyController
from .editor_history_controller import EditorHistoryController
from .editor_hover_state_controller import EditorHoverStateController
from .editor_inspector_controller import EditorInspectorController
from .editor_keymap_controller import EditorKeymapController
from .editor_lights_controller import EditorLightsController
from .editor_marquee_controller import EditorMarqueeController
from .editor_overlay_controller import EditorOverlayController
from .editor_palette_controller import EditorPaletteController
from .editor_panels_controller import EditorPanelsController
from .editor_play_controller import EditorPlayController
from .editor_prefab_controller import EditorPrefabController
from .editor_problems_actions_controller import EditorProblemsActionsController
from .editor_problems_controller import ProblemsController
from .editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)
from .editor_project_explorer_controller import ProjectExplorerController
from .editor_providers_controller import EditorProvidersController
from .editor_scene_browse_controller import EditorSceneBrowseController
from .editor_scene_open_controller import EditorSceneOpenController
from .editor_scene_ops import EditorSceneOpsController
from .editor_search_controller import EditorSearchController
from .editor_selection_controller import EditorSelectionController
from .editor_session_controller import EditorSessionController
from .editor_shape_controller import EditorShapeController
from .editor_tile_controller import EditorTileController
from .editor_tool_controller import EditorToolController
from .editor_ui_flow_controller import EditorUIFlowController
from .editor_undo_controller import EditorUndoController
from .editor_unsaved_changes_controller import EditorUnsavedChangesController
from .editor_workspace_controller import EditorWorkspaceController
from .state import (
    ENTITY_PANEL_FOCUS_OUTLINER,
    TOOL_MODE_MOVE,
    TRANSFORM_MODE_MOVE,
    EditorDirtyState,
    EditorPlaySession,
)


def bootstrap_dependencies(controller: Any) -> None:
    controller._workspace_ctl = EditorWorkspaceController(controller)
    controller._selection_ctl = EditorSelectionController(controller)
    controller._scene_ops = EditorSceneOpsController(controller)
    controller.undo = EditorUndoController(controller, max_history=50)
    controller._ui_flow_ctl = EditorUIFlowController(controller)
    controller.search = EditorSearchController(controller, controller._ui_flow_ctl)
    controller._file_ops_ctl = EditorFileOpsController(controller)
    controller.session = EditorSessionController()

    from engine.editor.editor_focus_controller import EditorFocusController  # noqa: PLC0415

    controller.focus = EditorFocusController(controller)
    controller.project_explorer = ProjectExplorerController(controller._get_repo_root())
    controller.project_explorer_actions = EditorProjectExplorerActionsController(controller)
    controller.scene_browse = EditorSceneBrowseController(controller)
    controller.scene_open = EditorSceneOpenController(controller)
    controller.problems = ProblemsController(include_structured_diagnostics=True)
    controller.panels = EditorPanelsController(controller)
    controller.providers = EditorProvidersController(controller)
    controller.unsaved_confirm = EditorUnsavedChangesController(controller)
    controller.dialogue = EditorDialogueController(controller)
    controller.debug_panels = EditorDebugPanelsController(controller)
    controller.debug_overlay = EditorDebugOverlayController(controller)
    controller.overlay = EditorOverlayController(controller)
    controller.tool = EditorToolController(controller)
    controller.animation = EditorAnimationController(controller)
    controller.tile = EditorTileController(controller)
    controller.lights = EditorLightsController(controller)
    controller.shape = EditorShapeController(controller)
    controller.palette = EditorPaletteController(controller)
    controller.prefab = EditorPrefabController(controller)
    controller.inspector = EditorInspectorController(controller)
    controller.clipboard = EditorClipboardController(controller)
    controller.hd2d = EditorHd2dController(controller)
    controller.duplicate = EditorDuplicateController(controller)
    controller.marquee = EditorMarqueeController(controller)
    controller.play = EditorPlayController(controller)
    controller.keymap = EditorKeymapController(controller)
    controller.entity_panels_controller = EditorEntityPanelsController(controller)
    controller.hierarchy = EditorHierarchyController(controller)
    controller.asset_browser = EditorAssetBrowserController(controller)
    controller.draw = EditorDrawController(controller)
    controller.cursor = EditorCursorController(controller)
    controller.problems_actions = EditorProblemsActionsController(controller)
    controller.find_actions = EditorFindActionsController(controller)
    controller.entity_ops = EditorEntityOpsController(controller)
    controller.command_dispatch = EditorCommandDispatchController(controller)
    controller.align = EditorAlignController(controller)


def bootstrap_browser_state(controller: Any) -> None:
    controller._multiselect_drag_starts = {}

    controller.inspector_active = False
    controller.inspector_selection_index = 0
    controller._cached_inspector_items = []
    controller._last_entity_revision = 0

    controller.entity_panels_active = False
    controller.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
    controller.entity_panels_filter = ""
    controller.entity_panels_filter_active = False
    controller.entity_panels_selection_index = 0
    controller.entity_panels_inspector_index = 0
    controller.entity_panels_text_edit_active = False
    controller.entity_panels_text_field = None
    controller.entity_panels_text_buffer = ""
    controller._cached_entity_panels_list = []
    controller._entity_panels_selected_id = None

    controller.scene_switcher_active = False
    controller.scene_switcher_query = ""
    controller.scene_switcher_index = 0
    controller._scene_switcher_cached = []

    controller.scene_browser_active = False
    controller.scene_browser_query = ""
    controller.scene_browser_index = 0
    controller._scene_browser_cached_rows = []

    controller.asset_browser_active = False
    controller.asset_browser_filter = ""
    controller.asset_browser_kind = "All"
    controller.asset_browser_selection_index = 0
    controller._asset_browser_cached_rows = []
    controller._asset_browser_filtered_rows = []

    controller.history = EditorHistoryController(controller)


def bootstrap_runtime_state(controller: Any) -> None:
    controller._menu_active = None

    controller._context_menu_x = 0.0
    controller._context_menu_y = 0.0

    controller.dock = EditorDockController(controller.session, left_tab="Outliner", right_tab="Inspector")
    controller.hover = EditorHoverStateController(controller.dock)

    controller._inspector_sections_expanded = {}
    controller._inspector_cursor = ("transform", 0)
    controller._inspector_text_edit_active = False
    controller._inspector_text_buffer = ""

    controller._component_inspector_index = 0
    controller._add_component_picker_active = False
    controller._add_component_picker_index = 0
    controller._add_component_picker_options = []

    controller._hd2d_batch_radius_px = 96

    controller.tool_mode = TOOL_MODE_MOVE
    controller.transform_mode = TRANSFORM_MODE_MOVE
    controller.selected_waypoint_index = -1
    controller.zone_behaviour_index = 0
    controller.zone_edit_target = ZONE_TARGET_TRIGGER

    controller._rotate_drag_active = False
    controller._scale_drag_active = False
    controller._transform_drag_pivot = None
    controller._transform_drag_mouse_start = None
    controller._transform_drag_start_rots = {}
    controller._transform_drag_start_scales = {}

    controller._move_preview_delta_xy = None
    controller._rotate_preview_delta_deg = None
    controller._scale_preview_factor = None
    controller._transform_snap_active = False

    controller.dirty_state = EditorDirtyState()
    controller.play_session = EditorPlaySession()

    controller.hierarchy_active = False
    controller.hierarchy_filter = ""
    controller.hierarchy_selection_index = 0
    controller.hierarchy_filter_active = False
    controller.hierarchy_rename_active = False
    controller.hierarchy_rename_buffer = ""
    controller._cached_hierarchy_list = []
    controller._hierarchy_name_cache = {}

    controller.dialogue_panel_active = False
    controller.dialogue_selected_node = 0
    controller.dialogue_selected_choice = 0
    controller.dialogue_field_focus = "node_text"
    controller.dialogue_editing = False
    controller.dialogue_edit_buffer = ""
    controller._cached_dialogue_nodes = []
    controller._dialogue_warnings = []

    controller.animation_active = False
    controller.animation_selected_index = 0
    controller.animation_field_focus = "mode"
    controller.animation_editing = False
    controller.animation_edit_buffer = ""
    controller._cached_animation_names = []

    controller.tile_panel_active = False
    controller.tile_palette = []
    controller.tile_palette_index = 0
    controller.tile_layer_index = 0
    controller.tile_layers = []

    controller.lights_tool_active = False
    controller.lights_selection = None
    controller.lights_dragging = False
    controller.lights_drag_start = None
    controller.lights_original_pos = None
    controller._light_color_palette = list(LIGHT_COLOR_PRESETS)
    controller._light_cookie_palette = list(COOKIE_PRESETS)
    controller.light_property_index = 0
    controller._light_property_defs = [
        {"name": "radius_px", "key": "radius", "default": 160.0, "step": 4.0, "min": 8.0},
        {"name": "flicker_amount", "key": "flicker_amount", "default": 0.0, "step": 0.05, "min": 0.0, "max": 1.0},
        {"name": "flicker_speed", "key": "flicker_speed", "default": 1.0, "step": 0.25, "min": 0.0},
        {"name": "cookie_scale", "key": "cookie_scale", "default": 1.0, "step": 0.1, "min": 0.0},
        {"name": "cookie_rotation_deg", "key": "cookie_rotation_deg", "default": 0.0, "step": 5.0, "wrap": 360.0},
    ]
    controller.lighting_preset_label = None
    controller.lighting_preset_until = 0.0

    controller.occluder_tool_active = False
    controller.occluder_points = []
    controller.occluder_selection = None
    controller.occluder_vertex_selection = None
    controller.occluder_dragging = False
    controller.occluder_drag_origin = None

    controller.asset_place_active = False
    controller.asset_place_path = None
    controller.asset_place_kind = None

    controller.snap_enabled = False
    controller.snap_mode = "grid16"

    controller._ghost_originals_enabled = True
    controller._ghost_originals_alpha = 90
    controller._ghost_originals_dim_scale = 0.65
    controller._hd2d_default_preset_id = None


def bootstrap_overlay_state(controller: Any) -> None:
    controller.shape_edit_mode = None
    controller.shape_edit_points = []
    controller.shape_edit_original = []
    controller.shape_edit_entity = None
    controller.shape_drag_index = -1
    controller.shape_snap_enabled = False
    controller._status_message = None
    controller._status_until = 0.0
    controller._show_swallowed_exceptions_overlay = False
    controller._swallowed_exceptions_overlay_summary = "no swallowed exceptions recorded"
    controller._swallowed_exceptions_overlay_distinct_sites = 0
    controller._swallowed_exceptions_overlay_total_count = 0
    controller._swallowed_exceptions_overlay_next_refresh_ts = 0.0

    controller._overlay_text_obj = optional_arcade.arcade.Text(
        text="",
        x=10,
        y=0,
        color=optional_arcade.arcade.color.YELLOW,
        font_size=12,
        font_name="Consolas",
        multiline=True,
        width=400,
    )
    controller._palette_text_obj = optional_arcade.arcade.Text(
        text="",
        x=0,
        y=0,
        color=optional_arcade.arcade.color.WHITE,
        font_size=12,
        font_name="Consolas",
        multiline=True,
        width=200,
    )
