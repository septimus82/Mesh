"""Utility helpers for reading JSON scene definitions."""

from __future__ import annotations

import copy
import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from engine.swallowed_exceptions import _log_swallow

from .behaviours import load_builtin_behaviours
from .behaviours.registry import get_behaviour_info, get_behaviour_param_defs
from .diagnostics import error as diag_error
from .diagnostics import warn as diag_warn
from .migrations import migrate_payload
from .paths import resolve_path
from .prefabs import get_prefab_manager
from .schema_validation import validate

DEFAULT_LAYERS = [
    {"name": "background"},
    {"name": "entities"},
    {"name": "foreground"},
]

DEFAULT_SETTINGS = {
    "background_color": "dark_blue_gray",
    "music": None,
    "music_volume": 1.0,
}

DEFAULT_ENTITY: dict[str, Any] = {
    "sprite": None,
    "sprite_sheet": {},
    "scale": 1.0,
    "rotation": 0,
    "layer": "entities",
    "behaviours": [],
    "behaviour_config": {},
    "solid": False,
    "patrol_points": [],
    "patrol_speed": 80.0,
    "follow_target": None,
    "follow_speed": 100.0,
    "animations": {},
    "animation_state": "idle",
    "animation_frame_rate": 8.0,
    "animation_blend": 0.0,
    "animation_root_motion": False,
    "dialogue": {},
    "dialogue_lines": [],
    "trigger_radius": None,
    "trigger_target": None,
    "on_trigger": None,
}

KNOWN_EXTRA_FIELDS = {
    "name",
    "mesh_name",
    "tag",
    "behaviours",
    "solid",
    "x",
    "y",
    "spawn_id",
    "tags",
    "type",
    "prefab_id",
    "prefab_overrides",
    "variant_id",
    "id",
    "require_flags",
    "forbid_flags",
    "collision_poly",
    "occluder_poly",
}
KNOWN_ENTITY_FIELDS: Set[str] = set(DEFAULT_ENTITY.keys()) | KNOWN_EXTRA_FIELDS

# If an entity uses `prefab_id`, these fields must come from the prefab (and variant patches),
# not from per-scene overrides.
PREFAB_OWNED_FIELDS: Set[str] = {"sprite", "name"}


