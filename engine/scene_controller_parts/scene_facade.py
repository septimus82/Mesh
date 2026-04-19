from __future__ import annotations

from typing import Any


def find_entity(self, identifier: str | int):
    return self.entities.find_entity(self, identifier)


def get_all_entities(self):
    return self.entities.iter_entities(self)


def find_sprite_by_name(self, name: str | None):
    return self.entities.find_sprite_by_name(self, name)


def _find_player_sprite(self):
    return self.entities.find_primary_player_sprite(self)


def _find_spawn_marker(self, spawn_id: str):
    import engine.scene_controller_core as scene_controller_module

    return scene_controller_module._find_spawn_marker_runtime(self.all_sprites, spawn_id)


def get_spawn(self, spawn_id: str | None):
    import engine.scene_controller_core as scene_controller_module

    return scene_controller_module._get_spawn_runtime(self._loaded_scene_data, spawn_id)


def apply_spawn(self, spawn_id: str | None) -> None:
    import engine.scene_controller_core as scene_controller_module

    player = self._find_player_sprite()
    if player is None:
        return
    spawn = self.get_spawn(spawn_id)
    if spawn is None:
        return

    x = spawn.get("x")
    y = spawn.get("y")
    facing = spawn.get("facing")
    self._apply_entity_mutation(
        player,
        x=float(x) if x is not None else None,
        y=float(y) if y is not None else None,
    )
    if facing is not None:
        try:
            setattr(player, "facing", facing)
        except Exception as exc:
            if "scene_set_facing" not in scene_controller_module._LOG_ONCE:
                scene_controller_module.logger.warning(
                    "Failed to set player facing: %s",
                    exc,
                    exc_info=True,
                )
                scene_controller_module._LOG_ONCE.add("scene_set_facing")
        entity_data = getattr(player, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            entity_data["facing"] = facing


def _apply_pending_spawn_point(self) -> None:
    import engine.scene_controller_core as scene_controller_module

    scene_controller_module._apply_pending_spawn_point_runtime(self)


def _apply_scene_settings(self, settings: dict[str, Any]) -> None:
    import engine.scene_controller_core as scene_controller_module

    scene_controller_module._save_load_proxy.apply_scene_settings(
        self,
        settings,
        scene_load_apply_runtime=scene_controller_module._scene_load_apply_runtime,
    )


def _apply_scene_state(self, state_block: Any) -> None:
    import engine.scene_controller_core as scene_controller_module

    scene_controller_module._save_load_proxy.apply_scene_state(
        self,
        state_block,
        scene_load_apply_runtime=scene_controller_module._scene_load_apply_runtime,
        apply_scene_state_runtime=scene_controller_module._apply_scene_state_runtime,
    )


def _configure_camera_from_scene(self, settings: dict[str, Any]) -> None:
    self.window.camera_controller.configure_from_scene(settings)


def get_sprites_in_layer(self, layer_name: str):
    return self.layers.get(layer_name)


def build_scene_snapshot(self, compact: bool = False):
    import engine.scene_controller_core as scene_controller_module

    return scene_controller_module._save_load_proxy.build_scene_snapshot(
        self,
        compact=compact,
        build_scene_snapshot_runtime=scene_controller_module._build_scene_snapshot_runtime,
    )


def bind_scene_facade_methods(cls) -> None:
    cls.find_entity = find_entity
    cls.get_all_entities = get_all_entities
    cls.find_sprite_by_name = find_sprite_by_name
    cls._find_player_sprite = _find_player_sprite
    cls._find_spawn_marker = _find_spawn_marker
    cls.get_spawn = get_spawn
    cls.apply_spawn = apply_spawn
    cls._apply_pending_spawn_point = _apply_pending_spawn_point
    cls._apply_scene_settings = _apply_scene_settings
    cls._apply_scene_state = _apply_scene_state
    cls._configure_camera_from_scene = _configure_camera_from_scene
    cls.get_sprites_in_layer = get_sprites_in_layer
    cls.build_scene_snapshot = build_scene_snapshot