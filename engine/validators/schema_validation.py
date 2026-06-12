from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TypeGuard

from engine.paths import resolve_path


@dataclass(frozen=True, slots=True)
class ValidationError:
    code: str
    path: str
    message: str


def sort_validation_errors(errors: Iterable[ValidationError]) -> list[ValidationError]:
    return sorted(
        list(errors),
        # Deterministic ordering; prefer schema paths over legacy wrappers.
        # (Legacy records use empty path.)
        key=lambda err: (str(err.path) == "", str(err.path), str(err.code), str(err.message)),
    )


def render_validation_error_line(error: ValidationError) -> str:
    payload = {
        "code": str(error.code),
        "path": str(error.path),
        "message": str(error.message),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _string(value: object | None) -> str:
    return str(value) if value is not None else ""


def _non_empty_str(value: object | None) -> str | None:
    text = _string(value).strip()
    return text or None


def _behaves_as_path(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if text.endswith(".json"):
        return True
    return ("/" in text) or ("\\" in text)


def validate_scene(
    path: Path,
    data: Any,
    *,
    workspace_root: Path | None = None,
    strict: bool = False,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if not isinstance(data, dict):
        return [
            ValidationError(
                code="scene.root_type",
                path="",
                message=f"Scene {path}: root must be an object",
            )
        ]

    entities = data.get("entities")
    if entities is None:
        # SceneLoader treats missing entities as a warning and defaults to [].
        entities = []

    if not isinstance(entities, list):
        errors.append(
            ValidationError(
                code="scene.entities.type",
                path="entities",
                message=f"Scene {path}: 'entities' must be an array",
            )
        )
        return sort_validation_errors(errors)

    seen_entity_ids: set[str] = set()
    for index, entity in enumerate(entities):
        ent_path = f"entities[{index}]"
        if not isinstance(entity, dict):
            errors.append(
                ValidationError(
                    code="entity.type",
                    path=ent_path,
                    message=f"Scene {path}: {ent_path} must be an object",
                )
            )
            continue

        # Strict-only: stable per-entity IDs.
        if strict:
            entity_id = _non_empty_str(entity.get("id"))
            if entity_id is None:
                errors.append(
                    ValidationError(
                        code="entity.id.required",
                        path=f"{ent_path}.id",
                        message=f"Scene {path}: {ent_path}.id must be a non-empty string (strict)",
                    )
                )
            else:
                if entity_id in seen_entity_ids:
                    errors.append(
                        ValidationError(
                            code="entity.id.duplicate",
                            path=f"{ent_path}.id",
                            message=f"Scene {path}: duplicate entity id '{entity_id}' (strict)",
                        )
                    )
                else:
                    seen_entity_ids.add(entity_id)

        for axis in ("x", "y"):
            value = entity.get(axis)
            if not _is_number(value):
                errors.append(
                    ValidationError(
                        code="entity.position.required",
                        path=f"{ent_path}.{axis}",
                        message=f"Scene {path}: {ent_path}.{axis} must be a number",
                    )
                )

        behaviour_config = entity.get("behaviour_config")
        if behaviour_config is not None and not isinstance(behaviour_config, dict):
            errors.append(
                ValidationError(
                    code="entity.behaviour_config.type",
                    path=f"{ent_path}.behaviour_config",
                    message=f"Scene {path}: {ent_path}.behaviour_config must be an object",
                )
            )
            behaviour_config = None

        behaviours = entity.get("behaviours")
        if behaviours is not None and not isinstance(behaviours, list):
            errors.append(
                ValidationError(
                    code="entity.behaviours.type",
                    path=f"{ent_path}.behaviours",
                    message=f"Scene {path}: {ent_path}.behaviours must be an array",
                )
            )
            behaviours = None

        behaviours_list = behaviours if isinstance(behaviours, list) else []

        # TriggerZone schema (radius-based).
        if "TriggerZone" in behaviours_list:
            tz_cfg = None
            if isinstance(behaviour_config, dict):
                tz_cfg = behaviour_config.get("TriggerZone")
            if not isinstance(tz_cfg, dict):
                errors.append(
                    ValidationError(
                        code="trigger_zone.config.required",
                        path=f"{ent_path}.behaviour_config.TriggerZone",
                        message=f"Scene {path}: TriggerZone requires behaviour_config.TriggerZone object",
                    )
                )
            else:
                if strict:
                    zone_id = _non_empty_str(tz_cfg.get("zone_id"))
                    if zone_id is None:
                        errors.append(
                            ValidationError(
                                code="trigger_zone.zone_id.required",
                                path=f"{ent_path}.behaviour_config.TriggerZone.zone_id",
                                message=f"Scene {path}: TriggerZone.zone_id must be a non-empty string (strict)",
                            )
                        )
                radius = tz_cfg.get("trigger_radius")
                if not _is_number(radius) or float(radius) <= 0.0:
                    errors.append(
                        ValidationError(
                            code="trigger_zone.trigger_radius.required",
                            path=f"{ent_path}.behaviour_config.TriggerZone.trigger_radius",
                            message=f"Scene {path}: TriggerZone.trigger_radius must be a positive number",
                        )
                    )
                target = _non_empty_str(tz_cfg.get("trigger_target"))
                if target is None:
                    errors.append(
                        ValidationError(
                            code="trigger_zone.trigger_target.required",
                            path=f"{ent_path}.behaviour_config.TriggerZone.trigger_target",
                            message=f"Scene {path}: TriggerZone.trigger_target must be a non-empty string",
                        )
                    )

        # SceneTransition minimal schema.
        st_cfg = None
        if isinstance(behaviour_config, dict):
            st_cfg = behaviour_config.get("SceneTransition")
        if isinstance(st_cfg, dict):
            target_scene = _non_empty_str(st_cfg.get("target_scene"))
            if target_scene is None:
                errors.append(
                    ValidationError(
                        code="scene_transition.target_scene.required",
                        path=f"{ent_path}.behaviour_config.SceneTransition.target_scene",
                        message=f"Scene {path}: SceneTransition.target_scene must be a non-empty string",
                    )
                )
            elif strict and _behaves_as_path(target_scene):
                # Strict-only: for path-like targets, the file must exist.
                # (World-level validation handles world-id targets.)
                try:
                    resolved = resolve_path(target_scene)
                except Exception:
                    resolved = None
                if resolved is None or not resolved.exists():
                    errors.append(
                        ValidationError(
                            code="scene_transition.target_scene.missing",
                            path=f"{ent_path}.behaviour_config.SceneTransition.target_scene",
                            message=f"Scene {path}: SceneTransition target not found: {target_scene}",
                        )
                    )
    return sort_validation_errors(errors)


def _scan_scene_transition_targets(scene_data: Any) -> list[tuple[str, str]]:
    """Return list of (json_path, target_scene) pairs."""
    targets: list[tuple[str, str]] = []

    if not isinstance(scene_data, dict):
        return targets

    entities = scene_data.get("entities")
    if not isinstance(entities, list):
        return targets

    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        bcfg = entity.get("behaviour_config")
        if not isinstance(bcfg, dict):
            continue
        st = bcfg.get("SceneTransition")
        if not isinstance(st, dict):
            continue
        raw_target = st.get("target_scene")
        target = _non_empty_str(raw_target)
        if target is None:
            continue
        path = f"entities[{index}].behaviour_config.SceneTransition.target_scene"
        targets.append((path, target))

    return targets


def validate_world(
    path: Path,
    data: Any,
    *,
    workspace_root: Path | None = None,
    validate_scene_files: bool = True,
    strict: bool = False,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if not isinstance(data, dict):
        return [
            ValidationError(
                code="world.root_type",
                path="",
                message=f"World {path}: root must be an object",
            )
        ]

    scenes = data.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        errors.append(
            ValidationError(
                code="world.scenes.required",
                path="scenes",
                message=f"World {path}: missing required object 'scenes'",
            )
        )
        return sort_validation_errors(errors)

    start_scene = _non_empty_str(data.get("start_scene"))
    if start_scene is None:
        if strict:
            errors.append(
                ValidationError(
                    code="world.start_scene.required",
                    path="start_scene",
                    message=f"World {path}: missing required string 'start_scene'",
                )
            )
    elif start_scene not in scenes:
        errors.append(
            ValidationError(
                code="world.start_scene.unknown",
                path="start_scene",
                message=f"World {path}: start_scene '{start_scene}' not found in scenes",
            )
        )

    scene_ids = sorted(str(k) for k in scenes.keys())

    # Validate scene entries and referenced files.
    scene_paths: dict[str, Path] = {}
    for scene_id in scene_ids:
        entry = scenes.get(scene_id)
        base_path = f"scenes.{scene_id}"
        if not isinstance(entry, dict):
            errors.append(
                ValidationError(
                    code="world.scene_entry.type",
                    path=base_path,
                    message=f"World {path}: scenes['{scene_id}'] must be an object",
                )
            )
            continue
        raw_scene_path = entry.get("path")
        scene_path_str = _non_empty_str(raw_scene_path)
        if scene_path_str is None:
            errors.append(
                ValidationError(
                    code="world.scene_entry.path.required",
                    path=f"{base_path}.path",
                    message=f"World {path}: scene '{scene_id}' missing required string path",
                )
            )
            continue

        try:
            resolved = resolve_path(scene_path_str)
        except Exception:
            resolved = None

        if resolved is None or not resolved.exists():
            errors.append(
                ValidationError(
                    code="world.scene_file.missing",
                    path=f"{base_path}.path",
                    message=f"World {path}: scene '{scene_id}' path not found: {scene_path_str}",
                )
            )
            continue
        scene_paths[scene_id] = resolved

    # Validate links refer to known scene IDs.
    links = data.get("links")
    if links is not None:
        if not isinstance(links, list):
            errors.append(
                ValidationError(
                    code="world.links.type",
                    path="links",
                    message=f"World {path}: 'links' must be an array when present",
                )
            )
        else:
            for index, link in enumerate(links):
                lp = f"links[{index}]"
                if not isinstance(link, dict):
                    errors.append(
                        ValidationError(
                            code="world.link.type",
                            path=lp,
                            message=f"World {path}: {lp} must be an object",
                        )
                    )
                    continue
                frm = _non_empty_str(link.get("from"))
                to = _non_empty_str(link.get("to"))
                if frm is None:
                    errors.append(
                        ValidationError(
                            code="world.link.from.required",
                            path=f"{lp}.from",
                            message=f"World {path}: {lp}.from must be a non-empty string",
                        )
                    )
                elif frm not in scenes:
                    errors.append(
                        ValidationError(
                            code="world.link.from.unknown",
                            path=f"{lp}.from",
                            message=f"World {path}: {lp}.from '{frm}' not found in scenes",
                        )
                    )
                if to is None:
                    errors.append(
                        ValidationError(
                            code="world.link.to.required",
                            path=f"{lp}.to",
                            message=f"World {path}: {lp}.to must be a non-empty string",
                        )
                    )
                elif to not in scenes:
                    errors.append(
                        ValidationError(
                            code="world.link.to.unknown",
                            path=f"{lp}.to",
                            message=f"World {path}: {lp}.to '{to}' not found in scenes",
                        )
                    )

    if validate_scene_files:
        # Validate each referenced scene's basic schema.
        for scene_id in scene_ids:
            scene_file = scene_paths.get(scene_id)
            if scene_file is None:
                continue
            try:
                scene_data = json.loads(scene_file.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(
                    ValidationError(
                        code="scene.json.invalid",
                        path=f"scenes.{scene_id}.path",
                        message=f"World {path}: failed to parse scene '{scene_id}' ({scene_file.as_posix()}): {exc}",
                    )
                )
                continue

            errors.extend(
                validate_scene(
                    scene_file,
                    scene_data,
                    workspace_root=workspace_root,
                    strict=strict,
                )
            )

            # Strict-only: validate SceneTransition targets resolve to an existing file.
            if strict:
                for jpath, target in _scan_scene_transition_targets(scene_data):
                    if target in scenes:
                        target_file = scene_paths.get(target)
                        if target_file is not None and target_file.exists():
                            continue
                        errors.append(
                            ValidationError(
                                code="scene_transition.target_scene.missing",
                                path=jpath,
                                message=(
                                    f"Scene {scene_file}: SceneTransition target '{target}' refers to missing scene file"
                                ),
                            )
                        )
                        continue

                    try:
                        resolved = resolve_path(target)
                    except Exception:
                        resolved = None
                    if resolved is not None and resolved.exists():
                        continue
                    errors.append(
                        ValidationError(
                            code="scene_transition.target_scene.missing",
                            path=jpath,
                            message=f"Scene {scene_file}: SceneTransition target not found: {target}",
                        )
                    )

    return sort_validation_errors(errors)


# ---------------------------------------------------------------------------
# Prefab validation
# ---------------------------------------------------------------------------

# Known top-level prefab fields
KNOWN_PREFAB_FIELDS: frozenset[str] = frozenset({
    "id",
    "base",
    "display_name",
    "category",
    "tags",
    "metadata",
    "entity",
    "variants",
    # Extension namespace: any field starting with "x_" is allowed
})

# Known entity fields within a prefab (subset relevant for prefab validation)
KNOWN_PREFAB_ENTITY_FIELDS: frozenset[str] = frozenset({
    "sprite",
    "sprite_sheet",
    "scale",
    "rotation",
    "layer",
    "behaviours",
    "behaviour_config",
    "solid",
    "collision_poly",
    "occluder_poly",
    "tags",
    "name",
    "animations",
    "animation_state",
    "animation_frame_rate",
    "depth_z",
    "render_layer",
    "shadow_offset_y",
    "shadow_scale",
    "tint",
    "alpha",
    # Extension namespace: any field starting with "x_" is allowed
})


def validate_prefab(
    path: Path,
    data: Any,
    *,
    index: int | None = None,
    strict: bool = False,
) -> list[ValidationError]:
    """Validate a single prefab definition.
    
    Args:
        path: Path to the prefab file (for error messages).
        data: The prefab dict to validate.
        index: Optional index within a prefab array (for error paths).
        strict: If True, enforce stricter validation rules.
    
    Returns:
        List of ValidationError objects (empty if valid).
    """
    errors: list[ValidationError] = []
    base_path = f"[{index}]" if index is not None else ""

    if not isinstance(data, dict):
        return [
            ValidationError(
                code="prefab.type",
                path=base_path,
                message=f"Prefab {path}{base_path}: must be an object",
            )
        ]

    # Required: id
    prefab_id = data.get("id")
    if not isinstance(prefab_id, str) or not prefab_id.strip():
        errors.append(
            ValidationError(
                code="prefab.id.required",
                path=f"{base_path}.id" if base_path else "id",
                message=f"Prefab {path}{base_path}: 'id' must be a non-empty string",
            )
        )
        prefab_id = "<unknown>"
    else:
        prefab_id = prefab_id.strip()
        # Validate id format (lowercase alphanumeric + underscores)
        import re
        if not re.match(r"^[a-z0-9_]+$", prefab_id):
            errors.append(
                ValidationError(
                    code="prefab.id.format",
                    path=f"{base_path}.id" if base_path else "id",
                    message=f"Prefab {path}{base_path}: 'id' must match pattern ^[a-z0-9_]+$ (got '{prefab_id}')",
                )
            )

    # Required: entity
    entity = data.get("entity")
    if entity is None:
        errors.append(
            ValidationError(
                code="prefab.entity.required",
                path=f"{base_path}.entity" if base_path else "entity",
                message=f"Prefab {path} '{prefab_id}': missing required 'entity' block",
            )
        )
    elif not isinstance(entity, dict):
        errors.append(
            ValidationError(
                code="prefab.entity.type",
                path=f"{base_path}.entity" if base_path else "entity",
                message=f"Prefab {path} '{prefab_id}': 'entity' must be an object",
            )
        )
        entity = None

    # Validate entity fields
    if isinstance(entity, dict):
        ent_base = f"{base_path}.entity" if base_path else "entity"

        # Check for unknown fields (strict mode)
        if strict:
            for key in entity.keys():
                if key not in KNOWN_PREFAB_ENTITY_FIELDS and not key.startswith("x_"):
                    errors.append(
                        ValidationError(
                            code="prefab.entity.unknown_field",
                            path=f"{ent_base}.{key}",
                            message=f"Prefab {path} '{prefab_id}': unknown entity field '{key}' "
                                    f"(use 'x_' prefix for extensions)",
                        )
                    )

        # Validate behaviours
        behaviours = entity.get("behaviours")
        if behaviours is not None:
            if not isinstance(behaviours, list):
                errors.append(
                    ValidationError(
                        code="prefab.entity.behaviours.type",
                        path=f"{ent_base}.behaviours",
                        message=f"Prefab {path} '{prefab_id}': behaviours must be an array",
                    )
                )
            else:
                for i, b in enumerate(behaviours):
                    if not isinstance(b, (str, dict)):
                        errors.append(
                            ValidationError(
                                code="prefab.entity.behaviours.entry_type",
                                path=f"{ent_base}.behaviours[{i}]",
                                message=f"Prefab {path} '{prefab_id}': behaviours[{i}] must be string or object",
                            )
                        )

        # Validate behaviour_config
        bcfg = entity.get("behaviour_config")
        if bcfg is not None and not isinstance(bcfg, dict):
            errors.append(
                ValidationError(
                    code="prefab.entity.behaviour_config.type",
                    path=f"{ent_base}.behaviour_config",
                    message=f"Prefab {path} '{prefab_id}': behaviour_config must be an object",
                )
            )

        # Validate collision_poly and occluder_poly
        for poly_field in ("collision_poly", "occluder_poly"):
            poly = entity.get(poly_field)
            if poly is not None:
                if not isinstance(poly, list):
                    errors.append(
                        ValidationError(
                            code=f"prefab.entity.{poly_field}.type",
                            path=f"{ent_base}.{poly_field}",
                            message=f"Prefab {path} '{prefab_id}': {poly_field} must be an array of points",
                        )
                    )
                elif len(poly) < 3:
                    errors.append(
                        ValidationError(
                            code=f"prefab.entity.{poly_field}.min_points",
                            path=f"{ent_base}.{poly_field}",
                            message=f"Prefab {path} '{prefab_id}': {poly_field} needs at least 3 points",
                        )
                    )

        # Validate tags
        tags = entity.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                errors.append(
                    ValidationError(
                        code="prefab.entity.tags.type",
                        path=f"{ent_base}.tags",
                        message=f"Prefab {path} '{prefab_id}': tags must be an array",
                    )
                )
            else:
                for i, t in enumerate(tags):
                    if not isinstance(t, str):
                        errors.append(
                            ValidationError(
                                code="prefab.entity.tags.entry_type",
                                path=f"{ent_base}.tags[{i}]",
                                message=f"Prefab {path} '{prefab_id}': tags[{i}] must be a string",
                            )
                        )

    # Optional: base (inheritance)
    base = data.get("base")
    if base is not None and not isinstance(base, str):
        errors.append(
            ValidationError(
                code="prefab.base.type",
                path=f"{base_path}.base" if base_path else "base",
                message=f"Prefab {path} '{prefab_id}': 'base' must be a string",
            )
        )

    # Optional: tags (top-level)
    top_tags = data.get("tags")
    if top_tags is not None:
        if not isinstance(top_tags, list):
            errors.append(
                ValidationError(
                    code="prefab.tags.type",
                    path=f"{base_path}.tags" if base_path else "tags",
                    message=f"Prefab {path} '{prefab_id}': 'tags' must be an array",
                )
            )
        else:
            for i, t in enumerate(top_tags):
                if not isinstance(t, str):
                    errors.append(
                        ValidationError(
                            code="prefab.tags.entry_type",
                            path=f"{base_path}.tags[{i}]" if base_path else f"tags[{i}]",
                            message=f"Prefab {path} '{prefab_id}': tags[{i}] must be a string",
                        )
                    )

    # Optional: metadata
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append(
            ValidationError(
                code="prefab.metadata.type",
                path=f"{base_path}.metadata" if base_path else "metadata",
                message=f"Prefab {path} '{prefab_id}': 'metadata' must be an object",
            )
        )

    # Check for unknown top-level fields (strict mode)
    if strict:
        for key in data.keys():
            if key not in KNOWN_PREFAB_FIELDS and not key.startswith("x_"):
                errors.append(
                    ValidationError(
                        code="prefab.unknown_field",
                        path=f"{base_path}.{key}" if base_path else key,
                        message=f"Prefab {path} '{prefab_id}': unknown field '{key}' "
                                f"(use 'x_' prefix for extensions)",
                    )
                )

    return sort_validation_errors(errors)


def validate_prefab_file(
    path: Path,
    data: Any,
    *,
    strict: bool = False,
) -> list[ValidationError]:
    """Validate a prefab file (array of prefab definitions).
    
    Args:
        path: Path to the prefab file.
        data: The parsed JSON data (should be a list).
        strict: If True, enforce stricter validation rules.
    
    Returns:
        List of ValidationError objects (empty if valid).
    """
    errors: list[ValidationError] = []

    if not isinstance(data, list):
        return [
            ValidationError(
                code="prefab_file.type",
                path="",
                message=f"Prefab file {path}: must be an array of prefab definitions",
            )
        ]

    seen_ids: set[str] = set()
    for index, prefab in enumerate(data):
        # Validate individual prefab
        prefab_errors = validate_prefab(path, prefab, index=index, strict=strict)
        errors.extend(prefab_errors)

        # Check for duplicate IDs
        if isinstance(prefab, dict):
            pid = prefab.get("id")
            if isinstance(pid, str) and pid.strip():
                pid = pid.strip()
                if pid in seen_ids:
                    errors.append(
                        ValidationError(
                            code="prefab_file.duplicate_id",
                            path=f"[{index}].id",
                            message=f"Prefab file {path}: duplicate prefab id '{pid}'",
                        )
                    )
                else:
                    seen_ids.add(pid)

    return sort_validation_errors(errors)

