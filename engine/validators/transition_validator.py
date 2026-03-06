"""Validator for scene transitions."""

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from engine.paths import resolve_path


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


class TransitionValidator:
    """Validates that all scene transitions point to valid targets."""

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.scene_ids: Set[str] = set()
        self.scene_paths: Dict[str, Path] = {}

    def validate(self, world_path: Path) -> bool:
        """Run validation. Returns True if no errors (or warnings in strict mode)."""
        self.errors.clear()
        self.warnings.clear()
        self.scene_ids.clear()
        self.scene_paths.clear()

        if not world_path.exists():
            self.errors.append(f"World file not found: {world_path}")
            return False

        try:
            with open(world_path, "r", encoding="utf-8") as f:
                world_data = json.load(f)
        except Exception as e:
            self.errors.append(f"Failed to load world: {e}")
            return False

        # Index all scenes
        scenes_map = world_data.get("scenes", {})
        for scene_id, entry in scenes_map.items():
            self.scene_ids.add(scene_id)
            path_str = entry.get("path")
            if path_str:
                self.scene_paths[scene_id] = resolve_path(path_str)

        # Validate each scene
        for scene_id, scene_path in self.scene_paths.items():
            if not scene_path.exists():
                # Already handled by other validators, but good to note
                continue

            self._validate_scene_transitions(scene_id, scene_path)

        if self.strict:
            return len(self.errors) == 0 and len(self.warnings) == 0
        return len(self.errors) == 0

    def _validate_scene_transitions(self, scene_id: str, scene_path: Path) -> None:
        try:
            with open(scene_path, "r", encoding="utf-8") as f:
                scene_data = json.load(f)
        except Exception as e:
            self.errors.append(f"Failed to load scene {scene_id}: {e}")
            return

        transitions = self._find_transitions(scene_data)
        for target in transitions:
            if not self._resolve_target(target):
                msg = f"Scene '{scene_id}' has broken transition to '{target}'"
                if self.strict:
                    self.errors.append(msg)
                else:
                    self.warnings.append(msg)

    def _resolve_target(self, target: str) -> bool:
        # 1. Check if it's a known scene ID
        if target in self.scene_ids:
            return True

        # 2. Check if it's a file path
        try:
            path = resolve_path(target)
            if path.exists():
                return True
        except Exception:
            _log_swallow("TRAN-001", "engine/validators/transition_validator.py pass-only blanket swallow")
            pass

        return False

    def _find_transitions(self, scene_data: Dict[str, Any]) -> List[str]:
        targets = []

        def check_entity(entity: Dict[str, Any]) -> None:
            # Check behaviours
            behaviours = entity.get("behaviours", {})
            if isinstance(behaviours, dict) and "SceneTransition" in behaviours:
                cfg = behaviours["SceneTransition"]
                if isinstance(cfg, dict) and "target_scene" in cfg:
                    targets.append(cfg["target_scene"])

            # Check behaviour_config
            b_config = entity.get("behaviour_config", {})
            if isinstance(b_config, dict) and "SceneTransition" in b_config:
                cfg = b_config["SceneTransition"]
                if isinstance(cfg, dict) and "target_scene" in cfg:
                    targets.append(cfg["target_scene"])

        # Scan entities
        entities = scene_data.get("entities", [])
        if isinstance(entities, list):
            for ent in entities:
                check_entity(ent)
        elif isinstance(entities, dict):
            for ent in entities.values():
                check_entity(ent)

        # Scan layers
        layers = scene_data.get("layers", {})
        if isinstance(layers, dict):
            for layer in layers.values():
                l_entities = layer.get("entities", [])
                if isinstance(l_entities, list):
                    for ent in l_entities:
                        check_entity(ent)
                elif isinstance(l_entities, dict):
                    for ent in l_entities.values():
                        check_entity(ent)
        elif isinstance(layers, list):
            for layer in layers:
                l_entities = layer.get("entities", [])
                if isinstance(l_entities, list):
                    for ent in l_entities:
                        check_entity(ent)
                elif isinstance(l_entities, dict):
                    for ent in l_entities.values():
                        check_entity(ent)

        return targets
