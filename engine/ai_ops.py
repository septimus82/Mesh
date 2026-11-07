"""AI-friendly operations layer for Mesh."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import json_io
from .editor_palette import load_prefab_palette
from .scene_loader import SceneLoader


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    json_io.write_json_atomic(path, payload)


def _deep_merge(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    merged = dict(dest)
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _unknown_light_settings(settings: dict[str, Any]) -> str | None:
    """A refusal naming settings a light doesn't have (the canonical set_light's), or None."""
    import inspect

    from . import project_ops as ops

    known = [name for name in inspect.signature(ops.set_light).parameters if name not in ("scene", "index")]
    unknown = sorted(set(settings) - set(known))
    return f"Lights have no setting {', '.join(map(repr, unknown))}. They have: {', '.join(known)}." if unknown else None


def find_prefab_palette_entry(
    palette: list[dict[str, Any]],
    prefab_name: str,
    *,
    include_id: bool = False,
) -> dict[str, Any] | None:
    """Find a prefab palette entry using the same keys as AIOps by default."""
    for entry in palette:
        if not isinstance(entry, dict):
            continue
        if entry.get("display_name") == prefab_name or entry.get("name") == prefab_name:
            return entry
        if include_id and entry.get("id") == prefab_name:
            return entry
    return None


def build_prefab_entity_definition(
    match: dict[str, Any],
    prefab_name: str,
    x: float,
    y: float,
    scene: dict[str, Any],
    *,
    name: str | None = None,
    entity_id: str | None = None,
) -> dict[str, Any]:
    """Build a uniquely named entity definition from a prefab palette entry."""
    entity_def = deepcopy(match.get("entity") or {})
    entity_def["x"] = float(x)
    entity_def["y"] = float(y)
    if entity_id:
        entity_def["id"] = str(entity_id)
    if name:
        entity_def["name"] = str(name)
    if "name" not in entity_def or not entity_def.get("name"):
        entity_def["name"] = f"{prefab_name}_{len(scene.get('entities', [])) + 1}"
    existing_names = {e.get("name") for e in scene.get("entities", []) if isinstance(e, dict)}
    base_name = str(entity_def["name"])
    counter = 1
    while entity_def["name"] in existing_names:
        entity_def["name"] = f"{base_name}_{counter}"
        counter += 1
    return entity_def


@dataclass
class AIOpsResult:
    ok: bool
    message: str
    data: dict[str, Any] | None = None


class AIOps:
    """Small, stable set of scene/content operations for AI tools."""

    def __init__(self, base_dir: str | Path = ".") -> None:
        self.base_dir = Path(base_dir)

    def _contain(self, path: Path, original: str | None) -> Path:
        resolved_base = self.base_dir.resolve()
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(resolved_base):
            raise ValueError(f"path escapes workspace: {original or path}")
        return resolved_path

    # ------------------------------------------------------------------ world helpers
    def _world_path(self, world_path: str | None) -> Path:
        path = Path(world_path or "worlds/main_world.json")
        if not path.is_absolute():
            path = self.base_dir / path
        return self._contain(path, world_path)

    def _load_world_json(self, world_path: str | None) -> tuple[Path, dict[str, Any]]:
        path = self._world_path(world_path)
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"World root must be an object: {path}")
        payload.setdefault("scenes", {})
        payload.setdefault("links", [])
        return path, payload

    def _save_world_json(self, path: Path, payload: dict[str, Any]) -> None:
        _write_json(path, payload)

    # ------------------------------------------------------------------ scene helpers
    def _scene_path(self, scene_path: str) -> Path:
        path = Path(scene_path)
        if not path.is_absolute():
            path = self.base_dir / path
        return self._contain(path, scene_path)

    def _load_scene(self, scene_path: str) -> tuple[Path, dict[str, Any]]:
        path = self._scene_path(scene_path)
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"Scene root must be an object: {path}")
        if "entities" not in payload:
            payload["entities"] = []
        return path, payload

    def _save_scene(self, path: Path, payload: dict[str, Any], compact: bool = True) -> None:
        if compact:
            from .scene_serializer import compact_scene_payload
            payload = compact_scene_payload(payload)
        _write_json(path, payload)

    # ------------------------------------------------------------------ cutscene helpers
    def _cutscene_path(self, cutscenes_path: str | None) -> Path:
        path = Path(cutscenes_path or "cutscenes.json")
        if not path.is_absolute():
            path = self.base_dir / path
        return self._contain(path, cutscenes_path)

    def _load_cutscene_store(self, cutscenes_path: str | None) -> tuple[Path, dict[str, Any]]:
        path = self._cutscene_path(cutscenes_path)
        if path.exists():
            raw = _load_json(path)
        else:
            raw = {}
        if isinstance(raw, list):
            payload = {"cutscenes": raw}
        elif isinstance(raw, dict):
            payload = raw
        else:
            raise ValueError(f"Cutscene file must be an object or array: {path}")
        payload.setdefault("cutscenes", [])
        if not isinstance(payload["cutscenes"], list):
            raise ValueError(f"Cutscene file 'cutscenes' must be an array: {path}")
        return path, payload

    def _save_cutscene_store(self, path: Path, payload: dict[str, Any]) -> None:
        _write_json(path, payload)

    # ------------------------------------------------------------------ operations
    def create_scene(self, name: str, template: str = "empty") -> AIOpsResult:
        from .tooling_runtime import scaffold

        scene_name = name if name.endswith(".json") else f"{name}.json"
        requested = Path(scene_name) if Path(scene_name).is_absolute() else self.base_dir / scene_name
        # The requested entry itself, in its folder inside the workspace: never where a link there points (resolving
        # the whole path made a broken link's destination the target, and the scene was written through the link).
        path = self._contain(requested.parent, scene_name) / requested.name
        if os.path.lexists(path):  # (F14: never taken for a scene just made, and never replaced)
            what = "a link" if path.is_symlink() else "a folder" if path.is_dir() else "a scene file"
            return AIOpsResult(False, f"Scene '{scene_name}' wasn't created: there is already {what} at {path}, "
                                      "left as it is. Choose another name (or read and edit that scene instead).",
                               {"path": str(path), "reason": "already_exists"})
        templates = scaffold.list_scene_template_names()
        if template not in templates:
            return AIOpsResult(False, f"Scene '{scene_name}' wasn't created: there is no scene template '{template}' "
                                      f"(templates: {', '.join(templates)}).",
                               {"path": str(path), "reason": "unknown_template"})
        if not scaffold.create_scene(str(path), template_name=template):
            if os.path.lexists(path):  # (something was put there meanwhile: left as it is, never taken as created)
                return AIOpsResult(False, f"Scene '{scene_name}' wasn't created: something appeared at {path} while "
                                          "it was being created, and was left as it is. Choose another name.",
                                   {"path": str(path), "reason": "already_exists"})
            return AIOpsResult(False, f"Scene '{scene_name}' wasn't created: writing {path} failed; see the log. "
                                      "Nothing else was changed.",
                               {"path": str(path), "reason": "write_failed"})
        return AIOpsResult(True, f"Created scene '{scene_name}'")

    def add_entity_from_prefab(
        self,
        scene_path: str,
        prefab_name: str,
        x: float,
        y: float,
        *,
        prefab_path: Optional[str] = None,
    ) -> AIOpsResult:
        scene_file, scene = self._load_scene(scene_path)
        # No path: the project's prefab catalogue (an empty path would name the project folder itself)
        palette = load_prefab_palette(prefab_path, strict=False) if prefab_path else load_prefab_palette(strict=False)
        match = find_prefab_palette_entry(palette, prefab_name)
        if match is None and prefab_path:
            try:
                raw = _load_json(Path(prefab_path))
                if isinstance(raw, list):
                    match = find_prefab_palette_entry(raw, prefab_name)
            except Exception:
                match = None
        if match is None:
            return AIOpsResult(False, f"Prefab '{prefab_name}' not found")
        entity_def = build_prefab_entity_definition(match, prefab_name, x, y, scene)
        scene.setdefault("entities", []).append(entity_def)
        self._save_scene(scene_file, scene)
        return AIOpsResult(True, f"Added prefab '{prefab_name}' to {scene_path}", {"entity_name": entity_def["name"]})

    def _edit_scene(self, scene_path: str, change: Callable[[dict[str, Any]], dict[str, Any]], done: str,
                    data: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> AIOpsResult:
        """One edit of one scene file through the canonical, validated operations (``project_ops``, as Mesh
        Studio and the authoring API use): the same result and the same refusals whoever asks."""
        from . import project_ops as ops

        scene_file, scene = self._load_scene(scene_path)
        if any(isinstance(e, dict) and not e.get("id") for e in ops.entities(scene)):
            scene = ops.ensure_entity_ids(scene, scene_file.stem)  # older scenes: objects are edited by id
        try:
            out = change(scene)
        except (ops.OpError, TypeError) as exc:
            return AIOpsResult(False, str(exc))
        self._save_scene(scene_file, out)
        return AIOpsResult(True, done, data(out) if data else {})

    def delete_entity(self, scene_path: str, entity_id: str) -> AIOpsResult:
        from . import project_ops as ops

        return self._edit_scene(scene_path, lambda s: ops.remove_entity(s, ops.entity_ref(s, entity_id)),
                                f"Deleted entity '{entity_id}'")

    def set_behaviour_params(
        self,
        scene_path: str,
        entity_id: str,
        behaviour_name: str,
        params: dict[str, Any],
    ) -> AIOpsResult:
        """Give the object the behaviour if it lacks it, then set each param. A dict value is merged into the
        current one (so a partial dialogue patch keeps the rest)."""
        from . import project_ops as ops

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            target = ops.entity_ref(scene, entity_id)
            if behaviour_name not in ops.entity_behaviours(ops.find_entity(scene, target)):
                scene = ops.add_behaviour(scene, target, behaviour_name)
            for param, value in (params or {}).items():
                config = (ops.find_entity(scene, target).get("behaviour_config") or {}).get(behaviour_name) or {}
                current = config.get(param)
                if isinstance(value, dict) and isinstance(current, dict):
                    value = _deep_merge(deepcopy(current), value)
                scene = ops.set_behaviour_param(scene, target, behaviour_name, param, value)
            return scene

        return self._edit_scene(scene_path, change, f"Updated {behaviour_name} on '{entity_id}'")

    def edit_dialogue(self, scene_path: str, entity_id: str, patch: dict[str, Any]) -> AIOpsResult:
        return self.set_behaviour_params(scene_path, entity_id, "Dialogue", {"dialogue": patch})

    def edit_quest(self, quest_id: str, patch: dict[str, Any], quests_path: str = "assets/data/quests.json") -> AIOpsResult:
        path = self._scene_path(quests_path)
        payload = _load_json(path)
        quests = payload.get("quests") if isinstance(payload, dict) else None
        if not isinstance(quests, dict):
            return AIOpsResult(False, "quests.json missing quests object")
        quest = quests.get(quest_id)
        if not isinstance(quest, dict):
            return AIOpsResult(False, f"Quest '{quest_id}' not found")
        quests[quest_id] = _deep_merge(quest, patch)
        _write_json(path, payload)
        return AIOpsResult(True, f"Updated quest '{quest_id}'")

    def add_or_update_quest_definition(
        self,
        quest_id: str,
        quest_data: dict[str, Any],
        quests_path: str = "assets/data/quests.json",
    ) -> AIOpsResult:
        path = self._scene_path(quests_path)
        payload = _load_json(path)
        if not isinstance(payload, dict):
            return AIOpsResult(False, "quests root must be an object")
        quests = payload.setdefault("quests", {})
        if not isinstance(quests, dict):
            payload["quests"] = {}
            quests = payload["quests"]
        existing = quests.get(quest_id, {})
        if isinstance(existing, dict):
            quests[quest_id] = _deep_merge(existing, quest_data)
        else:
            quests[quest_id] = quest_data
        _write_json(path, payload)
        return AIOpsResult(True, f"Upserted quest '{quest_id}'")

    def delete_quest_definition(self, quest_id: str, quests_path: str = "assets/data/quests.json") -> AIOpsResult:
        path = self._scene_path(quests_path)
        payload = _load_json(path)
        quests = payload.get("quests") if isinstance(payload, dict) else None
        if not isinstance(quests, dict):
            return AIOpsResult(False, "quests.json missing quests object")
        if quest_id not in quests:
            return AIOpsResult(False, f"Quest '{quest_id}' not found")
        deleted = quests.pop(quest_id)
        _write_json(path, payload)
        return AIOpsResult(True, f"Deleted quest '{quest_id}'", {"deleted": deleted})

    # --- world -------------------------------------------------------
    def add_world_scene(
        self,
        scene_key: str,
        path: str,
        *,
        world_path: str | None = None,
        label: str | None = None,
        tags: list[str] | None = None,
    ) -> AIOpsResult:
        world_file, world = self._load_world_json(world_path)
        scenes = world.setdefault("scenes", {})
        scenes[scene_key] = {
            "path": path,
            "label": label or scene_key,
            "tags": tags or [],
        }
        self._save_world_json(world_file, world)
        return AIOpsResult(True, f"Added world scene '{scene_key}'", {"scene_key": scene_key, "world_path": str(world_file)})

    def link_world_scenes(
        self,
        from_key: str,
        to_key: str,
        *,
        world_path: str | None = None,
        via: str | None = None,
        bidirectional: bool = True,
    ) -> AIOpsResult:
        world_file, world = self._load_world_json(world_path)
        links = world.setdefault("links", [])
        if not isinstance(links, list):
            links = []
            world["links"] = links

        def _append(a: str, b: str, v: str | None) -> None:
            links.append({"from": a, "to": b, "via": v})

        _append(from_key, to_key, via)
        if bidirectional:
            _append(to_key, from_key, via)
        self._save_world_json(world_file, world)
        return AIOpsResult(True, f"Linked {from_key}->{to_key}", {"world_path": str(world_file)})

    def set_world_start(
        self,
        *,
        world_path: str | None = None,
        start_scene: str | None = None,
        start_spawn: str | None = None,
    ) -> AIOpsResult:
        world_file, world = self._load_world_json(world_path)
        if start_scene is not None:
            world["start_scene"] = start_scene
        if start_spawn is not None:
            world["start_spawn"] = start_spawn
        self._save_world_json(world_file, world)
        return AIOpsResult(True, "Updated world start scene", {"world_path": str(world_file)})

    def paint_tiles(self, scene_path: str, ops: list[dict[str, Any]]) -> AIOpsResult:
        scene_file, scene = self._load_scene(scene_path)
        tilemap = scene.setdefault("tilemap", {})
        if not isinstance(tilemap, dict):
            return AIOpsResult(False, "tilemap must be an object")
        overrides = tilemap.setdefault("overrides", {})
        if not isinstance(overrides, dict):
            tilemap["overrides"] = {}
            overrides = tilemap["overrides"]
        layers = overrides.setdefault("layers", {})
        if not isinstance(layers, dict):
            overrides["layers"] = {}
            layers = overrides["layers"]

        # Determine map dimensions from the tilemap file if present.
        width = height = None
        map_path = tilemap.get("path")
        if isinstance(map_path, str):
            resolved = (scene_file.parent / map_path).resolve()
            try:
                map_json = _load_json(resolved)
                width = int(map_json.get("width", 0)) or None
                height = int(map_json.get("height", 0)) or None
            except Exception as exc:  # noqa: BLE001  # REASON: map dimension inference warning fallback
                if not getattr(self, "_mesh_paint_tiles_map_dim_error_logged", False):
                    print(f"[Mesh][AIOps] WARNING: Failed to infer map dimensions from '{resolved}': {exc}")
                    setattr(self, "_mesh_paint_tiles_map_dim_error_logged", True)

        for op in ops:
            layer = str(op.get("layer", "ground"))
            col = int(op.get("col", 0))
            row = int(op.get("row", 0))
            gid = int(op.get("gid", 0))
            data = layers.get(layer)
            if not isinstance(data, list):
                # Build a new layer sized by known map dims or minimal required size
                w = width or (col + 1)
                h = height or (row + 1)
                size = max(1, w * h)
                data = [0] * size
                layers[layer] = data
            if width and height:
                size = width * height
                if len(data) < size:
                    data.extend([0] * (size - len(data)))
                index = row * width + col
            else:
                # Best-effort: infer width from current data length if square-ish
                inferred_width = int((len(data) ** 0.5)) or (col + 1)
                inferred_width = max(inferred_width, col + 1)
                needed = inferred_width * (row + 1)
                if len(data) < needed:
                    data.extend([0] * (needed - len(data)))
                index = row * inferred_width + col
            if index >= len(data):
                data.extend([0] * (index - len(data) + 1))
            data[index] = gid

        self._save_scene(scene_file, scene)
        return AIOpsResult(True, f"Painted {len(ops)} tile op(s)")

    # --- lights ------------------------------------------------------
    def add_light(self, scene_path: str, light: dict[str, Any]) -> AIOpsResult:
        """A point light; settings beyond position, size and colour as ``update_light`` takes them."""
        from . import project_ops as ops

        rest = {k: v for k, v in light.items() if k not in ("x", "y", "radius", "color")}
        if unknown := _unknown_light_settings(rest):
            return AIOpsResult(False, unknown)

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, index = ops.add_light(scene, float(light.get("x", 0.0)), float(light.get("y", 0.0)),
                                       color=light.get("color", "#ffddaa"), radius=light.get("radius", 160.0))
            return ops.set_light(out, index, **rest) if rest else out

        return self._edit_scene(scene_path, change, "Added light", lambda s: {
            "index": len(s["lights"]) - 1, "light": s["lights"][-1]})

    def update_light(self, scene_path: str, index: int, patch: dict[str, Any]) -> AIOpsResult:
        from . import project_ops as ops

        if unknown := _unknown_light_settings(patch):
            return AIOpsResult(False, unknown)

        return self._edit_scene(scene_path, lambda s: ops.set_light(s, index, **patch), f"Updated light {index}",
                                lambda s: {"index": index, "light": s["lights"][index]})

    def delete_light(self, scene_path: str, index: int) -> AIOpsResult:
        from . import project_ops as ops

        _scene_file, before = self._load_scene(scene_path)
        lights = ops.lights(before)
        deleted = lights[index] if 0 <= index < len(lights) else None
        return self._edit_scene(scene_path, lambda s: ops.remove_light(s, index), f"Deleted light {index}",
                                lambda _s: {"deleted": deleted, "index": index})

    # ------------------------------------------------------------------ cutscene operations
    def add_or_update_cutscene(
        self,
        cutscene_id: str,
        steps: list[dict[str, Any]] | None = None,
        *,
        cutscenes_path: str | None = None,
    ) -> AIOpsResult:
        path, payload = self._load_cutscene_store(cutscenes_path)
        steps = steps or []
        cutscene_list = payload.setdefault("cutscenes", [])
        for entry in cutscene_list:
            if isinstance(entry, dict) and entry.get("id") == cutscene_id:
                entry["steps"] = steps
                self._save_cutscene_store(path, payload)
                return AIOpsResult(True, f"Updated cutscene '{cutscene_id}'", {"id": cutscene_id})
        cutscene_list.append({"id": cutscene_id, "steps": steps})
        self._save_cutscene_store(path, payload)
        return AIOpsResult(True, f"Added cutscene '{cutscene_id}'", {"id": cutscene_id})

    def delete_cutscene(self, cutscene_id: str, *, cutscenes_path: str | None = None) -> AIOpsResult:
        path, payload = self._load_cutscene_store(cutscenes_path)
        cutscene_list = payload.get("cutscenes") or []
        for idx, entry in enumerate(cutscene_list):
            if isinstance(entry, dict) and entry.get("id") == cutscene_id:
                deleted = cutscene_list.pop(idx)
                self._save_cutscene_store(path, payload)
                return AIOpsResult(True, f"Deleted cutscene '{cutscene_id}'", {"deleted": deleted})
        return AIOpsResult(False, f"Cutscene '{cutscene_id}' not found")

    def insert_cutscene_step(
        self,
        cutscene_id: str,
        step: dict[str, Any],
        *,
        index: int | None = None,
        cutscenes_path: str | None = None,
    ) -> AIOpsResult:
        path, payload = self._load_cutscene_store(cutscenes_path)
        cutscene = self._find_cutscene(payload, cutscene_id)
        if cutscene is None:
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' not found")
        steps = cutscene.setdefault("steps", [])
        if not isinstance(steps, list):
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' steps must be a list")
        if "type" not in step:
            return AIOpsResult(False, "Step must include 'type'")
        insert_at = len(steps) if index is None else max(0, min(int(index), len(steps)))
        steps.insert(insert_at, step)
        self._save_cutscene_store(path, payload)
        return AIOpsResult(True, f"Inserted step at {insert_at}", {"index": insert_at, "step": step})

    def update_cutscene_step(
        self,
        cutscene_id: str,
        index: int,
        patch: dict[str, Any],
        *,
        cutscenes_path: str | None = None,
    ) -> AIOpsResult:
        path, payload = self._load_cutscene_store(cutscenes_path)
        cutscene = self._find_cutscene(payload, cutscene_id)
        if cutscene is None:
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' not found")
        steps = cutscene.get("steps")
        if not isinstance(steps, list):
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' steps must be a list")
        if index < 0 or index >= len(steps):
            return AIOpsResult(False, f"Step index {index} out of range")
        target = steps[index]
        if not isinstance(target, dict):
            return AIOpsResult(False, f"Step at {index} is not an object")
        target.update(patch)
        self._save_cutscene_store(path, payload)
        return AIOpsResult(True, f"Updated step {index}", {"index": index, "step": target})

    def delete_cutscene_step(
        self,
        cutscene_id: str,
        index: int,
        *,
        cutscenes_path: str | None = None,
    ) -> AIOpsResult:
        path, payload = self._load_cutscene_store(cutscenes_path)
        cutscene = self._find_cutscene(payload, cutscene_id)
        if cutscene is None:
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' not found")
        steps = cutscene.get("steps")
        if not isinstance(steps, list):
            return AIOpsResult(False, f"Cutscene '{cutscene_id}' steps must be a list")
        if index < 0 or index >= len(steps):
            return AIOpsResult(False, f"Step index {index} out of range")
        deleted = steps.pop(index)
        self._save_cutscene_store(path, payload)
        return AIOpsResult(True, f"Deleted step {index}", {"deleted": deleted, "index": index})

    def _find_cutscene(self, payload: dict[str, Any], cutscene_id: str) -> dict[str, Any] | None:
        cutscene_list = payload.get("cutscenes") or []
        for entry in cutscene_list:
            if isinstance(entry, dict) and entry.get("id") == cutscene_id:
                return entry
        return None

    def run_validation(self, scene_path: str | None = None) -> AIOpsResult:
        if scene_path is None:
            return AIOpsResult(True, "No scene provided; skipped validation")
        loader = SceneLoader()
        report = loader.validate_scene_file(scene_path)
        ok = not report.errors
        message = "ok" if ok else f"{len(report.errors)} error(s)"
        return AIOpsResult(ok, message, {"errors": report.errors, "warnings": report.warnings})

    # ------------------------------------------------------------------ job runner
    def apply_job(self, job_payload: dict[str, Any]) -> dict[str, Any]:
        operations = job_payload.get("operations")
        if not isinstance(operations, list):
            raise ValueError("job.operations must be a list")
        results: list[dict[str, Any]] = []
        overall_ok = True
        for op in operations:
            if not isinstance(op, dict) or "type" not in op:
                results.append({"ok": False, "message": "Operation missing type"})
                overall_ok = False
                continue
            op_type = str(op["type"])
            try:
                if op_type == "create_scene":
                    res = self.create_scene(op["name"], op.get("template", "empty"))
                elif op_type == "add_entity_from_prefab":
                    res = self.add_entity_from_prefab(
                        op["scene_path"],
                        op["prefab_name"],
                        op.get("x", 0),
                        op.get("y", 0),
                        prefab_path=op.get("prefab_path"),
                    )
                elif op_type == "delete_entity":
                    res = self.delete_entity(op["scene_path"], op["entity_id"])
                elif op_type == "set_behaviour_params":
                    res = self.set_behaviour_params(
                        op["scene_path"],
                        op["entity_id"],
                        op["behaviour_name"],
                        op.get("params", {}),
                    )
                elif op_type == "edit_dialogue":
                    res = self.edit_dialogue(op["scene_path"], op["entity_id"], op.get("patch", {}))
                elif op_type == "edit_quest":
                    res = self.edit_quest(op["quest_id"], op.get("patch", {}), quests_path=op.get("quests_path", "assets/data/quests.json"))
                elif op_type == "add_quest_definition":
                    res = self.add_or_update_quest_definition(
                        op["quest_id"],
                        op.get("quest", {}),
                        quests_path=op.get("quests_path", "assets/data/quests.json"),
                    )
                elif op_type == "update_quest_definition":
                    res = self.add_or_update_quest_definition(
                        op["quest_id"],
                        op.get("quest", {}),
                        quests_path=op.get("quests_path", "assets/data/quests.json"),
                    )
                elif op_type == "delete_quest_definition":
                    res = self.delete_quest_definition(op["quest_id"], quests_path=op.get("quests_path", "assets/data/quests.json"))
                elif op_type == "paint_tiles":
                    res = self.paint_tiles(op["scene_path"], op.get("ops", []))
                elif op_type == "add_light":
                    res = self.add_light(op["scene_path"], op.get("light", {}))
                elif op_type == "update_light":
                    res = self.update_light(op["scene_path"], int(op.get("index", 0)), op.get("patch", {}))
                elif op_type == "delete_light":
                    res = self.delete_light(op["scene_path"], int(op.get("index", 0)))
                elif op_type == "run_validation":
                    res = self.run_validation(op.get("scene_path"))
                elif op_type == "add_world_scene":
                    res = self.add_world_scene(
                        op["scene_key"],
                        op["path"],
                        world_path=op.get("world_path"),
                        label=op.get("label"),
                        tags=op.get("tags"),
                    )
                elif op_type == "link_world_scenes":
                    res = self.link_world_scenes(
                        op["from_key"],
                        op["to_key"],
                        world_path=op.get("world_path"),
                        via=op.get("via"),
                        bidirectional=op.get("bidirectional", True),
                    )
                elif op_type == "set_world_start":
                    res = self.set_world_start(
                        world_path=op.get("world_path"),
                        start_scene=op.get("start_scene"),
                        start_spawn=op.get("start_spawn"),
                    )
                elif op_type == "add_cutscene":
                    res = self.add_or_update_cutscene(
                        op["id"],
                        op.get("steps"),
                        cutscenes_path=op.get("cutscenes_path"),
                    )
                elif op_type == "update_cutscene":
                    res = self.add_or_update_cutscene(
                        op["id"],
                        op.get("steps"),
                        cutscenes_path=op.get("cutscenes_path"),
                    )
                elif op_type == "delete_cutscene":
                    res = self.delete_cutscene(op["id"], cutscenes_path=op.get("cutscenes_path"))
                elif op_type == "insert_cutscene_step":
                    res = self.insert_cutscene_step(
                        op["id"],
                        op.get("step", {}),
                        index=op.get("index"),
                        cutscenes_path=op.get("cutscenes_path"),
                    )
                elif op_type == "update_cutscene_step":
                    res = self.update_cutscene_step(
                        op["id"],
                        int(op.get("index", 0)),
                        op.get("patch", {}),
                        cutscenes_path=op.get("cutscenes_path"),
                    )
                elif op_type == "delete_cutscene_step":
                    res = self.delete_cutscene_step(
                        op["id"],
                        int(op.get("index", 0)),
                        cutscenes_path=op.get("cutscenes_path"),
                    )
                else:
                    res = AIOpsResult(False, f"Unknown operation type '{op_type}'")
            except Exception as exc:  # noqa: BLE001  # REASON: apply_job operation isolation for batch execution
                res = AIOpsResult(False, f"{op_type} failed: {exc}")
            results.append({"ok": res.ok, "message": res.message, "data": res.data})
            overall_ok = overall_ok and res.ok
        return {"ok": overall_ok, "results": results}


def load_job(path: str | Path) -> dict[str, Any]:
    job_path = Path(path)
    payload = _load_json(job_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Job root must be an object: {job_path}")
    return payload
