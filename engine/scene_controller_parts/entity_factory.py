# mypy: ignore-errors
from __future__ import annotations

from typing import Any, cast

from engine.swallowed_exceptions import _log_swallow


def _apply_collision_poly(self, sprite: Any, poly: Any) -> None:
    import os

    from engine.geometry_tools import sanitize_poly  # noqa: PLC0415
    import engine.scene_controller_core as scene_controller_module

    points: list[tuple[float, float]] = []
    if isinstance(poly, list):
        points = sanitize_poly(poly)
    try:
        set_hit_box = getattr(sprite, "set_hit_box", None)
        if not callable(set_hit_box):
            return
        if points:
            if os.environ.get("MESH_POLY_DEBUG") == "1":
                cx = sum(p[0] for p in points) / len(points)
                cy = sum(p[1] for p in points) / len(points)
                if abs(cx) > 1e-3 or abs(cy) > 1e-3:
                    scene_controller_module.logger.info(
                        "[Mesh][Poly] collision_poly centroid offset for %s: (%.3f, %.3f)",
                        getattr(sprite, "mesh_name", "<unnamed>"),
                        cx,
                        cy,
                    )
            set_hit_box(points)
        else:
            set_hit_box()
    except Exception:  # noqa: BLE001  # REASON: invalid collision polygon application should skip only that sprite hitbox update
        scene_controller_module.logger.debug(
            "Failed to apply collision polygon on %s",
            getattr(sprite, "mesh_name", "?"),
            exc_info=True,
        )
        return


def _create_sprite(self, entity: dict[str, Any]) -> Any | None:
    import engine.scene_controller_core as scene_controller_module

    if entity.get("prefab_id"):
        entity = scene_controller_module.get_prefab_manager().resolve(entity)

    if not self.window.scene_loader.validate_entity(entity):
        return None
    sprite_path = entity.get("sprite") or "assets/placeholder.png"
    try:
        texture = self.window.assets.get_texture(sprite_path)
        if texture is None:
            print(
                f"[Mesh][Scene] WARNING: No texture available for '{sprite_path}', skipping entity",
            )
            return None

        sprite = scene_controller_module.optional_arcade.arcade.Sprite()
        sprite.texture = texture
        sprite.center_x = float(entity.get("x", 0))
        sprite.center_y = float(entity.get("y", 0))
        sprite.scale = float(entity.get("scale", 1.0))
        sprite.angle = float(entity.get("rotation", 0))

        entity_data = dict(entity)
        raw_behaviour_configs = scene_controller_module.prepare_behaviour_configs(
            entity_data.get("behaviours", []),
            include_metadata=True,
        )
        raw_behaviour_configs = [
            scene_controller_module.prune_optional_behaviour_defaults(entry)
            for entry in raw_behaviour_configs
        ]
        clean_behaviour_configs = [
            scene_controller_module.strip_behaviour_metadata(entry)
            for entry in raw_behaviour_configs
        ]
        entity_data["behaviours"] = clean_behaviour_configs
        behaviour_config_root = scene_controller_module.build_behaviour_config_map(
            entity_data,
            raw_behaviour_configs,
        )
        entity_data["behaviour_config"] = behaviour_config_root

        sprite_any = cast(Any, sprite)
        sprite_any.mesh_name = (
            entity_data.get("mesh_name")
            or entity_data.get("name")
            or entity_data.get("prefab_id")
        )
        sprite_any.mesh_entity_data = entity_data
        sprite_any.mesh_behaviours = [
            cfg.get("type") for cfg in clean_behaviour_configs
        ]
        sprite_any.mesh_behaviour_configs = clean_behaviour_configs
        sprite_any.mesh_behaviours_runtime = []
        sprite_any.mesh_tag = entity_data.get("tag")

        self._apply_collision_poly(sprite, entity_data.get("collision_poly"))
        self._attach_animator(sprite, entity_data)

        self._rebuild_behaviours_for_sprite(sprite)
        spawned_name = scene_controller_module.format_elite_label(
            str(entity_data.get("name") or entity.get("name") or "<unnamed>"),
            entity_data,
        )
        print(
            "[Mesh][Scene] [+] Spawned "
            f"'{spawned_name}' at ({sprite.center_x}, {sprite.center_y})",
        )
        if not bool(getattr(self, "_suppress_spawn_toasts", False)):
            scene_controller_module.maybe_enqueue_boss_spawn_toast(
                self.window,
                entity_data,
                self.current_scene_path,
                seconds=3.0,
            )
            scene_controller_module.maybe_enqueue_miniboss_spawn_toast(
                self.window,
                entity_data,
                self.current_scene_path,
                seconds=3.0,
            )
        return sprite
    except Exception:
        if getattr(self.window, "strict_mode", False):
            raise
        _log_swallow("scene_create_sprite", "Failed to create sprite")
        return None


