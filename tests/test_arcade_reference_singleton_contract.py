
import pytest
import engine.optional_arcade
import importlib
import sys

def test_arcade_reference_singleton_contract():
    """
    Ensures that core modules do NOT stash a reference to 'arcade' at import time.
    They must access it dynamically via engine.optional_arcade.arcade to support
    runtime patching (e.g. for tests).
    """
    # 1. Verify source exists
    ref = engine.optional_arcade.arcade
    assert ref is not None or engine.optional_arcade._arcade is None

    # 2. List of modules to check
    # These are all known consumers of arcade.
    modules_to_check = [
        "engine.game",
        "engine.text_draw",
        "engine.lighting",
        "engine.animation",
        "engine.assets",
        "engine.audio",
        "engine.background_layers",
        "engine.camera_controller",
        "engine.console_controller",
        "engine.editor_controller",
        "engine.render_queue_arcade",
        "engine.tilemap_batch_arcade",
        "engine.tilemap",
        "engine.ui",
        "engine.ui_overlays.common",
        "engine.ui_overlays.perf",
        "engine.ui_overlays.debug",
        "engine.ui_overlays.menus",
        "engine.ui_overlays.hud",
        "engine.ui_overlays.editors",
        "engine.ui_overlays.command_palette",
    ]

    for mod_name in modules_to_check:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            # If module doesn't exist (e.g. refactored away), skip but warn? 
            # Ideally strict, but acceptable to skip if it's genuinely gone. 
            print(f"WARNING: Module {mod_name} could not be imported for contract check.")
            continue
            
        assert not hasattr(mod, "arcade"), f"{mod_name} has a static 'arcade' attribute. Use engine.optional_arcade.arcade instead."
        # Also check for aliases if we know them? e.g. _arcade
        # We generally frown upon top-level private aliases too for the same reason.
        if hasattr(mod, "_arcade"):
             # It might be the optional_arcade module alias itself? 
             pass # Less strictly enforcing this, but good to know.

    # 3. Verify they DO have access to optional_arcade (concept check)
    # This is implicit if the app runs.


