"""
SavedEntityState - Minimal entity state for save/restore.

This module provides:
- SavedEntityState dataclass for serializing entity transform/state
- serialize_entities() to capture current entity state from a scene
- apply_entities() to restore entity state onto existing entities
- Migration support via save_schema_version

Design principles:
- Minimal: Only persist what's needed for meaningful restore
- Safe defaults: Missing fields use sensible defaults
- Extensible: Unknown fields preserved under x_ namespace
- Deterministic: Output is sorted and stable for hashing
- Observable: Serialization/restore errors are captured, never silenced
"""
from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass, field
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.log_utils import normalize_path


class SaveSerializationError(Exception):
    """Raised in strict mode when behaviour state serialization fails."""


# Schema version for entity state serialization
ENTITY_STATE_SCHEMA_VERSION = 1


def _diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str,
    hint: str | None = None,
    context_extra: dict[str, Any] | None = None,
) -> Diagnostic:
    context: dict[str, Any] = {
        "source": normalize_path(source),
        "pointer": pointer,
    }
    if context_extra:
        for key in sorted(context_extra.keys()):
            context[str(key)] = context_extra[key]
    return Diagnostic(
        level=level,
        code=code,
        message=str(message),
        context=context,
        hint=hint,
    )


def _append_diagnostic(
    diagnostics: list[Diagnostic] | None,
    diagnostic: Diagnostic,
) -> None:
    if diagnostics is not None:
        diagnostics.append(diagnostic)


def _coerce_non_strict_level(diag: Diagnostic, *, strict: bool) -> Diagnostic:
    if strict or diag.level != DiagnosticLevel.ERROR:
        return diag
    return Diagnostic(
        level=DiagnosticLevel.WARN,
        code=diag.code,
        message=diag.message,
        context=dict(diag.context),
        hint=diag.hint,
    )


@dataclass
class SavedEntityState:
    """Minimal entity state for persistence.
    
    Fields:
        entity_id: Unique identifier for this entity (mesh_name)
        prefab_id: Optional prefab template this entity was spawned from
        x: World X position
        y: World Y position
        tags: List of string tags (e.g. ["player", "friendly"])
        animation_state: Current animation name if applicable
        behaviour_state: Safe namespace dict for behaviour-specific state
        x_extra: Extension fields for forward compatibility
    """
    entity_id: str
    prefab_id: str | None = None
    x: float = 0.0
    y: float = 0.0
    tags: list[str] = field(default_factory=list)
    animation_state: str | None = None
    behaviour_state: dict[str, Any] = field(default_factory=dict)
    x_extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        result: dict[str, Any] = {
            "entity_id": self.entity_id,
            "x": float(self.x),
            "y": float(self.y),
        }
        
        if self.prefab_id:
            result["prefab_id"] = self.prefab_id
        
        if self.tags:
            result["tags"] = sorted(list(self.tags))
        
        if self.animation_state:
            result["animation_state"] = self.animation_state
        
        if self.behaviour_state:
            # Only include non-empty behaviour state
            clean_behaviour = {
                k: v for k, v in sorted(self.behaviour_state.items())
                if v is not None
            }
            if clean_behaviour:
                result["behaviour_state"] = clean_behaviour
        
        # Preserve unknown fields under x_ namespace
        if self.x_extra:
            for k, v in sorted(self.x_extra.items()):
                if k.startswith("x_"):
                    result[k] = v
        
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SavedEntityState":
        """Deserialize from dict with safe defaults."""
        if not isinstance(data, dict):
            return cls(entity_id="unknown")
        
        entity_id = str(data.get("entity_id", "") or "").strip()
        if not entity_id:
            entity_id = str(data.get("id", "") or "").strip() or "unknown"
        
        prefab_id = data.get("prefab_id")
        if prefab_id is not None:
            prefab_id = str(prefab_id).strip() or None
        
        try:
            x = float(data.get("x", 0.0))
        except (TypeError, ValueError):
            x = 0.0
        
        try:
            y = float(data.get("y", 0.0))
        except (TypeError, ValueError):
            y = 0.0
        
        tags_raw = data.get("tags", [])
        tags: list[str] = []
        if isinstance(tags_raw, list):
            for t in tags_raw:
                tag_str = str(t or "").strip()
                if tag_str:
                    tags.append(tag_str)
        elif isinstance(tags_raw, str):
            tag_str = tags_raw.strip()
            if tag_str:
                tags.append(tag_str)
        
        animation_state = data.get("animation_state")
        if animation_state is not None:
            animation_state = str(animation_state).strip() or None
        
        behaviour_state_raw = data.get("behaviour_state", {})
        behaviour_state: dict[str, Any] = {}
        if isinstance(behaviour_state_raw, dict):
            behaviour_state = dict(behaviour_state_raw)
        
        # Collect x_ extension fields
        x_extra: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and k.startswith("x_"):
                x_extra[k] = v
        
        return cls(
            entity_id=entity_id,
            prefab_id=prefab_id,
            x=x,
            y=y,
            tags=tags,
            animation_state=animation_state,
            behaviour_state=behaviour_state,
            x_extra=x_extra,
        )