def _rebuild_behaviours_for_sprite(self, sprite: Any) -> None:
    import engine.scene_controller_core as scene_controller_module

    names = [
        str(name)
        for name in getattr(sprite, "mesh_behaviours", [])
        if isinstance(name, str) and name.strip()
    ]
    entity_data = self._ensure_entity_data_dict(sprite)
    config_root = scene_controller_module.ensure_behaviour_config_root(entity_data)

    runtime_instances: list[Any] = []
    for index, behaviour_name in enumerate(names):
        config_for_behaviour = dict(config_root.get(behaviour_name, {}) or {})
        behaviour = scene_controller_module.create_behaviour(
            behaviour_name,
            sprite,
            self.window,
            config=config_for_behaviour,
        )
        if behaviour is None:
            continue
        setattr(behaviour, "mesh_behaviour_type", behaviour_name)
        setattr(behaviour, "mesh_behaviour_index", index)
        current_config = getattr(behaviour, "config", None)
        if isinstance(current_config, dict):
            current_config.update(config_for_behaviour)
        else:
            setattr(behaviour, "config", dict(config_for_behaviour))
        runtime_instances.append(behaviour)

    cast(Any, sprite).mesh_behaviours_runtime = runtime_instances


def _attach_animator(self, sprite: Any, entity_data: dict[str, Any]) -> None:
    import engine.scene_controller_core as scene_controller_module

    factory = getattr(self.window, "animation_factory", None)
    if factory is None:
        return
    try:
        animator = factory.build_for_entity(
            sprite,
            entity_data,
            debug=bool(getattr(self.window, "show_debug", False)),
            event_sink=lambda payload, spr=sprite: self._handle_animation_event(spr, payload),
        )
    except Exception as exc:
        scene_controller_module.logger.error("Failed to build animator: %s", exc, exc_info=True)
        return
    if animator is not None:
        entity_data.setdefault("default_animation", animator.current_state)


def _behaviour_config_copy(self, sprite: Any) -> dict[str, dict[str, Any]]:
    entity_data = getattr(sprite, "mesh_entity_data", None)
    if not isinstance(entity_data, dict):
        return {}
    root = entity_data.get("behaviour_config")
    if not isinstance(root, dict):
        return {}
    snapshot: dict[str, dict[str, Any]] = {}
    for key, value in root.items():
        if isinstance(key, str) and isinstance(value, dict):
            snapshot[key] = dict(value)
    return snapshot


def _get_behaviour_configs_for_sprite(self, sprite: Any) -> list[dict[str, Any]]:
    import engine.scene_controller_core as scene_controller_module

    raw_configs = getattr(sprite, "mesh_behaviour_configs", [])
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_configs, list):
        for entry in raw_configs:
            normalized_entry = scene_controller_module.normalize_behaviour_entry(entry)
            if normalized_entry is not None:
                normalized.append(normalized_entry)
    cast(Any, sprite).mesh_behaviour_configs = normalized
    return normalized


def _ensure_entity_data_dict(self, sprite: Any) -> dict[str, Any]:
    return self.entities.ensure_entity_data_dict(sprite)


def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    import engine.scene_controller_core as scene_controller_module

    return scene_controller_module.ensure_behaviour_config_root(entity_data)


def add_sprite_to_layer(self, sprite: Any, layer_name: str = "entities") -> None:
    import engine.scene_controller_core as scene_controller_module

    if layer_name not in self.layers:
        self.layers[layer_name] = scene_controller_module.optional_arcade.arcade.SpriteList()
    self.layers[layer_name].append(sprite)
    self._rebuild_behaviours_for_sprite(sprite)


def bind_entity_factory_methods(cls) -> None:
    cls._apply_collision_poly = _apply_collision_poly
    cls._create_sprite = _create_sprite
    cls._rebuild_behaviours_for_sprite = _rebuild_behaviours_for_sprite
    cls._attach_animator = _attach_animator
    cls._behaviour_config_copy = _behaviour_config_copy
    cls._get_behaviour_configs_for_sprite = _get_behaviour_configs_for_sprite
    cls._ensure_entity_data_dict = _ensure_entity_data_dict
    cls._ensure_behaviour_config_root = _ensure_behaviour_config_root
    cls.add_sprite_to_layer = add_sprite_to_layer
