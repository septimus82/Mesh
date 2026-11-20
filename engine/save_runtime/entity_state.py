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

import functools
import hashlib
import inspect
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.log_utils import normalize_path


class SaveSerializationError(Exception):
    """Raised in strict mode when behaviour state serialization fails."""


# Schema version for entity state serialization (2: records are keyed by authored id or, id-less, by name; B-01)
ENTITY_STATE_SCHEMA_VERSION = 2

KEYING_ID = "id"      # the sprite has an authored id: the record is bound by it (``mesh_id`` + ``occurrence``)
KEYING_NAME = "name"  # the sprite has no id (projectile, hitbox, console spawn): bound by name, then by position
POSITION_EPS = 0.01   # two places are "the same" when both coordinates differ by at most this

# What a restore says about identity. A load applies the records twice (to the room being left, then to the saved room
# once it exists): only the second, authoritative report is kept in the load attempt's diagnostics.
IDENTITY_DIAGNOSTIC_CODES = frozenset({
    "save.restore.entity_id_ambiguous",
    "save.restore.entity_legacy_ambiguous",
    "save.restore.entity_nameclash",
    "save.restore.entities_unbound",
    "save.restore.entities_unresolved",
    "save.restore.entities_wrong_room",
    "save.restore.primary_tag_guessed",
})


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
        keying: "id" (authored id: see mesh_id/occurrence), "name" (id-less sprite) or None (a v2-era record)
        mesh_id: the authored id of an id-keyed record
        occurrence: 0-based rank of the sprite among the live sprites sharing its authored id
        primary_tag: the sprite's primary tag (``mesh_tag``); ``tags`` is sorted so cannot say which one it was (B-02)
    """
    entity_id: str
    prefab_id: str | None = None
    x: float = 0.0
    y: float = 0.0
    tags: list[str] = field(default_factory=list)
    animation_state: str | None = None
    behaviour_state: dict[str, Any] = field(default_factory=dict)
    x_extra: dict[str, Any] = field(default_factory=dict)
    keying: str | None = None
    mesh_id: str | None = None
    occurrence: int = 0
    primary_tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        result: dict[str, Any] = {
            "entity_id": self.entity_id,
            "x": float(self.x),
            "y": float(self.y),
        }

        if self.keying:
            result["keying"] = self.keying
        if self.keying == KEYING_ID and self.mesh_id:
            result["mesh_id"] = self.mesh_id
            result["occurrence"] = int(self.occurrence)

        if self.prefab_id:
            result["prefab_id"] = self.prefab_id

        if self.tags:
            result["tags"] = sorted(list(self.tags))

        if self.primary_tag:
            result["primary_tag"] = self.primary_tag

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

        keying = data.get("keying")
        keying = keying if keying in (KEYING_ID, KEYING_NAME) else None
        mesh_id = data.get("mesh_id")
        mesh_id = mesh_id.strip() if isinstance(mesh_id, str) and mesh_id.strip() else None
        try:
            occurrence = max(0, int(data.get("occurrence", 0)))
        except (TypeError, ValueError):
            occurrence = 0

        primary_tag = data.get("primary_tag")
        primary_tag = primary_tag.strip() if isinstance(primary_tag, str) and primary_tag.strip() else None

        return cls(
            entity_id=entity_id,
            prefab_id=prefab_id,
            x=x,
            y=y,
            tags=tags,
            animation_state=animation_state,
            behaviour_state=behaviour_state,
            x_extra=x_extra,
            keying=keying,
            mesh_id=mesh_id,
            occurrence=occurrence,
            primary_tag=primary_tag,
        )


def _sprite_mesh_id(sprite: Any) -> str | None:
    """The sprite's authored id (``mesh_id``, from the scene file's ``id``), or None for an id-less sprite."""
    value = getattr(sprite, "mesh_id", None)
    if not isinstance(value, str) or not value.strip():
        data = getattr(sprite, "mesh_entity_data", None)
        value = data.get("id") if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _sprite_name(sprite: Any) -> str | None:
    value = getattr(sprite, "mesh_name", None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _sprite_xy(sprite: Any) -> tuple[float, float]:
    try:
        return float(getattr(sprite, "center_x", 0.0)), float(getattr(sprite, "center_y", 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def record_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """A total order for saved entity records, independent of sprite order: (keying, mesh_id, entity_id, x, y,
    occurrence). Duplicate names or ids no longer tie."""
    try:
        occurrence = int(record.get("occurrence", 0))
    except (TypeError, ValueError):
        occurrence = 0
    return (str(record.get("keying") or ""), str(record.get("mesh_id") or ""),
            str(record.get("entity_id") or record.get("id") or ""), _float(record.get("x")), _float(record.get("y")),
            occurrence)


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
    primary_tag: str | None = None
    if isinstance(mesh_tag, str) and mesh_tag.strip():
        primary_tag = mesh_tag.strip()
        tags.append(primary_tag)
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

    mesh_id = _sprite_mesh_id(sprite)
    return SavedEntityState(
        entity_id=entity_id,
        prefab_id=prefab_id,
        x=x,
        y=y,
        tags=sorted(tags),
        animation_state=animation_state,
        behaviour_state=behaviour_state,
        keying=KEYING_ID if mesh_id else KEYING_NAME,
        mesh_id=mesh_id,
        primary_tag=primary_tag,
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
    seen: dict[str, int] = {}
    for sprite in sprites:
        state = serialize_entity(
            sprite,
            errors=errors,
            strict=strict,
            diagnostics=diagnostics,
            source=source,
        )
        if state is None:
            continue
        if state.keying == KEYING_ID and state.mesh_id:
            state.occurrence = seen.get(state.mesh_id, 0)  # rank among the live sprites with this id
            seen[state.mesh_id] = state.occurrence + 1
        states.append(state)

    for mesh_id, count in sorted(seen.items()):
        if count > 1:  # every one is still written (occurrence 0..k-1): a clone or hand edit must not cost a save
            msg = f"{count} entities share the authored id '{mesh_id}'; all are saved, bound by order and position."
            sys.stderr.write(f"[Mesh][Save] WARNING: {msg}\n")
            _append_diagnostic(
                diagnostics,
                _diagnostic(
                    level=DiagnosticLevel.WARN,
                    code="save.serialize.entity_id_duplicate",
                    message=msg,
                    source=source,
                    pointer=f"/saved_entities/entities/{mesh_id}",
                    context_extra={"id": mesh_id, "count": count},
                    hint="Give each entity its own id (the scene linter can rename duplicates).",
                ),
            )

    records = [s.to_dict() for s in states]
    records.sort(key=record_sort_key)  # a total order: the output doesn't depend on sprite order
    return records


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
                if state.primary_tag:
                    sprite.mesh_tag = state.primary_tag
                elif getattr(sprite, "mesh_tag", None) not in state.tags:
                    # no recorded primary and the live one isn't a saved tag: sorted order is a guess (B-02)
                    sprite.mesh_tag = state.tags[0]
                    _append_diagnostic(
                        diagnostics,
                        _diagnostic(
                            level=DiagnosticLevel.WARN,
                            code="save.restore.primary_tag_guessed",
                            message=(
                                f"Entity '{state.entity_id}' has no recorded primary tag; "
                                f"used '{state.tags[0]}' (first saved tag)."
                            ),
                            source=source,
                            pointer=f"/saved_entities/entities/{state.entity_id}/tags",
                            hint="Save again to record the primary tag.",
                        ),
                    )
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


@dataclass
class EntityApplyResult:
    """What one restore of saved entity records did (see ``apply_entities_ex``)."""

    applied: int = 0
    missing: int = 0  # records whose entity is absent (an expired projectile, a removed id): as before, tolerated
    unbound: int = 0  # records of this load refused because their identity was not provable: now unresolved
    retried: int = 0  # carried unresolved records that bound this time
    unresolved: list[dict[str, Any]] = field(default_factory=list)  # every entry still unresolved after this load
    skipped_wrong_room: bool = False


@dataclass
class PendingSavedEntities:
    """A loaded save's entity records waiting for the saved room to exist (``scene_controller._pending_saved_entities``)."""

    records: list[dict[str, Any]]
    scene_path: str = ""
    snapshot: list[dict[str, Any]] | None = None
    carried: list[dict[str, Any]] = field(default_factory=list)
    first_seen: str = ""
    source: str = "save_runtime/entity_state"
    on_done: Callable[[EntityApplyResult, list[Diagnostic]], None] | None = None


