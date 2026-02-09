"""
Pure model helpers for safe asset refactoring (move/rename folders) v2.

Provides deterministic functions for:
- Computing path mappings for file and folder moves
- Scanning for references in scenes and prefabs
- Computing and applying replacements
- Generating preview summaries

Constraints:
- Pure functions, no IO
- Deterministic output ordering
"""
from __future__ import annotations

import copy
import posixpath
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

__all__ = [
    "normalize_repo_rel",
    "compute_move_mapping",
    "compute_rename_mapping",
    "scan_scene_references",
    "scan_prefab_references",
    "compute_replacements",
    "apply_replacements",
    "build_preview_summary",
    "build_refactor_preview",
    "format_preview_lines",
    "AssetReference",
    "Replacement",
    "PreviewSummary",
]

# Known asset path fields to scan in entities
ASSET_PATH_FIELDS = frozenset({
    "sprite",
    "texture",
    "asset_path",
    "image",
    "sound",
    "music",
    "tilemap",
})

# Fields inside nested dicts that may contain asset paths
NESTED_ASSET_FIELDS = {
    "sprite_sheet": ("image",),
    "light": ("texture",),
}


@dataclass(frozen=True, slots=True)
class AssetReference:
    """A reference to an asset found in a payload."""
    entity_id: str
    field_path: str  # e.g., "sprite" or "sprite_sheet.image"
    value: str
    order_key: str  # Deterministic sorting key


@dataclass(frozen=True, slots=True)
class Replacement:
    """A replacement to apply to a payload."""
    entity_id: str
    field_path: str
    old_value: str
    new_value: str
    order_key: str


@dataclass(frozen=True, slots=True)
class PreviewSummary:
    """Summary of proposed changes."""
    total_files: int
    total_refs: int
    changes_by_kind: Dict[str, int]  # e.g. "scene": 5, "prefab": 2
    first_few: List[str]


def normalize_repo_rel(path: str) -> str:
    """
    Normalize a repository-relative path.
    - Backslash to slash
    - Trim whitespace
    - No leading slash
    """
    if not path:
        return ""
    p = path.strip().replace("\\", "/")
    if p.startswith("/"):
        p = p.lstrip("/")
    return p


def compute_move_mapping(old_rel: str, new_rel: str) -> Dict[str, str]:
    """
    Compute mapping for a move operation (file or folder).
    
    If old_rel is a file, returns specific mapping.
    If old_rel is a folder (conceptually), logic primarily relies on prefix matching
    during replacement, but this function establishes the primary intent mapping.
    
    In the context of refactoring, we usually generate a mapping dict that explicit 
    replacements check against or use prefix logic.
    
    For V2, we return a dict where:
    key: old_normalized_path_prefix
    value: new_normalized_path_prefix
    
    Currently simple 1:1, but expandable.
    """
    src = normalize_repo_rel(old_rel)
    dst = normalize_repo_rel(new_rel)
    if not src:
        return {}
    return {src: dst}


def _get_nested_value(obj: Dict[str, Any], path: str) -> Optional[str]:
    parts = path.split(".")
    curr: Any = obj
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return str(curr) if isinstance(curr, str) else None


def _set_nested_value(obj: Dict[str, Any], path: str, value: str) -> None:
    parts = path.split(".")
    curr = obj
    for i, p in enumerate(parts[:-1]):
        if p not in curr or not isinstance(curr[p], dict):
            # This shouldn't happen if we scanned correctly, but robust check
            return
        curr = curr[p]
    
    last = parts[-1]
    if last in curr:
        curr[last] = value


