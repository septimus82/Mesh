from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorldSceneDef:
    key: str
    path: str
    label: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class WorldLink:
    from_key: str
    to_key: str
    via: str | None = None


class WorldController:
    """Lightweight world metadata: scenes, paths, and adjacency."""

    def __init__(self, world_data: Dict[str, Any]) -> None:
        self._id: str = str(world_data.get("id") or "main")
        self._scenes: Dict[str, WorldSceneDef] = {}
        self._links: List[WorldLink] = []
        self._neighbors: Dict[str, List[str]] = {}

        self._start_scene: str | None = world_data.get("start_scene")
        self._start_spawn: str | None = world_data.get("start_spawn")

        self._load_scenes(world_data.get("scenes") or {})
        self._load_links(world_data.get("links") or [])

    def _load_scenes(self, scenes_data: Dict[str, Any]) -> None:
        for key, raw in scenes_data.items():
            if not isinstance(raw, dict):
                continue
            path = raw.get("path")
            if not path:
                continue
            label = raw.get("label") or key
            tags = list(raw.get("tags") or [])
            self._scenes[key] = WorldSceneDef(
                key=key,
                path=str(path),
                label=str(label),
                tags=tags,
            )

    def _load_links(self, links_data: List[Dict[str, Any]]) -> None:
        for raw in links_data:
            if not isinstance(raw, dict):
                continue
            from_key = raw.get("from")
            to_key = raw.get("to")
            via = raw.get("via")
            if not from_key or not to_key:
                continue
            link = WorldLink(from_key=str(from_key), to_key=str(to_key), via=via)
            self._links.append(link)
            self._neighbors.setdefault(link.from_key, []).append(link.to_key)

    @property
    def id(self) -> str:
        return self._id

    def get_scene_def(self, key: str) -> Optional[WorldSceneDef]:
        return self._scenes.get(key)

    def get_scene_path(self, key: str) -> Optional[str]:
        scene = self.get_scene_def(key)
        return scene.path if scene is not None else None

    def get_scene_label(self, key: str) -> Optional[str]:
        scene = self.get_scene_def(key)
        return scene.label if scene is not None else None

    def get_neighbors(self, key: str) -> List[str]:
        return list(self._neighbors.get(key, []))

    def find_scene_key_by_path(self, path: str) -> Optional[str]:
        target = str(path or "").strip()
        if not target:
            return None
        for key, scene in self._scenes.items():
            if scene.path == target:
                return key
        return None

    def get_start_scene_key(self) -> Optional[str]:
        return self._start_scene

    def get_start_spawn(self) -> Optional[str]:
        return self._start_spawn

    def export_metadata(self) -> Dict[str, Any]:
        return {
            "id": self._id,
            "scene_keys": sorted(self._scenes.keys()),
            "start_scene": self._start_scene,
            "start_spawn": self._start_spawn,
        }
