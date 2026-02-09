"""Contract tests for keymap override model."""

from __future__ import annotations

from dataclasses import dataclass

from engine.editor.keymap_override_model import (
    apply_keymap_overrides,
    compute_keymap_conflicts,
    format_keymap_conflict,
    KeymapConflict,
    parse_keymap_overrides,
    parse_override_key,
    SHORTCUT_SCOPE_GLOBAL,
)
from engine.editor.editor_actions import SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_PROJECT_EXPLORER


@dataclass(frozen=True)
class _Action:
    id: str
    shortcut: str
    shortcut_scope: str = SHORTCUT_SCOPE_GLOBAL


# --- parse_override_key tests ---


def test_parse_override_key_global_default() -> None:
    """Non-scoped key defaults to global scope."""
    scope, action_id = parse_override_key("editor.foo")
    assert scope == "global"
    assert action_id == "editor.foo"


def test_parse_override_key_scoped() -> None:
    """Scoped key parses scope and action_id."""
    scope, action_id = parse_override_key("text_input.inline_rename:editor.foo")
    assert scope == "text_input.inline_rename"
    assert action_id == "editor.foo"


def test_parse_override_key_strips_whitespace() -> None:
    """Whitespace around scope and action_id is stripped."""
    scope, action_id = parse_override_key("  text_input.inline_rename : editor.foo  ")
    assert scope == "text_input.inline_rename"
    assert action_id == "editor.foo"


def test_parse_override_key_empty_action_id() -> None:
    """Empty action_id after colon returns empty string."""
    scope, action_id = parse_override_key("text_input.inline_rename:")
    assert scope == "text_input.inline_rename"
    assert action_id == ""


# --- parse_keymap_overrides tests ---


def test_parse_keymap_overrides_returns_scoped_dict() -> None:
    """parse_keymap_overrides returns (scope, action_id) keyed dict."""
    payload = {
        "editor.foo": "Ctrl+A",
        "text_input.inline_rename:editor.bar": "Enter",
    }
    overrides = parse_keymap_overrides(payload)
    assert ("global", "editor.foo") in overrides
    assert overrides[("global", "editor.foo")] == "Ctrl+A"
    assert ("text_input.inline_rename", "editor.bar") in overrides
    assert overrides[("text_input.inline_rename", "editor.bar")] == "Enter"


def test_parse_keymap_overrides_null_becomes_empty() -> None:
    """Null value becomes empty string for unbinding."""
    payload = {"editor.foo": None}
    overrides = parse_keymap_overrides(payload)
    assert overrides[("global", "editor.foo")] == ""


# --- apply_keymap_overrides tests ---


def test_keymap_apply_overrides_deterministic() -> None:
    actions = [
        _Action("a.one", "Ctrl+A"),
        _Action("b.two", "Ctrl+B"),
    ]
    overrides = parse_keymap_overrides({"a.one": "Ctrl+X"})
    updated, unknown_scopes, unknown_keys = apply_keymap_overrides(actions, overrides)
    updated2, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == ["Ctrl+X", "Ctrl+B"]
    assert [a.shortcut for a in updated2] == ["Ctrl+X", "Ctrl+B"]
    assert unknown_scopes == set()
    assert unknown_keys == set()


def test_keymap_unknown_action_ignored() -> None:
    actions = [_Action("a.one", "Ctrl+A")]
    overrides = parse_keymap_overrides({"missing.action": "Ctrl+M"})
    updated, unknown_scopes, unknown_keys = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == ["Ctrl+A"]
    assert unknown_scopes == set()
    assert unknown_keys == {("global", "missing.action")}


def test_keymap_can_unbind_shortcut() -> None:
    actions = [_Action("a.one", "Ctrl+A")]
    overrides = parse_keymap_overrides({"a.one": ""})
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == [""]