def scan_scene_references(scene_payload: Dict[str, Any]) -> List[AssetReference]:
    """Scan a scene dictionary for asset references."""
    refs = []
    
    entities = scene_payload.get("entities", [])
    # Sort entities for deterministic scanning order
    sorted_entities = sorted(entities, key=lambda e: e.get("id", ""))
    
    for entity in sorted_entities:
        eid = entity.get("id", "unknown")
        
        # Scan top-level fields
        for field in sorted(ASSET_PATH_FIELDS):
            val = entity.get(field)
            if isinstance(val, str) and val:
                refs.append(AssetReference(
                    entity_id=eid,
                    field_path=field,
                    value=normalize_repo_rel(val),
                    order_key=f"{eid}|{field}"
                ))
        
        # Scan nested fields
        for parent_field, child_fields in sorted(NESTED_ASSET_FIELDS.items()):
            parent_val = entity.get(parent_field)
            if isinstance(parent_val, dict):
                for child in sorted(child_fields):
                    child_val = parent_val.get(child)
                    if isinstance(child_val, str) and child_val:
                        full_field = f"{parent_field}.{child}"
                        refs.append(AssetReference(
                            entity_id=eid,
                            field_path=full_field,
                            value=normalize_repo_rel(child_val),
                            order_key=f"{eid}|{full_field}"
                        ))
                        
    return refs


def scan_prefab_references(prefab_payload: Dict[str, Any]) -> List[AssetReference]:
    """Scan a prefab dictionary for asset references."""
    # distinct from scene because prefab root is effectively an entity
    # but might also have children? For now, assume flat or single entity structure like scene
    # actually prefab payloads usually look like a single entity definition.
    
    refs = []
    # Prefabs often don't have an ID in the file itself until instantiated, 
    # or the root object is the entity.
    # We'll use "ROOT" as ID if missing.
    eid = prefab_payload.get("id", "ROOT")
    
    # Scan top-level fields
    for field in sorted(ASSET_PATH_FIELDS):
        val = prefab_payload.get(field)
        if isinstance(val, str) and val:
            refs.append(AssetReference(
                entity_id=eid,
                field_path=field,
                value=normalize_repo_rel(val),
                order_key=f"{eid}|{field}"
            ))
            
    # Scan nested fields
    for parent_field, child_fields in sorted(NESTED_ASSET_FIELDS.items()):
        parent_val = prefab_payload.get(parent_field)
        if isinstance(parent_val, dict):
            for child in sorted(child_fields):
                child_val = parent_val.get(child)
                if isinstance(child_val, str) and child_val:
                    full_field = f"{parent_field}.{child}"
                    refs.append(AssetReference(
                        entity_id=eid,
                        field_path=full_field,
                        value=normalize_repo_rel(child_val),
                        order_key=f"{eid}|{full_field}"
                    ))
                    
    return refs


def compute_replacements(refs: List[AssetReference], mapping: Dict[str, str]) -> List[Replacement]:
    """
    Compute replacements based on references and path mapping.
    Handles prefix matching for folder moves.
    """
    replacements = []
    
    # Sort mapping by length descending to match most specific paths first
    sorted_mapping = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)
    
    for ref in refs:
        # Check against mappings
        ref_val = ref.value
        
        match_found = False
        new_val = ""
        
        for old_prefix, new_prefix in sorted_mapping:
            # Exact match
            if ref_val == old_prefix:
                new_val = new_prefix
                match_found = True
                break
            # Prefix match (directory move)
            # Must match "dir/" to avoid partial filename matches like "hero" matching "hero_sprite"
            old_dir_prefix = old_prefix + "/"
            if ref_val.startswith(old_dir_prefix):
                suffix = ref_val[len(old_dir_prefix):]
                new_val = f"{new_prefix}/{suffix}"
                match_found = True
                break
        
        if match_found and new_val != ref_val:
            # Check if this change is redundant (e.g. somehow mapped to same) -> covered by new_val != ref_val
            replacements.append(Replacement(
                entity_id=ref.entity_id,
                field_path=ref.field_path,
                old_value=ref_val,
                new_value=new_val,
                order_key=ref.order_key
            ))
            
    # Deterministic sort
    return sorted(replacements, key=lambda r: r.order_key)


