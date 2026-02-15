"""Pure model helpers for safe asset rename with scene reference updates.

Provides deterministic functions for:
- Computing new relative paths from rename
- Finding asset references in scene payloads
- Computing and applying reference replacements
- Formatting undo labels
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

__all__ = [
    "compute_rename_paths",
    "find_scene_asset_references",
    "compute_reference_replacements",
    "apply_reference_replacements",
    "format_rename_undo_label",
    "AssetReference",
    "Replacement",
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
    """A reference to an asset found in a scene entity."""

    entity_id: str
    field_path: str  # e.g., "sprite" or "sprite_sheet.image"
    value: str


@dataclass(frozen=True, slots=True)
class Replacement:
    """A replacement to apply to a scene entity."""

    entity_id: str
    field_path: str
    old_value: str
    new_value: str


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison (forward slashes, stripped)."""
    if not path:
        return ""
    return path.strip().replace("\\", "/")


def compute_rename_paths(old_path: str, new_name: str) -> tuple[str, str]:
    """Compute old and new relative paths from a rename.

    Args:
        old_path: The current relative path (e.g., "assets/sprites/hero.png").
        new_name: The new filename only (e.g., "player.png").

    Returns:
        Tuple of (old_rel, new_rel) normalized paths.

    Deterministic: same inputs always produce same output.
    """
    old_rel = _normalize_path(old_path)
    new_name_clean = new_name.strip() if new_name else ""

    if not old_rel or not new_name_clean:
        return (old_rel, "")

    # Extract directory from old path
    if "/" in old_rel:
        directory = old_rel.rsplit("/", 1)[0]
        new_rel = f"{directory}/{new_name_clean}"
    else:
        new_rel = new_name_clean

    return (old_rel, _normalize_path(new_rel))


def find_scene_asset_references(scene_payload: dict[str, Any] | None) -> list[AssetReference]:
    """Find all asset path references in a scene payload.

    Scans entities deterministically (sorted by entity_id) and returns
    references to known asset path fields.

    Args:
        scene_payload: The scene data dict with "entities" list.

    Returns:
        List of AssetReference objects in deterministic order.

    Deterministic: same inputs always produce same output.
    """
    if not isinstance(scene_payload, dict):
        return []

    entities = scene_payload.get("entities")
    if not isinstance(entities, list):
        return []

    references: list[AssetReference] = []

    # Sort entities by ID for deterministic ordering
    def get_entity_id(ent: Any) -> str:
        if not isinstance(ent, dict):
            return ""
        return str(ent.get("id") or ent.get("mesh_name") or ent.get("name") or "")

    sorted_entities = sorted(
        [e for e in entities if isinstance(e, dict)],
        key=get_entity_id,
    )

    for entity in sorted_entities:
        entity_id = get_entity_id(entity)
        if not entity_id:
            continue

        # Check top-level asset fields
        for field in sorted(ASSET_PATH_FIELDS):
            value = entity.get(field)
            if isinstance(value, str) and value.strip():
                references.append(AssetReference(
                    entity_id=entity_id,
                    field_path=field,
                    value=_normalize_path(value),
                ))

        # Check nested asset fields
        for parent_field, child_fields in sorted(NESTED_ASSET_FIELDS.items()):
            nested = entity.get(parent_field)
            if not isinstance(nested, dict):
                continue
            for child_field in sorted(child_fields):
                value = nested.get(child_field)
                if isinstance(value, str) and value.strip():
                    references.append(AssetReference(
                        entity_id=entity_id,
                        field_path=f"{parent_field}.{child_field}",
                        value=_normalize_path(value),
                    ))

    return references


def compute_reference_replacements(
    scene_payload: dict[str, Any] | None,
    old_rel: str,
    new_rel: str,
) -> list[Replacement]:
    """Compute replacements needed to update asset references.

    Args:
        scene_payload: The scene data dict.
        old_rel: The old normalized relative path.
        new_rel: The new normalized relative path.

    Returns:
        List of Replacement objects for references that match old_rel.

    Deterministic: same inputs always produce same output.
    """
    if not old_rel or not new_rel or old_rel == new_rel:
        return []

    old_norm = _normalize_path(old_rel)
    new_norm = _normalize_path(new_rel)

    references = find_scene_asset_references(scene_payload)
    replacements: list[Replacement] = []

    for ref in references:
        if ref.value == old_norm:
            replacements.append(Replacement(
                entity_id=ref.entity_id,
                field_path=ref.field_path,
                old_value=ref.value,
                new_value=new_norm,
            ))

    return replacements


def apply_reference_replacements(
    scene_payload: dict[str, Any] | None,
    replacements: list[Replacement],
) -> dict[str, Any]:
    """Apply replacements to a scene payload, returning a new payload.

    This is a pure function - the original payload is not modified.

    Args:
        scene_payload: The original scene data dict.
        replacements: List of replacements to apply.

    Returns:
        A new scene payload dict with replacements applied.

    Deterministic: same inputs always produce same output.
    """
    if not isinstance(scene_payload, dict):
        return {}

    if not replacements:
        return copy.deepcopy(scene_payload)

    # Deep copy to avoid mutation
    new_payload = copy.deepcopy(scene_payload)

    entities = new_payload.get("entities")
    if not isinstance(entities, list):
        return new_payload

    # Build lookup for entity by ID
    entity_by_id: dict[str, dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        eid = str(entity.get("id") or entity.get("mesh_name") or entity.get("name") or "")
        if eid:
            entity_by_id[eid] = entity

    # Apply replacements
    for replacement in replacements:
        entity = entity_by_id.get(replacement.entity_id)
        if entity is None:
            continue

        field_path = replacement.field_path
        if "." in field_path:
            # Nested field (e.g., "sprite_sheet.image")
            parent_field, child_field = field_path.split(".", 1)
            nested = entity.get(parent_field)
            if isinstance(nested, dict):
                current = nested.get(child_field)
                if current == replacement.old_value:
                    nested[child_field] = replacement.new_value
        else:
            # Top-level field
            current = entity.get(field_path)
            if current == replacement.old_value:
                entity[field_path] = replacement.new_value

    return new_payload


def format_rename_undo_label(old_rel: str, new_rel: str, n_refs: int) -> str:
    """Format an undo label for a rename operation.

    Args:
        old_rel: The old relative path.
        new_rel: The new relative path.
        n_refs: Number of references updated.

    Returns:
        A descriptive undo label string.

    Deterministic: same inputs always produce same output.
    """
    old_name = old_rel.rsplit("/", 1)[-1] if "/" in old_rel else old_rel
    new_name = new_rel.rsplit("/", 1)[-1] if "/" in new_rel else new_rel

    if n_refs == 0:
        return f"Rename {old_name} → {new_name}"
    elif n_refs == 1:
        return f"Rename {old_name} → {new_name} (1 ref)"
    else:
        return f"Rename {old_name} → {new_name} ({n_refs} refs)"