def serialize_entity(
    sprite: Any,
    *,
    errors: list[str] | None = None,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
) -> SavedEntityState | None:
    """Extract SavedEntityState from a sprite/entity.
    
    Args:
        sprite: An entity sprite with mesh_* attributes
        errors: Optional list to collect warning strings for failed behaviours.
        strict: If True, raise SaveSerializationError on any failure.
        
    Returns:
        SavedEntityState or None if entity has no valid ID
    """
    entity_id = getattr(sprite, "mesh_name", None)
    if not isinstance(entity_id, str) or not entity_id.strip():
        # Try entity data dict
        entity_data = getattr(sprite, "mesh_entity_data", {})
        if isinstance(entity_data, dict):
            entity_id = entity_data.get("id") or entity_data.get("name")
        if not isinstance(entity_id, str) or not entity_id.strip():
            return None
    
    entity_id = entity_id.strip()
    
    # Get prefab ID
    prefab_id = None
    entity_data = getattr(sprite, "mesh_entity_data", {})
    if isinstance(entity_data, dict):
        prefab_id = entity_data.get("prefab_id")
        if prefab_id is not None:
            prefab_id = str(prefab_id).strip() or None
    
    # Get position
    try:
        x = float(getattr(sprite, "center_x", 0.0))
    except (TypeError, ValueError):
        x = 0.0
    
    try:
        y = float(getattr(sprite, "center_y", 0.0))
    except (TypeError, ValueError):
        y = 0.0
    
    # Get tags
    tags: list[str] = []
    mesh_tag = getattr(sprite, "mesh_tag", None)
    if isinstance(mesh_tag, str) and mesh_tag.strip():
        tags.append(mesh_tag.strip())
    mesh_tags = getattr(sprite, "mesh_tags", None)
    if isinstance(mesh_tags, (list, tuple)):
        for t in mesh_tags:
            tag_str = str(t or "").strip()
            if tag_str and tag_str not in tags:
                tags.append(tag_str)
    
    # Get animation state
    animation_state = None
    animator = getattr(sprite, "mesh_animator", None)
    if animator is not None:
        current_anim = getattr(animator, "current_animation", None)
        if isinstance(current_anim, str) and current_anim.strip():
            animation_state = current_anim.strip()
    
    # Get safe behaviour state
    behaviour_state: dict[str, Any] = {}
    behaviours_runtime = getattr(sprite, "mesh_behaviours_runtime", [])
    if isinstance(behaviours_runtime, list):
        for behaviour in behaviours_runtime:
            # Only serialize if behaviour has a saveable_state() method
            if hasattr(behaviour, "saveable_state") and callable(behaviour.saveable_state):
                behaviour_name = behaviour.__class__.__name__
                try:
                    bstate = behaviour.saveable_state()
                    if isinstance(bstate, dict) and bstate:
                        behaviour_state[behaviour_name] = bstate
                except Exception as exc:
                    msg = (
                        f"saveable_state() failed for {behaviour_name} "
                        f"on entity '{entity_id}': {exc}"
                    )
                    sys.stderr.write(f"[Mesh][Save] WARNING: {msg}\n")
                    _append_diagnostic(
                        diagnostics,
                        _diagnostic(
                            level=DiagnosticLevel.WARN,
                            code="save.serialize.behaviour_state_failed",
                            message=msg,
                            source=source,
                            pointer=f"/saved_entities/entities/{entity_id}/behaviour_state/{behaviour_name}",
                            hint="Fix behaviour saveable_state() or run strict mode to fail fast.",
                        ),
                    )
                    if errors is not None:
                        errors.append(msg)
                    if strict:
                        raise SaveSerializationError(msg) from exc
    
    return SavedEntityState(
        entity_id=entity_id,
        prefab_id=prefab_id,
        x=x,
        y=y,
        tags=sorted(tags),
        animation_state=animation_state,
        behaviour_state=behaviour_state,
    )


