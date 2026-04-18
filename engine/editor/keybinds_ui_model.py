"""
Pure model for Keybinds UI.

Manages state for viewing, searching, recording, and patching keybinds.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Tuple, Dict, Optional, Any, Set, Sequence, TypedDict
from .keymap_override_model import ScopedOverrides

@dataclass(frozen=True)
class KeybindRow:
    """A single row in the keybinds list."""
    scope: str
    action_id: str
    title: str
    shortcut_effective: str
    shortcut_default: str
    has_override: bool
    conflict_ids: Tuple[str, ...]

@dataclass(frozen=True)
class KeybindsState:
    """State of the Keybinds modal."""
    visible: bool = False
    query: str = ""
    selected_index: int = 0
    
    # Live recording preview
    recording: bool = False
    recording_target: Optional[Tuple[str, str]] = None  # (scope, action_id)
    pending_record_shortcut: Optional[str] = None
    pending_conflicts: Tuple[Tuple[str, str], ...] = ()
    
    # Filters
    scope_filter: str = "all"
    show_conflicts_only: bool = False
    
    staged_overrides: ScopedOverrides = field(default_factory=dict)

    
def build_keybind_rows(
    actions: Sequence[Any],
    staged_overrides: ScopedOverrides,
    query: str = "",
    scope_filter: str = "all",
    show_conflicts_only: bool = False
) -> Tuple[KeybindRow, ...]:
    """
    Build filtered and sorted rows for the UI.
    
    actions: iterable of EditorAction (or minimal protocol objects)
    staged_overrides: overrides to apply on top of defaults
    """
    # 1. Resolve effective shortcuts
    # We do a simplified resolution here for display.
    # We assume 'actions' contains defaults.
    
    # Map (scope, shortcut) -> [action_ids] to find conflicts
    # We need to compute conflicts for what we are *displaying*, 
    # which includes the staged overrides.
    
    # First pass: Build raw data + Apply overrides
    raw_items: list[_RawItem] = []
    
    # normalized query
    q_norm = query.lower().strip()
    
    # Track usage within scope for conflict detection
    # scope -> shortcut -> list[action_id]
    usage_map: Dict[str, Dict[str, list[str]]] = {}
    
    for action in actions:
        scope = getattr(action, "shortcut_scope", "global")
        aid = getattr(action, "id", "")
        if not aid:
            continue
        
        default_sc = getattr(action, "shortcut", "") or ""
        override = staged_overrides.get((scope, aid))
        
        effective = default_sc
        has_override = False
        
        if override is not None:
            effective = override
            has_override = True
            
        if effective:
            if scope not in usage_map:
                usage_map[scope] = {}
            if effective not in usage_map[scope]:
                usage_map[scope][effective] = []
            usage_map[scope][effective].append(aid)
            
        raw_items.append({
            "scope": scope,
            "aid": aid,
            "title": getattr(action, "title", aid),
            "effective": effective,
            "default": default_sc,
            "has_override": has_override
        })
            
    # Second pass: Filter and Build Rows
    final_rows = []
    
    for item in raw_items:
        scope = item["scope"]
        aid = item["aid"]
        title = item["title"]
        effective = item["effective"]
        
        # Conflict detection
        conflict_ids = []
        has_conflict = False
        
        if effective:
            same_scope_users = usage_map.get(scope, {}).get(effective, [])
            for other_aid in same_scope_users:
                if other_aid != aid:
                    conflict_ids.append(other_aid)
                    
        if conflict_ids:
            has_conflict = True
            
        # Filters
        if scope_filter != "all" and scope != scope_filter:
            continue
            
        if show_conflicts_only and not has_conflict:
            continue
            
        if q_norm:
            if (q_norm not in title.lower() and 
                q_norm not in aid.lower() and 
                q_norm not in effective.lower()):
                continue
                
        final_rows.append(KeybindRow(
            scope=scope,
            action_id=aid,
            title=title,
            shortcut_effective=effective,
            shortcut_default=item["default"],
            has_override=item["has_override"],
            conflict_ids=tuple(sorted(conflict_ids))
        ))
        
    # Sort
    # 1. Conflicts on top
    # 2. Scope (alpha)
    # 3. Title (alpha)
    final_rows.sort(key=lambda r: (not bool(r.conflict_ids), r.scope, r.title))
    
    return tuple(final_rows)

def update_recording_preview(
    state: KeybindsState, 
    shortcut: str, 
    all_actions: Sequence[Any] # Needed to check conflicts against
) -> KeybindsState:
    """Update recording preview and calculate hypothetical conflicts."""
    if not state.recording or not state.recording_target:
        return state
        
    target_scope, target_aid = state.recording_target
    
    # We need to simulate the conflict check
    # We check if 'shortcut' is used by any *other* action in the *same* scope.
    
    conflicts = []
    
    # We need to know effective shortcuts of everything else.
    # This loop is slightly expensive (O(N)), but N ~200 actions, ok for UI event.
    for action in all_actions:
        aid = getattr(action, "id", "")
        # Skip self
        if aid == target_aid:
            continue
            
        a_scope = getattr(action, "shortcut_scope", "global")
        if a_scope != target_scope:
            continue
            
        # Determine effective shortcut of OTHER action
        default = getattr(action, "shortcut", "") or ""
        override = state.staged_overrides.get((a_scope, aid))
        
        eff = default
        if override is not None:
            eff = override # can be ""
            
        if eff == shortcut:
            conflicts.append((a_scope, aid))
    
    if conflicts:
        conflicts.sort()
        
    return replace(
        state,
        pending_record_shortcut=shortcut,
        pending_conflicts=tuple(conflicts)
    )

def apply_staged_override(
    state: KeybindsState, 
    scope: str, 
    action_id: str, 
    shortcut: Optional[str]
) -> KeybindsState:
    """Stage a new shortcut (or None to unbind/reset)."""
    new_overrides = dict(state.staged_overrides)
    
    if shortcut is None:
        # Reset to default
        if (scope, action_id) in new_overrides:
            del new_overrides[(scope, action_id)]
    else:
        # Set specific (empty string = unbind)
        new_overrides[(scope, action_id)] = shortcut
        
    return replace(
        state, 
        staged_overrides=new_overrides, 
        recording=False, 
        recording_target=None,
        pending_record_shortcut=None,
        pending_conflicts=()
    )

def begin_recording(state: KeybindsState, scope: str, action_id: str) -> KeybindsState:
    return replace(
        state, 
        recording=True, 
        recording_target=(scope, action_id),
        pending_record_shortcut=None,
        pending_conflicts=()
    )

def cancel_recording(state: KeybindsState) -> KeybindsState:
    return replace(
        state, 
        recording=False, 
        recording_target=None,
        pending_record_shortcut=None,
        pending_conflicts=()
    )

def should_enable_apply(state: KeybindsState) -> bool:
    """Return True if there are staged changes."""
    return True 

def commit_recorded_key(
    state: KeybindsState, 
    key_name: str, 
    modifiers_str: str
) -> KeybindsState:
    """
    Commit a recorded keypress to the recording target.
    
    key_name: e.g. "F", "Enter"
    modifiers_str: e.g. "Ctrl+Shift"
    """
    if not state.recording or not state.recording_target:
        return state
        
    combo = key_name
    if modifiers_str:
        combo = f"{modifiers_str}+{key_name}"
        
    # Simplify/Normalize?
    # Assuming inputs are already normalized strings like "Ctrl+S"
    
    scope, aid = state.recording_target
    return apply_staged_override(state, scope, aid, combo)

class _RawItem(TypedDict):
    scope: str
    aid: str
    title: str
    effective: str
    default: str
    has_override: bool
