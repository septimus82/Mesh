from __future__ import annotations

import copy
import importlib
import json
import os
import time
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Tuple
import engine.optional_arcade as optional_arcade

from engine.asset_index import AssetRow
from engine.asset_place_overlay import draw_asset_placement_ghost
from engine.repo_root import get_repo_root

from .behaviours import get_behaviour_param_defs
from .behaviours.utils import (
    HITBOX_CANONICAL,
    HITBOX_CLASSNAMES,
    TRIGGER_ZONE_CANONICAL,
    TRIGGER_ZONE_CLASSNAMES,
    ZONE_TARGET_HITBOX,
    ZONE_TARGET_TRIGGER,
    describe_zone_behaviour,
)
from .editor_palette import DEFAULT_PREFAB_PATH
from .editor_entity_ops import EntitySummary
from .editor_prefab_variant_ops import DiffRow
from .editor_runtime import input as editor_input
from .editor_runtime import ops as editor_ops
from engine.editor.editor_search_controller import EditorSearchController
from engine.editor.editor_file_ops_controller import EditorFileOpsController
from engine.editor.editor_project_explorer_controller import ProjectExplorerController
from engine.editor.editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)
from engine.editor.editor_entity_panels_controller import EditorEntityPanelsController
from engine.editor.editor_hierarchy_controller import EditorHierarchyController
from engine.editor.editor_draw_controller import EditorDrawController
from engine.editor.editor_cursor_controller import EditorCursorController
from engine.editor.editor_problems_actions_controller import EditorProblemsActionsController
from engine.editor.editor_find_actions_controller import EditorFindActionsController
from engine.editor.editor_entity_ops_controller import EditorEntityOpsController
from engine.editor.editor_command_dispatch_controller import EditorCommandDispatchController
from engine.editor.editor_align_controller import EditorAlignController
from engine.editor.editor_scene_browse_controller import EditorSceneBrowseController
from engine.editor.editor_scene_open_controller import EditorSceneOpenController
from engine.editor.editor_problems_controller import ProblemsController
from engine.editor.editor_panels_controller import EditorPanelsController
from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.editor_hover_state_controller import EditorHoverStateController
from engine.editor.editor_history_controller import EditorHistoryController
from engine.editor.editor_inspector_controller import EditorInspectorController
from engine.editor.editor_dialogue_controller import EditorDialogueController
from engine.editor.editor_debug_panels_controller import EditorDebugPanelsController
from engine.editor.editor_debug_overlay_controller import EditorDebugOverlayController
from engine.editor.editor_overlay_controller import EditorOverlayController
from engine.editor.editor_tool_controller import EditorToolController
from engine.editor.editor_animation_controller import EditorAnimationController
from engine.editor.editor_tile_controller import EditorTileController
from engine.editor.editor_lights_controller import EditorLightsController
from engine.editor.editor_palette_controller import EditorPaletteController
from engine.editor.editor_prefab_controller import EditorPrefabController
from engine.editor.editor_shape_controller import EditorShapeController
from engine.editor.editor_clipboard_controller import EditorClipboardController
from engine.editor.editor_hd2d_controller import EditorHd2dController
from engine.editor.editor_duplicate_controller import EditorDuplicateController
from engine.editor.editor_marquee_controller import EditorMarqueeController
from engine.editor.editor_play_controller import EditorPlayController
from engine.editor.editor_keymap_controller import EditorKeymapController
from engine.editor.editor_dock_query import get_effective_dock_widths
from engine.editor.editor_providers_controller import EditorProvidersController
from .editor_light_occluder_ops import (
    COOKIE_PRESETS,
    LIGHT_COLOR_PRESETS,
    LIGHTING_PRESET_ORDER,
    LIGHTING_PRESETS,
    add_occluder,
    add_light,
    capture_lighting_preset,
    apply_lighting_preset as apply_lighting_preset_ops,
    apply_occluder_command,
    build_delete_polygon_cmd,
    build_finish_polygon_cmd,
    build_insert_point_cmd,
    build_move_point_cmd,
    build_remove_point_cmd,
    cycle_light_color,
    cycle_light_cookie,
    ensure_scene_lights,
    ensure_scene_occluders,
    find_closest_edge_insert_index,
    invert_occluder_command,
    snap_world_point,
    toggle_light_flicker,
    update_light_property,
)
from .import_tools import repair_package_submodule_attr
from .i18n import tr
from .logging_tools import get_logger
from .path_norm import normalize_scene_path
from .ui_overlays.common import (
    _draw_rectangle_filled,
    draw_outline_centered,
    draw_panel_bg,
)
from engine.repo_root import get_repo_root

if TYPE_CHECKING:
    from .game import GameWindow
    from .scene_index import SceneRow
    from engine.workspace_settings import WorkspaceSettings

logger = get_logger(__name__)

# Import from extracted modules
from .editor.state import (
    TOOL_MODE_MOVE,
    TOOL_MODE_PATH,
    TOOL_MODE_ZONE,
    TRANSFORM_MODE_MOVE,
    TRANSFORM_MODE_ROTATE,
    TRANSFORM_MODE_SCALE,
    ENTITY_PANEL_FOCUS_OUTLINER,
    ENTITY_PANEL_FOCUS_INSPECTOR,
    ENTITY_PANEL_FIELDS,
    SCENE_SWITCHER_RECENT_LIMIT,
    EditorDirtyState,
    EditorPlaySession,
)
from .editor.scene_opening import (
    open_scene_by_id as _open_scene_by_id_impl,
)
from .editor.editor_asset_browser_controller import EditorAssetBrowserController

from .editor.editor_workspace_controller import EditorWorkspaceController
from .editor.editor_selection_controller import EditorSelectionController
from .editor.editor_scene_ops import EditorSceneOpsController
from .editor.editor_undo_controller import EditorUndoController
from .editor.editor_ui_flow_controller import EditorUIFlowController
from .editor.editor_session_controller import EditorSessionController
from .editor.editor_unsaved_changes_controller import EditorUnsavedChangesController

ZONE_BEHAVIOUR_CANONICAL = TRIGGER_ZONE_CANONICAL | HITBOX_CANONICAL
ZONE_BEHAVIOUR_CLASSNAMES = TRIGGER_ZONE_CLASSNAMES | HITBOX_CLASSNAMES


PREFAB_PALETTE: list[dict[str, Any]] | None = None
WORKSPACE_AUTOSAVE_DELAY_NS = 500_000_000

# This module is intentionally resilient to being removed from sys.modules and
# re-imported (some tests verify import surfaces and pop modules). In those
# cases, other test modules may still hold references to classes/functions from
# the old module instance while monkeypatch targets the newly-imported instance.
# We route a few call sites through the *current* sys.modules entry when
# possible so monkeypatches still apply.
_MODULE_INSTANCE_ID: object = object()


def _canonical_editor_controller_module():
    """Return the canonical engine.editor_controller module instance.

    Some tests temporarily remove modules from sys.modules and then restore prior
    instances. That can leave multiple live module objects; class references in
    already-imported test modules may point at a non-canonical instance.

    We use importlib to re-resolve the canonical module so test monkeypatches
    targeting 'engine.editor_controller.*' are honored reliably.
    """
    try:
        mod = importlib.import_module("engine.editor_controller")
        repair_package_submodule_attr("engine", "editor_controller")
        return mod
    except Exception:
        return sys.modules.get(__name__)


# Best-effort: keep the package attribute aligned at import time too.
repair_package_submodule_attr("engine", "editor_controller")