def apply_replacements(payload: Dict[str, Any], replacements: List[Replacement]) -> Dict[str, Any]:
    """
    Apply replacements to a payload immutably (deepcopy).
    Works for both Scene and Prefab payloads if structure matches.
    """
    new_payload = copy.deepcopy(payload)
    
    # Index entities by ID for fast cleanup if it's a scene
    # If it's a prefab (single dict), we treat new_payload as the entity
    
    is_scene = "entities" in new_payload and isinstance(new_payload["entities"], list)
    
    entity_map = {}
    if is_scene:
        for ent in new_payload["entities"]:
            if "id" in ent:
                entity_map[ent["id"]] = ent
    else:
        # Single entity prefab case
        eid = new_payload.get("id", "ROOT")
        entity_map[eid] = new_payload

    for rep in replacements:
        ent = entity_map.get(rep.entity_id)
        if ent:
            _set_nested_value(ent, rep.field_path, rep.new_value)
            
    return new_payload


def build_preview_summary(replacements: List[Replacement]) -> PreviewSummary:
    """Generate a summary of changes."""
    total = len(replacements)
    # We don't have file counts directly here since replacements are just for one payload context usually
    # But if we pass a list of ALL replacements across all files?
    # The signature implies we might pass replacements for a single file context 
    # OR we need to adjust to aggregate outside.
    # Let's assume this is for a collection of replacements.
    
    # Actually, for the global summary, the controller will aggregate.
    # This helper might be just for formatting or simple stats.
    
    # Let's return stats for this SET of replacements
    
    # We'll just list the first few changes as descriptions
    first_few = []
    for r in replacements[:3]:
        first_few.append(f"{r.entity_id}.{r.field_path}: {r.old_value} -> {r.new_value}")
    
    if total > 3:
        first_few.append(f"...and {total - 3} more")
        
    return PreviewSummary(
        total_files=0, # Context unaware
        total_refs=total,
        changes_by_kind={}, # Context unaware
        first_few=first_few
    )


def compute_rename_mapping(old_rel: str, new_rel: str) -> Dict[str, str]:
    """
    Compute mapping for a rename operation (file or folder).
    
    If old_rel is a folder, returns prefix mapping for it.
    Input paths should be repo-relative.
    """
    old_norm = normalize_repo_rel(old_rel)
    new_norm = normalize_repo_rel(new_rel)
    return {old_norm: new_norm}


def build_refactor_preview(
    mapping: Dict[str, str], 
    replacements: List[Replacement]
) -> PreviewSummary:
    """
    Build a rich preview summary for the UI.
    
    Args:
        mapping: The source->dest path mapping (files or folders)
        replacements: The calculated reference updates
        
    Returns:
        PreviewSummary with detailed stats.
    """
    total_files_renamed = len(mapping)
    total_refs = len(replacements)
    
    # Simple categorization
    changes_by_kind: Dict[str, int] = {}
    changes_by_kind["files_renamed"] = total_files_renamed
    changes_by_kind["references_updated"] = total_refs
    
    # Sort replacements for stable preview
    # Sort by entity_id, field_path
    sorted_repls = sorted(replacements, key=lambda r: (r.entity_id, r.field_path))
    
    preview_lines = []
    MAX_LINES = 10
    
    for r in sorted_repls:
        # Truncate values
        orig = r.old_value if len(r.old_value) < 30 else "..." + r.old_value[-27:]
        newv = r.new_value if len(r.new_value) < 30 else "..." + r.new_value[-27:]
        line = f"[{r.entity_id}] {r.field_path}: {orig} -> {newv}"
        preview_lines.append(line)
        if len(preview_lines) >= MAX_LINES:
            break
            
    return PreviewSummary(
        total_files=total_files_renamed,
        total_refs=total_refs,
        changes_by_kind=changes_by_kind,
        first_few=preview_lines
    )


def format_preview_lines(summary: PreviewSummary, max_lines: int = 40) -> List[str]:
    """Format the preview summary into a list of strings for the modal."""
    lines = []
    
    lines.append(f"Renaming {summary.total_files} file(s/folders).")
    lines.append(f"Updating {summary.total_refs} references.")
    lines.append("-" * 40)
    
    if summary.total_refs == 0:
        lines.append("No references found to update.")
        return lines

    lines.append("Preview changes:")
    count = 0
    for line in summary.first_few:
        lines.append(f"  {line}")
        count += 1
        
    remaining = summary.total_refs - count
    if remaining > 0:
        lines.append(f"  ...and {remaining} more references.")
        
    return lines
