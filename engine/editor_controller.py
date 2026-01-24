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

from engine.asset_index import AssetRow, scan_assets, filter_assets
from engine.workspace_settings import WorkspaceSettings, load_workspace, save_workspace
from engine.editor_asset_ops import spawn_entity_from_asset
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
    infer_zone_target_from_behaviour,
    is_hitbox_behaviour,
    is_trigger_behaviour,
    parse_flag_list,
)
from .editor_palette import DEFAULT_PREFAB_PATH
from .editor_palette_thumbs import DEFAULT_THUMB_SIZE, request_thumb, tick_thumb_generation
from .editor_entity_ops import EntitySummary, list_entities, update_entity_field
from .editor_runtime import input as editor_input
from .editor_runtime import ops as editor_ops
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
from .prefab_overrides import compute_prefab_overrides
from .ui_overlays.common import (
    _draw_rectangle_filled,
    draw_outline_centered,
    draw_panel_bg,
)
from engine.workspace_settings import load_workspace, save_workspace, WorkspaceSettings
from engine.repo_root import get_repo_root

if TYPE_CHECKING:
    from .game import GameWindow
    from .scene_index import SceneRow

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
from .editor.prefab_palette_panel import (
    parse_palette_filter as _parse_palette_filter_impl,
    filter_prefab_palette_items as _filter_prefab_palette_items_impl,
    palette_tag_frequencies as _palette_tag_frequencies_impl,
    normalize_entity_panel_tags as _normalize_entity_panel_tags_impl,
    apply_entity_panel_tag_delta as _apply_entity_panel_tag_delta_impl,
)
from .editor.dialogue_panel import (
    entity_has_dialogue as _entity_has_dialogue_impl,
    get_entity_dialogue_config as _get_entity_dialogue_config_impl,
    build_dialogue_nodes_list as _build_dialogue_nodes_list_impl,
    collect_dialogue_warnings as _collect_dialogue_warnings_impl,
    next_dialogue_field as _next_dialogue_field_impl,
    prev_dialogue_field as _prev_dialogue_field_impl,
    get_dialogue_edit_value as _get_dialogue_edit_value_impl,
    apply_dialogue_edit_to_root as _apply_dialogue_edit_to_root_impl,
)
from .editor.animation_panel import (
    entity_has_animator as _entity_has_animator_impl,
    get_animator_config as _get_animator_config_impl,
    get_animation_names as _get_animation_names_impl,
    apply_animator_runtime as _apply_animator_runtime_impl,
    next_animation_field as _next_animation_field_impl,
    prev_animation_field as _prev_animation_field_impl,
    cycle_animation_mode as _cycle_animation_mode_impl,
)
from .editor.scene_opening import (
    build_scene_switcher_rows as _build_scene_switcher_rows_impl,
    clamp_scene_selection_index as _clamp_scene_selection_index_impl,
    compute_scene_window as _compute_scene_window_impl,
    compute_scene_browser_layout as _compute_scene_browser_layout_impl,
    compute_scene_browser_hit_index as _compute_scene_browser_hit_index_impl,
    build_scene_switcher_lines as _build_scene_switcher_lines_impl,
    build_scene_browser_lines as _build_scene_browser_lines_impl,
    open_scene_by_id as _open_scene_by_id_impl,
)
from .editor.entity_panels import (
    filter_entity_panels_items as _filter_entity_panels_items_impl,
    clamp_entity_panels_index as _clamp_entity_panels_index_impl,
    resolve_entity_panels_id as _resolve_entity_panels_id_impl,
    build_outliner_lines as _build_outliner_lines_impl,
    build_inspector_lines as _build_inspector_lines_impl,
    format_entity_field_value as _format_entity_field_value_impl,
    get_entity_numeric_value as _get_entity_numeric_value_impl,
)
from .editor.asset_browser_panel import (
    filter_assets_for_browser as _filter_assets_for_browser_impl,
    clamp_asset_selection_index as _clamp_asset_selection_index_impl,
    cycle_asset_browser_kind as _cycle_asset_browser_kind_impl,
    move_asset_selection as _move_asset_selection_impl,
    resolve_asset_activation as _resolve_asset_activation_impl,
)

ZONE_BEHAVIOUR_CANONICAL = TRIGGER_ZONE_CANONICAL | HITBOX_CANONICAL
ZONE_BEHAVIOUR_CLASSNAMES = TRIGGER_ZONE_CLASSNAMES | HITBOX_CLASSNAMES

PALETTE_THUMB_SIZE = DEFAULT_THUMB_SIZE
PALETTE_THUMB_DRAW_SIZE = 18
PALETTE_LINE_HEIGHT = 20

PREFAB_PALETTE: list[dict[str, Any]] | None = None

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


# Backwards-compatible delegations to extracted palette helpers
def _parse_palette_filter(raw: str) -> tuple[list[str], list[str]]:
    """Parse palette filter string into (free_text_terms, tag_terms)."""
    return _parse_palette_filter_impl(raw)


def _filter_prefab_palette_items(items: list[dict[str, Any]], raw_filter: str) -> list[dict[str, Any]]:
    """Filter prefabs by free-text and/or tags."""
    return _filter_prefab_palette_items_impl(items, raw_filter)


def _palette_tag_frequencies(prefabs: list[dict[str, Any]]) -> list[str]:
    """Return tags sorted by descending count, then alphabetical (stable)."""
    return _palette_tag_frequencies_impl(prefabs)


def _normalize_entity_panel_tags(value: Any) -> list[str]:
    return _normalize_entity_panel_tags_impl(value)