def load_prefab_palette(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    current = sys.modules.get(__name__)
    if current is not None:
        try:
            current_id = getattr(current, "_MODULE_INSTANCE_ID", None)
            if current_id is not _MODULE_INSTANCE_ID:
                fn = getattr(current, "load_prefab_palette", None)
                if callable(fn) and fn is not load_prefab_palette:
                    return fn(*args, **kwargs)
        except Exception:
            pass
    from .editor_palette import load_prefab_palette as _impl

    return _impl(*args, **kwargs)


def get_prefab_palette() -> list[dict[str, Any]]:
    current = sys.modules.get(__name__)
    if current is not None:
        try:
            current_id = getattr(current, "_MODULE_INSTANCE_ID", None)
            if current_id is not _MODULE_INSTANCE_ID:
                fn = getattr(current, "get_prefab_palette", None)
                if callable(fn) and fn is not get_prefab_palette:
                    return fn()
        except Exception:
            pass

    global PREFAB_PALETTE
    if PREFAB_PALETTE is None:
        PREFAB_PALETTE = load_prefab_palette()
    return PREFAB_PALETTE

class EditorModeController:
    def __init__(self, window: GameWindow):
        self.window = window
        self.active: bool = False
        self.selected_entity: Optional[optional_arcade.arcade.Sprite] = None
        self.entity_dragging: bool = False
        self.entity_drag_start_pos: Optional[tuple[float, float]] = None
        self.grid_size: float = 16.0
        self._repo_root_override: Any = None  # For testing: set to a Path to override get_repo_root
        # _keymap_overrides - DELEGATED to EditorKeymapController
        # Panel/controller wiring (set by EditorPanelsController)
        self.ui_layers: Any = None
        self.keybinds: Any = None
        self.keybinds_overlay: Any = None
        self.confirm_modal: Any = None
        self.confirm_modal_overlay: Any = None
        self.project_context_menu_overlay: Any = None
        
        # Sub-controllers (Vertical Slice Diet V2)
        # We initialize these early so legacy fields can be proxied to them
        self._workspace_ctl = EditorWorkspaceController(self)
        self._selection_ctl = EditorSelectionController(self)
        self._scene_ops = EditorSceneOpsController(self)
        self.undo = EditorUndoController(self, max_history=50)
        self._ui_flow_ctl = EditorUIFlowController(self)
        self.search = EditorSearchController(self, self._ui_flow_ctl)
        self._file_ops_ctl = EditorFileOpsController(self)
        self.session = EditorSessionController()
        from engine.editor.editor_focus_controller import EditorFocusController  # noqa: PLC0415

        self.focus = EditorFocusController(self)
        self.project_explorer = ProjectExplorerController(self._get_repo_root())
        self.project_explorer_actions = EditorProjectExplorerActionsController(self)
        self.scene_browse = EditorSceneBrowseController(self)
        self.scene_open = EditorSceneOpenController(self)
        self.problems = ProblemsController()
        self.panels = EditorPanelsController(self)
        self.providers = EditorProvidersController(self)
        self.unsaved_confirm = EditorUnsavedChangesController(self)
        self.dialogue = EditorDialogueController(self)
        self.debug_panels = EditorDebugPanelsController(self)
        self.debug_overlay = EditorDebugOverlayController(self)
        self.overlay = EditorOverlayController(self)
        self.tool = EditorToolController(self)
        self.animation = EditorAnimationController(self)
        self.tile = EditorTileController(self)
        self.lights = EditorLightsController(self)
        self.shape = EditorShapeController(self)
        self.palette = EditorPaletteController(self)
        self.prefab = EditorPrefabController(self)
        self.inspector = EditorInspectorController(self)
        self.clipboard = EditorClipboardController(self)
        self.hd2d = EditorHd2dController(self)
        self.duplicate = EditorDuplicateController(self)
        self.marquee = EditorMarqueeController(self)
        self.play = EditorPlayController(self)
        self.keymap = EditorKeymapController(self)
        self.entity_panels_controller = EditorEntityPanelsController(self)
        self.hierarchy = EditorHierarchyController(self)
        self.asset_browser = EditorAssetBrowserController(self)
        self.draw = EditorDrawController(self)
        self.cursor = EditorCursorController(self)
        self.problems_actions = EditorProblemsActionsController(self)
        self.find_actions = EditorFindActionsController(self)
        self.entity_ops = EditorEntityOpsController(self)
        self.command_dispatch = EditorCommandDispatchController(self)
        self.align = EditorAlignController(self)

        # Multi-selection state
        # DELEGATED to EditorSelectionController
        # self._selected_entity_ids: List[str] = []
        # self._primary_entity_id: Optional[str] = None
        self._multiselect_drag_starts: Dict[str, tuple[float, float]] = {}

        # Inspector state
        self.inspector_active: bool = False
        self.inspector_selection_index: int = 0
        self._cached_inspector_items: List[Dict[str, Any]] = []
        self._last_entity_revision: int = 0

        # Entity panels (Outliner/Inspector)
        self.entity_panels_active: bool = False
        self.entity_panels_focus: str = ENTITY_PANEL_FOCUS_OUTLINER
        self.entity_panels_filter: str = ""
        self.entity_panels_filter_active: bool = False
        self.entity_panels_selection_index: int = 0
        self.entity_panels_inspector_index: int = 0
        self.entity_panels_text_edit_active: bool = False
        self.entity_panels_text_field: str | None = None
        self.entity_panels_text_buffer: str = ""
        self._cached_entity_panels_list: List[EntitySummary] = []
        self._entity_panels_selected_id: str | None = None

        # Scene switcher state
        self.scene_switcher_active: bool = False
        self.scene_switcher_query: str = ""
        self.scene_switcher_index: int = 0
        # self.scene_switcher_recent: list[str] = [] # DELEGATED to EditorWorkspaceController
        self._scene_switcher_cached: list[tuple[str, str]] = []

        # Scene browser state
        self.scene_browser_active: bool = False
        self.scene_browser_query: str = ""
        self.scene_browser_index: int = 0
        self._scene_browser_cached_rows: list["SceneRow"] = []

        # Asset browser state
        self.asset_browser_active: bool = False
        self.asset_browser_filter: str = ""
        self.asset_browser_kind: str = "All"
        self.asset_browser_selection_index: int = 0
        self._asset_browser_cached_rows: list[AssetRow] = []
        self._asset_browser_filtered_rows: list[AssetRow] = []

        # Undo history controller
        self.history = EditorHistoryController(self)

        # Problems panel state
        # MOVED to self.problems (ProblemsController)

        # Find Everything launcher state
        # DELEGATED to EditorUIFlowController
        # self._find_everything_open: bool = False
        # self._find_everything_query: str = ""
        # self._find_everything_selection_index: int = 0
        # self._find_everything_cached_results: list[Any] = []
        # self._find_everything_all_results: list[Any] = []
        # self._find_everything_counts: dict[str, object] = {"total": 0, "by_group": {}}
        # self._find_asset_lookup: dict[str, Any] = {}

        # Palette state
        self.palette_active: bool = False
        self.palette_index: int = 0
        self.prefab_palette_path: str = DEFAULT_PREFAB_PATH
        strict_prefabs = getattr(window, "strict_mode", False)
        current = _canonical_editor_controller_module()
        palette_loader = getattr(current, "load_prefab_palette", load_prefab_palette) if current is not None else load_prefab_palette
        palette_getter = getattr(current, "get_prefab_palette", get_prefab_palette) if current is not None else get_prefab_palette

        loaded_palette = palette_loader(path=self.prefab_palette_path, strict=strict_prefabs)
        base_palette = palette_getter()
        self.prefab_palette: List[Dict[str, Any]] = loaded_palette if loaded_palette else list(base_palette)
        self.palette_filter: str = ""
        self.palette_filter_active: bool = False
        self._cached_palette_list: List[Dict[str, Any]] = list(self.prefab_palette)
        self._palette_thumb_textures: Dict[str, optional_arcade.arcade.Texture] = {}
        self._palette_tag_ranked: List[str] = []

        # Command palette state delegated to EditorSearchController

        # Menu bar state
        self._menu_active: Optional[str] = None
        self._menu_hover_item_id: Optional[str] = None

        # Context menu state (right-click menu)
        self._context_menu_x: float = 0.0
        self._context_menu_y: float = 0.0
        self._context_menu_hover_id: Optional[str] = None

        # Dock state controller (tabs + sizing/collapse)
        self.dock = EditorDockController(self.session, left_tab="Outliner", right_tab="Inspector")
        self.hover = EditorHoverStateController(self.dock)

        # Component Inspector state (for right dock "Inspector" tab)
        self._inspector_sections_expanded: Dict[str, bool] = {}  # section_id -> expanded
        self._inspector_cursor: Tuple[str, int] = ("transform", 0)  # (section_id, row_index)
        self._inspector_text_edit_active: bool = False
        self._inspector_text_buffer: str = ""
        
        # Component Inspector v1 state
        self._component_inspector_index: int = 0  # Selection index in flattened row list
        self._add_component_picker_active: bool = False
        self._add_component_picker_index: int = 0
        self._add_component_picker_options: List[str] = []  # ["sprite", "light", "collider"]

        # Clipboard state - DELEGATED to EditorClipboardController
        # self._entity_clipboard: Optional[Dict[str, Any]] = None
        # self._entity_clipboard_source_id: Optional[str] = None
        # self._hd2d_overrides_clipboard: Optional[Dict[str, Any]] = None

        # HD-2D batch paste radius (loaded from workspace settings)
        self._hd2d_batch_radius_px: int = 96

        # Tool state
        self.tool_mode: str = TOOL_MODE_MOVE
        self.transform_mode: str = TRANSFORM_MODE_MOVE  # "move", "rotate", "scale"
        self.selected_waypoint_index: int = -1
        self.zone_behaviour_index: int = 0
        self.zone_edit_target: str = ZONE_TARGET_TRIGGER

        # Rotate/Scale drag state
        self._rotate_drag_active: bool = False
        self._scale_drag_active: bool = False
        self._transform_drag_pivot: Tuple[float, float] | None = None
        self._transform_drag_mouse_start: Tuple[float, float] | None = None
        self._transform_drag_start_rots: Dict[str, float] = {}
        self._transform_drag_start_scales: Dict[str, float] = {}

        # Transform preview state for gizmo overlay
        self._move_preview_delta_xy: Tuple[float, float] | None = None
        self._rotate_preview_delta_deg: float | None = None
        self._scale_preview_factor: float | None = None
        self._transform_snap_active: bool = False

        # Marquee box selection state - DELEGATED to EditorMarqueeController
        # State accessed via marquee controller: _marquee_active, _marquee_start_world, etc.

        # Alt-drag duplicate state - DELEGATED to EditorDuplicateController
        # State accessed via duplicate controller: _alt_dup_active, _alt_dup_specs, etc.

        # Cursor hint state - DELEGATED to EditorCursorController
        # State accessed via cursor controller: _last_mouse_x, _last_mouse_y

        # Undo/Redo state
        # DELEGATED to EditorSceneOpsController
        # self.undo_stack: List[Dict[str, Any]] = []
        # self.redo_stack: List[Dict[str, Any]] = []
        # self.scene_dirty: bool = False
        self.dirty_state = EditorDirtyState()
        self.play_session = EditorPlaySession()

        # Hierarchy state
        self.hierarchy_active: bool = False
        self.hierarchy_filter: str = ""
        self.hierarchy_selection_index: int = 0
        self.hierarchy_filter_active: bool = False
        self.hierarchy_rename_active: bool = False
        self.hierarchy_rename_buffer: str = ""
        self._cached_hierarchy_list: List[optional_arcade.arcade.Sprite] = []
        self._hierarchy_name_cache: Dict[int, str] = {}


        # Dialogue / Quest inspector state
        self.dialogue_panel_active: bool = False
        self.dialogue_selected_node: int = 0
        self.dialogue_selected_choice: int = 0
        self.dialogue_field_focus: str = "node_text"
        self.dialogue_editing: bool = False
        self.dialogue_edit_buffer: str = ""
        self._cached_dialogue_nodes: List[str] = []
        self._dialogue_warnings: List[str] = []

        # Animation panel state
        self.animation_active: bool = False
        self.animation_selected_index: int = 0
        self.animation_field_focus: str = "mode"
        self.animation_editing: bool = False
        self.animation_edit_buffer: str = ""
        self._cached_animation_names: List[str] = []

        # Tile painting state
        self.tile_panel_active: bool = False
        self.session.set_tile_paint_active(self.tile_panel_active)
        self.tile_palette: List[int] = []
        self.tile_palette_index: int = 0
        self.tile_layer_index: int = 0
        self.tile_layers: List[str] = []
        # Lights tool state
        self.lights_tool_active: bool = False
        self.lights_selection: Optional[int] = None
        self.lights_dragging: bool = False
        self.lights_drag_start: Optional[tuple[float, float]] = None
        self.lights_original_pos: Optional[tuple[float, float]] = None
        self._light_color_palette: List[str] = list(LIGHT_COLOR_PRESETS)
        self._light_cookie_palette: List[str | None] = list(COOKIE_PRESETS)
        self.light_property_index: int = 0
        self._light_property_defs: list[dict[str, Any]] = [
            {"name": "radius_px", "key": "radius", "default": 160.0, "step": 4.0, "min": 8.0},
            {"name": "flicker_amount", "key": "flicker_amount", "default": 0.0, "step": 0.05, "min": 0.0, "max": 1.0},
            {"name": "flicker_speed", "key": "flicker_speed", "default": 1.0, "step": 0.25, "min": 0.0},
            {"name": "cookie_scale", "key": "cookie_scale", "default": 1.0, "step": 0.1, "min": 0.0},
            {"name": "cookie_rotation_deg", "key": "cookie_rotation_deg", "default": 0.0, "step": 5.0, "wrap": 360.0},
        ]
        self.lighting_preset_label: str | None = None
        self.lighting_preset_until: float = 0.0

        # HD-2D preset preview state - DELEGATED to EditorHd2dController
        # State accessed via hd2d controller: _hd2d_preview_active, _hd2d_preview_snapshot, _hd2d_preview_preset_id

        # Scene occluder tool state
        self.occluder_tool_active: bool = False
        self.occluder_points: List[tuple[float, float]] = []
        self.occluder_selection: Optional[int] = None
        self.occluder_vertex_selection: Optional[int] = None
        self.occluder_dragging: bool = False
        self.occluder_drag_origin: Optional[tuple[float, float]] = None

        # Asset Placement Mode
        self.asset_place_active: bool = False
        self.asset_place_path: Optional[str] = None
        self.asset_place_kind: Optional[str] = None

        # Snap settings (lights + occluders)
        self.snap_enabled: bool = False
        self.snap_mode: str = "grid16"

        # Ghost originals settings (for alt-drag duplicate visual feedback)
        self._ghost_originals_enabled: bool = True
        self._ghost_originals_alpha: int = 90
        self._ghost_originals_dim_scale: float = 0.65

        # HD2D default preset (for auto-apply on new scenes)
        self._hd2d_default_preset_id: str | None = None

        self.load_workspace()
        self.load_keymap_overrides()

        # Shape editing state (entity-local collision/occluder polygons)
        self.shape_edit_mode: Optional[str] = None
        self.shape_edit_points: List[tuple[float, float]] = []
        self.shape_edit_original: List[tuple[float, float]] = []
        self.shape_edit_entity: Optional[optional_arcade.arcade.Sprite] = None
        self.shape_drag_index: int = -1
        self.shape_snap_enabled: bool = False
        self._status_message: str | None = None
        self._status_until: float = 0.0

        # UI Text Objects (Optimization)
        self._overlay_text_obj = optional_arcade.arcade.Text(
            text="",
            x=10,
            y=0, # Updated dynamically
            color=optional_arcade.arcade.color.YELLOW,
            font_size=12,
            font_name="Consolas",
            multiline=True,
            width=400
        )
        self._palette_text_obj = optional_arcade.arcade.Text(
            text="",
            x=0, # Updated dynamically
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            font_name="Consolas",
            multiline=True,
            width=200
        )

    # -- Sub-Controller Accessors --

    @property
    def file_ops(self) -> EditorFileOpsController:
        return self._file_ops_ctl

    @property
    def ui_flow(self) -> EditorUIFlowController:
        return self._ui_flow_ctl

    @property
    def selection(self) -> EditorSelectionController:
        return self._selection_ctl

    @property
    def scene_ops(self) -> EditorSceneOpsController:
        return self._scene_ops

    @property
    def workspace(self) -> EditorWorkspaceController:
        return self._workspace_ctl

    @property
    def confirm_open(self) -> bool:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return False
        return confirm.is_open

    @confirm_open.setter
    def confirm_open(self, value: bool) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.set_open(bool(value))

    @property
    def confirm_reason(self) -> str:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return ""
        return confirm.reason

    @confirm_reason.setter
    def confirm_reason(self, value: str) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.reason = str(value or "")

    @property
    def confirm_selection_index(self) -> int:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return 0
        return confirm.selection_index

    @confirm_selection_index.setter
    def confirm_selection_index(self, value: int) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.selection_index = int(value)

    @property
    def pending_action(self) -> Callable[[], None] | None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return None
        return confirm.pending_action

    @pending_action.setter
    def pending_action(self, value: Callable[[], None] | None) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.pending_action = value
    
    # -- EditorUiFlowHost Protocol Implementation --
    
    def ui_activate_command(self, cmd_id: str) -> bool:
        return self._activate_find_command(cmd_id)
        
    def ui_activate_asset(self, item_id: str) -> bool:
        return self._activate_find_asset(item_id)
        
    def ui_activate_scene(self, item_id: str) -> bool:
        return self._activate_find_scene(item_id)
        
    def ui_activate_entity(self, item_id: str) -> bool:
        return self._activate_find_entity(item_id)
        
    def ui_activate_problem(self, item_id: str) -> bool:
        return self._activate_find_problem(item_id)
        
    def ui_get_palette_items(self) -> List[Any]:
        return self.search.ui_get_palette_items()

    def _ui_get_problems(self, scene_data: Any, window: Any) -> List[Any]:
        """Helper for palette items."""
        return self.search._ui_get_problems(scene_data, window)

    def ui_toast(self, msg: str) -> None:
        self._show_toast(msg)

    def ui_hd2d_preview(self, preset_id: str) -> None:
        self.preview_hd2d_preset(preset_id)
        
    def ui_hd2d_cancel_preview(self) -> None:
        self._cancel_hd2d_preview()
        
    def ui_hd2d_commit(self, preset_id: str) -> bool:
        return self.commit_hd2d_preset(preset_id)

    # -- Vertical Slice Diet V2 Delegation Properties --

    @property
    def workspace_data(self) -> WorkspaceSettings:
        return self._workspace_ctl.workspace_data

    @workspace_data.setter
    def workspace_data(self, value: WorkspaceSettings) -> None:
        self._workspace_ctl.workspace_data = value

    @property
    def recent_projects(self) -> List[str]:
        return self._workspace_ctl.recent_projects

    @recent_projects.setter
    def recent_projects(self, value: List[str]) -> None:
        self._workspace_ctl.recent_projects = value
        
    @property
    def scene_switcher_recent(self) -> List[str]:
        return self._workspace_ctl.recent_scenes

    @scene_switcher_recent.setter
    def scene_switcher_recent(self, value: List[str]) -> None:
        self._workspace_ctl.recent_scenes = value

    @property
    def _selected_entity_ids(self) -> List[str]:
        return self._selection_ctl.selected_ids

    @_selected_entity_ids.setter
    def _selected_entity_ids(self, value: List[str]) -> None:
        if value is None:
            value = []
        self._selection_ctl.selected_ids = value

    @property
    def _primary_entity_id(self) -> Optional[str]:
        return self._selection_ctl.primary_selected_id

    @_primary_entity_id.setter
    def _primary_entity_id(self, value: Optional[str]) -> None:
        self._selection_ctl.primary_selected_id = value

    @property
    def undo_stack(self) -> List[Dict[str, Any]]:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "undo_stack"):
            return undo_ctrl.undo_stack
        return []

    @undo_stack.setter
    def undo_stack(self, value: List[Dict[str, Any]]) -> None:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "set_undo_stack"):
            undo_ctrl.set_undo_stack(value)
            return
        return

    @property
    def redo_stack(self) -> List[Dict[str, Any]]:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "redo_stack"):
            return undo_ctrl.redo_stack
        return []

    @redo_stack.setter
    def redo_stack(self, value: List[Dict[str, Any]]) -> None:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "set_redo_stack"):
            undo_ctrl.set_redo_stack(value)
            return
        return

    @property
    def scene_dirty(self) -> bool:
        return self._scene_ops.scene_dirty

    @scene_dirty.setter
    def scene_dirty(self, value: bool) -> None:
        self._scene_ops.scene_dirty = value

    @property
    def dirty_state(self) -> EditorDirtyState:
        return self._scene_ops.dirty_state

    @dirty_state.setter
    def dirty_state(self, value: EditorDirtyState) -> None:
        self._scene_ops.dirty_state = value

    # -- UI Flow Delegation Properties --

    @property
    def _find_everything_open(self) -> bool:
        return self._ui_flow_ctl.is_open

    @_find_everything_open.setter
    def _find_everything_open(self, value: bool) -> None:
        self._ui_flow_ctl.is_open = value

    @property
    def _find_everything_query(self) -> str:
        return self._ui_flow_ctl.query

    @_find_everything_query.setter
    def _find_everything_query(self, value: str) -> None:
        self._ui_flow_ctl.query = value

    @property
    def _find_everything_selection_index(self) -> int:
        return self._ui_flow_ctl.selection_index

    @_find_everything_selection_index.setter
    def _find_everything_selection_index(self, value: int) -> None:
        self._ui_flow_ctl.selection_index = value

    @property
    def _find_everything_cached_results(self) -> List[Any]:
        return self._ui_flow_ctl.cached_results

    @_find_everything_cached_results.setter
    def _find_everything_cached_results(self, value: List[Any]) -> None:
        self._ui_flow_ctl.cached_results = value

    @property
    def _find_everything_all_results(self) -> List[Any]:
        return self._ui_flow_ctl.all_results

    @_find_everything_all_results.setter
    def _find_everything_all_results(self, value: List[Any]) -> None:
        self._ui_flow_ctl.all_results = value

    @property
    def _find_everything_counts(self) -> Dict[str, object]:
        return self._ui_flow_ctl.counts

    @_find_everything_counts.setter
    def _find_everything_counts(self, value: Dict[str, object]) -> None:
        self._ui_flow_ctl.counts = value

    @property
    def _find_asset_lookup(self) -> Dict[str, Any]:
        return self._ui_flow_ctl.asset_lookup

    @_find_asset_lookup.setter
    def _find_asset_lookup(self, value: Dict[str, Any]) -> None:
        self._ui_flow_ctl.asset_lookup = value

    def _get_repo_root(self) -> Any:
        """Get repo root, allowing override for testing."""
        if self._repo_root_override is not None:
            return self._repo_root_override
        return get_repo_root()

    def load_keymap_overrides(self) -> None:
        """Load keymap overrides from keymap.json.

        DELEGATED to EditorKeymapController.
        """
        self.keymap.load_overrides()

    def load_workspace(self) -> None:
        self._workspace_ctl.load_workspace()

    def save_workspace(self) -> None:
        self._workspace_ctl.save_workspace()

    def _autosave_workspace(self, now_ns: int | None = None) -> None:
        self._workspace_ctl.schedule_autosave(now_ns=now_ns)

    def _tick_workspace_autosave(self, now_ns: int | None = None) -> None:
        self._workspace_ctl.tick_autosave(delay_ns=WORKSPACE_AUTOSAVE_DELAY_NS, now_ns=now_ns)

    def _flush_workspace_autosave(self) -> None:
        self._workspace_ctl.flush_autosave()

    # -------------------------------------------------------------------------
    # Ghost Originals Settings (for alt-drag duplicate visual feedback)
    # -------------------------------------------------------------------------

    def get_ghost_originals_enabled(self) -> bool:
        """Return whether ghost originals effect is enabled."""
        return self._ghost_originals_enabled

    def get_ghost_originals_alpha(self) -> int:
        """Return the ghost alpha value (0..255)."""
        return self._ghost_originals_alpha

    def get_ghost_originals_dim_scale(self) -> float:
        """Return the ghost dim scale (0.0..1.0)."""
        return self._ghost_originals_dim_scale

    def toggle_ghost_originals(self) -> None:
        """Toggle ghost originals effect on/off and save workspace."""
        self._ghost_originals_enabled = not self._ghost_originals_enabled
        self.save_workspace()

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """Handle window resize; overlays use live window dimensions so nothing to cache."""
        return

    def _get_scene_lights(self) -> List[Dict[str, Any]]:
        return self.lights.get_scene_lights()

    def _get_scene_occluders(self) -> List[Dict[str, Any]]:
        return self.lights.get_scene_occluders()

    def _sync_lighting_runtime(self) -> None:
        self.lights.sync_lighting_runtime()

    def _sync_lighting_settings(self) -> None:
        self.lights.sync_lighting_settings()

    def apply_lighting_preset(self, preset_id: str) -> bool:
        return self.lights.apply_lighting_preset(preset_id)

    def apply_lighting_preset_hotkey(self, index: int) -> bool:
        return self.lights.apply_lighting_preset_hotkey(index)

    def apply_custom_lighting_preset(self, slot: str) -> bool:
        return self.lights.apply_custom_lighting_preset(slot)

    def capture_lighting_preset(self, slot: str) -> bool:
        return self.lights.capture_lighting_preset(slot)

    def get_active_lighting_preset_label(self) -> str | None:
        return self.lights.get_active_lighting_preset_label()

    def _sync_occluders_runtime(self) -> None:
        self.lights.sync_occluders_runtime()

    def toggle(self) -> None:
        if self.play_session.is_playing:
            self.stop_playing()
            return
        if self.active:
            if self.confirm_unsaved_changes("Exit Editor Mode", self._disable_editor_mode):
                return
            self._disable_editor_mode()
            return
        self._enable_editor_mode()

    def _enable_editor_mode(self) -> None:
        self.active = True
        logger.info("[Editor] Mode ENABLED")
        # Pause game logic to prevent interference
        self.window.paused = True
        self.inspector.set_inspector_active(False)
        self.palette_active = False
        self.palette_filter_active = False

    def _disable_editor_mode(self) -> None:
        self._flush_workspace_autosave()
        self.active = False
        logger.info("[Editor] Mode DISABLED")
        self.selected_entity = None
        self.shape.reset_zone_selection_state()
        self.window.paused = False
        self.inspector.set_inspector_active(False)
        self.palette_active = False
        self.palette_filter_active = False
        self.panels.close_command_palette()
        self.search.clear_command_palette_state()
        self.scene_browser_active = False
        self.scene_browser_query = ""
        self.scene_browser_index = 0
        self._cancel_hierarchy_rename()
        self._close_dialogue_panel()
        self._close_animation_panel()
        self._close_tile_panel()
        self.scene_switcher_active = False
        self.scene_switcher_query = ""
        self.scene_switcher_index = 0
        self._toggle_lights_mode(False)
        self._toggle_occluder_mode(False)
        self.shape.cancel_shape_edit()

    # -------------------------------------------------------------------------
    # Play Session
    # DELEGATED to EditorPlayController
    # -------------------------------------------------------------------------

    def play_from_here(self) -> bool:
        """Start play session from current camera position.

        DELEGATED to EditorPlayController.
        """
        return self.play.play_from_here()

    def stop_playing(self) -> bool:
        """Stop the current play session.

        DELEGATED to EditorPlayController.
        """
        return self.play.stop_playing()

    def _start_play_session(self) -> None:
        """Start play session.

        DELEGATED to EditorPlayController.
        """
        self.play.start_session()

    def _stop_play_session(self) -> None:
        """Stop play session and restore editor state.

        DELEGATED to EditorPlayController.
        """
        self.play.stop_session()

    def _get_camera_center(self) -> tuple[float, float]:
        """Get the current camera center position.

        DELEGATED to EditorPlayController.
        """
        return self.play._get_camera_center()

    def _restore_camera_position(self, pos: tuple[float, float] | None) -> None:
        """Restore camera to a saved position.

        DELEGATED to EditorPlayController.
        """
        self.play._restore_camera_position(pos)

    def _spawn_player_for_play(self) -> None:
        """Spawn player at camera center for play session.

        DELEGATED to EditorPlayController.
        """
        self.play._spawn_player()

    def handle_mouse_click(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_click(self, x, y, button, modifiers)

    def handle_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input when editor is active. Returns True if consumed."""
        # Check UI Layer Stack first (modals, etc)
        panels = getattr(self, "panels", None)
        if panels is not None and panels.dispatch_input(key, modifiers):
            return True
            
        return editor_input.handle_input(self, key, modifiers)

    def run_editor_action(self, action_id: str) -> bool:
        """Run a registered editor action by id."""
        from engine.editor.editor_actions import run_editor_action  # noqa: PLC0415

        return run_editor_action(action_id, self, self.window)

    def on_text(self, text: str) -> bool:
        """Handle text input when editor is active. Returns True if consumed."""
        panels = getattr(self, "panels", None)
        if panels is not None and panels.dispatch_text(text):
            return True
        # Future: Route to focused widget?
        return False

    def _cycle_tool_mode(self) -> None:
        self.tool.cycle_tool_mode()

    def _handle_palette_input(self, key: int, modifiers: int) -> bool:
        return self.palette.handle_palette_input(key, modifiers)

    def _prefab_sprite_path(self, prefab: Dict[str, Any]) -> str | None:
        return self.palette.prefab_sprite_path(prefab)

    def _palette_visible_index_range(self, item_count: int) -> tuple[int, int]:
        return self.palette.palette_visible_index_range(item_count)

    def _palette_header_line_count(self) -> int:
        return self.palette.palette_header_line_count()

    def _palette_tag_suggestions(self) -> List[str]:
        return self.palette.palette_tag_suggestions()

    def _apply_palette_tag_autocomplete(self) -> bool:
        return self.palette.apply_palette_tag_autocomplete()

    def _palette_visible_items(self) -> List[Dict[str, Any]]:
        return self.palette.palette_visible_items()

    def _prewarm_visible_palette_thumbs(self) -> None:
        self.palette.prewarm_visible_palette_thumbs()

    def _build_palette_list(self) -> List[Dict[str, Any]]:
        return self.palette.build_palette_list()

    def _refresh_palette_list(self) -> None:
        self.palette.refresh_palette_list()

    def _get_palette_items(self) -> List[Dict[str, Any]]:
        return self.palette.get_palette_items()

    def _get_palette_thumb_texture(self, prefab: Dict[str, Any]) -> Optional[optional_arcade.arcade.Texture]:
        return self.palette.get_palette_thumb_texture(prefab)

    def _handle_movement_input(self, key: int, modifiers: int) -> bool:
        if not self.selected_entity:
            return False

        grid = self.grid_size
        dx, dy = 0.0, 0.0

        if key == optional_arcade.arcade.key.LEFT:
            dx = -grid
        elif key == optional_arcade.arcade.key.RIGHT:
            dx = grid
        elif key == optional_arcade.arcade.key.UP:
            dy = grid
        elif key == optional_arcade.arcade.key.DOWN:
            dy = -grid
        else:
            return False

        self.nudge_selected(dx, dy)
        return True

    def _handle_inspector_input(self, key: int, modifiers: int) -> bool:
        return self.inspector.handle_inspector_input(key, modifiers)

    # ------------------------------------------------------------------
    # Dialogue / Quest editing
    # ------------------------------------------------------------------
    def toggle_dialogue_panel(self) -> None:
        self.dialogue.toggle_dialogue_panel()

    def _close_dialogue_panel(self) -> None:
        self.dialogue.close_dialogue_panel()

    def _entity_has_dialogue(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return self.dialogue.entity_has_dialogue(sprite)

    def _refresh_dialogue_cache(self) -> None:
        self.dialogue.refresh_dialogue_cache()

    def _get_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite) -> Dict[str, Any]:
        return self.dialogue.get_entity_dialogue_config(sprite)

    def _set_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite, dialogue_root: Dict[str, Any]) -> None:
        self.dialogue.set_entity_dialogue_config(sprite, dialogue_root)

    def _dialogue_nodes(self) -> List[Dict[str, Any]]:
        return self.dialogue.dialogue_nodes()

    def _get_selected_node(self) -> Optional[Dict[str, Any]]:
        return self.dialogue.get_selected_node()

    def _get_selected_choice(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.dialogue.get_selected_choice(node)

    def _handle_dialogue_input(self, key: int, modifiers: int) -> bool:
        return self.dialogue.handle_dialogue_input(key, modifiers)

    def _next_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        return self.dialogue.next_dialogue_field(current, has_choice=has_choice)

    def _prev_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        return self.dialogue.prev_dialogue_field(current, has_choice=has_choice)

    def _begin_dialogue_edit(self) -> None:
        self.dialogue.begin_dialogue_edit()

    def _commit_dialogue_edit(self) -> None:
        self.dialogue.commit_dialogue_edit()

    def _apply_dialogue_edit(
        self,
        node: Dict[str, Any],
        choice: Optional[Dict[str, Any]],
        focus: str,
        new_text: str,
    ) -> bool:
        return self.dialogue.apply_dialogue_edit(node, choice, focus, new_text)

    def _collect_dialogue_warnings(self, dialogue_root: Dict[str, Any]) -> List[str]:
        return self.dialogue.collect_dialogue_warnings(dialogue_root)

    # ------------------------------------------------------------------
    # Animation panel helpers
    # ------------------------------------------------------------------
    def toggle_animation_panel(self) -> None:
        self.animation.toggle_animation_panel()

    def _close_animation_panel(self) -> None:
        self.animation.close_animation_panel()

    def _entity_has_animator(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return self.animation.entity_has_animator(sprite)

    def _refresh_animation_cache(self) -> None:
        self.animation.refresh_animation_cache()

    def _get_animator_config(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> Dict[str, Any]:
        return self.animation.get_animator_config(sprite)

    def _set_animator_config(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        self.animation.set_animator_config(sprite, animator_cfg)

    def _apply_animator_runtime(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        self.animation.apply_animator_runtime(sprite, animator_cfg)

    def _handle_animation_input(self, key: int, modifiers: int) -> bool:
        return self.animation.handle_animation_input(key, modifiers)

    def _next_animation_field(self, current: str) -> str:
        return self.animation.next_animation_field(current)

    def _prev_animation_field(self, current: str) -> str:
        return self.animation.prev_animation_field(current)

    def _cycle_mode(self, current: str, forward: bool) -> str:
        return self.animation.cycle_mode(current, forward)

    def _commit_animation_edit(self) -> None:
        self.animation.commit_animation_edit()

    def _apply_animation_change(
        self,
        names: List[str],
        animations: Dict[str, Any],
        clip_name: str,
        field: str,
        new_value: Any,
    ) -> None:
        self.animation.apply_animation_change(names, animations, clip_name, field, new_value)

    # ------------------------------------------------------------------
    # Tile painting helpers
    # ------------------------------------------------------------------
    def _tilemap_available(self) -> bool:
        return self.tile.tilemap_available()

    def _set_tile_panel_active(self, value: bool) -> None:
        self.tile.set_tile_panel_active(value)

    def toggle_tile_panel(self) -> None:
        self.tile.toggle_tile_panel()

    def _close_tile_panel(self) -> None:
        self.tile.close_tile_panel()

    def _refresh_tile_palette(self) -> None:
        self.tile.refresh_tile_palette()

    def _current_tile_gid(self) -> int:
        return self.tile.current_tile_gid()

    def _paint_tile_at(self, world_x: float, world_y: float, gid: int) -> None:
        self.tile.paint_tile_at(world_x, world_y, gid)

    def _current_tile_layer(self) -> str:
        return self.tile.current_tile_layer()

    def _handle_tile_input(self, key: int, modifiers: int) -> bool:
        return self.tile.handle_tile_input(key, modifiers)

    # ------------------------------------------------------------------
    # Lights tool
    # ------------------------------------------------------------------
    def _handle_lights_mouse_press(self, world_x: float, world_y: float) -> None:
        self.lights.handle_lights_mouse_press(world_x, world_y)

    def _handle_lights_key_input(self, key: int, modifiers: int) -> bool:
        return self.lights.handle_lights_key_input(key, modifiers)

    def _hit_test_light(self, world_x: float, world_y: float, pick_radius: float = 16.0) -> Optional[int]:
        return self.lights.hit_test_light(world_x, world_y, pick_radius=pick_radius)

    def _add_light(self, x: float, y: float) -> None:
        self.lights.add_light(x, y)

    def _delete_selected_light(self) -> None:
        self.lights.delete_selected_light()

    def handle_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_drag(self, x, y, dx, dy, buttons, modifiers)

    def handle_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_release(self, x, y, button, modifiers)

    def _draw_lights_overlay(self) -> None:
        self.lights.draw_lights_overlay()

    # ------------------------------------------------------------------
    # Scene occluder tool
    # ------------------------------------------------------------------
    def toggle_occluder_tool(self) -> None:
        self.lights.toggle_occluder_tool()

    def _toggle_occluder_mode(self, enabled: bool) -> None:
        self.lights.toggle_occluder_mode(enabled)

    def _handle_occluder_mouse_press(self, world_x: float, world_y: float) -> None:
        self.lights.handle_occluder_mouse_press(world_x, world_y)

    def _hit_test_occluder_vertex(self, world_x: float, world_y: float, *, radius_px: float = 10.0) -> Optional[tuple[int, int]]:
        return self.lights.hit_test_occluder_vertex(world_x, world_y, radius_px=radius_px)

    def _commit_occluder_polygon(self) -> bool:
        return self.lights.commit_occluder_polygon()

    def _remove_occluder_point(self) -> bool:
        return self.lights.remove_occluder_point()

    def _update_occluder_point(self, world_x: float, world_y: float, *, push_command: bool = True) -> bool:
        return self.lights.update_occluder_point(world_x, world_y, push_command=push_command)

    def _get_occluder_point(self, occ_idx: int, pt_idx: int) -> Optional[tuple[float, float]]:
        return self.lights.get_occluder_point(occ_idx, pt_idx)

    def _build_move_occluder_cmd(
        self,
        occ_idx: int,
        pt_idx: int,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> Any | None:
        return self.lights.build_move_occluder_cmd(occ_idx, pt_idx, start, end)

    def _snap_world_point(self, world_x: float, world_y: float) -> tuple[float, float]:
        if not self.snap_enabled:
            return (float(world_x), float(world_y))
        tile_size = None
        instance = getattr(self.window.scene_controller, "tilemap_instance", None)
        if instance is not None:
            tile_size_value = getattr(instance, "tile_size", None)
            if isinstance(tile_size_value, tuple) and len(tile_size_value) >= 1:
                try:
                    tile_size = int(tile_size_value[0])
                except Exception:  # noqa: BLE001
                    tile_size = None
        return snap_world_point((float(world_x), float(world_y)), self.snap_mode, tile_size)

    def _delete_selected_occluder(self) -> bool:
        return self.lights.delete_selected_occluder()

    def _remove_selected_occluder_vertex(self) -> bool:
        return self.lights.remove_selected_occluder_vertex()

    def _handle_occluder_key_input(self, key: int) -> bool:
        return self.lights.handle_occluder_key_input(key)

    def _insert_occluder_point(self, world_x: float, world_y: float) -> bool:
        return self.lights.insert_occluder_point(world_x, world_y)

    def _update_param(self, behaviour_name: str, param_name: str, value: Any) -> None:
        self.inspector.update_param(behaviour_name, param_name, value)

    def _update_param_internal(self, behaviour_name: str, param_name: str, value: Any, entity_name: str) -> None:
        self.inspector.update_param_internal(behaviour_name, param_name, value, entity_name)

    def _remove_param_internal(self, behaviour_name: str, param_name: str, entity_name: str) -> None:
        self.inspector.remove_param_internal(behaviour_name, param_name, entity_name)

    def _apply_behaviour_config_map(self, entity: optional_arcade.arcade.Sprite, config_map: dict[str, Any]) -> None:
        self.inspector.apply_behaviour_config_map(entity, config_map)

    def _get_prefab_base_entity(self, entity_data: dict[str, Any]) -> dict[str, Any] | None:
        return self.inspector.get_prefab_base_entity(entity_data)

    def _prefab_override_info(
        self, entity_data: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, set[str]]:
        return self.prefab.prefab_override_info(entity_data)

    def _reset_selected_prefab_override(self, selected_item: dict[str, Any]) -> bool:
        return self.prefab.reset_selected_prefab_override(selected_item)

    def _reset_all_prefab_overrides(self) -> bool:
        return self.prefab.reset_all_prefab_overrides()

    def _refresh_inspector_items(self) -> None:
        self.inspector.refresh_inspector_items()

    def _get_inspector_items(self) -> List[Dict[str, Any]]:
        return self.inspector.get_inspector_items()

    def _build_inspector_items(self) -> List[Dict[str, Any]]:
        return self.inspector.build_inspector_items()

    def nudge_selected(self, dx: float, dy: float) -> None:
        editor_ops.nudge_selected(self, dx, dy)

    def save_current_scene(self) -> None:
        self._flush_workspace_autosave()
        editor_ops.save_current_scene(self)

    # -------------------------------------------------------------------------
    # Problems Panel Actions
    # DELEGATED to EditorProblemsActionsController
    # -------------------------------------------------------------------------

    def problems_jump_to_selected(self) -> bool:
        """Jump to the selected problem (load scene, select entity, reveal in explorer).

        DELEGATED to EditorProblemsActionsController.
        """
        return self.problems_actions.jump_to_selected()

    def problems_copy_location(self) -> bool:
        """Copy the selected problem's location to clipboard (native only).

        DELEGATED to EditorProblemsActionsController.
        """
        return self.problems_actions.copy_location()

    def _reveal_in_project_explorer(self, path: str) -> bool:
        """Reveal a path in the Project Explorer.

        DELEGATED to EditorProblemsActionsController.
        """
        return self.problems_actions._reveal_in_project_explorer(path)

    def _toast_problems(self, message: str, seconds: float = 2.5) -> None:
        """Show a toast notification for problems panel actions.

        DELEGATED to EditorProblemsActionsController.
        """
        self.problems_actions._toast(message, seconds=seconds)

    def toggle_palette(self) -> None:
        self.palette.toggle_palette()

    def move_palette_selection(self, delta: int) -> None:
        self.palette.move_palette_selection(delta)

    def select_palette_index(self, index: int) -> None:
        self.palette.select_palette_index(index)

    def toggle_lights_tool(self) -> None:
        self.lights.toggle_lights_tool()

    def _toggle_lights_mode(self, enabled: bool) -> None:
        self.lights.toggle_lights_mode(enabled)

    @property
    def palette_selected_prefab(self) -> Optional[str]:
        return self.palette.palette_selected_prefab()

    def place_entity_at_mouse(self, x: float, y: float) -> None:
        editor_ops.place_entity_at_mouse(self, x, y)

    def duplicate_selected(self) -> None:
        editor_ops.duplicate_selected(self)

    def delete_selected(self) -> None:
        if self.project_explorer_actions.delete_selected_paths_if_active():
            return
        editor_ops.delete_selected(self)

    def copy_selected_entity_to_clipboard(self) -> None:
        """Copy the selected entity to the internal clipboard."""
        self.clipboard.copy_selected_entity()

    def paste_entity_from_clipboard(
        self, spawn_world_xy: tuple[float, float] | None = None
    ) -> None:
        """Paste an entity from the internal clipboard."""
        self.clipboard.paste_entity(spawn_world_xy)

    # Clipboard state property accessors for backward compatibility
    @property
    def _entity_clipboard(self) -> Optional[Dict[str, Any]]:
        return self.clipboard.entity_clipboard

    @_entity_clipboard.setter
    def _entity_clipboard(self, value: Optional[Dict[str, Any]]) -> None:
        self.clipboard.entity_clipboard = value

    @property
    def _entity_clipboard_source_id(self) -> Optional[str]:
        return self.clipboard.entity_clipboard_source_id

    @_entity_clipboard_source_id.setter
    def _entity_clipboard_source_id(self, value: Optional[str]) -> None:
        self.clipboard.entity_clipboard_source_id = value

    @property
    def _hd2d_overrides_clipboard(self) -> Optional[Dict[str, Any]]:
        return self.clipboard.hd2d_overrides_clipboard

    @_hd2d_overrides_clipboard.setter
    def _hd2d_overrides_clipboard(self, value: Optional[Dict[str, Any]]) -> None:
        self.clipboard.hd2d_overrides_clipboard = value

    # HD2D preview state accessors (DELEGATED to EditorHd2dController)
    @property
    def _hd2d_preview_active(self) -> bool:
        return self.hd2d.preview_active

    @_hd2d_preview_active.setter
    def _hd2d_preview_active(self, value: bool) -> None:
        self.hd2d.preview_active = value

    @property
    def _hd2d_preview_snapshot(self) -> Any:
        return self.hd2d.preview_snapshot

    @_hd2d_preview_snapshot.setter
    def _hd2d_preview_snapshot(self, value: Any) -> None:
        self.hd2d.preview_snapshot = value

    @property
    def _hd2d_preview_preset_id(self) -> Optional[str]:
        return self.hd2d.preview_preset_id

    @_hd2d_preview_preset_id.setter
    def _hd2d_preview_preset_id(self, value: Optional[str]) -> None:
        self.hd2d.preview_preset_id = value

    # Alt-drag duplicate state accessors (DELEGATED to EditorDuplicateController)
    @property
    def _alt_dup_active(self) -> bool:
        return self.duplicate.active

    @_alt_dup_active.setter
    def _alt_dup_active(self, value: bool) -> None:
        self.duplicate.active = value

    @property
    def _alt_dup_specs(self) -> Tuple[Any, ...] | None:
        return self.duplicate.specs

    @_alt_dup_specs.setter
    def _alt_dup_specs(self, value: Tuple[Any, ...] | None) -> None:
        self.duplicate.specs = value

    @property
    def _alt_dup_pivot_new_id(self) -> str | None:
        return self.duplicate.pivot_new_id

    @_alt_dup_pivot_new_id.setter
    def _alt_dup_pivot_new_id(self, value: str | None) -> None:
        self.duplicate.pivot_new_id = value

    @property
    def _alt_dup_drag_start_world(self) -> Tuple[float, float] | None:
        return self.duplicate.drag_start_world

    @_alt_dup_drag_start_world.setter
    def _alt_dup_drag_start_world(self, value: Tuple[float, float] | None) -> None:
        self.duplicate.drag_start_world = value

    @property
    def _alt_dup_last_world(self) -> Tuple[float, float] | None:
        return self.duplicate.last_world

    @_alt_dup_last_world.setter
    def _alt_dup_last_world(self, value: Tuple[float, float] | None) -> None:
        self.duplicate.last_world = value

    @property
    def _alt_dup_original_selection(self) -> List[str] | None:
        return self.duplicate.original_selection

    @_alt_dup_original_selection.setter
    def _alt_dup_original_selection(self, value: List[str] | None) -> None:
        self.duplicate.original_selection = value

    @property
    def _alt_dup_original_primary(self) -> str | None:
        return self.duplicate.original_primary

    @_alt_dup_original_primary.setter
    def _alt_dup_original_primary(self, value: str | None) -> None:
        self.duplicate.original_primary = value

    # Marquee selection state accessors (DELEGATED to EditorMarqueeController)
    @property
    def _marquee_active(self) -> bool:
        return self.marquee.active

    @_marquee_active.setter
    def _marquee_active(self, value: bool) -> None:
        self.marquee.active = value

    @property
    def _marquee_start_world(self) -> Tuple[float, float] | None:
        return self.marquee.start_world

    @_marquee_start_world.setter
    def _marquee_start_world(self, value: Tuple[float, float] | None) -> None:
        self.marquee.start_world = value

    @property
    def _marquee_end_world(self) -> Tuple[float, float] | None:
        return self.marquee.end_world

    @_marquee_end_world.setter
    def _marquee_end_world(self, value: Tuple[float, float] | None) -> None:
        self.marquee.end_world = value

    @property
    def _marquee_shift(self) -> bool:
        return self.marquee.shift

    @_marquee_shift.setter
    def _marquee_shift(self, value: bool) -> None:
        self.marquee.shift = value

    # Keymap overrides accessor (DELEGATED to EditorKeymapController)
    @property
    def _keymap_overrides(self) -> dict[str, str]:
        return self.keymap.keymap_overrides

    # -------------------------------------------------------------------------
    # World-Space Drawing
    # DELEGATED to EditorDrawController
    # -------------------------------------------------------------------------

    def draw_world(self) -> None:
        """Draws in world space (camera active).

        DELEGATED to EditorDrawController.
        """
        self.draw.draw_world()

    def draw_overlay(self) -> None:
        """Draws in screen space (UI)."""
        self.overlay.draw_overlay()

    def _quest_definitions(self) -> Dict[str, Dict[str, Any]]:
        return self.dialogue._quest_definitions()

    def _related_quest_ids(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> set[str]:
        return self.dialogue._related_quest_ids(sprite)


    def set_status(self, message: str, *, seconds: float = 1.5) -> None:
        self._status_message = str(message)
        self._status_until = float(time.time()) + float(seconds)

    def _update_status(self) -> None:
        if not self._status_message:
            return
        if float(time.time()) >= float(self._status_until):
            self._status_message = None
            self._status_until = 0.0

    def _resolve_prefab_source_path(self, prefab_id: str) -> tuple["Path", bool]:
        return self.prefab.resolve_prefab_source_path(prefab_id)

    def _load_prefab_entries(self, path: "Path") -> list[dict[str, Any]] | None:
        return self.prefab.load_prefab_entries(path)

    def _write_prefab_entries(self, path: "Path", entries: list[dict[str, Any]]) -> None:
        self.prefab.write_prefab_entries(path, entries)

    def _update_prefab_entry(
        self,
        path: "Path",
        prefab_id: str,
        entry_payload: dict[str, Any],
        *,
        status_prefix: str,
    ) -> bool:
        return self.prefab.update_prefab_entry(path, prefab_id, entry_payload, status_prefix=status_prefix)

    def _promote_prefab_shapes(self) -> bool:
        return self.prefab.promote_prefab_shapes()

    def _apply_prefab_shapes(self, *, only_missing: bool) -> bool:
        return self.prefab.apply_prefab_shapes(only_missing=only_missing)

    def _toggle_zone_edit_target(self) -> bool:
        return self.shape.toggle_zone_edit_target()

    # --- Helper Methods for Behaviours ---

    def _get_patrol_behaviour(self, entity: optional_arcade.arcade.Sprite) -> Optional[Any]:
        return self.shape.get_patrol_behaviour(entity)

    def _get_patrol_points(self, patrol_behaviour) -> list:
        return self.shape.get_patrol_points(patrol_behaviour)

    def _add_waypoint(self, patrol_behaviour, x: float, y: float):
        self.shape.add_waypoint(patrol_behaviour, x, y)

    def _remove_waypoint(self, behaviour: Any, index: int) -> None:
        self.shape.remove_waypoint(behaviour, index)

    def _move_waypoint(self, behaviour: Any, index: int, dx: float, dy: float) -> None:
        self.shape.move_waypoint(behaviour, index, dx, dy)

    def _get_zone_behaviours(self, entity: Optional[optional_arcade.arcade.Sprite]) -> List[Any]:
        return self.shape.get_zone_behaviours(entity)

    def _get_zone_behaviour(self, entity: Optional[optional_arcade.arcade.Sprite]) -> Optional[Any]:
        return self.shape.get_zone_behaviour(entity)

    def _cycle_zone_behaviour(self) -> bool:
        return self.shape.cycle_zone_behaviour()

    def _resize_zone(self, behaviour: Any, dx: float, dy: float) -> None:
        self.shape.resize_zone(behaviour, dx, dy)

    def _update_behaviour_config(self, behaviour: Any, param_name: str, value: Any) -> None:
        # Similar to _update_param but takes behaviour instance
        if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
            behaviour.config[param_name] = value

        # Also need to update the entity data for saving
        behaviour_name = getattr(behaviour, "mesh_behaviour_type", None)
        if behaviour_name:
            self._update_param(behaviour_name, param_name, value)

    def undo_last(self) -> None:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "undo"):
            undo_ctrl.undo()
            return
        editor_ops.undo_last(self)

    def redo_last(self) -> None:
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "redo"):
            undo_ctrl.redo()
            return
        editor_ops.redo_last(self)

    def _push_command(self, cmd: Dict[str, Any]) -> None:
        if isinstance(cmd, dict):
            from engine.editor.editor_command_push_model import (  # noqa: PLC0415
                backfill_label_from_action,
                compute_command_backfill,
            )

            # First pass: backfill action_id, detail, label from command type
            compute_command_backfill(cmd)

            # Second pass: if label still missing, try to get from action registry
            if "label" not in cmd:
                action_id = cmd.get("action_id")
                if isinstance(action_id, str) and action_id:
                    from engine.editor.editor_actions import find_action, get_editor_actions  # noqa: PLC0415

                    actions = get_editor_actions(self, self.window)
                    action = find_action(actions, action_id)
                    title = action.title if action is not None else ""
                    backfill_label_from_action(cmd, action_id, title)
        undo_ctrl = getattr(self, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "push"):
            undo_ctrl.push(cmd, label=cmd.get("label") if isinstance(cmd.get("label"), str) else None)
        else:
            self.undo_stack.append(cmd)
            self.redo_stack.clear()
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        self.scene_dirty = True
        self.dirty_state.is_dirty = True

    def _mark_clean(self) -> None:
        self.scene_dirty = False
        self.dirty_state.is_dirty = False

    def confirm_unsaved_changes(self, reason: str, action: Callable[[], None]) -> bool:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return False
        return confirm.confirm_unsaved_changes(reason, action)

    def _close_unsaved_confirm(self, *, clear_pending: bool = False) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.close(clear_pending=clear_pending)

    def _run_pending_confirm_action(self) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm._run_pending_confirm_action()

    def _apply_unsaved_confirm_choice(self, choice_index: int) -> None:
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return
        confirm.apply_choice(choice_index)

    def _handle_unsaved_confirm_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        confirm = getattr(self, "unsaved_confirm", None)
        if confirm is None:
            return False
        return confirm.handle_input(key, modifiers)

    # -------------------------------------------------------------------------
    # Entity CRUD and Transform Operations
    # DELEGATED to EditorEntityOpsController
    # -------------------------------------------------------------------------

    def _find_entity_by_name(self, name: str) -> Optional[optional_arcade.arcade.Sprite]:
        """Find entity by name. DELEGATED to EditorEntityOpsController."""
        return self.entity_ops.find_entity_by_name(name)

    def _find_entity_by_id(self, entity_id: str) -> Optional[optional_arcade.arcade.Sprite]:
        """Find entity by id. DELEGATED to EditorEntityOpsController."""
        return self.entity_ops.find_entity_by_id(entity_id)

    def _apply_rotate_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a RotateEntities command.

        DELEGATED to EditorEntityOpsController.
        """
        self.entity_ops.apply_rotate_entities_cmd(cmd, use_before)

    def _apply_scale_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a ScaleEntities command.

        DELEGATED to EditorEntityOpsController.
        """
        self.entity_ops.apply_scale_entities_cmd(cmd, use_before)

    def _revert_command(self, cmd: Dict[str, Any]) -> None:
        """Revert (undo) a command by type dispatch.

        DELEGATED to EditorCommandDispatchController.
        """
        self.command_dispatch.revert_command(cmd)

    def _apply_command(self, cmd: Dict[str, Any]) -> None:
        """Apply (redo) a command by type dispatch.

        DELEGATED to EditorCommandDispatchController.
        """
        self.command_dispatch.apply_command(cmd)

    def _apply_background_planes_payload(self, planes: Any) -> None:
        sc = getattr(self.window, "scene_controller", None)
        scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if not isinstance(scene, dict):
            return
        if not isinstance(planes, list):
            planes = []
        scene["background_planes"] = copy.deepcopy(planes)
        if sc is not None:
            try:
                from engine.parallax_model import parse_background_planes  # noqa: PLC0415

                sc._background_planes = parse_background_planes(scene)
                cache = getattr(sc, "_background_plane_texture_cache", None)
                if isinstance(cache, dict):
                    cache.clear()
            except Exception:
                pass

    def _revert_alt_drag_duplicate_cmd(self, cmd: Dict[str, Any]) -> None:
        """Revert an alt-drag duplicate command (undo)."""
        from .editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            AltDragDuplicateCommand,
            remove_alt_drag_duplicates,
        )
        from .editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        alt_cmd = AltDragDuplicateCommand.from_dict(cmd)

        # Remove sprites for duplicated entities
        for spec in alt_cmd.specs:
            sprite = get_sprite_for_entity_id(self, spec.new_id)
            if sprite:
                self._delete_entity_internal(sprite)

        # Remove from scene data
        sc = getattr(self.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                new_scene = remove_alt_drag_duplicates(scene_data, alt_cmd)
                sc._loaded_scene_data = new_scene

    def _apply_alt_drag_duplicate_cmd(self, cmd: Dict[str, Any]) -> None:
        """Apply an alt-drag duplicate command (redo).

        DELEGATED to EditorDuplicateController.
        """
        self.duplicate.apply_command(cmd)

    def _create_entity_internal(self, entity_def: Dict[str, Any]) -> Optional[optional_arcade.arcade.Sprite]:
        """Create entity from definition. DELEGATED to EditorEntityOpsController."""
        return self.entity_ops.create_entity_internal(entity_def)

    def _delete_entity_internal(self, sprite: optional_arcade.arcade.Sprite) -> None:
        """Delete entity sprite. DELEGATED to EditorEntityOpsController."""
        self.entity_ops.delete_entity_internal(sprite)

    def toggle_hierarchy(self) -> None:
        self.hierarchy.toggle_hierarchy()

    def toggle_entity_panels(self) -> bool:
        return self.entity_panels_controller.toggle_entity_panels()

    def toggle_scene_switcher(self) -> bool:
        return self.scene_browse.toggle_scene_switcher()

    def toggle_scene_browser(self) -> bool:
        return self.scene_browse.toggle_scene_browser()

    def toggle_command_palette(self) -> bool:
        return self.search.toggle_command_palette()

    # -------------------------------------------------------------------------
    # Find Everything (Ctrl+K)
    # -------------------------------------------------------------------------

    def toggle_find_everything(self) -> bool:
        return self.search.toggle_find_everything()

    def close_find_everything(self) -> None:
        self.search.close_find_everything()

    # -------------------------------------------------------------------------
    # HD-2D Preset Preview (non-destructive preview while browsing)
    # DELEGATED to EditorHd2dController
    # -------------------------------------------------------------------------

    def preview_hd2d_preset(self, preset_id: str) -> bool:
        """Begin or update HD-2D preset preview without marking dirty or pushing undo.

        DELEGATED to EditorHd2dController.

        Args:
            preset_id: The preset to preview (e.g., "soft", "crisp").

        Returns:
            True if preview was applied.
        """
        return self.hd2d.preview_preset(preset_id)

    def _cancel_hd2d_preview(self) -> None:
        """Cancel active HD2D preview and restore original settings.

        DELEGATED to EditorHd2dController.
        Does NOT mark dirty or push undo - this is non-destructive.
        """
        self.hd2d.cancel_preview()

    def commit_hd2d_preset(self, preset_id: str) -> bool:
        """Commit an HD2D preset (cancels preview first, then applies via action).

        DELEGATED to EditorHd2dController.
        This marks dirty and pushes ONE undo entry.

        Args:
            preset_id: The preset to commit.

        Returns:
            True if preset was committed.
        """
        return self.hd2d.commit_preset(preset_id)

    def _maybe_preview_hd2d_from_selection(self) -> None:
        """Check if current find selection is an HD2D preset and preview it.
        
        DEPRECATED: delegated to EditorUIFlowController
        """
        self._ui_flow_ctl.maybe_preview_from_selection()

    def maybe_auto_apply_hd2d_defaults(self) -> bool:
        """Auto-apply HD2D defaults to the current scene if configured.

        DELEGATED to EditorHd2dController.

        This is called after scene load. It will apply the default preset
        ONLY if:
        1. A default preset is configured in workspace settings
        2. The scene does NOT already have any HD2D setting keys

        Does NOT push undo or mark dirty (silent auto-apply).

        Returns:
            True if defaults were applied, False otherwise.
        """
        return self.hd2d.maybe_auto_apply_defaults()

    def upgrade_scene_to_hd2d_defaults(self) -> bool:
        """Explicitly upgrade scene to HD2D defaults.

        DELEGATED to EditorHd2dController.

        This is the user-triggered action. It:
        1. Uses the configured default preset (no-op if not set)
        2. Only fills missing HD2D keys (safe merge)
        3. Marks dirty
        4. Pushes ONE undo entry

        Returns:
            True if upgrade was applied, False otherwise.
        """
        return self.hd2d.upgrade_scene_to_defaults()

    def set_find_query(self, text: str) -> None:
        self.search.set_find_query(text)

    def append_find_query_text(self, text: str) -> bool:
        return self.search.append_find_query_text(text)

    def backspace_find_query(self) -> bool:
        return self.search.backspace_find_query()

    def move_find_selection(self, delta: int) -> None:
        self.search.move_find_selection(delta)

    def activate_find_selection(self) -> bool:
        return self.search.activate_find_selection()

    def _refresh_find_everything_results(self) -> None:
        """DEPRECATED: delegated to EditorUIFlowController."""
        self.search.refresh_find_everything_results()

    def _build_find_everything_items(self) -> list[Any]:
        """DEPRECATED: delegated to EditorUIFlowController."""
        return self.search.build_find_everything_items()

    def _get_find_everything_problems(self) -> list[Any]:
        """DEPRECATED: delegated to EditorUIFlowController."""
        return self.search.get_find_everything_problems()

    # -------------------------------------------------------------------------
    # Find/Activate Actions
    # DELEGATED to EditorFindActionsController
    # -------------------------------------------------------------------------

    def _activate_find_command(self, command_id: str) -> bool:
        """Activate a command from find-everything or command palette.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.activate_find_command(command_id)

    def _activate_find_scene(self, scene_id: str) -> bool:
        """Activate a scene from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.activate_find_scene(scene_id)

    def _activate_find_entity(self, entity_id: str) -> bool:
        """Activate an entity from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.activate_find_entity(entity_id)

    def _activate_find_asset(self, asset_path: str) -> bool:
        """Activate an asset from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.activate_find_asset(asset_path)

    def _spawn_find_asset(self, asset_path: str) -> bool:
        """Spawn an asset from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.spawn_find_asset(asset_path)

    def _copy_find_asset_path(self, asset_path: str) -> bool:
        """Copy asset path to clipboard from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.copy_find_asset_path(asset_path)

    def _activate_find_problem(self, issue_id: str) -> bool:
        """Activate a problem from find-everything.

        DELEGATED to EditorFindActionsController.
        """
        return self.find_actions.activate_find_problem(issue_id)

    def _handle_find_everything_input(self, key: int, modifiers: int) -> bool:
        return self.search.handle_find_everything_input(key, modifiers)

    def toggle_asset_browser(self) -> bool:
        return self.asset_browser.toggle_asset_browser()

    def refresh_asset_browser(self) -> None:
        self.asset_browser.refresh_asset_browser()

    def set_asset_browser_filter(self, text: str) -> None:
        self.asset_browser.set_asset_browser_filter(text)

    def cycle_asset_browser_kind(self) -> None:
        self.asset_browser.cycle_asset_browser_kind()

    def _filter_asset_browser(self) -> None:
        self.asset_browser._filter_asset_browser()

    def asset_browser_move_selection(self, delta: int) -> None:
        self.asset_browser.asset_browser_move_selection(delta)

    def _handle_asset_browser_input(self, key: int, modifiers: int) -> bool:
        return self.asset_browser.handle_asset_browser_input(key, modifiers)

    def _activate_selected_asset(self) -> None:
        self.asset_browser._activate_selected_asset()

    def place_asset_at(self, x: float, y: float) -> None:
        self.asset_browser.place_asset_at(x, y)




    def record_recent_scene(self, scene_path: str) -> None:
        normalized = normalize_scene_path(scene_path)
        if not normalized:
            return
        recent = [path for path in self.scene_switcher_recent if path != normalized]
        recent.insert(0, normalized)
        self.scene_switcher_recent = recent[:SCENE_SWITCHER_RECENT_LIMIT]

    def _refresh_scene_switcher_items(self) -> None:
        self.scene_browse.refresh_scene_switcher_items()

    def _scene_switcher_all_options(self) -> list[tuple[str, str]]:
        return self.scene_browse.scene_switcher_all_options()

    def _scene_switcher_visible_options(self) -> list[tuple[str, str]]:
        return self.scene_browse.scene_switcher_visible_options()

    def _scene_switcher_clamp_index(self, count: int) -> None:
        self.scene_browse.scene_switcher_clamp_index(count)

    def _scene_switcher_lines(self) -> list[str]:
        return self.scene_browse.scene_switcher_lines()

    def _refresh_scene_browser_rows(self) -> None:
        self.scene_browse.refresh_scene_browser_rows()

    def _scene_browser_rows(self) -> list["SceneRow"]:
        return self.scene_browse.scene_browser_rows()

    def _scene_browser_clamp_index(self, count: int) -> None:
        self.scene_browse.scene_browser_clamp_index(count)

    def _scene_browser_window(self, count: int) -> tuple[int, int]:
        return self.scene_browse.scene_browser_window(count)

    def _scene_browser_layout(self, count: int) -> dict[str, float]:
        return self.scene_browse.scene_browser_layout(count)

    def _scene_browser_lines(self) -> list[str]:
        return self.scene_browse.scene_browser_lines()

    def _open_scene_by_id(self, scene_id: str) -> bool:
        return self.scene_open.open_scene_by_id(scene_id)

    def _scene_switcher_open_selected(self) -> bool:
        return self.scene_browse.scene_switcher_open_selected()

    def _scene_browser_open_selected(self) -> bool:
        return self.scene_browse.scene_browser_open_selected()

    def _scene_browser_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        return self.scene_browse.scene_browser_handle_mouse_click(x, y, button)

    # -------------------------------------------------------------------------
    # Project Explorer Panel
    # -------------------------------------------------------------------------

    def _refresh_project_explorer_rows(self) -> None:
        self.project_explorer_actions.refresh_rows()

    def _project_explorer_display_rows(self) -> list[Any]:
        return self.project_explorer_actions.get_display_rows()

    def _project_explorer_selectable_rows(self) -> list[Any]:
        return self.project_explorer_actions.get_selectable_rows()

    def _activate_project_explorer_selected(self) -> bool:
        return self.project_explorer_actions.activate_selected()

    def _handle_project_explorer_input(self, key: int, modifiers: int) -> bool:
        return self.project_explorer_actions.handle_input(key, modifiers)

    def _project_explorer_handle_mouse_click(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return self.project_explorer_actions.handle_mouse_click(x, y, button, modifiers)

    def _activate_project_recent(self, recent: Any) -> bool:
        return self.project_explorer_actions.activate_recent(recent)

    def _push_project_recent(self, kind: str, rel_path: str, label: str) -> None:
        self.project_explorer_actions.push_recent(kind, rel_path, label)

    def _project_explorer_recent_payloads(self) -> list[dict[str, Any]]:
        return self.project_explorer_actions.get_recent_payloads()

    def _clear_project_recents(self) -> bool:
        return self.project_explorer_actions.clear_recents()


    def reveal_in_project_explorer(self, target_path: str) -> bool:
        return self.project_explorer_actions.reveal_in_explorer(target_path)


    def reveal_current_in_project_explorer(self) -> bool:
        return self.project_explorer_actions.reveal_current_in_explorer()

    def _get_current_scene_path(self) -> str | None:
        return self.project_explorer_actions.get_current_scene_path()

    def _get_selected_entity_asset_path(self) -> str | None:
        return self.project_explorer_actions.get_selected_entity_asset_path()

    def copy_project_explorer_selected_path(self) -> bool:
        return self.project_explorer_actions.copy_selected_path()

    def _try_copy_to_os_clipboard(self, text: str) -> None:
        self.project_explorer_actions.try_copy_to_os_clipboard(text)

    def safe_rename_selected_asset(self, new_name: str) -> bool:
        return self.project_explorer_actions.safe_rename_selected_asset(new_name)

    def safe_move_selected_asset(self, dest_folder_rel: str) -> bool:
        return self.project_explorer_actions.safe_move_selected_asset(dest_folder_rel)

    def safe_move_selected_assets(self, dest_folder_rel: str) -> bool:
        return self.project_explorer_actions.safe_move_selected_assets(dest_folder_rel)

    def prompt_project_explorer_move_destination(self, on_confirm) -> bool:
        return self.project_explorer_actions.prompt_move_destination(on_confirm)

    def _get_selected_project_entry_path(self) -> str | None:
        return self.project_explorer_actions.get_selected_project_entry_path()

    # -------------------------------------------------------------------------
    # Undo History Panel
    # -------------------------------------------------------------------------

    def get_undo_history_entries(self) -> list[Any]:
        return self.history.get_entries()

    def get_filtered_undo_history_entries(self) -> list[Any]:
        return self.history.get_filtered_entries()

    def jump_undo_history_to(self, cursor_index: int) -> bool:
        return self.history.jump_to(cursor_index)

    def _handle_history_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return self.history.handle_input(key, modifiers)

    def _history_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        return self.history.handle_mouse_click(x, y, button)

    # -------------------------------------------------------------------------
    # Problems Panel
    # -------------------------------------------------------------------------

    def scan_scene_problems(self) -> int:
        """Scan current scene JSON for issues."""
        from pathlib import Path  # noqa: PLC0415

        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)

        repo_root = self._get_repo_root()
        if not isinstance(repo_root, Path):
            repo_root = Path(repo_root)

        resolver = getattr(self, "_prefab_resolver", None)
        if not callable(resolver):
            def resolver(prefab_id: str) -> bool:
                try:
                    from engine.prefabs import get_prefab_manager  # noqa: PLC0415
                    manager = get_prefab_manager()
                    return bool(manager.get_prefab(prefab_id))
                except Exception:  # noqa: BLE001
                    return False

        issues = self.problems.scan_scene(scene, repo_root, resolver)

        hud = getattr(self.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(tr("UI_PROBLEMS_SCANNED"), seconds=2.5)
        return len(issues)

    def get_filtered_problems(self) -> list[Any]:
        return self.problems.get_filtered_issues()

    def _clamp_problems_selection(self) -> None:
        # Managed by content controller
        pass

    def _problems_input_blocked(self) -> bool:
        return self.problems.input_blocked(self)

    def apply_selected_problem_fix(self) -> bool:
        return self._apply_selected_problem_fix(advance=False)

    def apply_fix_all_safe(self) -> bool:
        return self._apply_all_safe_problem_fixes()

    def _open_problems_preview(self) -> bool:
        return self.problems.open_preview(self)

    def _close_problems_preview(self) -> None:
        self.problems.close_preview(self)

    def _toggle_problems_preview(self) -> bool:
        return self.problems.toggle_preview(self)

    def _apply_selected_problem_fix(self, *, advance: bool) -> bool:
        return self.problems.apply_selected_fix(self, advance=advance)

    def _apply_all_safe_problem_fixes(self) -> bool:
        return self.problems.apply_all_safe_fixes(self)

    def _problems_toast_no_fix(self) -> None:
        self.problems._toast_no_fix(self)

    def _apply_scene_fix_update(self, new_scene: dict[str, Any]) -> None:
        self.problems._apply_scene_fix_update(self, new_scene)

    def _refresh_after_scene_fix(self) -> None:
        self.problems._refresh_after_scene_fix(self)

    def _handle_problems_input(self, key: int, modifiers: int) -> bool:
        return self.problems.handle_input(self, key, modifiers)

    def _problems_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        return self.problems.handle_mouse_click(self, x, y, button)

    def _debug_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        return self.debug_panels.handle_mouse_click(x, y, button)

    def _refresh_hierarchy_list(self) -> None:
        self.hierarchy.refresh_hierarchy_list()

    def _build_hierarchy_list(self) -> List[optional_arcade.arcade.Sprite]:
        return self.hierarchy.build_hierarchy_list()

    def _entity_panels_scene_data(self) -> Dict[str, Any]:
        return self.entity_panels_controller.entity_panels_scene_data()

    def _resolve_entity_panels_id(self, entity: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
        return self.entity_panels_controller.resolve_entity_panels_id(entity, fallback_index)

    def _entity_panels_selected_id_value(self) -> str | None:
        return self.entity_panels_controller.entity_panels_selected_id_value()

    def _prefab_variant_label(self, entity_data: dict[str, Any]) -> str | None:
        return self.prefab.prefab_variant_label(entity_data)

    def _prefab_variant_override_rows(self, entity_data: dict[str, Any]) -> list[DiffRow]:
        return self.prefab.prefab_variant_override_rows(entity_data)

    def _entity_panels_prefab_override_rows(self) -> list[DiffRow]:
        return self.prefab.entity_panels_prefab_override_rows()

    def _prefab_override_base_value(self, base_entity: dict[str, Any], key: str) -> tuple[bool, Any]:
        return self.prefab.prefab_override_base_value(base_entity, key)

    def _apply_prefab_override_payload(self, entity_data: dict[str, Any], updated: dict[str, Any]) -> None:
        self.prefab.apply_prefab_override_payload(entity_data, updated)

    def _apply_prefab_override_entity_value(
        self,
        sprite: optional_arcade.arcade.Sprite,
        key: str,
        value: Any,
        *,
        present: bool,
    ) -> None:
        self.prefab.apply_prefab_override_entity_value(sprite, key, value, present=present)

    def _apply_prefab_override_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        self.prefab.apply_prefab_override_command(cmd, use_before=use_before)

    def _apply_prefab_override_bulk_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        self.prefab.apply_prefab_override_bulk_command(cmd, use_before=use_before)

    def _filter_entity_panels_items(self, items: list[EntitySummary]) -> list[EntitySummary]:
        return self.entity_panels_controller.filter_entity_panels_items(items)

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:
        self.entity_panels_controller.refresh_entity_panels_list(sync_selected=sync_selected)

    def _get_entity_panels_list(self) -> list[EntitySummary]:
        return self.entity_panels_controller.get_entity_panels_list()

    def _resolve_display_name(self, sprite: optional_arcade.arcade.Sprite, fallback_index: Optional[int] = None) -> str:
        return self.entity_panels_controller.resolve_display_name(sprite, fallback_index)

    def _get_sprite_index(self, sprite: optional_arcade.arcade.Sprite) -> Optional[int]:
        return self.entity_panels_controller.get_sprite_index(sprite)

    def _get_display_name_for_sprite(self, sprite: optional_arcade.arcade.Sprite) -> str:
        return self.entity_panels_controller.get_display_name_for_sprite(sprite)

    def get_gizmo_feedback_state(self) -> "GizmoFeedbackState":
        """Get current state for gizmo overlay rendering.

        DELEGATED to EditorCursorController.

        Returns:
            GizmoFeedbackState snapshot for overlay to render.
        """
        return self.cursor.get_gizmo_feedback_state()

    # -------------------------------------------------------------------------
    # Dock Collapse / Viewport Maximize
    # -------------------------------------------------------------------------

    def get_viewport_maximized(self) -> bool:
        """Get whether the viewport is maximized."""
        return self.dock.get_viewport_maximized()

    def toggle_viewport_maximized(self) -> None:
        """Toggle viewport maximized state.

        When turning ON: stores current collapsed states and forces both docks hidden.
        When turning OFF: restores previous collapsed states.
        """
        self.dock.toggle_viewport_maximized(self)

    def get_effective_dock_widths(self, window_w: int) -> Tuple[int, int]:
        """Get effective dock widths accounting for collapse/maximize state.

        Args:
            window_w: Window width for clamping.

        Returns:
            Tuple of (left_w_effective, right_w_effective).
        """
        return self.dock.get_effective_dock_widths(window_w)

    # -------------------------------------------------------------------------
    # Cursor Hint / Affordance Feedback
    # DELEGATED to EditorCursorController
    # -------------------------------------------------------------------------

    @property
    def _last_mouse_x(self) -> float:
        return self.cursor._last_mouse_x

    @_last_mouse_x.setter
    def _last_mouse_x(self, value: float) -> None:
        self.cursor._last_mouse_x = value

    @property
    def _last_mouse_y(self) -> float:
        return self.cursor._last_mouse_y

    @_last_mouse_y.setter
    def _last_mouse_y(self, value: float) -> None:
        self.cursor._last_mouse_y = value

    def set_last_mouse_pos(self, x: float, y: float) -> None:
        """Update the last known mouse position.

        DELEGATED to EditorCursorController.

        Args:
            x: Mouse X in screen coordinates.
            y: Mouse Y in screen coordinates.
        """
        self.cursor.update_mouse_pos(x, y)

    def get_last_mouse_pos(self) -> Tuple[float, float]:
        """Get the last known mouse position.

        DELEGATED to EditorCursorController.

        Returns:
            Tuple of (x, y) in screen coordinates.
        """
        return self.cursor.get_last_mouse_pos()

    def get_cursor_hint_text(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint text based on current editor state.

        DELEGATED to EditorCursorController.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Hint text string or None if no hint.
        """
        return self.cursor.get_cursor_hint_text(window_w, window_h)

    def get_cursor_hint_kind(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint kind for cursor affordance.

        DELEGATED to EditorCursorController.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Cursor kind string or None when editor is inactive.
        """
        return self.cursor.get_cursor_hint_kind(window_w, window_h)

    def _compute_cursor_hint(self, window_w: int, window_h: int):
        """Compute cursor hint. DELEGATED to EditorCursorController."""
        return self.cursor._compute_cursor_hint(window_w, window_h)

    # -------------------------------------------------------------------------
    # Marquee Box Selection
    # DELEGATED to EditorMarqueeController
    # -------------------------------------------------------------------------

    def begin_marquee(self, world_x: float, world_y: float, shift: bool) -> None:
        """Begin a marquee box selection.

        DELEGATED to EditorMarqueeController.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
            shift: Whether Shift modifier is held.
        """
        self.marquee.begin(world_x, world_y, shift)

    def update_marquee(self, world_x: float, world_y: float) -> None:
        """Update marquee end point during drag.

        DELEGATED to EditorMarqueeController.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        self.marquee.update(world_x, world_y)

    def end_marquee(self) -> None:
        """Commit marquee selection and deactivate.

        DELEGATED to EditorMarqueeController.
        """
        self.marquee.end()

    def cancel_marquee(self) -> None:
        """Cancel marquee selection without committing.

        DELEGATED to EditorMarqueeController.
        """
        self.marquee.cancel()

    def _reset_marquee(self) -> None:
        """Reset marquee state.

        DELEGATED to EditorMarqueeController.
        """
        self.marquee.reset()

    # -------------------------------------------------------------------------
    # Alt-Drag Duplicate
    # DELEGATED to EditorDuplicateController
    # -------------------------------------------------------------------------

    def begin_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Begin alt-drag duplicate operation.

        DELEGATED to EditorDuplicateController.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
        """
        self.duplicate.begin(world_x, world_y)

    def update_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Update alt-drag duplicate positions during drag.

        DELEGATED to EditorDuplicateController.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        self.duplicate.update(world_x, world_y)

    def cancel_alt_drag_duplicate(self) -> None:
        """Cancel alt-drag duplicate and remove duplicated entities.

        DELEGATED to EditorDuplicateController.
        """
        self.duplicate.cancel()

    def end_alt_drag_duplicate(self) -> None:
        """Commit alt-drag duplicate and push undo command.

        DELEGATED to EditorDuplicateController.
        """
        self.duplicate.end()

    def _reset_alt_drag_duplicate(self) -> None:
        """Reset alt-drag duplicate state.

        DELEGATED to EditorDuplicateController.
        """
        self.duplicate.reset()

    def _get_entity_tags(self, sprite: optional_arcade.arcade.Sprite) -> List[str]:
        tags: List[str] = []
        entity_data = getattr(sprite, "mesh_entity_data", {}) or {}
        raw_tags = entity_data.get("tags")
        if isinstance(raw_tags, (list, tuple, set)):
            for entry in raw_tags:
                if isinstance(entry, str) and entry.strip():
                    tags.append(entry.strip())
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags.append(raw_tags.strip())

        single_tag = getattr(sprite, "mesh_tag", None)
        if isinstance(single_tag, str) and single_tag.strip():
            tag_value = single_tag.strip()
            if tag_value not in tags:
                tags.append(tag_value)

        return tags

    def _entity_panels_outliner_lines(self) -> list[str]:
        return self.entity_panels_controller.entity_panels_outliner_lines()

    def _entity_panels_inspector_lines(self) -> list[str]:
        return self.entity_panels_controller.entity_panels_inspector_lines()

    def _entity_panels_format_field_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
        kind: str,
    ) -> str:
        return self.entity_panels_controller.entity_panels_format_field_value(entity_data, sprite, key, kind)

    def _entity_panels_numeric_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
    ) -> float:
        return self.entity_panels_controller.entity_panels_numeric_value(entity_data, sprite, key)

    def _entity_panels_select_current(self) -> bool:
        return self.entity_panels_controller.entity_panels_select_current()

    def _entity_panels_find_sprite(self, summary: EntitySummary) -> Optional[optional_arcade.arcade.Sprite]:
        return self.entity_panels_controller.entity_panels_find_sprite(summary)

    def _entity_panels_begin_text_edit(self, field: str, initial: str) -> None:
        self.entity_panels_controller.entity_panels_begin_text_edit(field, initial)

    def _entity_panels_cancel_text_edit(self) -> None:
        self.entity_panels_controller.entity_panels_cancel_text_edit()

    def _entity_panels_commit_text_edit(self) -> bool:
        return self.entity_panels_controller.entity_panels_commit_text_edit()

    def _entity_panels_apply_field_update(self, field: str, value: Any) -> bool:
        return self.entity_panels_controller.entity_panels_apply_field_update(field, value)

    def _entity_panels_apply_prefab_override(self, key: str, value: Any) -> bool:
        return self.prefab.entity_panels_apply_prefab_override(key, value)

    def _entity_panels_revert_prefab_override(self, row: DiffRow) -> bool:
        return self.prefab.entity_panels_revert_prefab_override(row)

    def _entity_panels_clear_prefab_overrides(self) -> bool:
        return self.prefab.entity_panels_clear_prefab_overrides()

    # --------------------------------------------------------------------------
    # Component Inspector Input Handling
    # --------------------------------------------------------------------------

    def _handle_inspector_component_input(self, key: int, modifiers: int) -> bool:
        return self.inspector.handle_inspector_component_input(key, modifiers)

    def _get_selected_entity_json_for_inspector(self) -> dict[str, Any] | None:
        return self.inspector.get_selected_entity_json_for_inspector()

    def _inspector_begin_text_edit(self, initial: str) -> None:
        self.inspector.inspector_begin_text_edit(initial)

    def _inspector_cancel_text_edit(self) -> None:
        self.inspector.inspector_cancel_text_edit()

    def _inspector_commit_text_edit(self) -> bool:
        return self.inspector.inspector_commit_text_edit()

    def _apply_inspector_entity_update(self, new_entity_json: dict[str, Any], field_key: str) -> None:
        self.inspector.apply_inspector_entity_update(new_entity_json, field_key)

    def _get_entity_id_for_inspector(self) -> str | None:
        return self.inspector.get_entity_id_for_inspector()

    def _apply_inspector_to_sprite(self, field_key: str, value: Any) -> None:
        self.inspector.apply_inspector_to_sprite(field_key, value)

    def _handle_inspector_text_input(self, text: str) -> bool:
        return self.inspector.handle_inspector_text_input(text)

    # --------------------------------------------------------------------------
    # Component Inspector v1 Input Handling
    # --------------------------------------------------------------------------

    def _handle_component_inspector_v1_input(self, key: int, modifiers: int) -> bool:
        return self.inspector.handle_component_inspector_v1_input(key, modifiers)

    def _handle_add_component_picker_input(self, key: int, entity_json: Dict[str, Any]) -> bool:
        return self.inspector.handle_add_component_picker_input(key, entity_json)

    def _component_inspector_commit_text_edit(
        self, entity_json: Dict[str, Any], selection: Optional[Dict[str, Any]]
    ) -> bool:
        return self.inspector.component_inspector_commit_text_edit(entity_json, selection)

    def _apply_component_entity_update(self, new_entity_json: Dict[str, Any]) -> None:
        self.inspector.apply_component_entity_update(new_entity_json)

    def _sync_sprite_from_component_json(self, entity_json: Dict[str, Any]) -> None:
        """Sync runtime sprite state from component JSON."""
        if not self.selected_entity:
            return

        sprite = self.selected_entity

        # Get transform from components or legacy
        components = entity_json.get("components", {})
        transform = components.get("transform", {})

        # Fall back to top-level if not in components
        x = transform.get("x") if "x" in transform else entity_json.get("x")
        y = transform.get("y") if "y" in transform else entity_json.get("y")
        rot = transform.get("rot") if "rot" in transform else entity_json.get("rotation", 0.0)

        if x is not None:
            self.window.scene_controller._apply_entity_mutation(sprite, x=float(x))
        if y is not None:
            self.window.scene_controller._apply_entity_mutation(sprite, y=float(y))
        if rot is not None:
            sprite.angle = float(rot) % 360.0
            entity_data = getattr(sprite, "mesh_entity_data", {})
            if isinstance(entity_data, dict):
                entity_data["rotation"] = float(rot) % 360.0

    def _begin_hierarchy_rename(self) -> bool:
        return self.hierarchy.begin_hierarchy_rename()

    def _cancel_hierarchy_rename(self) -> None:
        self.hierarchy.cancel_hierarchy_rename()

    def _commit_hierarchy_rename(self) -> bool:
        return self.hierarchy.commit_hierarchy_rename()

    def _apply_entity_rename(self, sprite: optional_arcade.arcade.Sprite, new_name: str) -> None:
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        entity_data["name"] = new_name
        setattr(sprite, "mesh_entity_data", entity_data)
        setattr(sprite, "mesh_name", new_name)
        self._hierarchy_name_cache[id(sprite)] = new_name

    def _select_hierarchy_item(self, index: int) -> None:
        self.hierarchy.select_hierarchy_item(index)

    def _handle_hierarchy_input(self, key: int, modifiers: int) -> bool:
        return self.hierarchy.handle_hierarchy_input(key, modifiers)

    def _handle_entity_panels_input(self, key: int, modifiers: int) -> bool:
        return self.entity_panels_controller.handle_entity_panels_input(key, modifiers)

    def _handle_scene_switcher_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return self.scene_browse.handle_scene_switcher_input(key, modifiers)

    def _handle_scene_browser_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return self.scene_browse.handle_scene_browser_input(key, modifiers)

    def _handle_entity_panels_text_input(self, text: str) -> bool:
        return self.entity_panels_controller.handle_entity_panels_text_input(text)

    def _handle_scene_switcher_text_input(self, text: str) -> bool:
        return self.scene_browse.handle_scene_switcher_text_input(text)

    def _handle_scene_browser_text_input(self, text: str) -> bool:
        return self.scene_browse.handle_scene_browser_text_input(text)

    def _handle_context_menu_input(self, key: int, modifiers: int) -> bool:
        """Handle key input for the project explorer context menu (modal)."""
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if not panels_is_open(self, "project_context_menu"):
            return False
        # Route through scoped shortcut dispatch
        return editor_input._handle_editor_action_shortcut(self, key, modifiers)
        
    def open_project_explorer_context_menu(self, x: int, y: int) -> None:
        """Open the project explorer context menu."""
        self.project_explorer_actions.open_context_menu(x, y)

    def open_project_explorer_context_menu_at_selection(self) -> None:
        """Open the context menu anchored to the selected row (keyboard open)."""
        self.project_explorer_actions.open_context_menu_at_selection()

    def handle_text_input(self, text: str) -> None:
        editor_input.handle_text_input(self, text)
