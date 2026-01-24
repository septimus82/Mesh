"""Validator for prefab definitions."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Set

from engine.paths import resolve_path


class PrefabValidator:
    """Validates prefab definitions against schema and integrity rules."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.prefabs: List[Dict[str, Any]] = []

    def validate_path(self, path: str | Path) -> bool:
        """Run validation for a specific prefab file path."""

        self.errors = []
        self.warnings = []
        self.prefabs = []

        resolved = resolve_path(path) if isinstance(path, str) else path
        print(f"[Mesh][Validator] Validating prefabs: {resolved}")

        if not resolved.exists():
            self.errors.append(f"{resolved} not found")
            return False

        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            self.errors.append(f"Failed to parse {resolved}: {e}")
            return False

        if not isinstance(data, list):
            self.errors.append(f"{resolved} must be a list")
            return False

        self.prefabs = data
        seen_ids: Set[str] = set()

        for idx, item in enumerate(self.prefabs):
            if not isinstance(item, dict):
                self.errors.append(f"Item {idx} is not a dictionary")
                continue

            pid = item.get("id")
            if not pid:
                self.errors.append(f"Item {idx} missing 'id'")
                continue

            if pid in seen_ids:
                self.errors.append(f"Duplicate prefab ID: '{pid}'")
            seen_ids.add(pid)

            if "entity" not in item:
                self.errors.append(f"Prefab '{pid}' missing 'entity' block")

            # Basic entity validation
            entity = item.get("entity", {})
            if not isinstance(entity, dict):
                self.errors.append(f"Prefab '{pid}' entity is not a dictionary")

            for field in ("collision_poly", "occluder_poly"):
                points = entity.get(field)
                if not isinstance(points, list):
                    continue
                try:
                    from engine.geometry_tools import sanitize_poly  # noqa: PLC0415

                    sanitized = sanitize_poly(points)
                except Exception:  # noqa: BLE001
                    sanitized = []
                if not sanitized:
                    self.warnings.append(f"Prefab '{pid}' {field} is invalid/degenerate")

            # Validate tags
            if "tags" in item:
                if not isinstance(item["tags"], list):
                    self.errors.append(f"Prefab '{pid}' tags must be a list")
                else:
                    for t in item["tags"]:
                        if not isinstance(t, str):
                            self.errors.append(f"Prefab '{pid}' tag '{t}' is not a string")

            # Validate metadata
            if "metadata" in item:
                if not isinstance(item["metadata"], dict):
                    self.errors.append(f"Prefab '{pid}' metadata must be a dictionary")

            # Boss convention: if a prefab is explicitly tagged as boss, require minimal metadata.
            tags = item.get("tags", [])
            if isinstance(tags, list) and "boss" in tags:
                meta_raw = item.get("metadata")
                metadata: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
                if "author" not in metadata:
                    self.errors.append(f"Prefab '{pid}' tagged boss must include metadata.author")
                if not item.get("display_name"):
                    self.errors.append(f"Prefab '{pid}' tagged boss must include display_name")

        self._validate_inheritance(seen_ids)
        self._validate_usage_in_encounter_sets(seen_ids)

        return len(self.errors) == 0

    def validate(self) -> bool:
        """Run validation. Returns True if no errors."""
        return self.validate_path("assets/prefabs.json")

    def _validate_inheritance(self, all_ids: Set[str]) -> None:
        """Validate inheritance chains."""
        # Build map for easy lookup
        prefab_map = {p["id"]: p for p in self.prefabs if isinstance(p, dict) and "id" in p}

        for pid, item in prefab_map.items():
            base = item.get("base")
            if not base:
                continue

            if base not in all_ids:
                self.errors.append(f"Prefab '{pid}' inherits from unknown base '{base}'")
                continue

            # Check for cycles and depth
            visited = set()
            curr = pid
            depth = 0
            max_depth = 20

            while curr:
                if curr in visited:
                    self.errors.append(f"Inheritance cycle detected involving '{pid}'")
                    break
                visited.add(curr)

                curr_def = prefab_map.get(curr)
                if not curr_def:
                    break # Should be caught by unknown base check

                curr = curr_def.get("base")
                depth += 1

                if depth > max_depth:
                    self.errors.append(f"Inheritance depth exceeded for '{pid}' (> {max_depth})")
                    break

    def _validate_usage_in_encounter_sets(self, valid_ids: Set[str]) -> None:
        """Check that encounter sets reference valid prefabs."""
        path = resolve_path("packs/core_regions/data/encounter_sets.json")
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            encounter_sets = data.get("encounter_sets", [])

            for es in encounter_sets:
                es_id = es.get("id", "unknown")
                prefab_ids = es.get("enemy_prefab_ids", [])

                if not isinstance(prefab_ids, list):
                    self.errors.append(f"Encounter Set '{es_id}': enemy_prefab_ids must be a list")
                    continue

                for pid in prefab_ids:
                    prefab_id: str | None = None
                    if isinstance(pid, str):
                        prefab_id = pid.strip()
                    elif isinstance(pid, Mapping):
                        raw = pid.get("prefab_id")
                        if isinstance(raw, str):
                            prefab_id = raw.strip()
                        else:
                            self.errors.append(f"Encounter Set '{es_id}' has enemy_prefab_ids entry missing prefab_id")
                            continue
                    else:
                        self.errors.append(f"Encounter Set '{es_id}' has invalid enemy_prefab_ids entry type")
                        continue

                    if not prefab_id:
                        self.errors.append(f"Encounter Set '{es_id}' has empty enemy prefab id")
                        continue
                    if prefab_id not in valid_ids:
                        self.errors.append(f"Encounter Set '{es_id}' references unknown prefab '{prefab_id}'")

        except json.JSONDecodeError:
            self.errors.append("Failed to parse packs/core_regions/data/encounter_sets.json")
        except Exception as e:
            self.errors.append(f"Error validating encounter sets: {e}")

    def print_report(self) -> None:
        """Print validation results to console."""
        if not self.errors and not self.warnings:
            print("[Mesh][Validator] Prefabs OK.")
            return

        for w in self.warnings:
            print(f"[WARN] {w}")
        for e in self.errors:
            print(f"[ERR]  {e}")