def _apply_entity_panel_tag_delta(
    tags: list[str],
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[str]:
    return _apply_entity_panel_tag_delta_impl(tags, add=add, remove=remove)


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

        # Multi-selection state
        self._selected_entity_ids: List[str] = []
        self._primary_entity_id: Optional[str] = None
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

        # Panel search state (Outliner/Assets/History)
        self._outliner_search: str = ""
        self._assets_search: str = ""
        self._history_search: str = ""
        self._search_focus: str | None = None

        # Scene switcher state
        self.scene_switcher_active: bool = False
        self.scene_switcher_query: str = ""
        self.scene_switcher_index: int = 0
        self.scene_switcher_recent: list[str] = []
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

        # Undo history state
        self._history_cursor_index: int = 0

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

        # Command palette state (editor-only)
        self.command_palette_active: bool = False
        self.command_palette_query: str = ""
        self.command_palette_index: int = 0

        # Menu bar state
        self._menu_active: Optional[str] = None
        self._menu_hover_item_id: Optional[str] = None

        # Context menu state (right-click menu)
        self._context_menu_open: bool = False
        self._context_menu_x: float = 0.0
        self._context_menu_y: float = 0.0
        self._context_menu_hover_id: Optional[str] = None

        # Hover highlight state (for EditorHoverHighlightOverlay)
        self._hover_menu_title: Optional[str] = None
        self._hover_menu_title_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_menu_item_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_top_bar_control_id: Optional[str] = None
        self._hover_dock_tab: Optional[Tuple[str, str]] = None  # ("left"/"right", tab_name)
        self._hover_dock_tab_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_splitter: Optional[str] = None  # "left" or "right"
        self._hover_splitter_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_context_item_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_inspector_field_key: Optional[str] = None
        self._hover_inspector_field_rect: Optional[Tuple[float, float, float, float]] = None
        self._hover_entity_id: Optional[str] = None
        self._hover_entity_rect: Optional[Tuple[float, float, float, float]] = None

        # Dock tab state (which panel is active in each dock)
        self._left_dock_tab: str = "Outliner"  # "Scene" or "Outliner"
        self._right_dock_tab: str = "Inspector"  # "Inspector" or "Assets"

        # Dock resize state
        from .editor.editor_shell_layout import DOCK_WIDTH  # noqa: PLC0415
        self._dock_left_w: int = DOCK_WIDTH
        self._dock_right_w: int = DOCK_WIDTH
        self._dock_drag_active: Optional[str] = None  # "left" or "right" or None
        self._dock_drag_start_x: float = 0.0
        self._dock_drag_start_w: int = 0

        # Dock collapse / viewport maximize state
        self._dock_left_collapsed: bool = False
        self._dock_right_collapsed: bool = False
        self._viewport_maximized: bool = False
        # Stores previous collapse states for when maximize is toggled off
        self._dock_prev_left_collapsed: bool = False
        self._dock_prev_right_collapsed: bool = False

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

        # Clipboard state (internal, not OS clipboard)
        self._entity_clipboard: Optional[Dict[str, Any]] = None
        self._entity_clipboard_source_id: Optional[str] = None

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

        # Marquee box selection state
        self._marquee_active: bool = False
        self._marquee_start_world: Tuple[float, float] | None = None
        self._marquee_end_world: Tuple[float, float] | None = None
        self._marquee_shift: bool = False

        # Alt-drag duplicate state
        self._alt_dup_active: bool = False
        self._alt_dup_specs: Tuple[Any, ...] | None = None
        self._alt_dup_pivot_new_id: str | None = None
        self._alt_dup_drag_start_world: Tuple[float, float] | None = None
        self._alt_dup_last_world: Tuple[float, float] | None = None
        self._alt_dup_original_selection: List[str] | None = None
        self._alt_dup_original_primary: str | None = None

        # Cursor hint state (for affordance feedback)
        self._last_mouse_x: float = 0.0
        self._last_mouse_y: float = 0.0

        # Undo/Redo state
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.scene_dirty: bool = False
        self.dirty_state = EditorDirtyState()
        self.play_session = EditorPlaySession()

        # Unsaved changes confirmation
        self.confirm_open: bool = False
        self.confirm_reason: str = ""
        self.confirm_selection_index: int = 0
        self.pending_action: Callable[[], None] | None = None
        self._confirm_bypass: bool = False

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

        self.load_workspace()

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

    def _get_repo_root(self) -> Any:
        """Get repo root, allowing override for testing."""
        if self._repo_root_override is not None:
            return self._repo_root_override
        return get_repo_root()

    def load_workspace(self) -> None:
        if os.environ.get("PYGBAG") == "1":
            return
        if os.environ.get("PYTEST_CURRENT_TEST") and self._repo_root_override is None:
            return

        settings = load_workspace(self._get_repo_root())
        self.entity_panels_active = settings.entity_panels_open
        self.command_palette_active = settings.command_palette_open
        self.scene_switcher_active = settings.scene_switcher_open
        self.scene_browser_active = settings.scene_browser_open
        self.asset_browser_active = settings.asset_browser_open
        self._outliner_search = settings.outliner_search
        self.entity_panels_filter = self._outliner_search
        self._assets_search = settings.assets_search
        self.asset_browser_filter = self._assets_search
        self.asset_browser_kind = settings.asset_browser_kind
        self._history_search = settings.history_search
        self.entity_panels_focus = settings.outliner_focus

        # Load dock tab state
        self._left_dock_tab = settings.left_dock_tab
        self._right_dock_tab = settings.right_dock_tab

        # Load dock resize widths
        self._dock_left_w = settings.dock_left_w
        self._dock_right_w = settings.dock_right_w

        # Load dock collapse / maximize state
        self._dock_left_collapsed = settings.dock_left_collapsed
        self._dock_right_collapsed = settings.dock_right_collapsed
        self._viewport_maximized = settings.viewport_maximized

        # Load ghost originals settings
        self._ghost_originals_enabled = settings.ghost_originals_enabled
        self._ghost_originals_alpha = settings.ghost_originals_alpha
        self._ghost_originals_dim_scale = settings.ghost_originals_dim_scale

        if self.asset_browser_active:
            self.refresh_asset_browser()
            
        if settings.light_occluder_tool == "light":
            self.lights_tool_active = True
            self.occluder_tool_active = False
        elif settings.light_occluder_tool == "occluder":
            self.lights_tool_active = False
            self.occluder_tool_active = True
        else:
            self.lights_tool_active = False
            self.occluder_tool_active = False

        if settings.last_scene_id:
            current_key = getattr(self.window, "current_scene_key", None)
            if current_key != settings.last_scene_id:
                load_fn = getattr(self.window, "load_scene", None)
                if callable(load_fn):
                    try:
                        load_fn(settings.last_scene_id)
                        if settings.last_camera_center and hasattr(self.window, "camera"):
                            self.window.camera.position = (
                                settings.last_camera_center[0], settings.last_camera_center[1]
                            )
                    except Exception as e:
                        logger.warning("Failed to restore workspace scene %s: %s", settings.last_scene_id, e)
        elif settings.last_camera_center and hasattr(self.window, "camera"):
            self.window.camera.position = (settings.last_camera_center[0], settings.last_camera_center[1])

    def save_workspace(self) -> None:
        if os.environ.get("PYGBAG") == "1":
            return

        tool = None
        if self.lights_tool_active:
            tool = "light"
        elif self.occluder_tool_active:
            tool = "occluder"

        scene_id = getattr(self.window, "current_scene_key", None)
        cam_center = None
        cam = getattr(self.window, "camera", None)
        if cam:
            cam_center = list(cam.position)

        settings = WorkspaceSettings(
            entity_panels_open=self.entity_panels_active,
            command_palette_open=self.command_palette_active,
            scene_switcher_open=self.scene_switcher_active,
            scene_browser_open=self.scene_browser_active,
            asset_browser_open=self.asset_browser_active,
            asset_browser_filter=self.asset_browser_filter,
            asset_browser_kind=self.asset_browser_kind,
            outliner_search=self._outliner_search,
            assets_search=self._assets_search,
            history_search=self._history_search,
            light_occluder_tool=tool,
            outliner_focus=self.entity_panels_focus,
            last_scene_id=scene_id,
            last_camera_center=cam_center,
            left_dock_tab=self._left_dock_tab,
            right_dock_tab=self._right_dock_tab,
            dock_left_w=self._dock_left_w,
            dock_right_w=self._dock_right_w,
            dock_left_collapsed=self._dock_left_collapsed,
            dock_right_collapsed=self._dock_right_collapsed,
            viewport_maximized=self._viewport_maximized,
            ghost_originals_enabled=self._ghost_originals_enabled,
            ghost_originals_alpha=self._ghost_originals_alpha,
            ghost_originals_dim_scale=self._ghost_originals_dim_scale,
        )

        save_workspace(self._get_repo_root(), settings)

    def _autosave_workspace(self) -> None:
        self.save_workspace()

    # -------------------------------------------------------------------------
    # Panel Search (Outliner / Assets / History)
    # -------------------------------------------------------------------------

    def is_search_focused(self) -> bool:
        return self._search_focus in ("outliner", "assets", "history")

    def focus_search_for_active_panel(self) -> bool:
        if not self.active:
            return False
        panel = self._resolve_active_search_panel()
        if panel is None:
            return False
        self._search_focus = panel
        self.entity_panels_filter_active = panel == "outliner"
        return True

    def clear_search_focus(self) -> None:
        self._search_focus = None
        self.entity_panels_filter_active = False

    def get_active_panel_search_text(self) -> str:
        panel = self._resolve_active_search_panel()
        if panel is None:
            return ""
        return self._get_search_text_for_panel(panel)

    def set_active_panel_search_text(self, new_text: str) -> bool:
        panel = self._resolve_active_search_panel()
        if panel is None:
            return False
        self._set_search_text_for_panel(panel, new_text)
        return True

    def clear_search_for_active_panel(self) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        current = self._get_search_text_for_panel(panel)
        if not current:
            return False
        self._set_search_text_for_panel(panel, "")
        return True

    def append_search_text(self, text: str) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        if not text or not text.isprintable():
            return False
        current = self._get_search_text_for_panel(panel)
        self._set_search_text_for_panel(panel, current + text)
        return True

    def backspace_search_text(self) -> bool:
        panel = self._search_focus
        if panel is None:
            return False
        current = self._get_search_text_for_panel(panel)
        if not current:
            return False
        self._set_search_text_for_panel(panel, current[:-1])
        return True

    def _resolve_active_search_panel(self) -> str | None:
        if self._left_dock_tab == "Outliner" and self.entity_panels_active:
            return "outliner"
        if self._right_dock_tab == "Assets" and self.asset_browser_active:
            return "assets"
        if self._right_dock_tab == "History":
            return "history"
        return None

    def _get_search_text_for_panel(self, panel: str) -> str:
        if panel == "outliner":
            return self._outliner_search
        if panel == "assets":
            return self._assets_search
        if panel == "history":
            return self._history_search
        return ""

    def _set_search_text_for_panel(self, panel: str, new_text: str) -> None:
        value = str(new_text or "")
        if panel == "outliner":
            if value == self._outliner_search:
                return
            self._outliner_search = value
            self.entity_panels_filter = value
            self._refresh_entity_panels_list()
            self._autosave_workspace()
            return
        if panel == "assets":
            self.set_asset_browser_filter(value)
            return
        if panel == "history":
            if value == self._history_search:
                return
            self._history_search = value
            self._autosave_workspace()
            return

    def _sync_search_focus(self) -> None:
        if self._search_focus is None:
            return
        if self._resolve_active_search_panel() != self._search_focus:
            self.clear_search_focus()

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
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        return ensure_scene_lights(scene)

    def _get_scene_occluders(self) -> List[Dict[str, Any]]:
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        return ensure_scene_occluders(scene)

    def _sync_lighting_runtime(self) -> None:
        lighting = getattr(self.window, "lighting", None)
        if lighting is not None:
            lights = copy.deepcopy(self._get_scene_lights())
            try:
                lighting.configure_scene_lights(lights)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_lighting_sync_error_logged", False):
                    logger.error("[Mesh][Editor] ERROR syncing lighting runtime: %s", exc)
                    setattr(self, "_mesh_lighting_sync_error_logged", True)

    def _sync_lighting_settings(self) -> None:
        lighting = getattr(self.window, "lighting", None)
        if lighting is None:
            return
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return
        settings = scene.get("settings")
        if not isinstance(settings, dict):
            return
        ambient_tint = settings.get("ambient_light_rgba")
        if ambient_tint is not None:
            try:
                lighting.set_ambient_tint(ambient_tint)
            except Exception:  # noqa: BLE001
                pass
        if "ambient_darkness_alpha" in settings:
            try:
                lighting.set_ambient_darkness_alpha(int(settings.get("ambient_darkness_alpha")))
            except Exception:  # noqa: BLE001
                pass

    def apply_lighting_preset(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        if preset_id not in LIGHTING_PRESETS:
            scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
            if not isinstance(scene, dict):
                return False
            settings = scene.get("settings")
            if not isinstance(settings, dict):
                return False
            custom = settings.get("custom_lighting_presets")
            if not isinstance(custom, dict) or preset_id not in custom:
                return False
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        apply_lighting_preset_ops(scene, preset_id)
        settings = scene.get("settings")
        if isinstance(settings, dict) and hasattr(self.window, "scene_controller"):
            self.window.scene_controller.scene_settings = settings
        self._sync_lighting_settings()
        self.lighting_preset_label = tr("UI_APPLIED_PRESET", slot=preset_id)
        self.lighting_preset_until = time.time() + 1.5
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue) and self.lighting_preset_label:
            enqueue(self.lighting_preset_label, seconds=2.5)
        self._mark_dirty()
        return True

    def apply_lighting_preset_hotkey(self, index: int) -> bool:
        if not (0 <= index < len(LIGHTING_PRESET_ORDER)):
            return False
        return self.apply_lighting_preset(LIGHTING_PRESET_ORDER[index])

    def apply_custom_lighting_preset(self, slot: str) -> bool:
        return self.apply_lighting_preset(slot)

    def capture_lighting_preset(self, slot: str) -> bool:
        slot = str(slot or "")
        if slot not in ("custom_1", "custom_2"):
            return False
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        capture_lighting_preset(scene, slot)
        settings = scene.get("settings")
        if isinstance(settings, dict) and hasattr(self.window, "scene_controller"):
            self.window.scene_controller.scene_settings = settings
        self.lighting_preset_label = tr("UI_SAVED_PRESET", slot=slot)
        self.lighting_preset_until = time.time() + 1.5
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue) and self.lighting_preset_label:
            enqueue(self.lighting_preset_label, seconds=2.5)
        self._mark_dirty()
        return True

    def get_active_lighting_preset_label(self) -> str | None:
        label = self.lighting_preset_label
        if not label:
            return None
        if time.time() > self.lighting_preset_until:
            return None
        return label

    def _sync_occluders_runtime(self) -> None:
        lighting = getattr(self.window, "lighting", None)
        if lighting is None:
            return
        occluders = copy.deepcopy(self._get_scene_occluders())
        try:
            from engine.lighting.occluders import build_entity_occluders_from_scene_payload  # noqa: PLC0415
            scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
            entity_occluders = build_entity_occluders_from_scene_payload(scene) if isinstance(scene, dict) else []
        except Exception:  # noqa: BLE001
            entity_occluders = []
        if entity_occluders:
            occluders.extend(entity_occluders)
        try:
            lighting.configure_scene_occluders(occluders)
        except Exception as exc:  # noqa: BLE001
            if not getattr(self, "_mesh_occluder_sync_error_logged", False):
                logger.error("[Mesh][Editor] ERROR syncing occluders runtime: %s", exc)
                setattr(self, "_mesh_occluder_sync_error_logged", True)

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
        self.inspector_active = False
        self.palette_active = False
        self.palette_filter_active = False

    def _disable_editor_mode(self) -> None:
        self.active = False
        logger.info("[Editor] Mode DISABLED")
        self.selected_entity = None
        self._reset_zone_selection_state()
        self.window.paused = False
        self.inspector_active = False
        self.palette_active = False
        self.palette_filter_active = False
        self.command_palette_active = False
        self.command_palette_query = ""
        self.command_palette_index = 0
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
        self._cancel_shape_edit()

    def play_from_here(self) -> bool:
        if not self.active or self.play_session.is_playing:
            return False

        def _apply() -> None:
            self._start_play_session()

        if self.confirm_unsaved_changes("Play From Here", _apply):
            return False
        _apply()
        return True

    def stop_playing(self) -> bool:
        if not self.play_session.is_playing:
            return False
        self._stop_play_session()
        return True

    def _start_play_session(self) -> None:
        session = self.play_session
        session.is_playing = True
        scene_controller = getattr(self.window, "scene_controller", None)
        session.return_scene_id = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        session.return_camera_pos = self._get_camera_center()
        session.return_selection = self.selected_entity
        session.spawn_mode = "camera_center"
        self.active = False
        try:
            self.window.paused = False
        except Exception:  # noqa: BLE001
            pass
        self._spawn_player_for_play()

    def _stop_play_session(self) -> None:
        session = self.play_session
        session.is_playing = False
        self.active = True
        try:
            self.window.paused = True
        except Exception:  # noqa: BLE001
            pass

        scene_controller = getattr(self.window, "scene_controller", None)
        current_scene = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        return_scene = session.return_scene_id
        if return_scene and current_scene and return_scene != current_scene:
            requester = getattr(self.window, "request_scene_change", None)
            if callable(requester):
                requester(return_scene)
            else:
                changer = getattr(scene_controller, "request_scene_change", None) if scene_controller is not None else None
                if callable(changer):
                    changer(return_scene)

        if return_scene and current_scene and return_scene == current_scene:
            selection = session.return_selection
            sprites = getattr(scene_controller, "all_sprites", None) if scene_controller is not None else None
            if selection is not None and isinstance(sprites, list) and selection in sprites:
                self.selected_entity = selection

        self._restore_camera_position(session.return_camera_pos)

    def _get_camera_center(self) -> tuple[float, float]:
        getter = getattr(self.window, "get_camera_center", None)
        if callable(getter):
            try:
                pos = getter()
                if isinstance(pos, (tuple, list)) and len(pos) == 2:
                    return (float(pos[0]), float(pos[1]))
            except Exception:  # noqa: BLE001
                pass
        camera = getattr(self.window, "camera", None)
        if camera is None:
            controller = getattr(self.window, "camera_controller", None)
            camera = getattr(controller, "camera", None) if controller is not None else None
        position = getattr(camera, "position", None) if camera is not None else None
        if isinstance(position, (tuple, list)) and len(position) == 2:
            return (float(position[0]), float(position[1]))
        return (0.0, 0.0)

    def _restore_camera_position(self, pos: tuple[float, float] | None) -> None:
        if pos is None:
            return
        camera = getattr(self.window, "camera", None)
        if camera is None:
            controller = getattr(self.window, "camera_controller", None)
            camera = getattr(controller, "camera", None) if controller is not None else None
        if camera is None:
            return
        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to(pos, 1.0)
            return
        try:
            setattr(camera, "position", pos)
        except Exception:  # noqa: BLE001
            pass

    def _spawn_player_for_play(self) -> None:
        if self.play_session.spawn_mode != "camera_center":
            return
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return
        finder = getattr(scene_controller, "_find_player_sprite", None)
        player = finder() if callable(finder) else None
        if player is None:
            return
        cam_x, cam_y = self._get_camera_center()
        mutator = getattr(scene_controller, "_apply_entity_mutation", None)
        if callable(mutator):
            mutator(player, x=cam_x, y=cam_y)
            return
        try:
            player.center_x = float(cam_x)
            player.center_y = float(cam_y)
        except Exception:  # noqa: BLE001
            return
        entity_data = getattr(player, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            entity_data["x"] = float(cam_x)
            entity_data["y"] = float(cam_y)

    def handle_mouse_click(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_click(self, x, y, button, modifiers)

    def handle_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input when editor is active. Returns True if consumed."""
        return editor_input.handle_input(self, key, modifiers)

    def _cycle_tool_mode(self) -> None:
        modes = [TOOL_MODE_MOVE, TOOL_MODE_PATH, TOOL_MODE_ZONE]
        try:
            idx = modes.index(self.tool_mode)
            self.tool_mode = modes[(idx + 1) % len(modes)]
        except ValueError:
            self.tool_mode = TOOL_MODE_MOVE
        logger.info("[Editor] Tool Mode: %s", self.tool_mode)
        self.selected_waypoint_index = -1

    def _handle_palette_input(self, key: int, modifiers: int) -> bool:
        if self.palette_filter_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.ESCAPE):
                self.palette_filter_active = False
                return True
            if key == optional_arcade.arcade.key.TAB:
                applied = self._apply_palette_tag_autocomplete()
                if applied:
                    self._refresh_palette_list()
                    self._prewarm_visible_palette_thumbs()
                    return True
                return False
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.palette_filter = self.palette_filter[:-1]
                self._refresh_palette_list()
                self._prewarm_visible_palette_thumbs()
                return True
            return False

        if key == optional_arcade.arcade.key.SLASH or (key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL)):
            self.palette_filter_active = True
            return True

        if key == optional_arcade.arcade.key.UP:
            self.move_palette_selection(-1)
            return True
        elif key == optional_arcade.arcade.key.DOWN:
            self.move_palette_selection(1)
            return True

        # Number keys
        if optional_arcade.arcade.key.KEY_1 <= key <= optional_arcade.arcade.key.KEY_9:
            self.select_palette_index(key - optional_arcade.arcade.key.KEY_1)
            return True

        return False

    def _prefab_sprite_path(self, prefab: Dict[str, Any]) -> str | None:
        entity = prefab.get("entity")
        if not isinstance(entity, dict):
            return None
        sprite_path = entity.get("sprite")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            sprite_sheet = entity.get("sprite_sheet")
            if isinstance(sprite_sheet, dict):
                sprite_path = sprite_sheet.get("image")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            return None
        return str(sprite_path)

    def _palette_visible_index_range(self, item_count: int) -> tuple[int, int]:
        """Return (start_inclusive, end_exclusive) for visible palette item rows."""
        count = max(0, int(item_count))
        if count == 0:
            return (0, 0)

        # Matches the palette overlay layout:
        # p_start_y = window.height - 100, fixed PALETTE_LINE_HEIGHT, and header lines.
        header_lines = self._palette_header_line_count()
        p_start_y = float(getattr(self.window, "height", 0) or 0) - 100.0
        available_lines = int(max(0.0, p_start_y) // float(PALETTE_LINE_HEIGHT))
        visible_rows = max(0, available_lines - header_lines)
        end = min(count, visible_rows)
        return (0, max(0, end))

    def _palette_header_line_count(self) -> int:
        # Title + rule + filter line + rule
        base = 4
        if self.palette_filter_active and self._palette_tag_suggestions():
            return base + 1
        return base

    def _palette_tag_suggestions(self) -> List[str]:
        """Return up to 5 tag suggestions while the filter input is active."""
        if not self.palette_filter_active:
            return []
        raw = str(self.palette_filter or "")
        # If the user just typed a space, they're not currently typing a token.
        if raw and raw[-1].isspace():
            return []
        tokens = raw.split()
        if not tokens:
            return []
        last = tokens[-1].strip()
        if not last:
            return []
        lower = last.lower()
        partial: str | None = None
        if lower.startswith("#"):
            partial = lower[1:]
        elif lower.startswith("t:"):
            partial = lower[2:]
        if partial is None:
            return []
        partial = partial.strip()

        ranked = list(self._palette_tag_ranked or [])
        if not ranked:
            self._palette_tag_ranked = _palette_tag_frequencies(list(self.prefab_palette))
            ranked = list(self._palette_tag_ranked or [])
            if not ranked:
                return []

        if partial:
            filtered = [t for t in ranked if t.startswith(partial)]
            if not filtered:
                # If cached ranking is stale (e.g. palette changed), refresh once.
                self._palette_tag_ranked = _palette_tag_frequencies(list(self.prefab_palette))
                ranked = list(self._palette_tag_ranked or [])
                filtered = [t for t in ranked if t.startswith(partial)]
            ranked = filtered

        return ranked[:5]

    def _apply_palette_tag_autocomplete(self) -> bool:
        """Replace the currently-typed tag token with the top suggestion."""
        suggestions = self._palette_tag_suggestions()
        if not suggestions:
            return False
        raw = str(self.palette_filter or "")
        tokens = raw.split()
        if not tokens:
            return False
        last = tokens[-1].strip()
        if not last:
            return False
        lower = last.lower()
        prefix = ""
        if lower.startswith("#"):
            prefix = "#"
        elif lower.startswith("t:"):
            prefix = "t:"
        else:
            return False
        tokens[-1] = f"{prefix}{suggestions[0]}"
        self.palette_filter = " ".join(tokens)
        return True

    def _palette_visible_items(self) -> List[Dict[str, Any]]:
        """Return the subset of palette items that are actually visible on-screen."""
        items = self._get_palette_items()
        start, end = self._palette_visible_index_range(len(items))
        return items[start:end] if end > start else []

    def _prewarm_visible_palette_thumbs(self) -> None:
        if not (self.active and self.palette_active):
            return
        for prefab in self._palette_visible_items():
            sprite_path = self._prefab_sprite_path(prefab)
            if sprite_path:
                request_thumb(sprite_path, thumb_size=PALETTE_THUMB_SIZE)

    def _build_palette_list(self) -> List[Dict[str, Any]]:
        return _filter_prefab_palette_items(list(self.prefab_palette), self.palette_filter)

    def _refresh_palette_list(self) -> None:
        self._cached_palette_list = self._build_palette_list()
        count = len(self._cached_palette_list)
        if count == 0:
            self.palette_index = 0
            return
        self.palette_index = max(0, min(self.palette_index, count - 1))

    def _get_palette_items(self) -> List[Dict[str, Any]]:
        return self._cached_palette_list

    def _get_palette_thumb_texture(self, prefab: Dict[str, Any]) -> Optional[optional_arcade.arcade.Texture]:
        entity = prefab.get("entity")
        if not isinstance(entity, dict):
            return None
        sprite_path = entity.get("sprite")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            sprite_sheet = entity.get("sprite_sheet")
            if isinstance(sprite_sheet, dict):
                sprite_path = sprite_sheet.get("image")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            return None
        thumb_path = request_thumb(sprite_path, thumb_size=PALETTE_THUMB_SIZE)
        if thumb_path is None:
            return None
        key = thumb_path.as_posix()
        texture = self._palette_thumb_textures.get(key)
        if texture is None:
            try:
                texture = optional_arcade.arcade.load_texture(str(thumb_path))
            except Exception:
                return None
            self._palette_thumb_textures[key] = texture
        return texture

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
        items = self._get_inspector_items()
        if not items:
            return False

        if key == optional_arcade.arcade.key.UP:
            self.inspector_selection_index = max(0, self.inspector_selection_index - 1)
            return True
        elif key == optional_arcade.arcade.key.DOWN:
            self.inspector_selection_index = min(len(items) - 1, self.inspector_selection_index + 1)
            return True

        # Editing
        selected_item = items[self.inspector_selection_index]
        if key == optional_arcade.arcade.key.R and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            if modifiers & optional_arcade.arcade.key.MOD_CTRL:
                return self._reset_all_prefab_overrides()
            return self._reset_selected_prefab_override(selected_item)
        if selected_item["type"] != "param":
            return False # Can't edit headers

        behaviour_name = selected_item["behaviour"]
        param_name = selected_item["name"]
        current_value = selected_item["value"]
        param_type = selected_item["kind"] # int, float, bool, string

        new_value = current_value
        changed = False

        if param_type == "bool":
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE, optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                new_value = not current_value
                changed = True
        elif param_type in ("int", "float"):
            delta = 0
            if key == optional_arcade.arcade.key.LEFT:
                delta = -1 if param_type == "int" else -0.1
            elif key == optional_arcade.arcade.key.RIGHT:
                delta = 1 if param_type == "int" else 0.1

            if delta != 0:
                # Shift for larger steps
                if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                    delta *= 10

                if param_type == "int":
                    new_value = int(current_value + delta)
                else:
                    new_value = round(current_value + delta, 2)
                changed = True

        if changed:
            self._update_param(behaviour_name, param_name, new_value)
            self._refresh_inspector_items() # Refresh to show new value
            return True

        return False

    # ------------------------------------------------------------------
    # Dialogue / Quest editing
    # ------------------------------------------------------------------
    def toggle_dialogue_panel(self) -> None:
        if not self._entity_has_dialogue(self.selected_entity):
            logger.info("[Editor] Dialogue panel unavailable: select an entity with Dialogue")
            return
        self.dialogue_panel_active = not self.dialogue_panel_active
        self.dialogue_editing = False
        self.dialogue_edit_buffer = ""
        if self.dialogue_panel_active:
            self.inspector_active = False
            self.palette_active = False
            self.palette_filter_active = False
            self.hierarchy_active = False
            self._refresh_dialogue_cache()
            logger.info("[Editor] Dialogue panel OPEN")
        else:
            self._close_dialogue_panel()

    def _close_dialogue_panel(self) -> None:
        self.dialogue_panel_active = False
        self.dialogue_editing = False
        self.dialogue_edit_buffer = ""
        self._cached_dialogue_nodes = []
        self._dialogue_warnings = []
        self.animation_active = False
        self.animation_editing = False
        self.animation_edit_buffer = ""
        self.tile_panel_active = False

    def _entity_has_dialogue(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return _entity_has_dialogue_impl(sprite)

    def _refresh_dialogue_cache(self) -> None:
        self._cached_dialogue_nodes = []
        self._dialogue_warnings = []
        self.dialogue_selected_node = 0
        self.dialogue_selected_choice = 0
        if not self.selected_entity:
            return
        dialogue_root = self._get_entity_dialogue_config(self.selected_entity)
        nodes = dialogue_root.get("nodes", {})
        if isinstance(nodes, dict):
            self._cached_dialogue_nodes = sorted(nodes.keys())
        start_node = dialogue_root.get("start")
        if start_node in self._cached_dialogue_nodes:
            self.dialogue_selected_node = self._cached_dialogue_nodes.index(start_node)
        self._dialogue_warnings = self._collect_dialogue_warnings(dialogue_root)

    def _get_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite) -> Dict[str, Any]:
        return _get_entity_dialogue_config_impl(self.window.scene_controller, sprite)

    def _set_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite, dialogue_root: Dict[str, Any]) -> None:
        entity_name = getattr(sprite, "mesh_name", "")
        self._update_param_internal("Dialogue", "dialogue", dialogue_root, entity_name)

    def _dialogue_nodes(self) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        if not self.selected_entity:
            return nodes
        dialogue_root = self._get_entity_dialogue_config(self.selected_entity)
        raw_nodes = dialogue_root.get("nodes", {})
        if isinstance(raw_nodes, dict):
            for node_id in self._cached_dialogue_nodes:
                node = raw_nodes.get(node_id, {})
                if isinstance(node, dict):
                    node_copy = dict(node)
                    node_copy["_id"] = node_id
                    nodes.append(node_copy)
        return nodes

    def _get_selected_node(self) -> Optional[Dict[str, Any]]:
        nodes = self._dialogue_nodes()
        if not nodes:
            return None
        self.dialogue_selected_node = max(0, min(self.dialogue_selected_node, len(nodes) - 1))
        return nodes[self.dialogue_selected_node]

    def _get_selected_choice(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        choices = node.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return None
        self.dialogue_selected_choice = max(0, min(self.dialogue_selected_choice, len(choices) - 1))
        choice = choices[self.dialogue_selected_choice]
        return choice if isinstance(choice, dict) else None

    def _handle_dialogue_input(self, key: int, modifiers: int) -> bool:
        if not self.dialogue_panel_active:
            return False

        if self.dialogue_editing:
            if key == optional_arcade.arcade.key.ENTER:
                self._commit_dialogue_edit()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.dialogue_editing = False
                self.dialogue_edit_buffer = ""
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.dialogue_edit_buffer = self.dialogue_edit_buffer[:-1]
                return True
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self._close_dialogue_panel()
            return True

        nodes = self._dialogue_nodes()
        if not nodes:
            return False
        node = self._get_selected_node()
        choice = node and self._get_selected_choice(node)

        if key == optional_arcade.arcade.key.UP:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT and choice:
                self.dialogue_selected_choice = max(0, self.dialogue_selected_choice - 1)
            else:
                self.dialogue_selected_node = max(0, self.dialogue_selected_node - 1)
                self.dialogue_selected_choice = 0
            return True
        if key == optional_arcade.arcade.key.DOWN:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT and choice:
                choices = node.get("choices") if node else []
                count = len(choices) if isinstance(choices, list) else 0
                if count:
                    self.dialogue_selected_choice = min(count - 1, self.dialogue_selected_choice + 1)
            else:
                self.dialogue_selected_node = min(len(nodes) - 1, self.dialogue_selected_node + 1)
                self.dialogue_selected_choice = 0
            return True
        if key == optional_arcade.arcade.key.RIGHT and choice:
            self.dialogue_field_focus = self._next_dialogue_field(self.dialogue_field_focus, has_choice=True)
            return True
        if key == optional_arcade.arcade.key.LEFT:
            self.dialogue_field_focus = self._prev_dialogue_field(self.dialogue_field_focus, has_choice=bool(choice))
            return True
        if key in (optional_arcade.arcade.key.TAB,):
            self.dialogue_field_focus = self._next_dialogue_field(self.dialogue_field_focus, has_choice=bool(choice))
            return True
        if key == optional_arcade.arcade.key.ENTER:
            self._begin_dialogue_edit()
            return True
        return False

    def _next_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        fields = ["node_text"]
        if has_choice:
            fields.extend(["choice_text", "choice_next", "choice_require", "choice_forbid"])
        if current not in fields:
            return fields[0]
        idx = (fields.index(current) + 1) % len(fields)
        return fields[idx]

    def _prev_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        fields = ["node_text"]
        if has_choice:
            fields.extend(["choice_text", "choice_next", "choice_require", "choice_forbid"])
        if current not in fields:
            return fields[-1]
        idx = (fields.index(current) - 1) % len(fields)
        return fields[idx]

    def _begin_dialogue_edit(self) -> None:
        node = self._get_selected_node()
        if not node:
            return
        choice = self._get_selected_choice(node)
        focus = self.dialogue_field_focus
        value = ""
        if focus == "node_text":
            value = str(node.get("text", ""))
        elif choice:
            if focus == "choice_text":
                value = str(choice.get("text", ""))
            elif focus == "choice_next":
                value = str(choice.get("next", "") or "")
            elif focus == "choice_require":
                value = ", ".join(choice.get("require_flags") or [])
            elif focus == "choice_forbid":
                value = ", ".join(choice.get("forbid_flags") or [])
        self.dialogue_edit_buffer = value
        self.dialogue_editing = True

    def _commit_dialogue_edit(self) -> None:
        node = self._get_selected_node()
        if not node or not self.selected_entity:
            self.dialogue_editing = False
            self.dialogue_edit_buffer = ""
            return
        choice = self._get_selected_choice(node)
        focus = self.dialogue_field_focus
        new_text = self.dialogue_edit_buffer
        success = self._apply_dialogue_edit(node, choice, focus, new_text)
        if success:
            self._refresh_dialogue_cache()
        self.dialogue_editing = False
        self.dialogue_edit_buffer = ""

    def _apply_dialogue_edit(
        self,
        node: Dict[str, Any],
        choice: Optional[Dict[str, Any]],
        focus: str,
        new_text: str,
    ) -> bool:
        if not self.selected_entity:
            return False
        before = self._get_entity_dialogue_config(self.selected_entity)
        dialogue_root = copy.deepcopy(before)
        nodes = dialogue_root.setdefault("nodes", {})
        node_id = node.get("_id")
        if not node_id:
            return False
        current_node = nodes.get(node_id, {})
        if not isinstance(current_node, dict):
            current_node = {}
        nodes[node_id] = current_node
        if focus == "node_text":
            current_node["text"] = new_text
        else:
            choices = current_node.setdefault("choices", [])
            if not isinstance(choices, list):
                choices = []
                current_node["choices"] = choices
            if choice is None:
                return False
            if 0 <= self.dialogue_selected_choice < len(choices):
                target = choices[self.dialogue_selected_choice]
                if not isinstance(target, dict):
                    target = {}
                    choices[self.dialogue_selected_choice] = target
            else:
                return False
            if focus == "choice_text":
                target["text"] = new_text
            elif focus == "choice_next":
                target["next"] = new_text or None
            elif focus == "choice_require":
                target["require_flags"] = parse_flag_list(new_text)
            elif focus == "choice_forbid":
                target["forbid_flags"] = parse_flag_list(new_text)
            else:
                return False
        self._set_entity_dialogue_config(self.selected_entity, dialogue_root)
        self._push_command({
            "type": "EditDialogue",
            "entity_name": getattr(self.selected_entity, "mesh_name", ""),
            "before": before,
            "after": dialogue_root,
        })
        return True

    def _collect_dialogue_warnings(self, dialogue_root: Dict[str, Any]) -> List[str]:
        return _collect_dialogue_warnings_impl(dialogue_root)

    # ------------------------------------------------------------------
    # Animation panel helpers
    # ------------------------------------------------------------------
    def toggle_animation_panel(self) -> None:
        if not self._entity_has_animator(self.selected_entity):
            logger.info("[Editor] Animation panel unavailable: select an entity with Animator")
            return
        self.animation_active = not self.animation_active
        self.animation_editing = False
        self.animation_edit_buffer = ""
        if self.animation_active:
            self.inspector_active = False
            self.palette_active = False
            self.hierarchy_active = False
            self.dialogue_panel_active = False
            self._refresh_animation_cache()
            logger.info("[Editor] Animation panel OPEN")
        else:
            self._close_animation_panel()

    def _close_animation_panel(self) -> None:
        self.animation_active = False
        self.animation_editing = False
        self.animation_edit_buffer = ""

    def _entity_has_animator(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return _entity_has_animator_impl(sprite)

    def _refresh_animation_cache(self) -> None:
        self.animation_selected_index = 0
        config = self._get_animator_config(self.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        if isinstance(animations, dict):
            self._cached_animation_names = sorted(animations.keys())
        else:
            self._cached_animation_names = []

    def _get_animator_config(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> Dict[str, Any]:
        return _get_animator_config_impl(self.window.scene_controller, sprite)

    def _set_animator_config(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        entity_name = getattr(sprite, "mesh_name", "")
        self._update_param_internal("Animator", "animations", animator_cfg.get("animations", {}), entity_name)
        if "animation_frame_rate" in animator_cfg:
            self._update_param_internal("Animator", "animation_frame_rate", animator_cfg.get("animation_frame_rate", 8.0), entity_name)
        if "animation_state" in animator_cfg:
            self._update_param_internal("Animator", "animation_state", animator_cfg.get("animation_state", ""), entity_name)
        animations = animator_cfg.get("animations", {})
        if isinstance(animations, dict):
            self._cached_animation_names = sorted(animations.keys())
        self._apply_animator_runtime(sprite, animator_cfg)

    def _apply_animator_runtime(self, sprite: optional_arcade.arcade.Sprite, animator_cfg: Dict[str, Any]) -> None:
        _apply_animator_runtime_impl(
            sprite,
            animator_cfg,
            self._cached_animation_names,
            self.animation_selected_index,
        )

    def _handle_animation_input(self, key: int, modifiers: int) -> bool:
        if not self.animation_active:
            return False

        if self.animation_editing:
            if key == optional_arcade.arcade.key.ENTER:
                self._commit_animation_edit()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.animation_editing = False
                self.animation_edit_buffer = ""
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.animation_edit_buffer = self.animation_edit_buffer[:-1]
                return True
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self._close_animation_panel()
            return True

        config = self._get_animator_config(self.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        names = sorted(animations.keys()) if isinstance(animations, dict) else []
        if not names:
            return False

        if key == optional_arcade.arcade.key.UP:
            self.animation_selected_index = max(0, self.animation_selected_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.animation_selected_index = min(len(names) - 1, self.animation_selected_index + 1)
            return True

        clip_name = names[self.animation_selected_index]
        clip_cfg = animations.get(clip_name, {})
        if not isinstance(clip_cfg, dict):
            clip_cfg = {}

        if key == optional_arcade.arcade.key.TAB:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                self.animation_field_focus = self._prev_animation_field(self.animation_field_focus)
            else:
                self.animation_field_focus = self._next_animation_field(self.animation_field_focus)
            return True

        if self.animation_field_focus == "mode":
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE, optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                new_mode = self._cycle_mode(clip_cfg.get("mode", "loop"), key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE))
                self._apply_animation_change(names, animations, clip_name, "mode", new_mode)
                return True
        elif self.animation_field_focus == "fps":
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
                self._apply_animation_change(names, animations, clip_name, "fps", new_fps)
                return True
        elif self.animation_field_focus == "frames":
            if key == optional_arcade.arcade.key.ENTER:
                frames = clip_cfg.get("frames")
                if isinstance(frames, list):
                    rendered = ", ".join(str(f) for f in frames)
                else:
                    rendered = ""
                self.animation_edit_buffer = rendered
                self.animation_editing = True
                return True
        return False

    def _next_animation_field(self, current: str) -> str:
        fields = ["mode", "fps", "frames"]
        if current not in fields:
            return fields[0]
        idx = (fields.index(current) + 1) % len(fields)
        return fields[idx]

    def _prev_animation_field(self, current: str) -> str:
        fields = ["mode", "fps", "frames"]
        if current not in fields:
            return fields[-1]
        idx = (fields.index(current) - 1) % len(fields)
        return fields[idx]

    def _cycle_mode(self, current: str, forward: bool) -> str:
        modes = ["loop", "once", "ping-pong"]
        if current not in modes:
            current = "loop"
        idx = modes.index(current)
        idx = (idx + (1 if forward else -1)) % len(modes)
        return modes[idx]

    def _commit_animation_edit(self) -> None:
        if not self.selected_entity:
            self.animation_editing = False
            self.animation_edit_buffer = ""
            return
        config = self._get_animator_config(self.selected_entity)
        animations = config.get("animations", {})
        if not isinstance(animations, dict):
            self.animation_editing = False
            self.animation_edit_buffer = ""
            return
        names = sorted(animations.keys())
        if not names:
            self.animation_editing = False
            self.animation_edit_buffer = ""
            return
        clip_name = names[self.animation_selected_index]
        clip_cfg = dict(animations.get(clip_name, {}))
        frames = [entry.strip() for entry in self.animation_edit_buffer.split(",") if entry.strip()]
        clip_cfg["frames"] = frames
        animations[clip_name] = clip_cfg
        before = self._get_animator_config(self.selected_entity)
        config["animations"] = animations
        self._set_animator_config(self.selected_entity, config)
        self._push_command({
            "type": "EditAnimation",
            "entity_name": getattr(self.selected_entity, "mesh_name", ""),
            "before": before,
            "after": copy.deepcopy(config),
        })
        self.animation_editing = False
        self.animation_edit_buffer = ""
        self._refresh_animation_cache()

    def _apply_animation_change(
        self,
        names: List[str],
        animations: Dict[str, Any],
        clip_name: str,
        field: str,
        new_value: Any,
    ) -> None:
        if not self.selected_entity:
            return
        before = self._get_animator_config(self.selected_entity)
        clip_cfg = dict(animations.get(clip_name, {}))
        clip_cfg[field] = new_value
        animations[clip_name] = clip_cfg
        config = self._get_animator_config(self.selected_entity)
        config["animations"] = animations
        self._set_animator_config(self.selected_entity, config)
        self._push_command({
            "type": "EditAnimation",
            "entity_name": getattr(self.selected_entity, "mesh_name", ""),
            "before": before,
            "after": copy.deepcopy(config),
        })
        self._refresh_animation_cache()

    # ------------------------------------------------------------------
    # Tile painting helpers
    # ------------------------------------------------------------------
    def _tilemap_available(self) -> bool:
        return getattr(self.window.scene_controller, "tilemap_instance", None) is not None

    def toggle_tile_panel(self) -> None:
        if not self._tilemap_available():
            logger.info("[Editor] Tile panel unavailable: no tilemap loaded")
            return
        self.tile_panel_active = not self.tile_panel_active
        if self.tile_panel_active:
            self.inspector_active = False
            self.palette_active = False
            self.palette_filter_active = False
            self.hierarchy_active = False
            self.dialogue_panel_active = False
            self.animation_active = False
            self._refresh_tile_palette()
            logger.info("[Editor] Tile panel OPEN")
        else:
            self._close_tile_panel()

    def _close_tile_panel(self) -> None:
        self.tile_panel_active = False

    def _refresh_tile_palette(self) -> None:
        instance = getattr(self.window.scene_controller, "tilemap_instance", None)
        if instance is None:
            self.tile_palette = []
            self.tile_layers = []
            return
        self.tile_layers = list(instance.layer_data.keys())
        if self.tile_layer_index >= len(self.tile_layers):
            self.tile_layer_index = 0
        gids: List[int] = []
        for tileset in getattr(instance, "tilesets", []):
            for i in range(min(8, tileset.tile_count)):
                gids.append(tileset.first_gid + i)
            if gids:
                break
        if not gids:
            gids = [1]
        self.tile_palette = gids
        self.tile_palette_index = min(self.tile_palette_index, max(0, len(self.tile_palette) - 1))

    def _current_tile_gid(self) -> int:
        if not self.tile_palette:
            return 0
        if self.tile_palette_index < 0 or self.tile_palette_index >= len(self.tile_palette):
            self.tile_palette_index = 0
        return int(self.tile_palette[self.tile_palette_index])

    def _paint_tile_at(self, world_x: float, world_y: float, gid: int) -> None:
        instance = getattr(self.window.scene_controller, "tilemap_instance", None)
        if instance is None:
            return
        tile_w, tile_h = instance.tile_size
        width, height = instance.layer_dimensions or (0, 0)
        if tile_w <= 0 or tile_h <= 0 or width <= 0 or height <= 0:
            return
        col = int(world_x // tile_w)
        map_pixel_height = height * tile_h
        row = int((map_pixel_height - world_y) // tile_h)
        if not (0 <= col < width and 0 <= row < height):
            return
        layer_name = self._current_tile_layer()
        result = self.window.scene_controller.set_tile(layer_name, col, row, gid)
        if result is None:
            return
        before, after = result
        if before == after:
            return
        self._push_command({
            "type": "PaintTile",
            "layer": layer_name,
            "col": col,
            "row": row,
            "before": before,
            "after": after,
        })

    def _current_tile_layer(self) -> str:
        if not self.tile_layers:
            self._refresh_tile_palette()
        if not self.tile_layers:
            return "background"
        self.tile_layer_index = max(0, min(self.tile_layer_index, len(self.tile_layers) - 1))
        return self.tile_layers[self.tile_layer_index]

    def _handle_tile_input(self, key: int, modifiers: int) -> bool:
        if not self.tile_panel_active:
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            self._close_tile_panel()
            return True
        if key == optional_arcade.arcade.key.UP:
            self.tile_palette_index = max(0, self.tile_palette_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.tile_palette_index = min(len(self.tile_palette) - 1, self.tile_palette_index + 1)
            return True
        if key == optional_arcade.arcade.key.LEFT_BRACKET:
            if self.tile_layers:
                self.tile_layer_index = (self.tile_layer_index - 1) % len(self.tile_layers)
            return True
        if key == optional_arcade.arcade.key.RIGHT_BRACKET:
            if self.tile_layers:
                self.tile_layer_index = (self.tile_layer_index + 1) % len(self.tile_layers)
            return True
        return False

    # ------------------------------------------------------------------
    # Lights tool
    # ------------------------------------------------------------------
    def _handle_lights_mouse_press(self, world_x: float, world_y: float) -> None:
        ref = self._hit_test_light(world_x, world_y)
        if ref is not None:
            self.lights_selection = ref
            self.lights_dragging = True
            self.lights_drag_start = (world_x, world_y)
            lights = self._get_scene_lights()
            light = lights[ref] if 0 <= ref < len(lights) else {}
            self.lights_original_pos = (
                float(light.get("x", world_x)),
                float(light.get("y", world_y)),
            )
        else:
            self._add_light(world_x, world_y)

    def _handle_lights_key_input(self, key: int, modifiers: int) -> bool:
        if self.lights_selection is None:
            return False
        lights = self._get_scene_lights()
        if not (0 <= self.lights_selection < len(lights)):
            return False
        light = lights[self.lights_selection]
        if key in (optional_arcade.arcade.key.DELETE, optional_arcade.arcade.key.BACKSPACE):
            self._delete_selected_light()
            return True
        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.DOWN):
            delta = -1 if key == optional_arcade.arcade.key.UP else 1
            count = len(self._light_property_defs)
            if count:
                self.light_property_index = (self.light_property_index + delta) % count
            return True
        if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
            prop = self._light_property_defs[self.light_property_index]
            step = float(prop.get("step", 1.0))
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                step *= 5.0
            delta = step if key == optional_arcade.arcade.key.RIGHT else -step
            key_name = str(prop.get("key") or prop.get("name"))
            default = float(prop.get("default", 0.0))
            current = light.get(key_name, default)
            try:
                current_val = float(current)
            except Exception:  # noqa: BLE001
                current_val = default
            new_value = current_val + delta
            if "min" in prop:
                new_value = max(float(prop["min"]), new_value)
            if "max" in prop:
                new_value = min(float(prop["max"]), new_value)
            if "wrap" in prop:
                new_value = new_value % float(prop["wrap"])
            if new_value != current_val:
                before = current_val
                scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if hasattr(self.window, "scene_controller"):
                        self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
                update_light_property(scene, self.lights_selection, prop.get("name", key_name), new_value)
                self._push_command({
                    "type": "EditLight",
                    "index": self.lights_selection,
                    "field": key_name,
                    "before": before,
                    "after": new_value,
                })
                self._sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.R:
            prop = self._light_property_defs[self.light_property_index]
            key_name = str(prop.get("key") or prop.get("name"))
            default = float(prop.get("default", 0.0))
            before = float(light.get(key_name, default))
            scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
            if not isinstance(scene, dict):
                scene = {}
                if hasattr(self.window, "scene_controller"):
                    self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
            update_light_property(scene, self.lights_selection, prop.get("name", key_name), default)
            if before != default:
                self._push_command({
                    "type": "EditLight",
                    "index": self.lights_selection,
                    "field": key_name,
                    "before": before,
                    "after": default,
                })
                self._sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.M:
            old_mode = str(light.get("mode", "soft"))
            new_mode = "hard" if old_mode == "soft" else "soft"
            light["mode"] = new_mode
            self._push_command({
                "type": "EditLight",
                "index": self.lights_selection,
                "field": "mode",
                "before": old_mode,
                "after": new_mode,
            })
            self._sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.C:
            old_color, new_color = cycle_light_color(light, self._light_color_palette)
            self._push_command({
                "type": "EditLight",
                "index": self.lights_selection,
                "field": "color",
                "before": old_color,
                "after": new_color,
            })
            self._sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.F:
            old_value, new_value = toggle_light_flicker(light)
            self._push_command({
                "type": "EditLight",
                "index": self.lights_selection,
                "field": "flicker_enabled",
                "before": old_value,
                "after": new_value,
            })
            self._sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.K:
            old_cookie, new_cookie = cycle_light_cookie(light, self._light_cookie_palette)
            self._push_command({
                "type": "EditLight",
                "index": self.lights_selection,
                "field": "cookie_id",
                "before": old_cookie,
                "after": new_cookie,
            })
            self._sync_lighting_runtime()
            return True
        return False

    def _hit_test_light(self, world_x: float, world_y: float, pick_radius: float = 16.0) -> Optional[int]:
        lights = self._get_scene_lights()
        for idx, light in enumerate(lights):
            lx = float(light.get("x", 0.0))
            ly = float(light.get("y", 0.0))
            dx = world_x - lx
            dy = world_y - ly
            if dx * dx + dy * dy <= pick_radius * pick_radius:
                return idx
        return None

    def _add_light(self, x: float, y: float) -> None:
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        sx, sy = self._snap_world_point(float(x), float(y))
        index, light = add_light(scene, sx, sy)
        self.lights_selection = index
        self._push_command({
            "type": "AddLight",
            "index": index,
            "light": copy.deepcopy(light),
        })
        self._sync_lighting_runtime()

    def _delete_selected_light(self) -> None:
        if self.lights_selection is None:
            return
        lights = self._get_scene_lights()
        if not (0 <= self.lights_selection < len(lights)):
            return
        removed = lights.pop(self.lights_selection)
        self._push_command({
            "type": "DeleteLight",
            "index": self.lights_selection,
            "light": copy.deepcopy(removed),
        })
        self.lights_selection = None
        self._sync_lighting_runtime()

    def handle_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_drag(self, x, y, dx, dy, buttons, modifiers)

    def handle_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return editor_input.handle_mouse_release(self, x, y, button, modifiers)

    def _draw_lights_overlay(self) -> None:
        if not (self.active and self.lights_tool_active):
            return
        lights = self._get_scene_lights()
        if not lights:
            return
        for idx, light in enumerate(lights):
            x = float(light.get("x", 0.0))
            y = float(light.get("y", 0.0))
            radius = float(light.get("radius", 160.0))
            is_selected = self.lights_selection == idx
            color = optional_arcade.arcade.color.YELLOW if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
            optional_arcade.arcade.draw_circle_outline(x, y, radius, color, 2)
            optional_arcade.arcade.draw_circle_filled(x, y, 4, color)
            if is_selected:
                optional_arcade.arcade.draw_text(f"r={int(radius)}", x + 8, y + 8, color, 10)

    # ------------------------------------------------------------------
    # Scene occluder tool
    # ------------------------------------------------------------------
    def toggle_occluder_tool(self) -> None:
        editor_ops.toggle_occluder_tool(self)
        self._autosave_workspace()

    def _toggle_occluder_mode(self, enabled: bool) -> None:
        self.occluder_tool_active = enabled
        if enabled:
            self.lights_tool_active = False
            self._cancel_shape_edit()
        self.occluder_points = []
        self.occluder_selection = None
        self.occluder_vertex_selection = None
        self.occluder_dragging = False
        self.occluder_drag_origin = None

    def _handle_occluder_mouse_press(self, world_x: float, world_y: float) -> None:
        hit = self._hit_test_occluder_vertex(world_x, world_y)
        if hit is not None:
            occ_idx, pt_idx = hit
            self.occluder_selection = occ_idx
            self.occluder_vertex_selection = pt_idx
            self.occluder_dragging = True
            self.occluder_drag_origin = self._get_occluder_point(occ_idx, pt_idx)
            return
        sx, sy = self._snap_world_point(world_x, world_y)
        if self.occluder_points:
            self.occluder_points.append((sx, sy))
        else:
            self.occluder_points = [(sx, sy)]
            self.occluder_selection = None
            self.occluder_vertex_selection = None

    def _hit_test_occluder_vertex(self, world_x: float, world_y: float, *, radius_px: float = 10.0) -> Optional[tuple[int, int]]:
        radius_world = self._shape_pick_radius_world(radius_px)
        radius_sq = radius_world * radius_world
        occluders = self._get_scene_occluders()
        for occ_idx, occ in enumerate(occluders):
            if not isinstance(occ, dict) or occ.get("type") != "poly":
                continue
            points = occ.get("points")
            if not isinstance(points, list):
                continue
            for pt_idx, entry in enumerate(points):
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                try:
                    px = float(entry[0])
                    py = float(entry[1])
                except Exception:  # noqa: BLE001
                    continue
                dx = float(world_x) - px
                dy = float(world_y) - py
                if dx * dx + dy * dy <= radius_sq:
                    return (occ_idx, pt_idx)
        return None

    def _commit_occluder_polygon(self) -> bool:
        if len(self.occluder_points) < 3:
            return False
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        index, occ = add_occluder(scene, list(self.occluder_points))
        self.occluder_points = []
        self.occluder_selection = index
        self.occluder_vertex_selection = None
        cmd = build_finish_polygon_cmd(index=index, occluder=copy.deepcopy(occ))
        self._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self._sync_occluders_runtime()
        return True

    def _remove_occluder_point(self) -> bool:
        if self.occluder_points:
            self.occluder_points.pop()
            return True
        if self.occluder_selection is None:
            return False
        if self.occluder_vertex_selection is not None:
            return self._remove_selected_occluder_vertex()
        return self._delete_selected_occluder()

    def _update_occluder_point(self, world_x: float, world_y: float, *, push_command: bool = True) -> bool:
        if self.occluder_selection is None or self.occluder_vertex_selection is None:
            return False
        occluders = self._get_scene_occluders()
        occ_idx = self.occluder_selection
        pt_idx = self.occluder_vertex_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return False
        before = points[pt_idx]
        sx, sy = self._snap_world_point(world_x, world_y)
        after = [float(sx), float(sy)]
        if before != after:
            points[pt_idx] = after
            if push_command:
                cmd = build_move_point_cmd(
                    occ_index=occ_idx,
                    point_index=pt_idx,
                    before=before if isinstance(before, list) else after,
                    after=after,
                    occ_id=occ.get("id") if isinstance(occ, dict) else None,
                )
                self._push_command({
                    "type": "EditOccluder",
                    "cmd": {"kind": cmd.kind, "payload": cmd.payload},
                })
            else:
                self._mark_dirty()
            self._sync_occluders_runtime()
        return True

    def _get_occluder_point(self, occ_idx: int, pt_idx: int) -> Optional[tuple[float, float]]:
        occluders = self._get_scene_occluders()
        if not (0 <= occ_idx < len(occluders)):
            return None
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return None
        entry = points[pt_idx]
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            try:
                return (float(entry[0]), float(entry[1]))
            except Exception:  # noqa: BLE001
                return None
        return None

    def _build_move_occluder_cmd(
        self,
        occ_idx: int,
        pt_idx: int,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> Any | None:
        occluders = self._get_scene_occluders()
        if not (0 <= occ_idx < len(occluders)):
            return None
        occ = occluders[occ_idx]
        return build_move_point_cmd(
            occ_index=occ_idx,
            point_index=pt_idx,
            before=[float(start[0]), float(start[1])],
            after=[float(end[0]), float(end[1])],
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )

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
        if self.occluder_selection is None:
            return False
        occluders = self._get_scene_occluders()
        if not (0 <= self.occluder_selection < len(occluders)):
            return False
        removed = occluders.pop(self.occluder_selection)
        cmd = build_delete_polygon_cmd(index=self.occluder_selection, occluder=copy.deepcopy(removed))
        self._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self.occluder_selection = None
        self.occluder_vertex_selection = None
        self._sync_occluders_runtime()
        return True

    def _remove_selected_occluder_vertex(self) -> bool:
        if self.occluder_selection is None or self.occluder_vertex_selection is None:
            return False
        occluders = self._get_scene_occluders()
        occ_idx = self.occluder_selection
        pt_idx = self.occluder_vertex_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return False
        if len(points) <= 3:
            return False
        removed = points.pop(pt_idx)
        cmd = build_remove_point_cmd(
            occ_index=occ_idx,
            point_index=pt_idx,
            point=removed if isinstance(removed, list) else [float(removed[0]), float(removed[1])],
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )
        self._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self.occluder_vertex_selection = None
        self._sync_occluders_runtime()
        return True

    def _handle_occluder_key_input(self, key: int) -> bool:
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return self._remove_occluder_point()
        if key == optional_arcade.arcade.key.I:
            mx = getattr(self.window, "_mouse_x", None)
            my = getattr(self.window, "_mouse_y", None)
            if isinstance(mx, (int, float)) and isinstance(my, (int, float)):
                wx, wy = self.window.screen_to_world(mx, my)
                return self._insert_occluder_point(wx, wy)
        return False

    def _insert_occluder_point(self, world_x: float, world_y: float) -> bool:
        if self.occluder_selection is None:
            return False
        occluders = self._get_scene_occluders()
        occ_idx = self.occluder_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return False
        insert_idx, proj = find_closest_edge_insert_index(points, (world_x, world_y))
        sx, sy = self._snap_world_point(proj[0], proj[1])
        cmd = build_insert_point_cmd(
            occ_index=occ_idx,
            insert_index=insert_idx,
            point=(sx, sy),
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
        self._push_command({"type": "EditOccluder", "cmd": {"kind": cmd.kind, "payload": cmd.payload}})
        self.occluder_vertex_selection = insert_idx
        self._sync_occluders_runtime()
        return True

    def _update_param(self, behaviour_name: str, param_name: str, value: Any) -> None:
        if not self.selected_entity:
            return

        entity_name = getattr(self.selected_entity, "mesh_name", "")

        # Get old value for undo
        # We need to dig it out from config or runtime
        # Ideally we get it from runtime as that's the source of truth for the editor view
        # But config is what we save.
        # Let's use the current config value as "before"
        entity_data = self.window.scene_controller._ensure_entity_data_dict(self.selected_entity)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        current_config = config_root.get(behaviour_name, {})
        old_value = current_config.get(param_name)

        # If not in config, check param defs default
        if old_value is None:
             param_defs = get_behaviour_param_defs(behaviour_name)
             if param_name in param_defs:
                 old_value = param_defs[param_name].default

        self._update_param_internal(behaviour_name, param_name, value, entity_name)

        self._push_command({
            "type": "ChangeProperty",
            "entity_name": entity_name,
            "behaviour": behaviour_name,
            "param": param_name,
            "before": old_value,
            "after": value
        })

    def _update_param_internal(self, behaviour_name: str, param_name: str, value: Any, entity_name: str) -> None:
        entity = self._find_entity_by_name(entity_name)
        if not entity and self.selected_entity:
            selected_name = getattr(self.selected_entity, "mesh_name", "") or ""
            if not entity_name or selected_name == entity_name:
                entity = self.selected_entity
        if not entity:
            return

        # 1. Update Entity Data (for saving)
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.setdefault(behaviour_name, {})
        behaviour_config[param_name] = value

        # Also update the list-based config if present (legacy/mixed support)
        entries = self.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        behaviour_index = -1
        for idx, entry in enumerate(entries):
            if entry.get("type") == behaviour_name:
                behaviour_index = idx
                params = entry.setdefault("params", {})
                if isinstance(params, dict):
                    params[param_name] = value
                break

        # 2. Update Runtime Instance
        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        if 0 <= behaviour_index < len(runtime_behaviours):
            behaviour = runtime_behaviours[behaviour_index]

            # Update config dict on behaviour
            if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                behaviour.config[param_name] = value

            # Update attribute if it exists
            if hasattr(behaviour, param_name):
                setattr(behaviour, param_name, value)

            # Call hook
            if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                try:
                    behaviour.on_config_updated(param_name, value)
                except Exception as e:
                    logger.error("[Editor] Error updating behaviour: %s", e)

    def _remove_param_internal(self, behaviour_name: str, param_name: str, entity_name: str) -> None:
        entity = self._find_entity_by_name(entity_name)
        if not entity and self.selected_entity:
            selected_name = getattr(self.selected_entity, "mesh_name", "") or ""
            if not entity_name or selected_name == entity_name:
                entity = self.selected_entity
        if not entity:
            return

        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.get(behaviour_name)
        if isinstance(behaviour_config, dict):
            behaviour_config.pop(param_name, None)
            if not behaviour_config:
                config_root.pop(behaviour_name, None)

        entries = self.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        for entry in entries:
            if entry.get("type") == behaviour_name:
                params = entry.get("params")
                if isinstance(params, dict):
                    params.pop(param_name, None)
                break

        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for behaviour in runtime_behaviours:
            if getattr(behaviour, "mesh_behaviour_type", None) == behaviour_name:
                if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                    behaviour.config.pop(param_name, None)
                if hasattr(behaviour, param_name):
                    try:
                        setattr(behaviour, param_name, None)
                    except Exception:
                        pass
                if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                    try:
                        behaviour.on_config_updated(param_name, None)
                    except Exception as e:
                        logger.error("[Editor] Error updating behaviour: %s", e)

    def _apply_behaviour_config_map(self, entity: optional_arcade.arcade.Sprite, config_map: dict[str, Any]) -> None:
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        entity_data["behaviour_config"] = copy.deepcopy(config_map)

        entries = self.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            behaviour_type = entry.get("type")
            if not isinstance(behaviour_type, str):
                continue
            params = config_map.get(behaviour_type, {})
            if isinstance(params, dict):
                entry["params"] = copy.deepcopy(params)

        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for behaviour in runtime_behaviours:
            behaviour_type = getattr(behaviour, "mesh_behaviour_type", None)
            if not isinstance(behaviour_type, str):
                continue
            params = config_map.get(behaviour_type, {})
            if isinstance(params, dict):
                if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                    behaviour.config.clear()
                    behaviour.config.update(copy.deepcopy(params))
                for key, value in params.items():
                    if hasattr(behaviour, key):
                        try:
                            setattr(behaviour, key, value)
                        except Exception:
                            pass
                if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                    for key, value in params.items():
                        try:
                            behaviour.on_config_updated(key, value)
                        except Exception as e:
                            logger.error("[Editor] Error updating behaviour: %s", e)

    def _get_prefab_base_entity(self, entity_data: dict[str, Any]) -> dict[str, Any] | None:
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            return None
        variant_id = entity_data.get("variant_id")
        try:
            from .prefabs import get_prefab_manager  # noqa: PLC0415

            resolved = get_prefab_manager().resolve_with_variant(prefab_id.strip(), variant_id)
        except Exception:
            return None
        if not isinstance(resolved, dict):
            return None
        base_entity = resolved.get("entity")
        if not isinstance(base_entity, dict):
            return None
        return base_entity

    def _prefab_override_info(
        self, entity_data: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, set[str]]:
        base_entity = self._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return None, set()
        overrides = compute_prefab_overrides(entity_data, base_entity)
        return base_entity, {o.field_path for o in overrides}

    def _reset_selected_prefab_override(self, selected_item: dict[str, Any]) -> bool:
        if not self.selected_entity:
            return False
        if selected_item.get("type") != "param":
            return False
        entity = self.selected_entity
        entity_name = getattr(entity, "mesh_name", "")
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        base_entity, override_paths = self._prefab_override_info(entity_data)
        if base_entity is None:
            self.set_status("Reset override: no prefab for selection")
            return False
        behaviour_name = selected_item.get("behaviour")
        param_name = selected_item.get("name")
        if not isinstance(behaviour_name, str) or not isinstance(param_name, str):
            return False
        field_path = f"behaviour_config.{behaviour_name}.{param_name}"
        if field_path not in override_paths:
            self.set_status("Reset override: no prefab override")
            return False

        current_config = entity_data.get("behaviour_config", {})
        if not isinstance(current_config, dict):
            return False
        current_behaviour = current_config.get(behaviour_name, {})
        if not isinstance(current_behaviour, dict) or param_name not in current_behaviour:
            return False

        old_value = current_behaviour.get(param_name)
        base_cfg = base_entity.get("behaviour_config", {})
        base_value = None
        base_missing = True
        if isinstance(base_cfg, dict):
            base_behaviour = base_cfg.get(behaviour_name, {})
            if isinstance(base_behaviour, dict) and param_name in base_behaviour:
                base_value = base_behaviour.get(param_name)
                base_missing = False

        if base_missing:
            self._remove_param_internal(behaviour_name, param_name, entity_name)
        else:
            self._update_param_internal(behaviour_name, param_name, base_value, entity_name)

        self._push_command(
            {
                "type": "ResetPrefabOverride",
                "entity_name": entity_name,
                "behaviour": behaviour_name,
                "param": param_name,
                "before": old_value,
                "after": base_value,
                "base_missing": base_missing,
            }
        )
        self._refresh_inspector_items()
        self.set_status("Reset override: ok")
        return True

    def _reset_all_prefab_overrides(self) -> bool:
        if not self.selected_entity:
            return False
        entity = self.selected_entity
        entity_name = getattr(entity, "mesh_name", "")
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        base_entity, override_paths = self._prefab_override_info(entity_data)
        if base_entity is None:
            self.set_status("Reset overrides: no prefab for selection")
            return False

        before_config = copy.deepcopy(entity_data.get("behaviour_config") or {})
        after_config = copy.deepcopy(before_config)
        before_shapes = {
            "collision_poly": self._shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._shape_payload_for_undo(entity_data.get("occluder_poly")),
        }
        changed = False

        base_cfg = base_entity.get("behaviour_config", {})
        if not isinstance(base_cfg, dict):
            base_cfg = {}

        for path in sorted(override_paths):
            if not path.startswith("behaviour_config."):
                if path in {"collision_poly", "occluder_poly"}:
                    base_shape = base_entity.get(path)
                    if base_shape is None:
                        self._apply_shape_payload(entity, path, [])
                    else:
                        self._apply_shape_payload(entity, path, base_shape)
                    changed = True
                continue
            parts = path.split(".")
            if len(parts) < 3:
                continue
            behaviour_name = parts[1]
            param_name = parts[2]
            base_behaviour = base_cfg.get(behaviour_name, {})
            base_missing = True
            base_value = None
            if isinstance(base_behaviour, dict) and param_name in base_behaviour:
                base_missing = False
                base_value = base_behaviour.get(param_name)

            target = after_config.get(behaviour_name)
            if not isinstance(target, dict):
                target = {}
                after_config[behaviour_name] = target
            if base_missing:
                if param_name in target:
                    target.pop(param_name, None)
                    changed = True
                    if not target:
                        after_config.pop(behaviour_name, None)
            else:
                if target.get(param_name) != base_value:
                    target[param_name] = base_value
                    changed = True

        after_shapes = {
            "collision_poly": self._shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._shape_payload_for_undo(entity_data.get("occluder_poly")),
        }

        if not changed:
            self.set_status("Reset overrides: none to reset")
            return False

        self._apply_behaviour_config_map(entity, after_config)
        self._push_command(
            {
                "type": "ResetPrefabOverrides",
                "entity_name": entity_name,
                "before": before_config,
                "after": after_config,
                "before_shapes": before_shapes,
                "after_shapes": after_shapes,
            }
        )
        self._refresh_inspector_items()
        self.set_status("Reset overrides: ok")
        return True

    def _refresh_inspector_items(self) -> None:
        self._cached_inspector_items = self._build_inspector_items()

    def _get_inspector_items(self) -> List[Dict[str, Any]]:
        # In a real app we might cache this and invalidate on selection change
        # For now, let's rebuild if empty, but we need to keep it stable during a frame
        if not self._cached_inspector_items and self.selected_entity:
            self._refresh_inspector_items()
        return self._cached_inspector_items

    def _build_inspector_items(self) -> List[Dict[str, Any]]:
        if not self.selected_entity:
            return []

        items = []
        sprite = self.selected_entity

        # Entity Properties Header
        items.append({
            "type": "header",
            "text": f"Entity: {getattr(sprite, 'mesh_name', '<unnamed>')}",
            "kind": "entity_header"
        })

        # Behaviours
        behaviours = getattr(sprite, "mesh_behaviours", [])
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        _base_entity, override_paths = self._prefab_override_info(entity_data)

        for b_name in behaviours:
            items.append({
                "type": "header",
                "text": f"Behaviour: {b_name}",
                "kind": "behaviour_header"
            })

            param_defs = get_behaviour_param_defs(b_name)
            current_config = config_root.get(b_name, {})

            # Sort params: defined ones first, then custom
            all_keys = set(param_defs.keys()) | set(current_config.keys())
            sorted_keys = sorted(list(all_keys))

            for key in sorted_keys:
                # Determine value
                if key in current_config:
                    val = current_config[key]
                    is_default = False
                elif key in param_defs:
                    val = param_defs[key].default
                    is_default = True
                else:
                    val = None
                    is_default = True # Should not happen given set union

                # Determine type
                kind = "string"
                if key in param_defs:
                    def_type = param_defs[key].type
                    if def_type in (int, "int"): kind = "int"
                    elif def_type in (float, "float"): kind = "float"
                    elif def_type in (bool, "bool"): kind = "bool"
                else:
                    # Infer from value
                    if isinstance(val, bool): kind = "bool"
                    elif isinstance(val, int): kind = "int"
                    elif isinstance(val, float): kind = "float"

                items.append({
                    "type": "param",
                    "name": key,
                    "value": val,
                    "kind": kind,
                    "behaviour": b_name,
                    "is_default": is_default,
                    "is_override": f"behaviour_config.{b_name}.{key}" in override_paths,
                })

        return items

    def nudge_selected(self, dx: float, dy: float) -> None:
        editor_ops.nudge_selected(self, dx, dy)

    def save_current_scene(self) -> None:
        editor_ops.save_current_scene(self)

    def toggle_palette(self) -> None:
        editor_ops.toggle_palette(self)
        if self.palette_active:
            # Recompute tag ranking on open (cheap, keeps caching simple).
            self._palette_tag_ranked = _palette_tag_frequencies(list(self.prefab_palette))
            self._prewarm_visible_palette_thumbs()

    def move_palette_selection(self, delta: int) -> None:
        editor_ops.move_palette_selection(self, delta)

    def select_palette_index(self, index: int) -> None:
        editor_ops.select_palette_index(self, index)

    def toggle_lights_tool(self) -> None:
        editor_ops.toggle_lights_tool(self)
        self._autosave_workspace()

    def _toggle_lights_mode(self, enabled: bool) -> None:
        self.lights_tool_active = enabled
        if enabled:
            self._toggle_occluder_mode(False)
        if enabled:
            self.inspector_active = False
            self.palette_active = False
            self.palette_filter_active = False
            self.hierarchy_active = False
            self.dialogue_panel_active = False
            self.animation_active = False
            self.tile_panel_active = False
        else:
            self.lights_selection = None
            self.lights_dragging = False
            self.lights_drag_start = None
            self.lights_original_pos = None

    @property
    def palette_selected_prefab(self) -> Optional[str]:
        items = self._get_palette_items()
        if 0 <= self.palette_index < len(items):
            return items[self.palette_index]["display_name"]
        return None

    def place_entity_at_mouse(self, x: float, y: float) -> None:
        editor_ops.place_entity_at_mouse(self, x, y)

    def duplicate_selected(self) -> None:
        editor_ops.duplicate_selected(self)

    def delete_selected(self) -> None:
        editor_ops.delete_selected(self)

    def copy_selected_entity_to_clipboard(self) -> None:
        """Copy the selected entity to the internal clipboard."""
        from engine.editor.editor_clipboard_ops import get_entity_id_from_data  # noqa: PLC0415

        if not self.active or self.selected_entity is None:
            return

        entity_data = getattr(self.selected_entity, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            logger.info("[Editor] Cannot copy: missing entity data")
            return

        import copy as copy_module  # noqa: PLC0415
        self._entity_clipboard = copy_module.deepcopy(entity_data)
        self._entity_clipboard_source_id = get_entity_id_from_data(entity_data)

        logger.info("[Editor] Copied entity: %s", self._entity_clipboard_source_id)

        # Toast feedback
        hud = getattr(self.window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue(f"Copied: {self._entity_clipboard_source_id}")

    def paste_entity_from_clipboard(
        self, spawn_world_xy: tuple[float, float] | None = None
    ) -> None:
        """Paste an entity from the internal clipboard.

        Args:
            spawn_world_xy: Optional position to spawn at. If None, uses camera center.
        """
        from engine.editor.editor_clipboard_ops import (  # noqa: PLC0415
            clone_entity_payload,
            collect_existing_entity_ids,
            generate_copy_entity_id,
        )

        if not self.active:
            return

        if self._entity_clipboard is None:
            logger.info("[Editor] Nothing to paste")
            hud = getattr(self.window, "player_hud", None)
            if hud is not None:
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue("Nothing to paste")
            return

        # Get spawn position (camera center if not specified)
        if spawn_world_xy is None:
            camera_ctrl = getattr(self.window, "camera_controller", None)
            if camera_ctrl is not None:
                camera = getattr(camera_ctrl, "camera", None)
                if camera is not None:
                    pos = getattr(camera, "position", None)
                    if pos is not None:
                        spawn_world_xy = (float(pos[0]), float(pos[1]))
            if spawn_world_xy is None:
                spawn_world_xy = (0.0, 0.0)

        # Generate unique ID
        existing_ids = collect_existing_entity_ids(self.window.scene_controller.all_sprites)
        source_id = self._entity_clipboard_source_id or "entity"
        new_id = generate_copy_entity_id(existing_ids, source_id)

        # Clone entity with new ID and position
        new_entity_data = clone_entity_payload(self._entity_clipboard, new_id, spawn_world_xy)

        # Create entity
        new_sprite = self._create_entity_internal(new_entity_data)
        if new_sprite:
            self.selected_entity = new_sprite
            self._reset_zone_selection_state()
            self._sync_zone_selection_state(self.selected_entity)
            logger.info("[Editor] Pasted entity: %s at (%.1f, %.1f)", new_id, spawn_world_xy[0], spawn_world_xy[1])

            # Push undo command
            self._push_command({
                "type": "AddEntity",
                "entity_name": new_id,
                "data": new_entity_data,
            })

            # Toast feedback
            hud = getattr(self.window, "player_hud", None)
            if hud is not None:
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue(f"Pasted: {new_id}")

    def draw_world(self) -> None:
        """Draws in world space (camera active)."""
        if not self.active:
            return

        # Draw selection highlight
        if self.selected_entity:
            color = optional_arcade.arcade.color.NEON_GREEN if not self.inspector_active else optional_arcade.arcade.color.CYAN
            draw_outline_centered(
                self.selected_entity.center_x,
                self.selected_entity.center_y,
                self.selected_entity.width,
                self.selected_entity.height,
                color,
                2,
            )

            # Draw Tool Visuals
            if self.tool_mode == TOOL_MODE_PATH:
                patrol = self._get_patrol_behaviour(self.selected_entity)
                if patrol:
                    points = self._get_patrol_points(patrol)
                    if points:
                        # Draw lines connecting points
                        if len(points) > 1:
                            optional_arcade.arcade.draw_line_strip(points, optional_arcade.arcade.color.CYAN, 2)

                        # Draw points
                        for i, (px, py) in enumerate(points):
                            color = optional_arcade.arcade.color.ORANGE if i == self.selected_waypoint_index else optional_arcade.arcade.color.CYAN
                            optional_arcade.arcade.draw_circle_filled(px, py, 4, color)
                            # Draw index number
                            optional_arcade.arcade.draw_text(str(i), px + 5, py + 5, optional_arcade.arcade.color.WHITE, 10)

            elif self.tool_mode == TOOL_MODE_ZONE:
                zone_behaviours = self._get_zone_behaviours(self.selected_entity)
                active_behaviour = self._get_zone_behaviour(self.selected_entity) if zone_behaviours else None

                for behaviour in zone_behaviours:
                    is_active = behaviour is active_behaviour
                    owner = getattr(behaviour, "entity", self.selected_entity)
                    cx = getattr(owner, "center_x", self.selected_entity.center_x)
                    cy = getattr(owner, "center_y", self.selected_entity.center_y)

                    if hasattr(behaviour, "radius"):
                        radius = max(0.0, float(getattr(behaviour, "radius", 0.0)))
                        outline = optional_arcade.arcade.color.NEON_GREEN if is_active else optional_arcade.arcade.color.DARK_SPRING_GREEN
                        fill_alpha = 80 if is_active else 30
                        fill_color = (outline[0], outline[1], outline[2], fill_alpha)
                        optional_arcade.arcade.draw_circle_outline(cx, cy, radius, outline, 2)
                        optional_arcade.arcade.draw_circle_filled(cx, cy, radius, fill_color)
                    else:
                        width = max(0.0, float(getattr(behaviour, "width", 0.0)))
                        height = max(0.0, float(getattr(behaviour, "height", 0.0)))
                        outline = optional_arcade.arcade.color.RED if is_active else optional_arcade.arcade.color.DARK_RED
                        fill_alpha = 80 if is_active else 30
                        fill_color = (outline[0], outline[1], outline[2], fill_alpha)
                        draw_outline_centered(cx, cy, width, height, outline, 2)
                        _draw_rectangle_filled(cx, cy, width, height, fill_color)

            if self.shape_edit_mode and self.shape_edit_entity is self.selected_entity:
                points = [
                    (self.selected_entity.center_x + px, self.selected_entity.center_y + py)
                    for px, py in self.shape_edit_points
                ]
                if len(points) >= 2:
                    optional_arcade.arcade.draw_line_strip(points, optional_arcade.arcade.color.YELLOW, 2)
                    optional_arcade.arcade.draw_line(points[-1][0], points[-1][1], points[0][0], points[0][1], optional_arcade.arcade.color.YELLOW, 2)
                for px, py in points:
                    optional_arcade.arcade.draw_circle_filled(px, py, 4, optional_arcade.arcade.color.YELLOW)

        overlay = getattr(self.window, "light_occluder_overlay", None)
        if overlay is not None and callable(getattr(overlay, "draw_world", None)):
            overlay.draw_world()
        else:
            self._draw_lights_overlay()

        # Draw Asset Placement Ghost
        if self.asset_place_active and self.asset_place_path:
            mx = getattr(self.window, "_mouse_x", 0)
            my = getattr(self.window, "_mouse_y", 0)
            wx, wy = self.window.screen_to_world(mx, my)
            
            if self.snap_enabled:
                wx, wy = snap_world_point((wx, wy), self.snap_mode, self.grid_size)
            
            draw_asset_placement_ghost(self.asset_place_path, wx, wy)

        # Draw Palette Preview
        if self.palette_active and self.palette_selected_prefab:
            # Get mouse pos from window (hacky but needed since we don't track it in update)
            mx = self.window._mouse_x
            my = self.window._mouse_y
            wx, wy = self.window.screen_to_world(mx, my)

            # Snap
            grid = self.grid_size
            wx = round(wx / grid) * grid
            wy = round(wy / grid) * grid

            draw_outline_centered(wx, wy, 32, 32, optional_arcade.arcade.color.GREEN, 2)
            optional_arcade.arcade.draw_text(self.palette_selected_prefab, wx, wy + 20, optional_arcade.arcade.color.WHITE, 10, anchor_x="center")

    def draw_overlay(self) -> None:
        """Draws in screen space (UI)."""
        if not self.active:
            return

        self._update_status()

        # Draw overlay text
        dirty_flag = bool(self.dirty_state.is_dirty)
        scene_name = self.window.scene_controller.current_scene_path or ""
        # Shorten path for display
        if scene_name and len(scene_name) > 30:
            scene_name = "..." + scene_name[-27:]

        lines = [
            "EDITOR MODE (F4)",
            f"Scene: {scene_name or 'Unsaved'}" + (" *" if dirty_flag else ""),
            f"Tool: {self.tool_mode} (R)",
            "----------------",
            "Click: Select Entity",
            "TAB: Toggle Inspector",
            "H: Toggle Hierarchy",
            "Ctrl+S: Save Scene",
            "Ctrl+Z: Undo | Ctrl+Y: Redo",
            "----------------"
        ]

        if self.shape_edit_mode:
            lines.append(f"Shape Mode: {self.shape_edit_mode} (Esc to exit)")
            lines.append(f"Shape Snap: {'on' if self.shape_snap_enabled else 'off'} (G)")
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        elif self.selected_entity:
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        if self._status_message:
            lines.append(self._status_message)
            lines.append("----------------")

        if self.tool_mode == TOOL_MODE_PATH:
            lines.append("PATH TOOL:")
            lines.append("Click Point: Select")
            lines.append("Shift+Click: Add Point")
            lines.append("Arrows: Move Point")
            lines.append("Del: Remove Point")
            lines.append("----------------")
        elif self.tool_mode == TOOL_MODE_ZONE:
            lines.append("ZONE TOOL:")
            lines.append("Shift+Arrows: Resize")
            zone_behaviours = self._get_zone_behaviours(self.selected_entity)
            if zone_behaviours:
                active_zone = self._get_zone_behaviour(self.selected_entity)
                description = describe_zone_behaviour(active_zone)
                if len(zone_behaviours) > 1:
                    lines.append(
                        f"Ctrl+R: Cycle Zone ({self.zone_behaviour_index + 1}/{len(zone_behaviours)})"
                    )
                trigger, hitbox = self._split_zone_behaviours(self.selected_entity)
                if trigger and hitbox:
                    lines.append("T: Toggle Trigger/Hitbox")
                lines.append(f"Active Target: {description}")
            else:
                lines.append("Select entity with TriggerZone/Hitbox")
            lines.append("----------------")

        if self.selected_entity:
            if self.inspector_active:
                lines.append("[INSPECTOR ACTIVE]")
                lines.append("UP/DOWN: Select")
                lines.append("LEFT/RIGHT: Edit")

                items = self._get_inspector_items()

                if any(item.get("is_override") for item in items if item.get("type") == "param"):
                    lines.append("Shift+R: Reset override | Ctrl+Shift+R: Reset all")
                lines.append("----------------")

                # Ensure selection index is valid
                if items:
                    self.inspector_selection_index = max(0, min(self.inspector_selection_index, len(items) - 1))

                # Viewport for scrolling if too many items
                max_visible = 20
                start_idx = 0
                if self.inspector_selection_index > max_visible / 2:
                    start_idx = max(0, int(self.inspector_selection_index - max_visible / 2))
                end_idx = min(len(items), start_idx + max_visible)

                for i in range(start_idx, end_idx):
                    item = items[i]
                    is_selected = (i == self.inspector_selection_index)
                    prefix = "> " if is_selected else "  "

                    if item["type"] == "header":
                        lines.append(f"{prefix}{item['text']}")
                    elif item["type"] == "param":
                        val_str = str(item['value'])
                        if item['kind'] == 'bool':
                            val_str = "ON" if item['value'] else "OFF"

                        # Highlight modified values
                        if item.get("is_override"):
                            mod_marker = "!"
                        else:
                            mod_marker = "" if item['is_default'] else "*"
                        lines.append(f"{prefix}  {item['name']}: {val_str} {mod_marker}")
            else:
                # Simple view
                name = self._get_display_name_for_sprite(self.selected_entity)
                x = self.selected_entity.center_x
                y = self.selected_entity.center_y
                lines.append(f"Selected: {name}")
                lines.append(f"Pos: ({x:.1f}, {y:.1f})")
                tags = self._get_entity_tags(self.selected_entity)
                if tags:
                    lines.append(f"Tags: {', '.join(tags)}")
                lines.append("(Press TAB to edit params)")
        else:
            lines.append("No selection")

        start_y = self.window.height - 100
        # Draw background for text
        draw_panel_bg(
            0,
            300,
            start_y - len(lines) * 20 - 10,
            start_y + 20,
        )

        # Optimize: Join lines and use single Text object
        # Note: We lose per-line color this way, but it fixes the performance warning.
        # To keep colors, we'd need a batch or multiple Text objects.
        # For now, let's use a simple join and maybe use rich text if Arcade supports it later,
        # or just accept monochrome for the main block.
        # Actually, let's just use the Text object for the bulk and maybe separate header?
        # The warning is about creating NEW objects every frame.
        # Updating .text is faster.

        full_text = "\n".join(lines)
        self._overlay_text_obj.text = full_text
        self._overlay_text_obj.y = start_y
        self._overlay_text_obj.draw()

        # Draw Palette
        if self.palette_active:
            try:
                max_per_frame = int(os.environ.get("MESH_EDITOR_THUMBS_PER_FRAME", "2"))
            except Exception:
                max_per_frame = 2
            if max_per_frame > 0:
                tick_thumb_generation(max_per_frame=max_per_frame)

            items = self._get_palette_items()
            p_lines = ["PALETTE (P)", "-----------"]
            raw_filter = str(self.palette_filter or "")
            _terms, _tags = _parse_palette_filter(raw_filter)
            tag_summary = ""
            if _tags:
                shown = _tags[:3]
                more = len(_tags) - len(shown)
                tail = f" +{more}" if more > 0 else ""
                tag_summary = f" (Tags: {', '.join(shown)}{tail})"
            else:
                tag_summary = " (#tag or t:tag)"

            filter_status = f"Filter: \"{raw_filter}\"{tag_summary}"
            if self.palette_filter_active:
                filter_status += "_"
            p_lines.append(filter_status)

            # Tag suggestions (only while actively typing a tag token)
            if self.palette_filter_active:
                sugg = self._palette_tag_suggestions()
                if sugg:
                    shown = list(sugg)
                    shown[0] = f"[{shown[0]}]"
                    p_lines.append("Tags: " + "  ".join(shown))
            p_lines.append("-----------")
            header_lines = len(p_lines)

            if items:
                for i, item in enumerate(items):
                    prefix = "> " if i == self.palette_index else f"{i+1} "
                    p_lines.append(f"{prefix}{item['display_name']}")
            else:
                p_lines.append("  (No prefabs found)")

            panel_width = 240
            panel_left = self.window.width - panel_width
            p_start_y = self.window.height - 100
            text_indent = PALETTE_THUMB_DRAW_SIZE + 10
            p_start_x = panel_left + text_indent

            draw_panel_bg(
                panel_left - 10,
                self.window.width,
                p_start_y - len(p_lines) * PALETTE_LINE_HEIGHT - 10,
                p_start_y + 20,
            )

            self._palette_text_obj.text = "\n".join(p_lines)
            self._palette_text_obj.x = p_start_x
            self._palette_text_obj.y = p_start_y
            self._palette_text_obj.width = panel_width - text_indent - 10
            self._palette_text_obj.draw()

            thumb_x = panel_left + (PALETTE_THUMB_DRAW_SIZE / 2) + 4
            start_i, end_i = self._palette_visible_index_range(len(items))
            for i in range(start_i, end_i):
                item = items[i]
                texture = self._get_palette_thumb_texture(item)
                line_index = header_lines + i
                thumb_y = p_start_y - (line_index * PALETTE_LINE_HEIGHT) - (PALETTE_LINE_HEIGHT / 2)
                if texture is None:
                    # Thumb not ready yet: draw placeholder box.
                    draw_panel_bg(
                        thumb_x - (PALETTE_THUMB_DRAW_SIZE / 2),
                        thumb_x + (PALETTE_THUMB_DRAW_SIZE / 2),
                        thumb_y - (PALETTE_THUMB_DRAW_SIZE / 2),
                        thumb_y + (PALETTE_THUMB_DRAW_SIZE / 2),
                        color=(0, 0, 0, 60),
                    )
                    draw_outline_centered(
                        thumb_x,
                        thumb_y,
                        PALETTE_THUMB_DRAW_SIZE,
                        PALETTE_THUMB_DRAW_SIZE,
                        color=(255, 255, 255, 80),
                        border=1,
                    )
                else:
                    optional_arcade.arcade.draw_texture_rectangle(
                        thumb_x,
                        thumb_y,
                        PALETTE_THUMB_DRAW_SIZE,
                        PALETTE_THUMB_DRAW_SIZE,
                        texture,
                    )

        # Draw Hierarchy
        if self.hierarchy_active:
            h_lines = ["HIERARCHY (H)", "-------------"]

            # Usage hints
            h_lines.append("UP/DOWN: Navigate")
            h_lines.append("ENTER/SPACE: Select")
            h_lines.append("SHIFT+R: Rename selection")
            h_lines.append("/ or CTRL+F: Filter")
            h_lines.append("-------------")

            # Filter status
            filter_status = f"Filter: {self.hierarchy_filter}"
            if self.hierarchy_filter_active:
                filter_status += "_"
            h_lines.append(filter_status)

            if self.hierarchy_rename_active:
                rename_status = f"Rename: {self.hierarchy_rename_buffer}_"
            else:
                rename_status = "Rename: (SHIFT+R)"
            h_lines.append(rename_status)
            h_lines.append("-------------")

            # List items
            items = self._cached_hierarchy_list

            # Viewport
            max_visible = 25
            start_idx = 0
            if self.hierarchy_selection_index > max_visible / 2:
                start_idx = max(0, int(self.hierarchy_selection_index - max_visible / 2))
            end_idx = min(len(items), start_idx + max_visible)

            for i in range(start_idx, end_idx):
                sprite = items[i]
                is_selected = (i == self.hierarchy_selection_index)
                prefix = "> " if is_selected else "  "
                name = self._get_display_name_for_sprite(sprite)
                layer = getattr(sprite, "layer", "?")
                tags = self._get_entity_tags(sprite)
                tag_suffix = f" [{', '.join(tags)}]" if tags else ""
                h_lines.append(f"{prefix}{name} ({layer}){tag_suffix}")

            if len(items) == 0:
                h_lines.append("  (No entities found)")

            # Draw panel on right side (left of palette if active, or just right)
            # Let's put it on the right, maybe overlapping palette if both open (user should toggle)
            h_start_x = self.window.width - 300
            h_start_y = self.window.height - 100

            draw_panel_bg(
                h_start_x - 10,
                self.window.width,
                h_start_y - len(h_lines) * 20 - 10,
                h_start_y + 20,
            )

            for i, line in enumerate(h_lines):
                color = optional_arcade.arcade.color.CYAN if line.startswith(">") or "Filter:" in line else optional_arcade.arcade.color.WHITE
                optional_arcade.arcade.draw_text(
                    line,
                    h_start_x,
                    h_start_y - i * 20,
                    color,
                    12,
                    font_name="Consolas"
                )

        # Dialogue / Quest panel (screen space)
        if self.dialogue_panel_active:
            self._draw_dialogue_panel()
            self._draw_quest_context_panel()

        if self.animation_active:
            self._draw_animation_panel()

        if self.tile_panel_active:
            self._draw_tile_panel()

        if self.confirm_open:
            self._draw_unsaved_confirm_dialog()

    def _draw_dialogue_panel(self) -> None:
        lines: List[str] = ["DIALOGUE (D)", "--------------"]
        if self.dialogue_editing:
            lines.append("Editing: type to change, ENTER to save, ESC to cancel")
        nodes = self._dialogue_nodes()
        if not nodes:
            lines.append("No dialogue nodes found on this entity.")
        else:
            for idx, node in enumerate(nodes):
                prefix = "> " if idx == self.dialogue_selected_node else "  "
                node_id = node.get("_id", f"node_{idx}")
                text = str(node.get("text", ""))[:80]
                lines.append(f"{prefix}{node_id}: {text}")
                choices = node.get("choices") or []
                if isinstance(choices, list):
                    for c_idx, choice in enumerate(choices):
                        marker = "    *" if (idx == self.dialogue_selected_node and c_idx == self.dialogue_selected_choice) else "     "
                        if not isinstance(choice, dict):
                            continue
                        label = choice.get("text", "<empty>")
                        nxt = choice.get("next") or "<end>"
                        lines.append(f"{marker} [{choice.get('id','?')}] {label} -> {nxt}")
        if self._dialogue_warnings:
            lines.append("Warnings:")
            for warn in self._dialogue_warnings[:4]:
                lines.append(f"  - {warn}")

        start_x = 320
        start_y = self.window.height - 80
        panel_width = 520
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = optional_arcade.arcade.color.CYAN if line.startswith(">") or "Editing" in line else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def _draw_animation_panel(self) -> None:
        lines: List[str] = ["ANIMATOR (A)", "--------------"]
        if self.animation_editing:
            lines.append("Editing frames: type values comma-separated, ENTER to save, ESC to cancel")
        config = self._get_animator_config(self.selected_entity)
        animations = config.get("animations", {}) if isinstance(config, dict) else {}
        names = sorted(animations.keys()) if isinstance(animations, dict) else []
        if not names:
            lines.append("No animations configured on this entity.")
        else:
            self.animation_selected_index = max(0, min(self.animation_selected_index, len(names) - 1))
            for idx, name in enumerate(names):
                clip_cfg = animations.get(name, {})
                prefix = "> " if idx == self.animation_selected_index else "  "
                mode = clip_cfg.get("mode", "loop")
                fps = clip_cfg.get("fps", config.get("animation_frame_rate", 8.0))
                frames = clip_cfg.get("frames")
                frame_desc = ", ".join(str(f) for f in frames) if isinstance(frames, list) else "<frames?>"
                lines.append(f"{prefix}{name} | mode={mode} fps={fps} frames={frame_desc}")
            lines.append("Fields: mode / fps / frames (TAB/LEFT/RIGHT to change focus)")
            lines.append(f"Active field: {self.animation_field_focus}")
            lines.append("ENTER edits field; ESC closes panel")
        start_x = 320
        start_y = self.window.height - 80
        panel_width = 520
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = optional_arcade.arcade.color.CYAN if line.startswith(">") or "Active field" in line else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def _draw_tile_panel(self) -> None:
        lines: List[str] = ["TILES (G)", "--------------"]
        if not self._tilemap_available():
            lines.append("No tilemap loaded")
        else:
            lines.append(f"Layer: {self._current_tile_layer()} ([ / ] to change)")
            if not self.tile_palette:
                lines.append("No tiles available")
            else:
                for idx, gid in enumerate(self.tile_palette):
                    prefix = "> " if idx == self.tile_palette_index else "  "
                    lines.append(f"{prefix}Tile GID {gid}")
            lines.append("Left Click: paint | Right Click: erase")
            lines.append("Ctrl+Z / Ctrl+Y: undo/redo")
        start_x = 10
        start_y = self.window.height - 120
        panel_width = 240
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = optional_arcade.arcade.color.CYAN if line.startswith(">") or line.startswith("Layer") else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def _draw_unsaved_confirm_dialog(self) -> None:
        title = tr("UI_UNSAVED_CHANGES")
        reason = self.confirm_reason
        labels = [tr("UI_SAVE"), tr("UI_DISCARD"), tr("UI_CANCEL")]
        rendered = []
        for idx, label in enumerate(labels):
            if idx == self.confirm_selection_index:
                rendered.append(f"[{label}]")
            else:
                rendered.append(label)
        buttons_line = "   ".join(rendered)

        lines = [title]
        if reason:
            lines.append(reason)
        lines.append("")
        lines.append(buttons_line)

        dim_color = (0, 0, 0, 140)
        _draw_rectangle_filled(
            self.window.width / 2,
            self.window.height / 2,
            self.window.width,
            self.window.height,
            dim_color,
        )

        width = min(520.0, max(360.0, self.window.width * 0.6))
        height = 140.0 + (len(lines) - 2) * 18.0
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        draw_panel_bg(left, right, bottom, top, color=(0, 0, 0, 220))
        draw_outline_centered((left + right) / 2.0, (top + bottom) / 2.0, width, height, optional_arcade.arcade.color.SKY_BLUE, 2)

        start_x = left + 24.0
        start_y = top - 24.0
        for idx, line in enumerate(lines):
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - idx * 18.0,
                optional_arcade.arcade.color.WHITE,
                14,
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )

    def _draw_quest_context_panel(self) -> None:
        related = self._related_quest_ids(self.selected_entity) if self.selected_entity else set()
        quests = self._quest_definitions()
        lines: List[str] = ["QUEST CONTEXT", "--------------"]
        if not quests:
            lines.append("No quests loaded.")
        else:
            for quest_id, quest in quests.items():
                prefix = "*" if quest_id in related else "-"
                stage_count = len(quest.get("stages") or [])
                lines.append(f"{prefix} {quest_id} ({stage_count} stages)")
                if quest_id in related:
                    title = quest.get("name") or quest.get("title") or ""
                    if title:
                        lines.append(f"    {title}")
        start_x = self.window.width - 320
        start_y = self.window.height - 80
        panel_width = 300
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = optional_arcade.arcade.color.YELLOW if line.startswith("*") else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def _quest_definitions(self) -> Dict[str, Dict[str, Any]]:
        quests: Dict[str, Dict[str, Any]] = {}
        manager = getattr(self.window, "quest_manager", None)
        definitions = getattr(manager, "_definitions", None)
        if isinstance(definitions, dict):
            quests.update(definitions)
        return quests

    def _related_quest_ids(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> set[str]:
        related: set[str] = set()
        if sprite is None:
            return related
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        for behaviour_cfg in config_root.values():
            if not isinstance(behaviour_cfg, dict):
                continue
            quest_id = behaviour_cfg.get("quest_id")
            if isinstance(quest_id, str) and quest_id.strip():
                related.add(quest_id.strip())
        quest_defs = self._quest_definitions()
        for behaviour_cfg in config_root.values():
            if not isinstance(behaviour_cfg, dict):
                continue
            for key in ("require_flags", "set_flags", "clear_flags"):
                flags = behaviour_cfg.get(key)
                if isinstance(flags, dict):
                    for flag in flags.keys():
                        if flag in quest_defs:
                            related.add(flag)
                elif isinstance(flags, list):
                    for flag in flags:
                        if isinstance(flag, str) and flag in quest_defs:
                            related.add(flag)
        return related

    def _handle_path_input(self, key: int, modifiers: int) -> bool:
        if not self.selected_entity:
            return False

        patrol = self._get_patrol_behaviour(self.selected_entity)
        if not patrol:
            return False

        points = self._get_patrol_points(patrol)
        if not points:
            return False

        if self.selected_waypoint_index < 0 or self.selected_waypoint_index >= len(points):
            return False

        # Delete waypoint
        if key == optional_arcade.arcade.key.DELETE:
            self._remove_waypoint(patrol, self.selected_waypoint_index)
            self.selected_waypoint_index = -1
            return True

        # Move waypoint
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

        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            dx *= 4
            dy *= 4

        self._move_waypoint(patrol, self.selected_waypoint_index, dx, dy)
        return True

    def _handle_zone_input(self, key: int, modifiers: int) -> bool:
        if not self.selected_entity:
            return False

        zone = self._get_zone_behaviour(self.selected_entity)
        if not zone:
            return False

        if not (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            return False

        # Resize zone
        dx, dy = 0.0, 0.0
        step = self.grid_size

        if key == optional_arcade.arcade.key.LEFT:
            dx = -step
        elif key == optional_arcade.arcade.key.RIGHT:
            dx = step
        elif key == optional_arcade.arcade.key.UP:
            dy = step
        elif key == optional_arcade.arcade.key.DOWN:
            dy = -step
        else:
            return False

        self._resize_zone(zone, dx, dy)
        return True

    def _shape_field_for_mode(self, mode: str) -> str:
        return "occluder_poly" if mode == "occluder" else "collision_poly"

    def _begin_shape_edit(self, mode: str) -> bool:
        if not self.selected_entity:
            return False
        key = self._shape_field_for_mode(mode)
        entity_data = getattr(self.selected_entity, "mesh_entity_data", None)
        points: List[tuple[float, float]] = []
        if isinstance(entity_data, dict):
            raw = entity_data.get(key)
            if isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    try:
                        points.append((float(entry[0]), float(entry[1])))
                    except Exception:  # noqa: BLE001
                        continue
        self.shape_edit_mode = mode
        self.shape_edit_entity = self.selected_entity
        self.shape_edit_points = list(points)
        self.shape_edit_original = list(points)
        self.shape_drag_index = -1
        # Keep focus on shape editing.
        self.inspector_active = False
        self.palette_active = False
        self.hierarchy_active = False
        return True

    def _cancel_shape_edit(self) -> None:
        self.shape_edit_mode = None
        self.shape_edit_points = []
        self.shape_edit_original = []
        self.shape_edit_entity = None
        self.shape_drag_index = -1

    def _commit_shape_edit(self) -> bool:
        if not self.shape_edit_mode or not self.shape_edit_entity:
            return False
        entity = self.shape_edit_entity
        key = self._shape_field_for_mode(self.shape_edit_mode)
        before = list(self.shape_edit_original)
        after = list(self.shape_edit_points)

        self._set_entity_shape_points(entity, key, after)

        if before != after:
            name = getattr(entity, "mesh_name", "") or getattr(entity, "name", "")
            self._push_command(
                {
                    "type": "EditShape",
                    "entity_name": name,
                    "field": key,
                    "before": [[float(x), float(y)] for x, y in before],
                    "after": [[float(x), float(y)] for x, y in after],
                }
            )
        self._cancel_shape_edit()
        return True

    def _shape_pick_radius_world(self, radius_px: float) -> float:
        zoom = 1.0
        camera_controller = getattr(self.window, "camera_controller", None)
        if camera_controller is not None:
            try:
                zoom = float(getattr(camera_controller, "zoom", 1.0))
            except Exception:  # noqa: BLE001
                zoom = 1.0
        if zoom <= 0.0:
            zoom = 1.0
        return float(radius_px) / zoom

    def _nearest_shape_vertex_index(self, world_x: float, world_y: float, *, radius_px: float = 10.0) -> int:
        if not self.shape_edit_mode or not self.shape_edit_entity:
            return -1
        radius_world = self._shape_pick_radius_world(radius_px)
        radius_sq = radius_world * radius_world
        entity = self.shape_edit_entity
        best_index = -1
        best_dist = radius_sq
        for idx, (px, py) in enumerate(self.shape_edit_points):
            dx = float(world_x) - (float(entity.center_x) + float(px))
            dy = float(world_y) - (float(entity.center_y) + float(py))
            dist = dx * dx + dy * dy
            if dist <= best_dist:
                best_dist = dist
                best_index = idx
        return best_index

    def _set_entity_shape_points(self, entity: optional_arcade.arcade.Sprite, key: str, points: List[tuple[float, float]]) -> None:
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        if points:
            entity_data[key] = [[float(x), float(y)] for x, y in points]
        else:
            entity_data.pop(key, None)

        if key == "collision_poly":
            self.window.scene_controller._apply_collision_poly(entity, entity_data.get(key))

    def _coerce_shape_points(self, raw: Any) -> List[tuple[float, float]]:
        points: List[tuple[float, float]] = []
        if not isinstance(raw, list):
            return points
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            try:
                points.append((float(entry[0]), float(entry[1])))
            except Exception:  # noqa: BLE001
                continue
        return points

    def _shape_payload_for_undo(self, raw: Any) -> list[list[float]] | None:
        if not isinstance(raw, list):
            return None
        points: list[list[float]] = []
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            try:
                points.append([float(entry[0]), float(entry[1])])
            except Exception:  # noqa: BLE001
                continue
        return points

    def _apply_shape_payload(self, entity: optional_arcade.arcade.Sprite, field: str, payload: Any) -> None:
        points = self._coerce_shape_points(payload)
        self._set_entity_shape_points(entity, field, points)

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
        from pathlib import Path

        from .paths import resolve_path  # noqa: PLC0415
        from .prefabs import get_prefab_manager  # noqa: PLC0415

        fallback_used = False
        manager = get_prefab_manager()
        source = manager.prefab_sources.get(prefab_id)
        if not isinstance(source, str) or not source.strip():
            fallback_used = True
            source = "assets/prefabs.json"
        resolved = resolve_path(source)
        if not resolved.exists():
            fallback_used = True
            resolved = resolve_path("assets/prefabs.json")
        return Path(resolved), fallback_used

    def _load_prefab_entries(self, path: "Path") -> list[dict[str, Any]] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"Promote shapes: failed to read {path}: {exc}")
            return None
        if not isinstance(raw, list):
            self.set_status(f"Promote shapes: {path} must contain a JSON list")
            return None
        entries: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                entries.append(item)
        return entries

    def _write_prefab_entries(self, path: "Path", entries: list[dict[str, Any]]) -> None:
        from engine.persistence_io import write_json_atomic  # noqa: PLC0415

        ordered = sorted(entries, key=lambda e: str(e.get("id") or ""))
        write_json_atomic(path, ordered, indent=2, sort_keys=False, trailing_newline=True)

    def _update_prefab_entry(
        self,
        path: "Path",
        prefab_id: str,
        entry_payload: dict[str, Any],
        *,
        status_prefix: str,
    ) -> bool:
        entries = self._load_prefab_entries(path)
        if entries is None:
            return False
        target_index = None
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("id") == prefab_id:
                target_index = idx
                break
        if target_index is None:
            self.set_status(f"{status_prefix}: prefab '{prefab_id}' not found")
            return False
        entries[target_index] = entry_payload
        self._write_prefab_entries(path, entries)
        return True

    def _promote_prefab_shapes(self) -> bool:
        if not self.selected_entity:
            self.set_status("Promote shapes: no selection")
            return False
        entity = self.selected_entity
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            self.set_status("Promote shapes: selected entity has no prefab")
            return False

        try:
            from engine.geometry_tools import sanitize_poly  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            sanitize_poly = None

        shapes_to_promote: dict[str, list[list[float]]] = {}
        for field in ("collision_poly", "occluder_poly"):
            raw = entity_data.get(field)
            if not isinstance(raw, list):
                continue
            if sanitize_poly is not None and not sanitize_poly(raw):
                continue
            points = []
            for entry in raw:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                try:
                    points.append([float(entry[0]), float(entry[1])])
                except Exception:  # noqa: BLE001
                    continue
            if points:
                shapes_to_promote[field] = points

        if not shapes_to_promote:
            self.set_status("Promote shapes: selected entity has no shapes")
            return False

        path, fallback_used = self._resolve_prefab_source_path(prefab_id)
        entries = self._load_prefab_entries(path)
        if entries is None:
            return False

        target_index = None
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("id") == prefab_id:
                target_index = idx
                break
        if target_index is None:
            self.set_status(f"Promote shapes: prefab '{prefab_id}' not found")
            return False

        target_entry = entries[target_index]
        if not isinstance(target_entry, dict):
            self.set_status(f"Promote shapes: prefab '{prefab_id}' not found")
            return False

        before_entry = copy.deepcopy(target_entry)
        entity_block = target_entry.get("entity")
        if not isinstance(entity_block, dict):
            self.set_status(f"Promote shapes: prefab '{prefab_id}' not found")
            return False

        for field, points in shapes_to_promote.items():
            entity_block[field] = copy.deepcopy(points)

        target_entry["entity"] = entity_block
        entries[target_index] = target_entry
        self._write_prefab_entries(path, entries)

        after_entry = copy.deepcopy(target_entry)
        self._push_command(
            {
                "type": "PromotePrefabShapes",
                "prefab_id": prefab_id,
                "source": str(path.as_posix()),
                "before": before_entry,
                "after": after_entry,
            }
        )

        from .prefabs import get_prefab_manager  # noqa: PLC0415

        get_prefab_manager().load(force=True)
        suffix = " (fallback)" if fallback_used else ""
        self.set_status(f"Promote shapes: wrote to {path.as_posix()}{suffix}")
        return True

    def _apply_prefab_shapes(self, *, only_missing: bool) -> bool:
        if not self.selected_entity:
            return False
        entity = self.selected_entity
        entity_data = self.window.scene_controller._ensure_entity_data_dict(entity)
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            action = "Apply" if only_missing else "Reset"
            self.set_status(f"{action} shapes: no prefab on selected entity")
            return False
        try:
            from .prefabs import get_prefab_manager  # noqa: PLC0415

            prefab = get_prefab_manager().get_prefab(prefab_id)
        except Exception as exc:  # noqa: BLE001
            action = "Apply" if only_missing else "Reset"
            self.set_status(f"{action} shapes: prefab '{prefab_id}' not found")
            return False
        if not isinstance(prefab, dict) or not prefab:
            action = "Apply" if only_missing else "Reset"
            self.set_status(f"{action} shapes: prefab '{prefab_id}' not found")
            return False
        prefab_entity = prefab.get("entity", {})
        if not isinstance(prefab_entity, dict):
            action = "Apply" if only_missing else "Reset"
            self.set_status(f"{action} shapes: prefab '{prefab_id}' not found")
            return False

        before = {
            "collision_poly": self._shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._shape_payload_for_undo(entity_data.get("occluder_poly")),
        }

        changed = False
        for field in ("collision_poly", "occluder_poly"):
            prefab_points = self._coerce_shape_points(prefab_entity.get(field))
            has_entity_value = field in entity_data

            if only_missing and has_entity_value:
                continue

            if prefab_points:
                self._set_entity_shape_points(entity, field, prefab_points)
                changed = True
            else:
                if not only_missing and has_entity_value:
                    self._set_entity_shape_points(entity, field, [])
                    changed = True

        after = {
            "collision_poly": self._shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._shape_payload_for_undo(entity_data.get("occluder_poly")),
        }

        if changed and before != after:
            name = getattr(entity, "mesh_name", "") or getattr(entity, "name", "")
            entity_id = entity_data.get("id")
            self._push_command(
                {
                    "type": "EditShapes",
                    "entity_name": name,
                    "entity_id": entity_id,
                    "before": before,
                    "after": after,
                }
            )
            logger.info(
                "[Editor] %s prefab shapes for '%s'",
                "Applied missing" if only_missing else "Reset",
                name or prefab_id,
            )
            return True

        return False

    def _add_shape_point(self, world_x: float, world_y: float) -> bool:
        if not self.shape_edit_mode or not self.shape_edit_entity:
            return False
        entity = self.shape_edit_entity
        local_x = float(world_x) - float(entity.center_x)
        local_y = float(world_y) - float(entity.center_y)
        self.shape_edit_points.append((local_x, local_y))
        return True

    def _update_shape_point(self, world_x: float, world_y: float, modifiers: int) -> bool:
        if not self.shape_edit_mode or not self.shape_edit_entity:
            return False
        if self.shape_drag_index < 0 or self.shape_drag_index >= len(self.shape_edit_points):
            return False
        entity = self.shape_edit_entity
        local_x = float(world_x) - float(entity.center_x)
        local_y = float(world_y) - float(entity.center_y)
        if self.shape_snap_enabled and self.grid_size > 0:
            local_x = round(local_x / self.grid_size) * self.grid_size
            local_y = round(local_y / self.grid_size) * self.grid_size
        old_x, old_y = self.shape_edit_points[self.shape_drag_index]
        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            dx = local_x - old_x
            dy = local_y - old_y
            if abs(dx) >= abs(dy):
                local_y = old_y
            else:
                local_x = old_x
        self.shape_edit_points[self.shape_drag_index] = (local_x, local_y)
        return True

    def _remove_shape_point(self) -> bool:
        if not self.shape_edit_mode:
            return False
        if self.shape_edit_points:
            self.shape_edit_points.pop()
            return True
        return False

    def toggle_shape_edit_mode(self, mode: str) -> bool:
        if self.shape_edit_mode == mode:
            self._cancel_shape_edit()
            return True
        return self._begin_shape_edit(mode)

    def _reset_zone_selection_state(self) -> None:
        self.zone_behaviour_index = 0
        self.zone_edit_target = ZONE_TARGET_TRIGGER

    def _sync_zone_selection_state(self, entity: Optional[optional_arcade.arcade.Sprite]) -> None:
        if not entity:
            return

        behaviours = self._get_zone_behaviours(entity)
        if not behaviours:
            self.zone_behaviour_index = 0
            return

        targeted = self._get_targeted_zone_behaviour(entity, behaviours)
        if targeted:
            return

        # Fallback to the first available behaviour and align the edit target
        self.zone_behaviour_index = 0
        self.zone_edit_target = infer_zone_target_from_behaviour(behaviours[0])

    def _split_zone_behaviours(self, entity: Optional[optional_arcade.arcade.Sprite]) -> tuple[Optional[Any], Optional[Any]]:
        trigger = None
        hitbox = None
        for behaviour in self._get_zone_behaviours(entity):
            if trigger is None and is_trigger_behaviour(behaviour):
                trigger = behaviour
            elif hitbox is None and is_hitbox_behaviour(behaviour):
                hitbox = behaviour

        return trigger, hitbox

    def _get_targeted_zone_behaviour(
        self,
        entity: Optional[optional_arcade.arcade.Sprite],
        behaviours: Optional[List[Any]] = None
    ) -> Optional[Any]:
        if not entity:
            return None

        if behaviours is None:
            behaviours = self._get_zone_behaviours(entity)

        if not behaviours:
            return None

        predicate = is_trigger_behaviour if self.zone_edit_target == ZONE_TARGET_TRIGGER else is_hitbox_behaviour
        for index, behaviour in enumerate(behaviours):
            if predicate(behaviour):
                self.zone_behaviour_index = index
                return behaviour
        return None

    def _toggle_zone_edit_target(self) -> bool:
        if not (self.selected_entity and self.tool_mode == TOOL_MODE_ZONE):
            return False

        trigger, hitbox = self._split_zone_behaviours(self.selected_entity)
        if not (trigger and hitbox):
            return False

        self.zone_edit_target = (
            ZONE_TARGET_HITBOX if self.zone_edit_target == ZONE_TARGET_TRIGGER else ZONE_TARGET_TRIGGER
        )
        self._sync_zone_selection_state(self.selected_entity)
        active = self._get_zone_behaviour(self.selected_entity)
        if active:
            description = describe_zone_behaviour(active)
            logger.info("[Editor] Zone target toggled: %s", description)
        return True

    # --- Helper Methods for Behaviours ---

    def _get_patrol_behaviour(self, entity: optional_arcade.arcade.Sprite) -> Optional[Any]:
        behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for b in behaviours:
            if b.__class__.__name__ == "PatrolBehaviour":
                return b
        return None

    def _get_patrol_points(self, patrol_behaviour) -> list:
        """Helper to get points list safely."""
        if hasattr(patrol_behaviour, 'points'):
            return patrol_behaviour.points
        return []

    def _add_waypoint(self, patrol_behaviour, x: float, y: float):
        """Add a new waypoint to the patrol path."""
        points = self._get_patrol_points(patrol_behaviour)
        old_points = list(points)
        points.append((x, y))

        entity_name = getattr(patrol_behaviour.entity, "mesh_name", "")
        self._update_param_internal("patrol", "points", points, entity_name)
        logger.info("[Editor] Added waypoint at (%s, %s)", x, y)

        self._push_command({
            "type": "ModifyPatrolPath",
            "entity_name": entity_name,
            "before": old_points,
            "after": list(points)
        })

    def _remove_waypoint(self, behaviour: Any, index: int) -> None:
        points = self._get_patrol_points(behaviour)
        old_points = list(points)
        if 0 <= index < len(points):
            removed = points.pop(index)
            entity_name = getattr(behaviour.entity, "mesh_name", "")
            self._update_param_internal("patrol", "points", points, entity_name)
            logger.info("[Editor] Removed waypoint at %s", removed)

            self._push_command({
                "type": "ModifyPatrolPath",
                "entity_name": entity_name,
                "before": old_points,
                "after": list(points)
            })

    def _move_waypoint(self, behaviour: Any, index: int, dx: float, dy: float) -> None:
        points = self._get_patrol_points(behaviour)
        old_points = list(points)
        if 0 <= index < len(points):
            px, py = points[index]
            points[index] = (px + dx, py + dy)
            entity_name = getattr(behaviour.entity, "mesh_name", "")
            self._update_param_internal("patrol", "points", points, entity_name)

            self._push_command({
                "type": "ModifyPatrolPath",
                "entity_name": entity_name,
                "before": old_points,
                "after": list(points)
            })

    def _get_zone_behaviours(self, entity: Optional[optional_arcade.arcade.Sprite]) -> List[Any]:
        if not entity:
            return []

        behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        zone_behaviours: List[Any] = []
        for behaviour in behaviours:
            if is_trigger_behaviour(behaviour) or is_hitbox_behaviour(behaviour):
                zone_behaviours.append(behaviour)
        return zone_behaviours

    def _get_zone_behaviour(self, entity: Optional[optional_arcade.arcade.Sprite]) -> Optional[Any]:
        behaviours = self._get_zone_behaviours(entity)
        if not behaviours:
            return None

        targeted = self._get_targeted_zone_behaviour(entity, behaviours)
        if targeted:
            return targeted

        max_index = len(behaviours) - 1
        self.zone_behaviour_index = max(0, min(self.zone_behaviour_index, max_index))
        chosen = behaviours[self.zone_behaviour_index]
        self.zone_edit_target = infer_zone_target_from_behaviour(chosen)
        return chosen

    def _cycle_zone_behaviour(self) -> bool:
        if not self.selected_entity:
            return False

        behaviours = self._get_zone_behaviours(self.selected_entity)
        if not behaviours:
            logger.info("[Editor] No zone behaviours on selected entity.")
            return False

        if len(behaviours) == 1:
            description = describe_zone_behaviour(behaviours[0])
            self.zone_edit_target = infer_zone_target_from_behaviour(behaviours[0])
            logger.info("[Editor] Single zone target active: %s", description)
            return True

        self.zone_behaviour_index = (self.zone_behaviour_index + 1) % len(behaviours)
        behaviour = behaviours[self.zone_behaviour_index]
        self.zone_edit_target = infer_zone_target_from_behaviour(behaviour)
        description = describe_zone_behaviour(behaviour)
        logger.info(
            "[Editor] Zone target: %s (%s/%s)",
            description,
            self.zone_behaviour_index + 1,
            len(behaviours),
        )
        return True

    def _resize_zone(self, behaviour: Any, dx: float, dy: float) -> None:
        entity_name = getattr(behaviour.entity, "mesh_name", "")

        if is_trigger_behaviour(behaviour):
            # Radius based
            current = getattr(behaviour, "radius", 0.0)
            # Use max of dx/dy to change radius
            delta = dx if abs(dx) > abs(dy) else dy
            new_radius = max(0.0, current + delta)

            behaviour.radius = new_radius
            self._update_param_internal("trigger_zone", "trigger_radius", new_radius, entity_name)
            logger.info("[Editor] Trigger radius: %s", new_radius)

            self._push_command({
                "type": "ResizeZone",
                "entity_name": entity_name,
                "before": current,
                "after": new_radius
            })

        elif is_hitbox_behaviour(behaviour):
            # Width/Height based
            w = getattr(behaviour, "width", 0.0)
            h = getattr(behaviour, "height", 0.0)

            new_w = max(0.0, w + dx)
            new_h = max(0.0, h + dy)

            behaviour.width = new_w
            behaviour.height = new_h
            self._update_param_internal("hitbox", "width", new_w, entity_name)
            self._update_param_internal("hitbox", "height", new_h, entity_name)
            logger.info("[Editor] Hitbox size: %s x %s", new_w, new_h)

            self._push_command({
                "type": "ResizeHitbox",
                "entity_name": entity_name,
                "before": {"width": w, "height": h},
                "after": {"width": new_w, "height": new_h}
            })

    def _update_behaviour_config(self, behaviour: Any, param_name: str, value: Any) -> None:
        # Similar to _update_param but takes behaviour instance
        if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
            behaviour.config[param_name] = value

        # Also need to update the entity data for saving
        behaviour_name = getattr(behaviour, "mesh_behaviour_type", None)
        if behaviour_name:
            self._update_param(behaviour_name, param_name, value)

    def undo_last(self) -> None:
        editor_ops.undo_last(self)

    def redo_last(self) -> None:
        editor_ops.redo_last(self)

    def _push_command(self, cmd: Dict[str, Any]) -> None:
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
        """Return True if the action is blocked by the confirm dialog."""
        if not self.active:
            return False
        if not self.dirty_state.is_dirty:
            return False
        if self._confirm_bypass:
            return False
        if self.confirm_open:
            return True
        self.confirm_open = True
        self.confirm_reason = str(reason or "").strip()
        self.confirm_selection_index = 0
        self.pending_action = action
        return True

    def _close_unsaved_confirm(self, *, clear_pending: bool = False) -> None:
        self.confirm_open = False
        self.confirm_reason = ""
        self.confirm_selection_index = 0
        if clear_pending:
            self.pending_action = None

    def _run_pending_confirm_action(self) -> None:
        action = self.pending_action
        if action is None:
            return
        self.pending_action = None
        self._confirm_bypass = True
        try:
            action()
        finally:
            self._confirm_bypass = False

    def _apply_unsaved_confirm_choice(self, choice_index: int) -> None:
        if choice_index == 0:
            self.save_current_scene()
            self._close_unsaved_confirm()
            self._run_pending_confirm_action()
            return
        if choice_index == 1:
            self._mark_clean()
            self._close_unsaved_confirm()
            self._run_pending_confirm_action()
            return
        self._close_unsaved_confirm(clear_pending=True)

    def _handle_unsaved_confirm_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.confirm_open:
            return False

        if key == optional_arcade.arcade.key.LEFT:
            self.confirm_selection_index = max(0, self.confirm_selection_index - 1)
            return True
        if key == optional_arcade.arcade.key.RIGHT:
            self.confirm_selection_index = min(2, self.confirm_selection_index + 1)
            return True
        if key in (
            optional_arcade.arcade.key.ENTER,
            optional_arcade.arcade.key.RETURN,
            optional_arcade.arcade.key.SPACE,
            optional_arcade.arcade.key.A,
        ):
            self._apply_unsaved_confirm_choice(self.confirm_selection_index)
            return True
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.B):
            self._apply_unsaved_confirm_choice(2)
            return True

        return True

    def _find_entity_by_name(self, name: str) -> Optional[optional_arcade.arcade.Sprite]:
        for sprite in self.window.scene_controller.all_sprites:
            if getattr(sprite, "mesh_name", "") == name:
                return sprite
        return None

    def _find_entity_by_id(self, entity_id: str) -> Optional[optional_arcade.arcade.Sprite]:
        for sprite in self.window.scene_controller.all_sprites:
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict) and data.get("id") == entity_id:
                return sprite
        return None

    def _apply_rotate_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a RotateEntities command."""
        rotates = cmd.get("rotates", [])
        key = "start_rot_deg" if use_before else "end_rot_deg"
        for item in rotates:
            eid = item.get("entity_id")
            rot = item.get(key)
            if eid is None or rot is None:
                continue
            entity = self._find_entity_by_id(eid)
            if entity:
                entity.angle = rot

    def _apply_scale_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a ScaleEntities command."""
        scales = cmd.get("scales", [])
        key = "start_scale" if use_before else "end_scale"
        for item in scales:
            eid = item.get("entity_id")
            sc = item.get(key)
            if eid is None or sc is None:
                continue
            entity = self._find_entity_by_id(eid)
            if entity:
                entity.scale = sc

    def _revert_command(self, cmd: Dict[str, Any]) -> None:
        ctype = cmd["type"]
        entity_name = cmd.get("entity_name")

        if ctype == "MoveEntity":
            entity = self._find_entity_by_name(entity_name)
            if entity:
                self.window.scene_controller._apply_entity_mutation(entity, x=cmd["before"]["x"], y=cmd["before"]["y"])

        elif ctype == "RotateEntities":
            self._apply_rotate_entities_cmd(cmd, use_before=True)

        elif ctype == "ScaleEntities":
            self._apply_scale_entities_cmd(cmd, use_before=True)

        elif ctype == "ChangeProperty":
            self._update_param_internal(cmd["behaviour"], cmd["param"], cmd["before"], entity_name)

        elif ctype == "AddEntity":
            entity = self._find_entity_by_name(entity_name)
            if entity:
                self._delete_entity_internal(entity)

        elif ctype == "DeleteEntity":
            self._create_entity_internal(cmd["data"])

        elif ctype == "ModifyPatrolPath":
             self._update_param_internal("patrol", "points", cmd["before"], entity_name)

        elif ctype == "ResizeZone":
             self._update_param_internal("trigger_zone", "trigger_radius", cmd["before"], entity_name)

        elif ctype == "ResizeHitbox":
             self._update_param_internal("hitbox", "width", cmd["before"]["width"], entity_name)
             self._update_param_internal("hitbox", "height", cmd["before"]["height"], entity_name)

        elif ctype == "EditShape":
            field = cmd.get("field")
            if isinstance(field, str):
                entity = self._find_entity_by_name(entity_name)
                if entity:
                    before = cmd.get("before") or []
                    self._apply_shape_payload(entity, field, before)

        elif ctype == "EditShapes":
            entity_id = cmd.get("entity_id")
            entity = None
            if isinstance(entity_id, str) and entity_id:
                entity = self._find_entity_by_id(entity_id)
            if entity is None:
                entity = self._find_entity_by_name(entity_name)
            if not entity:
                logger.debug("[Editor] EditShapes undo skipped; entity not found (id=%s name=%s)", entity_id, entity_name)
            else:
                before = cmd.get("before", {})
                if isinstance(before, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in before:
                            self._apply_shape_payload(entity, field, before.get(field))

        elif ctype == "ResetPrefabOverride":
            behaviour_name = cmd.get("behaviour")
            param_name = cmd.get("param")
            before = cmd.get("before")
            if isinstance(behaviour_name, str) and isinstance(param_name, str):
                self._update_param_internal(behaviour_name, param_name, before, entity_name)

        elif ctype == "ResetPrefabOverrides":
            entity = self._find_entity_by_name(entity_name) if entity_name else None
            before_cfg = cmd.get("before")
            if entity and isinstance(before_cfg, dict):
                self._apply_behaviour_config_map(entity, before_cfg)
                before_shapes = cmd.get("before_shapes")
                if isinstance(before_shapes, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in before_shapes:
                            self._apply_shape_payload(entity, field, before_shapes.get(field))
                if self.selected_entity is entity:
                    self._refresh_inspector_items()

        elif ctype == "PromotePrefabShapes":
            prefab_id = cmd.get("prefab_id")
            source = cmd.get("source")
            before = cmd.get("before")
            if not isinstance(prefab_id, str) or not isinstance(source, str) or not isinstance(before, dict):
                return
            from pathlib import Path

            path = Path(source)
            if not path.exists():
                self.set_status(f"Promote shapes undo: source missing for '{prefab_id}'")
                return
            ok = self._update_prefab_entry(path, prefab_id, before, status_prefix="Promote shapes undo")
            if ok:
                from .prefabs import get_prefab_manager  # noqa: PLC0415

                get_prefab_manager().load(force=True)

        elif ctype == "RenameEntity":
            entity = None
            for key in (cmd.get("current_name"), cmd.get("after"), cmd.get("before")):
                if isinstance(key, str) and key:
                    entity = self._find_entity_by_name(key)
                    if entity:
                        break
            if entity:
                self._apply_entity_rename(entity, cmd.get("before", ""))
                cmd["current_name"] = cmd.get("before", "")
                if self.selected_entity is entity:
                    self._refresh_inspector_items()
                self._refresh_hierarchy_list()

        elif ctype == "EditAnimation":
            entity = self._find_entity_by_name(entity_name) or self.selected_entity
            if entity:
                self._set_animator_config(entity, copy.deepcopy(cmd.get("before", {})))
                self._refresh_animation_cache()

        elif ctype == "EditDialogue":
            self._update_param_internal("Dialogue", "dialogue", copy.deepcopy(cmd.get("before", {})), entity_name)

        elif ctype == "PaintTile":
            layer = cmd.get("layer")
            col = cmd.get("col")
            row = cmd.get("row")
            before = cmd.get("before")
            if layer is not None and before is not None and col is not None and row is not None:
                self.window.scene_controller.set_tile(str(layer), int(col), int(row), int(before))

        elif ctype == "AddLight":
            index = cmd.get("index", 0)
            lights = self._get_scene_lights()
            if 0 <= index < len(lights):
                lights.pop(index)
            self._sync_lighting_runtime()
            if self.lights_selection is not None and self.lights_selection == index:
                self.lights_selection = None

        elif ctype == "MoveLight":
            index = cmd.get("index")
            from_pos = cmd.get("from")
            if index is not None and from_pos:
                lights = self._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index]["x"], lights[index]["y"] = from_pos
                    self._sync_lighting_runtime()

        elif ctype == "EditLight":
            index = cmd.get("index")
            field = cmd.get("field")
            value = cmd.get("before")
            if index is not None and field is not None:
                lights = self._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index][field] = value
                    self._sync_lighting_runtime()

        elif ctype == "DeleteLight":
            index = cmd.get("index", 0)
            light = cmd.get("light")
            lights = self._get_scene_lights()
            if light is not None:
                lights.insert(index, light)
                self._sync_lighting_runtime()

        elif ctype == "EditOccluder":
            raw_cmd = cmd.get("cmd")
            if isinstance(raw_cmd, dict):
                scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if hasattr(self.window, "scene_controller"):
                        self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
                inverse = invert_occluder_command(raw_cmd)
                apply_occluder_command(scene, {"kind": inverse.kind, "payload": inverse.payload})
                self._sync_occluders_runtime()

        elif ctype == "AltDragDuplicate":
            self._revert_alt_drag_duplicate_cmd(cmd)

    def _apply_command(self, cmd: Dict[str, Any]) -> None:
        ctype = cmd["type"]
        entity_name = cmd.get("entity_name")

        if ctype == "MoveEntity":
            entity = self._find_entity_by_name(entity_name)
            if entity:
                self.window.scene_controller._apply_entity_mutation(entity, x=cmd["after"]["x"], y=cmd["after"]["y"])

        elif ctype == "RotateEntities":
            self._apply_rotate_entities_cmd(cmd, use_before=False)

        elif ctype == "ScaleEntities":
            self._apply_scale_entities_cmd(cmd, use_before=False)

        elif ctype == "ChangeProperty":
            self._update_param_internal(cmd["behaviour"], cmd["param"], cmd["after"], entity_name)

        elif ctype == "AddEntity":
            self._create_entity_internal(cmd["data"])

        elif ctype == "DeleteEntity":
            entity = self._find_entity_by_name(entity_name)
            if entity:
                self._delete_entity_internal(entity)

        elif ctype == "ModifyPatrolPath":
             self._update_param_internal("patrol", "points", cmd["after"], entity_name)

        elif ctype == "ResizeZone":
             self._update_param_internal("trigger_zone", "trigger_radius", cmd["after"], entity_name)

        elif ctype == "ResizeHitbox":
             self._update_param_internal("hitbox", "width", cmd["after"]["width"], entity_name)
             self._update_param_internal("hitbox", "height", cmd["after"]["height"], entity_name)

        elif ctype == "EditShape":
            field = cmd.get("field")
            if isinstance(field, str):
                entity = self._find_entity_by_name(entity_name)
                if entity:
                    after = cmd.get("after") or []
                    self._apply_shape_payload(entity, field, after)

        elif ctype == "EditShapes":
            entity_id = cmd.get("entity_id")
            entity = None
            if isinstance(entity_id, str) and entity_id:
                entity = self._find_entity_by_id(entity_id)
            if entity is None:
                entity = self._find_entity_by_name(entity_name)
            if not entity:
                logger.debug("[Editor] EditShapes redo skipped; entity not found (id=%s name=%s)", entity_id, entity_name)
            else:
                after = cmd.get("after", {})
                if isinstance(after, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in after:
                            self._apply_shape_payload(entity, field, after.get(field))

        elif ctype == "ResetPrefabOverride":
            behaviour_name = cmd.get("behaviour")
            param_name = cmd.get("param")
            base_missing = bool(cmd.get("base_missing"))
            if isinstance(behaviour_name, str) and isinstance(param_name, str):
                if base_missing:
                    self._remove_param_internal(behaviour_name, param_name, entity_name)
                else:
                    self._update_param_internal(behaviour_name, param_name, cmd.get("after"), entity_name)

        elif ctype == "ResetPrefabOverrides":
            entity = self._find_entity_by_name(entity_name) if entity_name else None
            after_cfg = cmd.get("after")
            if entity and isinstance(after_cfg, dict):
                self._apply_behaviour_config_map(entity, after_cfg)
                after_shapes = cmd.get("after_shapes")
                if isinstance(after_shapes, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in after_shapes:
                            self._apply_shape_payload(entity, field, after_shapes.get(field))
                if self.selected_entity is entity:
                    self._refresh_inspector_items()

        elif ctype == "PromotePrefabShapes":
            prefab_id = cmd.get("prefab_id")
            source = cmd.get("source")
            after = cmd.get("after")
            if not isinstance(prefab_id, str) or not isinstance(source, str) or not isinstance(after, dict):
                return
            from pathlib import Path

            path = Path(source)
            if not path.exists():
                self.set_status(f"Promote shapes redo: source missing for '{prefab_id}'")
                return
            ok = self._update_prefab_entry(path, prefab_id, after, status_prefix="Promote shapes redo")
            if ok:
                from .prefabs import get_prefab_manager  # noqa: PLC0415

                get_prefab_manager().load(force=True)

        elif ctype == "RenameEntity":
            entity = None
            for key in (cmd.get("current_name"), cmd.get("before"), cmd.get("after")):
                if isinstance(key, str) and key:
                    entity = self._find_entity_by_name(key)
                    if entity:
                        break
            if entity:
                self._apply_entity_rename(entity, cmd.get("after", ""))
                cmd["current_name"] = cmd.get("after", "")
                if self.selected_entity is entity:
                    self._refresh_inspector_items()
                self._refresh_hierarchy_list()

        elif ctype == "EditAnimation":
            entity = self._find_entity_by_name(entity_name) or self.selected_entity
            if entity:
                self._set_animator_config(entity, copy.deepcopy(cmd.get("after", {})))
                self._refresh_animation_cache()

        elif ctype == "EditDialogue":
            self._update_param_internal("Dialogue", "dialogue", copy.deepcopy(cmd.get("after", {})), entity_name)

        elif ctype == "PaintTile":
            layer = cmd.get("layer")
            col = cmd.get("col")
            row = cmd.get("row")
            after = cmd.get("after")
            if layer is not None and after is not None and col is not None and row is not None:
                self.window.scene_controller.set_tile(str(layer), int(col), int(row), int(after))

        elif ctype == "AddLight":
            index = cmd.get("index", 0)
            light = cmd.get("light", {})
            lights = self._get_scene_lights()
            lights.insert(index, copy.deepcopy(light))
            self._sync_lighting_runtime()
            self.lights_selection = index

        elif ctype == "MoveLight":
            index = cmd.get("index")
            to_pos = cmd.get("to")
            if index is not None and to_pos:
                lights = self._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index]["x"], lights[index]["y"] = to_pos
                    self._sync_lighting_runtime()

        elif ctype == "EditLight":
            index = cmd.get("index")
            field = cmd.get("field")
            value = cmd.get("after")
            if index is not None and field is not None:
                lights = self._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index][field] = value
                    self._sync_lighting_runtime()

        elif ctype == "DeleteLight":
            index = cmd.get("index", 0)
            lights = self._get_scene_lights()
            if 0 <= index < len(lights):
                lights.pop(index)
                self._sync_lighting_runtime()

        elif ctype == "EditOccluder":
            raw_cmd = cmd.get("cmd")
            if isinstance(raw_cmd, dict):
                scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if hasattr(self.window, "scene_controller"):
                        self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
                apply_occluder_command(scene, raw_cmd)
                self._sync_occluders_runtime()

        elif ctype == "AltDragDuplicate":
            self._apply_alt_drag_duplicate_cmd(cmd)

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
        """Apply an alt-drag duplicate command (redo)."""
        from .editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            AltDragDuplicateCommand,
            apply_alt_drag_duplicate,
        )

        alt_cmd = AltDragDuplicateCommand.from_dict(cmd)

        # Apply to scene data
        sc = getattr(self.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                new_scene = apply_alt_drag_duplicate(scene_data, alt_cmd)
                sc._loaded_scene_data = new_scene

                # Create sprites for duplicated entities
                entities = new_scene.get("entities", [])
                for spec in alt_cmd.specs:
                    # Find the new entity data
                    for entity in entities:
                        eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                        if eid == spec.new_id:
                            self._create_entity_internal(entity)
                            break

    def _create_entity_internal(self, entity_def: Dict[str, Any]) -> Optional[optional_arcade.arcade.Sprite]:
        sprite = self.window.scene_controller._create_sprite(entity_def)
        if sprite:
            layer_name = entity_def.get("layer", "entities")
            self.window.scene_controller.add_sprite_to_layer(sprite, layer_name)
        return sprite

    def _delete_entity_internal(self, sprite: optional_arcade.arcade.Sprite) -> None:
        # Remove from layers
        for layer in self.window.scene_controller.layers.values():
            if sprite in layer:
                layer.remove(sprite)

        # Remove from solids if present
        if sprite in self.window.scene_controller.solid_sprites:
            self.window.scene_controller.solid_sprites.remove(sprite)

        if self.selected_entity == sprite:
            self.selected_entity = None
            self.inspector_active = False
            self._reset_zone_selection_state()
            self._cancel_hierarchy_rename()

    def toggle_hierarchy(self) -> None:
        if not self.active:
            return
        self.hierarchy_active = not self.hierarchy_active
        if self.hierarchy_active:
            self.inspector_active = False
            self.palette_active = False
            self.palette_filter_active = False
            self._refresh_hierarchy_list()
            # Try to find selected entity in list
            if self.selected_entity:
                try:
                    self.hierarchy_selection_index = self._cached_hierarchy_list.index(self.selected_entity)
                except ValueError:
                    self.hierarchy_selection_index = 0 if self._cached_hierarchy_list else -1
            elif not self._cached_hierarchy_list:
                self.hierarchy_selection_index = -1
            logger.info("[Editor] Hierarchy OPEN")
        else:
            self.hierarchy_filter_active = False
            self._cancel_hierarchy_rename()
            logger.info("[Editor] Hierarchy CLOSED")

    def toggle_entity_panels(self) -> bool:
        if not self.active:
            return False
        self.entity_panels_active = not self.entity_panels_active
        if self.entity_panels_active:
            self.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
            self.entity_panels_filter_active = False
            self.entity_panels_text_edit_active = False
            self.entity_panels_text_field = None
            self.entity_panels_text_buffer = ""
            self._entity_panels_selected_id = self._entity_panels_selected_id_value()
            self._refresh_entity_panels_list(sync_selected=True)
            logger.info("[Editor] Entity panels OPEN")
        else:
            self.entity_panels_filter_active = False
            self.entity_panels_text_edit_active = False
            self.entity_panels_text_field = None
            self.entity_panels_text_buffer = ""
            if self._search_focus == "outliner":
                self.clear_search_focus()
            logger.info("[Editor] Entity panels CLOSED")
        self._autosave_workspace()
        return self.entity_panels_active

    def toggle_scene_switcher(self) -> bool:
        if not self.active:
            return False
        self.scene_switcher_active = not self.scene_switcher_active
        if self.scene_switcher_active:
            self.scene_browser_active = False
            self.scene_switcher_query = ""
            self.scene_switcher_index = 0
            self._refresh_scene_switcher_items()
            logger.info("[Editor] Scene switcher OPEN")
        else:
            self.scene_switcher_query = ""
            self.scene_switcher_index = 0
            logger.info("[Editor] Scene switcher CLOSED")
        self._autosave_workspace()
        return self.scene_switcher_active

    def toggle_scene_browser(self) -> bool:
        if not self.active:
            return False
        self.scene_browser_active = not self.scene_browser_active
        if self.scene_browser_active:
            self.scene_switcher_active = False
            self.scene_browser_query = ""
            self.scene_browser_index = 0
            self._refresh_scene_browser_rows()
            logger.info("[Editor] Scene browser OPEN")
        else:
            self.scene_browser_query = ""
            self.scene_browser_index = 0
            logger.info("[Editor] Scene browser CLOSED")
        self._autosave_workspace()
        return self.scene_browser_active

    def toggle_command_palette(self) -> bool:
        if not self.active:
            return False
        self.command_palette_active = not self.command_palette_active
        if self.command_palette_active:
            self.command_palette_query = ""
            self.command_palette_index = 0
            # Close other overlays potentially?
        else:
            self.command_palette_query = ""
            self.command_palette_index = 0
        self._autosave_workspace()
        return self.command_palette_active

    def toggle_asset_browser(self) -> bool:
        if not self.active:
            return False
        self.asset_browser_active = not self.asset_browser_active
        if self.asset_browser_active:
            # Close conflicting overlays
            self.scene_switcher_active = False
            self.scene_browser_active = False
            self.command_palette_active = False
            
            self.refresh_asset_browser()
            logger.info("[Editor] Asset browser OPEN")
        else:
            if self._search_focus == "assets":
                self.clear_search_focus()
            logger.info("[Editor] Asset browser CLOSED")
        self._autosave_workspace()
        return self.asset_browser_active

    def set_dock_tab(self, dock: str, tab: str) -> bool:
        """Switch the active tab in a dock panel.

        Args:
            dock: "left" or "right"
            tab: Tab name ("Scene", "Outliner", "Inspector", "Assets", "History")

        Returns:
            True if switch was successful.
        """
        if not self.active:
            return False

        # Close any open menus/context menus
        self._menu_active = None
        self._context_menu_open = False

        if dock == "left":
            if tab not in ("Scene", "Outliner"):
                return False
            if self._left_dock_tab == tab:
                return False  # Already active
            self._left_dock_tab = tab

            # Route visibility based on new tab
            if tab == "Scene":
                self.scene_browser_active = True
                # entity_panels_active can stay True but Scene tab takes priority
            elif tab == "Outliner":
                self.entity_panels_active = True
                self.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
                self._entity_panels_selected_id = self._entity_panels_selected_id_value()
                self._refresh_entity_panels_list(sync_selected=True)

            logger.info("[Editor] Left dock tab switched to %s", tab)
            self._sync_search_focus()
            self._autosave_workspace()
            return True

        elif dock == "right":
            if tab not in ("Inspector", "Assets", "History"):
                return False
            if self._right_dock_tab == tab:
                return False  # Already active
            self._right_dock_tab = tab

            # Route visibility based on new tab
            if tab == "Inspector":
                self.entity_panels_active = True
                self.entity_panels_focus = ENTITY_PANEL_FOCUS_INSPECTOR
            elif tab == "Assets":
                self.asset_browser_active = True
                self.refresh_asset_browser()
            elif tab == "History":
                entries = self.get_undo_history_entries()
                current = self._history_current_index(entries)
                if current >= 0:
                    self._history_cursor_index = current

            logger.info("[Editor] Right dock tab switched to %s", tab)
            self._sync_search_focus()
            self._autosave_workspace()
            return True

        return False

    def begin_dock_drag(self, which: str, mouse_x: float) -> bool:
        """Begin dragging a dock splitter.

        Args:
            which: "left" or "right"
            mouse_x: Current mouse x position.

        Returns:
            True if drag started successfully.
        """
        if not self.active:
            return False
        if which not in ("left", "right"):
            return False

        self._dock_drag_active = which
        self._dock_drag_start_x = mouse_x
        self._dock_drag_start_w = self._dock_left_w if which == "left" else self._dock_right_w

        # Close any open menus/context menus
        self._menu_active = None
        self._context_menu_open = False

        logger.info("[Editor] Begin dock drag: %s", which)
        return True

    def update_dock_drag(self, mouse_x: float, window_width: int) -> bool:
        """Update dock width during drag.

        Args:
            mouse_x: Current mouse x position.
            window_width: Window width for clamping.

        Returns:
            True if drag was updated.
        """
        if self._dock_drag_active is None:
            return False

        from .editor.editor_shell_layout import clamp_dock_width  # noqa: PLC0415

        delta = mouse_x - self._dock_drag_start_x

        if self._dock_drag_active == "left":
            # Dragging left splitter: moving right increases left dock width
            new_w = int(self._dock_drag_start_w + delta)
            other_w = self._dock_right_w
            clamped = clamp_dock_width(new_w, window_width, other_w)
            if clamped != self._dock_left_w:
                self._dock_left_w = clamped
                return True
        else:
            # Dragging right splitter: moving left increases right dock width
            new_w = int(self._dock_drag_start_w - delta)
            other_w = self._dock_left_w
            clamped = clamp_dock_width(new_w, window_width, other_w)
            if clamped != self._dock_right_w:
                self._dock_right_w = clamped
                return True

        return False

    def end_dock_drag(self) -> bool:
        """End dock drag and save workspace.

        Returns:
            True if drag was active and ended.
        """
        if self._dock_drag_active is None:
            return False

        logger.info("[Editor] End dock drag: %s, left_w=%d, right_w=%d",
                    self._dock_drag_active, self._dock_left_w, self._dock_right_w)

        self._dock_drag_active = None
        self._dock_drag_start_x = 0.0
        self._dock_drag_start_w = 0

        # Save workspace with new dock widths
        self._autosave_workspace()
        return True

    def refresh_asset_browser(self) -> None:
        self._asset_browser_cached_rows = scan_assets(get_repo_root())
        self._filter_asset_browser()

    def set_asset_browser_filter(self, text: str) -> None:
        if self._assets_search != text:
            self._assets_search = text
        if self.asset_browser_filter == text:
            return
        self.asset_browser_filter = text
        self._filter_asset_browser()
        self._autosave_workspace()

    def cycle_asset_browser_kind(self) -> None:
        self.asset_browser_kind = _cycle_asset_browser_kind_impl(self.asset_browser_kind)
        self._filter_asset_browser()
        self._autosave_workspace()

    def _filter_asset_browser(self) -> None:
        self._asset_browser_filtered_rows = _filter_assets_for_browser_impl(
            self._asset_browser_cached_rows,
            self.asset_browser_filter,
            self.asset_browser_kind
        )
        self.asset_browser_selection_index = _clamp_asset_selection_index_impl(
            self.asset_browser_selection_index,
            len(self._asset_browser_filtered_rows)
        )

    def asset_browser_move_selection(self, delta: int) -> None:
        count = len(self._asset_browser_filtered_rows)
        self.asset_browser_selection_index = _move_asset_selection_impl(
            self.asset_browser_selection_index, delta, count
        )

    def _handle_asset_browser_input(self, key: int, modifiers: int) -> bool:
        if key == optional_arcade.arcade.key.ESCAPE:
            self.toggle_asset_browser()
            return True
        if self._search_focus == "assets":
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.backspace_search_text()
                return True
        if key == optional_arcade.arcade.key.TAB:
            self.cycle_asset_browser_kind()
            return True
        if key == optional_arcade.arcade.key.UP:
            self.asset_browser_move_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.asset_browser_move_selection(1)
            return True
        if key == optional_arcade.arcade.key.PAGE_UP:
            self.asset_browser_move_selection(-10)
            return True
        if key == optional_arcade.arcade.key.PAGE_DOWN:
            self.asset_browser_move_selection(10)
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
             return True
        if key == optional_arcade.arcade.key.ENTER:
            self._activate_selected_asset()
            return True
        return True

    def _activate_selected_asset(self) -> None:
        if not self._asset_browser_filtered_rows:
            return

        idx = _clamp_asset_selection_index_impl(
            self.asset_browser_selection_index,
            len(self._asset_browser_filtered_rows)
        )
        if idx < 0 or idx >= len(self._asset_browser_filtered_rows):
            return

        row = self._asset_browser_filtered_rows[idx]
        intent = _resolve_asset_activation_impl(row)

        hud = getattr(self.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud else None

        if intent["kind"] == "spawn_entity":
            # Enter placement mode
            self.asset_place_active = True
            self.asset_place_path = intent["asset_path"]
            self.asset_place_kind = row.kind
            self.asset_browser_active = False

            if callable(toaster):
                toaster(f"Placement Mode: {row.display_name}")
        else:
            # Copy path (mock)
            if callable(toaster):
                toaster(f"Copied: {intent['asset_path']}")

    def place_asset_at(self, x: float, y: float) -> None:
        if not self.asset_place_active or not self.asset_place_path:
            return
            
        # Snap logic (duplicated from draw or centralized? Centralized usage of imported function)
        if self.snap_enabled:
            x, y = snap_world_point((x, y), self.snap_mode, self.grid_size)

        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller:
            scene_data = getattr(scene_controller, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                spawn_entity_from_asset(scene_data, self.asset_place_path, (x, y))
                self.scene_dirty = True
                if hasattr(scene_controller, "reload_scene"):
                    scene_controller.reload_scene()




    def record_recent_scene(self, scene_path: str) -> None:
        normalized = normalize_scene_path(scene_path)
        if not normalized:
            return
        recent = [path for path in self.scene_switcher_recent if path != normalized]
        recent.insert(0, normalized)
        self.scene_switcher_recent = recent[:SCENE_SWITCHER_RECENT_LIMIT]

    def _refresh_scene_switcher_items(self) -> None:
        from .scene_index import list_pack_scene_options  # noqa: PLC0415

        self._scene_switcher_cached = list_pack_scene_options()

    def _scene_switcher_all_options(self) -> list[tuple[str, str]]:
        if not self._scene_switcher_cached:
            self._refresh_scene_switcher_items()
        return list(self._scene_switcher_cached)

    def _scene_switcher_visible_options(self) -> list[tuple[str, str]]:
        options = self._scene_switcher_all_options()
        return _build_scene_switcher_rows_impl(
            options,
            self.scene_switcher_query,
            self.scene_switcher_recent,
        )

    def _scene_switcher_clamp_index(self, count: int) -> None:
        self.scene_switcher_index = _clamp_scene_selection_index_impl(
            self.scene_switcher_index, count
        )

    def _scene_switcher_lines(self) -> list[str]:
        options = self._scene_switcher_visible_options()
        self._scene_switcher_clamp_index(len(options))
        return _build_scene_switcher_lines_impl(
            self.scene_switcher_active,
            self.scene_switcher_query,
            options,
            self.scene_switcher_index,
            self.scene_switcher_recent,
        )

    def _refresh_scene_browser_rows(self) -> None:
        from .scene_index import build_scene_rows  # noqa: PLC0415

        self._scene_browser_cached_rows = build_scene_rows(self.scene_browser_query, self.scene_switcher_recent)

    def _scene_browser_rows(self) -> list["SceneRow"]:
        if not self._scene_browser_cached_rows:
            self._refresh_scene_browser_rows()
        return list(self._scene_browser_cached_rows)

    def _scene_browser_clamp_index(self, count: int) -> None:
        self.scene_browser_index = _clamp_scene_selection_index_impl(
            self.scene_browser_index, count
        )

    def _scene_browser_window(self, count: int) -> tuple[int, int]:
        return _compute_scene_window_impl(self.scene_browser_index, count)

    def _scene_browser_layout(self, count: int) -> dict[str, float]:
        return _compute_scene_browser_layout_impl(
            float(self.window.width),
            float(self.window.height),
            count,
        )

    def _scene_browser_lines(self) -> list[str]:
        rows = self._scene_browser_rows()
        self._scene_browser_clamp_index(len(rows))
        return _build_scene_browser_lines_impl(
            self.scene_browser_active,
            self.scene_browser_query,
            rows,
            self.scene_browser_index,
        )

    def _open_scene_by_id(self, scene_id: str) -> bool:
        normalized = normalize_scene_path(scene_id)
        if not normalized:
            return False

        def _apply() -> None:
            self.scene_switcher_active = False
            self.scene_browser_active = False
            requester = getattr(self.window, "request_scene_change", None)
            if callable(requester):
                requester(normalized)
            else:
                controller = getattr(self.window, "scene_controller", None)
                change = getattr(controller, "request_scene_change", None) if controller is not None else None
                if callable(change):
                    change(normalized)
            self.record_recent_scene(normalized)

        if self.confirm_unsaved_changes("Switch Scene", _apply):
            return False
        _apply()
        return True

    def _scene_switcher_open_selected(self) -> bool:
        options = self._scene_switcher_visible_options()
        if not options:
            return False
        self._scene_switcher_clamp_index(len(options))
        if self.scene_switcher_index < 0:
            return False
        path, _label = options[self.scene_switcher_index]
        return self._open_scene_by_id(path)

    def _scene_browser_open_selected(self) -> bool:
        rows = self._scene_browser_rows()
        if not rows:
            return False
        self._scene_browser_clamp_index(len(rows))
        if self.scene_browser_index < 0:
            return False
        row = rows[self.scene_browser_index]
        return self._open_scene_by_id(row.scene_id)

    def _scene_browser_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        if not self.scene_browser_active:
            return False
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        rows = self._scene_browser_rows()
        if not rows:
            return True
        layout = self._scene_browser_layout(len(rows))
        start_idx, end_idx = self._scene_browser_window(len(rows))
        visible = end_idx - start_idx
        
        hit_index = _compute_scene_browser_hit_index_impl(
            x, y, layout, start_idx, visible
        )
        if hit_index is not None:
            self.scene_browser_index = hit_index
            self._scene_browser_open_selected()
        return True

    # -------------------------------------------------------------------------
    # Undo History Panel
    # -------------------------------------------------------------------------

    def get_undo_history_entries(self) -> list[Any]:
        from engine.editor.undo_history_model import build_undo_history_entries  # noqa: PLC0415

        entries = build_undo_history_entries(self.undo_stack, self.redo_stack)
        self._history_cursor_index = self._clamp_history_cursor(self._history_cursor_index, len(entries))
        return entries

    def get_filtered_undo_history_entries(self) -> list[Any]:
        from engine.editor.undo_history_model import filter_undo_history_entries  # noqa: PLC0415

        entries = self.get_undo_history_entries()
        filtered = filter_undo_history_entries(entries, self._history_search)
        if filtered:
            if not any(entry.real_index == self._history_cursor_index for entry in filtered):
                self._history_cursor_index = filtered[0].real_index
        return filtered

    def _history_input_blocked(self) -> bool:
        from engine.editor_tooltips_model import (  # noqa: PLC0415
            _is_modal_open_state,
            _is_text_input_active_state,
        )

        if getattr(self, "confirm_open", False):
            return True
        if self._search_focus == "history":
            return _is_modal_open_state(self)
        return _is_text_input_active_state(self) or _is_modal_open_state(self)

    def _clamp_history_cursor(self, cursor: int, count: int) -> int:
        from engine.editor.undo_history_model import clamp_history_cursor  # noqa: PLC0415

        return clamp_history_cursor(cursor, count)

    def _history_current_index(self, entries: list[Any]) -> int:
        for i, entry in enumerate(entries):
            if getattr(entry, "is_current", False):
                return int(getattr(entry, "real_index", i))
        return -1

    def _history_display_index(self, entries: list[Any]) -> int:
        if not entries:
            return 0
        for i, entry in enumerate(entries):
            if getattr(entry, "real_index", None) == self._history_cursor_index:
                return i
        return 0

    def _jump_by_delta(self, delta: int) -> None:
        if delta == 0:
            return
        if delta < 0:
            for _ in range(abs(delta)):
                self.undo_last()
        else:
            for _ in range(delta):
                self.redo_last()

    def jump_undo_history_to(self, cursor_index: int) -> bool:
        entries = self.get_undo_history_entries()
        count = len(entries)
        if count <= 0:
            return False

        cursor_index = self._clamp_history_cursor(cursor_index, count)
        from engine.editor.undo_history_model import resolve_jump_delta  # noqa: PLC0415

        delta = resolve_jump_delta(entries, cursor_index)
        if delta == 0:
            return False
        self._jump_by_delta(delta)

        entries = self.get_undo_history_entries()
        current = self._history_current_index(entries)
        if current >= 0:
            self._history_cursor_index = current
        return True

    def _handle_history_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.active or self._right_dock_tab != "History":
            return False
        if self._history_input_blocked():
            return True

        entries = self.get_filtered_undo_history_entries()
        count = len(entries)
        if count <= 0:
            return True

        cursor_display = self._history_display_index(entries)
        if key == optional_arcade.arcade.key.UP:
            new_index = max(0, cursor_display - 1)
            self._history_cursor_index = entries[new_index].real_index
            return True
        if key == optional_arcade.arcade.key.DOWN:
            new_index = min(count - 1, cursor_display + 1)
            self._history_cursor_index = entries[new_index].real_index
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if self._search_focus == "history":
                return True
            return self.jump_undo_history_to(self._history_cursor_index)

        return False

    def _history_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        if not self.active or self._right_dock_tab != "History":
            return False
        if self._history_input_blocked():
            return True
        if self._search_focus == "history":
            return True
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        entries = self.get_filtered_undo_history_entries()
        if not entries:
            return True

        from engine.editor.editor_shell_layout import (  # noqa: PLC0415
            compute_editor_shell_layout,
            TAB_HEADER_HEIGHT,
        )
        from engine.editor.undo_history_model import (
            HISTORY_LINE_HEIGHT,
            HISTORY_PADDING,
            compute_history_window,
        )

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        getter = getattr(self, "get_effective_dock_widths", None)
        if callable(getter):
            left_w, right_w = getter(window_w)
        else:
            left_w = getattr(self, "_dock_left_w", 320)
            right_w = getattr(self, "_dock_right_w", 320)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock
        if not dock.contains_point(x, y):
            return False

        content_top = dock.top - TAB_HEADER_HEIGHT - HISTORY_PADDING - HISTORY_LINE_HEIGHT
        content_bottom = dock.bottom + HISTORY_PADDING
        if y > content_top or y < content_bottom:
            return True

        cursor_display = self._history_display_index(entries)
        visible_capacity = int((content_top - content_bottom) / HISTORY_LINE_HEIGHT)
        start_idx, visible = compute_history_window(cursor_display, len(entries), visible_capacity)

        row_y = content_top
        for idx in range(start_idx, start_idx + visible):
            row_top = row_y
            row_bottom = row_y - HISTORY_LINE_HEIGHT
            if row_bottom <= y <= row_top:
                self._history_cursor_index = entries[idx].real_index
                self.jump_undo_history_to(self._history_cursor_index)
                return True
            row_y -= HISTORY_LINE_HEIGHT

        return True

    def _refresh_hierarchy_list(self) -> None:
        previous_selection = self.selected_entity
        self._cached_hierarchy_list = self._build_hierarchy_list()
        if previous_selection and previous_selection in self._cached_hierarchy_list:
            self.hierarchy_selection_index = self._cached_hierarchy_list.index(previous_selection)
        else:
            count = len(self._cached_hierarchy_list)
            if count == 0:
                self.hierarchy_selection_index = -1
            else:
                if self.hierarchy_selection_index == -1:
                    self.hierarchy_selection_index = 0
                else:
                    self.hierarchy_selection_index = max(0, min(self.hierarchy_selection_index, count - 1))

    def _build_hierarchy_list(self) -> List[optional_arcade.arcade.Sprite]:
        all_sprites = list(self.window.scene_controller.all_sprites)
        self._hierarchy_name_cache = {}
        for idx, sprite in enumerate(all_sprites):
            self._hierarchy_name_cache[id(sprite)] = self._resolve_display_name(sprite, idx)

        if not self.hierarchy_filter:
            return all_sprites

        filtered = []
        search_term = self.hierarchy_filter.lower()
        is_behaviour_search = search_term.startswith("@")
        if is_behaviour_search:
            search_term = search_term[1:]

        for sprite in all_sprites:
            if is_behaviour_search:
                behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
                if any(search_term in b.__class__.__name__.lower() for b in behaviours):
                    filtered.append(sprite)
            else:
                name = self._hierarchy_name_cache.get(id(sprite), "").lower()
                tags = [tag.lower() for tag in self._get_entity_tags(sprite)]
                class_name = getattr(sprite.__class__, "__name__", "").lower()
                haystacks = [name]
                if tags:
                    haystacks.extend(tags)
                if class_name:
                    haystacks.append(class_name)

                if any(search_term in entry for entry in haystacks):
                    filtered.append(sprite)

        return filtered

    def _entity_panels_scene_data(self) -> Dict[str, Any]:
        scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self.window, "scene_controller"):
                self.window.scene_controller._loaded_scene_data = scene  # type: ignore[attr-defined]
        return scene

    def _resolve_entity_panels_id(self, entity: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
        return _resolve_entity_panels_id_impl(entity, fallback_index)

    def _entity_panels_selected_id_value(self) -> str | None:
        sprite = self.selected_entity
        if sprite is None:
            return None
        entity_data = getattr(sprite, "mesh_entity_data", None)
        fallback_index = self._get_sprite_index(sprite)
        if isinstance(entity_data, dict):
            return self._resolve_entity_panels_id(entity_data, fallback_index)
        mesh_name = getattr(sprite, "mesh_name", None)
        if isinstance(mesh_name, str) and mesh_name.strip():
            return mesh_name.strip()
        if fallback_index is not None:
            return f"idx:{int(fallback_index)}"
        return None

    def _filter_entity_panels_items(self, items: list[EntitySummary]) -> list[EntitySummary]:
        return _filter_entity_panels_items_impl(items, self._outliner_search)

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:
        items = list_entities(self._entity_panels_scene_data())
        items = self._filter_entity_panels_items(items)
        self._cached_entity_panels_list = items
        count = len(items)
        if count == 0:
            self.entity_panels_selection_index = -1
            self._entity_panels_selected_id = self._entity_panels_selected_id_value()
            return

        if self.entity_panels_selection_index < 0:
            self.entity_panels_selection_index = 0
        self.entity_panels_selection_index = _clamp_entity_panels_index_impl(
            self.entity_panels_selection_index, count
        )

        current_selected_id = self._entity_panels_selected_id_value()
        if sync_selected or current_selected_id != self._entity_panels_selected_id:
            if current_selected_id:
                for i, summary in enumerate(items):
                    if summary.id == current_selected_id:
                        self.entity_panels_selection_index = i
                        break
            self._entity_panels_selected_id = current_selected_id

    def _get_entity_panels_list(self) -> list[EntitySummary]:
        if not self._cached_entity_panels_list:
            self._refresh_entity_panels_list()
        return self._cached_entity_panels_list

    def _resolve_display_name(self, sprite: optional_arcade.arcade.Sprite, fallback_index: Optional[int] = None) -> str:
        def _normalize(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                value = str(value)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    return candidate
            return None

        entity_data = getattr(sprite, "mesh_entity_data", None)
        candidates: List[Any] = []
        if isinstance(entity_data, dict):
            candidates.extend([
                entity_data.get("name"),
                entity_data.get("display_name"),
                entity_data.get("id"),
                entity_data.get("tag"),
            ])

        candidates.extend([
            getattr(sprite, "mesh_name", None),
            getattr(sprite, "name", None),
            getattr(sprite, "mesh_tag", None),
        ])

        for entry in candidates:
            normalized = _normalize(entry)
            if normalized:
                return normalized

        if fallback_index is None:
            fallback_index = self._get_sprite_index(sprite)

        index_value = (fallback_index or 0) + 1
        tag_hint = None
        if isinstance(entity_data, dict):
            tag_hint = _normalize(entity_data.get("tag"))
        if not tag_hint:
            tag_hint = _normalize(getattr(sprite, "mesh_tag", None))

        base_label = tag_hint or "Entity"
        return f"{base_label}#{index_value}"

    def _get_sprite_index(self, sprite: optional_arcade.arcade.Sprite) -> Optional[int]:
        try:
            return list(self.window.scene_controller.all_sprites).index(sprite)
        except ValueError:
            return None

    def _get_display_name_for_sprite(self, sprite: optional_arcade.arcade.Sprite) -> str:
        return self._hierarchy_name_cache.get(id(sprite)) or self._resolve_display_name(sprite)

    def get_gizmo_feedback_state(self) -> "GizmoFeedbackState":
        """Get current state for gizmo overlay rendering.

        Returns:
            GizmoFeedbackState snapshot for overlay to render.
        """
        from engine.editor.editor_gizmo_feedback import GizmoFeedbackState  # noqa: PLC0415

        # Determine if any transform drag is active
        move_drag = getattr(self, "entity_dragging", False) and self.selected_entity is not None
        rotate_drag = getattr(self, "_rotate_drag_active", False)
        scale_drag = getattr(self, "_scale_drag_active", False)
        active = move_drag or rotate_drag or scale_drag

        if not active:
            return GizmoFeedbackState(
                active=False,
                mode="move",
                pivot_xy=None,
                move_delta_xy=None,
                rotate_delta_deg=None,
                scale_factor=None,
                snap_active=False,
            )

        # Determine mode
        if rotate_drag:
            mode = "rotate"
        elif scale_drag:
            mode = "scale"
        else:
            mode = "move"

        # Get pivot position
        pivot_xy = getattr(self, "_transform_drag_pivot", None)
        if pivot_xy is None and move_drag:
            # For move, use primary entity start position as pivot
            drag_starts = getattr(self, "_multiselect_drag_starts", {})
            primary_id = getattr(self, "_primary_entity_id", None)
            if primary_id and primary_id in drag_starts:
                pivot_xy = drag_starts[primary_id]
            elif self.selected_entity:
                start_pos = getattr(self, "entity_drag_start_pos", None)
                if start_pos:
                    pivot_xy = start_pos

        return GizmoFeedbackState(
            active=True,
            mode=mode,
            pivot_xy=pivot_xy,
            move_delta_xy=getattr(self, "_move_preview_delta_xy", None),
            rotate_delta_deg=getattr(self, "_rotate_preview_delta_deg", None),
            scale_factor=getattr(self, "_scale_preview_factor", None),
            snap_active=getattr(self, "_transform_snap_active", False),
        )

    # -------------------------------------------------------------------------
    # Hover Highlight State Management
    # -------------------------------------------------------------------------

    def set_hover_dock_tab(self, dock: str | None, tab: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered dock tab state.

        Args:
            dock: "left" or "right" or None.
            tab: Tab name like "Scene", "Outliner", "Inspector", "Assets" or None.
            rect: Rect tuple (x, y, w, h) of the tab, or None.
        """
        if dock is not None and tab is not None:
            self._hover_dock_tab = (dock, tab)
            self._hover_dock_tab_rect = rect
        else:
            self._hover_dock_tab = None
            self._hover_dock_tab_rect = None

    def set_hover_splitter(self, which: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered splitter state.

        Args:
            which: "left" or "right" or None.
            rect: Rect tuple (x, y, w, h) of the splitter, or None.
        """
        self._hover_splitter = which
        self._hover_splitter_rect = rect

    def set_hover_menu_title(self, title: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered menu title state.

        Args:
            title: Menu title like "File", "Edit", etc. or None.
            rect: Rect tuple (x, y, w, h) of the title, or None.
        """
        self._hover_menu_title = title
        self._hover_menu_title_rect = rect

    def set_hover_menu_item_rect(self, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered menu item rect (ID is already in _menu_hover_item_id).

        Args:
            rect: Rect tuple (x, y, w, h) of the item, or None.
        """
        self._hover_menu_item_rect = rect

    def set_hover_top_bar_control(self, control_id: str | None) -> None:
        """Set hovered top bar control ID.

        Args:
            control_id: "L", "R", "M", or None.
        """
        self._hover_top_bar_control_id = control_id

    def get_hover_top_bar_control_id(self) -> str | None:
        """Get hovered top bar control ID."""
        return self._hover_top_bar_control_id

    def set_hover_context_item_rect(self, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered context menu item rect (ID is already in _context_menu_hover_id).

        Args:
            rect: Rect tuple (x, y, w, h) of the item, or None.
        """
        self._hover_context_item_rect = rect

    def set_hover_inspector_field(self, key: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered inspector field state.

        Args:
            key: Field key like "position.x", "sprite", etc. or None.
            rect: Rect tuple (x, y, w, h) of the field row, or None.
        """
        self._hover_inspector_field_key = key
        self._hover_inspector_field_rect = rect

    def set_hover_entity(self, entity_id: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        """Set hovered entity state (world-space).

        Args:
            entity_id: Entity ID or None.
            rect: Rect tuple (x, y, w, h) in world coordinates, or None.
        """
        self._hover_entity_id = entity_id
        self._hover_entity_rect = rect

    def clear_hover_state(self) -> None:
        """Clear all hover highlight state."""
        self._hover_menu_title = None
        self._hover_menu_title_rect = None
        self._hover_menu_item_rect = None
        self._hover_top_bar_control_id = None
        self._hover_dock_tab = None
        self._hover_dock_tab_rect = None
        self._hover_splitter = None
        self._hover_splitter_rect = None
        self._hover_context_item_rect = None
        self._hover_inspector_field_key = None
        self._hover_inspector_field_rect = None
        self._hover_entity_id = None
        self._hover_entity_rect = None

    # -------------------------------------------------------------------------
    # Dock Collapse / Viewport Maximize
    # -------------------------------------------------------------------------

    def get_dock_left_collapsed(self) -> bool:
        """Get whether the left dock is collapsed."""
        return self._dock_left_collapsed

    def get_dock_right_collapsed(self) -> bool:
        """Get whether the right dock is collapsed."""
        return self._dock_right_collapsed

    def get_viewport_maximized(self) -> bool:
        """Get whether the viewport is maximized."""
        return self._viewport_maximized

    def toggle_left_dock(self) -> None:
        """Toggle the left dock collapsed state.

        When viewport is maximized, this does nothing (user must un-maximize first).
        """
        if self._viewport_maximized:
            return
        self._dock_left_collapsed = not self._dock_left_collapsed
        self._autosave_workspace()

    def toggle_right_dock(self) -> None:
        """Toggle the right dock collapsed state.

        When viewport is maximized, this does nothing (user must un-maximize first).
        """
        if self._viewport_maximized:
            return
        self._dock_right_collapsed = not self._dock_right_collapsed
        self._autosave_workspace()

    def toggle_viewport_maximized(self) -> None:
        """Toggle viewport maximized state.

        When turning ON: stores current collapsed states and forces both docks hidden.
        When turning OFF: restores previous collapsed states.
        """
        if self._viewport_maximized:
            # Turning OFF - restore previous collapse states
            self._viewport_maximized = False
            self._dock_left_collapsed = self._dock_prev_left_collapsed
            self._dock_right_collapsed = self._dock_prev_right_collapsed
        else:
            # Turning ON - store current collapse states
            self._dock_prev_left_collapsed = self._dock_left_collapsed
            self._dock_prev_right_collapsed = self._dock_right_collapsed
            self._viewport_maximized = True
        self._autosave_workspace()

    def get_effective_dock_widths(self, window_w: int) -> Tuple[int, int]:
        """Get effective dock widths accounting for collapse/maximize state.

        Args:
            window_w: Window width for clamping.

        Returns:
            Tuple of (left_w_effective, right_w_effective).
        """
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths  # noqa: PLC0415
        return resolve_effective_dock_widths(
            left_collapsed=self._dock_left_collapsed,
            right_collapsed=self._dock_right_collapsed,
            viewport_maximized=self._viewport_maximized,
            left_w=self._dock_left_w,
            right_w=self._dock_right_w,
            window_width=window_w,
        )

    # -------------------------------------------------------------------------
    # Cursor Hint / Affordance Feedback
    # -------------------------------------------------------------------------

    def set_last_mouse_pos(self, x: float, y: float) -> None:
        """Update the last known mouse position.

        Args:
            x: Mouse X in screen coordinates.
            y: Mouse Y in screen coordinates.
        """
        self._last_mouse_x = float(x)
        self._last_mouse_y = float(y)

    def get_last_mouse_pos(self) -> Tuple[float, float]:
        """Get the last known mouse position.

        Returns:
            Tuple of (x, y) in screen coordinates.
        """
        return (self._last_mouse_x, self._last_mouse_y)

    def get_cursor_hint_text(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint text based on current editor state.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Hint text string or None if no hint.
        """
        result = self._compute_cursor_hint(window_w, window_h)
        return result.text if result is not None else None

    def get_cursor_hint_kind(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint kind for cursor affordance.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Cursor kind string or None when editor is inactive.
        """
        result = self._compute_cursor_hint(window_w, window_h)
        return result.kind if result is not None else None

    def _compute_cursor_hint(self, window_w: int, window_h: int):
        if not self.active:
            return None

        from engine.editor.editor_cursor_model import build_cursor_hint  # noqa: PLC0415
        from engine.editor_tooltips_model import (  # noqa: PLC0415
            _is_modal_open_state,
            _is_text_input_active_state,
        )

        mouse_x, mouse_y = self._last_mouse_x, self._last_mouse_y

        ui_blocked = _is_text_input_active_state(self) or _is_modal_open_state(self)

        splitter_hit = getattr(self, "_dock_drag_active", None) or getattr(self, "_hover_splitter", None)
        entity_hit = getattr(self, "_hover_entity_id", None) is not None

        ui_hover = False
        if getattr(self, "_hover_menu_title", None) is not None:
            ui_hover = True
        if getattr(self, "_menu_active", None) and getattr(self, "_menu_hover_item_id", None) is not None:
            ui_hover = True
        if getattr(self, "_hover_dock_tab", None) is not None:
            ui_hover = True
        if getattr(self, "_hover_top_bar_control_id", None) is not None:
            ui_hover = True

        # Determine gizmo drag state
        move_drag = getattr(self, "entity_dragging", False) and self.selected_entity is not None
        rotate_drag = getattr(self, "_rotate_drag_active", False)
        scale_drag = getattr(self, "_scale_drag_active", False)
        gizmo_drag_active = move_drag or rotate_drag or scale_drag

        gizmo_mode: str | None = None
        if rotate_drag:
            gizmo_mode = "rotate"
        elif scale_drag:
            gizmo_mode = "scale"
        elif move_drag:
            gizmo_mode = "move"

        return build_cursor_hint(
            editor_active=self.active,
            mouse_x=mouse_x,
            mouse_y=mouse_y,
            window_w=window_w,
            window_h=window_h,
            ui_blocked=ui_blocked,
            marquee_active=getattr(self, "_marquee_active", False),
            alt_dup_active=getattr(self, "_alt_dup_active", False),
            gizmo_drag_active=gizmo_drag_active,
            gizmo_mode=gizmo_mode,
            ui_hover=ui_hover,
            shell_layout=None,
            splitter_hit=splitter_hit,
            entity_hit=entity_hit,
        )

    # -------------------------------------------------------------------------
    # Marquee Box Selection
    # -------------------------------------------------------------------------

    def begin_marquee(self, world_x: float, world_y: float, shift: bool) -> None:
        """Begin a marquee box selection.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
            shift: Whether Shift modifier is held.
        """
        self._marquee_active = True
        self._marquee_start_world = (world_x, world_y)
        self._marquee_end_world = (world_x, world_y)
        self._marquee_shift = shift

    def update_marquee(self, world_x: float, world_y: float) -> None:
        """Update marquee end point during drag.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        if self._marquee_active:
            self._marquee_end_world = (world_x, world_y)

    def end_marquee(self) -> None:
        """Commit marquee selection and deactivate."""
        if not self._marquee_active:
            return

        from .editor.marquee_select import (  # noqa: PLC0415
            rect_from_points,
            compute_marquee_candidates,
            apply_marquee_selection,
        )
        from .editor.selection_outline import resolve_entity_bounds  # noqa: PLC0415
        from .editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        start = self._marquee_start_world
        end = self._marquee_end_world

        if start is None or end is None:
            self._reset_marquee()
            return

        # Build marquee rect
        marquee_rect = rect_from_points(start, end)

        # Build entity bounds list
        entity_bounds: list[tuple[str, Any]] = []
        sc = getattr(self.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "current_scene_data", None)
            if isinstance(scene_data, dict):
                entities = scene_data.get("entities", [])
                if isinstance(entities, list):
                    for entity in entities:
                        if isinstance(entity, dict):
                            eid = entity.get("id")
                            if eid:
                                sprite = get_sprite_for_entity_id(self, eid)
                                rect = resolve_entity_bounds(entity, sprite)
                                if rect is not None:
                                    entity_bounds.append((eid, rect))

        # Compute candidates
        candidates = compute_marquee_candidates(marquee_rect, entity_bounds)

        # Apply selection
        current_selected = list(getattr(self, "_selected_entity_ids", []))
        new_selection = apply_marquee_selection(current_selected, candidates, self._marquee_shift)

        # Update selection state
        self._selected_entity_ids = new_selection
        self._primary_entity_id = new_selection[0] if new_selection else None

        # Update selected_entity sprite reference
        if self._primary_entity_id:
            self.selected_entity = get_sprite_for_entity_id(self, self._primary_entity_id)
        else:
            self.selected_entity = None

        self._reset_marquee()

    def cancel_marquee(self) -> None:
        """Cancel marquee selection without committing."""
        self._reset_marquee()

    def _reset_marquee(self) -> None:
        """Reset marquee state."""
        self._marquee_active = False
        self._marquee_start_world = None
        self._marquee_end_world = None
        self._marquee_shift = False

    # -------------------------------------------------------------------------
    # Alt-Drag Duplicate
    # -------------------------------------------------------------------------

    def begin_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Begin alt-drag duplicate operation.

        Duplicates selected entities immediately and starts dragging them.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
        """
        from .editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            duplicate_entities_in_scene,
            normalize_selection_ids,
        )
        from .editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        selected_ids = list(getattr(self, "_selected_entity_ids", []))
        if not selected_ids:
            return

        # Store original selection for cancel
        self._alt_dup_original_selection = selected_ids.copy()
        self._alt_dup_original_primary = getattr(self, "_primary_entity_id", None)

        # Get scene data
        sc = getattr(self.window, "scene_controller", None)
        if sc is None:
            return
        scene_data = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene_data, dict):
            return

        # Duplicate entities into scene
        new_scene, specs = duplicate_entities_in_scene(scene_data, selected_ids)

        if not specs:
            return

        # Update scene data in place
        sc._loaded_scene_data = new_scene

        # Create sprites for duplicated entities
        entities = new_scene.get("entities", [])
        for spec in specs:
            # Find the new entity data
            new_entity_data = None
            for entity in entities:
                eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                if eid == spec.new_id:
                    new_entity_data = entity
                    break
            if new_entity_data:
                self._create_entity_internal(new_entity_data)

        # Determine pivot (copy of primary, or first)
        primary_src = self._alt_dup_original_primary
        pivot_new_id: str | None = None
        for spec in specs:
            if spec.src_id == primary_src:
                pivot_new_id = spec.new_id
                break
        if pivot_new_id is None and specs:
            pivot_new_id = specs[0].new_id

        # Set selection to duplicated entities
        new_selection = [spec.new_id for spec in specs]
        self._selected_entity_ids = new_selection
        self._primary_entity_id = pivot_new_id

        # Update selected_entity sprite reference
        if pivot_new_id:
            self.selected_entity = get_sprite_for_entity_id(self, pivot_new_id)

        # Store state
        self._alt_dup_active = True
        self._alt_dup_specs = tuple(specs)
        self._alt_dup_pivot_new_id = pivot_new_id
        self._alt_dup_drag_start_world = (world_x, world_y)
        self._alt_dup_last_world = (world_x, world_y)

        self._mark_dirty()

    def update_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Update alt-drag duplicate positions during drag.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        from .editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            apply_drag_delta_to_specs,
            DuplicateEntitySpec,
        )
        from .editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        if not self._alt_dup_active or self._alt_dup_specs is None:
            return

        start = self._alt_dup_drag_start_world
        if start is None:
            return

        # Compute delta
        delta_xy = (world_x - start[0], world_y - start[1])

        # Get snap settings
        snap_enabled = getattr(self, "snap_enabled", True)
        snap_mode = getattr(self, "snap_mode", "grid16")
        tile_size = int(getattr(self, "grid_size", 16))

        # Apply drag delta with snapping
        updated_specs = apply_drag_delta_to_specs(
            list(self._alt_dup_specs),
            delta_xy,
            snap_enabled,
            snap_mode,
            tile_size,
            self._alt_dup_pivot_new_id,
        )

        # Update specs
        self._alt_dup_specs = tuple(updated_specs)
        self._alt_dup_last_world = (world_x, world_y)

        # Apply positions to sprites
        for spec in updated_specs:
            sprite = get_sprite_for_entity_id(self, spec.new_id)
            if sprite:
                sprite.center_x = spec.end_xy[0]
                sprite.center_y = spec.end_xy[1]
                # Also update entity data
                entity_data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(entity_data, dict):
                    entity_data["x"] = spec.end_xy[0]
                    entity_data["y"] = spec.end_xy[1]

    def cancel_alt_drag_duplicate(self) -> None:
        """Cancel alt-drag duplicate and remove duplicated entities."""
        from .editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            remove_alt_drag_duplicates,
            AltDragDuplicateCommand,
        )
        from .editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        if not self._alt_dup_active:
            return

        specs = self._alt_dup_specs
        if specs:
            # Remove sprites for duplicated entities
            for spec in specs:
                sprite = get_sprite_for_entity_id(self, spec.new_id)
                if sprite:
                    self._delete_entity_internal(sprite)

            # Also remove from scene data
            sc = getattr(self.window, "scene_controller", None)
            if sc is not None:
                scene_data = getattr(sc, "_loaded_scene_data", None)
                if isinstance(scene_data, dict):
                    cmd = AltDragDuplicateCommand(specs=specs)
                    new_scene = remove_alt_drag_duplicates(scene_data, cmd)
                    sc._loaded_scene_data = new_scene

        # Restore original selection
        if self._alt_dup_original_selection is not None:
            self._selected_entity_ids = self._alt_dup_original_selection
            self._primary_entity_id = self._alt_dup_original_primary
            if self._alt_dup_original_primary:
                self.selected_entity = get_sprite_for_entity_id(self, self._alt_dup_original_primary)
            else:
                self.selected_entity = None

        self._reset_alt_drag_duplicate()
        self._mark_dirty()

    def end_alt_drag_duplicate(self) -> None:
        """Commit alt-drag duplicate and push undo command."""
        from .editor.editor_alt_drag_duplicate_ops import AltDragDuplicateCommand  # noqa: PLC0415

        if not self._alt_dup_active:
            return

        specs = self._alt_dup_specs
        if not specs:
            self._reset_alt_drag_duplicate()
            return

        # Get snap settings for command
        snap_enabled = getattr(self, "snap_enabled", True)
        snap_mode = getattr(self, "snap_mode", "grid16")

        # Build command
        cmd = AltDragDuplicateCommand(
            kind="alt_drag_duplicate",
            specs=specs,
            pivot_src_id=self._alt_dup_original_primary,
            pivot_new_id=self._alt_dup_pivot_new_id,
            snap_enabled=snap_enabled,
            snap_mode=snap_mode,
        )

        # Push undo command
        self._push_command(cmd.to_dict())

        # Sync final positions to scene data
        sc = getattr(self.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                entities = scene_data.get("entities", [])
                if isinstance(entities, list):
                    for spec in specs:
                        for entity in entities:
                            eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                            if eid == spec.new_id:
                                entity["x"] = spec.end_xy[0]
                                entity["y"] = spec.end_xy[1]
                                break

        self._reset_alt_drag_duplicate()

    def _reset_alt_drag_duplicate(self) -> None:
        """Reset alt-drag duplicate state."""
        self._alt_dup_active = False
        self._alt_dup_specs = None
        self._alt_dup_pivot_new_id = None
        self._alt_dup_drag_start_world = None
        self._alt_dup_last_world = None
        self._alt_dup_original_selection = None
        self._alt_dup_original_primary = None

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
        if not self.entity_panels_active:
            return []

        self._refresh_entity_panels_list()
        return _build_outliner_lines_impl(
            active=self.entity_panels_active,
            focus=self.entity_panels_focus,
            search_text=self._outliner_search,
            search_focused=self._search_focus == "outliner",
            items=self._cached_entity_panels_list,
            cursor_index=self.entity_panels_selection_index,
            selected_id=self._entity_panels_selected_id_value(),
        )

    def _entity_panels_inspector_lines(self) -> list[str]:
        if not self.entity_panels_active:
            return []

        sprite = self.selected_entity
        sprite_name = self._get_display_name_for_sprite(sprite) if sprite else None
        entity_data = (
            self.window.scene_controller._ensure_entity_data_dict(sprite)
            if sprite
            else {}
        )
        return _build_inspector_lines_impl(
            active=self.entity_panels_active,
            focus=self.entity_panels_focus,
            text_edit_active=self.entity_panels_text_edit_active,
            sprite_name=sprite_name,
            entity_data=entity_data,
            inspector_index=self.entity_panels_inspector_index,
            text_field=self.entity_panels_text_field,
            text_buffer=self.entity_panels_text_buffer,
            sprite=sprite,
        )

    def _entity_panels_format_field_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
        kind: str,
    ) -> str:
        return _format_entity_field_value_impl(entity_data, sprite, key, kind)

    def _entity_panels_numeric_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
    ) -> float:
        return _get_entity_numeric_value_impl(entity_data, sprite, key)

    def _entity_panels_select_current(self) -> bool:
        items = self._cached_entity_panels_list
        if not items:
            return False
        idx = _clamp_entity_panels_index_impl(self.entity_panels_selection_index, len(items))
        summary = items[idx]
        target = self._entity_panels_find_sprite(summary)
        if target is None:
            return False
        from .editor_runtime.state import apply_selection  # noqa: PLC0415

        apply_selection(self, target)
        self._entity_panels_selected_id = self._entity_panels_selected_id_value()
        self._refresh_entity_panels_list(sync_selected=True)
        return True

    def _entity_panels_find_sprite(self, summary: EntitySummary) -> Optional[optional_arcade.arcade.Sprite]:
        sprite = self._find_entity_by_id(summary.id)
        if sprite is not None:
            return sprite
        sprite = self._find_entity_by_name(summary.id)
        if sprite is not None:
            return sprite
        if summary.id.startswith("idx:"):
            try:
                idx = int(summary.id.split(":", 1)[1])
            except Exception:  # noqa: BLE001
                idx = -1
            if idx >= 0:
                try:
                    all_sprites = list(self.window.scene_controller.all_sprites)
                    if idx < len(all_sprites):
                        return all_sprites[idx]
                except Exception:  # noqa: BLE001
                    pass
            scene = self._entity_panels_scene_data()
            entities = scene.get("entities")
            if isinstance(entities, list) and 0 <= idx < len(entities):
                entity = entities[idx]
                if isinstance(entity, dict):
                    alt_id = self._resolve_entity_panels_id(entity, idx)
                    sprite = self._find_entity_by_id(alt_id) or self._find_entity_by_name(alt_id)
                    if sprite is not None:
                        return sprite
        return None

    def _entity_panels_begin_text_edit(self, field: str, initial: str) -> None:
        self.entity_panels_text_edit_active = True
        self.entity_panels_text_field = field
        self.entity_panels_text_buffer = initial

    def _entity_panels_cancel_text_edit(self) -> None:
        self.entity_panels_text_edit_active = False
        self.entity_panels_text_field = None
        self.entity_panels_text_buffer = ""

    def _entity_panels_commit_text_edit(self) -> bool:
        if not self.entity_panels_text_edit_active or not self.entity_panels_text_field:
            return False
        field = self.entity_panels_text_field
        value = self.entity_panels_text_buffer
        applied = self._entity_panels_apply_field_update(field, value)
        self._entity_panels_cancel_text_edit()
        return applied

    def _entity_panels_apply_field_update(self, field: str, value: Any) -> bool:
        if not self.selected_entity:
            return False
        entity_id = self._entity_panels_selected_id_value()
        if not entity_id:
            return False
        update_entity_field(self._entity_panels_scene_data(), entity_id, field, value)

        sprite = self.selected_entity
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        key = str(field or "").strip().lower()

        if key in {"x", "y"}:
            try:
                numeric = float(value)
            except Exception:  # noqa: BLE001
                return False
            if key == "x":
                self.window.scene_controller._apply_entity_mutation(sprite, x=numeric)
            else:
                self.window.scene_controller._apply_entity_mutation(sprite, y=numeric)
        elif key == "mesh_name":
            new_name = str(value or "")
            entity_data["mesh_name"] = new_name
            setattr(sprite, "mesh_name", new_name)
            if id(sprite) in self._hierarchy_name_cache:
                self._hierarchy_name_cache[id(sprite)] = new_name
        elif key == "interact_label":
            entity_data["interact_label"] = str(value or "")
        elif key in {"rotation_deg", "rotation"}:
            try:
                rotation = float(value) % 360.0
            except Exception:  # noqa: BLE001
                return False
            entity_data["rotation"] = rotation
            sprite.angle = rotation
        elif key in {"tags", "tags_add", "tags_remove"}:
            tags = _normalize_entity_panel_tags(entity_data.get("tags"))
            if key == "tags_add":
                tags = _apply_entity_panel_tag_delta(tags, add=_normalize_entity_panel_tags(value))
            elif key == "tags_remove":
                tags = _apply_entity_panel_tag_delta(tags, remove=_normalize_entity_panel_tags(value))
            elif isinstance(value, dict):
                add = _normalize_entity_panel_tags(value.get("add"))
                remove = _normalize_entity_panel_tags(value.get("remove"))
                tags = _apply_entity_panel_tag_delta(tags, add=add, remove=remove)
            else:
                tags = _normalize_entity_panel_tags(value)
            entity_data["tags"] = tags
        else:
            return False

        self._mark_dirty()
        self._refresh_entity_panels_list(sync_selected=True)
        return True

    # --------------------------------------------------------------------------
    # Component Inspector Input Handling
    # --------------------------------------------------------------------------

    def _handle_inspector_component_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input for component inspector navigation and editing."""
        # Only handle when Inspector tab is active and we have a selection
        if self._right_dock_tab != "Inspector":
            return False
        if not self.selected_entity:
            return False

        from .editor.inspector_components_model import (
            build_inspector_sections,
            clamp_inspector_cursor,
            move_cursor,
            get_cursor_row,
            toggle_section,
            apply_inspector_edit,
            InspectorCursor,
            NUMERIC_STEP_NORMAL,
            NUMERIC_STEP_SHIFT,
        )

        # Get entity JSON
        entity_json = self._get_selected_entity_json_for_inspector()
        if entity_json is None:
            return False

        sections = build_inspector_sections(
            entity_json, None, self._inspector_sections_expanded
        )
        if not sections:
            return False

        cursor = InspectorCursor(
            section_id=self._inspector_cursor[0],
            row_index=self._inspector_cursor[1],
        )
        cursor = clamp_inspector_cursor(cursor, sections)

        # Text edit mode takes priority
        if self._inspector_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self._inspector_commit_text_edit()
            if key == optional_arcade.arcade.key.ESCAPE:
                self._inspector_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._inspector_text_buffer = self._inspector_text_buffer[:-1]
                return True
            # Consume all keys in text edit mode
            return True

        # Navigation
        if key == optional_arcade.arcade.key.UP:
            new_cursor = move_cursor(cursor, sections, "up")
            self._inspector_cursor = (new_cursor.section_id, new_cursor.row_index)
            return True

        if key == optional_arcade.arcade.key.DOWN:
            new_cursor = move_cursor(cursor, sections, "down")
            self._inspector_cursor = (new_cursor.section_id, new_cursor.row_index)
            return True

        row = get_cursor_row(cursor, sections)
        if row is None:
            return False

        # Header row actions (toggle collapse)
        if row.kind == "header":
            if key in (
                optional_arcade.arcade.key.ENTER,
                optional_arcade.arcade.key.RETURN,
                optional_arcade.arcade.key.LEFT,
                optional_arcade.arcade.key.RIGHT,
                optional_arcade.arcade.key.SPACE,
            ):
                # Toggle section expand/collapse (UI-only, no dirty)
                self._inspector_sections_expanded = toggle_section(
                    self._inspector_sections_expanded, row.key
                )
                return True
            return False

        # Field row actions
        if row.kind == "field" and row.editable:
            # Numeric adjustment with Left/Right
            if row.field_kind in ("float", "int"):
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    step = NUMERIC_STEP_SHIFT if (modifiers & optional_arcade.arcade.key.MOD_SHIFT) else NUMERIC_STEP_NORMAL
                    delta = -step if key == optional_arcade.arcade.key.LEFT else step
                    new_json, changed = apply_inspector_edit(
                        entity_json, cursor, sections, delta, is_text_commit=False
                    )
                    if changed:
                        self._apply_inspector_entity_update(new_json, row.key)
                    return True

            # String edit with Enter
            if row.field_kind == "string":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    self._inspector_begin_text_edit(str(row.value or ""))
                    return True

            # Bool toggle with Enter
            if row.field_kind == "bool":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    new_json, changed = apply_inspector_edit(
                        entity_json, cursor, sections, True, is_text_commit=False
                    )
                    if changed:
                        self._apply_inspector_entity_update(new_json, row.key)
                    return True

        return False

    def _get_selected_entity_json_for_inspector(self) -> dict[str, Any] | None:
        """Get the JSON data for the currently selected entity."""
        primary_id = getattr(self, "_primary_selected_id", None)
        if not primary_id:
            selected = getattr(self, "selected_entity", None)
            if not selected:
                return None
            primary_id = getattr(selected, "mesh_name", None) or getattr(selected, "mesh_entity_data", {}).get("id")
            if not primary_id:
                return None

        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return None

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return None

        entities = loaded_data.get("entities", [])
        for ent in entities:
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == primary_id:
                    return ent

        return None

    def _inspector_begin_text_edit(self, initial: str) -> None:
        """Begin text editing mode for inspector string field."""
        self._inspector_text_edit_active = True
        self._inspector_text_buffer = initial

    def _inspector_cancel_text_edit(self) -> None:
        """Cancel text editing mode without applying changes."""
        self._inspector_text_edit_active = False
        self._inspector_text_buffer = ""

    def _inspector_commit_text_edit(self) -> bool:
        """Commit text edit and apply to entity."""
        if not self._inspector_text_edit_active:
            return False

        from .editor.inspector_components_model import (
            build_inspector_sections,
            clamp_inspector_cursor,
            get_cursor_row,
            apply_inspector_edit,
            InspectorCursor,
        )

        entity_json = self._get_selected_entity_json_for_inspector()
        if entity_json is None:
            self._inspector_cancel_text_edit()
            return False

        sections = build_inspector_sections(
            entity_json, None, self._inspector_sections_expanded
        )
        cursor = InspectorCursor(
            section_id=self._inspector_cursor[0],
            row_index=self._inspector_cursor[1],
        )
        cursor = clamp_inspector_cursor(cursor, sections)

        row = get_cursor_row(cursor, sections)
        if row is None or row.kind != "field":
            self._inspector_cancel_text_edit()
            return False

        new_json, changed = apply_inspector_edit(
            entity_json, cursor, sections, self._inspector_text_buffer, is_text_commit=True
        )

        if changed:
            self._apply_inspector_entity_update(new_json, row.key)

        self._inspector_cancel_text_edit()
        return True

    def _apply_inspector_entity_update(self, new_entity_json: dict[str, Any], field_key: str) -> None:
        """Apply entity JSON update, push undo command, and mark dirty."""
        if not self.selected_entity:
            return

        # Get old value for undo
        old_json = self._get_selected_entity_json_for_inspector()
        if old_json is None:
            return

        # Get the old and new values
        from .editor.inspector_components_model import _get_nested_value
        old_value = _get_nested_value(old_json, field_key)
        new_value = _get_nested_value(new_entity_json, field_key)

        # Push undo command
        self._push_command({
            "type": "InspectorEdit",
            "entity_id": self._get_entity_id_for_inspector(),
            "field_key": field_key,
            "before": old_value,
            "after": new_value,
        })

        # Apply the change to scene data
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return

        entity_id = self._get_entity_id_for_inspector()
        entities = loaded_data.get("entities", [])
        for i, ent in enumerate(entities):
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == entity_id:
                    entities[i] = new_entity_json
                    break

        # Also update sprite if relevant
        self._apply_inspector_to_sprite(field_key, new_value)

        self._mark_dirty()

    def _get_entity_id_for_inspector(self) -> str | None:
        """Get the ID of the currently selected entity."""
        primary_id = getattr(self, "_primary_selected_id", None)
        if primary_id:
            return primary_id
        selected = getattr(self, "selected_entity", None)
        if not selected:
            return None
        return getattr(selected, "mesh_name", None) or getattr(selected, "mesh_entity_data", {}).get("id")

    def _apply_inspector_to_sprite(self, field_key: str, value: Any) -> None:
        """Apply a field change to the sprite runtime state."""
        if not self.selected_entity:
            return

        sprite = self.selected_entity

        # Handle simple direct fields
        if field_key == "x":
            self.window.scene_controller._apply_entity_mutation(sprite, x=float(value))
        elif field_key == "y":
            self.window.scene_controller._apply_entity_mutation(sprite, y=float(value))
        elif field_key == "rotation":
            try:
                rotation = float(value) % 360.0
            except (ValueError, TypeError):
                return
            sprite.angle = rotation
            entity_data = getattr(sprite, "mesh_entity_data", {})
            if isinstance(entity_data, dict):
                entity_data["rotation"] = rotation
        elif field_key == "scale":
            try:
                scale = float(value)
            except (ValueError, TypeError):
                return
            sprite.scale = scale
            entity_data = getattr(sprite, "mesh_entity_data", {})
            if isinstance(entity_data, dict):
                entity_data["scale"] = scale

    def _handle_inspector_text_input(self, text: str) -> bool:
        """Handle text input for inspector text editing."""
        if self._inspector_text_edit_active:
            if text and text.isprintable():
                self._inspector_text_buffer += text
                return True
        return False

    # --------------------------------------------------------------------------
    # Component Inspector v1 Input Handling
    # --------------------------------------------------------------------------

    def _handle_component_inspector_v1_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input for component inspector v1 navigation and editing.
        
        Uses the new components_model and components_ops modules.
        """
        # Only handle when Inspector tab is active and we have a selection
        if self._right_dock_tab != "Inspector":
            return False
        if not self.selected_entity:
            return False

        from .editor.components_model import (
            build_components,
            add_component,
            remove_component,
            set_component_field,
            get_addable_components,
            ComponentKind,
            COMPONENT_TITLES,
        )
        from .editor.components_ops import (
            apply_inspector_delta,
            reset_field_to_default,
            get_step_for_field,
        )
        from .editor.entity_panels import (
            get_component_inspector_row_count,
            resolve_component_inspector_selection,
        )

        # Get entity JSON
        entity_json = self._get_selected_entity_json_for_inspector()
        if entity_json is None:
            return False

        # Handle add component picker mode
        if self._add_component_picker_active:
            return self._handle_add_component_picker_input(key, entity_json)

        # Build components
        components = build_components(entity_json, self.selected_entity)
        row_count = get_component_inspector_row_count(components, include_add_row=True)

        # Clamp selection
        if row_count > 0:
            self._component_inspector_index = max(0, min(self._component_inspector_index, row_count - 1))
        else:
            self._component_inspector_index = 0

        # Resolve what's selected
        selection = resolve_component_inspector_selection(components, self._component_inspector_index)

        # Text edit mode takes priority
        if self._inspector_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self._component_inspector_commit_text_edit(entity_json, selection)
            if key == optional_arcade.arcade.key.ESCAPE:
                self._inspector_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._inspector_text_buffer = self._inspector_text_buffer[:-1]
                return True
            # Consume all keys in text edit mode
            return True

        # Navigation
        if key == optional_arcade.arcade.key.UP:
            self._component_inspector_index = max(0, self._component_inspector_index - 1)
            return True

        if key == optional_arcade.arcade.key.DOWN:
            self._component_inspector_index = min(row_count - 1, self._component_inspector_index + 1)
            return True

        if selection is None:
            return False

        sel_type = selection.get("type")

        # Header row actions
        if sel_type == "header":
            comp_kind = selection.get("component_kind")
            removable = selection.get("removable", False)

            # Delete/Backspace removes component (if removable)
            if key in (optional_arcade.arcade.key.DELETE, optional_arcade.arcade.key.BACKSPACE):
                if removable and comp_kind:
                    new_json = remove_component(entity_json, comp_kind)
                    self._apply_component_entity_update(new_json)
                    return True
            return False

        # Field row actions
        if sel_type == "field":
            comp_kind = selection.get("component_kind")
            field_key = selection.get("field_key")
            field = selection.get("field")

            if not field or not field.editable:
                return False

            # R key resets to default
            if key == optional_arcade.arcade.key.R:
                new_json = reset_field_to_default(entity_json, comp_kind, field_key)
                self._apply_component_entity_update(new_json)
                return True

            # Left/Right for numeric adjustment
            if field.kind in ("float", "int"):
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    step = get_step_for_field(comp_kind, field_key)
                    delta = -step if key == optional_arcade.arcade.key.LEFT else step
                    shift = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                    new_json = apply_inspector_delta(entity_json, comp_kind, field_key, delta, shift)
                    self._apply_component_entity_update(new_json)
                    return True

            # Left/Right for enum cycling
            if field.kind == "enum":
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    delta = -1.0 if key == optional_arcade.arcade.key.LEFT else 1.0
                    new_json = apply_inspector_delta(entity_json, comp_kind, field_key, delta, False)
                    self._apply_component_entity_update(new_json)
                    return True

            # Enter for bool toggle
            if field.kind == "bool":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    new_json = apply_inspector_delta(entity_json, comp_kind, field_key, 1.0, False)
                    self._apply_component_entity_update(new_json)
                    return True

            # Enter for string/asset edit
            if field.kind in ("string", "asset"):
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    self._inspector_begin_text_edit(str(field.value or ""))
                    return True

            return False

        # Add Component row
        if sel_type == "add_row":
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                # Open add component picker
                addable = get_addable_components(entity_json)
                if addable:
                    self._add_component_picker_active = True
                    self._add_component_picker_index = 0
                    self._add_component_picker_options = list(addable)
                return True

        return False

    def _handle_add_component_picker_input(self, key: int, entity_json: Dict[str, Any]) -> bool:
        """Handle input for the add component picker."""
        from .editor.components_model import add_component, COMPONENT_TITLES

        if key == optional_arcade.arcade.key.ESCAPE:
            self._add_component_picker_active = False
            return True

        if key == optional_arcade.arcade.key.UP:
            self._add_component_picker_index = max(0, self._add_component_picker_index - 1)
            return True

        if key == optional_arcade.arcade.key.DOWN:
            max_idx = len(self._add_component_picker_options) - 1
            self._add_component_picker_index = min(max_idx, self._add_component_picker_index + 1)
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if 0 <= self._add_component_picker_index < len(self._add_component_picker_options):
                kind = self._add_component_picker_options[self._add_component_picker_index]
                new_json = add_component(entity_json, kind)  # type: ignore[arg-type]
                self._apply_component_entity_update(new_json)
            self._add_component_picker_active = False
            return True

        return True  # Consume all keys while picker is open

    def _component_inspector_commit_text_edit(
        self, entity_json: Dict[str, Any], selection: Optional[Dict[str, Any]]
    ) -> bool:
        """Commit text edit for component inspector field."""
        if not self._inspector_text_edit_active:
            return False
        if selection is None or selection.get("type") != "field":
            self._inspector_cancel_text_edit()
            return False

        from .editor.components_model import set_component_field

        comp_kind = selection.get("component_kind")
        field_key = selection.get("field_key")
        field = selection.get("field")

        if not comp_kind or not field_key:
            self._inspector_cancel_text_edit()
            return False

        # Parse value based on field kind
        new_value: Any = self._inspector_text_buffer
        if field and field.kind == "float":
            try:
                new_value = float(self._inspector_text_buffer)
            except ValueError:
                self._inspector_cancel_text_edit()
                return False
        elif field and field.kind == "int":
            try:
                new_value = int(self._inspector_text_buffer)
            except ValueError:
                self._inspector_cancel_text_edit()
                return False

        new_json = set_component_field(entity_json, comp_kind, field_key, new_value)
        self._apply_component_entity_update(new_json)
        self._inspector_cancel_text_edit()
        return True

    def _apply_component_entity_update(self, new_entity_json: Dict[str, Any]) -> None:
        """Apply component entity JSON update, mark dirty, refresh runtime."""
        if not self.selected_entity:
            return

        # Get entity ID
        entity_id = self._get_entity_id_for_inspector()
        if not entity_id:
            return

        # Apply the change to scene data
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return

        entities = loaded_data.get("entities", [])
        for i, ent in enumerate(entities):
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == entity_id:
                    entities[i] = new_entity_json
                    break

        # Sync runtime sprite from new JSON
        self._sync_sprite_from_component_json(new_entity_json)

        self._mark_dirty()

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
        if not (self.hierarchy_active and self.selected_entity):
            return False
        if self.hierarchy_filter_active:
            return False

        current = getattr(self.selected_entity, "mesh_name", "")
        if not (isinstance(current, str) and current.strip()):
            current = self._get_display_name_for_sprite(self.selected_entity)

        self.hierarchy_rename_active = True
        self.hierarchy_filter_active = False
        self.hierarchy_rename_buffer = current
        return True

    def _cancel_hierarchy_rename(self) -> None:
        self.hierarchy_rename_active = False
        self.hierarchy_rename_buffer = ""

    def _commit_hierarchy_rename(self) -> bool:
        if not (self.hierarchy_rename_active and self.selected_entity):
            return False

        new_name = self.hierarchy_rename_buffer.strip()
        if not new_name:
            fallback_index = self._get_sprite_index(self.selected_entity)
            new_name = f"Entity#{(fallback_index or 0) + 1}"

        old_name = getattr(self.selected_entity, "mesh_name", "") or ""
        if new_name == old_name:
            self._cancel_hierarchy_rename()
            return False

        self._apply_entity_rename(self.selected_entity, new_name)
        self._push_command({
            "type": "RenameEntity",
            "before": old_name,
            "after": new_name,
            "current_name": new_name,
        })

        self._cancel_hierarchy_rename()
        self._refresh_hierarchy_list()
        self._refresh_inspector_items()
        logger.info("[Editor] Renamed entity to '%s'", new_name)
        return True

    def _apply_entity_rename(self, sprite: optional_arcade.arcade.Sprite, new_name: str) -> None:
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        entity_data["name"] = new_name
        setattr(sprite, "mesh_entity_data", entity_data)
        setattr(sprite, "mesh_name", new_name)
        self._hierarchy_name_cache[id(sprite)] = new_name

    def _select_hierarchy_item(self, index: int) -> None:
        if 0 <= index < len(self._cached_hierarchy_list):
            self.selected_entity = self._cached_hierarchy_list[index]
            self._reset_zone_selection_state()
            self._sync_zone_selection_state(self.selected_entity)
            self._cancel_hierarchy_rename()
            name = self._get_display_name_for_sprite(self.selected_entity)
            logger.info("[Editor] Selected from hierarchy: %s", name)
            # Also refresh inspector if needed
            self._refresh_inspector_items()

    def _handle_hierarchy_input(self, key: int, modifiers: int) -> bool:
        if self.hierarchy_rename_active:
            if key == optional_arcade.arcade.key.ENTER:
                return self._commit_hierarchy_rename()
            if key == optional_arcade.arcade.key.ESCAPE:
                self._cancel_hierarchy_rename()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.hierarchy_rename_buffer = self.hierarchy_rename_buffer[:-1]
                return True
            return False

        if self.hierarchy_filter_active:
            # Let text input handle it, but check for exit keys
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.ESCAPE):
                self.hierarchy_filter_active = False
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.hierarchy_filter = self.hierarchy_filter[:-1]
                self._refresh_hierarchy_list()
                return True
            return False # Let on_text handle typing

        if key == optional_arcade.arcade.key.UP:
            self.hierarchy_selection_index = max(0, self.hierarchy_selection_index - 1)
            self._select_hierarchy_item(self.hierarchy_selection_index)
            return True
        elif key == optional_arcade.arcade.key.DOWN:
            count = len(self._cached_hierarchy_list)
            if count > 0:
                self.hierarchy_selection_index = min(count - 1, self.hierarchy_selection_index + 1)
                self._select_hierarchy_item(self.hierarchy_selection_index)
            return True
        elif key == optional_arcade.arcade.key.ENTER or key == optional_arcade.arcade.key.SPACE:
            # Confirm selection (already done on move, but maybe close panel?)
            # For now just keep open
            return True
        elif key == optional_arcade.arcade.key.SLASH or (key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL)):
            self.hierarchy_filter_active = True
            return True

        return False

    def _handle_entity_panels_input(self, key: int, modifiers: int) -> bool:
        if not self.entity_panels_active:
            return False

        if self.entity_panels_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self._entity_panels_commit_text_edit()
            if key == optional_arcade.arcade.key.ESCAPE:
                self._entity_panels_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self.entity_panels_text_buffer = self.entity_panels_text_buffer[:-1]
                return True
            return True

        if self._search_focus == "outliner" and self.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                return self.backspace_search_text()
            return True

        if key == optional_arcade.arcade.key.TAB:
            if self.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
                self.entity_panels_focus = ENTITY_PANEL_FOCUS_INSPECTOR
            else:
                self.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
            return True

        if self.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
            if key == optional_arcade.arcade.key.UP:
                self.entity_panels_selection_index = max(0, self.entity_panels_selection_index - 1)
                return True
            if key == optional_arcade.arcade.key.DOWN:
                count = len(self._cached_entity_panels_list)
                if count:
                    self.entity_panels_selection_index = min(count - 1, self.entity_panels_selection_index + 1)
                return True
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                if self._search_focus == "outliner":
                    return True
                return self._entity_panels_select_current()
            if key == optional_arcade.arcade.key.SLASH or (key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL)):
                return self.focus_search_for_active_panel()
            return False

        if self.entity_panels_focus == ENTITY_PANEL_FOCUS_INSPECTOR:
            if not self.selected_entity:
                return False
            if key == optional_arcade.arcade.key.UP:
                self.entity_panels_inspector_index = max(0, self.entity_panels_inspector_index - 1)
                return True
            if key == optional_arcade.arcade.key.DOWN:
                count = len(ENTITY_PANEL_FIELDS)
                if count:
                    self.entity_panels_inspector_index = min(count - 1, self.entity_panels_inspector_index + 1)
                return True
            if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                field = ENTITY_PANEL_FIELDS[self.entity_panels_inspector_index]
                if field["kind"] != "float":
                    return False
                entity_data = self.window.scene_controller._ensure_entity_data_dict(self.selected_entity)
                current = self._entity_panels_numeric_value(entity_data, self.selected_entity, field["key"])
                delta = -1.0 if key == optional_arcade.arcade.key.LEFT else 1.0
                if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                    delta *= 10.0
                return self._entity_panels_apply_field_update(field["key"], current + delta)
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                field = ENTITY_PANEL_FIELDS[self.entity_panels_inspector_index]
                if field["kind"] not in ("string", "tags"):
                    return False
                entity_data = self.window.scene_controller._ensure_entity_data_dict(self.selected_entity)
                if field["kind"] == "tags":
                    initial = ", ".join(_normalize_entity_panel_tags(entity_data.get("tags")))
                else:
                    initial = str(entity_data.get(field["key"], "") or "")
                self._entity_panels_begin_text_edit(field["key"], initial)
                return True
            return False

        return False

    def _handle_scene_switcher_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.scene_switcher_active:
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self.scene_switcher_active = False
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            self.scene_switcher_query = self.scene_switcher_query[:-1]
            self._scene_switcher_clamp_index(len(self._scene_switcher_visible_options()))
            return True
        if key == optional_arcade.arcade.key.UP:
            self.scene_switcher_index = max(0, self.scene_switcher_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            count = len(self._scene_switcher_visible_options())
            if count:
                self.scene_switcher_index = min(count - 1, self.scene_switcher_index + 1)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return self._scene_switcher_open_selected()

        return True

    def _handle_scene_browser_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.scene_browser_active:
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self.scene_browser_active = False
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            self.scene_browser_query = self.scene_browser_query[:-1]
            self._refresh_scene_browser_rows()
            self._scene_browser_clamp_index(len(self._scene_browser_rows()))
            return True
        if key == optional_arcade.arcade.key.UP:
            self.scene_browser_index = max(0, self.scene_browser_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            count = len(self._scene_browser_rows())
            if count:
                self.scene_browser_index = min(count - 1, self.scene_browser_index + 1)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return self._scene_browser_open_selected()

        return True

    def _handle_entity_panels_text_input(self, text: str) -> bool:
        if not self.entity_panels_active:
            return False
        if self.entity_panels_text_edit_active:
            if text and text.isprintable():
                self.entity_panels_text_buffer += text
                return True
            return False
        if self._search_focus == "outliner" and self.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
            return self.append_search_text(text)
        return False

    def _handle_scene_switcher_text_input(self, text: str) -> bool:
        if not self.scene_switcher_active:
            return False
        if text and text.isprintable():
            self.scene_switcher_query += text
            self._scene_switcher_clamp_index(len(self._scene_switcher_visible_options()))
            return True
        return False

    def _handle_scene_browser_text_input(self, text: str) -> bool:
        if not self.scene_browser_active:
            return False
        if text and text.isprintable():
            self.scene_browser_query += text
            self._refresh_scene_browser_rows()
            self._scene_browser_clamp_index(len(self._scene_browser_rows()))
            return True
        return False

    def handle_text_input(self, text: str) -> None:
        editor_input.handle_text_input(self, text)
