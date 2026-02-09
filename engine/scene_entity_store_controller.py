from __future__ import annotations

from typing import Any

from engine.scene_entity_ops_model import EntityOp, build_drain_plan, stable_entity_order


class SceneEntityStoreController:
    def __init__(self, controller: Any | None = None) -> None:
        self._controller: Any | None = controller
        self._revision: int = 0
        self._pending_ops: list[EntityOp] = []
        self._index_revision: int = -1
        self._index_by_name: dict[str, Any] = {}
        self._op_seq: int = 0

    def attach_controller(self, controller: Any) -> None:
        self._controller = controller

    def _get_controller(self, controller: Any | None) -> Any | None:
        return controller or self._controller

    def __iter__(self) -> Any:
        controller = self._get_controller(None)
        if controller is None:
            return iter([])
        return iter(self.iter_entities(controller))

    def __len__(self) -> int:
        controller = self._get_controller(None)
        if controller is None:
            return 0
        return len(getattr(controller, "all_sprites", []))

    @property
    def revision(self) -> int:
        return self._revision

    def invalidate(self, _reason: str | None = None) -> None:
        self._revision += 1
        self._index_revision = -1

    def get(self, controller: Any | None, entity_id: str) -> Any | None:
        return self.find_entity(controller, entity_id)

    def has(self, controller: Any | None, entity_id: str) -> bool:
        return self.get(controller, entity_id) is not None

    def iter_entities(self, controller: Any | None = None) -> list[Any]:
        ctrl = self._get_controller(controller)
        if ctrl is None:
            return []
        return list(ctrl.all_sprites)

    def iter_entity_ids(self, controller: Any | None = None) -> list[str]:
        ctrl = self._get_controller(controller)
        if ctrl is None:
            return []
        ids: list[str] = []
        for sprite in ctrl.all_sprites:
            name = getattr(sprite, "mesh_name", None)
            if isinstance(name, str) and name.strip():
                ids.append(name)
        primary = self._primary_entity_id(ctrl)
        return stable_entity_order(ids, primary)

    def rebuild_index(self, controller: Any | None) -> None:
        ctrl = self._get_controller(controller)
        if ctrl is None:
            self._index_by_name.clear()
            self._index_revision = self._revision
            return
        self._index_by_name.clear()
        for sprite in ctrl.all_sprites:
            name = getattr(sprite, "mesh_name", None)
            if isinstance(name, str) and name.strip() and name not in self._index_by_name:
                self._index_by_name[name] = sprite
        self._index_revision = self._revision

    def _ensure_index(self, controller: Any | None) -> None:
        if self._index_revision == self._revision:
            return
        self.rebuild_index(controller)

    def find_entity(self, controller: Any | None, identifier: str | int) -> Any | None:
        ctrl = self._get_controller(controller)
        if ctrl is None:
            return None
        all_sprites = list(ctrl.all_sprites)
        try:
            idx = int(identifier)
            if 0 <= idx < len(all_sprites):
                return all_sprites[idx]
        except (ValueError, TypeError):
            pass

        target_name = str(identifier).strip()
        if not target_name:
            return None
        self._ensure_index(controller)
        sprite = self._index_by_name.get(target_name)
        if sprite is not None:
            return sprite
        for sprite in all_sprites:
            if getattr(sprite, "mesh_name", "") == target_name:
                return sprite
        return None

    def find_sprite_by_name(self, controller: Any | None, name: str | None) -> Any | None:
        if not name:
            return None
        self._ensure_index(controller)
        sprite = self._index_by_name.get(name)
        if sprite is not None:
            return sprite
        ctrl = self._get_controller(controller)
        if ctrl is None:
            return None
        for sprite in ctrl.all_sprites:
            if getattr(sprite, "mesh_name", None) == name:
                return sprite
        return None

    def find_primary_player_sprite(self, controller: Any | None) -> Any | None:
        ctrl = self._get_controller(controller)
        if ctrl is None:
            return None
        sprites = list(ctrl.all_sprites)
        for sprite in sprites:
            tag = getattr(sprite, "mesh_tag", None)
            if isinstance(tag, str) and tag.strip().lower() == "player":
                return sprite
        for sprite in sprites:
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            for behaviour in behaviours:
                if behaviour.__class__.__name__ == "PlayerController":
                    return sprite
        return None

    def _primary_entity_id(self, controller: Any | None) -> str | None:
        sprite = self.find_primary_player_sprite(controller)
        if sprite is None:
            return None
        name = getattr(sprite, "mesh_name", None)
        if isinstance(name, str) and name.strip():
            return name
        return None

    def enqueue_op(self, op: EntityOp) -> None:
        self._pending_ops.append(op)

    def enqueue_spawn(self, sprite: Any, *, layer_name: str, is_solid: bool) -> None:
        op = EntityOp(kind="spawn", payload={"sprite": sprite, "layer": layer_name, "is_solid": is_solid}, seq=self._op_seq)
        self._op_seq += 1
        self._pending_ops.append(op)

    def enqueue_despawn(self, sprite: Any) -> None:
        op = EntityOp(kind="despawn", payload={"sprite": sprite}, seq=self._op_seq)
        self._op_seq += 1
        self._pending_ops.append(op)

    def enqueue_mutation(
        self,
        sprite: Any,
        *,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        tag: str | None = None,
    ) -> None:
        op = EntityOp(
            kind="mutate",
            payload={"sprite": sprite, "x": x, "y": y, "scale": scale, "tag": tag},
            seq=self._op_seq,
        )
        self._op_seq += 1
        self._pending_ops.append(op)

    def apply_pending_ops(self, controller: Any, *, stage: str | None = None) -> None:
        if not self._pending_ops:
            return
        plan = build_drain_plan(self._pending_ops)
        self._pending_ops.clear()
        for op in plan.ordered_ops:
            payload = op.payload
            if op.kind == "spawn" and isinstance(payload, dict):
                sprite = payload.get("sprite")
                layer_name = payload.get("layer", "entities")
                is_solid = bool(payload.get("is_solid", False))
                if sprite is None:
                    continue
                if layer_name not in controller.layers:
                    controller.layers[layer_name] = []
                layer = controller.layers[layer_name]
                if hasattr(layer, "append"):
                    layer.append(sprite)
                if is_solid:
                    controller.solid_sprites.append(sprite)
                continue
            if op.kind == "despawn" and isinstance(payload, dict):
                sprite = payload.get("sprite")
                if sprite is None:
                    continue
                for layer in controller.layers.values():
                    try:
                        if hasattr(layer, "remove"):
                            layer.remove(sprite)
                    except Exception:
                        pass
                try:
                    controller.solid_sprites.remove(sprite)
                except Exception:
                    pass
                continue
            if op.kind == "mutate" and isinstance(payload, dict):
                sprite = payload.get("sprite")
                if sprite is None:
                    continue
                self.apply_entity_mutation(
                    sprite,
                    x=payload.get("x"),
                    y=payload.get("y"),
                    scale=payload.get("scale"),
                    tag=payload.get("tag"),
                )
                continue
        if plan.ordered_ops:
            self._revision += 1
            self._index_revision = -1

    def drain_pending(self, controller: Any) -> None:
        self.apply_pending_ops(controller, stage="drain")

    def ensure_entity_data_dict(self, sprite: Any) -> dict[str, Any]:
        if not hasattr(sprite, "mesh_entity_data"):
            sprite.mesh_entity_data = {}
        data = getattr(sprite, "mesh_entity_data")
        if not isinstance(data, dict):
            data = {}
            sprite.mesh_entity_data = data
        return data

    def apply_entity_mutation(
        self,
        sprite: Any,
        *,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        tag: str | None = None,
    ) -> None:
        if x is not None:
            sprite.center_x = float(x)
        if y is not None:
            sprite.center_y = float(y)
        if scale is not None:
            sprite.scale = float(scale)
        if tag is not None:
            sprite.mesh_tag = tag

        entity_data = self.ensure_entity_data_dict(sprite)
        if x is not None:
            entity_data["x"] = float(x)
        if y is not None:
            entity_data["y"] = float(y)
        if scale is not None:
            entity_data["scale"] = float(scale)
        if tag is not None:
            entity_data["tag"] = tag
