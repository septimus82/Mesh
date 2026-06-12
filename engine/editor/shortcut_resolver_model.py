"""Pure shortcut resolver helpers for editor actions."""

from __future__ import annotations

from typing import Iterable

import engine.optional_arcade as optional_arcade

# Scope constants (re-exported for convenience)
SHORTCUT_SCOPE_GLOBAL = "global"
SHORTCUT_SCOPE_INLINE_RENAME = "text_input.inline_rename"
SHORTCUT_SCOPE_PROJECT_EXPLORER = "project_explorer"
SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU = "project_explorer.context_menu"


_MOD_ORDER = ("Ctrl", "Alt", "Shift")
_MOD_TOKENS = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "cmd": "Ctrl",
    "command": "Ctrl",
    "alt": "Alt",
    "option": "Alt",
    "shift": "Shift",
}
_KEY_TOKEN_ALIASES = {
    "esc": "Esc",
    "escape": "Esc",
    "enter": "Enter",
    "return": "Enter",
    "backspace": "Backspace",
    "delete": "Del",
    "del": "Del",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "pgup": "PageUp",
    "pgdown": "PageDown",
    "space": "Space",
    "tab": "Tab",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def _build_keycode_map() -> dict[int, str]:
    key = optional_arcade.arcade.key
    mapping: dict[int, str] = {}
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        code = getattr(key, ch, None)
        if isinstance(code, int):
            mapping[code] = ch
    for num in range(10):
        code = getattr(key, f"KEY_{num}", None)
        if isinstance(code, int):
            mapping[code] = str(num)
    for i in range(1, 13):
        code = getattr(key, f"F{i}", None)
        if isinstance(code, int):
            mapping[code] = f"F{i}"
    for attr, label in (
        ("SPACE", "Space"),
        ("TAB", "Tab"),
        ("ENTER", "Enter"),
        ("RETURN", "Enter"),
        ("ESCAPE", "Esc"),
        ("BACKSPACE", "Backspace"),
        ("DELETE", "Del"),
        ("PAGE_UP", "PageUp"),
        ("PAGE_DOWN", "PageDown"),
        ("UP", "Up"),
        ("DOWN", "Down"),
        ("LEFT", "Left"),
        ("RIGHT", "Right"),
    ):
        code = getattr(key, attr, None)
        if isinstance(code, int):
            mapping[code] = label
    return mapping


_KEYCODE_TO_TOKEN = _build_keycode_map()


def normalize_shortcut_text(text: str) -> str:
    """Normalize a shortcut string into a deterministic form."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    tokens = [part.strip() for part in raw.split("+") if part.strip()]
    if not tokens:
        return ""
    mods: set[str] = set()
    key_token = ""
    for token in tokens:
        lowered = token.strip().lower()
        if lowered in _MOD_TOKENS:
            mods.add(_MOD_TOKENS[lowered])
            continue
        key_token = _normalize_key_token(token)
    if not key_token:
        return ""
    ordered_mods = [mod for mod in _MOD_ORDER if mod in mods]
    return "+".join([*ordered_mods, key_token])


def _normalize_key_token(token: str) -> str:
    cleaned = str(token or "").strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered in _KEY_TOKEN_ALIASES:
        return _KEY_TOKEN_ALIASES[lowered]
    if len(cleaned) == 1 and cleaned.isalnum():
        return cleaned.upper()
    if lowered.startswith("f") and cleaned[1:].isdigit():
        return f"F{int(cleaned[1:])}"
    return cleaned


def normalize_shortcut_event(key: int, modifiers: int) -> str:
    """Normalize a key/modifier event into shortcut string form."""
    key_token = _KEYCODE_TO_TOKEN.get(int(key), "")
    if not key_token:
        return ""
    mods: list[str] = []
    if modifiers & optional_arcade.arcade.key.MOD_CTRL:
        mods.append("Ctrl")
    if modifiers & optional_arcade.arcade.key.MOD_ALT:
        mods.append("Alt")
    if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
        mods.append("Shift")
    ordered_mods = [mod for mod in _MOD_ORDER if mod in mods]
    return "+".join([*ordered_mods, key_token])


def build_shortcut_map(actions: Iterable[object]) -> dict[str, list[str]]:
    shortcut_map: dict[str, list[str]] = {}
    for action in actions:
        shortcut = normalize_shortcut_text(getattr(action, "shortcut", ""))
        if not shortcut:
            continue
        shortcut_map.setdefault(shortcut, []).append(str(getattr(action, "id", "")))
    return shortcut_map


def resolve_shortcut(shortcut_map: dict[str, list[str]], shortcut: str) -> str | None:
    normalized = normalize_shortcut_text(shortcut)
    if not normalized:
        return None
    matches = shortcut_map.get(normalized, [])
    if not matches:
        return None
    return matches[0]


# --- Scoped Shortcut Resolution ---


def build_shortcut_map_by_scope(
    actions: Iterable[object],
) -> dict[str, dict[str, str]]:
    """Build a mapping of shortcuts to action IDs, organized by scope.
    
    Returns: {scope: {shortcut: action_id}}
    
    Within each scope, only the first action for a given shortcut is kept
    (deterministic resolution). Duplicates within the same scope are detected
    by validate_shortcut_scopes.
    """
    scope_maps: dict[str, dict[str, str]] = {}
    for action in actions:
        shortcut = normalize_shortcut_text(getattr(action, "shortcut", ""))
        if not shortcut:
            continue
        scope = getattr(action, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL)
        action_id = str(getattr(action, "id", ""))
        if scope not in scope_maps:
            scope_maps[scope] = {}
        # First action wins for deterministic resolution
        if shortcut not in scope_maps[scope]:
            scope_maps[scope][shortcut] = action_id
    return scope_maps


def resolve_shortcut_scoped(
    scope_maps: dict[str, dict[str, str]],
    shortcut: str,
    active_scopes: list[str],
) -> str | None:
    """Resolve a shortcut to an action ID using scoped priority.
    
    Args:
        scope_maps: Result from build_shortcut_map_by_scope
        shortcut: The shortcut string to resolve
        active_scopes: List of active scopes in priority order (first = highest)
    
    Returns:
        The action ID if found, or None
    """
    normalized = normalize_shortcut_text(shortcut)
    if not normalized:
        return None

    for scope in active_scopes:
        scope_map = scope_maps.get(scope, {})
        if normalized in scope_map:
            return scope_map[normalized]

    return None


def validate_shortcut_scopes(actions: Iterable[object]) -> list[str]:
    """Validate that there are no duplicate shortcuts within the same scope.
    
    Returns:
        List of error messages for any duplicates found.
    """
    # Track: {scope: {shortcut: [action_ids]}}
    scope_shortcuts: dict[str, dict[str, list[str]]] = {}

    for action in actions:
        shortcut = normalize_shortcut_text(getattr(action, "shortcut", ""))
        if not shortcut:
            continue
        scope = getattr(action, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL)
        action_id = str(getattr(action, "id", ""))

        if scope not in scope_shortcuts:
            scope_shortcuts[scope] = {}
        if shortcut not in scope_shortcuts[scope]:
            scope_shortcuts[scope][shortcut] = []
        scope_shortcuts[scope][shortcut].append(action_id)

    errors: list[str] = []
    for scope, shortcuts in scope_shortcuts.items():
        for shortcut, action_ids in shortcuts.items():
            if len(action_ids) > 1:
                errors.append(
                    f"Duplicate shortcut '{shortcut}' in scope '{scope}': {', '.join(action_ids)}"
                )

    return errors
