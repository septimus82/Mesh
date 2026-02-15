"""Project indexing helpers for Mesh Engine."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Set

from .. import json_io
from ..behaviours import list_behaviours
from ..config import EngineConfig
from ..input import InputManager
from mesh_cli.version_info import get_tool_version
import engine.optional_arcade as optional_arcade
arcade_mod = optional_arcade.arcade
from ..scene_loader import SceneLoader

CLI_PREFIX = "[Mesh][ProjectIndex]"


def build_project_index(
    scenes_root: str = "scenes",
    config: EngineConfig | None = None,
) -> dict[str, Any]:
    """Scan scenes, behaviours, and input bindings to build an index."""

    loader = SceneLoader()
    root = Path(scenes_root)
    project_root = Path.cwd()
    scene_files = _discover_scene_files(root)

    scenes: list[dict[str, Any]] = []
    all_tags: Set[str] = set()
    all_layers: Set[str] = set()

    for path in scene_files:
        summary = _summarize_scene(path, loader, project_root)
        scenes.append(summary)
        all_tags.update(summary.get("tags", []))
        all_layers.update(summary.get("layers", []))

    engine_section = {
        "version": get_tool_version(),
        "config_defaults": asdict(config) if config is not None else {},
        "input_actions": _input_snapshot(),
    }

    behaviours_section = _behaviours_snapshot()

    index: dict[str, Any] = {
        "engine": engine_section,
        "behaviours": behaviours_section,
        "scenes": scenes,
        "tags": sorted(all_tags),
        "layers": sorted(all_layers),
    }
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Mesh project index JSON file.")
    parser.add_argument("--scenes-root", default="scenes", help="Directory containing scene JSON files")
    parser.add_argument("--output", default="mesh_index.json", help="Where to write the index JSON")
    args = parser.parse_args(argv)

    index = build_project_index(args.scenes_root)
    output_path = Path(args.output)
    json_io.write_json_atomic(output_path, index)

    scene_count = len(index.get("scenes", []))
    behaviour_count = len(index.get("behaviours", []))
    print(f"{CLI_PREFIX} Indexed {scene_count} scene(s), {behaviour_count} behaviours -> {output_path}")
    return 0


def _discover_scene_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def _summarize_scene(
    path: Path,
    loader: SceneLoader,
    project_root: Path,
) -> dict[str, Any]:
    display_path = _format_scene_path(path, project_root)
    report = loader.validate_scene_file(str(path))
    scene_data = _load_scene_data(path, loader)

    entities = scene_data.get("entities", []) if scene_data else []
    settings = scene_data.get("settings", {}) if scene_data else {}
    declared_layers = _declared_layers(scene_data)
    entity_layers = _entity_layers(entities)
    tags = _collect_tags(entities)
    behaviours_used = _collect_behaviours(entities)

    summary = {
        "path": display_path,
        "valid": report.ok,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "entity_count": len(entities),
        "tags": sorted(tags),
        "behaviours_used": sorted(behaviours_used),
        "layers": sorted(set(declared_layers) | entity_layers),
        "settings": _settings_summary(settings),
    }
    return summary


def _load_scene_data(path: Path, loader: SceneLoader) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw_scene: Dict[str, Any] = json.load(handle)
    except Exception:
        return None

    scene = loader.apply_scene_defaults(raw_scene)
    normalized_entities = [loader.apply_entity_defaults(entity) for entity in scene.get("entities", [])]
    scene["entities"] = normalized_entities
    return scene


def _declared_layers(scene: dict[str, Any] | None) -> Set[str]:
    layers: Set[str] = set()
    if not scene:
        return layers
    for entry in scene.get("layers", []) or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                layers.add(name.strip())
    return layers


def _entity_layers(entities: list[dict[str, Any]]) -> Set[str]:
    layers: Set[str] = set()
    for entity in entities:
        name = entity.get("layer")
        if isinstance(name, str) and name.strip():
            layers.add(name.strip())
    return layers


def _collect_tags(entities: list[dict[str, Any]]) -> Set[str]:
    tags: Set[str] = set()
    for entity in entities:
        tag = entity.get("tag")
        if isinstance(tag, str) and tag.strip():
            tags.add(tag.strip())
    return tags


def _collect_behaviours(entities: list[dict[str, Any]]) -> Set[str]:
    behaviours: Set[str] = set()
    for entity in entities:
        for entry in entity.get("behaviours", []) or []:
            if isinstance(entry, dict):
                behaviour_type = entry.get("type")
            elif isinstance(entry, str):
                behaviour_type = entry
            else:
                behaviour_type = None
            if isinstance(behaviour_type, str) and behaviour_type.strip():
                behaviours.add(behaviour_type.strip())
    return behaviours


def _settings_summary(settings: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("background_color", "world_width", "world_height"):
        if key in settings:
            summary[key] = settings[key]
    return summary


def _behaviours_snapshot() -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for info in list_behaviours():
        fields = [_behaviour_field_snapshot(field) for field in info.config_fields]
        snapshot.append(
            {
                "name": info.name,
                "description": info.description,
                "config_fields": fields,
            },
        )
    return snapshot


def _behaviour_field_snapshot(field_entry: Any) -> dict[str, Any]:
    if isinstance(field_entry, dict):
        return {
            "name": field_entry.get("name"),
            "description": field_entry.get("description"),
            "type": field_entry.get("type"),
            "default": field_entry.get("default"),
        }
    return {
        "name": None,
        "description": None,
        "type": None,
        "default": None,
    }


def _input_snapshot() -> dict[str, Any]:
    manager = InputManager()
    if arcade_mod is not None:
        manager.bind_default_actions(arcade_mod)
    bindings = manager.get_bindings()
    snapshot: dict[str, Any] = {}
    for action, codes in sorted(bindings.items()):
        key_codes = [int(code) for code in codes]
        snapshot[action] = {
            "key_codes": key_codes,
            "key_names": _key_names_for_codes(key_codes, arcade_mod=arcade_mod),
        }
    return snapshot


def _key_names_for_codes(codes: Iterable[int], *, arcade_mod: object | None) -> list[str]:
    names: list[str] = []
    symbol_string = getattr(getattr(arcade_mod, "key", None), "symbol_string", None) if arcade_mod is not None else None
    for code in codes:
        label: str | None = None
        if callable(symbol_string):
            try:
                label = symbol_string(int(code))
            except Exception:
                label = None
        names.append(label or f"KEY_{code}")
    return names


def _format_scene_path(path: Path, project_root: Path) -> str:
    try:
        rel = path.relative_to(project_root)
        return rel.as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
