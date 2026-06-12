from __future__ import annotations


def test_ui_overlay_class_identities_match_reexports() -> None:
    import engine.ui as ui
    import engine.ui_overlays as overlays
    import engine.ui_overlays.debug as debug
    import engine.ui_overlays.editors as editors

    # Existing overlays
    assert ui.InspectorOverlay is overlays.InspectorOverlay
    assert ui.DevBrowserOverlay is overlays.DevBrowserOverlay
    assert ui.GoldenSliceVariantPickerOverlay is overlays.GoldenSliceVariantPickerOverlay
    assert ui.GoldenSliceDemoHUDStripOverlay is overlays.GoldenSliceDemoHUDStripOverlay

    # Debug overlays
    assert ui.EncounterDebugOverlay is debug.EncounterDebugOverlay
    assert ui.SceneInspectorOverlay is debug.SceneInspectorOverlay
    assert ui.SceneDirtyOverlay is debug.SceneDirtyOverlay
    assert ui.EntityInspector is debug.EntityInspector
    assert ui.AnimationStateOverlay is debug.AnimationStateOverlay
    assert ui.DevConsole is debug.DevConsole
    assert ui.PaletteOverlay is debug.PaletteOverlay

    # Editor overlays
    assert ui.TilePaintOverlay is editors.TilePaintOverlay
    assert ui.EntityPaintOverlay is editors.EntityPaintOverlay
    assert ui.EntitySelectOverlay is editors.EntitySelectOverlay
    assert ui.CaptureOverlay is editors.CaptureOverlay

    # Helpers
    assert ui.format_encounter_debug_text is debug.format_encounter_debug_text
    assert ui.format_scene_inspector_text is debug.format_scene_inspector_text
    assert ui.format_scene_dirty_overlay_lines is debug.format_scene_dirty_overlay_lines
    assert ui.format_tile_paint_overlay_lines is editors.format_tile_paint_overlay_lines
    assert ui.format_entity_paint_overlay_lines is editors.format_entity_paint_overlay_lines
    assert ui.format_entity_select_overlay_lines is editors.format_entity_select_overlay_lines
    assert ui.format_capture_overlay_lines is editors.format_capture_overlay_lines

    import engine.ui_overlays.command_palette as command_palette
    import engine.ui_overlays.menus as menus

    # Menus
    assert ui.PauseMenu is menus.PauseMenu
    assert ui.MainMenuOverlay is menus.MainMenuOverlay
    assert ui.SettingsOverlay is menus.SettingsOverlay
    assert ui.HelpOverlay is menus.HelpOverlay
    assert ui.GameOverScreen is menus.GameOverScreen
    assert ui.DemoCompleteOverlay is menus.DemoCompleteOverlay
    assert ui.DialogueBox is menus.DialogueBox
    assert ui.ShopPanel is menus.ShopPanel
    assert ui.CharacterPanel is menus.CharacterPanel

    # Command Palette
    assert ui.CommandPaletteOverlay is command_palette.CommandPaletteOverlay
    assert ui.format_command_palette_overlay_lines is command_palette.format_command_palette_overlay_lines

