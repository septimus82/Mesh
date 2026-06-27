# ruff: noqa: F401

from __future__ import annotations

import copy
import importlib
import sys
import time as _time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import engine.optional_arcade as optional_arcade
from engine.editor.editor_file_ops_controller import EditorFileOpsController
from engine.logging_tools import get_logger
from engine.repo_root import get_repo_root

from .behaviours import get_behaviour_param_defs as _get_behaviour_param_defs
from .behaviours.utils import (
    HITBOX_CANONICAL,
    HITBOX_CLASSNAMES,
    TRIGGER_ZONE_CANONICAL,
    TRIGGER_ZONE_CLASSNAMES,
    ZONE_TARGET_HITBOX,
    ZONE_TARGET_TRIGGER,
)
from .editor_palette import DEFAULT_PREFAB_PATH
from .editor_runtime import ops as editor_ops
from .import_tools import repair_package_submodule_attr

if TYPE_CHECKING:
    from engine.editor.editor_animation_controller import EditorAnimationController
    from engine.editor.editor_asset_browser_controller import EditorAssetBrowserController
    from engine.editor.editor_command_dispatch_controller import (
        EditorCommandDispatchController,
    )
    from engine.editor.editor_cursor_controller import EditorCursorController
    from engine.editor.editor_dialogue_controller import EditorDialogueController
    from engine.editor.editor_dock_controller import EditorDockController
    from engine.editor.editor_draw_controller import EditorDrawController
    from engine.editor.editor_entity_panels_controller import EditorEntityPanelsController
    from engine.editor.editor_find_actions_controller import EditorFindActionsController
    from engine.workspace_settings import WorkspaceSettings

    from .editor.editor_duplicate_controller import EditorDuplicateController
    from .editor.editor_entity_ops_controller import EditorEntityOpsController
    from .editor.editor_gizmo_feedback import GizmoFeedbackState
    from .editor.editor_hd2d_controller import EditorHd2dController
    from .editor.editor_hierarchy_controller import EditorHierarchyController
    from .editor.editor_history_controller import EditorHistoryController
    from .editor.editor_inspector_controller import EditorInspectorController
    from .editor.editor_keymap_controller import EditorKeymapController
    from .editor.editor_lights_controller import EditorLightsController
    from .editor.editor_live_ops_controller import EditorLiveOpsController
    from .editor.editor_marquee_controller import EditorMarqueeController
    from .editor.editor_overlay_controller import EditorOverlayController
    from .editor.editor_palette_controller import EditorPaletteController
    from .editor.editor_play_controller import EditorPlayController
    from .editor.editor_prefab_controller import EditorPrefabController
    from .editor.editor_problems_actions_controller import EditorProblemsActionsController
    from .editor.editor_problems_controller import ProblemsController
    from .editor.editor_project_explorer_actions_controller import EditorProjectExplorerActionsController
    from .editor.editor_project_explorer_controller import ProjectExplorerController
    from .editor.editor_search_controller import EditorSearchController
    from .editor.editor_shape_controller import EditorShapeController
    from .editor.editor_tile_controller import EditorTileController
    from .editor.editor_undo_controller import EditorUndoController
    from .editor.keymap_override_model import ScopedOverrides
    from .game import GameWindow

