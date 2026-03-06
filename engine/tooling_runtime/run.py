"""Runtime implementation for validate-all tooling (pure refactor)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Type

from engine.paths import resolve_path
from engine.behaviours import load_builtin_behaviours
from engine.tooling_runtime import discovery, json_lines
from engine.validators.prefab_validator import PrefabValidator
from engine.validators.reference_validator import ReferenceValidator
from engine.validators.schema_validation import (
    ValidationError,
    render_validation_error_line,
    sort_validation_errors,
    validate_scene as schema_validate_scene,
    validate_world as schema_validate_world,
)
from engine.validators.transition_validator import TransitionValidator
from engine.validators.variant_validator import VariantValidator
from engine.validators.theme_spawn_variant_override_validator import validate_theme_spawn_variant_override_settings
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)



class UnifiedValidatorCore:
    def __init__(
        self,
        root_path: Path,
        strict_compact: bool = False,
        check_events: bool = True,
        check_reachability: bool = False,
        check_orphans: bool = False,
        check_refs: bool = False,
        check_prefabs: bool = True,
        strict: bool = False,
        schema_strict: bool = False,
        *,
        prefix: str = "[Mesh][ValidateAll]",
        scene_loader_cls: Type[Any] | None = None,
        event_validator_cls: Type[Any] | None = None,
        prefab_validator_cls: Type[Any] = PrefabValidator,
        variant_validator_cls: Type[Any] = VariantValidator,
        transition_validator_cls: Type[Any] = TransitionValidator,
    ):
        self.root = root_path
        self.prefix = str(prefix)
        self.strict_compact = strict_compact
        self.strict = strict
        self.schema_strict = schema_strict
        self.check_events = check_events
        self.do_check_reachability = check_reachability
        self.do_check_orphans = check_orphans
        self.do_check_refs = check_refs
        self.do_check_prefabs = check_prefabs

        # Ensure behaviours are registered for validation
        load_builtin_behaviours()

        if scene_loader_cls is None:
            from engine.scene_loader import SceneLoader

            scene_loader_cls = SceneLoader
        if event_validator_cls is None:
            from engine.tooling.event_validator import EventValidator

            event_validator_cls = EventValidator

        self.scene_loader = scene_loader_cls()
        self.event_validator = event_validator_cls(root_path)
        self.prefab_validator = prefab_validator_cls()
        self.variant_validator = variant_validator_cls()
        self.transition_validator = transition_validator_cls(strict=strict)

        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.schema_errors: list[ValidationError] = []
        self.schema_warnings: list[ValidationError] = []

    def _add_legacy_error(self, message: str) -> None:
        self.errors.append(str(message))

    def _add_legacy_warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def validate_path(self, target_path: Path) -> bool:
        if self.do_check_prefabs:
            if not self.prefab_validator.validate():
                self.errors.extend(self.prefab_validator.errors)
                self.warnings.extend(self.prefab_validator.warnings)

            if not self.variant_validator.validate():
                self.errors.extend(self.variant_validator.errors)
                self.warnings.extend(self.variant_validator.warnings)

        if not target_path.exists():
            self.errors.append(f"Path not found: {target_path}")
            return False

        try:
            with open(target_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            _log_swallow("TRUN-001", "engine/tooling_runtime/run.py blanket swallow", once=True)
            self.errors.append(f"Failed to parse JSON {target_path}: {e}")
            return False

        is_world = "scenes" in data and isinstance(data["scenes"], dict)
        is_scene = "entities" in data and isinstance(data["entities"], list)

        if is_world:
            return self.validate_world(target_path, data)
        if is_scene:
            return self.validate_scene(target_path)
        self.errors.append(f"Unknown file type: {target_path}")
        return False

    def validate_world(self, path: Path, data: Dict[str, Any]) -> bool:
        print(f"{self.prefix} Validating world: {path}")
        ok = True

        self.schema_errors.extend(
            schema_validate_world(
                path,
                data,
                workspace_root=self.root,
                validate_scene_files=False,
                strict=self.schema_strict,
            )
        )
        if self.schema_errors:
            ok = False

        scenes = data.get("scenes", {})
        for key, scene_def in scenes.items():
            scene_path_str = scene_def.get("path")
            if not scene_path_str:
                self._add_legacy_error(f"World {path}: Scene '{key}' missing path")
                ok = False
                continue

            scene_path = resolve_path(scene_path_str)
            if not scene_path.exists():
                self._add_legacy_error(f"World {path}: Scene '{key}' path not found: {scene_path}")
                ok = False
                continue

            if not self.validate_scene(scene_path):
                ok = False

        print(f"{self.prefix} Validating transitions...")
        if not self.transition_validator.validate(path):
            self.errors.extend(self.transition_validator.errors)
            if self.strict:
                ok = False
        self.warnings.extend(self.transition_validator.warnings)

        if self.check_events:
            print(f"{self.prefix} Running event validation...")
            self.event_validator.load_definitions()
            self.event_validator.validate_quests()
            self.event_validator.validate_scenes()

            if self.event_validator.errors:
                self.errors.extend(self.event_validator.errors)
                ok = False
            if self.event_validator.warnings:
                self.warnings.extend(self.event_validator.warnings)

        if self.do_check_reachability:
            self.check_reachability(data)

        if self.do_check_orphans:
            self.check_orphans(data, path)

        if self.do_check_refs:
            ref_validator = ReferenceValidator(str(path), treat_overrides_as_warn=True)
            if not ref_validator.validate():
                self.errors.extend(ref_validator.errors)
                self.warnings.extend(ref_validator.warnings)
                ok = False
            else:
                self.warnings.extend(ref_validator.warnings)

        self.validate_region_theme(path, data)

        return ok

    def validate_scene(self, path: Path) -> bool:
        print(f"{self.prefix} Validating scene: {path}")

        ok = True

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            _log_swallow("TRUN-002", "engine/tooling_runtime/run.py blanket swallow", once=True)
            self._add_legacy_error(f"Scene {path}: Failed to load JSON: {e}")
            return False

        schema_errors = schema_validate_scene(path, data, workspace_root=self.root, strict=self.schema_strict)
        if schema_errors:
            self.schema_errors.extend(schema_errors)
            ok = False

        report = self.scene_loader.validate_scene_file(str(path), strict=self.strict)
        if not report.ok:
            for err in report.errors:
                self._add_legacy_error(f"Scene {path}: {err}")
            ok = False

        for warn in report.warnings:
            self._add_legacy_warning(f"Scene {path}: {warn}")

        if not self.validate_region_theme(path, data):
            pass

        if self.strict_compact:
            from engine.scene_serializer import compact_scene_payload

            try:
                full_scene = self.scene_loader.apply_scene_defaults(data)
                compacted = compact_scene_payload(full_scene)

                if data != compacted:
                    diffs = []
                    for k in data:
                        if k not in compacted:
                            diffs.append(f"Top-level key '{k}' is redundant (matches default)")
                        elif data[k] != compacted[k]:
                            if k == "settings":
                                for sk in data["settings"]:
                                    if sk not in compacted.get("settings", {}):
                                        diffs.append(f"Settings key '{sk}' is redundant")

                    if not diffs:
                        diffs.append("Content differs (unknown detail)")

                    msg = (
                        f"Scene {path} is not compact. Run 'mesh tidy-scene' to fix.\n"
                        + "\n".join([f"  - {d}" for d in diffs])
                    )
                    self._add_legacy_error(msg)
                    return False
            except Exception as e:
                _log_swallow("TRUN-003", "engine/tooling_runtime/run.py blanket swallow", once=True)
                self._add_legacy_error(f"Scene {path}: Compactness check failed: {e}")
                return False

        if not self.validate_puzzle_wiring(path):
            if self.strict_compact and self.errors:
                return False

        from engine.validators.encounter_budget_validator import EncounterBudgetValidator

        budget_validator = EncounterBudgetValidator()
        results = budget_validator.validate(data, str(path), strict=self.strict_compact)
        for res in results:
            if res.level == "ERROR":
                self._add_legacy_error(f"Scene {path}: {res.message}")
                ok = False
            else:
                self._add_legacy_warning(f"Scene {path}: {res.message}")

        return ok

    def check_reachability(self, world_data: Dict[str, Any]) -> bool:
        scenes = world_data.get("scenes", {})
        links = world_data.get("links", [])

        if not scenes:
            return True

        start_node = world_data.get("start_scene")
        if not start_node:
            start_node = next(iter(scenes.keys()))

        if start_node not in scenes:
            self.errors.append(f"Start scene '{start_node}' not found in scenes list")
            return False

        adj: Dict[str, list[str]] = {str(k): [] for k in scenes}
        for link in links:
            src = link.get("from")
            dst = link.get("to")
            if src in adj and dst in scenes:
                adj[src].append(dst)

        visited = {start_node}
        queue = [start_node]

        while queue:
            curr = queue.pop(0)
            for neighbor in adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        unreachable = set(scenes.keys()) - visited
        if unreachable:
            for node in unreachable:
                self.warnings.append(f"Scene '{node}' is unreachable from start '{start_node}'")
            return False

        return True

    def check_orphans(self, world_data: Dict[str, Any], world_path: Path) -> bool:
        referenced_paths = set()
        scenes = world_data.get("scenes", {})
        for s in scenes.values():
            p = s.get("path")
            if p:
                referenced_paths.add(Path(p).resolve())

        scenes_dir = self.root / "scenes"
        if not scenes_dir.exists():
            return True

        orphans = []
        for f in discovery.discover_scene_files_under(scenes_dir):
            if f.resolve() not in referenced_paths:
                orphans.append(f)

        if orphans:
            for o in orphans:
                self.warnings.append(f"Orphan scene file found: {o.relative_to(self.root)}")
            return False

        return True

    def validate_puzzle_wiring(self, path: Path) -> bool:
        try:
            scene = self.scene_loader.load_scene(str(path))
        except Exception:
            _log_swallow("TRUN-004", "engine/tooling_runtime/run.py blanket swallow", once=True)
            return False

        producers = set()
        consumers = set()

        entities = scene.get("entities", [])
        for entity in entities:
            behaviours = entity.get("behaviours", {})
            behaviour_config = entity.get("behaviour_config", {})

            normalized_behaviours = {}
            if isinstance(behaviours, list):
                for b in behaviours:
                    if isinstance(b, str):
                        normalized_behaviours[b] = behaviour_config.get(b, {})
                    elif isinstance(b, dict):
                        b_type = b.get("type")
                        if b_type:
                            normalized_behaviours[b_type] = b.get("params", {})
            elif isinstance(behaviours, dict):
                normalized_behaviours = behaviours

            if "SwitchInteract" in normalized_behaviours:
                cfg = normalized_behaviours["SwitchInteract"]
                event_id = cfg.get("event_id") if cfg else ""
                if event_id:
                    producers.add(event_id)

            if "DoorLock" in normalized_behaviours:
                cfg = normalized_behaviours["DoorLock"]
                event_id = cfg.get("unlock_event") if cfg else ""
                if event_id:
                    consumers.add((event_id, entity.get("id", "unknown"), "DoorLock"))

            if "RewardChest" in normalized_behaviours:
                cfg = normalized_behaviours["RewardChest"]
                event_id = cfg.get("unlock_event") if cfg else ""
                if event_id:
                    consumers.add((event_id, entity.get("id", "unknown"), "RewardChest"))

        ok = True
        for event_id, ent_id, b_type in consumers:
            if event_id not in producers:
                msg = (
                    f"Scene {path}: Entity '{ent_id}' ({b_type}) listens to '{event_id}' but no local SwitchInteract emits it."
                )
                if self.strict_compact:
                    self.errors.append(msg)
                    ok = False
                else:
                    self.warnings.append(msg)

        return ok

    def validate_region_theme(self, path: Path, data: Dict[str, Any]) -> bool:
        settings = data.get("settings", {})
        theme_id = settings.get("region_theme")
        encounter_set_id = settings.get("encounter_set_id")

        if not theme_id and not encounter_set_id:
            return True

        themes = {}
        themes_loaded = False
        themes_path = self.root / "assets/data/themes.json"
        if themes_path.exists():
            try:
                themes = json.loads(themes_path.read_text(encoding="utf-8"))
                themes_loaded = True
            except Exception as e:
                _log_swallow("TRUN-005", "engine/tooling_runtime/run.py blanket swallow", once=True)
                self.warnings.append(f"Failed to load themes.json: {e}")
        else:
            self.warnings.append(f"Scene {path}: Theme validation skipped (themes.json missing)")

        encounter_sets = {}
        sets_loaded = False
        for sets_path in (self.root / "packs/core_regions/data/encounter_sets.json",):
            if not sets_path.exists():
                continue
            try:
                sets_data = json.loads(sets_path.read_text(encoding="utf-8"))
                for es in sets_data.get("encounter_sets", []):
                    encounter_sets[es["id"]] = es
                sets_loaded = True
            except Exception as e:
                _log_swallow("TRUN-006", "engine/tooling_runtime/run.py blanket swallow", once=True)
                self.warnings.append(f"Failed to load {sets_path}: {e}")

        ok = True

        if theme_id and themes_loaded:
            if theme_id not in themes:
                self.errors.append(f"Scene {path}: Unknown region_theme '{theme_id}'")
                ok = False
            else:
                theme_es_id = themes[theme_id].get("encounter_set_id")
                if theme_es_id and sets_loaded and theme_es_id not in encounter_sets:
                    self.errors.append(
                        f"Scene {path}: Theme '{theme_id}' references unknown encounter_set '{theme_es_id}'"
                    )
                    ok = False

        if encounter_set_id and sets_loaded:
            if encounter_set_id not in encounter_sets:
                self.errors.append(f"Scene {path}: Unknown encounter_set_id '{encounter_set_id}'")
                ok = False

        errors, warnings = validate_theme_spawn_variant_override_settings(
            scene_path=str(path),
            settings=settings if isinstance(settings, dict) else None,
        )
        if errors:
            self.errors.extend(errors)
            ok = False
        if warnings:
            self.warnings.extend(warnings)

        return ok

    def print_report(self) -> int:
        warnings: list[ValidationError] = []
        errors: list[ValidationError] = []

        errors.extend(self.schema_errors)
        warnings.extend(self.schema_warnings)

        for warn_msg in self.warnings:
            warnings.append(ValidationError(code="warn.validate_all.legacy", path="", message=str(warn_msg)))
        for err_msg in self.errors:
            errors.append(ValidationError(code="validate_all.legacy", path="", message=str(err_msg)))

        warnings = sort_validation_errors(warnings)
        errors = sort_validation_errors(errors)

        for warning in warnings:
            print(render_validation_error_line(warning))
        for error in errors:
            print(render_validation_error_line(error))

        summary = {
            "ok": len(errors) == 0,
            "warnings": len(warnings),
            "errors": len(errors),
        }
        print(json_lines.dumps_one_line(summary))
        return 0 if len(errors) == 0 else 1
