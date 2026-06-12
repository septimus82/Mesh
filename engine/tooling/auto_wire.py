"""Auto-wiring tool for scene transitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

from engine import json_io
from engine.paths import resolve_path


class AutoWireController:
    """Analyzes and fixes missing scene transitions."""

    def __init__(self, world_path: str, writer: Optional[Callable[[Path, str], None]] = None) -> None:
        self.world_path = resolve_path(world_path)
        self._writer = writer
        # Back-compat: some callers access `controller.writer` directly.
        self.writer = writer
        self.world_data: Dict[str, Any] = {}
        self.scenes: Dict[str, Dict[str, Any]] = {}
        self.scene_paths: Dict[str, Path] = {}
        self.modified_scenes: Dict[str, Dict[str, Any]] = {}

    def load(self) -> None:
        """Load world and all referenced scenes."""
        self.modified_scenes = {}
        if not self.world_path.exists():
            raise FileNotFoundError(f"World file not found: {self.world_path}")

        with open(self.world_path, "r", encoding="utf-8") as f:
            self.world_data = json.load(f)

        scenes_map = self.world_data.get("scenes", {})
        for scene_id, entry in scenes_map.items():
            path_str = entry.get("path")
            if not path_str:
                continue
            path = resolve_path(path_str)
            if path.exists():
                self.scene_paths[scene_id] = path
                with open(path, "r", encoding="utf-8") as f:
                    self.scenes[scene_id] = json.load(f)

    def process(self, dry_run: bool = True) -> List[str]:
        """Find and fix missing transitions."""
        changes = []

        # 1. Infer links from naming conventions (Hub <-> Interior, Hub <-> Dungeon)
        # 2. Check existing one-way transitions

        # Strategy: Build a graph of existing transitions
        graph: Dict[str, List[str]] = {sid: [] for sid in self.scenes}

        for scene_id, scene_data in self.scenes.items():
            transitions = self._find_transitions(scene_data)
            for target in transitions:
                # Resolve target path to scene_id
                target_id = self._resolve_scene_id(target)
                if target_id and target_id in self.scenes:
                    graph[scene_id].append(target_id)

        # Check for missing back-links
        for src, targets in graph.items():
            for dst in targets:
                if src not in graph[dst]:
                    # Missing back-link from dst to src
                    if self._add_transition(dst, src):
                        changes.append(f"Added transition from {dst} to {src}")

        # 3. Template-based Wiring (Metadata)
        for scene_id, scene_data in self.scenes.items():
            settings = scene_data.get("settings", {})
            template = settings.get("region_template")
            kind = settings.get("scene_kind")

            if not template or not kind:
                continue

            # Deduce prefix from ID and kind
            prefix = None
            if kind == "hub" and scene_id.endswith("_hub"):
                prefix = scene_id[:-4]
            elif kind == "interior" and scene_id.endswith("_interior"):
                prefix = scene_id[:-9]
            elif kind == "dungeon" and scene_id.endswith("_dungeon"):
                prefix = scene_id[:-8]
            elif kind == "path" and scene_id.endswith("_path"):
                prefix = scene_id[:-5]
            elif kind == "entry" and scene_id.endswith("_entry"):
                prefix = scene_id[:-6]
            elif kind == "depths" and scene_id.endswith("_depths"):
                prefix = scene_id[:-7]

            if not prefix:
                continue

            siblings = {}
            if template == "hub-interior-dungeon":
                siblings = {
                    "hub": f"{prefix}_hub",
                    "interior": f"{prefix}_interior",
                    "dungeon": f"{prefix}_dungeon"
                }
                if kind == "hub":
                    self._ensure_link(scene_id, siblings["interior"], changes, graph)
                    self._ensure_link(scene_id, siblings["dungeon"], changes, graph)
                elif kind == "interior":
                    self._ensure_link(scene_id, siblings["hub"], changes, graph)
                elif kind == "dungeon":
                    self._ensure_link(scene_id, siblings["hub"], changes, graph)

            elif template == "ruins":
                siblings = {
                    "hub": f"{prefix}_hub",
                    "path": f"{prefix}_path",
                    "dungeon": f"{prefix}_dungeon"
                }
                if kind == "hub":
                    self._ensure_link(scene_id, siblings["path"], changes, graph)
                elif kind == "path":
                    self._ensure_link(scene_id, siblings["hub"], changes, graph)
                    self._ensure_link(scene_id, siblings["dungeon"], changes, graph)
                elif kind == "dungeon":
                    self._ensure_link(scene_id, siblings["path"], changes, graph)

            elif template == "deep-dungeon":
                siblings = {
                    "entry": f"{prefix}_entry",
                    "depths": f"{prefix}_depths"
                }
                if kind == "entry":
                    self._ensure_link(scene_id, siblings["depths"], changes, graph)
                elif kind == "depths":
                    self._ensure_link(scene_id, siblings["entry"], changes, graph)

        # 4. Legacy Heuristic (Fallback)
        for scene_id in self.scenes:
            # Skip if metadata present (handled above)
            if self.scenes[scene_id].get("settings", {}).get("region_template"):
                continue

            if "_hub" in scene_id:
                base_name = scene_id.replace("_hub", "")
                interior = f"{base_name}_interior"
                dungeon = f"{base_name}_dungeon"

                if interior in self.scenes:
                    self._ensure_link(scene_id, interior, changes, graph)
                    self._ensure_link(interior, scene_id, changes, graph)

                if dungeon in self.scenes:
                    self._ensure_link(scene_id, dungeon, changes, graph)
                    self._ensure_link(dungeon, scene_id, changes, graph)

        if not dry_run and changes:
            self._save_changes()

        return changes

    def _ensure_link(self, src: str, dst: str, changes: List[str], graph: Dict[str, List[str]]) -> None:
        if dst in self.scenes:
            if dst not in graph[src]:
                if self._add_transition(src, dst):
                    changes.append(f"Added transition from {src} to {dst}")
                    graph[src].append(dst)

    def _find_transitions(self, scene_data: Dict[str, Any]) -> List[str]:
        targets = []

        # Helper to check entities
        def check_entities(entity_iter):
            for entity in entity_iter:
                behavious = entity.get("behaviours", {})
                # Check explicit config
                if isinstance(behavious, dict) and "SceneTransition" in behavious:
                    cfg = behavious["SceneTransition"]
                    if "target_scene" in cfg:
                        targets.append(cfg["target_scene"])
                # Check behaviour_config
                b_config = entity.get("behaviour_config", {})
                if "SceneTransition" in b_config:
                    cfg = b_config["SceneTransition"]
                    if "target_scene" in cfg:
                        targets.append(cfg["target_scene"])

        # Check top-level entities
        top_entities = scene_data.get("entities")
        if top_entities:
            if isinstance(top_entities, dict):
                check_entities(top_entities.values())
            elif isinstance(top_entities, list):
                check_entities(top_entities)

        # Check layers
        layers = scene_data.get("layers", {})
        layer_iter: Iterable[Any]
        if isinstance(layers, dict):
            layer_iter = layers.values()
        elif isinstance(layers, list):
            layer_iter = layers
        else:
            layer_iter = []

        for layer in layer_iter:
            entities = layer.get("entities", {})
            if isinstance(entities, dict):
                check_entities(entities.values())
            elif isinstance(entities, list):
                check_entities(entities)

        return targets

    def _resolve_scene_id(self, path_str: str) -> Optional[str]:
        # Normalize path separators
        norm_path = str(Path(path_str)).replace("\\", "/")
        for sid, path in self.scene_paths.items():
            # Check if path ends with the target path (handling relative paths)
            # This is a bit loose but works for now
            if str(path).replace("\\", "/").endswith(norm_path):
                return sid
        return None

    def _add_transition(self, from_id: str, to_id: str) -> bool:
        if from_id in self.modified_scenes:
            scene = self.modified_scenes[from_id]
        else:
            scene = self.scenes[from_id]

        # Check if already exists (double check to avoid duplicates in same pass)
        existing = self._find_transitions(scene)
        to_path_obj = self.scene_paths[to_id]
        try:
            # Ensure we compare absolute paths
            root = resolve_path(".").resolve()
            to_path = str(to_path_obj.resolve().relative_to(root))
        except ValueError:
            to_path = str(to_path_obj)

        # Fix path separators for JSON
        to_path = to_path.replace("\\", "/")

        # If we already have a transition to this path (or resolved ID), skip
        # But _find_transitions returns paths.
        # Let's just check if we've already added it in this session or it existed
        # For simplicity, assume if it wasn't in the graph, it's not there.

        # Determine position
        pos = (0, 0)
        if "interior" in from_id:
            pos = (0, -200)  # Bottom center for interior exit
        elif "hub" in from_id:
            # Place randomly or at edge?
            # Let's put it at (300, 0) for now to avoid overlap
            pos = (300, 0)

        # Create entity
        entity = {
            "type": "prop",
            "x": pos[0],
            "y": pos[1],
            "behaviours": ["SceneTransition"],
            "behaviour_config": {
                "SceneTransition": {
                    "target_scene": to_path,
                    "spawn_point": "default"
                }
            },
            "tags": ["auto_wired"]
        }

        # Add to "entities" layer or top-level
        layers = scene.get("layers")
        top_entities = scene.get("entities")

        target_collection = None

        if not layers and top_entities is not None:
            # Use top-level
            target_collection = top_entities
        else:
            # Use layers (create if needed)
            if layers is None:
                layers = []
                scene["layers"] = layers

            ent_layer = None
            if isinstance(layers, list):
                for layer in layers:
                    if layer.get("name") == "entities":
                        ent_layer = layer
                        break
                if not ent_layer:
                    ent_layer = {"name": "entities", "entities": {}}
                    layers.append(ent_layer)
            elif isinstance(layers, dict):
                ent_layer = layers.setdefault("entities", {})

            ent_layer_dict = cast(dict[str, Any], ent_layer)
            target_collection = ent_layer_dict.get("entities")
            if target_collection is None:
                target_collection = {}
                ent_layer_dict["entities"] = target_collection

        if isinstance(target_collection, list):
            target_collection.append(entity)
        else:
            # Find unique ID
            next_id = 1
            while str(next_id) in target_collection:
                next_id += 1
            target_collection[str(next_id)] = entity

        self.modified_scenes[from_id] = scene
        return True

    def _save_changes(self) -> None:
        for sid, scene in self.modified_scenes.items():
            path = self.scene_paths[sid]
            content = json_io.dumps_stable(scene) + "\n"
            if self._writer is not None:
                self._writer(path, content)
            else:
                json_io.write_text_atomic(path, content, encoding="utf-8")
