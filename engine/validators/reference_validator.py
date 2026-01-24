"""Validator for asset references in game content."""

import json
from typing import List, Set

from engine.migrations import migrate_payload
from engine.paths import resolve_path


class ReferenceValidator:
    """Validates that all assets referenced in a world/scene exist."""

    def __init__(self, world_path: str, treat_overrides_as_warn: bool = True) -> None:
        self.world_path = world_path
        self.treat_overrides_as_warn = treat_overrides_as_warn
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._checked_paths: Set[str] = set()

    def _check_asset(self, path: str, context: str) -> bool:
        """Check if an asset exists. Returns True if valid."""
        if not path:
            return True

        if path in self._checked_paths:
            return True

        resolved = resolve_path(path)
        if not resolved.exists():
            self.errors.append(f"[{context}] Missing asset: '{path}'")
            return False

        self._checked_paths.add(path)
        return True

    def validate(self) -> bool:
        """Run validation. Returns True if no errors."""
        print(f"[Mesh][Validator] Validating references in '{self.world_path}'...")

        world_file = resolve_path(self.world_path)
        if not world_file.exists():
            self.errors.append(f"World file not found: {self.world_path}")
            return False

        try:
            world_data = json.loads(world_file.read_text(encoding="utf-8"))
            world_data = migrate_payload("world", world_data)
        except Exception as e:
            self.errors.append(f"Failed to load world: {e}")
            return False

        # Validate scenes
        initial_scene = world_data.get("initial_scene")
        if initial_scene:
            self._validate_scene(initial_scene, "World Initial")

        # Validate map nodes
        for node_id, node in world_data.get("map_nodes", {}).items():
            scene_path = node.get("scene_file")
            if scene_path:
                self._validate_scene(scene_path, f"Node {node_id}")

        return len(self.errors) == 0

    def _validate_scene(self, scene_path: str, context: str) -> None:
        resolved = resolve_path(scene_path)
        if not resolved.exists():
            self.errors.append(f"[{context}] Missing scene file: '{scene_path}'")
            return

        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
            data = migrate_payload("scene", data)
        except Exception as e:
            self.errors.append(f"[{context}] Failed to load scene '{scene_path}': {e}")
            return

        scene_ctx = f"Scene {scene_path}"

        # Check tilemap
        tilemap = data.get("tilemap")
        if tilemap:
            self._check_asset(tilemap, scene_ctx)

        # Check entities
        for entity in data.get("entities", []):
            ent_id = entity.get("id", "unknown")
            ent_ctx = f"{scene_ctx} -> Entity {ent_id}"

            # Sprite
            sprite = entity.get("sprite")
            if sprite:
                self._check_asset(sprite, ent_ctx)

            # Animation
            anim = entity.get("animation")
            if anim:
                self._check_asset(anim, ent_ctx)

            # Prefab
            prefab = entity.get("prefab")
            if prefab:
                self._check_asset(prefab, ent_ctx)

            # Check behaviour config for known asset fields?
            # This is harder as it's dynamic.
            # We could check "dialogue_file" if we knew about it.
