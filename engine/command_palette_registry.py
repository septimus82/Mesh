"""Command palette registry - extracted helper functions and command definitions.

This module contains the extracted helper functions and command definitions
that were previously nested inside build_default_commands(). The refactoring
reduces cyclomatic complexity while maintaining identical behavior.

The command definitions are stored in DEFAULT_COMMAND_DEFS as a deterministic
ordered list. Each definition is converted to a CommandSpec at runtime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from engine.command_palette import CommandSpec, PromptSpec

# ---------------------------------------------------------------------------
# Lazy imports cached once
# ---------------------------------------------------------------------------

def _list_prefab_ids_from_assets_cached() -> tuple[str, ...]:
    """Return cached list of prefab IDs from assets/prefabs.json."""
    from engine.command_palette import _list_prefab_ids_from_assets
    return _list_prefab_ids_from_assets()


def _list_behaviour_names_cached() -> tuple[str, ...]:
    """Return cached list of behaviour names from the registry."""
    from engine.command_palette import _list_behaviour_names
    return _list_behaviour_names()


# ---------------------------------------------------------------------------
# Enablement checks - pure functions taking window (w) -> (bool, reason)
# ---------------------------------------------------------------------------

def enabled_always(_w: Any) -> tuple[bool, str]:
    """Always enabled."""
    return True, ""


def enabled_has_scene(w: Any) -> tuple[bool, str]:
    """Enabled when a scene is loaded."""
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return False, "no_scene"
    return True, ""


def enabled_has_scene_and_authored_payload(w: Any) -> tuple[bool, str]:
    """Enabled when a scene with authored payload is loaded."""
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    return True, ""


def enabled_scene_persist_armed(w: Any) -> tuple[bool, str]:
    """Enabled when scene is loaded and persist is armed."""
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_persist_armed_only(w: Any) -> tuple[bool, str]:
    """Enabled when persist is armed (no scene required)."""
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_scene_index_nonempty(_w: Any) -> tuple[bool, str]:
    """Enabled when scene index has at least one scene."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415
    paths = iter_known_scene_paths()
    if not paths:
        return False, "no_scenes"
    return True, ""


def enabled_recent_nonempty(w: Any) -> tuple[bool, str]:
    """Enabled when there are recent scenes."""
    getter = getattr(w, "get_recent_scenes", None)
    recent = getter() if callable(getter) else []
    if not isinstance(recent, list) or not recent:
        return False, "empty"
    return True, ""


def enabled_selection_has_non_player(w: Any) -> tuple[bool, str]:
    """Enabled when selection contains at least one non-player entity."""
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        return False, "no_selection"
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    non_player, saw_player = _selection_non_player_ids(w, selected_ids)
    if not non_player and saw_player:
        return False, "only_player"
    if not non_player:
        return False, "no_selection"
    return True, ""


def enabled_selection_has_primary_non_player(w: Any) -> tuple[bool, str]:
    """Enabled when selection has a non-player primary (or deterministic fallback)."""
    selected_ids, primary_id = _get_selection_ids_and_primary(w)
    if not selected_ids:
        return False, "no_selection"
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    non_player, saw_player = _selection_non_player_ids(w, selected_ids)
    if not non_player and saw_player:
        return False, "only_player"
    if not non_player:
        return False, "no_selection"
    # Primary might be the player; still allow since we can deterministically pick a non-player primary.
    return True, ""


# ---------------------------------------------------------------------------
# Helper functions for selection/entity data
# ---------------------------------------------------------------------------

def _get_selection_ids_and_primary(w: Any) -> tuple[list[str], str]:
    """Return (selected_ids, primary_id) from entity_select_state."""
    state = getattr(w, "entity_select_state", None)
    ids = getattr(state, "selected_ids", None) if state is not None else None
    if not isinstance(ids, list):
        ids = []
    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    primary_id = getattr(state, "primary_id", None) if state is not None else None
    primary_id = str(primary_id).strip() if isinstance(primary_id, str) and str(primary_id).strip() else (selected_ids[0] if selected_ids else "")
    return selected_ids, primary_id


def _get_authored_payload(w: Any) -> dict[str, Any] | None:
    """Return the authored scene payload dict, or None."""
    sc = getattr(w, "scene_controller", None)
    getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    payload = getter() if callable(getter) else None
    return payload if isinstance(payload, dict) else None