# Import from extracted modules
from .editor import state as _editor_state
from .editor.editor_controller_bootstrap import (
    bootstrap_browser_state as _bootstrap_browser_state,
)
from .editor.editor_controller_bootstrap import (
    bootstrap_dependencies as _bootstrap_dependencies,
)
from .editor.editor_controller_bootstrap import (
    bootstrap_overlay_state as _bootstrap_overlay_state,
)
from .editor.editor_controller_bootstrap import (
    bootstrap_runtime_state as _bootstrap_runtime_state,
)
from .editor.editor_controller_content_panels_bridge import (
    bind_content_panels_bridge_methods as _bind_content_panels_bridge_methods,
)
from .editor.editor_controller_diagnostics_bridge import (
    bind_diagnostics_bridge_methods as _bind_diagnostics_bridge_methods,
)
from .editor.editor_controller_entity_panels_bridge import (
    bind_entity_panels_bridge_methods as _bind_entity_panels_bridge_methods,
)
from .editor.editor_controller_find_browser_bridge import (
    bind_find_browser_bridge_methods as _bind_find_browser_bridge_methods,
)
from .editor.editor_controller_input_routing import (
    bind_input_routing_methods as _bind_input_routing_methods,
)
from .editor.editor_controller_project_explorer_bridge import (
    bind_project_explorer_bridge_methods as _bind_project_explorer_bridge_methods,
)
from .editor.editor_controller_scene_ops import (
    bind_scene_ops_methods as _bind_scene_ops_methods,
)
from .editor.editor_controller_ui_state import (
    bind_ui_state_methods as _bind_ui_state_methods,
)
from .editor.editor_controller_workspace_lifecycle import (
    bind_workspace_lifecycle_methods as _bind_workspace_lifecycle_methods,
)
from .editor.editor_scene_ops import EditorSceneOpsController
from .editor.editor_selection_controller import EditorSelectionController
from .editor.editor_session_controller import EditorSessionController
from .editor.editor_ui_flow_controller import EditorUIFlowController
from .editor.editor_workspace_controller import EditorWorkspaceController
from .editor.input_router import bind_input_router_methods as _bind_input_router_methods
from .editor.overlays_modals import (
    bind_overlays_modals_methods as _bind_overlays_modals_methods,
)
from .editor.selection_clipboard import (
    bind_selection_clipboard_methods as _bind_selection_clipboard_methods,
)
from .editor.state import (
    EditorDirtyState,
)

logger = get_logger(__name__)

ZONE_BEHAVIOUR_CANONICAL = TRIGGER_ZONE_CANONICAL | HITBOX_CANONICAL
ZONE_BEHAVIOUR_CLASSNAMES = TRIGGER_ZONE_CLASSNAMES | HITBOX_CLASSNAMES
TOOL_MODE_MOVE = _editor_state.TOOL_MODE_MOVE
TOOL_MODE_PATH = _editor_state.TOOL_MODE_PATH
TOOL_MODE_ZONE = _editor_state.TOOL_MODE_ZONE
get_behaviour_param_defs = _get_behaviour_param_defs
time = _time


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
                    forwarded = _coerce_prefab_palette_rows(fn(*args, **kwargs))
                    if forwarded is not None:
                        return forwarded
        except Exception:
            logger.debug(
                "SWALLOW[%s] %s",
                "EDIT-001",
                "engine/editor_controller.py pass-only blanket swallow",
                exc_info=True,
            )
    from .editor_palette import load_prefab_palette as _impl

    loaded = _coerce_prefab_palette_rows(_impl(*args, **kwargs))
    return loaded if loaded is not None else []


def get_prefab_palette() -> list[dict[str, Any]]:
    current = sys.modules.get(__name__)
    if current is not None:
        try:
            current_id = getattr(current, "_MODULE_INSTANCE_ID", None)
            if current_id is not _MODULE_INSTANCE_ID:
                fn = getattr(current, "get_prefab_palette", None)
                if callable(fn) and fn is not get_prefab_palette:
                    forwarded = _coerce_prefab_palette_rows(fn())
                    if forwarded is not None:
                        return forwarded
        except Exception:
            logger.debug(
                "SWALLOW[%s] %s",
                "EDIT-002",
                "engine/editor_controller.py pass-only blanket swallow",
                exc_info=True,
            )

    global PREFAB_PALETTE
    if PREFAB_PALETTE is None:
        PREFAB_PALETTE = load_prefab_palette()
    return PREFAB_PALETTE


