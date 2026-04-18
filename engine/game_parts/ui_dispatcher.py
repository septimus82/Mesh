from __future__ import annotations

import os
from typing import TYPE_CHECKING, Sequence

from engine.game_runtime import ui_wiring as game_ui_wiring
from engine.ui import (
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
    HotReloadOverlay,
    InspectorOverlay,
    InteractPromptOverlay,
    MainMenuOverlay,
    ObjectiveTrackerOverlay,
    PauseMenu,
    PhysicsBroadphaseOverlay,
    PlayerHUD,
    SceneDirtyOverlay,
    SceneInspectorOverlay,
    SettingsOverlay,
    TilePaintOverlay,
    UIElement,
)
from engine.ui_overlays import providers as ui_providers
from engine.ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from engine.ui_overlays.component_inspector_overlay import ComponentInspectorOverlay
from engine.ui_overlays.debug_panels_overlay import DebugPanelsOverlay
from engine.ui_overlays.editor_shell_overlay import EditorShellOverlay
from engine.ui_overlays.editor_status_bar_overlay import EditorStatusBarOverlay
from engine.ui_overlays.entity_panels_overlay import EntityPanelsOverlay
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays.fog_overlay import FogOverlay
from engine.ui_overlays.hd2d_settings_panel_overlay import Hd2dSettingsPanelOverlay
from engine.ui_overlays.light_occluder_editor import LightOccluderEditorOverlay
from engine.ui_overlays.problems_panel_overlay import ProblemsPanelOverlay
from engine.ui_overlays.project_explorer_overlay import ProjectExplorerOverlay
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from engine.ui_overlays.scene_switcher_overlay import SceneSwitcherOverlay
from engine.ui_overlays.transition_fade import TransitionFadeOverlay
from engine.ui_overlays.undo_history_overlay import UndoHistoryOverlay

if TYPE_CHECKING:
    from engine.game import GameWindow