def _selection_non_player_ids(w: Any, selected_ids: list[str]) -> tuple[list[str], bool]:
    """Return (non_player_ids, saw_player) for given selection."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415
    authored = _get_authored_payload(w)
    if authored is None:
        return ([], False)
    entities = ensure_entities_list(authored)
    non_player: list[str] = []
    saw_player = False
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            saw_player = True
            continue
        non_player.append(entity_id)
    return (sorted(set(non_player)), saw_player)


def _parse_float(text: str) -> float | None:
    """Parse float from text, returning None on failure."""
    try:
        return float(str(text).strip())
    except Exception:  # noqa: BLE001
        return None


def _entity_has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
    """Check if entity has a behaviour of given type."""
    behaviours = ent.get("behaviours")
    if not isinstance(behaviours, list):
        return False
    for b in behaviours:
        if isinstance(b, str) and b.strip() == behaviour:
            return True
        if isinstance(b, dict):
            bt = b.get("type")
            if isinstance(bt, str) and bt.strip() == behaviour:
                return True
    return False


# ---------------------------------------------------------------------------
# Options providers - functions returning [(value, label), ...]
# ---------------------------------------------------------------------------

def options_all_scenes(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415
    paths = iter_known_scene_paths()
    return [(p, p) for p in paths]


def options_recent_scenes(w: Any) -> list[tuple[str, str]]:
    """Return recent scene paths as options."""
    getter = getattr(w, "get_recent_scenes", None)
    recent = getter() if callable(getter) else []
    if not isinstance(recent, list):
        recent = []
    out: list[tuple[str, str]] = []
    for p in recent:
        if isinstance(p, str) and p.strip():
            out.append((p.strip(), p.strip()))
    return out


def options_prefab_ids(_w: Any) -> list[tuple[str, str]]:
    """Return all prefab IDs as options."""
    ids = _list_prefab_ids_from_assets_cached()
    return [(pid, pid) for pid in ids]


def options_behaviour_names(_w: Any) -> list[tuple[str, str]]:
    """Return all behaviour names as options."""
    names = _list_behaviour_names_cached()
    return [(n, n) for n in names]


def options_behaviours_in_selection(w: Any) -> list[tuple[str, str]]:
    """Return behaviours present in selected entities as options."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415
    authored = _get_authored_payload(w)
    if authored is None:
        return []
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    entities = ensure_entities_list(authored)

    names: set[str] = set()
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            continue
        for b in behaviours:
            if isinstance(b, str) and b.strip():
                names.add(b.strip())
            elif isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip():
                    names.add(bt.strip())
    return [(n, n) for n in sorted(names)]