def test_scoped_override_applies_only_in_scope() -> None:
    """Scoped override applies only to action with matching scope."""
    actions = [
        _Action("editor.commit", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
        _Action("editor.commit", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    # Override only the inline_rename scoped action
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.commit": "Ctrl+Enter",
    })
    updated, unknown_scopes, unknown_keys = apply_keymap_overrides(actions, overrides)
    assert updated[0].shortcut == "Ctrl+S"  # global unchanged
    assert updated[1].shortcut == "Ctrl+Enter"  # inline_rename changed
    assert unknown_scopes == set()
    assert unknown_keys == set()


def test_scoped_unbind_shortcut() -> None:
    """Scoped unbind only affects action in that scope."""
    actions = [
        _Action("editor.foo", "Ctrl+A", SHORTCUT_SCOPE_GLOBAL),
        _Action("editor.bar", "Escape", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.bar": None,
    })
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert updated[0].shortcut == "Ctrl+A"  # global unchanged
    assert updated[1].shortcut == ""  # inline_rename unbound


def test_unknown_scope_is_reported_and_ignored() -> None:
    """Unknown scope is reported and does not affect actions."""
    actions = [
        _Action("editor.foo", "Ctrl+A", SHORTCUT_SCOPE_GLOBAL),
    ]
    overrides = parse_keymap_overrides({
        "bogus_scope:editor.foo": "Ctrl+X",
    })
    known_scopes = {SHORTCUT_SCOPE_GLOBAL, SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_PROJECT_EXPLORER}
    updated, unknown_scopes, unknown_keys = apply_keymap_overrides(
        actions, overrides, known_scopes
    )
    assert updated[0].shortcut == "Ctrl+A"  # unchanged
    assert unknown_scopes == {"bogus_scope"}
    assert unknown_keys == set()


# --- compute_keymap_conflicts tests ---


def test_keymap_conflict_resolution_stable() -> None:
    actions = [
        _Action("a.one", "Ctrl+A"),
        _Action("b.two", "Ctrl+A"),
        _Action("c.three", "Ctrl+C"),
    ]
    conflicts = compute_keymap_conflicts(actions)
    assert len(conflicts) == 1
    assert conflicts[0] == KeymapConflict("global", "Ctrl+A", ("a.one", "b.two"))
    # Verify formatted output matches legacy format
    assert format_keymap_conflict(conflicts[0]) == "global:Ctrl+A: a.one, b.two"


def test_scoped_conflict_reporting_stable() -> None:
    """Conflicts include scope and are sorted deterministically."""
    actions = [
        _Action("a.one", "Ctrl+A", SHORTCUT_SCOPE_GLOBAL),
        _Action("b.two", "Ctrl+A", SHORTCUT_SCOPE_GLOBAL),
        _Action("c.one", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
        _Action("c.two", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    conflicts = compute_keymap_conflicts(actions)
    # Sorted by scope then shortcut
    assert len(conflicts) == 2
    assert conflicts[0] == KeymapConflict("global", "Ctrl+A", ("a.one", "b.two"))
    assert conflicts[1] == KeymapConflict("text_input.inline_rename", "Enter", ("c.one", "c.two"))
    # Verify formatted output matches legacy format
    assert format_keymap_conflict(conflicts[0]) == "global:Ctrl+A: a.one, b.two"
    assert format_keymap_conflict(conflicts[1]) == "text_input.inline_rename:Enter: c.one, c.two"


def test_cross_scope_same_shortcut_not_conflict() -> None:
    """Same shortcut in different scopes is NOT a conflict."""
    actions = [
        _Action("global.enter", "Enter", SHORTCUT_SCOPE_GLOBAL),
        _Action("inline.enter", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    conflicts = compute_keymap_conflicts(actions)
    assert conflicts == []


# --- Inline Rename Action Override Tests ---


def test_inline_rename_commit_shortcut_can_be_overridden() -> None:
    """Inline rename commit action shortcut can be remapped via overrides."""
    actions = [
        _Action("editor.project_explorer.inline_rename.commit", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
        _Action("editor.project_explorer.inline_rename.cancel", "Escape", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.project_explorer.inline_rename.commit": "Ctrl+Enter",
    })
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == ["Ctrl+Enter", "Escape"]


def test_inline_rename_cancel_shortcut_can_be_overridden() -> None:
    """Inline rename cancel action shortcut can be remapped via overrides."""
    actions = [
        _Action("editor.project_explorer.inline_rename.commit", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
        _Action("editor.project_explorer.inline_rename.cancel", "Escape", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.project_explorer.inline_rename.cancel": "Ctrl+Escape",
    })
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == ["Enter", "Ctrl+Escape"]


def test_inline_rename_backspace_shortcut_can_be_unbound() -> None:
    """Inline rename backspace action can be unbound via empty override."""
    actions = [
        _Action("editor.project_explorer.inline_rename.backspace", "Backspace", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.project_explorer.inline_rename.backspace": "",
    })
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == [""]


def test_inline_rename_delete_shortcut_can_be_overridden() -> None:
    """Inline rename delete action shortcut can be remapped."""
    actions = [
        _Action("editor.project_explorer.inline_rename.delete", "Delete", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    overrides = parse_keymap_overrides({
        "text_input.inline_rename:editor.project_explorer.inline_rename.delete": "Ctrl+D",
    })
    updated, _, _ = apply_keymap_overrides(actions, overrides)
    assert [a.shortcut for a in updated] == ["Ctrl+D"]