def init_ui_dispatcher(window: "GameWindow") -> None:
    game_ui_wiring.init_default_overlays(
        window,
        PlayerHUD=PlayerHUD,
        GameOverScreen=GameOverScreen,
        PauseMenu=PauseMenu,
        HelpOverlay=HelpOverlay,
        InspectorOverlay=InspectorOverlay,
        GoldenSliceVariantPickerOverlay=GoldenSliceVariantPickerOverlay,
        GoldenSliceDemoHUDStripOverlay=GoldenSliceDemoHUDStripOverlay,
        DevBrowserOverlay=DevBrowserOverlay,
    )

    window.encounter_debug_overlay = EncounterDebugOverlay(window, provider=ui_providers.encounter_debug_provider)
    window.register_ui_element(window.encounter_debug_overlay)

    window.scene_dirty_overlay = SceneDirtyOverlay(window, provider=ui_providers.scene_dirty_provider)
    window.register_ui_element(window.scene_dirty_overlay)
    window.physics_broadphase_overlay = PhysicsBroadphaseOverlay(window, provider=ui_providers.physics_broadphase_provider)
    window.register_ui_element(window.physics_broadphase_overlay)

    window.hd2d_preview_indicator_overlay = HD2DPreviewIndicatorOverlay(window, provider=ui_providers.hd2d_preview_indicator_provider)
    window.register_ui_element(window.hd2d_preview_indicator_overlay)

    window.hot_reload_overlay = HotReloadOverlay(window)
    window.register_ui_element(window.hot_reload_overlay)

    from engine.entity_select_mode import EntitySelectState  # noqa: PLC0415

    window.entity_select_state = EntitySelectState()

    window.entity_select_overlay = EntitySelectOverlay(window, provider=ui_providers.entity_select_provider)
    window.register_ui_element(window.entity_select_overlay)

    window.scene_inspector_overlay = SceneInspectorOverlay(window, provider=ui_providers.scene_inspector_provider)
    window.register_ui_element(window.scene_inspector_overlay)

    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    window.tile_paint_state = TilePaintState()

    window.tile_paint_overlay = TilePaintOverlay(window, provider=ui_providers.tile_paint_provider)
    window.register_ui_element(window.tile_paint_overlay)

    from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

    window.entity_paint_state = EntityPaintState()

    window.entity_paint_overlay = EntityPaintOverlay(window, provider=ui_providers.entity_paint_provider)
    window.register_ui_element(window.entity_paint_overlay)

    from engine.capture_mode import CaptureState  # noqa: PLC0415

    window.capture_state = CaptureState()
    window.capture_persist_armed = False
    window.capture_persist_status = ""

    window.capture_overlay = CaptureOverlay(window, provider=ui_providers.capture_provider)
    window.register_ui_element(window.capture_overlay)

    window.command_palette_overlay = CommandPaletteOverlay(window, provider=ui_providers.command_palette_provider)
    window.register_ui_element(window.command_palette_overlay)

    window.editor_command_palette_overlay = CommandPaletteOverlay(window, provider=ui_providers.editor_command_palette_provider)
    window.register_ui_element(window.editor_command_palette_overlay)

    window.editor_shell_overlay = EditorShellOverlay(window)
    window.register_ui_element(window.editor_shell_overlay)

    from engine.ui_overlays.context_menu_overlay import ContextMenuOverlay  # noqa: PLC0415
    from engine.ui_overlays.menu_bar_overlay import MenuBarOverlay  # noqa: PLC0415

    window.menu_bar_overlay = MenuBarOverlay(window)
    window.register_ui_element(window.menu_bar_overlay)

    window.context_menu_overlay = ContextMenuOverlay(window)
    window.register_ui_element(window.context_menu_overlay)

    window.entity_panels_overlay = EntityPanelsOverlay(window)
    window.register_ui_element(window.entity_panels_overlay)
    window.component_inspector_overlay = ComponentInspectorOverlay(window)
    window.register_ui_element(window.component_inspector_overlay)
    window.hd2d_settings_panel_overlay = Hd2dSettingsPanelOverlay(window, provider=ui_providers.hd2d_settings_panel_provider)
    window.register_ui_element(window.hd2d_settings_panel_overlay)
    window.editor_status_bar_overlay = EditorStatusBarOverlay(window)
    window.register_ui_element(window.editor_status_bar_overlay)
    window.scene_switcher_overlay = SceneSwitcherOverlay(window)
    window.register_ui_element(window.scene_switcher_overlay)
    window.scene_browser_overlay = SceneBrowserOverlay(window)
    window.register_ui_element(window.scene_browser_overlay)
    window.project_explorer_overlay = ProjectExplorerOverlay(window)
    window.register_ui_element(window.project_explorer_overlay)
    window.asset_browser_overlay = AssetBrowserOverlay(window)
    window.register_ui_element(window.asset_browser_overlay)
    window.undo_history_overlay = UndoHistoryOverlay(window)
    window.register_ui_element(window.undo_history_overlay)
    window.problems_panel_overlay = ProblemsPanelOverlay(window)
    window.register_ui_element(window.problems_panel_overlay)
    window.debug_panels_overlay = DebugPanelsOverlay(window)
    window.register_ui_element(window.debug_panels_overlay)
    window.find_everything_overlay = FindEverythingOverlay(window)
    window.register_ui_element(window.find_everything_overlay)

    window.interact_prompt_overlay = InteractPromptOverlay(window, provider=ui_providers.interact_prompt_provider)
    window.register_ui_element(window.interact_prompt_overlay)
    window.objective_tracker_overlay = ObjectiveTrackerOverlay(window, provider=ui_providers.objective_tracker_provider)
    window.register_ui_element(window.objective_tracker_overlay)

    window.demo_complete_overlay = DemoCompleteOverlay(window)
    window.register_ui_element(window.demo_complete_overlay)
    window.main_menu_overlay = MainMenuOverlay(window)
    window.register_ui_element(window.main_menu_overlay)

    window.settings_overlay = SettingsOverlay(window)
    window.settings_overlay.apply()
    window.register_ui_element(window.settings_overlay)

    from engine.ui_overlays.perf import PerfOverlay  # noqa: PLC0415
    from engine.ui_overlays.profiler_overlay import ProfilerOverlay  # noqa: PLC0415

    window.perf_overlay = PerfOverlay(window)
    window.register_ui_element(window.perf_overlay)
    window.profiler_overlay = ProfilerOverlay(window, provider=ui_providers.profiler_provider)
    window.register_ui_element(window.profiler_overlay)

    window.light_occluder_overlay = LightOccluderEditorOverlay(window)
    window.register_ui_element(window.light_occluder_overlay)

    from engine.editor.editor_gizmo_overlay import EditorGizmoOverlay  # noqa: PLC0415
    from engine.editor.editor_cursor_hint_overlay import EditorCursorHintOverlay  # noqa: PLC0415
    from engine.editor.selection_outline_overlay import SelectionOutlineOverlay  # noqa: PLC0415
    from engine.editor.marquee_select_overlay import MarqueeSelectOverlay  # noqa: PLC0415
    from engine.editor_hover_highlight_overlay import EditorHoverHighlightOverlay  # noqa: PLC0415
    from engine.editor_tooltip_overlay import EditorTooltipOverlay  # noqa: PLC0415

    window.selection_outline_overlay = SelectionOutlineOverlay(window)
    window.register_ui_element(window.selection_outline_overlay)
    window.editor_hover_highlight_overlay = EditorHoverHighlightOverlay(window)
    window.register_ui_element(window.editor_hover_highlight_overlay)
    window.marquee_select_overlay = MarqueeSelectOverlay(window)
    window.register_ui_element(window.marquee_select_overlay)
    window.editor_gizmo_overlay = EditorGizmoOverlay(window)
    window.register_ui_element(window.editor_gizmo_overlay)
    window.editor_tooltip_overlay = EditorTooltipOverlay(window)
    window.register_ui_element(window.editor_tooltip_overlay)
    window.editor_cursor_hint_overlay = EditorCursorHintOverlay(window)
    window.register_ui_element(window.editor_cursor_hint_overlay)

    window.fog_overlay = FogOverlay(window)
    window.register_ui_element(window.fog_overlay)

    window.transition_fade_overlay = TransitionFadeOverlay(window)
    window.register_ui_element(window.transition_fade_overlay)

    window.main_menu_overlay.open()

    preset_id = os.environ.get("MESH_ACTIVE_PRESET")
    preset_desc = os.environ.get("MESH_PRESET_DESCRIPTION")
    preset_notes = os.environ.get("MESH_PRESET_NOTES")
    if preset_id:
        desc_text = f" — {preset_desc}" if preset_desc else ""
        notes_text = f" (Notes: {preset_notes})" if preset_notes else ""
        window.player_hud.enqueue_toast(f"Preset: {preset_id}{desc_text}{notes_text}")