def options_scene_paths(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options (alias for options_all_scenes)."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415
    return [(p, p) for p in iter_known_scene_paths()]


def options_dialogue_speakers(w: Any) -> list[tuple[str, str]]:
    """Return entity IDs of dialogue speakers in scene."""
    from engine.entity_paint_mode import ensure_entities_list  # noqa: PLC0415
    authored = _get_authored_payload(w)
    if authored is None:
        return []
    entities = ensure_entities_list(authored)
    out: list[tuple[str, str]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if not _entity_has_behaviour(ent, "Dialogue"):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            out.append((entity_id.strip(), entity_id.strip()))
    out.sort(key=lambda pair: pair[0])
    return out


def options_macro_anchor(w: Any) -> list[tuple[str, str]]:
    """Return anchor options for macros."""
    selected_ids, _primary_id = _get_selection_ids_and_primary(w)
    base = [("cursor", "cursor"), ("player", "player")]
    if selected_ids:
        return [("primary", "primary"), *base]
    return base


# ---------------------------------------------------------------------------
# Default value providers
# ---------------------------------------------------------------------------

def default_empty(_w: Any) -> str:
    """Return empty string as default."""
    return ""


def default_save_as(_w: Any) -> str:
    """Return empty string for save-as default."""
    return ""


def default_scene_create(w: Any) -> str:
    """Return default path for scene creation."""
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return "scenes/new_scene.json"
    base = Path(scene_path)
    return str(base.parent / f"{base.stem}__new.json")


def default_cursor(_w: Any) -> str:
    """Return 'cursor' as default anchor."""
    return "cursor"


def default_radius_72(_w: Any) -> str:
    """Return '72' as default radius."""
    return "72"


# ---------------------------------------------------------------------------
# Action handlers - functions taking (window, arg) -> None
# ---------------------------------------------------------------------------

def action_toggle_tile_paint(w: Any, _arg: str | None) -> None:
    """Toggle tile paint mode."""
    state = getattr(w, "tile_paint_state", None)
    if state is None:
        return
    state.enabled = not bool(getattr(state, "enabled", False))
    if bool(getattr(state, "enabled", False)) and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(w, "scene_controller", None)
        payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        tilemap_value = payload.get("tilemap") if isinstance(payload, dict) else None
        tilemap = tilemap_value if isinstance(tilemap_value, dict) else {}
        from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415
        tile_layers = tilemap.get("tile_layers")
        tile_layers_list = tile_layers if isinstance(tile_layers, list) else []
        state.layer_id = cycle_layer_id(tile_layers=tile_layers_list, current="", direction=1)


def action_toggle_entity_paint(w: Any, _arg: str | None) -> None:
    """Toggle entity paint mode."""
    from engine.entity_paint_mode import EntityPaintState, load_prefab_infos  # noqa: PLC0415
    state = getattr(w, "entity_paint_state", None)
    if not isinstance(state, EntityPaintState):
        return
    state.enabled = not bool(getattr(state, "enabled", False))
    if state.enabled and not getattr(state, "prefabs", ()):
        state.prefabs = load_prefab_infos()
        state.selected_index = 0
    if not state.enabled:
        state.persist_armed = False


def action_toggle_palette_mode(_w: Any, _arg: str | None) -> None:
    """Toggle palette mode."""
    from engine.palette_mode import toggle_palette  # noqa: PLC0415
    toggle_palette()


def action_toggle_capture(w: Any, _arg: str | None) -> None:
    """Toggle capture mode."""
    from engine.capture_mode import CaptureState, iter_layer_ids_sorted_by_z_id  # noqa: PLC0415
    state = getattr(w, "capture_state", None)
    if not isinstance(state, CaptureState):
        state = CaptureState()
        w.capture_state = state
    state.enabled = not bool(getattr(state, "enabled", False))
    state.drag_anchor = None
    state.rect = None
    if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(w, "scene_controller", None)
        payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if isinstance(payload, dict):
            ids = iter_layer_ids_sorted_by_z_id(payload)
            state.layer_id = ids[0] if ids else ""


def action_toggle_ghost_originals(w: Any, _arg: str | None) -> None:
    """Toggle ghost originals display."""
    editor = getattr(w, "editor_controller", None)
    if editor is None:
        return
    toggler = getattr(editor, "toggle_ghost_originals", None)
    if callable(toggler):
        toggler()


def action_scene_reload(w: Any, _arg: str | None) -> None:
    """Reload current scene from disk."""
    reloader = getattr(w, "reload_scene_from_disk", None)
    ok = bool(reloader()) if callable(reloader) else False
    print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")


def action_scene_toggle_persist_armed(w: Any, _arg: str | None) -> None:
    """Toggle scene persist armed state."""
    w.scene_persist_armed = not bool(getattr(w, "scene_persist_armed", False))
    print(f"SCENE_PERSIST_ARMED {'on' if w.scene_persist_armed else 'off'}")


def action_scene_persist(w: Any, _arg: str | None) -> None:
    """Persist scene to disk (if armed)."""
    if not bool(getattr(w, "scene_persist_armed", False)):
        print("SCENE_PERSIST (not armed)")
        return
    persister = getattr(w, "persist_scene_to_disk", None)
    result = persister() if callable(persister) else None
    ok = bool(getattr(result, "ok", False))
    path = str(getattr(result, "path", "") or "").strip()
    print(f"SCENE_PERSIST {'ok' if ok else 'fail'} path={path or '-'}")


def action_scene_save_as(w: Any, arg: str | None) -> None:
    """Save scene to a new path."""
    saver = getattr(w, "save_scene_as", None)
    new_path = str(arg or "").strip()
    result = saver(new_path) if callable(saver) else None
    ok = bool(getattr(result, "ok", False))
    out_path = str(getattr(result, "path", "") or "").strip()
    if ok and out_path:
        print(f"TIP: python -m mesh_cli world add-scene worlds/main_world.json --key <key> --path {out_path}")


def action_scene_create(w: Any, arg: str | None) -> None:
    """Create a new empty scene file."""
    from engine.tooling_runtime.scene_create import create_empty_scene_file  # noqa: PLC0415
    path = str(arg or "").strip()
    if not path:
        print("SCENE_CREATE fail path=- reason=empty_path")
        return
    name = Path(path).stem
    result = create_empty_scene_file(path, name=name)
    reason = ",".join(result.errors) if result.errors else "-"
    print(f"SCENE_CREATE {'ok' if result.ok else 'fail'} path={result.path} reason={reason}")


def action_go_to_scene(w: Any, arg: str | None) -> None:
    """Go to a specific scene."""
    requester = getattr(w, "request_scene_change", None)
    if not callable(requester):
        return
    path = str(arg or "").strip()
    if not path:
        return
    requester(path)


def action_recent_scene(w: Any, arg: str | None) -> None:
    """Open a recent scene."""
    return action_go_to_scene(w, arg)


# ---------------------------------------------------------------------------
# Selection property actions
# ---------------------------------------------------------------------------

def _set_last_props_action(w: Any, *, action: str, changed: int) -> None:
    """Record last property action for repeat commands."""
    try:
        w.last_props_action = str(action)
        w.last_props_changed = int(changed)
        w.last_props_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001
        pass


def _set_last_config_action(w: Any, *, action: str, changed: int) -> None:
    """Record last config action for repeat commands."""
    try:
        w.last_config_action = str(action)
        w.last_config_changed = int(changed)
        w.last_config_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001
        pass


def action_props_set_prefab_id(w: Any, arg: str | None) -> None:
    """Set prefab ID for selected entities."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    wanted = str(arg or "").strip()
    if not wanted:
        print("ENTITY_PROPS noop reason=empty_prefab_id")
        return
    if wanted not in _list_prefab_ids_from_assets_cached():
        print("ENTITY_PROPS noop reason=unknown_prefab")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)
    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if ent.get("prefab_id") != wanted:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_prefab")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_set_prefab_id", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = setter(selected_ids, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_prefab")
    _set_last_props_action(w, action="set_prefab_id", changed=int(changed))
    print(f"ENTITY_PROPS ok action=set_prefab_id changed={int(changed)} skipped_player={int(skipped)}")


def action_props_add_behaviour(w: Any, arg: str | None) -> None:
    """Add behaviour to selected entities."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    wanted = str(arg or "").strip()
    if not wanted:
        print("ENTITY_PROPS noop reason=empty_behaviour")
        return
    if wanted not in _list_behaviour_names_cached():
        print("ENTITY_PROPS noop reason=unknown_behaviour")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)
    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        behaviours = ent.get("behaviours")
        existing: set[str] = set()
        if isinstance(behaviours, list):
            for b in behaviours:
                if isinstance(b, str) and b.strip():
                    existing.add(b.strip())
                elif isinstance(b, dict):
                    bt = b.get("type")
                    if isinstance(bt, str) and bt.strip():
                        existing.add(bt.strip())
        if wanted not in existing:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_add_behaviour")
    sc = getattr(w, "scene_controller", None)
    adder = getattr(sc, "debug_add_behaviour", None) if sc is not None else None
    if not callable(adder):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = adder(selected_ids, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_add_behaviour")
    _set_last_props_action(w, action="add_behaviour", changed=int(changed))
    print(f"ENTITY_PROPS ok action=add_behaviour changed={int(changed)} skipped_player={int(skipped)}")


def action_props_remove_behaviour(w: Any, arg: str | None) -> None:
    """Remove behaviour from selected entities."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    wanted = str(arg or "").strip()
    if not wanted:
        print("ENTITY_PROPS noop reason=empty_behaviour")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)
    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            continue
        for b in behaviours:
            if isinstance(b, str) and b.strip() == wanted:
                change_count += 1
                break
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == wanted:
                    change_count += 1
                    break
    if change_count <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_remove_behaviour")
    sc = getattr(w, "scene_controller", None)
    remover = getattr(sc, "debug_remove_behaviour", None) if sc is not None else None
    if not callable(remover):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = remover(selected_ids, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_remove_behaviour")
    _set_last_props_action(w, action="remove_behaviour", changed=int(changed))
    print(f"ENTITY_PROPS ok action=remove_behaviour changed={int(changed)} skipped_player={int(skipped)}")


def action_props_set_name(w: Any, arg: str | None) -> None:
    """Set name for primary selected entity."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, primary_id = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    wanted = str(arg or "").strip()
    if not wanted:
        print("ENTITY_PROPS noop reason=empty_name")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)
    primary_ent = find_entity_by_id(entities, primary_id)
    if not isinstance(primary_ent, dict) or is_player_entity(primary_ent):
        primary_id = ""
        for candidate in selected_ids:
            ent = find_entity_by_id(entities, candidate)
            if isinstance(ent, dict) and not is_player_entity(ent):
                primary_id = candidate
                primary_ent = ent
                break
    if not primary_id or not isinstance(primary_ent, dict):
        print("ENTITY_PROPS noop reason=only_player")
        return
    if primary_ent.get("name") == wanted:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_name")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_set_name", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = setter(primary_id, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_name")
    _set_last_props_action(w, action="set_name", changed=int(changed))
    print(f"ENTITY_PROPS ok action=set_name changed={int(changed)} skipped_player={int(skipped)}")


def action_props_add_tag(w: Any, arg: str | None) -> None:
    """Add tag to selected entities."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    wanted = str(arg or "").strip()
    if not wanted:
        print("ENTITY_PROPS noop reason=empty_tag")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)
    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        tags = ent.get("tags")
        existing = {str(t).strip() for t in tags if isinstance(t, str) and str(t).strip()} if isinstance(tags, list) else set()
        if wanted not in existing:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_tag")
    sc = getattr(w, "scene_controller", None)
    adder = getattr(sc, "debug_add_tag", None) if sc is not None else None
    if not callable(adder):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = adder(selected_ids, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_tag")
    _set_last_props_action(w, action="add_tag", changed=int(changed))
    print(f"ENTITY_PROPS ok action=add_tag changed={int(changed)} skipped_player={int(skipped)}")


# ---------------------------------------------------------------------------
# Entity config actions (TriggerZone, SetGameStateOnEvent, SceneTransition)
# ---------------------------------------------------------------------------

def action_config_tz_set_zone_id(w: Any, arg: str | None) -> None:
    """Set zone_id for TriggerZone behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    zone_id = str(arg or "").strip()
    if not zone_id:
        print("ENTITY_CONFIG noop reason=empty_zone_id")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "TriggerZone"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("TriggerZone")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        if cfg.get("zone_id") != zone_id:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_tz_zone_id")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_triggerzone_set_zone_id", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, zone_id)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_tz_zone_id")
    _set_last_config_action(w, action="tz_set_zone_id", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=tz_set_zone_id "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_tz_set_radius(w: Any, arg: str | None) -> None:
    """Set radius for TriggerZone behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    radius_text = str(arg or "").strip()
    radius = _parse_float(radius_text)
    if radius is None:
        print("ENTITY_CONFIG noop reason=bad_float")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "TriggerZone"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("TriggerZone")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        before = cfg.get("trigger_radius")
        if not isinstance(before, (int, float)) or float(before) != float(radius):
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_tz_radius")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_triggerzone_set_radius", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, float(radius))
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_tz_radius")
    _set_last_config_action(w, action="tz_set_radius", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=tz_set_radius "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def _parse_toast_and_seconds(arg: str | None) -> tuple[str, float | None] | None:
    """Parse 'toast[|seconds]' format."""
    raw = str(arg or "").strip()
    if not raw:
        return None
    if "|" not in raw:
        return (raw, None)
    toast_part, seconds_part = raw.rsplit("|", 1)
    toast = toast_part.strip()
    seconds_raw = seconds_part.strip()
    if not toast:
        return None
    if not seconds_raw:
        return (toast, None)
    seconds = _parse_float(seconds_raw)
    if seconds is None:
        return None
    return (toast, float(seconds))


def action_config_sgs_set_toast(w: Any, arg: str | None) -> None:
    """Set toast for SetGameStateOnEvent behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    parsed = _parse_toast_and_seconds(arg)
    if parsed is None:
        print("ENTITY_CONFIG noop reason=bad_toast")
        return
    toast, seconds = parsed
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SetGameStateOnEvent")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        before_toast = cfg.get("toast")
        before_s = cfg.get("toast_seconds")
        before_s_val = float(before_s) if isinstance(before_s, (int, float)) else None
        if seconds is None:
            new_s = before_s_val if isinstance(before_s_val, float) and before_s_val > 0.0 else 3.0
        else:
            new_s = float(seconds)
        if before_toast != toast:
            change_count += 1
            continue
        if before_s_val is None or before_s_val <= 0.0:
            if float(new_s) != float(before_s_val or 0.0):
                change_count += 1
                continue
        elif float(before_s_val) != float(new_s):
            change_count += 1
            continue
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_sgs_toast")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_set_game_state_set_toast", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, toast=toast, toast_seconds=seconds)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_sgs_toast")
    _set_last_config_action(w, action="sgs_set_toast", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=sgs_set_toast "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_sgs_add_require_flag(w: Any, arg: str | None) -> None:
    """Add require flag for SetGameStateOnEvent behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    flag = str(arg or "").strip()
    if not flag:
        print("ENTITY_CONFIG noop reason=empty_flag")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SetGameStateOnEvent")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        req = cfg.get("require_flags")
        existing = {str(v).strip() for v in req if isinstance(v, str) and str(v).strip()} if isinstance(req, list) else set()
        if flag not in existing:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_sgs_require")
    sc = getattr(w, "scene_controller", None)
    adder = getattr(sc, "debug_config_set_game_state_add_require_flag", None) if sc is not None else None
    if not callable(adder):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = adder(selected_ids, flag)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_sgs_require")
    _set_last_config_action(w, action="sgs_add_require_flag", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=sgs_add_require_flag "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_sgs_add_forbid_flag(w: Any, arg: str | None) -> None:
    """Add forbid flag for SetGameStateOnEvent behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    flag = str(arg or "").strip()
    if not flag:
        print("ENTITY_CONFIG noop reason=empty_flag")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SetGameStateOnEvent")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        forbid = cfg.get("forbid_flags")
        existing = {str(v).strip() for v in forbid if isinstance(v, str) and str(v).strip()} if isinstance(forbid, list) else set()
        if flag not in existing:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_sgs_forbid")
    sc = getattr(w, "scene_controller", None)
    adder = getattr(sc, "debug_config_set_game_state_add_forbid_flag", None) if sc is not None else None
    if not callable(adder):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = adder(selected_ids, flag)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_sgs_forbid")
    _set_last_config_action(w, action="sgs_add_forbid_flag", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=sgs_add_forbid_flag "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_sgs_set_flag_true(w: Any, arg: str | None) -> None:
    """Set flag to true for SetGameStateOnEvent behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    flag = str(arg or "").strip()
    if not flag:
        print("ENTITY_CONFIG noop reason=empty_flag")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SetGameStateOnEvent")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        flags = cfg.get("set_flags")
        before = flags.get(flag) if isinstance(flags, dict) else None
        if before is not True:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_sgs_set_flag_true")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_set_game_state_set_flag_true", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, flag)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_sgs_set_flag_true")
    _set_last_config_action(w, action="sgs_set_flag_true", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=sgs_set_flag_true "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_st_set_target_scene(w: Any, arg: str | None) -> None:
    """Set target scene for SceneTransition behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    target_scene = str(arg or "").strip()
    if not target_scene:
        print("ENTITY_CONFIG noop reason=empty_scene")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SceneTransition"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SceneTransition")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        if cfg.get("target_scene") != target_scene:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_st_target_scene")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_scene_transition_set_target_scene", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, target_scene)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_st_target_scene")
    _set_last_config_action(w, action="st_set_target_scene", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=st_set_target_scene "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


def action_config_st_set_spawn_id(w: Any, arg: str | None) -> None:
    """Set spawn id for SceneTransition behaviour."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_CONFIG noop reason=no_selection")
        return
    spawn_id = str(arg or "").strip()
    if not spawn_id:
        print("ENTITY_CONFIG noop reason=empty_spawn_id")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_CONFIG noop reason=no_authored_payload")
        return
    entities = ensure_entities_list(authored)

    change_count = 0
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SceneTransition"):
            continue
        root_value = ent.get("behaviour_config")
        root = root_value if isinstance(root_value, dict) else {}
        cfg_value = root.get("SceneTransition")
        cfg = cfg_value if isinstance(cfg_value, dict) else {}
        if cfg.get("spawn_id") != spawn_id or cfg.get("spawn_point") != spawn_id:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_config_st_spawn_id")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_config_scene_transition_set_spawn_id", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_CONFIG noop reason=no_scene_controller")
        return
    changed, skipped_player, skipped_no_behaviour = setter(selected_ids, spawn_id)
    if changed <= 0:
        print("ENTITY_CONFIG noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_config_st_spawn_id")
    _set_last_config_action(w, action="st_set_spawn_id", changed=int(changed))
    print(
        "ENTITY_CONFIG ok action=st_set_spawn_id "
        f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
    )


# ---------------------------------------------------------------------------
# Macro helpers
# ---------------------------------------------------------------------------

def _get_player_pos_from_authored(w: Any) -> tuple[float, float] | None:
    """Get player position from authored payload."""
    from engine.entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415
    authored = _get_authored_payload(w)
    if authored is None:
        return None
    entities = ensure_entities_list(authored)
    for ent in entities:
        if not isinstance(ent, dict) or not is_player_entity(ent):
            continue
        try:
            x = float(ent.get("x", 0.0))
        except Exception:  # noqa: BLE001
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001
            y = 0.0
        return float(x), float(y)
    return None


def _get_entity_pos_from_authored(w: Any, entity_id: str) -> tuple[float, float] | None:
    """Get entity position from authored payload by ID."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415
    authored = _get_authored_payload(w)
    if authored is None:
        return None
    entities = ensure_entities_list(authored)
    ent = find_entity_by_id(entities, entity_id)
    if not isinstance(ent, dict):
        return None
    try:
        x = float(ent.get("x", 0.0))
    except Exception:  # noqa: BLE001
        x = 0.0
    try:
        y = float(ent.get("y", 0.0))
    except Exception:  # noqa: BLE001
        y = 0.0
    return float(x), float(y)


def _get_cursor_world_pos(w: Any) -> tuple[float, float] | None:
    """Get cursor position in world coordinates."""
    input_ctrl = getattr(w, "input_controller", None)
    mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
    my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
    to_world = getattr(w, "screen_to_world", None)
    if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
        try:
            x, y = to_world(float(mx), float(my))
        except Exception:  # noqa: BLE001
            return None
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return float(x), float(y)
    return None


def _resolve_macro_anchor_pos(w: Any, anchor: str) -> tuple[tuple[float, float] | None, str]:
    """Resolve anchor position for macros."""
    a = str(anchor or "").strip().lower()
    if a == "primary":
        selected_ids, primary_id = _get_selection_ids_and_primary(w)
        if not selected_ids or not primary_id:
            return None, "no_selection"
        pos = _get_entity_pos_from_authored(w, primary_id)
        if pos is None:
            return None, "no_selection"
        return pos, ""
    if a == "player":
        pos = _get_player_pos_from_authored(w)
        if pos is None:
            return (0.0, 0.0), ""
        return pos, ""
    # Default: cursor (fallback to player).
    pos = _get_cursor_world_pos(w)
    if pos is not None:
        return pos, ""
    pos = _get_player_pos_from_authored(w)
    if pos is None:
        return (0.0, 0.0), ""
    return pos, ""


# ---------------------------------------------------------------------------
# Macro actions
# ---------------------------------------------------------------------------

def action_macro_objective_zone(w: Any, arg: str | None) -> None:
    """Execute objective zone macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}

    anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
    zone_id = str(data.get("zone_id") or "").strip()
    set_flag = str(data.get("set_flag") or "").strip()
    radius_raw = str(data.get("radius") or "").strip()
    toast = str(data.get("toast") or "")
    toast = toast.strip() if isinstance(toast, str) else ""
    toast_val = toast if toast else None
    req_raw = data.get("require_flags")
    forb_raw = data.get("forbid_flags")
    toast_seconds_raw = data.get("toast_seconds")
    require_flags = [str(v).strip() for v in (req_raw or []) if isinstance(req_raw, list) and str(v).strip()] if isinstance(req_raw, list) else None
    forbid_flags = [str(v).strip() for v in (forb_raw or []) if isinstance(forb_raw, list) and str(v).strip()] if isinstance(forb_raw, list) else None
    toast_seconds: float | None
    if toast_seconds_raw is None or toast_seconds_raw == "":
        toast_seconds = None
    else:
        try:
            toast_seconds = float(toast_seconds_raw)
        except Exception:  # noqa: BLE001
            toast_seconds = None
    try:
        radius = float(radius_raw)
    except Exception:  # noqa: BLE001
        print("AUTHOR_MACRO noop reason=bad_args")
        return
    if not zone_id or not set_flag:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    pos, reason = _resolve_macro_anchor_pos(w, anchor)
    if reason:
        print(f"AUTHOR_MACRO noop reason={reason}")
        return
    if pos is None:
        pos = (0.0, 0.0)

    payload_new, created, updated = sc.debug_build_macro_objective_zone_payload(
        center_x=float(pos[0]),
        center_y=float(pos[1]),
        zone_id=zone_id,
        set_flag=set_flag,
        radius=float(radius),
        toast=toast_val,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_objective_zone")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_objective_zone")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        stored: dict[str, Any] = {
            "anchor": anchor,
            "zone_id": zone_id,
            "set_flag": set_flag,
            "radius": float(radius),
            "toast": toast,
        }
        if "toast_seconds" in data:
            stored["toast_seconds"] = float(toast_seconds) if isinstance(toast_seconds, (int, float)) else ""
        if "require_flags" in data:
            stored["require_flags"] = require_flags or []
        if "forbid_flags" in data:
            stored["forbid_flags"] = forbid_flags or []
        last_args["macro.objective_zone"] = stored
    print(f"AUTHOR_MACRO ok action=objective_zone created={int(created)} updated={int(updated)}")


def action_macro_door_transition(w: Any, arg: str | None) -> None:
    """Execute door transition macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}

    anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
    target_scene = str(data.get("target_scene") or "").strip()
    spawn_id = str(data.get("spawn_id") or "").strip()
    if not target_scene or not spawn_id:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    _selected_ids, primary_id = _get_selection_ids_and_primary(w)
    pos, reason = _resolve_macro_anchor_pos(w, anchor)
    if reason:
        print(f"AUTHOR_MACRO noop reason={reason}")
        return
    if pos is None:
        pos = (0.0, 0.0)
    payload_new, created, updated = sc.debug_build_macro_door_transition_payload(
        center_x=float(pos[0]),
        center_y=float(pos[1]),
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id if primary_id else None,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_door_transition")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_door_transition")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        last_args["macro.door_transition"] = {
            "anchor": anchor,
            "target_scene": target_scene,
            "spawn_id": spawn_id,
        }
    print(f"AUTHOR_MACRO ok action=door_transition created={int(created)} updated={int(updated)}")


def action_macro_dialogue_choice_flag(w: Any, arg: str | None) -> None:
    """Execute dialogue choice flag macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}

    speaker_id = str(data.get("speaker_id") or "").strip()
    choice_id = str(data.get("choice_id") or "").strip()
    choice_text = str(data.get("choice_text") or "").strip()
    set_flag = str(data.get("set_flag") or "").strip()
    toast = str(data.get("toast") or "")
    toast = toast.strip() if isinstance(toast, str) else ""
    toast_val = toast if toast else None
    if not speaker_id or not choice_id or not choice_text or not set_flag:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    payload_new, created, updated = sc.debug_build_macro_dialogue_choice_flag_payload(
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast_val,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_dialogue_choice_flag")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_dialogue_choice_flag")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        last_args["macro.dialogue_choice_flag"] = {
            "speaker_id": speaker_id,
            "choice_id": choice_id,
            "choice_text": choice_text,
            "set_flag": set_flag,
            "toast": toast,
        }
    print(f"AUTHOR_MACRO ok action=dialogue_choice_flag created={int(created)} updated={int(updated)}")


# ---------------------------------------------------------------------------
# Macro runners registry (used by macro asset commands)
# ---------------------------------------------------------------------------

MACRO_RUNNERS: dict[str, Callable[[Any, str | None], None]] = {
    "macro.objective_zone": action_macro_objective_zone,
    "macro.door_transition": action_macro_door_transition,
    "macro.dialogue_choice_flag": action_macro_dialogue_choice_flag,
}
