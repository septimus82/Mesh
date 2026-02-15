"""Arcade window and runtime glue for the Mesh engine prototype.

This module contains the main GameWindow class which serves as the central
facade for the entire Mesh Engine. It orchestrates all subsystems and provides
the main game loop.

Architecture:
    GameWindow follows the Facade pattern, delegating responsibilities to
    specialized controllers while providing a unified interface:

    - **SceneController**: Entity management, layer rendering, scene loading
    - **CameraController**: Viewport, zoom, shake, camera areas
    - **InputController**: Keyboard/mouse/gamepad input handling
    - **UIController**: UI overlays, HUD, menus, dialogue
    - **EditorController**: In-game editor mode (dev only)
    - **ConsoleController**: Developer console commands
    - **LightManager**: Dynamic lighting and shadows
    - **AudioManager**: Music and sound effects

Game Loop:
    Each frame, GameWindow.on_update() and on_draw() are called:

    1. **on_update(dt)**:
        - Process input
        - Update behaviours (pre_update -> update -> late_update)
        - Update physics/collisions
        - Process pending scene changes
        - Tick animations, particles, day/night cycle
        - Deliver queued events

    2. **on_draw()**:
        - Clear screen
        - Draw background layers/parallax
        - Draw tilemap
        - Draw entities (sorted by depth)
        - Apply lighting
        - Draw UI overlays

Configuration:
    Engine settings are loaded from config.json::

        {
            "title": "My Game",
            "width": 1280,
            "height": 720,
            "fullscreen": false,
            "start_scene": "scenes/main.json",
            "lighting_enabled": true
        }

Example Usage::

    from engine.config import load_config
    from engine.game import GameWindow

    config = load_config("config.json")
    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        config=config
    )
    window.run()

See Also:
    - :class:`SceneController` for entity and scene management
    - :class:`CameraController` for viewport control
    - :mod:`engine.behaviours` for entity logic components
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Sequence

import engine.optional_arcade

from .ai_debug_overlay import AIDebugOverlay
from .animation import AnimationFactory
from .assets import AssetManager
from .audio import AudioManager
from .behaviours import load_builtin_behaviours
from .camera_controller import CameraArea, CameraController
from .config import EngineConfig
from .console_controller import ConsoleController
from .constants import (
    DEBUG_STRICT_EXCEPTIONS,
    EVENT_COLLECTIBLE_PICKED,
    EVENT_DAMAGE_APPLIED,
    EVENT_LEVEL_UP,
)
from .cutscene_controller import CutsceneController
from .day_night import DayNightCycle
from .editor_controller import EditorModeController
from .encounter_debug import get_encounter_debug_lines
from .encounter_report import compute_current_scene_encounter_report
from .events import MeshEvent, MeshEventBus
from .event_runtime.emit import emit_event as emit_event_normalized
from .game_state_controller import GameState, GameStateController
from .fx_presets import build_fx_preset_registry
from .input import InputManager
from .input_controller import InputController
from .lighting import LightManager
from .logging_tools import get_logger
from .migrations import migrate_payload
from .particles import ParticleManager
from .paths import resolve_path
from .perf import PerfStats
from .render_queue import SpriteRenderQueue
from .render_queue_arcade import ArcadeSpriteBatcher
from .quests import QuestManager
from .runtime_settings import ensure_runtime_settings, RuntimeSettings
from .runtime_settings_storage import load_runtime_settings, resolve_runtime_settings_path
from .save_manager import SaveManager
from .scene_controller import SceneController
from .scene_loader import SceneLoader
from .tilemap import TilemapManager
from .ui import (
    CommandPaletteOverlay,
    CaptureOverlay,
    DemoCompleteOverlay,
    DevBrowserOverlay,
    EntityPaintOverlay,
    EntitySelectOverlay,
    EncounterDebugOverlay,
    GameOverScreen,
    GoldenSliceDemoHUDStripOverlay,
    GoldenSliceVariantPickerOverlay,
    HD2DPreviewIndicatorOverlay,
    HelpOverlay,
    InspectorOverlay,
    InteractPromptOverlay,
    MainMenuOverlay,
    HotReloadOverlay,
    ObjectiveTrackerOverlay,
    PauseMenu,
    PlayerHUD,
    SceneDirtyOverlay,
    PhysicsBroadphaseOverlay,
    SceneInspectorOverlay,
    SettingsOverlay,
    TilePaintOverlay,
    UIElement,
    maybe_trigger_demo_complete_endcap,
)
from .ui_controller import UIController
from .world_controller import WorldController
from .ui_overlays.transition_fade import TransitionFadeOverlay
from .ui_overlays.light_occluder_editor import LightOccluderEditorOverlay
from .ui_overlays.fog_overlay import FogOverlay
from .ui_overlays.entity_panels_overlay import EntityPanelsOverlay
from .ui_overlays.editor_status_bar_overlay import EditorStatusBarOverlay
from .ui_overlays.editor_shell_overlay import EditorShellOverlay
from .editor.editor_cursor_hint_overlay import EditorCursorHintOverlay
from .ui_overlays.scene_switcher_overlay import SceneSwitcherOverlay
from .ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from .ui_overlays.project_explorer_overlay import ProjectExplorerOverlay
from .ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from .ui_overlays.undo_history_overlay import UndoHistoryOverlay
from .ui_overlays.problems_panel_overlay import ProblemsPanelOverlay
from .ui_overlays.debug_panels_overlay import DebugPanelsOverlay
from .ui_overlays.find_everything_overlay import FindEverythingOverlay
from .ui_overlays.component_inspector_overlay import ComponentInspectorOverlay
from .ui_overlays.hd2d_settings_panel_overlay import Hd2dSettingsPanelOverlay
from .editor.editor_gizmo_overlay import EditorGizmoOverlay
from .editor.selection_outline_overlay import SelectionOutlineOverlay
from .editor.marquee_select_overlay import MarqueeSelectOverlay
from .game_runtime import tick as game_tick
from .game_runtime import ui_wiring as game_ui_wiring
from .game_runtime import events as game_events
from .game_runtime.undo import UndoFrame
from .services import (
    InputService,
    PersistenceService,
    ReplayService,
    build_input_service,
    build_persistence_service,
    build_replay_service,
)
from .ui_overlays import providers as ui_providers

_BEHAVIOUR_META_EXPLICIT = "__explicit_behaviour_keys__"
_OPTIONAL_BEHAVIOUR_DEFAULTS: tuple[tuple[str, str], ...] = ()
_MISSING = object()
logger = get_logger(__name__)


def _resolve_input_service(window: Any) -> InputService:
    service = getattr(window, "input_service", None)
    if isinstance(service, InputService):
        return service
    service = build_input_service()
    try:
        setattr(window, "input_service", service)
    except Exception:
        pass
    return service


def _resolve_persistence_service(window: Any) -> PersistenceService:
    service = getattr(window, "persistence_service", None)
    if isinstance(service, PersistenceService):
        return service
    service = build_persistence_service()
    try:
        setattr(window, "persistence_service", service)
    except Exception:
        pass
    return service


def _resolve_replay_service(window: Any) -> ReplayService:
    service = getattr(window, "replay_service", None)
    if isinstance(service, ReplayService):
        return service
    service = build_replay_service()
    try:
        setattr(window, "replay_service", service)
    except Exception:
        pass
    return service


class GameWindow(engine.optional_arcade.arcade.Window):
    """Main game window and central facade for the Mesh Engine.

    GameWindow inherits from Arcade's Window class and orchestrates all engine
    subsystems. It serves as the service container that controllers and systems
    reference to access other parts of the engine.

    Key Responsibilities:
        - Initialize and wire up all engine subsystems
        - Run the main game loop (update/draw cycle)
        - Dispatch input events to the appropriate handlers
        - Manage scene loading and transitions
        - Coordinate UI overlay rendering

    Subsystems (accessible as attributes):
        scene_controller: Entity and scene management
        camera_controller: Viewport, zoom, shake
        input_controller: Input handling and action dispatch
        ui_controller: UI overlays and HUD
        editor_controller: In-game editor (dev mode)
        console_controller: Developer console
        lighting: Dynamic lighting system
        audio: Music and sound effects
        events: Event bus for gameplay events
        game_state: Global game state (flags, counters)
        quest_manager: Quest progress tracking
        save_manager: Save/load functionality

    UI Overlays:
        player_hud: Health/stamina/inventory HUD
        pause_menu: In-game pause menu
        help_overlay: Controls help screen
        settings_overlay: Settings/options menu

    Example::

        # Access subsystems from a behaviour
        def update(self, dt):
            # Get player entity
            player = self.window.scene_controller.player

            # Emit a gameplay event
            self.window.events.emit("item_collected", item_id="key_1")

            # Check game state
            if self.window.game_state.get_flag("boss_defeated"):
                self.window.scene_controller.request_scene_change("credits.json")

            # Play sound effect
            self.window.audio.play_sound("coin_pickup")
    """

    player_hud: PlayerHUD
    game_over_screen: GameOverScreen
    pause_menu: PauseMenu
    help_overlay: HelpOverlay
    inspector_overlay: InspectorOverlay
    variant_picker_overlay: GoldenSliceVariantPickerOverlay
    golden_slice_demo_hud: GoldenSliceDemoHUDStripOverlay
    dev_browser_overlay: DevBrowserOverlay
    settings_overlay: SettingsOverlay
    input_service: InputService
    persistence_service: PersistenceService
    replay_service: ReplayService

    def __init__(
        self,
        width: int,
        height: int,
        title: str,
        *,
        fullscreen: bool = False,
        vsync: bool = True,
        config: EngineConfig | None = None,
        config_path: str = "config.json",
    ) -> None:
        """Initialize the game window and all engine subsystems.

        Args:
            width: Window width in pixels.
            height: Window height in pixels.
            title: Window title text.
            fullscreen: Start in fullscreen mode.
            vsync: Enable vertical sync.
            config: Pre-loaded EngineConfig, or None to use defaults.
            config_path: Path to config.json for runtime reference.
        """
        super().__init__(
            width=width,
            height=height,
            title=title,
            fullscreen=fullscreen,
            vsync=vsync,
        )
        try:
            engine.optional_arcade.arcade.set_background_color(engine.optional_arcade.arcade.color.DARK_BLUE_GRAY)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Mesh][GameWindow] WARNING: Failed to set background color: %r", exc)

        load_builtin_behaviours()

        self.config_path = config_path
        if config is None:
            config = EngineConfig(
                width=width,
                height=height,
                title=title,
                fullscreen=fullscreen,
                vsync=vsync,
            )
        self.engine_config = config
        self.engine_config.width = width
        self.engine_config.height = height
        self.engine_config.title = title
        self.engine_config.fullscreen = fullscreen
        self.engine_config.vsync = vsync
        
        # Text cache for overlays to avoid PerformanceWarning
        from engine.text_draw import TextCache
        self.text_cache = TextCache()

        self.world_controller = None
        world_file = getattr(self.engine_config, "world_file", None)
        if world_file:
            path = resolve_path(world_file)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    raw = migrate_payload("world", raw)
                    self.world_controller = WorldController(raw)
                    logger.info(
                        "[Mesh][World] Loaded world '%s' from %s",
                        self.world_controller.id,
                        world_file,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("[Mesh][World] Failed to load '%s': %s", world_file, exc)

        self.scene_loader = SceneLoader()
        self.fx_presets = build_fx_preset_registry()
        self.assets = AssetManager()
        self.animation_factory = AnimationFactory(self.assets)
        self.tilemap_manager = TilemapManager(self.assets)
        self.audio = AudioManager()
        self.audio.set_master_volume(self.engine_config.master_volume)
        self.audio.set_sfx_volume(self.engine_config.sfx_volume)
        self.audio.set_music_volume(self.engine_config.music_volume)
        self.runtime_settings = ensure_runtime_settings(self)
        self.runtime_settings_path = resolve_runtime_settings_path()
        loaded_settings = load_runtime_settings(
            self.runtime_settings_path,
            base=self.runtime_settings,
        )
        if isinstance(loaded_settings, RuntimeSettings):
            self.runtime_settings = loaded_settings
        self.runtime_settings.apply(self)
        self.console_controller = ConsoleController(self)
        self.camera_controller = CameraController(self)
        self.scene_controller = SceneController(self)
        self.input_controller = InputController(self)
        self.ui_controller = UIController(self)
        self.editor_controller = EditorModeController(self)
        self.ai_debug_overlay = AIDebugOverlay()
        self.ai_debug_overlay_enabled = False

        # Debug-only scene authoring state (dirty tracking + guarded persist)
        self.scene_dirty: bool = False
        self.scene_dirty_reason: str = ""
        self.scene_dirty_counter: int = 0
        self.last_persist_path: str | None = None
        self.hot_reload_error_message: str = ""
        self.hot_reload_error_scene_path: str = ""
        self.hot_reload_error_visible: bool = False
        self.scene_persist_armed: bool = False
        self.entity_snap_to_tile: bool = False
        self.last_duplicate_count: int = 0
        self.last_duplicate_primary: str = ""
        self.last_duplicate_counter: int = 0
        self.entity_clipboard: dict[str, Any] | None = None
        self.last_transform_action: str = ""
        self.last_transform_count: int = 0
        self.last_transform_counter: int = 0
        self.last_props_action: str = ""
        self.last_props_changed: int = 0
        self.last_props_counter: int = 0
        self.last_config_action: str = ""
        self.last_config_changed: int = 0
        self.last_config_counter: int = 0
        self.tile_quick_slots: dict[int, int] = {}
        self.tile_recent: list[int] = []
        self.prefab_quick_slots: dict[int, str] = {}
        self.prefab_recent: list[str] = []
        self.recent_scenes: list[str] = []
        self.command_palette_enabled: bool = False
        self.command_palette_query: str = ""
        self.command_palette_index: int = 0
        self.command_palette_prompt_active: bool = False
        self.command_palette_prompt_text: str = ""
        self.command_palette_prompt_placeholder: str = ""
        self.command_palette_prompt_title: str = ""
        self.command_palette_prompt_command_id: str = ""
        self.command_palette_prompt_kind: str = "text"
        self.command_palette_prompt_query: str = ""
        self.command_palette_prompt_index: int = 0
        self.command_palette_prompt_steps: tuple[Any, ...] = ()
        self.command_palette_prompt_step_index: int = 0
        self.command_palette_prompt_values: dict[str, Any] = {}
        self.last_macro_args: dict[str, dict[str, Any]] = {}
        self.undo_stack: list[UndoFrame] = []
        self.redo_stack: list[UndoFrame] = []
        self._undo_ts_counter: int = 0
        self._undo_suppress_count: int = 0
        self.cutscene_controller = CutsceneController(self)
        cutscene_path = Path("cutscenes.json")
        if cutscene_path.exists():
            try:
                self.cutscene_controller.load_from_file(str(cutscene_path))
            except Exception as exc:  # noqa: BLE001
                logger.error("[Mesh][Cutscene] Failed to load cutscenes.json: %s", exc)
        ambient = list(getattr(self.engine_config, "lighting_ambient_color", [10, 10, 10, 255]))
        ambient_alpha = getattr(self.engine_config, "ambient_darkness_alpha", None)
        if ambient_alpha is not None and len(ambient) >= 4:
            try:
                ambient[3] = int(ambient_alpha)
            except Exception:  # noqa: BLE001
                pass
        self.lighting = LightManager(
            self,
            enabled=getattr(self.engine_config, "lighting_enabled", True),
            ambient_color=tuple(ambient),
            max_static_lights=getattr(self.engine_config, "lighting_max_static_lights", 128),
            max_dynamic_lights=getattr(self.engine_config, "lighting_max_dynamic_lights", 64),
            shadows_mode=getattr(self.engine_config, "lighting_shadows_mode", "hard"),
            debug_shadows=getattr(self.engine_config, "lighting_debug_shadows", False),
        )
        ambient_tint = getattr(self.engine_config, "ambient_light_rgba", None)
        if ambient_tint is not None:
            self.lighting.set_ambient_tint(ambient_tint)
        if ambient_alpha is not None:
            self.lighting.set_ambient_darkness_alpha(ambient_alpha)
        self.day_night = DayNightCycle(
            self.lighting,
            enabled=getattr(self.engine_config, "day_night_enabled", False),
            start_hour=float(
                getattr(
                    self.engine_config,
                    "day_start_hour",
                    getattr(self.engine_config, "day_night_start_hour", 21.0),
                )
            ),
            cycle_length_seconds=float(
                getattr(
                    self.engine_config,
                    "day_length_seconds",
                    getattr(self.engine_config, "day_night_cycle_length_seconds", 600.0),
                )
            ),
        )

        # Initialize UI elements
        game_ui_wiring.init_default_overlays(
            self,
            PlayerHUD=PlayerHUD,
            GameOverScreen=GameOverScreen,
            PauseMenu=PauseMenu,
            HelpOverlay=HelpOverlay,
            InspectorOverlay=InspectorOverlay,
            GoldenSliceVariantPickerOverlay=GoldenSliceVariantPickerOverlay,
            GoldenSliceDemoHUDStripOverlay=GoldenSliceDemoHUDStripOverlay,
            DevBrowserOverlay=DevBrowserOverlay,
        )

        self.encounter_debug_overlay = EncounterDebugOverlay(self, provider=ui_providers.encounter_debug_provider)
        self.register_ui_element(self.encounter_debug_overlay)

        self.scene_dirty_overlay = SceneDirtyOverlay(self, provider=ui_providers.scene_dirty_provider)
        self.register_ui_element(self.scene_dirty_overlay)
        self.physics_broadphase_overlay = PhysicsBroadphaseOverlay(self, provider=ui_providers.physics_broadphase_provider)
        self.register_ui_element(self.physics_broadphase_overlay)

        self.hd2d_preview_indicator_overlay = HD2DPreviewIndicatorOverlay(self, provider=ui_providers.hd2d_preview_indicator_provider)
        self.register_ui_element(self.hd2d_preview_indicator_overlay)

        self.hot_reload_overlay = HotReloadOverlay(self)
        self.register_ui_element(self.hot_reload_overlay)

        from engine.entity_select_mode import EntitySelectState  # noqa: PLC0415

        self.entity_select_state = EntitySelectState()

        self.entity_select_overlay = EntitySelectOverlay(self, provider=ui_providers.entity_select_provider)
        self.register_ui_element(self.entity_select_overlay)

        self.scene_inspector_overlay = SceneInspectorOverlay(self, provider=ui_providers.scene_inspector_provider)
        self.register_ui_element(self.scene_inspector_overlay)

        from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

        self.tile_paint_state = TilePaintState()

        self.tile_paint_overlay = TilePaintOverlay(self, provider=ui_providers.tile_paint_provider)
        self.register_ui_element(self.tile_paint_overlay)

        from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

        self.entity_paint_state = EntityPaintState()

        self.entity_paint_overlay = EntityPaintOverlay(self, provider=ui_providers.entity_paint_provider)
        self.register_ui_element(self.entity_paint_overlay)

        from engine.capture_mode import CaptureState  # noqa: PLC0415

        self.capture_state = CaptureState()
        self.capture_persist_armed = False
        self.capture_persist_status = ""

        self.capture_overlay = CaptureOverlay(self, provider=ui_providers.capture_provider)
        self.register_ui_element(self.capture_overlay)

        self.command_palette_overlay = CommandPaletteOverlay(self, provider=ui_providers.command_palette_provider)
        self.register_ui_element(self.command_palette_overlay)

        self.editor_command_palette_overlay = CommandPaletteOverlay(self, provider=ui_providers.editor_command_palette_provider); self.register_ui_element(self.editor_command_palette_overlay)

        # Editor shell draws first (behind other editor overlays)
        self.editor_shell_overlay = EditorShellOverlay(self); self.register_ui_element(self.editor_shell_overlay)

        # Menu bar draws on top of shell but below panels
        from engine.ui_overlays.menu_bar_overlay import MenuBarOverlay
        self.menu_bar_overlay = MenuBarOverlay(self); self.register_ui_element(self.menu_bar_overlay)

        # Context menu (right-click) draws on top of everything
        from engine.ui_overlays.context_menu_overlay import ContextMenuOverlay
        self.context_menu_overlay = ContextMenuOverlay(self); self.register_ui_element(self.context_menu_overlay)

        self.entity_panels_overlay = EntityPanelsOverlay(self); self.register_ui_element(self.entity_panels_overlay)
        self.component_inspector_overlay = ComponentInspectorOverlay(self); self.register_ui_element(self.component_inspector_overlay)
        self.hd2d_settings_panel_overlay = Hd2dSettingsPanelOverlay(self, provider=ui_providers.hd2d_settings_panel_provider); self.register_ui_element(self.hd2d_settings_panel_overlay)
        self.editor_status_bar_overlay = EditorStatusBarOverlay(self); self.register_ui_element(self.editor_status_bar_overlay)
        self.scene_switcher_overlay = SceneSwitcherOverlay(self); self.register_ui_element(self.scene_switcher_overlay)
        self.scene_browser_overlay = SceneBrowserOverlay(self); self.register_ui_element(self.scene_browser_overlay)
        self.project_explorer_overlay = ProjectExplorerOverlay(self); self.register_ui_element(self.project_explorer_overlay)
        self.asset_browser_overlay = AssetBrowserOverlay(self); self.register_ui_element(self.asset_browser_overlay)
        self.undo_history_overlay = UndoHistoryOverlay(self); self.register_ui_element(self.undo_history_overlay)
        self.problems_panel_overlay = ProblemsPanelOverlay(self); self.register_ui_element(self.problems_panel_overlay)
        self.debug_panels_overlay = DebugPanelsOverlay(self); self.register_ui_element(self.debug_panels_overlay)
        self.find_everything_overlay = FindEverythingOverlay(self); self.register_ui_element(self.find_everything_overlay)

        self.interact_prompt_overlay = InteractPromptOverlay(self, provider=ui_providers.interact_prompt_provider); self.register_ui_element(self.interact_prompt_overlay)
        self.objective_tracker_overlay = ObjectiveTrackerOverlay(self, provider=ui_providers.objective_tracker_provider); self.register_ui_element(self.objective_tracker_overlay)

        self.demo_complete_overlay = DemoCompleteOverlay(self); self.register_ui_element(self.demo_complete_overlay)
        self.main_menu_overlay = MainMenuOverlay(self); self.register_ui_element(self.main_menu_overlay)

        self.settings_overlay = SettingsOverlay(self)
        self.settings_overlay.apply()
        self.register_ui_element(self.settings_overlay)

        from engine.ui_overlays.perf import PerfOverlay
        self.perf_overlay = PerfOverlay(self)
        self.register_ui_element(self.perf_overlay)

        self.light_occluder_overlay = LightOccluderEditorOverlay(self); self.register_ui_element(self.light_occluder_overlay)

        self.selection_outline_overlay = SelectionOutlineOverlay(self); self.register_ui_element(self.selection_outline_overlay)

        from engine.editor_hover_highlight_overlay import EditorHoverHighlightOverlay
        self.editor_hover_highlight_overlay = EditorHoverHighlightOverlay(self); self.register_ui_element(self.editor_hover_highlight_overlay)

        self.marquee_select_overlay = MarqueeSelectOverlay(self); self.register_ui_element(self.marquee_select_overlay)

        self.editor_gizmo_overlay = EditorGizmoOverlay(self); self.register_ui_element(self.editor_gizmo_overlay)

        from engine.editor_tooltip_overlay import EditorTooltipOverlay
        self.editor_tooltip_overlay = EditorTooltipOverlay(self); self.register_ui_element(self.editor_tooltip_overlay)

        self.editor_cursor_hint_overlay = EditorCursorHintOverlay(self); self.register_ui_element(self.editor_cursor_hint_overlay)

        self.fog_overlay = FogOverlay(self)
        self.register_ui_element(self.fog_overlay)

        self.transition_fade_overlay = TransitionFadeOverlay(self)
        self.register_ui_element(self.transition_fade_overlay)

        self.main_menu_overlay.open()

        # Check for preset header toast
        preset_id = os.environ.get("MESH_ACTIVE_PRESET")
        preset_desc = os.environ.get("MESH_PRESET_DESCRIPTION")
        preset_notes = os.environ.get("MESH_PRESET_NOTES")
        if preset_id:
            desc_text = f" — {preset_desc}" if preset_desc else ""
            notes_text = f" (Notes: {preset_notes})" if preset_notes else ""
            self.player_hud.enqueue_toast(f"Preset: {preset_id}{desc_text}{notes_text}")

        self.paused: bool = False
        self.game_over: bool = False
        self.world_width: int | None = None
        self.world_height: int | None = None
        self.show_debug: bool = bool(self.engine_config.debug_on_start)
        self._debug_text = engine.optional_arcade.arcade.Text(
            text="",
            x=10,
            y=self.height - 10,
            color=engine.optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
        )
        self.event_bus = MeshEventBus()
        self._mesh_event_queue: list[MeshEvent] = []
        self._scene_event_unsubscribes: list[Callable[[], None]] = []
        self.game_state_controller = GameStateController(self)
        self.save_manager = SaveManager(self)
        self.quest_manager = QuestManager(self)
        self.particle_manager = ParticleManager(self)
        self.render_batching_enabled = True
        self.render_culling_enabled = True
        self.tilemap_batching_enabled = True
        self.tilemap_chunk_size = 16
        self.render_queue = SpriteRenderQueue(ArcadeSpriteBatcher(self))
        self.perf_stats = PerfStats()

        # Post-processing pipeline (empty by default — add effects at runtime)
        from .post_processing import PostProcessPipeline
        self.post_process_pipeline = PostProcessPipeline()
        self.strict_mode: bool = DEBUG_STRICT_EXCEPTIONS
        self.input_service = build_input_service()
        self.persistence_service = build_persistence_service()
        self.replay_service = build_replay_service()

        # Plugin / mod system
        from .plugin_system import PluginManager
        self.plugin_manager = PluginManager()
        try:
            from .repo_root import find_repo_root
            _repo = find_repo_root()
            _mods_dir = (_repo / "mods") if _repo else None
            if _mods_dir and _mods_dir.is_dir():
                self.plugin_manager.load_all(self, _mods_dir)
                self.plugin_manager.enable_all()
        except Exception as _exc:  # noqa: BLE001
            logger.warning("[Mesh][Plugins] Plugin loading failed: %s", _exc)

        logger.info("[Mesh][GameWindow] Initialized %sx%s window", width, height)

        self.event_bus.subscribe("died", self._on_entity_died)
        self.event_bus.subscribe(EVENT_DAMAGE_APPLIED, self._on_damage_event)
        self.event_bus.subscribe(EVENT_COLLECTIBLE_PICKED, self._on_collectible_event)
        self.event_bus.subscribe(EVENT_LEVEL_UP, self._on_level_up)

        self.last_events: list[str] = []
        self.event_bus.subscribe_all(self._on_any_event)
        self.event_bus.subscribe_all(self._on_any_event_boss_reward_clarity)

    @property
    def input(self) -> InputManager:
        return self.input_controller.manager

    @property
    def mouse_x(self) -> float:
        return self.input_controller.mouse_x

    @property
    def mouse_y(self) -> float:
        return self.input_controller.mouse_y

    def should_collide(self, sprite_a: engine.optional_arcade.arcade.Sprite, sprite_b: engine.optional_arcade.arcade.Sprite) -> bool:
        return self.scene_controller.should_collide(sprite_a, sprite_b)



    def load_scene(self, scene_path: str) -> Dict[str, Any]:
        """Load entities from a JSON scene file and build sprites for them."""
        return _resolve_persistence_service(self).load_scene(self, scene_path)

    def request_scene_reload(self, clear_assets: bool = False) -> None:
        """Request that the currently loaded scene reload on the next frame."""
        _resolve_persistence_service(self).request_scene_reload(self, clear_assets=clear_assets)

    def request_reload_current_scene(self, clear_assets: bool = False) -> None:
        """Request that the currently loaded scene reload on the next frame."""
        _resolve_persistence_service(self).request_reload_current_scene(self, clear_assets=clear_assets)

    def request_scene_change(self, scene_path: str) -> None:
        """Request that a different scene load on the next frame."""
        _resolve_persistence_service(self).request_scene_change(self, scene_path)

    def queue_scene_change(self, scene_path: str, *, spawn_id: str | None = None) -> None:
        """Request that the game switches to another scene at the end of the frame."""
        _resolve_persistence_service(self).queue_scene_change(self, scene_path, spawn_id=spawn_id)

    def mark_scene_dirty(self, reason: str) -> None:
        _resolve_persistence_service(self).mark_scene_dirty(self, reason)

    def record_recent_scene(self, scene_path: str) -> None:
        _resolve_persistence_service(self).record_recent_scene(self, scene_path)

    def get_recent_scenes(self) -> list[str]:
        return _resolve_persistence_service(self).get_recent_scenes(self)

    def clear_scene_dirty(self) -> None:
        _resolve_persistence_service(self).clear_scene_dirty(self)

    def set_hot_reload_error(self, message: str, scene_path: str | None = None) -> None:
        self.hot_reload_error_message = str(message or "").strip()
        self.hot_reload_error_scene_path = str(scene_path or "").strip()
        self.hot_reload_error_visible = bool(self.hot_reload_error_message)

    def clear_hot_reload_error(self) -> None:
        self.hot_reload_error_message = ""
        self.hot_reload_error_scene_path = ""
        self.hot_reload_error_visible = False

    def _undo_enabled(self) -> bool:
        return _resolve_persistence_service(self).undo_enabled(self)

    def _snapshot_current_authored_scene_payload(self) -> UndoFrame | None:
        return _resolve_persistence_service(self).snapshot_current_authored_scene_payload(self)

    def push_undo_frame(self, reason: str) -> bool:
        return _resolve_persistence_service(self).push_undo_frame(self, reason)

    def undo(self) -> bool:
        return _resolve_persistence_service(self).undo(self)

    def redo(self) -> bool:
        return _resolve_persistence_service(self).redo(self)

    def reload_scene_from_disk(self) -> bool:
        return _resolve_persistence_service(self).reload_scene_from_disk(self)

    def persist_scene_to_disk(self):
        return _resolve_persistence_service(self).persist_scene_to_disk(self)

    def save_scene_as(self, new_scene_path: str) -> Any:
        return _resolve_persistence_service(self).save_scene_as(self, new_scene_path)

    def reload_scene(self, new_path: str | None = None) -> bool:
        """Hot reload the current (or provided) scene immediately."""
        return _resolve_persistence_service(self).reload_scene(self, new_path)

    def reload_current_scene(self) -> None:
        """Debug: Reload the current scene from disk."""
        _resolve_persistence_service(self).reload_current_scene(self)

    def warp_to_scene(self, scene_path: str) -> None:
        """Debug: Warp to a specific scene."""
        _resolve_persistence_service(self).warp_to_scene(self, scene_path)

    def track_scene_subscription(self, unsubscribe: Callable[[], None]) -> None:
        self.scene_controller.track_scene_subscription(unsubscribe)





    def _draw_debug_overlay(self) -> None:
        """Draw debug information on the screen."""
        fps = engine.optional_arcade.arcade.get_fps()
        cam_x, cam_y = self.camera_controller.get_camera_center()
        mx, my = self.mouse_x, self.mouse_y
        wx, wy = self.screen_to_world(mx, my)

        debug_info = [
            f"FPS: {fps:.1f}",
            f"Camera: ({cam_x:.1f}, {cam_y:.1f})",
            f"Mouse Screen: ({mx:.1f}, {my:.1f})",
            f"Mouse World: ({wx:.1f}, {wy:.1f})",
            f"Zoom: {self.camera_controller.zoom:.2f}",
            f"Entities: {len(self.scene_controller.get_all_entities())}",
        ]
        lighting = getattr(self, "lighting", None)
        if lighting is not None:
            stats = lighting.get_stats()
            status = "avail" if stats["available"] else "no-api"
            state = "on" if stats["enabled"] else "off"
            s_info = str(stats["static_count"])
            if stats["max_static"] is not None:
                s_info += f"/{stats['max_static']}"
            d_info = str(stats["dynamic_count"])
            if stats["max_dynamic"] is not None:
                d_info += f"/{stats['max_dynamic']}"
            debug_info.append(f"Lighting: {state} ({status}) S:{s_info} D:{d_info}")

        debug_info.extend(get_encounter_debug_lines(self.scene_controller))

        self._debug_text.text = "\n".join(debug_info)
        self._debug_text.draw()

    def on_draw(self) -> None:
        self.perf_stats.mark_draw_start()
        game_tick.on_draw(self)
        self.perf_stats.mark_draw_end()

    def _draw_shadowcast_debug(self) -> None:
        """Draw shadowcast rays if enabled."""
        lighting = getattr(self, "lighting", None)
        if lighting is None:
            return
            
        # We need to draw in world space
        self.camera.use()
        
        snapshot = lighting.get_lighting_snapshot()
        shadowcast = snapshot.get("shadowcast", {})
        
        for light_id, rays in shadowcast.items():
            # Find light position from snapshot or config
            # The snapshot has "lights" list, but we need to match ID or index.
            # The shadowcast keys are "light_{i}".
            try:
                idx = int(light_id.split("_")[1])
                if idx < len(snapshot["lights"]):
                    light = snapshot["lights"][idx]
                    lx = light.get("x", 0)
                    ly = light.get("y", 0)
                    
                    for ray in rays:
                        hit = ray["hit"]
                        # Draw line from light to hit
                        engine.optional_arcade.arcade.draw_line(lx, ly, hit[0], hit[1], engine.optional_arcade.arcade.color.YELLOW, 1)
                        # Draw hit point
                        engine.optional_arcade.arcade.draw_circle_filled(hit[0], hit[1], 2, engine.optional_arcade.arcade.color.RED)
            except (ValueError, IndexError):
                continue
        
        # Switch back to GUI camera if needed (though on_draw ends soon)
        self.camera_controller.gui_camera.use()

    def on_update(self, delta_time: float) -> None:
        self.perf_stats.enter_frame()
        self.perf_stats.mark_update_start()
        game_tick.on_update(self, delta_time)
        self.perf_stats.mark_update_end()

    def run(self) -> None:
        """Start Arcade's main loop."""
        logger.info("[Mesh][GameWindow] Starting Arcade loop...")
        engine.optional_arcade.arcade.run()

    @property
    def all_sprites(self) -> Iterator[engine.optional_arcade.arcade.Sprite]:
        """Iterate through every sprite across all layers."""
        return self.scene_controller.all_sprites

    def find_entity(self, identifier: str | int) -> engine.optional_arcade.arcade.Sprite | None:
        """Find an entity by ID (index) or name."""
        return self.scene_controller.find_entity(identifier)

    def get_all_entities(self) -> list[engine.optional_arcade.arcade.Sprite]:
        """Return a stable list of all entities."""
        return self.scene_controller.get_all_entities()

    def find_sprite_by_name(self, name: str | None) -> engine.optional_arcade.arcade.Sprite | None:
        """Return the first sprite whose mesh_name matches the provided value."""
        return self.scene_controller.find_sprite_by_name(name)

    def register_ui_element(self, element: UIElement) -> None:
        self.ui_controller.register_ui_element(element)

    def clear_ui_elements(self) -> None:
        self.ui_controller.clear_ui_elements()

    def show_dialogue(self, entries: Sequence[dict[str, str]], *, owner: str) -> bool:
        return self.ui_controller.show_dialogue(entries, owner=owner)

    def advance_dialogue(self, *, owner: str | None = None) -> bool:
        return self.ui_controller.advance_dialogue(owner=owner)

    def close_dialogue(self, *, owner: str | None = None) -> None:
        self.ui_controller.close_dialogue(owner=owner)

    def lock_player_input(self, *, owner: str | None = None) -> None:
        self.input_controller.lock_player_input(owner=owner)

    def unlock_player_input(self, *, owner: str | None = None) -> None:
        self.input_controller.unlock_player_input(owner=owner)

    def clear_input_locks(self) -> None:
        self.input_controller.clear_input_locks()

    def is_input_locked(self) -> bool:
        return self.input_controller.is_input_locked()

    def player_input_blocked(self) -> bool:
        return self.input_controller.player_input_blocked()

    def is_dialogue_active(self, *, owner: str | None = None) -> bool:
        return self.ui_controller.is_dialogue_active(owner=owner)

    def dialogue_blocks_input(self) -> bool:
        return self.ui_controller.dialogue_blocks_input()

    def is_quest_log_visible(self) -> bool:
        return self.ui_controller.is_quest_log_visible()

    def quest_log_blocks_input(self) -> bool:
        return self.ui_controller.quest_log_blocks_input()

    def toggle_quest_log(self) -> bool:
        visible = self.ui_controller.toggle_quest_log()
        if visible:
            try:
                self.set_flag("auto_opened_quest_log", True)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[Mesh][GameWindow] WARNING: Failed to set flag 'auto_opened_quest_log': %r",
                    exc,
                )
        return visible

    def hide_quest_log(self) -> None:
        self.ui_controller.hide_quest_log()

    def toggle_inventory_overlay(self) -> bool:
        return self.ui_controller.toggle_inventory_overlay()

    def toggle_character_panel(self) -> bool:
        return self.ui_controller.toggle_character_panel()

    def hide_character_panel(self) -> None:
        self.ui_controller.hide_character_panel()

    def is_character_panel_visible(self) -> bool:
        return self.ui_controller.is_character_panel_visible()

    def hide_inventory_overlay(self) -> None:
        self.ui_controller.hide_inventory_overlay()

    def is_inventory_overlay_visible(self) -> bool:
        return self.ui_controller.is_inventory_overlay_visible()





    def _resolve_collisions_stage(self, delta_time: float) -> None:  # noqa: ARG002
        """Reserved hook for deterministic collision processing."""
        # Intentionally empty: projects can subclass GameWindow and override
        # this method to run deterministic collision or physics steps between
        # behaviour updates and late updates without touching the main loop.



    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self.engine_config.width = int(width)
        self.engine_config.height = int(height)
        self.console_visible_line_count = max(4, min(12, height // 60 or 4))
        if self.camera_controller is not None:
            self.camera_controller.on_resize(int(width), int(height))
        if getattr(self, "ui_controller", None) is not None:
            resize = getattr(self.ui_controller, "on_resize", None)
            if callable(resize):
                resize(int(width), int(height))
        if getattr(self, "editor_controller", None) is not None:
            resize = getattr(self.editor_controller, "on_resize", None)
            if callable(resize):
                resize(int(width), int(height))
        self._debug_text.y = self.height - 10
        lighting = getattr(self, "lighting", None)
        if lighting is not None:
            lighting.resize(int(width), int(height))

    def on_key_press(self, key: int, modifiers: int) -> None:  # noqa: D401 ARG002
        _resolve_input_service(self).on_key_press(self, key, modifiers)

    def on_key_release(self, key: int, modifiers: int) -> None:  # noqa: ARG002
        _resolve_input_service(self).on_key_release(self, key, modifiers)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        _resolve_input_service(self).on_mouse_motion(self, x, y, dx, dy)

    def on_mouse_drag(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None:
        _resolve_input_service(self).on_mouse_drag(self, x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
        _resolve_input_service(self).on_mouse_release(self, x, y, button, modifiers)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        _resolve_input_service(self).on_mouse_press(self, x, y, button, modifiers)

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> None:
        _resolve_input_service(self).on_mouse_scroll(self, x, y, scroll_x, scroll_y)

    def on_text(self, text: str) -> None:
        # logger.debug("GameWindow on_text: %r", text)
        _resolve_input_service(self).on_text(self, text)

    def on_text_motion(self, motion: int) -> None:
        return

    def get_pressed_keys(self) -> set[int]:
        return self.input_controller.get_keys_down()

    def get_sprites_in_layer(self, layer_name: str) -> engine.optional_arcade.arcade.SpriteList | None:
        return self.scene_controller.get_sprites_in_layer(layer_name)

    def get_camera_center(self) -> tuple[float, float]:
        return self.camera_controller.get_camera_center()

    def build_scene_snapshot(self, compact: bool = False) -> Dict[str, Any]:
        """Build a JSON-serializable snapshot of the current scene state."""
        return _resolve_replay_service(self).build_scene_snapshot(self, compact=compact)

    def clamp_camera_to_world(
        self,
        target_x: float,
        target_y: float,
        *,
        padding: float = 0.0,
    ) -> tuple[float, float]:
        return self.camera_controller.clamp_camera_to_world(target_x, target_y, padding=padding)

    def clamp_camera_to_rect(
        self,
        target_x: float,
        target_y: float,
        rect: tuple[float, float, float, float],
        *,
        padding: float = 0.0,
    ) -> tuple[float, float]:
        return self.camera_controller.clamp_camera_to_rect(target_x, target_y, rect, padding=padding)

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return self.camera_controller.screen_to_world(x, y)

    def get_camera_area_for_point(self, x: float, y: float) -> CameraArea | None:
        # Note: CameraArea is now in camera_controller, but we return it as Any or import it if needed.
        # Since we removed the class definition from this file, we should probably update the return type hint
        # or import CameraArea. We imported CameraController, but not CameraArea.
        # Let's fix the import first.
        return self.camera_controller.get_camera_area_for_point(x, y)

    def update_camera_follow(
        self,
        *,
        target_x: float,
        target_y: float,
        dt: float,
        lerp_factor: float | None = None,
        follow_strength: float | None = None,
        deadzone_px: float | None = None,
        deadzone_w: float | None = None,
        deadzone_h: float | None = None,
        max_speed: float | None = None,
        padding: float = 0.0,
        zoom: float | None = None,
        zoom_speed: float | None = None,
        min_zoom: float | None = None,
        max_zoom: float | None = None,
    ) -> None:
        self.camera_controller.update_camera_follow(
            target_x=target_x,
            target_y=target_y,
            dt=dt,
            lerp_factor=lerp_factor,
            follow_strength=follow_strength,
            deadzone_px=deadzone_px,
            deadzone_w=deadzone_w,
            deadzone_h=deadzone_h,
            max_speed=max_speed,
            padding=padding,
            zoom=zoom,
            zoom_speed=zoom_speed,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
        )

    def set_camera_zoom_target(self, zoom: float, *, speed: float | None = None) -> None:
        self.camera_controller.set_zoom_target(zoom, speed=speed)

    def start_camera_shake(
        self,
        *,
        duration: float,
        amplitude: float,
        frequency: float = 18.0,
        falloff: float = 1.0,
    ) -> None:
        self.camera_controller.start_camera_shake(
            duration=duration,
            amplitude=amplitude,
            frequency=frequency,
            falloff=falloff,
        )

    def add_camera_trauma(
        self,
        amount: float,
        *,
        decay: float | None = None,
        max_offset: float | None = None,
        frequency: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.camera_controller.add_camera_trauma(
            amount,
            decay=decay,
            max_offset=max_offset,
            frequency=frequency,
            seed=seed,
        )

    def stop_camera_shake(self) -> None:
        self.camera_controller.stop_camera_shake()

    def emit_event(self, event: MeshEvent) -> None:
        self._mesh_event_queue.append(event)
        event_bus = getattr(self, "event_bus", None)
        if event_bus is not None:
            try:
                event_bus.emit_event(event)
            except Exception as exc:  # noqa: BLE001 - event bus should not break runtime
                logger.error("[Mesh][EventBus] ERROR forwarding event '%s': %s", event.type, exc)

    def emit_signal(self, event_type: str, **payload: Any) -> None:
        emit_event_normalized(self, str(event_type), dict(payload))

    def consume_events(self) -> list[MeshEvent]:
        events = self._mesh_event_queue
        self._mesh_event_queue = []
        return events

    @property
    def game_state(self) -> GameState:
        return self.game_state_controller.state

    @game_state.setter
    def game_state(self, value: GameState) -> None:
        self.game_state_controller.state = value

    def set_flag(self, name: str, value: bool = True) -> None:
        key = str(name)
        previous = self.game_state_controller.get_flag(key, False)
        self.game_state_controller.set_flag(key, bool(value))
        if key == "demo.reached_cellar":
            current = self.game_state_controller.get_flag(key, False)
            maybe_trigger_demo_complete_endcap(self, previous=previous, current=current)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def toggle_flag(self, name: str) -> bool:
        return self.game_state_controller.toggle_flag(name)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

    def set_counter(self, name: str, value: float = 0.0) -> float:
        return self.game_state_controller.set_counter(name, value)

    def add_counter(self, name: str, delta: float = 1.0) -> float:
        return self.game_state_controller.add_counter(name, delta)

    def set_var(self, name: str, value: Any) -> None:
        self.game_state_controller.set_var(name, value)

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.game_state_controller.get_var(name, default)

    def set_chapter(self, chapter: int) -> None:
        self.game_state_controller.set_chapter(chapter)

    def get_chapter(self) -> int:
        return self.game_state_controller.get_chapter()

    def set_main_quest(self, quest_id: str | None) -> None:
        self.game_state_controller.set_main_quest(quest_id)

    def get_main_quest(self) -> str | None:
        return self.game_state_controller.get_main_quest()

    def get_playtime_seconds(self) -> float:
        return self.game_state_controller.get_playtime_seconds()

    def set_next_spawn_point(self, spawn_id: str | None) -> None:
        self.game_state_controller.set_next_spawn_point(spawn_id)

    def get_next_spawn_point(self) -> str | None:
        return self.game_state_controller.get_next_spawn_point()

    def _consume_next_spawn_point(self) -> str | None:
        return self.game_state_controller.consume_next_spawn_point()

    def _debug_print_events(self, events: list[MeshEvent]) -> None:
        if not events or not self.show_debug:
            return
        for event in events:
            payload = event.payload or {}
            payload_preview = (
                payload.get("name")
                or payload.get("collectible")
                or payload.get("collectible_name")
                or payload.get("label")
                or payload
            )
            logger.info("[Mesh][Event] %s %s", event.type, payload_preview)



    def on_collectible_picked(self, collectible: engine.optional_arcade.arcade.Sprite, collector: engine.optional_arcade.arcade.Sprite) -> None:
        self.scene_controller.on_collectible_picked(collectible, collector)

    def on_damage(self, source: engine.optional_arcade.arcade.Sprite, target: engine.optional_arcade.arcade.Sprite, amount: float) -> None:
        self.scene_controller.on_damage(source, target, amount)

    def _toggle_paused_state(self) -> bool:
        """Flip the paused flag and report the new state."""
        self.paused = not getattr(self, "paused", False)
        logger.info("[Mesh][Debug] paused = %s", self.paused)
        return self.paused

    # ------------------------------------------------------------------
    # Console: delegated to ConsoleController
    # ------------------------------------------------------------------
    def console_log(self, message: str) -> None:
        self.console_controller.log(message)

    def _hot_reload_log(self, message: str) -> None:
        """Compat helper used by input/scene controllers when strict mode blocks hot reload."""
        self.console_log(f"[HotReload] {message}")



    def move_entity_with_collision(
        self,
        sprite: engine.optional_arcade.arcade.Sprite,
        dx: float,
        dy: float,
        friction: float = 1.0,
    ) -> None:
        self.scene_controller.move_entity_with_collision(sprite, dx, dy, friction)

    @property
    def camera(self) -> Any:
        return self.camera_controller.camera

    def _on_entity_died(self, event: MeshEvent) -> None:
        game_events.on_entity_died(self, event)

    def _on_any_event_boss_reward_clarity(self, event: MeshEvent) -> None:
        game_events.on_any_event_boss_reward_clarity(self, event)

    def _on_damage_event(self, event: MeshEvent) -> None:
        game_events.on_damage_event(self, event)

    def _on_collectible_event(self, event: MeshEvent) -> None:
        game_events.on_collectible_event(self, event)

    def _on_level_up(self, event: MeshEvent) -> None:
        game_events.on_level_up(self, event)

    def draw_debug_overlay(self) -> None:
        """Draw a lightweight developer HUD."""
        if not self.engine_config.debug_mode:
            return

        page = self.engine_config.debug_page
        lines = [f"DEBUG MODE (F3) - Page {page+1}/3 (F4)"]

        if page == 0:
            # Page 1: Scene + Player + Events
            scene_id = self.scene_controller.current_scene_path if self.scene_controller else "N/A"
            player_pos = "N/A"
            if self.scene_controller:
                p = self.scene_controller._find_player_sprite()
                if p:
                    player_pos = f"{int(p.center_x)}, {int(p.center_y)}"

            lines.append(f"Scene: {scene_id}")
            lines.append(f"Player: {player_pos}")
            lines.append("Recent Events:")

            # Use centralized history
            if hasattr(self.event_bus, "get_recent_event_names"):
                for name in self.event_bus.get_recent_event_names(5):
                    lines.append(f"  {name}")
            elif hasattr(self.event_bus, "get_recent_events"):
                # Fallback for older bus versions if any
                for e in self.event_bus.get_recent_events(5):
                    lines.append(f"  {getattr(e, 'type', str(e))}")

        elif page == 1:
            # Page 2: Active Quests
            lines.append("Active Quests:")
            # Use self.quest_manager if available, else try controller
            qm = getattr(self, "quest_manager", None)
            if not qm and self.game_state_controller:
                qm = getattr(self.game_state_controller, "quests", None)

            if qm:
                for q_id, q in qm._quests.items():
                    if q.state == "active":
                        lines.append(f"  {q.title}: {q.state}")
                        # Show stages/requirements if possible
                        for req, val in q.requirements.items():
                            lines.append(f"    req: {req}={val}")

        elif page == 2:
            # Page 3: Counters/Flags
            lines.append("Counters:")
            if self.game_state_controller:
                # Sort counters, prioritize quest scoped
                counters = self.game_state_controller.state.counters
                quest_counters = {k: v for k, v in counters.items() if "quest:" in k}
                other_counters = {k: v for k, v in counters.items() if "quest:" not in k}

                for k, v in quest_counters.items():
                    lines.append(f"  [Q] {k}: {v}")
                for k, v in other_counters.items():
                    lines.append(f"  {k}: {v}")

                lines.append("Flags:")
                for k, v in self.game_state_controller.state.flags.items():
                    lines.append(f"  {k}: {v}")

        self._draw_debug_output(lines)

    def _draw_debug_output(self, lines: list[str]) -> None:
        """Draw debug text lines and legacy overlays."""
        # Draw text
        from engine.text_draw import TextCache, draw_text_cached

        if getattr(self, "text_cache", None) is None:
            self.text_cache = TextCache()

        start_y = self.height - 20
        for line in lines:
            draw_text_cached(line, 10, start_y, color=engine.optional_arcade.arcade.color.YELLOW, font_size=12, cache=self.text_cache)
            start_y -= 16

        # Legacy encounter debug lines integration (opt-in boolean flag).
        # The EncounterDebugOverlay UI element is controlled separately.
        if getattr(self, "encounter_debug_overlay", False) is True:
            from .encounter_debug import get_encounter_debug_lines as _get_encounter_debug_lines

            enc_lines = _get_encounter_debug_lines(self.scene_controller)
            start_y = self.height - 20
            for line in enc_lines:
                draw_text_cached(line, self.width - 10, start_y, color=engine.optional_arcade.arcade.color.CYAN, font_size=12, anchor_x="right", cache=self.text_cache)
                start_y -= 16

    def _on_any_event(self, event: MeshEvent) -> None:
        game_events.on_any_event(self, event)
