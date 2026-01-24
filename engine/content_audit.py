"""Content audit system for detecting unused assets and data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from engine.migrations import migrate_payload
from engine.paths import get_content_index, resolve_path

logger = logging.getLogger(__name__)

_MESH_AUDIT_LOGGED_ONCE: set[str] = set()


def _mesh_audit_log_once(key: str, exc: Exception, *, context: str = "") -> None:
    if key in _MESH_AUDIT_LOGGED_ONCE:
        return
    _MESH_AUDIT_LOGGED_ONCE.add(key)
    suffix = f" ({context})" if context else ""
    logger.error("Audit error %s%s: %s", key, suffix, exc, exc_info=True)


class ContentAuditor:
    """Audits content to find unused assets and definitions."""

    def __init__(self, world_path: str = "worlds/main_world.json") -> None:
        self.world_path = world_path

        # Collections of found references
        self.ref_assets: Set[str] = set()
        self.ref_prefabs: Set[str] = set()
        self.ref_items: Set[str] = set()
        self.ref_quests: Set[str] = set()

        # Collections of definitions
        self.def_prefabs: Set[str] = set()
        self.def_items: Set[str] = set()
        self.def_quests: Set[str] = set()

        # Available files on disk
        self.available_files: Dict[str, str] = {} # path -> pack_id

        # Heuristic text corpus (all loaded JSON content dumped to string)
        self._corpus: List[str] = []

    def audit(self, ignore_patterns: Optional[List[str]] = None, allow_packs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run the full audit."""
        self._scan_index()

        # Auto-exempt packs based on manifest
        index = get_content_index()
        allow_pack_ids: set[str] = set(allow_packs or [])

        for pack in index.packs:
            if pack.audit_exempt:
                allow_pack_ids.add(pack.id)

        self._scan_definitions()
        self._scan_world()

        # Heuristic check for quests and items in the corpus
        # (e.g. referenced in dialogue, events, scripts)
        full_corpus = " ".join(self._corpus)

        # Check items
        for item_id in list(self.def_items):
            if item_id not in self.ref_items:
                # Simple heuristic: if the ID appears in the corpus (outside its definition), mark used
                # We need to be careful not to match the definition itself.
                # But _scan_definitions adds to corpus? No, let's not add definitions to corpus.
                if item_id in full_corpus:
                    self.ref_items.add(item_id)

        # Check quests
        for quest_id in list(self.def_quests):
            if quest_id not in self.ref_quests:
                if quest_id in full_corpus:
                    self.ref_quests.add(quest_id)

        return self._build_report(ignore_patterns, list(allow_pack_ids))

    def _scan_index(self) -> None:
        """Index all available files."""
        index = get_content_index(refresh=True)
        index.build()

        for key, entry in index.entries.items():
            self.available_files[key] = entry.providing_pack_id

    def _scan_definitions(self) -> None:
        """Load definitions for prefabs, items, quests."""

        # Prefabs
        p_path = resolve_path("assets/prefabs.json")
        if p_path.exists():
            try:
                data = json.loads(p_path.read_text(encoding="utf-8"))
                for p in data:
                    self.def_prefabs.add(p["id"])
                    # Prefab definition references assets
                    if "entity" in p:
                        self._scan_entity(p["entity"])
            except Exception as exc:  # noqa: BLE001
                _mesh_audit_log_once("scan_definitions:prefabs", exc, context=str(p_path))

        # Items
        i_path = resolve_path("assets/data/items.json")
        if i_path.exists():
            try:
                data = json.loads(i_path.read_text(encoding="utf-8"))
                for item in data.get("items", []):
                    self.def_items.add(item["id"])
                    if "icon" in item:
                        self.ref_assets.add(item["icon"])
            except Exception as exc:  # noqa: BLE001
                _mesh_audit_log_once("scan_definitions:items", exc, context=str(i_path))

        # Quests
        q_path = resolve_path("assets/data/quests.json")
        if q_path.exists():
            try:
                data = json.loads(q_path.read_text(encoding="utf-8"))
                for q in data.get("quests", []):
                    self.def_quests.add(q["id"])
                    # Quests might reference items or other things in stages
                    # We add quest text to corpus? No, quest definition is self-contained.
            except Exception as exc:  # noqa: BLE001
                _mesh_audit_log_once("scan_definitions:quests", exc, context=str(q_path))

    def _scan_world(self) -> None:
        """Scan the world and all referenced scenes."""
        w_path = resolve_path(self.world_path)
        if not w_path.exists():
            return

        try:
            w_data = json.loads(w_path.read_text(encoding="utf-8"))
            w_data = migrate_payload("world", w_data)

            # Add to corpus for heuristic matching
            self._corpus.append(json.dumps(w_data))

            scenes_to_scan = set()
            if "initial_scene" in w_data:
                scenes_to_scan.add(w_data["initial_scene"])

            for node in w_data.get("map_nodes", {}).values():
                if "scene_file" in node:
                    scenes_to_scan.add(node["scene_file"])

            for s_def in w_data.get("scenes", {}).values():
                if "path" in s_def:
                    scenes_to_scan.add(s_def["path"])

            for s_path in scenes_to_scan:
                self._scan_scene(s_path)

        except Exception as exc:  # noqa: BLE001
            _mesh_audit_log_once("scan_world", exc, context=str(w_path))

    def _scan_scene(self, path: str) -> None:
        """Scan a single scene."""
        self.ref_assets.add(path) # The scene file itself is used

        p = resolve_path(path)
        if not p.exists():
            return

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data = migrate_payload("scene", data)

            # Add to corpus
            self._corpus.append(json.dumps(data))

            if "tilemap" in data:
                self.ref_assets.add(data["tilemap"])

            for ent in data.get("entities", []):
                self._scan_entity(ent)

        except Exception as exc:  # noqa: BLE001
            _mesh_audit_log_once("scan_scene", exc, context=str(p))

    def _scan_entity(self, ent: Dict[str, Any]) -> None:
        """Scan an entity definition for references."""
        if "sprite" in ent:
            self.ref_assets.add(ent["sprite"])
        if "animation" in ent:
            self.ref_assets.add(ent["animation"])
        if "prefab_id" in ent:
            self.ref_prefabs.add(ent["prefab_id"])

        # Check for dialogue which might reference things
        if "dialogue" in ent:
            # Dialogue is usually a dict or string. If it's a file path, add it.
            d = ent["dialogue"]
            if isinstance(d, str) and d.endswith(".json"):
                self.ref_assets.add(d)
                # Load dialogue to scan for quest/item refs?
                # For now, rely on corpus heuristic.
                try:
                    dp = resolve_path(d)
                    if dp.exists():
                        self._corpus.append(dp.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    _mesh_audit_log_once("scan_entity:dialogue", exc, context=str(d))

    def _build_report(self, ignore_patterns: Optional[List[str]] = None, allow_packs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Construct the audit report."""
        import fnmatch

        ignore_patterns = ignore_patterns or []
        allow_pack_ids: set[str] = set(allow_packs or [])

        # Filter available files to only assets we care about
        asset_extensions = {".png", ".jpg", ".wav", ".ogg", ".mp3", ".json"}
        # Exclude definitions themselves from "unused assets" check if they are config files
        # But actually, if a texture is in available_files and not in ref_assets, it's unused.

        unused_assets = []

        # Categorize unused assets
        categories = {
            "texture": {".png", ".jpg"},
            "audio": {".wav", ".ogg", ".mp3"},
            "data": {".json"},
            "other": set()
        }

        for path, pack_id in self.available_files.items():
            suffix = Path(path).suffix
            if suffix not in asset_extensions:
                continue

            # Skip known config files
            if path in ["config.json", "mesh_index.json", "assets/prefabs.json",
                       "assets/data/items.json", "assets/data/quests.json", "assets/data/events.json"]:
                continue

            # Skip python files, etc
            if path.startswith("engine/") or path.startswith("tests/") or path.startswith("tooling/"):
                continue

            # Check allow packs
            if pack_id in allow_pack_ids:
                continue

            # Check ignore patterns
            if any(fnmatch.fnmatch(path, pat) for pat in ignore_patterns):
                continue

            if path not in self.ref_assets:
                # Determine category
                cat = "other"
                for c_name, c_exts in categories.items():
                    if suffix in c_exts:
                        cat = c_name
                        break

                unused_assets.append({
                    "path": path,
                    "pack": pack_id,
                    "type": "asset",
                    "category": cat
                })

        unused_prefabs = [
            {"id": pid, "type": "prefab"}
            for pid in self.def_prefabs if pid not in self.ref_prefabs
        ]

        unused_items = [
            {"id": iid, "type": "item"}
            for iid in self.def_items if iid not in self.ref_items
        ]

        unused_quests = [
            {"id": qid, "type": "quest"}
            for qid in self.def_quests if qid not in self.ref_quests
        ]

        # Count categories
        cat_counts: dict[str, int] = {}
        for item in unused_assets:
            c = item["category"]
            cat_counts[c] = cat_counts.get(c, 0) + 1

        return {
            "unused_assets": sorted(unused_assets, key=lambda x: x["path"]),
            "unused_prefabs": sorted(unused_prefabs, key=lambda x: x["id"]),
            "unused_items": sorted(unused_items, key=lambda x: x["id"]),
            "unused_quests": sorted(unused_quests, key=lambda x: x["id"]),
            "stats": {
                "total_assets": len(self.available_files),
                "referenced_assets": len(self.ref_assets),
                "unused_assets_count": len(unused_assets),
                "unused_prefabs_count": len(unused_prefabs),
                "unused_items_count": len(unused_items),
                "unused_quests_count": len(unused_quests),
                "unused_by_category": cat_counts
            }
        }

def audit_world(world_path: str = "worlds/main_world.json", ignore_patterns: Optional[List[str]] = None, allow_packs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Convenience wrapper for ContentAuditor."""
    auditor = ContentAuditor(world_path)
    return auditor.audit(ignore_patterns, allow_packs)