def register_ui_element(self: "GameWindow", element: UIElement) -> None:
    self.ui_controller.register_ui_element(element)


def clear_ui_elements(self: "GameWindow") -> None:
    self.ui_controller.clear_ui_elements()


def show_dialogue(self: "GameWindow", entries: Sequence[dict[str, str]], *, owner: str) -> bool:
    return self.ui_controller.show_dialogue(entries, owner=owner)


def advance_dialogue(self: "GameWindow", *, owner: str | None = None) -> bool:
    return self.ui_controller.advance_dialogue(owner=owner)


def close_dialogue(self: "GameWindow", *, owner: str | None = None) -> None:
    self.ui_controller.close_dialogue(owner=owner)


def is_dialogue_active(self: "GameWindow", *, owner: str | None = None) -> bool:
    return self.ui_controller.is_dialogue_active(owner=owner)


def dialogue_blocks_input(self: "GameWindow") -> bool:
    return self.ui_controller.dialogue_blocks_input()


def is_quest_log_visible(self: "GameWindow") -> bool:
    return self.ui_controller.is_quest_log_visible()


def quest_log_blocks_input(self: "GameWindow") -> bool:
    return self.ui_controller.quest_log_blocks_input()


def toggle_quest_log(self: "GameWindow") -> bool:
    visible = self.ui_controller.toggle_quest_log()
    if visible:
        try:
            self.set_flag("auto_opened_quest_log", True)
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            from engine.game import _log_swallow, logger  # noqa: PLC0415

            _log_swallow("GAME-005", "engine/game.py blanket swallow", once=True)
            logger.warning(
                "[Mesh][GameWindow] WARNING: Failed to set flag 'auto_opened_quest_log': %r",
                exc,
            )
    return visible


def hide_quest_log(self: "GameWindow") -> None:
    self.ui_controller.hide_quest_log()


def toggle_inventory_overlay(self: "GameWindow") -> bool:
    return self.ui_controller.toggle_inventory_overlay()


def toggle_character_panel(self: "GameWindow") -> bool:
    return self.ui_controller.toggle_character_panel()


def hide_character_panel(self: "GameWindow") -> None:
    self.ui_controller.hide_character_panel()


def is_character_panel_visible(self: "GameWindow") -> bool:
    return self.ui_controller.is_character_panel_visible()


def hide_inventory_overlay(self: "GameWindow") -> None:
    self.ui_controller.hide_inventory_overlay()


def is_inventory_overlay_visible(self: "GameWindow") -> bool:
    return self.ui_controller.is_inventory_overlay_visible()


def bind_ui_dispatcher_methods(cls) -> None:
    cls.register_ui_element = register_ui_element
    cls.clear_ui_elements = clear_ui_elements
    cls.show_dialogue = show_dialogue
    cls.advance_dialogue = advance_dialogue
    cls.close_dialogue = close_dialogue
    cls.is_dialogue_active = is_dialogue_active
    cls.dialogue_blocks_input = dialogue_blocks_input
    cls.is_quest_log_visible = is_quest_log_visible
    cls.quest_log_blocks_input = quest_log_blocks_input
    cls.toggle_quest_log = toggle_quest_log
    cls.hide_quest_log = hide_quest_log
    cls.toggle_inventory_overlay = toggle_inventory_overlay
    cls.toggle_character_panel = toggle_character_panel
    cls.hide_character_panel = hide_character_panel
    cls.is_character_panel_visible = is_character_panel_visible
    cls.hide_inventory_overlay = hide_inventory_overlay
    cls.is_inventory_overlay_visible = is_inventory_overlay_visible