def serialize_entities(
    scene_controller: Any,
    *,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
) -> list[dict[str, Any]]:
    """Serialize all entities from a scene controller.
    
    Args:
        scene_controller: SceneController or similar with all_sprites
        strict: If True, raise SaveSerializationError on any failure.
        
    Returns:
        List of entity state dicts, sorted by entity_id for determinism.
        Any serialization warnings are written to stderr.
    """
    sprites = getattr(scene_controller, "all_sprites", [])
    if not sprites:
        return []
    
    errors: list[str] = []
    states: list[SavedEntityState] = []
    for sprite in sprites:
        state = serialize_entity(
            sprite,
            errors=errors,
            strict=strict,
            diagnostics=diagnostics,
            source=source,
        )
        if state is not None:
            states.append(state)
    
    # Sort by entity_id for deterministic output
    states.sort(key=lambda s: s.entity_id)
    
    return [s.to_dict() for s in states]


def _invoke_restore_state(
    behaviour: Any,
    payload: dict[str, Any],
    *,
    strict: bool,
    source: str,
) -> None:
    restore = getattr(behaviour, "restore_state", None)
    if not callable(restore):
        return
    try:
        signature = inspect.signature(restore)
        has_strict = "strict" in signature.parameters
        has_source = "source" in signature.parameters
    except (TypeError, ValueError):
        has_strict = False
        has_source = False
    if has_strict:
        kwargs: dict[str, Any] = {"strict": bool(strict)}
        if has_source:
            kwargs["source"] = source
        restore(payload, **kwargs)
        return
    restore(payload)


def apply_entity_state(
    sprite: Any,
    state: SavedEntityState,
    *,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
) -> bool:
    """Apply saved state to an existing entity.
    
    Args:
        sprite: Target entity sprite
        state: SavedEntityState to apply
        
    Returns:
        True if state was applied, False on error
    """
    try:
        # Apply position
        sprite.center_x = float(state.x)
        sprite.center_y = float(state.y)
        
        # Update entity data dict
        entity_data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            entity_data["x"] = float(state.x)
            entity_data["y"] = float(state.y)
        
        # Apply tags
        if state.tags:
            # Set primary tag
            if hasattr(sprite, "mesh_tag"):
                sprite.mesh_tag = state.tags[0] if state.tags else None
            # Set all tags
            if hasattr(sprite, "mesh_tags"):
                sprite.mesh_tags = list(state.tags)
        
        # Apply animation state
        if state.animation_state:
            animator = getattr(sprite, "mesh_animator", None)
            if animator is not None and hasattr(animator, "play"):
                try:
                    animator.play(state.animation_state)
                except Exception as exc:
                    msg = (
                        f"animator.play('{state.animation_state}') "
                        f"failed for entity '{state.entity_id}': {exc}"
                    )
                    sys.stderr.write(f"[Mesh][Save] WARNING: {msg}\n")
                    _append_diagnostic(
                        diagnostics,
                        _diagnostic(
                            level=DiagnosticLevel.WARN,
                            code="save.restore.animation_failed",
                            message=msg,
                            source=source,
                            pointer=f"/saved_entities/entities/{state.entity_id}/animation_state",
                            hint="Verify animation id exists for this entity animator.",
                        ),
                    )
                    if strict:
                        return False
        
        # Apply behaviour state
        if state.behaviour_state:
            behaviours_runtime = getattr(sprite, "mesh_behaviours_runtime", [])
            if isinstance(behaviours_runtime, list):
                for behaviour in behaviours_runtime:
                    behaviour_name = behaviour.__class__.__name__
                    bstate = state.behaviour_state.get(behaviour_name)
                    if bstate and hasattr(behaviour, "restore_state") and callable(behaviour.restore_state):
                        try:
                            _invoke_restore_state(
                                behaviour,
                                bstate,
                                strict=bool(strict),
                                source=f"{source}/{state.entity_id}/{behaviour_name}",
                            )
                            restore_diags = getattr(behaviour, "_last_restore_diagnostics", ())
                            if isinstance(restore_diags, (list, tuple)):
                                for diag in restore_diags:
                                    if isinstance(diag, Diagnostic):
                                        _append_diagnostic(
                                            diagnostics,
                                            _coerce_non_strict_level(diag, strict=bool(strict)),
                                        )
                        except Exception as exc:
                            msg = (
                                "restore_state() failed for "
                                f"{behaviour_name} on entity '{state.entity_id}': {exc}"
                            )
                            sys.stderr.write(f"[Mesh][Save] WARNING: {msg}\n")
                            _append_diagnostic(
                                diagnostics,
                                _diagnostic(
                                    level=(DiagnosticLevel.ERROR if strict else DiagnosticLevel.WARN),
                                    code="save.restore.behaviour_state_failed",
                                    message=msg,
                                    source=source,
                                    pointer=f"/saved_entities/entities/{state.entity_id}/behaviour_state/{behaviour_name}",
                                    hint="Ensure restore_state payload matches current wrapper schema.",
                                ),
                            )
                            if strict:
                                return False

        return True
    except Exception as exc:
        msg = f"apply_entity_state failed for entity '{state.entity_id}': {exc}"
        sys.stderr.write(f"[Mesh][Save] WARNING: {msg}\n")
        _append_diagnostic(
            diagnostics,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.entity_apply_failed",
                message=msg,
                source=source,
                pointer=f"/saved_entities/entities/{state.entity_id}",
                hint="Inspect entity transform/behaviour restore hooks.",
            ),
        )
        return False


