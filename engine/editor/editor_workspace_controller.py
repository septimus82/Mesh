"""Editor workspace controller logic.

Handles:
- Workspace save/load (workspace.json)
- Recent project/scene tracking (controller-local)
- Debounced autosave orchestration

Inventory (read/write locations + triggers):
- workspace.json (engine.workspace_settings): loaded on editor startup/load, saved on autosave/explicit save
- projects.json (engine.projects): not used by editor_controller directly; UI menus still call projects.py
- user_settings.json (engine.runtime_settings_storage): not used by editor_controller (runtime handles)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import TYPE_CHECKING

from engine.editor.editor_modal_state_query import is_scene_browser_active
from engine.editor.editor_workspace_model import WorkspaceSnapshot
from engine.editor.safe_mode import is_safe_mode_enabled
from engine.editor.workspace_autosave_model import (
    AutosaveState,
    mark_flushed,
    schedule_change,
    should_flush,
)
from engine.logging_tools import get_logger
from engine.projects import add_recent_project, get_recent_projects, remove_recent_project, set_last_project
from engine.runtime_settings import ensure_runtime_settings
from engine.runtime_settings_storage import load_runtime_settings, resolve_runtime_settings_path, save_runtime_settings
from engine.swallowed_exceptions import _log_swallow
from engine.workspace_settings import WorkspaceSettings, load_workspace, save_workspace

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

SCENE_SWITCHER_RECENT_LIMIT = 10


class EditorWorkspaceController:
    """Manages workspace state, settings, and file operations."""

    def __init__(self, controller: EditorModeController) -> None:
        self._editor = controller
        try:
            setattr(self._editor.window, "_on_recent_scene_recorded", self._on_recent_scene_recorded)
        except Exception:
            _log_swallow("EDIT-001", "engine/editor/editor_workspace_controller.py pass-only blanket swallow")
            pass
        self.workspace_data: WorkspaceSettings = WorkspaceSettings()
        self.recent_projects: list[str] = []
        self.recent_scenes: list[str] = []
        self._autosave_state = AutosaveState()

    def load_on_startup(self) -> None:
        self.load_workspace()
        if self._is_web_runtime() or self._should_skip_load_for_tests():
            return
        self._load_editor_ui_state()
        if is_safe_mode_enabled():
            return
        cfg = getattr(self._editor.window, "engine_config", None)
        if getattr(cfg, "_mesh_editor_scene_override", None):
            return
        self._load_editor_session_state()

    def load_workspace_settings(self) -> None:
        """Compatibility shim for legacy call sites."""
        self.load_workspace()

    def save_workspace_settings(self) -> None:
        """Compatibility shim for legacy call sites."""
        self.save_workspace()

    def load_workspace(self) -> None:
        if self._is_web_runtime():
            return
        if self._should_skip_load_for_tests():
            return
        repo_root = self._get_repo_root()
        settings = load_workspace(repo_root)
        self.workspace_data = settings
        self._apply_workspace_settings(settings)
        self._load_recents_from_settings(settings)

    def save_workspace(self) -> None:
        if self._is_web_runtime():
            self._autosave_state = mark_flushed(self._autosave_state, time.monotonic_ns())
            return
        repo_root = self._get_repo_root()
        settings = self._build_workspace_settings()
        self.workspace_data = settings
        save_workspace(repo_root, settings)
        self._autosave_state = mark_flushed(self._autosave_state, time.monotonic_ns())

    def schedule_autosave(self, now_ns: int | None = None) -> None:
        now = time.monotonic_ns() if now_ns is None else int(now_ns)
        self._autosave_state = schedule_change(self._autosave_state, now)

    def tick_autosave(self, *, delay_ns: int, now_ns: int | None = None) -> None:
        if not self._autosave_state.pending:
            return
        if self._is_text_input_active():
            return
        now = time.monotonic_ns() if now_ns is None else int(now_ns)
        if not should_flush(self._autosave_state, now, delay_ns):
            return
        self.save_workspace()

    def flush_autosave(self) -> None:
        if not self._autosave_state.pending:
            return
        self.save_workspace()

    def add_recent_project(self, path: str) -> None:
        """Add a project path to recent projects list."""
        if not path:
            return
        normalized = str(path).replace("\\", "/")
        if normalized in self.recent_projects:
            self.recent_projects.remove(normalized)
        self.recent_projects.insert(0, normalized)
        if len(self.recent_projects) > 10:
            self.recent_projects = self.recent_projects[:10]

    def add_recent_scene(self, path: str) -> None:
        """Add a scene path to recent scenes list."""
        if not path:
            return
        normalized = str(path).replace("\\", "/")
        if normalized in self.recent_scenes:
            self.recent_scenes.remove(normalized)
        self.recent_scenes.insert(0, normalized)
        if len(self.recent_scenes) > SCENE_SWITCHER_RECENT_LIMIT:
            self.recent_scenes = self.recent_scenes[:SCENE_SWITCHER_RECENT_LIMIT]

    def get_snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            settings=self.workspace_data,
            recent_projects=tuple(self.recent_projects),
            last_project=None,
        )

    def record_project_open(self, root: str) -> None:
        if not root:
            return
        add_recent_project(root)
        set_last_project(root)

    def remove_recent_project(self, root: str) -> None:
        if not root:
            return
        remove_recent_project(root)

    def get_recent_projects(self) -> list[str]:
        return get_recent_projects()

    def load_user_settings(self) -> None:
        if self._is_web_runtime():
            return
        window = self._editor.window
        settings = ensure_runtime_settings(window)
        path = getattr(window, "runtime_settings_path", None)
        loaded = load_runtime_settings(path, base=settings)
        window.runtime_settings = loaded
        loaded.apply(window)

    def save_user_settings(self) -> None:
        if self._is_web_runtime():
            return
        window = self._editor.window
        settings = ensure_runtime_settings(window)
        path = getattr(window, "runtime_settings_path", None)
        if path is None:
            path = resolve_runtime_settings_path(path)
        save_runtime_settings(path, settings)

    def save_hd2d_batch_radius(self, radius: int) -> None:
        editor = self._editor
        repo_root_getter = getattr(editor, "_get_repo_root", None)
        if not callable(repo_root_getter):
            return
        try:
            repo_root = repo_root_getter()
            settings = load_workspace(repo_root)
            updated = dataclass_replace(settings, hd2d_batch_radius_px=radius)
            save_workspace(repo_root, updated)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-002", "engine/editor/editor_workspace_controller.py pass-only blanket swallow")
            pass

    def _apply_workspace_settings(self, settings: WorkspaceSettings) -> None:
        editor = self._editor
        editor.entity_panels_active = settings.entity_panels_open
        if settings.command_palette_open:
            editor.panels.open_command_palette()
        else:
            editor.panels.close_command_palette()
        editor.scene_switcher_active = settings.scene_switcher_open
        editor.scene_browser_active = settings.scene_browser_open
        editor.asset_browser_active = False
        editor.project_explorer.set_query(getattr(settings, "project_search", ""))
        editor.search.set_outliner_search(settings.outliner_search, autosave=False)
        editor.search.set_assets_search(settings.assets_search)
        editor.asset_browser_filter = settings.asset_browser_filter
        editor.asset_browser_kind = settings.asset_browser_kind
        editor.history.set_search_text(settings.history_search)
        editor.problems.set_query(settings.problems_search)
        editor.project_explorer.set_recents(getattr(settings, "project_explorer_recents", []))
        editor.entity_panels_focus = settings.outliner_focus

        editor.dock.set_left_tab(settings.left_dock_tab, force=True)
        editor.dock.set_right_tab(settings.right_dock_tab, force=True)

        editor.dock.set_left_width(settings.dock_left_w)
        editor.dock.set_right_width(settings.dock_right_w)
        editor.dock.set_left_collapsed(settings.dock_left_collapsed)
        editor.dock.set_right_collapsed(settings.dock_right_collapsed)
        editor.dock.set_viewport_maximized(settings.viewport_maximized)

        editor._ghost_originals_enabled = settings.ghost_originals_enabled
        editor._ghost_originals_alpha = settings.ghost_originals_alpha
        editor._ghost_originals_dim_scale = settings.ghost_originals_dim_scale

        editor._hd2d_default_preset_id = settings.hd2d_default_preset_id
        editor._hd2d_batch_radius_px = getattr(settings, "hd2d_batch_radius_px", 96)
        debug_panels = getattr(editor, "debug_panels", None)
        if debug_panels is not None and hasattr(debug_panels, "apply_workspace_settings"):
            debug_panels.apply_workspace_settings(settings)

        if editor.asset_browser_active:
            editor.refresh_asset_browser()

        editor.lights_tool_active = False
        editor.occluder_tool_active = False

        if settings.last_scene_id:
            current_key = getattr(editor.window, "current_scene_key", None)
            if current_key != settings.last_scene_id:
                load_fn = getattr(editor.window, "load_scene", None)
                if callable(load_fn):
                    try:
                        load_fn(settings.last_scene_id)
                        if settings.last_camera_center and hasattr(editor.window, "camera"):
                            editor.window.camera.position = (
                                settings.last_camera_center[0],
                                settings.last_camera_center[1],
                            )
                    except Exception as exc:  # noqa: BLE001  # REASON: editor fallback isolation
                        _log_swallow("EWSP-001", "engine/editor/editor_workspace_controller.py blanket swallow", once=True)
                        logger.warning(
                            "Failed to restore workspace scene %s: %s",
                            settings.last_scene_id,
                            exc,
                        )
        elif settings.last_camera_center and hasattr(editor.window, "camera"):
            editor.window.camera.position = (
                settings.last_camera_center[0],
                settings.last_camera_center[1],
            )

    def _build_workspace_settings(self) -> WorkspaceSettings:
        editor = self._editor
        tool = None
        if editor.lights_tool_active:
            tool = "light"
        elif editor.occluder_tool_active:
            tool = "occluder"

        scene_id = getattr(editor.window, "current_scene_key", None)
        cam_center = None
        cam = getattr(editor.window, "camera", None)
        if cam is not None:
            cam_center = list(cam.position)

        snapshot = editor.dock.get_snapshot()

        debug_panels = getattr(editor, "debug_panels", None)

        return WorkspaceSettings(
            entity_panels_open=editor.entity_panels_active,
            command_palette_open=editor.panels.is_command_palette_open(),
            scene_switcher_open=editor.scene_switcher_active,
            scene_browser_open=is_scene_browser_active(editor),
            asset_browser_open=editor.asset_browser_active,
            asset_browser_filter=editor.asset_browser_filter,
            asset_browser_kind=editor.asset_browser_kind,
            project_search=editor.project_explorer.search_query,
            outliner_search=editor.search.get_outliner_search(),
            assets_search=editor.search.get_assets_search(),
            history_search=editor.history.get_search_text(),
            problems_search=editor.problems.query,
            light_occluder_tool=tool,
            outliner_focus=editor.entity_panels_focus,
            last_scene_id=scene_id,
            last_camera_center=cam_center,
            left_dock_tab=snapshot.left_tab,
            right_dock_tab=snapshot.right_tab,
            dock_left_w=editor.dock.get_left_width(),
            dock_right_w=editor.dock.get_right_width(),
            dock_left_collapsed=editor.dock.get_left_collapsed(),
            dock_right_collapsed=editor.dock.get_right_collapsed(),
            viewport_maximized=editor.dock.get_viewport_maximized(),
            ghost_originals_enabled=editor._ghost_originals_enabled,
            ghost_originals_alpha=editor._ghost_originals_alpha,
            ghost_originals_dim_scale=editor._ghost_originals_dim_scale,
            project_explorer_recents=editor._project_explorer_recent_payloads(),
            hd2d_default_preset_id=editor._hd2d_default_preset_id,
            debug_event_type_filter=debug_panels.get_event_type_filter() if debug_panels is not None else "",
            debug_event_entity_id=debug_panels.get_event_entity_id_filter() if debug_panels is not None else "",
            debug_event_limit=debug_panels.get_event_limit() if debug_panels is not None else 20,
        )

    def _load_recents_from_settings(self, settings: WorkspaceSettings) -> None:
        recents = getattr(settings, "recent_projects", None)
        if isinstance(recents, list):
            self.recent_projects = [str(r) for r in recents if isinstance(r, str)]
        scene_recents = getattr(settings, "recent_scenes", None)
        if isinstance(scene_recents, list):
            self.recent_scenes = [str(r) for r in scene_recents if isinstance(r, str)]

    def _is_web_runtime(self) -> bool:
        return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"

    def _should_skip_load_for_tests(self) -> bool:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        return getattr(self._editor, "_repo_root_override", None) is None

    def _get_repo_root(self) -> Path:
        getter = getattr(self._editor, "_get_repo_root", None)
        if callable(getter):
            root = getter()
            if isinstance(root, Path):
                return root
            if root is not None:
                return Path(root)
        root = getattr(self._editor.window, "repo_root", None)
        if isinstance(root, Path):
            return root
        from engine.repo_root import get_repo_root  # noqa: PLC0415

        return get_repo_root()

    def _is_text_input_active(self) -> bool:
        from engine.editor_runtime import input as editor_input  # noqa: PLC0415

        fn = getattr(editor_input, "_is_text_input_active", None)
        if not callable(fn):
            return False
        try:
            return bool(fn(self._editor))
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EWSP-002", "engine/editor/editor_workspace_controller.py blanket swallow", once=True)
            return False

    def _load_editor_ui_state(self) -> None:
        try:
            from engine.editor.editor_ui_state import (  # noqa: PLC0415
                apply_editor_ui_state,
                load_editor_ui_state,
                resolve_editor_ui_state_path,
            )

            repo_root = self._get_repo_root()
            state_path = resolve_editor_ui_state_path(repo_root=repo_root)
            if not state_path.exists():
                return
            state = load_editor_ui_state(path=state_path)
            apply_editor_ui_state(self._editor, state)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EWSP-003", "engine/editor/editor_workspace_controller.py blanket swallow", once=True)
            return

    def _load_editor_session_state(self) -> None:
        try:
            from engine.editor.editor_session_state import (  # noqa: PLC0415
                apply_camera_state_for_editor,
                get_camera_for_scene,
                load_editor_session_state,
                resolve_editor_session_state_path,
            )

            repo_root = self._get_repo_root()
            state_path = resolve_editor_session_state_path(repo_root=repo_root)
            if not state_path.exists():
                return
            state = load_editor_session_state(path=state_path)
            scene_path = str(state.last_scene_path or "").strip()
            if not scene_path:
                return
            target = Path(scene_path)
            if not target.is_absolute():
                target = repo_root / target
            if not target.exists():
                return
            scene_controller = getattr(self._editor.window, "scene_controller", None)
            current_scene = str(getattr(scene_controller, "current_scene_path", "") or "").strip()
            if current_scene == scene_path:
                return
            load_fn = getattr(self._editor.window, "load_scene", None)
            if callable(load_fn):
                load_fn(scene_path)
                camera_state = get_camera_for_scene(state, scene_path)
                if camera_state is not None:
                    apply_camera_state_for_editor(self._editor, camera_state)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EWSP-004", "engine/editor/editor_workspace_controller.py blanket swallow", once=True)
            return

    def _on_recent_scene_recorded(self, scene_path: str) -> None:
        try:
            from engine.editor.editor_session_state import save_editor_session_state_for_editor  # noqa: PLC0415

            save_editor_session_state_for_editor(self._editor, scene_path)
        except Exception:
            _log_swallow("EWSP-005", "engine/editor/editor_workspace_controller.py blanket swallow", once=True)
            return
