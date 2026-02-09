"""
Contract tests for Keybinds UI Model.
"""
from engine.editor.keybinds_ui_model import (
    KeybindsState, KeybindRow, build_keybind_rows,
    apply_staged_override, begin_recording, commit_recorded_key
)
from types import SimpleNamespace

def make_action(id, title="Title", scope="global", shortcut=""):
    return SimpleNamespace(
        id=id, 
        title=title, 
        shortcut_scope=scope, 
        shortcut=shortcut
    )

def test_build_rows_filtering():
    actions = (
        make_action(id="a1", title="Save", shortcut="Ctrl+S"),
        make_action(id="a2", title="Open", shortcut="Ctrl+O"),
    )
    overrides = {}
    
    # All
    rows = build_keybind_rows(actions, overrides, "")
    assert len(rows) == 2
    
    # Query "Save"
    rows = build_keybind_rows(actions, overrides, "ave")
    assert len(rows) == 1
    assert rows[0].action_id == "a1"

def test_build_rows_overrides():
    actions = (
        make_action(id="a1", shortcut="Ctrl+S"),
    )
    overrides = {("global", "a1"): "Alt+S"}
    
    rows = build_keybind_rows(actions, overrides, "")
    assert rows[0].shortcut_effective == "Alt+S"
    assert rows[0].has_override is True

def test_conflict_detection():
    actions = (
        make_action(id="a1", shortcut="Ctrl+S"),
        make_action(id="a2", shortcut="Ctrl+S"), # default conflict
        make_action(id="a3", shortcut="Ctrl+X"),
    )
    overrides = {}
    
    rows = build_keybind_rows(actions, overrides, "")
    # Should sort conflicts first
    assert rows[0].action_id in ("a1", "a2")
    assert rows[1].action_id in ("a1", "a2")
    assert len(rows[0].conflict_ids) == 1
    
    # a3 no conflict
    assert rows[2].action_id == "a3"
    assert len(rows[2].conflict_ids) == 0

def test_recording_flow():
    state = KeybindsState()
    state = begin_recording(state, "global", "a1")
    assert state.recording is True
    assert state.recording_target == ("global", "a1")
    
    state = commit_recorded_key(state, "K", "Ctrl")
    assert state.recording is False
    assert state.staged_overrides[("global", "a1")] == "Ctrl+K"

def test_apply_staged_reset():
    state = KeybindsState(staged_overrides={("global", "a1"): "X"})
    # Passing None means delete/reset
    state = apply_staged_override(state, "global", "a1", None)
    assert ("global", "a1") not in state.staged_overrides
