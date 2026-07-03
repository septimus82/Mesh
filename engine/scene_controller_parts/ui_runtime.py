from __future__ import annotations

from engine.swallowed_exceptions import _log_swallow


def _rebuild_ui_for_scene(self) -> None:
    import engine.scene_controller_core as scene_controller_module

    self.window.clear_ui_elements()
    print("[Mesh][UI] Rebuilding UI for scene")

    from engine.ui import PERSISTENT_UI_ATTRS  # noqa: PLC0415

    for attr_name in PERSISTENT_UI_ATTRS:
        element = getattr(self.window, attr_name, None)
        if element is not None:
            self.window.register_ui_element(element)

    self.window.register_ui_element(scene_controller_module.EntityInspector(self.window), editor_chrome=False)
    self.window.register_ui_element(scene_controller_module.AnimationStateOverlay(self.window), editor_chrome=False)
    self.window.register_ui_element(scene_controller_module.DevConsole(self.window), editor_chrome=False)

    self.window.ui_controller.inventory_overlay = scene_controller_module.InventoryOverlay(self.window)
    self.window.register_ui_element(self.window.ui_controller.inventory_overlay, editor_chrome=False)

    self.window.ui_controller.dialogue_box = scene_controller_module.DialogueBox(self.window)
    self.window.register_ui_element(self.window.ui_controller.dialogue_box, editor_chrome=False)

    self.window.ui_controller.quest_log = scene_controller_module.QuestLog(self.window)
    self.window.register_ui_element(self.window.ui_controller.quest_log, editor_chrome=False)

    self.window.ui_controller.shop_panel = scene_controller_module.ShopPanel(self.window)
    self.window.register_ui_element(self.window.ui_controller.shop_panel, editor_chrome=False)

    self.window.ui_controller.character_panel = scene_controller_module.CharacterPanel(self.window)
    self.window.register_ui_element(self.window.ui_controller.character_panel, editor_chrome=False)

    try:
        from engine.behaviours.health import Health  # noqa: PLC0415
    except ImportError:
        return
    except Exception:
        _log_swallow("scene_import_health", "Unexpected error importing Health behaviour")
        return

    for sprite in self.all_sprites:
        behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
        if not behaviours:
            continue
        if any(isinstance(behaviour, Health) for behaviour in behaviours):
            print(
                "[Mesh][UI] Registering HealthBar for",
                getattr(sprite, "mesh_name", "<unnamed>"),
            )
            self.window.register_ui_element(scene_controller_module.HealthBar(self.window, sprite), editor_chrome=False)


def bind_ui_runtime_methods(cls) -> None:
    cls._rebuild_ui_for_scene = _rebuild_ui_for_scene
