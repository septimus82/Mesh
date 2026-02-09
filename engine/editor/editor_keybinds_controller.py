"""
Controller for Keybinds UI.

Manages state, recording, and persistence of keybindings.
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Optional, Dict, Tuple
from pathlib import Path

from engine.editor.keybinds_ui_model import (
    KeybindsState, KeybindRow, build_keybind_rows,
    apply_staged_override, begin_recording, cancel_recording, commit_recorded_key,
    update_recording_preview
)
from engine.editor.editor_actions import get_editor_actions
from engine.editor.shortcut_resolver_model import normalize_shortcut_event
from engine.editor.persistence_utils import write_atomic_utf8
from engine.repo_root import get_repo_root

KEYMAP_FILENAME = "keymap.json"

class EditorKeybindsController:
    def __init__(self, editor: Any):
        self._editor = editor
        # Load initial overrides from editor or disk?
        # Editor usually has `_keymap_overrides` which are ScopedOverrides.
        initial_overrides = getattr(editor, "_keymap_overrides", {})
        
        self.state = KeybindsState(
            staged_overrides=dict(initial_overrides)
        )
        self._cached_rows: Tuple[KeybindRow, ...] = ()
        self._rows_dirty = True
        
    def _refresh_rows(self) -> None:
        if not self._rows_dirty:
            return
            
        actions = get_editor_actions(self._editor, getattr(self._editor, "window", None))
        self._cached_rows = build_keybind_rows(
            actions, 
            self.state.staged_overrides,
            self.state.query,
            self.state.scope_filter,
            self.state.show_conflicts_only
        )
        self._rows_dirty = False

    @property
    def visible_rows(self) -> Tuple[KeybindRow, ...]:
        self._refresh_rows()
        return self._cached_rows

    def open(self) -> None:
        self.state = replace(self.state, visible=True, query="", selected_index=0, scope_filter="all", show_conflicts_only=False)
        self._rows_dirty = True
        # Also refresh staged from current editor state in case it changed externally?
        initial = getattr(self._editor, "_keymap_overrides", {})
        self.state = replace(self.state, staged_overrides=dict(initial))

    def close(self) -> None:
        self.state = replace(self.state, visible=False, recording=False)
            
    def set_scope_filter(self, scope: str) -> None:
        self.state = replace(self.state, scope_filter=scope, selected_index=0)
        self._rows_dirty = True
        
    def toggle_show_conflicts(self) -> None:
        self.state = replace(self.state, show_conflicts_only=not self.state.show_conflicts_only, selected_index=0)
        self._rows_dirty = True

    def set_query(self, text: str) -> None:
        self.state = replace(self.state, query=text, selected_index=0)
        self._rows_dirty = True

    def move_selection(self, delta: int) -> None:
        rows = self.visible_rows
        if not rows:
            return
        new_idx = max(0, min(len(rows) - 1, self.state.selected_index + delta))
        self.state = replace(self.state, selected_index=new_idx)

    def start_recording_selected(self) -> None:
        rows = self.visible_rows
        if not rows: return
        
        row = rows[self.state.selected_index]
        self.state = begin_recording(self.state, row.scope, row.action_id)

    def unbind_selected(self) -> None:
        rows = self.visible_rows
        if not rows: return
        row = rows[self.state.selected_index]
        
        # Unbind means set override to empty string
        self.state = apply_staged_override(self.state, row.scope, row.action_id, "")
        self._rows_dirty = True

    def reset_all(self) -> None:
        """Reset all overrides."""
        self.state = replace(self.state, staged_overrides={})
        self._rows_dirty = True

    def reset_selected(self) -> None:
        rows = self.visible_rows
        if not rows: return
        row = rows[self.state.selected_index]
        
        # Reset means remove override (None)
        self.state = apply_staged_override(self.state, row.scope, row.action_id, None)
        self._rows_dirty = True

    def handle_input(self, key: int, modifiers: int) -> bool:
        """
        Main input handler when modal is active.
        Returns True if consumed.
        """
        import engine.optional_arcade as optional_arcade
        
        # If recording, consume EVERYTHING
        if self.state.recording:
            # Check for Escape first -> Cancel
            if key == optional_arcade.arcade.key.ESCAPE:
                self.state = cancel_recording(self.state)
                return True
                
            is_mod = key in (
                optional_arcade.arcade.key.LSHIFT, optional_arcade.arcade.key.RSHIFT,
                optional_arcade.arcade.key.LCTRL, optional_arcade.arcade.key.RCTRL,
                optional_arcade.arcade.key.LALT, optional_arcade.arcade.key.RALT,
                optional_arcade.arcade.key.LMETA, optional_arcade.arcade.key.RMETA
            )
            
            # Build string representation for preview
            k_name = str(optional_arcade.arcade.key.symbol_string(key)).replace("KEY_", "")
            
            mod_str = ""
            parts = []
            if modifiers & optional_arcade.arcade.key.MOD_CTRL: parts.append("Ctrl")
            if modifiers & optional_arcade.arcade.key.MOD_ALT: parts.append("Alt")
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT: parts.append("Shift")
            mod_str = "+".join(parts)
            
            # Construct preview string
            if is_mod:
                # Just show modifiers
                preview_str = mod_str + ("+" if mod_str else "")
                # If mod key itself is pressed, it is included in modifiers usually?
                # Actually arcade Modifiers bitmask tracks HELD keys.
                # If I press LSHIFT, modifiers has MOD_SHIFT.
                pass
            else:
                preview_str = f"{mod_str}+{k_name}" if mod_str else k_name
                
            # Update Preview (Live conflict check)
            all_actions = get_editor_actions(self._editor, getattr(self._editor, "window", None))
            self.state = update_recording_preview(self.state, preview_str, all_actions)
            
            if is_mod:
                return True # Swallow modifier presses, just update preview
            
            # Commit on non-modifier press
            self.state = commit_recorded_key(self.state, k_name, mod_str)
            self._rows_dirty = True
            return True

        # Navigation
        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True
        if key == optional_arcade.arcade.key.UP:
            self.move_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.move_selection(1)
            return True
        if key == optional_arcade.arcade.key.ENTER:
            self.start_recording_selected()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            self.unbind_selected()
            return True
        if key == optional_arcade.arcade.key.Delete: # Case sensitivity? usually DELETE
            self.reset_selected()
            return True
        # Match DELETE as well just in case
        if key == optional_arcade.arcade.key.DELETE:
            self.reset_selected()
            return True
            
        # Ctrl+S or Apply?
        if key == optional_arcade.arcade.key.S and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            # Check for existing conflicts before applying?
            # V1.1: Just apply for now.
            self.apply_changes()
            self.close()
            return True
            
        # Filter Hotkeys
        if key == optional_arcade.arcade.key.F1:
            # Cycle scope filter: all -> global -> mesh -> all
            sc = self.state.scope_filter
            nxt = "global" if sc == "all" else ("mesh" if sc == "global" else "all")
            self.set_scope_filter(nxt)
            return True
            
        if key == optional_arcade.arcade.key.F2:
            self.toggle_show_conflicts()
            return True

        return True # Modal blocks everything else

    def on_text(self, text: str) -> bool:
        if not self.state.recording:
            # Append to query
            self.set_query(self.state.query + text)
            return True
        return True

    def backspace_query(self) -> None:
        if self.state.query:
            self.set_query(self.state.query[:-1])

    def apply_changes(self) -> None:
        """Persist changes to editor and disk."""
        # 1. Update Editor
        self._editor._keymap_overrides = dict(self.state.staged_overrides)
        if hasattr(self._editor, "_shortcut_map_cache"):
            self._editor._shortcut_map_cache.clear()

        # 2. Write to Disk
        repo_root = get_repo_root()
        if not repo_root: return
        
        path = repo_root / KEYMAP_FILENAME
        
        data = []
        # Sort for determinism
        for (scope, aid), sc in sorted(self.state.staged_overrides.items()):
            if sc is None: continue 
            data.append({
                "scope": scope,
                "action_id": aid,
                "shortcut": sc
            })
            
        try:
            write_atomic_utf8(path, json.dumps(data, indent=2))
        except Exception as e:
            print(f"Failed to save keymap: {e}")