@dataclass(slots=True)
class ValidationReport:
    """Aggregates validation errors and warnings."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    behaviour_details: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(str(message))

    def add_warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def add_behaviour_detail(self, entity_label: str, behaviour: str, message: str) -> None:
        entity_key = str(entity_label)
        behaviour_key = str(behaviour)
        behaviours = self.behaviour_details.setdefault(entity_key, {})
        behaviours.setdefault(behaviour_key, []).append(str(message))

    def extend(self, other: "ValidationReport") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        for entity, behaviours in other.behaviour_details.items():
            bucket = self.behaviour_details.setdefault(entity, {})
            for behaviour, messages in behaviours.items():
                bucket.setdefault(behaviour, []).extend(messages)

    @property
    def ok(self) -> bool:
        return not self.errors


class SceneLoader:
    """Loads JSON scene files and validates minimal entity data."""

    def apply_scene_defaults(self, raw_scene: Dict[str, Any]) -> Dict[str, Any]:
        """Public wrapper so tooling can reuse the defaulting logic."""

        return self._apply_scene_defaults(raw_scene)

    def apply_entity_defaults(self, raw_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Public wrapper for entity defaulting."""

        return self._apply_entity_defaults(raw_entity)

    def load_scene(self, scene_path: str) -> Dict[str, Any]:
        """Return the full scene dictionary from a JSON file."""
        full_path = resolve_path(scene_path)
        if not full_path.exists():
            diag_warn(
                "scene_loader.scene_missing",
                f"Missing scene file '{scene_path}'",
                "engine.scene_loader",
                location=str(scene_path),
            )
            raise FileNotFoundError(f"Scene file not found: {scene_path}")

        raw_scene: Dict[str, Any] = json.loads(full_path.read_text(encoding="utf-8"))
        migrated_scene = migrate_payload("scene", raw_scene)
        validate(migrated_scene, "scene.schema.json", full_path)
        scene = self._apply_scene_defaults(migrated_scene, migrated=True)

        scene_report = self.validate_scene(scene, validate_entities=False)
        self._log_validation_report(scene_report, context=f"Scene '{scene.get('name', '<unnamed>')}'")
        if not scene_report.ok:
            print(
                f"[Mesh][SceneLoader] ERROR: Scene '{scene.get('name', '<unnamed>')}' failed validation; "
                "loading empty fallback",
            )
            diag_error(
                "scene_loader.scene_validation_failed",
                f"Scene '{scene.get('name', '<unnamed>')}' failed validation; loading empty fallback",
                "engine.scene_loader",
                location=str(scene_path),
            )
            return self._default_scene()

        # Normalize entity list after validation messaging.
        normalized_entities = []
        for index, entity in enumerate(scene.get("entities", [])):
            entity_report = self.validate_entity(entity, index=index)
            self._log_validation_report(
                entity_report,
                context=f"Entity[{index}] {entity.get('name', '<unnamed>')}",
            )
            if not entity_report.ok:
                continue
            normalized = self._apply_entity_defaults(entity)
            normalized_entities.append(normalized)

        scene["entities"] = normalized_entities

        normalized_tilemap = self._normalize_tilemap_section(scene.get("tilemap"), base_path=full_path.parent)
        if normalized_tilemap is not None:
            scene["tilemap"] = normalized_tilemap
        else:
            scene.pop("tilemap", None)

        print(
            "[Mesh][SceneLoader] Loaded scene "
            f"'{scene.get('name', '<unnamed>')}' with {len(normalized_entities)} entities",
        )
        return scene

    def validate_scene_file(self, scene_path: str, strict: bool = False) -> ValidationReport:
        """Validate a scene JSON file without loading it into the engine."""

        load_builtin_behaviours()
        report = ValidationReport()
        full_path = resolve_path(scene_path)
        if not full_path.exists():
            report.add_error(f"Scene file '{scene_path}' does not exist")
            return report

        try:
            with full_path.open("r", encoding="utf-8") as handle:
                raw_scene: Dict[str, Any] = json.load(handle)
        except json.JSONDecodeError as exc:
            report.add_error(f"JSON parse failure in '{scene_path}': {exc}")
            return report
        except OSError as exc:
            report.add_error(f"Could not read '{scene_path}': {exc}")
            return report

        scene = self.apply_scene_defaults(raw_scene)
        return self.validate_scene(scene, strict=strict)

    def validate_scene(
        self,
        scene: Dict[str, Any],
        *,
        validate_entities: bool = True,
        strict: bool = False,
    ) -> ValidationReport:
        """Validate the top-level structure (and optionally each entity)."""

        report = ValidationReport()
        if not isinstance(scene, dict):
            report.add_error("Scene root must be a JSON object (dictionary)")
            return report

        allowed_keys = {
            "name",
            "version",
            "schema_version",
            "description",
            "settings",
            "state",
            "layers",
            "collision_rules",
            "entities",
            "tilemap",
            "background_layers",
            "foreground_layers",
            "lights",
            "occluders",
        }
        for key in scene.keys():
            if key not in allowed_keys:
                report.add_warning(f"Unknown top-level key '{key}' will be ignored")

        settings = scene.get("settings")
        if settings is not None and not isinstance(settings, dict):
            report.add_error("Scene 'settings' must be an object if provided")
        elif isinstance(settings, dict):
            self._validate_settings(settings, report)

        state = scene.get("state")
        if state is not None and not isinstance(state, dict):
            report.add_error("Scene 'state' must be an object if provided")

        layers = scene.get("layers")
        if layers is not None and not isinstance(layers, list):
            report.add_error("Scene 'layers' must be an array")
        elif isinstance(layers, list):
            self._validate_layers(layers, report)

        collision_rules = scene.get("collision_rules")
        if collision_rules is not None and not isinstance(collision_rules, dict):
            report.add_error("Scene 'collision_rules' must be an object")
        elif isinstance(collision_rules, dict):
            self._validate_collision_rules(collision_rules, report)

        tilemap_section = scene.get("tilemap")
        self._validate_tilemap_section(tilemap_section, report)

        backgrounds_section = scene.get("background_layers")
        self._validate_background_layers_section(backgrounds_section, report)

        lights = scene.get("lights")
        if lights is not None and not isinstance(lights, list):
            report.add_error("Scene 'lights' must be an array if provided")

        occluders = scene.get("occluders")
        if occluders is not None and not isinstance(occluders, list):
            report.add_error("Scene 'occluders' must be an array if provided")

        entities = scene.get("entities")
        if entities is None:
            report.add_warning("Scene missing 'entities'; defaulting to an empty list")
            entities = []
        if not isinstance(entities, list):
            report.add_error("Scene 'entities' must be an array of entity objects")
        elif validate_entities:
            for index, entity in enumerate(entities):
                entity_report = self.validate_entity(entity, index=index, strict=strict)
                report.extend(entity_report)

        return report

    def _validate_background_layers_section(self, background_layers: Any, report: ValidationReport) -> None:
        if background_layers is None:
            return
        if not isinstance(background_layers, list):
            report.add_error("Scene 'background_layers' must be an array when provided")
            return

        seen: set[str] = set()
        for idx, entry in enumerate(background_layers):
            if not isinstance(entry, dict):
                report.add_error(f"background_layers[{idx}] must be an object")
                continue
            layer_id = entry.get("id")
            if not isinstance(layer_id, str) or not layer_id.strip():
                report.add_error(f"background_layers[{idx}].id must be a non-empty string")
                continue
            layer_id = layer_id.strip()
            if layer_id in seen:
                report.add_error(f"background_layers has duplicate id '{layer_id}'")
            seen.add(layer_id)

            path_value = entry.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                report.add_error(f"background_layers[{idx}].path must be a non-empty string")

            z_value = entry.get("z")
            if not isinstance(z_value, int):
                report.add_error(f"background_layers[{idx}].z must be an int")

            parallax_value = entry.get("parallax")
            if parallax_value is not None and not self._is_number(parallax_value):
                report.add_error(f"background_layers[{idx}].parallax must be a number if provided")
            elif parallax_value is not None:
                parallax = float(parallax_value)
                if not (0.0 <= parallax <= 2.0):
                    report.add_error("background_layers[].parallax must be within [0, 2] when provided")

            repeat_x_value = entry.get("repeat_x")
            if repeat_x_value is not None and not isinstance(repeat_x_value, bool):
                report.add_error(f"background_layers[{idx}].repeat_x must be a boolean if provided")

            repeat_y_value = entry.get("repeat_y")
            if repeat_y_value is not None and not isinstance(repeat_y_value, bool):
                report.add_error(f"background_layers[{idx}].repeat_y must be a boolean if provided")

            # Backward compatibility: accept legacy `repeat` boolean (treated as repeat_x).
            repeat_value = entry.get("repeat")
            if repeat_value is not None and not isinstance(repeat_value, bool):
                report.add_error(f"background_layers[{idx}].repeat must be a boolean if provided")

    def validate_entity(self, entity: Dict[str, Any], index: Optional[int] = None, strict: bool = False) -> ValidationReport:
        """Ensure required coordinate fields exist before sprite creation."""

        report = ValidationReport()
        if not isinstance(entity, dict):
            report.add_error(
                f"Entity[{index if index is not None else '?'}]: must be an object, got {self._type_name(entity)}",
            )
            return report

        label = self._format_entity_label(index, entity)

        prefab_id = entity.get("prefab_id")
        if prefab_id:
            for field_name in PREFAB_OWNED_FIELDS:
                if field_name in entity and entity.get(field_name) is not None:
                    entity_name = entity.get("mesh_name") or entity.get("name") or entity.get("id") or label
                    if field_name == "name":
                        message = (
                            f"Entity '{entity_name}' uses prefab_id '{prefab_id}' and must not set 'name'. "
                            "Use mesh_name for instance naming or variant_id for display changes."
                        )
                    else:
                        message = (
                            f"Entity '{entity_name}' uses prefab_id '{prefab_id}' and must not set '{field_name}'. "
                            f"Move {field_name} to prefab or variant patch."
                        )
                    if strict:
                        report.add_error(message)
                    else:
                        report.add_warning(message)

        # Sprite is optional if it's a logic entity or marker
        self._require_string(entity, "sprite", report, label, required=False)
        self._require_number(entity, "x", report, label, required=True)
        self._require_number(entity, "y", report, label, required=True)
        self._require_string(entity, "layer", report, label, required=False)
        self._require_number(entity, "scale", report, label, required=False)
        self._require_number(entity, "rotation", report, label, required=False)
        self._require_number(entity, "patrol_speed", report, label, required=False)
        self._require_number(entity, "follow_speed", report, label, required=False)
        self._require_number(entity, "animation_frame_rate", report, label, required=False)
        self._require_number(entity, "animation_blend", report, label, required=False)
        self._validate_root_motion(entity.get("animation_root_motion"), report, label)
        self._require_number(entity, "trigger_radius", report, label, required=False)
        self._require_string(entity, "trigger_target", report, label, required=False)
        self._require_string(entity, "on_trigger", report, label, required=False)

        for flag_field in ("require_flags", "forbid_flags"):
            value = entity.get(flag_field)
            if value is None:
                continue
            if not isinstance(value, list):
                report.add_error(f"{label}: field '{flag_field}' must be an array of strings when present")
                continue
            for entry in value:
                if not isinstance(entry, str) or not entry.strip():
                    report.add_error(f"{label}: field '{flag_field}' must contain non-empty strings")
                    break

        for poly_field in ("collision_poly", "occluder_poly"):
            value = entity.get(poly_field)
            if value is None:
                continue
            if not isinstance(value, list):
                report.add_error(f"{label}: field '{poly_field}' must be an array of points")
                continue
            for point in value:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    report.add_error(f"{label}: field '{poly_field}' must contain [x,y] point pairs")
                    break
                if not isinstance(point[0], (int, float)) or not isinstance(point[1], (int, float)):
                    report.add_error(f"{label}: field '{poly_field}' must contain numeric [x,y] point pairs")
                    break

        sprite_sheet = entity.get("sprite_sheet")
        if sprite_sheet is not None:
            if not isinstance(sprite_sheet, dict):
                report.add_error(f"{label}: field 'sprite_sheet' must be an object")
            else:
                if sprite_sheet:
                    self._require_positive_int(sprite_sheet, "frame_width", report, label)
                    self._require_positive_int(sprite_sheet, "frame_height", report, label)
                    self._require_int(sprite_sheet, "margin", report, label, allow_zero=True, required=False)
                    self._require_int(sprite_sheet, "spacing", report, label, allow_zero=True, required=False)
                    self._require_positive_int(sprite_sheet, "columns", report, label, required=False)
                    self._require_positive_int(sprite_sheet, "rows", report, label, required=False)

        tag_value = entity.get("tag")
        if tag_value is not None and not isinstance(tag_value, str):
            report.add_error(f"{label}: field 'tag' must be a string when present")

        solid_value = entity.get("solid")
        if solid_value is not None and not isinstance(solid_value, bool):
            report.add_error(f"{label}: field 'solid' must be a boolean when present")

        patrol_points = entity.get("patrol_points")
        if patrol_points is not None and not isinstance(patrol_points, list):
            report.add_error(f"{label}: field 'patrol_points' must be an array of coordinates")

        animations = entity.get("animations")
        if animations is not None and not isinstance(animations, dict):
            report.add_error(f"{label}: field 'animations' must be an object")

        behaviour_fields = self._validate_behaviours(entity.get("behaviours"), label, report)
        self._validate_behaviour_config_section(entity.get("behaviour_config"), label, report)

        allowed_fields = set(KNOWN_ENTITY_FIELDS)
        allowed_fields.update(behaviour_fields)
        for key in entity.keys():
            if key not in allowed_fields:
                msg = f"{label}: unknown field '{key}' will be copied verbatim"
                if strict:
                    report.add_error(msg)
                else:
                    report.add_warning(msg)

        return report

    def _validate_root_motion(self, value: Any, report: ValidationReport, label: str) -> None:
        if value is None:
            return
        if isinstance(value, (bool, int, float)):
            return
        if isinstance(value, dict):
            labels = value.get("labels")
            if labels is not None and not isinstance(labels, (list, tuple, set, str)):
                report.add_error(f"{label}: animation_root_motion.labels must be string or array when provided")
            space = value.get("space")
            if space is not None and not isinstance(space, str):
                report.add_error(f"{label}: animation_root_motion.space must be a string when provided")
            collision = value.get("collision")
            if collision is not None and not isinstance(collision, bool):
                report.add_error(f"{label}: animation_root_motion.collision must be boolean when provided")
            scale = value.get("scale")
            if scale is not None and not self._is_number(scale):
                report.add_error(f"{label}: animation_root_motion.scale must be numeric when provided")
            enabled = value.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                report.add_error(f"{label}: animation_root_motion.enabled must be boolean when provided")
            return
        report.add_error(
            f"{label}: field 'animation_root_motion' must be a boolean, number, or object when present",
        )

    def _apply_scene_defaults(self, raw_scene: Dict[str, Any], *, migrated: bool = False) -> Dict[str, Any]:
        if not migrated:
            raw_scene = migrate_payload("scene", raw_scene)

        scene = copy.deepcopy(raw_scene)
        scene.setdefault("name", "<unnamed>")
        scene.setdefault("version", 1)
        scene.setdefault("schema_version", 1)
        settings = scene.setdefault("settings", {})
        for key, value in DEFAULT_SETTINGS.items():
            settings.setdefault(key, value)
        if "layers" not in scene:
            scene["layers"] = copy.deepcopy(DEFAULT_LAYERS)
        if "entities" not in scene:
            scene["entities"] = []
        return scene

    def _apply_entity_defaults(self, raw_entity: Dict[str, Any]) -> Dict[str, Any]:
        entity = dict(raw_entity)
        if entity.get("prefab_id"):
            try:
                entity = get_prefab_manager().resolve(entity)
            except Exception:  # noqa: BLE001  # REASON: prefab resolution failures should fall back to the raw authored entity payload
                _log_swallow("SCEN-001", "engine/scene_loader.py pass-only blanket swallow")
                pass
        for key, value in DEFAULT_ENTITY.items():
            entity.setdefault(key, copy.deepcopy(value) if isinstance(value, list) else value)
        # Ensure behaviours is always a list even if someone passed None.
        if not isinstance(entity.get("behaviours"), list):
            entity["behaviours"] = []
        else:
            normalized_behaviours: list[dict[str, Any]] = []
            for entry in entity["behaviours"]:
                normalized = self._normalize_behaviour_entry(entry)
                if normalized is not None:
                    normalized_behaviours.append(normalized)
            entity["behaviours"] = normalized_behaviours
        if not isinstance(entity.get("behaviour_config"), dict):
            entity["behaviour_config"] = {}
        if not isinstance(entity.get("patrol_points"), list):
            entity["patrol_points"] = []
        if not isinstance(entity.get("animations"), dict):
            entity["animations"] = {}
        if not isinstance(entity.get("sprite_sheet"), dict):
            entity["sprite_sheet"] = {}
        entity["solid"] = bool(entity.get("solid", False))
        return entity

    def _normalize_behaviour_entry(self, entry: Any) -> dict[str, Any] | None:
        if isinstance(entry, str):
            behaviour_type = entry.strip()
            if not behaviour_type:
                return None
            return {"type": behaviour_type, "params": {}}

        if isinstance(entry, dict):
            behaviour_type = str(entry.get("type", "")).strip()
            if not behaviour_type:
                return None
            params_source = entry.get("params")
            params: dict[str, Any] = {}
            if isinstance(params_source, dict):
                params.update(params_source)
            for key, value in entry.items():
                if key in {"type", "params"}:
                    continue
                params.setdefault(key, value)
            return {"type": behaviour_type, "params": params}

        return None

    def _default_scene(self) -> Dict[str, Any]:
        return {
            "name": "<missing>",
            "version": 1,
            "settings": copy.deepcopy(DEFAULT_SETTINGS),
            "layers": copy.deepcopy(DEFAULT_LAYERS),
            "entities": [],
        }

    def _log_validation_report(self, report: ValidationReport, *, context: str) -> None:
        for warning in report.warnings:
            print(f"[Mesh][SceneLoader] WARNING ({context}): {warning}")
        for error in report.errors:
            print(f"[Mesh][SceneLoader] ERROR ({context}): {error}")

    def _validate_settings(self, settings: Dict[str, Any], report: ValidationReport) -> None:
        color = settings.get("background_color")
        if color is not None and not isinstance(color, str):
            report.add_error("settings.background_color must be a string if provided")

        width = settings.get("world_width")
        if width is not None and not self._is_number(width):
            report.add_error("settings.world_width must be a number when provided")

        height = settings.get("world_height")
        if height is not None and not self._is_number(height):
            report.add_error("settings.world_height must be a number when provided")

        music = settings.get("music")
        if music is not None and not isinstance(music, str):
            report.add_error("settings.music must be a string (path) if provided")

        music_vol = settings.get("music_volume")
        if music_vol is not None and not self._is_number(music_vol):
            report.add_error("settings.music_volume must be a number if provided")

    def _validate_layers(self, layers: List[Any], report: ValidationReport) -> None:
        for index, layer in enumerate(layers):
            if not isinstance(layer, dict):
                report.add_error(f"layers[{index}] must be an object with a 'name' field")
                continue
            name = layer.get("name")
            if not isinstance(name, str) or not name.strip():
                report.add_error(f"layers[{index}] must define a non-empty string 'name'")

    def _validate_collision_rules(self, rules: Dict[str, Any], report: ValidationReport) -> None:
        for key, value in rules.items():
            if not isinstance(key, str) or ":" not in key:
                report.add_error(
                    f"collision_rules key '{key}' must look like 'tag_a:tag_b' (with ':' separator)",
                )
                continue
            if not isinstance(value, bool):
                report.add_error(f"collision_rules['{key}'] must be a boolean")

    def _validate_tilemap_section(self, tilemap: Any, report: ValidationReport) -> None:
        if tilemap is None:
            return
        if not isinstance(tilemap, dict):
            report.add_error("Scene 'tilemap' must be an object when provided")
            return

        path_value = tilemap.get("path")
        has_path = isinstance(path_value, str) and bool(path_value.strip())

        width_value = tilemap.get("width")
        height_value = tilemap.get("height")
        tilewidth_value = tilemap.get("tilewidth")
        tileheight_value = tilemap.get("tileheight")

        internal_dims_present = all(v is not None for v in (width_value, height_value, tilewidth_value, tileheight_value))
        if internal_dims_present:
            for key, raw in (("width", width_value), ("height", height_value), ("tilewidth", tilewidth_value), ("tileheight", tileheight_value)):
                if not isinstance(raw, int) or int(raw) <= 0:
                    report.add_error(f"tilemap.{key} must be a positive int when provided")

        if not has_path:
            if internal_dims_present:
                report.add_warning("tilemap.path missing; tilemap will not render unless runtime supports in-scene grids")
            else:
                report.add_error("tilemap.path must be a non-empty string")

        collision_layer_id = tilemap.get("collision_layer_id")
        if collision_layer_id is not None and not isinstance(collision_layer_id, str):
            report.add_error("tilemap.collision_layer_id must be a string when provided")

        tile_layers_value = tilemap.get("tile_layers")
        layers_value = tilemap.get("layers")
        if tile_layers_value is None and layers_value is None:
            report.add_warning("tilemap.layers missing; no tile layers will be processed")
            return

        if tile_layers_value is not None:
            if not isinstance(tile_layers_value, list):
                report.add_error("tilemap.tile_layers must be an array when provided")
            else:
                seen: set[str] = set()
                for index, entry in enumerate(tile_layers_value):
                    if not isinstance(entry, dict):
                        report.add_error(f"tilemap.tile_layers[{index}] must be an object")
                        continue
                    layer_id = entry.get("id")
                    if not isinstance(layer_id, str) or not layer_id.strip():
                        report.add_error(f"tilemap.tile_layers[{index}] must define a non-empty 'id'")
                        continue
                    layer_id = layer_id.strip()
                    if layer_id in seen:
                        report.add_error(f"tilemap.tile_layers has duplicate id '{layer_id}'")
                    seen.add(layer_id)

                    z_value = entry.get("z")
                    if not isinstance(z_value, int):
                        report.add_error(f"tilemap.tile_layers[{index}].z must be an int")

                    parallax_value = entry.get("parallax")
                    if parallax_value is not None and not self._is_number(parallax_value):
                        report.add_error(f"tilemap.tile_layers[{index}].parallax must be a number if provided")
                    elif parallax_value is not None:
                        parallax = float(parallax_value)
                        if not (0.0 <= parallax <= 2.0):
                            report.add_error(
                                f"tilemap.tile_layers[{index}].parallax must be within [0, 2] when provided",
                            )

                    tiles_value = entry.get("tiles")
                    if tiles_value is not None:
                        if not isinstance(tiles_value, list):
                            report.add_error(f"tilemap.tile_layers[{index}].tiles must be an array when provided")
                        else:
                            for tile_index, tile in enumerate(tiles_value):
                                if not isinstance(tile, int):
                                    report.add_error(
                                        f"tilemap.tile_layers[{index}].tiles[{tile_index}] must be an int",
                                    )
                                    break

        # `tilemap.layers` is the legacy configuration for selecting layers from the underlying Tiled map.
        # When scenes provide `tilemap.tile_layers`, the legacy `layers` section is optional.
        if layers_value is None:
            return

        pairs: list[tuple[str, Any]] = []
        if isinstance(layers_value, dict):
            pairs = [(str(name), cfg) for name, cfg in layers_value.items()]
        elif isinstance(layers_value, list):
            for index, entry in enumerate(layers_value):
                if not isinstance(entry, dict):
                    report.add_error(f"tilemap.layers[{index}] must be an object")
                    continue
                layer_name = entry.get("name")
                if not isinstance(layer_name, str) or not layer_name.strip():
                    report.add_error(f"tilemap.layers[{index}] must define a non-empty 'name'")
                    continue
                pairs.append((layer_name, entry))
        else:
            report.add_error("tilemap.layers must be an object or array")
            return

        for name, cfg in pairs:
            if not isinstance(name, str) or not name.strip():
                report.add_error("tilemap layer names must be non-empty strings")
                continue
            if not isinstance(cfg, dict):
                report.add_error(f"tilemap layer '{name}' must be an object")
                continue
            z_value = cfg.get("z")
            if z_value is not None:
                if isinstance(z_value, int):
                    pass
                else:
                    z_normalized = str(z_value).lower()
                    if z_normalized not in {"background", "foreground"}:
                        report.add_warning(
                            f"tilemap layer '{name}' uses unknown z bucket '{z_value}', defaulting to background",
                        )

            parallax_value = cfg.get("parallax")
            if parallax_value is not None and not self._is_number(parallax_value):
                report.add_error(f"tilemap layer '{name}'.parallax must be a number if provided")
            elif parallax_value is not None:
                parallax = float(parallax_value)
                if not (0.0 <= parallax <= 2.0):
                    report.add_error(f"tilemap layer '{name}'.parallax must be within [0, 2] when provided")

            properties_value = cfg.get("properties") if isinstance(cfg, dict) else None
            if properties_value is not None and not isinstance(properties_value, dict):
                report.add_warning(
                    f"tilemap layer '{name}' has non-object 'properties'; ignoring",
                )

    def _normalize_tilemap_section(
        self,
        tilemap: Any,
        *,
        base_path: Path,
    ) -> dict[str, Any] | None:
        if not isinstance(tilemap, dict):
            return None
        path_value = tilemap.get("path")
        has_path = isinstance(path_value, str) and bool(path_value.strip())

        normalized: dict[str, Any] = {}
        for key in ("width", "height", "tilewidth", "tileheight"):
            value = tilemap.get(key)
            if isinstance(value, int):
                normalized[key] = int(value)

        normalized_layers: list[dict[str, Any]] = []
        if has_path:
            for name, cfg in self._iter_tilemap_layers(tilemap.get("layers")):
                properties = cfg.get("properties")
                prop_dict = dict(properties) if isinstance(properties, dict) else {}
                normalized_layers.append(
                    {
                        "name": name,
                        "draw": bool(cfg.get("draw", True)),
                        "collision": bool(cfg.get("collision", False)),
                        "z": cfg.get("z", "background"),
                        "parallax": cfg.get("parallax", 1.0),
                        "collision_tag": cfg.get("collision_tag"),
                        "properties": prop_dict,
                    }
                )

        normalized_tile_layers: list[dict[str, Any]] = []
        raw_tile_layers = tilemap.get("tile_layers")
        if isinstance(raw_tile_layers, list):
            for entry in raw_tile_layers:
                if not isinstance(entry, dict):
                    continue
                layer_id = entry.get("id")
                if not isinstance(layer_id, str) or not layer_id.strip():
                    continue
                properties = entry.get("properties")
                prop_dict = dict(properties) if isinstance(properties, dict) else {}
                tiles = entry.get("tiles")
                normalized_entry: dict[str, Any] = {
                    "id": layer_id.strip(),
                    "z": entry.get("z", -100),
                    "parallax": entry.get("parallax", 1.0),
                    "draw": bool(entry.get("draw", True)),
                    "collision": bool(entry.get("collision", False)),
                    "collision_tag": entry.get("collision_tag"),
                    "properties": prop_dict,
                }
                if isinstance(tiles, list):
                    normalized_entry["tiles"] = list(tiles)
                normalized_tile_layers.append(normalized_entry)

        if has_path:
            resolved_path = Path(str(path_value))
            if not resolved_path.is_absolute():
                resolved_path = (base_path / resolved_path).resolve()
            normalized["path"] = str(path_value)
            normalized["resolved_path"] = str(resolved_path)
            normalized["layers"] = normalized_layers

        overrides_value = tilemap.get("overrides")
        if isinstance(overrides_value, dict):
            normalized["overrides"] = copy.deepcopy(overrides_value)

        collision_layer_id = tilemap.get("collision_layer_id")
        if isinstance(collision_layer_id, str) and collision_layer_id.strip():
            normalized["collision_layer_id"] = collision_layer_id.strip()

        if normalized_tile_layers:
            normalized["tile_layers"] = normalized_tile_layers

        if not normalized:
            return None

        return normalized

    def _iter_tilemap_layers(self, raw_layers: Any) -> Iterable[tuple[str, dict[str, Any]]]:
        if isinstance(raw_layers, dict):
            for name, cfg in raw_layers.items():
                if isinstance(name, str) and isinstance(cfg, dict) and name.strip():
                    yield name.strip(), cfg
        elif isinstance(raw_layers, list):
            for entry in raw_layers:
                if not isinstance(entry, dict):
                    continue
                layer_name = entry.get("name")
                if isinstance(layer_name, str) and layer_name.strip():
                    yield layer_name.strip(), entry

    def _validate_behaviours(
        self,
        behaviours_value: Any,
        entity_label: str,
        report: ValidationReport,
    ) -> Set[str]:
        allowed_fields: Set[str] = set()
        if behaviours_value is None:
            return allowed_fields
        if not isinstance(behaviours_value, list):
            report.add_error(f"{entity_label}: 'behaviours' must be an array")
            return allowed_fields

        for index, entry in enumerate(behaviours_value):
            entry_label = f"{entity_label} behaviour[{index}]"
            normalized = self._normalize_behaviour_entry(entry)
            if normalized is None:
                report.add_error(f"{entry_label}: behaviour entries must define a type")
                continue

            behaviour_type = normalized.get("type")
            if not behaviour_type:
                report.add_error(f"{entry_label}: missing behaviour type")
                continue

            info = get_behaviour_info(behaviour_type)
            if info is None:
                report.add_error(f"{entry_label}: behaviour '{behaviour_type}' is not registered")
                continue

            field_names = {
                str(field.get("name"))
                for field in info.config_fields
                if field.get("name")
            }
            allowed_fields.update(field_names)

            params = normalized.get("params", {})
            self._validate_behaviour_params(
                entity_label,
                entry_label,
                behaviour_type,
                params,
                report,
            )

        return allowed_fields

    def _validate_behaviour_params(
        self,
        entity_label: str,
        entry_label: str,
        behaviour_type: str,
        params: Any,
        report: ValidationReport,
    ) -> None:
        if params is None:
            report.add_behaviour_detail(entity_label, behaviour_type, "no params provided")
            return
        if not isinstance(params, dict):
            report.add_error(f"{entry_label}: params must be an object when provided")
            report.add_behaviour_detail(
                entity_label,
                behaviour_type,
                "params value must be an object",
            )
            return

        if not params:
            report.add_behaviour_detail(entity_label, behaviour_type, "no params provided")
        param_defs = get_behaviour_param_defs(behaviour_type)
        provided_keys = set(params.keys())
        if param_defs:
            missing_required = [k for k, spec in param_defs.items() if spec.default is None and k not in provided_keys]
            if missing_required:
                report.add_warning(f"{entry_label}: missing required params: {', '.join(missing_required)}")
                for key in missing_required:
                    report.add_behaviour_detail(
                        entity_label,
                        behaviour_type,
                        f"param {key} missing (REQUIRED)",
                    )
        if not params:
            return

        if not param_defs and params:
            report.add_behaviour_detail(entity_label, behaviour_type, "behaviour does not declare PARAM_DEFS")
        for key, value in params.items():
            spec = param_defs.get(key)
            display_value = self._format_param_value(value)
            if spec is None:
                suggestion = self._suggest_param_name(key, param_defs)
                message = f"{entry_label}: unknown param '{key}'"
                if suggestion:
                    message += f" (did you mean '{suggestion}'?)"
                report.add_warning(message)
                detail = f"param {key} = {display_value} (UNKNOWN PARAM"
                if suggestion:
                    detail += f", did you mean {suggestion}?"
                detail += ")"
                report.add_behaviour_detail(entity_label, behaviour_type, detail)
                continue
            expected = self._param_kind_from_def(spec)
            if not self._value_matches_type(value, expected):
                report.add_error(
                    f"{entry_label}: param '{key}' must be of type {expected}, got {self._type_name(value)}",
                )
                detail = f"param {key} = {display_value} (TYPE MISMATCH expected {expected})"
                report.add_behaviour_detail(entity_label, behaviour_type, detail)
                continue
            report.add_behaviour_detail(
                entity_label,
                behaviour_type,
                f"param {key} = {display_value} (OK)",
            )

    def _validate_behaviour_config(
        self,
        entry_label: str,
        config: Dict[str, Any],
        info,
        report: ValidationReport,
    ) -> None:
        spec_by_name = {
            str(field.get("name")): field
            for field in info.config_fields
            if field.get("name")
        }
        for key, value in config.items():
            if key == "type":
                continue
            spec = spec_by_name.get(key)
            if spec is None:
                report.add_warning(f"{entry_label}: unknown config field '{key}'")
                continue
            expected_type = str(spec.get("type", "string"))
            if not self._value_matches_type(value, expected_type):
                report.add_error(
                    f"{entry_label}: field '{key}' must be of type {expected_type}, got {self._type_name(value)}",
                )

    def _validate_behaviour_config_section(
        self,
        config_value: Any,
        entity_label: str,
        report: ValidationReport,
    ) -> None:
        if config_value is None:
            return
        if not isinstance(config_value, dict):
            report.add_error(f"{entity_label}: 'behaviour_config' must be an object when provided")
            return

        for behaviour_name, config in config_value.items():
            if not isinstance(behaviour_name, str) or not behaviour_name.strip():
                report.add_error(f"{entity_label}: behaviour_config keys must be non-empty strings")
                continue
            info = get_behaviour_info(behaviour_name)
            if info is None:
                report.add_error(
                    f"{entity_label}: behaviour_config references unknown behaviour '{behaviour_name}'",
                )
                continue
            if not isinstance(config, dict):
                report.add_error(
                    f"{entity_label}: behaviour_config['{behaviour_name}'] must be an object",
                )
                continue
            self._validate_behaviour_config(
                f"{entity_label} behaviour_config[{behaviour_name}]",
                config,
                info,
                report,
            )

    def _require_string(
        self,
        entity: Dict[str, Any],
        field: str,
        report: ValidationReport,
        label: str,
        *,
        required: bool,
    ) -> None:
        value = entity.get(field)
        if value is None:
            if required:
                report.add_error(f"{label}: missing required field '{field}'")
            return
        if not isinstance(value, str):
            report.add_error(f"{label}: field '{field}' must be a string")

    def _require_number(
        self,
        entity: Dict[str, Any],
        field: str,
        report: ValidationReport,
        label: str,
        *,
        required: bool,
    ) -> None:
        value = entity.get(field)
        if value is None:
            if required:
                report.add_error(f"{label}: missing required field '{field}'")
            return
        if not self._is_number(value):
            report.add_error(f"{label}: field '{field}' must be a number")

    def _require_int(
        self,
        entity: Dict[str, Any],
        field: str,
        report: ValidationReport,
        label: str,
        *,
        required: bool = True,
        allow_zero: bool = False,
    ) -> None:
        value = entity.get(field)
        if value is None:
            if required:
                report.add_error(f"{label}: missing required field '{field}'")
            return
        if not isinstance(value, int):
            report.add_error(f"{label}: field '{field}' must be an integer")
            return
        if allow_zero:
            if value < 0:
                report.add_error(f"{label}: field '{field}' must be >= 0")
        elif value <= 0:
            report.add_error(f"{label}: field '{field}' must be > 0")

    def _require_positive_int(
        self,
        entity: Dict[str, Any],
        field: str,
        report: ValidationReport,
        label: str,
        *,
        required: bool = True,
    ) -> None:
        self._require_int(entity, field, report, label, required=required, allow_zero=False)

    def _format_entity_label(self, index: Optional[int], entity: Dict[str, Any]) -> str:
        name = entity.get("name", "<unnamed>")
        if index is None:
            return f"Entity '{name}'"
        return f"Entity[{index}] '{name}'"

    def _type_name(self, value: Any) -> str:
        return type(value).__name__

    def _is_number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _value_matches_type(self, value: Any, expected: str) -> bool:
        expected = expected.lower()
        if expected == "bool":
            return isinstance(value, bool)
        if expected in {"float", "int"}:
            if not self._is_number(value):
                return False
            if expected == "int" and not isinstance(value, int):
                return False
            return True
        if expected == "string":
            return isinstance(value, str)
        if expected == "array":
            return isinstance(value, (list, tuple))
        if expected == "object":
            return isinstance(value, dict)
        return True

    @staticmethod
    def _format_param_value(value: Any) -> str:
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if value is None:
            return "null"
        return repr(value)

    def _suggest_param_name(self, candidate: str, param_defs: Dict[str, Any]) -> str | None:
        if not param_defs:
            return None
        names = list(param_defs.keys())
        matches = difflib.get_close_matches(candidate, names, n=1, cutoff=0.7)
        return matches[0] if matches else None

    def _param_kind_from_def(self, spec: Any) -> str:
        raw_type = getattr(spec, "type", None)
        if raw_type in {int, "int"}:
            return "int"
        if raw_type in {float, "float"}:
            return "float"
        if raw_type in {bool, "bool"}:
            return "bool"
        if raw_type in {list, tuple, "array"}:
            return "array"
        if raw_type in {dict, "object"}:
            return "object"
        return "string"