def _coerce_prefab_palette_rows(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        rows.append(entry)
    return rows

class EditorModeController:
    _file_ops_ctl: EditorFileOpsController
    _ui_flow_ctl: EditorUIFlowController
    _selection_ctl: EditorSelectionController
    _scene_ops: EditorSceneOpsController
    _workspace_ctl: EditorWorkspaceController
    search: EditorSearchController
    find_actions: EditorFindActionsController
    asset_browser: EditorAssetBrowserController
    project_explorer: ProjectExplorerController
    project_explorer_actions: EditorProjectExplorerActionsController
    history: EditorHistoryController
    problems: ProblemsController
    problems_actions: EditorProblemsActionsController
    dialogue: EditorDialogueController
    animation: EditorAnimationController
    tile: EditorTileController
    inspector: EditorInspectorController
    entity_panels_controller: EditorEntityPanelsController
    undo: EditorUndoController
    lights: EditorLightsController
    live_ops: EditorLiveOpsController
    play: EditorPlayController
    palette: EditorPaletteController
    hd2d: EditorHd2dController
    duplicate: EditorDuplicateController
    marquee: EditorMarqueeController
    keymap: EditorKeymapController
    draw: EditorDrawController
    overlay: EditorOverlayController
    prefab: EditorPrefabController
    shape: EditorShapeController
    entity_ops: EditorEntityOpsController
    command_dispatch: EditorCommandDispatchController
    dock: EditorDockController
    cursor: EditorCursorController
    hierarchy: EditorHierarchyController
    entity_panels_active: bool
    entity_panels_focus: str
    scene_switcher_active: bool
    scene_browser_active: bool
    asset_browser_active: bool
    asset_browser_filter: str
    asset_browser_kind: str
    hierarchy_filter: str
    hierarchy_rename_buffer: str
    dialogue_edit_buffer: str
    animation_edit_buffer: str
    tile_panel_active: bool
    lights_tool_active: bool
    lights_selection: Optional[int]
    lights_dragging: bool
    lights_original_pos: Optional[tuple[float, float]]
    occluder_tool_active: bool
    occluder_dragging: bool
    occluder_drag_origin: Optional[tuple[float, float]]
    asset_place_active: bool
    selected_waypoint_index: int
    transform_mode: str
    snap_enabled: bool
    snap_mode: str
    shape_drag_index: int
    shape_snap_enabled: bool
    _entity_panels_selected_id: str | None
    _ghost_originals_enabled: bool
    _ghost_originals_alpha: int
    _ghost_originals_dim_scale: float
    _hd2d_default_preset_id: str | None
    _hd2d_batch_radius_px: int
    _menu_active: Optional[str]
    _menu_hover_item_id: Optional[str]
    _context_menu_x: float
    _context_menu_y: float
    _context_menu_hover_id: Optional[str]
    _multiselect_drag_starts: Dict[str, tuple[float, float]]
    _move_preview_delta_xy: Tuple[float, float] | None
    _rotate_drag_active: bool
    _rotate_preview_delta_deg: float | None
    _scale_drag_active: bool
    _scale_preview_factor: float | None
    _transform_drag_mouse_start: Tuple[float, float] | None
    _transform_drag_pivot: Tuple[float, float] | None
    _transform_drag_start_rots: Dict[str, float]
    _transform_drag_start_scales: Dict[str, float]
    _transform_snap_active: bool

    def __init__(self, window: GameWindow):
        self.window = window
        self.active: bool = False
        self.selected_entity: Optional[optional_arcade.arcade.Sprite] = None
        self.entity_dragging: bool = False
        self.entity_drag_start_pos: Optional[tuple[float, float]] = None
        self.grid_size: float = 16.0
        self._repo_root_override: Path | None = None  # For testing: set to a Path to override get_repo_root
        # _keymap_overrides - DELEGATED to EditorKeymapController
        # Panel/controller wiring (set by EditorPanelsController)
        self.ui_layers: Any = None
        self.keybinds: Any = None
        self.keybinds_overlay: Any = None
        self.confirm_modal: Any = None
        self.confirm_modal_overlay: Any = None
        self.project_context_menu_overlay: Any = None
        self.session: EditorSessionController
        _bootstrap_dependencies(self)
        _bootstrap_browser_state(self)

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
        _bootstrap_runtime_state(self)
        self._menu_hover_item_id: Optional[str] = None
        self._context_menu_hover_id: Optional[str] = None
        self.session.set_tile_paint_active(self.tile_panel_active)

        self._workspace_ctl.load_on_startup()
        self.load_keymap_overrides()
        _bootstrap_overlay_state(self)

    # -- Sub-Controller Accessors --

    @property
    def file_ops(self) -> EditorFileOpsController:
        return self._file_ops_ctl

    @property
    def ui_flow(self) -> EditorUIFlowController:
        return self._ui_flow_ctl

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)

    @property
    def selection(self) -> EditorSelectionController:
        return self._selection_ctl

    @property
    def scene_ops(self) -> EditorSceneOpsController:
        return self._scene_ops

    @property
    def workspace(self) -> EditorWorkspaceController:
        return self._workspace_ctl

    # -- EditorUiFlowHost Protocol Implementation --

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
    def undo_stack(self) -> List[Dict[str, Any]]:
        return self.undo.undo_stack

    @undo_stack.setter
    def undo_stack(self, value: List[Dict[str, Any]]) -> None:
        self.undo.set_undo_stack(value)

    @property
    def redo_stack(self) -> List[Dict[str, Any]]:
        return self.undo.redo_stack

    @redo_stack.setter
    def redo_stack(self, value: List[Dict[str, Any]]) -> None:
        self.undo.set_redo_stack(value)

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

    def _get_repo_root(self) -> Path:
        """Get repo root, allowing override for testing."""
        if self._repo_root_override is not None:
            return self._repo_root_override
        return get_repo_root()





    def _tick_workspace_autosave(self, now_ns: int | None = None) -> None:
        self._workspace_ctl.tick_autosave(delay_ns=WORKSPACE_AUTOSAVE_DELAY_NS, now_ns=now_ns)


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

    def run_editor_action(self, action_id: str) -> bool:
        """Run a registered editor action by id."""
        from engine.editor.editor_actions import run_editor_action  # noqa: PLC0415

        return run_editor_action(action_id, self, self.window)

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

    # Dialogue / Animation / Tile → editor_controller_content_panels_bridge.py

    # Lights tool / Inspector / Prefab → editor_controller_entity_panels_bridge.py

    def save_current_scene(self) -> None:
        self._flush_workspace_autosave()
        editor_ops.save_current_scene(self)

    # Problems / Project Explorer → editor_controller_project_explorer_bridge.py

    def place_entity_at_mouse(self, x: float, y: float) -> None:
        editor_ops.place_entity_at_mouse(self, x, y)

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
    def _keymap_overrides(self) -> "ScopedOverrides":
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

    def apply_live_op(self, op: dict[str, Any]) -> dict[str, Any]:
        """Apply one AI-style operation to the live editor scene."""
        return self.live_ops.apply_live_op(op)

    def read_live_scene(self, compact: bool = False) -> dict[str, Any]:
        """Return the current live editor scene snapshot for AI read-back."""
        from engine.editor.editor_selection_model import selected_entity_ids  # noqa: PLC0415

        scene_controller = getattr(self.window, "scene_controller", None)
        snapshot = scene_controller.build_scene_snapshot(compact=compact) if scene_controller is not None else {}
        return {
            "scene": snapshot,
            "current_scene_path": str(getattr(scene_controller, "current_scene_path", "") or ""),
            "dirty": bool(self.scene_dirty),
            "revision": int(getattr(self, "content_revision", 0)),
            "selected_entity_ids": selected_entity_ids(self),
        }

    def _mark_dirty(self) -> None:
        self.content_revision = int(getattr(self, "content_revision", 0)) + 1
        self.scene_dirty = True
        self.dirty_state.is_dirty = True

    def _mark_clean(self) -> None:
        self.scene_dirty = False
        self.dirty_state.is_dirty = False

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
                logger.debug("Failed to parse background planes during undo/redo", exc_info=True)

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

    # -------------------------------------------------------------------------
    # Find Everything (Ctrl+K)
    # -------------------------------------------------------------------------

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

    # Find Everything / Asset Browser → editor_controller_find_browser_bridge.py

    # Project Explorer / Undo History / Problems → editor_controller_project_explorer_bridge.py











    def _refresh_hierarchy_list(self) -> None:
        self.hierarchy.refresh_hierarchy_list()

    def _build_hierarchy_list(self) -> List[optional_arcade.arcade.Sprite]:
        return self.hierarchy.build_hierarchy_list()

    # Entity Panels / Inspector / Prefab → editor_controller_entity_panels_bridge.py

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

    # Entity Panels tail / Inspector / Component Inspector → editor_controller_entity_panels_bridge.py

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


_bind_input_router_methods(EditorModeController)
_bind_selection_clipboard_methods(EditorModeController)
_bind_overlays_modals_methods(EditorModeController)

_bind_workspace_lifecycle_methods(EditorModeController)
_bind_ui_state_methods(EditorModeController)
_bind_scene_ops_methods(EditorModeController)
_bind_diagnostics_bridge_methods(EditorModeController)
_bind_input_routing_methods(EditorModeController)
_bind_entity_panels_bridge_methods(EditorModeController)
_bind_find_browser_bridge_methods(EditorModeController)
_bind_content_panels_bridge_methods(EditorModeController)
_bind_project_explorer_bridge_methods(EditorModeController)