# ---- unresolved records: kept (never discarded) until they bind or a developer edits the save -----------------------

_HELD_ATTR = "_saved_entities_unresolved"


def _record_digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def unresolved_entry(record: dict[str, Any], reason: str, scene_path: str, first_seen: str) -> dict[str, Any]:
    return {"first_seen": first_seen, "reason": reason, "record": record, "scene_path": scene_path}


def _entry_key(entry: dict[str, Any]) -> tuple[str, str]:
    record = entry.get("record")
    return (str(entry.get("scene_path") or ""), _record_digest(record if isinstance(record, dict) else {}))


def merge_unresolved(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every entry once, deduplicated by (scene_path, SHA-256 of the record), the first seen kept verbatim."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        for entry in group:
            if isinstance(entry, dict) and isinstance(entry.get("record"), dict):
                seen.setdefault(_entry_key(entry), entry)
    return [seen[key] for key in sorted(seen)]


def _session(controller: Any) -> Any:
    from engine.scene_runtime import room_memory  # noqa: PLC0415

    return room_memory.session(getattr(controller, "window", None))


def hold_unresolved(controller: Any, entries: list[dict[str, Any]]) -> None:
    """Keep the unresolved records with this game session: every later save writes them back."""
    setattr(controller, _HELD_ATTR, (_session(controller), merge_unresolved(entries)))


def held_unresolved(controller: Any) -> list[dict[str, Any]]:
    """The unresolved records of the game now (none after a new game: they belonged to the old one)."""
    held = getattr(controller, _HELD_ATTR, None)
    if isinstance(held, tuple) and len(held) == 2 and held[0] is _session(controller):
        return list(held[1])
    return []


def serialize_saved_entities(
    scene_controller: Any,
    *,
    room: str | None = None,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
) -> dict[str, Any]:
    """The v3 ``saved_entities`` block: the records, the room they belong to, counts and the unresolved records."""
    records = serialize_entities(scene_controller, strict=strict, diagnostics=diagnostics, source=source)
    by_keying = {KEYING_ID: 0, KEYING_NAME: 0}
    for record in records:
        by_keying[str(record.get("keying") or KEYING_NAME)] += 1
    return {
        "schema_version": ENTITY_STATE_SCHEMA_VERSION,
        "entities": records,
        "counters": by_keying,
        "scene_path": str(room or ""),
        "unresolved": held_unresolved(scene_controller),
    }


# ---- binding ---------------------------------------------------------------------------------------------------


def _near(ax: float, ay: float, bx: float, by: float) -> bool:
    return abs(ax - bx) <= POSITION_EPS and abs(ay - by) <= POSITION_EPS


def _snapshot_positions(snapshot: list[dict[str, Any]] | None) -> dict[str, list[tuple[float, float]]] | None:
    """The save's own scene snapshot (id + place of the same instant) by id; None when there is none to check."""
    if snapshot is None:
        return None
    out: dict[str, list[tuple[float, float]]] = {}
    for item in snapshot:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            out.setdefault(item["id"], []).append((_float(item.get("x")), _float(item.get("y"))))
    return out


_Item = tuple[dict[str, Any], SavedEntityState]


def _bind_by_position(
    items: list[_Item],
    sprites: list[Any],
    check: Callable[[_Item, Any], bool] | None,
) -> tuple[list[tuple[_Item, Any]], list[_Item]]:
    """Bind a record to a sprite only when the pairing is provably unique: the record's place is exactly one sprite's
    place, and no other record of the group claims that sprite."""
    candidates: list[list[int]] = []
    for _raw, state in items:
        candidates.append([j for j, s in enumerate(sprites)
                           if _near(state.x, state.y, *_sprite_xy(s)) and (check is None or check((_raw, state), s))])
    claimed_by: dict[int, int] = {}
    for found in candidates:
        for j in found:
            claimed_by[j] = claimed_by.get(j, 0) + 1
    pairs: list[tuple[_Item, Any]] = []
    unbound: list[_Item] = []
    for item, found in zip(items, candidates):
        if len(found) == 1 and claimed_by[found[0]] == 1:
            pairs.append((item, sprites[found[0]]))
        else:
            unbound.append(item)
    return pairs, unbound


def _bind_group(
    items: list[_Item],
    sprites: list[Any],
    *,
    by_id: bool,
    name_only_ok: bool,
    check: Callable[[_Item, Any], bool] | None,
) -> tuple[list[tuple[_Item, Any]], list[tuple[_Item, str]], list[_Item]]:
    """One id or one name: (pairs to apply, (refused record, why), records whose entity is absent)."""
    if not sprites:
        return [], [], list(items)
    count, live = len(items), len(sprites)
    if by_id:
        items = sorted(items, key=lambda it: it[1].occurrence)
        if count == live == 1:
            return [(items[0], sprites[0])], [], []
        if count != live:
            return [], [(it, "count_mismatch") for it in items], []
        # Twins of one id: occurrence is output order only, never identity. A record binds to the one twin standing
        # exactly at its place, and only if no other record claims that twin; identical places stay unbound.
        pairs, unbound = _bind_by_position(items, sprites, None)
        return pairs, [(it, "ambiguous_position") for it in unbound], []
    if count == live == 1 and name_only_ok:
        return [(items[0], sprites[0])], [], []
    pairs, unbound = _bind_by_position(items, sprites, check)
    return pairs, [(it, "position") for it in unbound], []


def _same_room(a: str, b: str) -> bool:
    from engine.scene_runtime.room_memory import room_key  # noqa: PLC0415

    return room_key(a) == room_key(b) or os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _classify(raw: Any) -> tuple[_Item, str, bool]:
    """(record, state), the group key space ("id" or "name"), and whether it is a legacy (v2, name-only) record."""
    record = raw if isinstance(raw, dict) else {}
    state = SavedEntityState.from_dict(record)
    legacy = bool(record.get("legacy")) or state.keying is None
    if state.keying == KEYING_ID and state.mesh_id:
        return (record, state), KEYING_ID, False
    return (record, state), KEYING_NAME, legacy


def apply_entities_ex(
    scene_controller: Any,
    saved_entities: list[dict[str, Any]],
    *,
    strict: bool = False,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/entity_state",
    scene_path: str | None = None,
    current_room: str | None = None,
    snapshot: list[dict[str, Any]] | None = None,
    carried: list[dict[str, Any]] | None = None,
    first_seen: str = "",
    strict_binding: bool | None = None,
    log: bool = True,
) -> EntityApplyResult:
    """Apply saved entity records to the scene by identity, never by guess.

    Records keyed by id bind to the sprite with that authored id (several sharing one id bind by order and place, only
    when the counts agree). Id-less records bind to id-less sprites by name, and by place when names repeat. Legacy
    (v2) records bind by name, and by place when names repeat, cross-checked against the save's own scene snapshot.
    A record whose identity is not provable is applied to nothing, reported, and becomes an *unresolved* entry that
    every later save carries; ``carried`` entries from earlier saves are retried against the sprites that received no
    record in this call. ``scene_path`` (the room the records belong to) with ``current_room``: records of another room
    are skipped. ``strict_binding``: report unprovable records as errors (default: when ``strict``). ``log=False``: no
    stderr lines (the diagnostics are still returned).
    """
    warn = functools.partial(_warn_binding, log=log)
    result = EntityApplyResult(unresolved=merge_unresolved(carried or []))
    sprites = list(getattr(scene_controller, "all_sprites", []))
    room = str(scene_path or "")
    if scene_path and current_room and not _same_room(scene_path, current_room):
        warn(diagnostics, DiagnosticLevel.WARN, "save.restore.entities_wrong_room",
                      f"Saved entities belong to room '{scene_path}', not '{current_room}'; not applied here.",
                      source, "/saved_entities/scene_path", {"records": len(saved_entities or []), "room": current_room},
                      "They are applied when their own room loads.")
        result.skipped_wrong_room = True
        return result
    if not saved_entities and not carried:
        return result
    bind_level = DiagnosticLevel.ERROR if (strict if strict_binding is None else strict_binding) else DiagnosticLevel.WARN
    positions = _snapshot_positions(snapshot)

    def snapshot_check(item: _Item, sprite: Any) -> bool:
        # a record bound to a sprite that has an authored id must also sit where the save's snapshot put that id
        sprite_id = _sprite_mesh_id(sprite)
        if positions is None or sprite_id is None:
            return True
        where = positions.get(sprite_id)  # (an id the save's snapshot doesn't have was added since: nothing to contradict)
        return where is None or any(_near(item[1].x, item[1].y, px, py) for px, py in where)

    claimed: set[int] = set()
    by_id: dict[str, list[Any]] = {}
    by_name: dict[str, list[Any]] = {}
    for sprite in sprites:
        sprite_id = _sprite_mesh_id(sprite)
        if sprite_id:
            by_id.setdefault(sprite_id, []).append(sprite)
        name = _sprite_name(sprite)
        if name:
            by_name.setdefault(name, []).append(sprite)

    def eligible(space: str, legacy: bool, key: str) -> list[Any]:
        if space == KEYING_ID:
            found = by_id.get(key, [])
        else:
            found = [s for s in by_name.get(key, []) if legacy or _sprite_mesh_id(s) is None]
        return [s for s in found if id(s) not in claimed]

    def apply_pair(item: _Item, sprite: Any) -> bool:
        claimed.add(id(sprite))
        return apply_entity_state(sprite, item[1], strict=bool(strict), diagnostics=diagnostics, source=source)

    groups: dict[tuple[str, bool, str], list[_Item]] = {}
    for raw in saved_entities or []:
        item, space, legacy = _classify(raw)
        key = item[1].mesh_id if space == KEYING_ID else item[1].entity_id
        groups.setdefault((space, legacy, str(key)), []).append(item)

    for (space, legacy, key) in sorted(groups):
        items = groups[(space, legacy, key)]
        group_sprites = eligible(space, legacy, key)
        pairs, refused, absent = _bind_group(items, group_sprites, by_id=space == KEYING_ID, name_only_ok=True,
                                             check=snapshot_check if legacy else None)
        claimed.update(id(s) for s in group_sprites)  # these sprites had their record(s) in this load
        for item in absent:
            result.missing += 1
            # not applied, so unmatched: kept (reported as missing, carried in every save) until it binds or is edited out
            result.unresolved = merge_unresolved(result.unresolved, [unresolved_entry(item[0], "entity_missing", room, first_seen)])
            _append_diagnostic(diagnostics, _diagnostic(
                level=DiagnosticLevel.WARN, code="save.restore.entity_missing",
                message=f"Saved entity '{item[1].entity_id}' not present in scene.", source=source,
                pointer=f"/saved_entities/entities/{item[1].entity_id}",
                hint="Entity ids must stay stable between save and restore scenes."))
        for item, sprite in pairs:
            if apply_pair(item, sprite):
                result.applied += 1
            else:
                result.missing += 1
        count_reported = False
        for item, why in refused:
            result.unbound += 1
            result.unresolved = merge_unresolved(result.unresolved, [unresolved_entry(item[0], why, room, first_seen)])
            if space == KEYING_ID:
                if why == "count_mismatch" and count_reported:
                    continue
                count_reported = count_reported or why == "count_mismatch"
                warn(diagnostics, bind_level, "save.restore.entity_id_ambiguous",
                              f"{len(items)} saved entities have id '{key}' but the scene has {len(group_sprites)} "
                              f"live with it; none applied." if why == "count_mismatch" else
                              f"Saved entity with id '{key}' at ({item[1].x:g}, {item[1].y:g}) cannot be told from its live twins by place; not applied.",
                              source, f"/saved_entities/entities/{key}",
                              {"id": key, "records": len(items), "sprites": len(group_sprites),
                               "x": item[1].x, "y": item[1].y},
                              "Give each entity its own id; the records are kept as unresolved in every save.")
            else:
                code = "save.restore.entity_legacy_ambiguous" if legacy else "save.restore.entity_nameclash"
                warn(diagnostics, bind_level, code,
                              f"Saved entity '{key}' at ({item[1].x:g}, {item[1].y:g}) cannot be matched to exactly "
                              f"one of {len(group_sprites)} live sprite(s) named '{key}'; not applied.",
                              source, f"/saved_entities/entities/{key}",
                              {"name": key, "records": len(items), "sprites": len(group_sprites),
                               "x": item[1].x, "y": item[1].y,
                               "behaviours": sorted(item[1].behaviour_state)},
                              "Give the entity an id, or a place of its own; the record is kept as unresolved.")

    # unresolved records of earlier saves: retried only against sprites that received no record above, and only
    # where identity is provable (an id, or a place that is exactly one sprite's)
    if carried:
        retry_groups: dict[tuple[str, bool, str], list[_Item]] = {}
        entry_of: dict[int, dict[str, Any]] = {}
        for entry in merge_unresolved(carried):
            item, space, legacy = _classify(entry["record"])
            entry_of[id(item[0])] = entry
            key = item[1].mesh_id if space == KEYING_ID else item[1].entity_id
            retry_groups.setdefault((space, legacy, str(key)), []).append(item)
        bound: list[dict[str, Any]] = []
        for (space, legacy, key) in sorted(retry_groups):
            items = retry_groups[(space, legacy, key)]
            pairs, _refused, _absent = _bind_group(items, eligible(space, legacy, key), by_id=space == KEYING_ID,
                                                   name_only_ok=False, check=None)
            for item, sprite in pairs:
                bound.append(entry_of[id(item[0])])
                apply_pair(item, sprite)
                result.applied += 1
                result.retried += 1
        if bound:
            bound_keys = {_entry_key(e) for e in bound}
            result.unresolved = [e for e in result.unresolved if _entry_key(e) not in bound_keys]

    if result.unbound:
        warn(diagnostics, DiagnosticLevel.WARN, "save.restore.entities_unbound",
                      f"{result.unbound} saved entity record(s) could not be matched and were not applied.",
                      source, "/saved_entities/entities",
                      {"applied": result.applied, "missing": result.missing, "unbound": result.unbound},
                      "They stay in the save as unresolved records.")
    if result.unresolved:
        warn(diagnostics, DiagnosticLevel.WARN, "save.restore.entities_unresolved",
                      f"{len(result.unresolved)} unresolved entity record(s) are carried in every save.",
                      source, "/saved_entities/unresolved", {"count": len(result.unresolved)},
                      "Fix the scene so they bind, or edit the save.")
    return result


def _warn_binding(
    diagnostics: list[Diagnostic] | None,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str,
    context: dict[str, Any],
    hint: str,
    log: bool = True,
) -> None:
    if log:
        sys.stderr.write(f"[Mesh][Save] WARNING: {code}: {message}\n")
    _append_diagnostic(diagnostics, _diagnostic(level=level, code=code, message=message, source=source,
                                                pointer=pointer, hint=hint, context_extra=context))


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
        Tuple of (applied_count, missing_count); see ``apply_entities_ex`` for the unbound count and the rest.
    """
    result = apply_entities_ex(scene_controller, saved_entities, strict=strict, diagnostics=diagnostics, source=source)
    return (result.applied, result.missing)


def saved_entities_context(payload: dict[str, Any]) -> dict[str, Any]:
    """What a restore needs besides the records, read from a (migrated, normalized) save payload."""
    block = payload.get("saved_entities")
    block = block if isinstance(block, dict) else {}
    raw_meta = payload.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    guard = block.get("scene_path") if isinstance(block.get("scene_path"), str) and block.get("scene_path") else None
    room = guard or str(meta.get("scene_path") or payload.get("scene_path") or "")
    entities = payload.get("entities")
    carried = block.get("unresolved")
    return {
        "scene_path": room,
        "guard_room": guard,
        "snapshot": [e for e in entities if isinstance(e, dict)] if isinstance(entities, list) else None,
        "carried": [e for e in carried if isinstance(e, dict) and isinstance(e.get("record"), dict)]
        if isinstance(carried, list) else [],
        "first_seen": str(meta.get("timestamp") or ""),
    }


def apply_pending_saved_entities(controller: Any, pending: PendingSavedEntities) -> EntityApplyResult:
    """Restore a loaded save's entity records onto the saved room, now that it exists, and hold its unresolved ones."""
    diagnostics: list[Diagnostic] = []
    result = apply_entities_ex(
        controller, pending.records, diagnostics=diagnostics, source=pending.source, scene_path=pending.scene_path,
        snapshot=pending.snapshot, carried=pending.carried, first_seen=pending.first_seen, strict_binding=False)
    hold_unresolved(controller, result.unresolved)
    if pending.on_done is not None:
        pending.on_done(result, diagnostics)
    return result

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