def apply_entities(
    scene_controller: Any,
    saved_entities: list[dict[str, Any]],
    *,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
) -> tuple[int, int]:
    """Apply saved entity states to matching entities in scene.
    
    Args:
        scene_controller: SceneController with all_sprites and entity lookup
        saved_entities: List of entity state dicts from serialize_entities()
        
    Returns:
        Tuple of (applied_count, missing_count)
    """
    if not saved_entities:
        return (0, 0)
    
    # Build lookup for existing entities
    sprites = getattr(scene_controller, "all_sprites", [])
    sprite_by_id: dict[str, Any] = {}
    for sprite in sprites:
        entity_id = getattr(sprite, "mesh_name", None)
        if isinstance(entity_id, str) and entity_id.strip():
            sprite_by_id[entity_id.strip()] = sprite
    
    applied = 0
    missing = 0
    
    for entity_dict in saved_entities:
        state = SavedEntityState.from_dict(entity_dict)
        sprite = sprite_by_id.get(state.entity_id)
        
        if sprite is None:
            missing += 1
            _append_diagnostic(
                diagnostics,
                _diagnostic(
                    level=DiagnosticLevel.WARN,
                    code="save.restore.entity_missing",
                    message=f"Saved entity '{state.entity_id}' not present in scene.",
                    source=source,
                    pointer=f"/saved_entities/entities/{state.entity_id}",
                    hint="Entity ids must stay stable between save and restore scenes.",
                ),
            )
            continue

        if apply_entity_state(
            sprite,
            state,
            strict=bool(strict),
            diagnostics=diagnostics,
            source=source,
        ):
            applied += 1
        else:
            missing += 1
    
    return (applied, missing)


def migrate_entity_state_v0(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate v0 entity state (no schema_version) to v1.
    
    v0 may have:
    - "id" instead of "entity_id"
    - "tag" instead of "tags"
    - Missing behaviour_state
    """
    # Normalize entity_id
    if "entity_id" not in data and "id" in data:
        data["entity_id"] = data.pop("id")
    
    # Normalize tags
    if "tags" not in data and "tag" in data:
        tag = data.pop("tag")
        if isinstance(tag, str) and tag.strip():
            data["tags"] = [tag.strip()]
    
    # Ensure behaviour_state exists
    if "behaviour_state" not in data:
        data["behaviour_state"] = {}
    
    return data
