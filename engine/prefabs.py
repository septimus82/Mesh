from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, cast

from engine.content_packs import discover_packs
from engine.paths import get_content_roots, resolve_path
from engine.schema_validation import validate

log = logging.getLogger(__name__)

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__ + "._swallow").debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def _load_prefab_entries(source_path: Path) -> list[Dict[str, Any]]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    validate(data, "prefab.schema.json", source_path)
    return cast(list[Dict[str, Any]], data)


class PrefabManager:
    """Manages loading and resolution of prefabs."""

    def __init__(self) -> None:
        self._prefabs: Dict[str, Dict[str, Any]] = {}
        self._variants: Dict[str, Dict[str, Any]] = {}
        self._resolved_cache: Dict[str, Dict[str, Any]] = {}
        self._resolved_variant_cache: Dict[str, Dict[str, Any]] = {}
        self._prefab_sources: Dict[str, str] = {}
        self._prefab_source_chain: Dict[str, list[str]] = {}
        self._loaded = False
        self._loaded_roots: tuple[str, ...] = ()

    def _maybe_reload_for_roots(self) -> None:
        """Reload prefabs/variants if content roots changed since last load.

        Pytest and tooling often call `engine.paths.set_content_roots()` or `chdir()`,
        which can otherwise leave this global singleton pointing at the wrong repo.
        """
        if not self._loaded:
            return
        # If this instance has never been loaded from disk (e.g. unit tests manually
        # populate `_prefabs`/`_variants` and flip `_loaded=True`), don't auto-reload.
        if not self._loaded_roots:
            return
        try:
            current = tuple(str(p) for p in get_content_roots())
        except Exception:  # noqa: BLE001  # REASON: prefabs fallback isolation
            _log_swallow("PREF-001", "get_content_roots call", once=True)
            return
        if current != self._loaded_roots:
            self.load(force=True)

    @property
    def prefabs(self) -> Dict[str, Dict[str, Any]]:
        return self._prefabs

    @property
    def prefab_sources(self) -> Dict[str, str]:
        return dict(self._prefab_sources)

    @property
    def prefab_source_chain(self) -> Dict[str, list[str]]:
        return {key: list(values) for key, values in self._prefab_source_chain.items()}

    def load(self, force: bool = False) -> None:
        """Load prefabs from disk."""
        if self._loaded and not force:
            return

        self._resolved_cache.clear()
        self._resolved_variant_cache.clear()
        self._prefab_sources = {}
        self._prefab_source_chain = {}
        merged: Dict[str, Dict[str, Any]] = {}
        source_map: Dict[str, str] = {}
        chain_map: Dict[str, list[str]] = {}
        sources = self.get_prefab_sources()
        base_path = sources[0] if sources else resolve_path("assets/prefabs.json")
        roots = get_content_roots()
        self._loaded_roots = tuple(str(p) for p in roots)
        warn_overrides = os.getenv("MESH_PREFAB_WARN_OVERRIDES") == "1"
        warned_overrides: set[tuple[str, str, str]] = set()

        def _format_source(path: "Path") -> str:
            try:
                resolved = path.resolve()
            except Exception:  # noqa: BLE001  # REASON: prefabs fallback isolation
                _log_swallow("PREF-002", "path resolve", once=True)
                resolved = path
            for root in roots:
                try:
                    root_resolved = root.resolve()
                except Exception:  # noqa: BLE001  # REASON: prefabs fallback isolation
                    _log_swallow("PREF-003", "root resolve", once=True)
                    root_resolved = root
                try:
                    rel = resolved.relative_to(root_resolved)
                except Exception:  # noqa: BLE001  # REASON: prefabs fallback isolation
                    _log_swallow("PREF-004", "relative_to calc", once=True)
                    continue
                return rel.as_posix()
            return path.as_posix()

        def _record_source(prefab_id: str, source_label: str) -> None:
            chain = chain_map.setdefault(prefab_id, [])
            chain.append(source_label)

        if not base_path.exists():
            print("[Mesh][Prefabs] WARNING: assets/prefabs.json not found")
        else:
            data = _load_prefab_entries(base_path)
            source_label = _format_source(base_path)
            for entry in data:
                prefab_id = str(entry["id"])
                merged[prefab_id] = entry
                source_map[prefab_id] = source_label
                _record_source(prefab_id, source_label)

        pack_sources = sources[1:] if len(sources) > 1 else []
        for pack_path in pack_sources:
            pack_data = _load_prefab_entries(pack_path)
            source_label = _format_source(pack_path)
            for entry in pack_data:
                prefab_id = str(entry["id"])
                if prefab_id in merged and warn_overrides:
                    old_source = source_map.get(prefab_id, "")
                    new_source = source_label
                    key = (prefab_id, old_source, new_source)
                    if key not in warned_overrides:
                        warned_overrides.add(key)
                        log.warning(
                            "[Prefabs] override id=%s from=%s to=%s",
                            prefab_id,
                            old_source,
                            new_source,
                        )
                merged[prefab_id] = entry
                source_map[prefab_id] = source_label
                _record_source(prefab_id, source_label)
            print(f"[Mesh][Prefabs] Loaded {len(pack_data)} prefabs from {pack_path}")

        sorted_ids = sorted(merged)
        self._prefabs = {pid: merged[pid] for pid in sorted_ids}
        self._prefab_sources = {pid: source_map.get(pid, "") for pid in sorted_ids}
        self._prefab_source_chain = {pid: list(chain_map.get(pid, [])) for pid in sorted_ids}
        if self._prefabs:
            print(f"[Mesh][Prefabs] Loaded {len(self._prefabs)} prefabs")

        # Load variants from all packs
        self._variants = {}
        roots = get_content_roots()
        packs = discover_packs(roots)

        for pack in packs:
            # Check for data/variant_patches.json in each pack
            variant_path = pack.root / "data" / "variant_patches.json"
            if variant_path.exists():
                try:
                    v_data = json.loads(variant_path.read_text(encoding="utf-8"))
                    # Merge variants (later packs override earlier ones)
                    for v in v_data:
                        self._variants[v["id"]] = v
                    print(f"[Mesh][Prefabs] Loaded {len(v_data)} variants from pack '{pack.id}'")
                except Exception as e:  # noqa: BLE001  # REASON: prefabs fallback isolation
                    _log_swallow("PREF-007", "variants load", once=True)
                    print(f"[Mesh][Prefabs] Failed to load variants from '{pack.id}': {e}")

        self._loaded = True

    def get_prefab_sources(self) -> list["Path"]:
        """Return prefab source files in merge order (base first, then pack prefabs)."""
        from pathlib import Path

        base = resolve_path("assets/prefabs.json")
        sources: list[Path] = [base]

        roots = get_content_roots()
        pack_entries: list[tuple[str, Path]] = []
        for root in roots:
            packs_dir = root / "packs"
            if not packs_dir.exists():
                continue
            for child in packs_dir.iterdir():
                if not child.is_dir():
                    continue
                prefab_path = child / "data" / "prefabs.json"
                if prefab_path.exists():
                    pack_entries.append((child.name, prefab_path))

        pack_entries.sort(key=lambda item: (item[0].lower(), item[1].as_posix()))
        sources.extend([path for _name, path in pack_entries])
        return sources

    def get_prefab(self, prefab_id: str) -> Optional[Dict[str, Any]]:
        """Get the resolved entity data for a prefab (including inheritance)."""
        if not self._loaded:
            self.load()
        else:
            self._maybe_reload_for_roots()

        if prefab_id in self._resolved_cache:
            return self._resolved_cache[prefab_id]

        try:
            resolved = self._resolve_inheritance(prefab_id, set())
            self._resolved_cache[prefab_id] = resolved
            return resolved
        except RecursionError:
            print(f"[Mesh][Prefabs] ERROR: Cycle detected in prefab '{prefab_id}'")
            return None
        except Exception as e:  # noqa: BLE001  # REASON: prefabs fallback isolation
            _log_swallow("PREF-008", "prefab resolution", once=True)
            print(f"[Mesh][Prefabs] ERROR resolving prefab '{prefab_id}': {e}")
            return None

    def _resolve_inheritance(self, prefab_id: str, visited: set[str]) -> Dict[str, Any]:
        """Recursively resolve prefab inheritance."""
        if prefab_id in visited:
            raise RecursionError(f"Cycle detected involving {prefab_id}")

        if len(visited) > 20:
            raise RecursionError(f"Max inheritance depth exceeded for {prefab_id}")

        prefab_def = self._prefabs.get(prefab_id)
        if not prefab_def:
            # If base is missing, we can't inherit. Return empty or error?
            # For robustness, return empty dict so we don't crash, but log warning?
            # The caller get_prefab handles None return if we raise, but here we might just return empty.
            # But wait, if I request a prefab that doesn't exist, get_prefab returns None.
            # If I request a base that doesn't exist, what happens?
            return {}

        base_id = prefab_def.get("base")
        raw_entity = prefab_def.get("entity", {})
        entity_data = raw_entity.copy()
        self._copy_shape_fields(entity_data, raw_entity)

        # Merge tags from base
        tags = set(prefab_def.get("tags", []))
        display_name = prefab_def.get("display_name")

        if base_id:
            visited.add(prefab_id)
            base_resolved = self._resolve_inheritance(base_id, visited)
            visited.remove(prefab_id)

            base_entity = base_resolved.get("entity", {})
            base_tags = base_resolved.get("tags", [])
            tags.update(base_tags)
            if not display_name:
                display_name = base_resolved.get("display_name")

            # Merge: Child overrides Base
            # We start with base, then update with child
            merged_entity = base_entity.copy()
            self._copy_shape_fields(merged_entity, base_entity)
            for k, v in entity_data.items():
                # Special handling for sprite: if child has None (default) and base has value, keep base
                if k == "sprite" and v is None and merged_entity.get("sprite") is not None:
                    continue
                # Deep merge for behaviour_config
                if k == "behaviour_config" and isinstance(v, dict) and isinstance(merged_entity.get("behaviour_config"), dict):
                    merged_config = merged_entity["behaviour_config"].copy()
                    merged_config.update(v)
                    merged_entity[k] = merged_config
                else:
                    merged_entity[k] = v

            return {
                "entity": merged_entity,
                "tags": sorted(list(tags)),
                "display_name": display_name,
                "id": prefab_id
            }

        return {
            "entity": entity_data,
            "tags": sorted(list(tags)),
            "display_name": display_name,
            "id": prefab_id
        }

    @staticmethod
    def _copy_shape_fields(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for field in ("collision_poly", "occluder_poly"):
            raw = source.get(field)
            if isinstance(raw, list):
                target[field] = copy.deepcopy(raw)

    def resolve(self, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve an entity dictionary against the prefab system.
        If 'prefab_id' is present, merges the prefab data into the entity.
        """
        prefab_id = entity_data.get("prefab_id")
        if not prefab_id:
            return entity_data

        variant_id = entity_data.get("variant_id")
        resolved_prefab = self.resolve_with_variant(prefab_id, variant_id)

        if not resolved_prefab:
            # Warning? Or just return as is?
            # Existing logic just ignored it if not found, but maybe we should warn.
            return entity_data

        prefab_entity = resolved_prefab.get("entity", {})

        # Merge: Entity overrides Prefab
        # We copy the prefab first
        merged = prefab_entity.copy()
        self._copy_shape_fields(merged, prefab_entity)
        if "name" not in merged:
            display_name = resolved_prefab.get("display_name")
            if isinstance(display_name, str) and display_name.strip():
                merged["name"] = display_name

        for k, v in entity_data.items():
            # Special handling for sprite: if entity has None (default) and prefab has value, keep prefab
            if k == "sprite" and v is None and merged.get("sprite") is not None:
                continue
            # Deep merge for behaviour_config
            if k == "behaviour_config" and isinstance(v, dict) and isinstance(merged.get("behaviour_config"), dict):
                merged_config = merged["behaviour_config"].copy()
                merged_config.update(v)
                merged[k] = merged_config
            else:
                merged[k] = v

        return cast(Dict[str, Any], merged)

    def get_variant(self, variant_id: str) -> Optional[Dict[str, Any]]:
        """Get a variant definition by ID."""
        if not self._loaded:
            self.load()
        else:
            self._maybe_reload_for_roots()
        return self._variants.get(variant_id)

    def resolve_with_variant(self, prefab_id: str, variant_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Resolve a prefab with an optional variant patch applied.
        Returns the merged entity dictionary.
        """
        if not variant_id:
            return self.get_prefab(prefab_id)

        if not self._loaded:
            self.load()
        else:
            self._maybe_reload_for_roots()

        cache_key = f"{prefab_id}|{variant_id}"
        if cache_key in self._resolved_variant_cache:
            return self._resolved_variant_cache[cache_key]

        base_entity = self.get_prefab(prefab_id)
        if not base_entity:
            return None

        variant = self.get_variant(variant_id)
        if not variant:
            # If variant not found, return base (maybe warn?)
            print(f"[Mesh][Prefabs] WARNING: Variant '{variant_id}' not found, using base prefab")
            return base_entity

        # Apply patch
        patched = self._apply_variant_patch(base_entity, variant)
        self._resolved_variant_cache[cache_key] = patched
        return patched

    def _apply_variant_patch(self, base: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a variant patch to a resolved prefab wrapper."""
        import copy
        wrapper = copy.deepcopy(base)
        entity_data = wrapper.setdefault("entity", {})

        # 1. Sprite Override
        if "sprite_override" in variant:
            entity_data["sprite"] = variant["sprite_override"]

        # 2. Tags (Top level in wrapper)
        tags = set(wrapper.get("tags", []))
        if "tags_add" in variant:
            tags.update(variant["tags_add"])
        if "tags_remove" in variant:
            tags.difference_update(variant["tags_remove"])
        wrapper["tags"] = sorted(list(tags))

        # 3. Multipliers
        hp_mult = variant.get("hp_mult", 1.0)
        dmg_mult = variant.get("damage_mult", 1.0)
        speed_mult = variant.get("speed_mult", 1.0)

        # Health
        if hp_mult != 1.0:
            health_cfg = entity_data.setdefault("Health", {})
            if "max_health" in health_cfg:
                health_cfg["max_health"] = int(health_cfg["max_health"] * hp_mult)
            if "current_health" in health_cfg:
                health_cfg["current_health"] = int(health_cfg["current_health"] * hp_mult)

        # Combat / EnemyAI (Damage)
        if dmg_mult != 1.0:
            if "Combat" in entity_data:
                combat_cfg = entity_data["Combat"]
                if "damage" in combat_cfg:
                    combat_cfg["damage"] = int(combat_cfg["damage"] * dmg_mult)
            if "EnemyAI" in entity_data:
                ai_cfg = entity_data["EnemyAI"]
                if "damage" in ai_cfg:
                    ai_cfg["damage"] = int(ai_cfg["damage"] * dmg_mult)

        # Speed
        if speed_mult != 1.0:
            if "Movement" in entity_data:
                move_cfg = entity_data["Movement"]
                if "speed" in move_cfg:
                    move_cfg["speed"] = float(move_cfg["speed"] * speed_mult)
            if "EnemyAI" in entity_data:
                ai_cfg = entity_data["EnemyAI"]
                if "speed" in ai_cfg:
                    ai_cfg["speed"] = float(ai_cfg["speed"] * speed_mult)

        # 4. Encounter Cost
        is_tier_variant = bool(variant.get("is_elite") or variant.get("is_mini_boss") or variant.get("is_boss"))
        if not is_tier_variant:
            base_cost = float(entity_data.get("encounter_cost", 1))
            cost_mult = float(variant.get("cost_mult", 1.0))
            cost_add = float(variant.get("cost_add", 0))

            new_cost = (base_cost * cost_mult) + cost_add
            entity_data["encounter_cost"] = max(0.0, new_cost)

        # 5. Elite Flag
        if variant.get("is_elite"):
            entity_data["is_elite"] = True

        # 6. Boss Flag
        if variant.get("is_boss"):
            entity_data["is_boss"] = True

        # 7. Mini-boss Flag
        if variant.get("is_mini_boss"):
            entity_data["is_mini_boss"] = True

        return wrapper


# Global instance
_instance = PrefabManager()


def get_prefab_manager() -> PrefabManager:
    return _instance
