"""Pure helpers for applying keymap overrides to editor actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from engine.editor.shortcut_resolver_model import normalize_shortcut_text
from engine.swallowed_exceptions import _log_swallow

# Re-export scope constants for convenience
from engine.editor.editor_actions import SHORTCUT_SCOPE_GLOBAL  # noqa: F401


# Type alias for scoped overrides: {(scope, action_id): shortcut_or_empty}
ScopedOverrides = dict[tuple[str, str], str]


@dataclass(frozen=True, slots=True)
class KeymapConflict:
    """Structured representation of a shortcut conflict within a scope."""

    scope: str
    shortcut: str
    action_ids: tuple[str, ...]


def format_keymap_conflict(conflict: KeymapConflict) -> str:
    """Format a KeymapConflict as a log-friendly string.

    Format: "scope:shortcut: action1, action2"
    """
    return f"{conflict.scope}:{conflict.shortcut}: {', '.join(conflict.action_ids)}"


def parse_override_key(key: str) -> tuple[str, str]:
    """Parse an override key into (scope, action_id).

    Format:
    - "editor.foo" -> ("global", "editor.foo")
    - "text_input.inline_rename:editor.foo" -> ("text_input.inline_rename", "editor.foo")
    """
    from engine.editor.editor_actions import SHORTCUT_SCOPE_GLOBAL  # noqa: PLC0415

    if ":" in key:
        scope, _, action_id = key.partition(":")
        return scope.strip(), action_id.strip()
    return SHORTCUT_SCOPE_GLOBAL, key.strip()


def parse_keymap_overrides(payload: dict) -> ScopedOverrides:
    """Parse keymap.json payload into scoped overrides.

    Returns dict mapping (scope, action_id) -> shortcut string (or empty to unbind).
    """
    overrides: ScopedOverrides = {}
    if not isinstance(payload, dict):
        return overrides
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        scope, action_id = parse_override_key(key)
        if not action_id:
            continue
        if value is None:
            overrides[(scope, action_id)] = ""
            continue
        if not isinstance(value, str):
            continue
        overrides[(scope, action_id)] = value.strip()
    return overrides


def apply_keymap_overrides(
    actions: Iterable[Any],
    overrides: ScopedOverrides,
    known_scopes: set[str] | None = None,
) -> tuple[list[Any], set[str], set[tuple[str, str]]]:
    """Apply scoped overrides to actions.

    Args:
        actions: Iterable of EditorAction-like objects with id, shortcut, shortcut_scope.
        overrides: Scoped overrides from parse_keymap_overrides.
        known_scopes: Optional set of valid scope strings. If None, all scopes accepted.

    Returns:
        Tuple of:
        - List of updated actions
        - Set of unknown scopes encountered (scope strings)
        - Set of unknown action keys (scope, action_id) tuples
    """
    from engine.editor.editor_actions import SHORTCUT_SCOPE_GLOBAL  # noqa: PLC0415

    if not overrides:
        return list(actions), set(), set()

    # Build index of actions by (scope, id)
    action_list = list(actions)
    action_index: dict[tuple[str, str], int] = {}
    for i, action in enumerate(action_list):
        action_id = getattr(action, "id", "")
        scope = getattr(action, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL)
        action_index[(scope, action_id)] = i

    # Collect all known scopes from actions if not provided
    if known_scopes is None:
        known_scopes = {getattr(a, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL) for a in action_list}

    unknown_scopes: set[str] = set()
    unknown_keys: set[tuple[str, str]] = set()
    updated = list(action_list)

    for (scope, action_id), shortcut in overrides.items():
        # Check for unknown scope
        if scope not in known_scopes:
            unknown_scopes.add(scope)
            continue
        # Check for unknown action in scope
        key = (scope, action_id)
        if key not in action_index:
            unknown_keys.add(key)
            continue
        # Apply override
        idx = action_index[key]
        action = updated[idx]
        new_shortcut = shortcut if shortcut is not None else ""
        try:
            updated[idx] = replace(action, shortcut=str(new_shortcut))
        except Exception:
            _log_swallow("KEYM-001", "engine/editor/keymap_override_model.py pass-only blanket swallow")
            pass

    return updated, unknown_scopes, unknown_keys


def compute_keymap_conflicts(actions: Iterable[object]) -> list[KeymapConflict]:
    """Compute shortcut conflicts per scope.

    Returns list of KeymapConflict sorted by (scope, shortcut, action_ids).
    """
    from engine.editor.editor_actions import SHORTCUT_SCOPE_GLOBAL  # noqa: PLC0415

    # Group by (scope, normalized_shortcut)
    scope_shortcut_to_ids: dict[tuple[str, str], list[str]] = {}
    for action in actions:
        shortcut = normalize_shortcut_text(getattr(action, "shortcut", ""))
        if not shortcut:
            continue
        scope = getattr(action, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL)
        key = (scope, shortcut)
        scope_shortcut_to_ids.setdefault(key, []).append(str(getattr(action, "id", "")))

    conflicts: list[KeymapConflict] = []
    # Sort by (scope, shortcut) for deterministic ordering
    for (scope, shortcut) in sorted(scope_shortcut_to_ids.keys()):
        ids = scope_shortcut_to_ids[(scope, shortcut)]
        if len(ids) > 1:
            conflicts.append(KeymapConflict(scope, shortcut, tuple(sorted(ids))))
    return conflicts
