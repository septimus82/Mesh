from __future__ import annotations

import json
from typing import Any, Dict, List

from engine.content_packs import discover_packs
from engine.paths import get_content_roots, resolve_path


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


class VariantValidator:
    """Validates variant patches and their usage."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        print("[Mesh][Validator] Validating variants...")

        roots = get_content_roots()
        packs = discover_packs(roots)
        all_valid = True
        all_variant_ids = set()

        for pack in packs:
            path = pack.root / "data" / "variant_patches.json"
            if not path.exists():
                continue

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid JSON in {path}: {e}")
                all_valid = False
                continue

            if not isinstance(data, list):
                self.errors.append(f"{path} must be a list")
                all_valid = False
                continue

            pack_variant_ids = set()
            for item in data:
                if not isinstance(item, dict):
                    self.errors.append(f"Variant item in {pack.id} must be a dict")
                    continue

                vid = item.get("id")
                if not vid:
                    self.errors.append(f"Variant in {pack.id} missing 'id'")
                    continue

                if vid in pack_variant_ids:
                    self.errors.append(f"Duplicate variant ID in {pack.id}: {vid}")
                pack_variant_ids.add(vid)
                all_variant_ids.add(vid)

                # Validate fields
                self._validate_variant_fields(vid, item)

        # 2. Validate usage in Encounter Sets
        self._validate_encounter_set_usage(all_variant_ids)

        return all_valid and len(self.errors) == 0

    def _validate_variant_fields(self, vid: str, item: Dict[str, Any]) -> None:
        # Multipliers
        for field in ["hp_mult", "damage_mult", "speed_mult"]:
            if field in item:
                val = item[field]
                if not isinstance(val, (int, float)):
                    self.errors.append(f"Variant '{vid}': {field} must be a number")
                elif val < 0:
                    self.errors.append(f"Variant '{vid}': {field} must be non-negative")

        # Tags
        for field in ["tags_add", "tags_remove"]:
            if field in item:
                val = item[field]
                if not isinstance(val, list):
                    self.errors.append(f"Variant '{vid}': {field} must be a list of strings")
                else:
                    for tag in val:
                        if not isinstance(tag, str):
                            self.errors.append(f"Variant '{vid}': {field} contains non-string")

        # Sprite
        if "sprite_override" in item:
            sprite = item["sprite_override"]
            if not isinstance(sprite, str):
                self.errors.append(f"Variant '{vid}': sprite_override must be a string")
            # We could check if file exists, but that might be slow or context-dependent

        # Tier conventions (stable representation for tooling)
        if item.get("is_elite"):
            tags_add = item.get("tags_add", [])
            if not (isinstance(tags_add, list) and any(isinstance(t, str) and t == "elite" for t in tags_add)):
                self.errors.append(f"Variant '{vid}': is_elite requires tags_add include 'elite'")

        if item.get("is_boss"):
            tags_add = item.get("tags_add", [])
            if not (isinstance(tags_add, list) and any(isinstance(t, str) and t == "boss" for t in tags_add)):
                self.errors.append(f"Variant '{vid}': is_boss requires tags_add include 'boss'")

        if item.get("is_mini_boss"):
            tags_add = item.get("tags_add", [])
            if not (isinstance(tags_add, list) and any(isinstance(t, str) and t == "mini_boss" for t in tags_add)):
                self.errors.append(f"Variant '{vid}': is_mini_boss requires tags_add include 'mini_boss'")

    def _validate_encounter_set_usage(self, valid_ids: set[str]) -> None:
        path = resolve_path("packs/core_regions/data/encounter_sets.json")
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for es in data.get("encounter_sets", []):
                vid = es.get("variant_id")
                if vid and vid not in valid_ids:
                    self.errors.append(f"Encounter Set '{es.get('id')}' references unknown variant '{vid}'")
        except Exception:
            _log_swallow("VARI-001", "engine/validators/variant_validator.py pass-only blanket swallow")
            pass
