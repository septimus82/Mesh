from __future__ import annotations

from typing import Any

from ._shared import (
    _get_authored_payload,
    _get_selection_ids_and_primary,
    _list_behaviour_names_cached,
    _list_prefab_ids_from_assets_cached,
    _parse_float,
    _parse_toast_and_seconds,
    _set_last_config_action,
    _set_last_props_action,
)


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


def action_props_remove_tag(w: Any, arg: str | None) -> None:
    """Remove tag from selected entities."""
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
        if wanted in existing:
            change_count += 1
    if change_count <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_tag")
    sc = getattr(w, "scene_controller", None)
    remover = getattr(sc, "debug_remove_tag", None) if sc is not None else None
    if not callable(remover):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = remover(selected_ids, wanted)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_tag")
    _set_last_props_action(w, action="remove_tag", changed=int(changed))
    print(f"ENTITY_PROPS ok action=remove_tag changed={int(changed)} skipped_player={int(skipped)}")


def action_props_toggle_tag(w: Any, arg: str | None) -> None:
    """Toggle tag on selected entities (add if missing, remove if present)."""
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
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_props_tag")
    sc = getattr(w, "scene_controller", None)
    toggler = getattr(sc, "debug_toggle_tag", None) if sc is not None else None
    if not callable(toggler):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    added, removed, skipped = toggler(selected_ids, wanted)
    total = added + removed
    if total <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_props_tag")
    _set_last_props_action(w, action="toggle_tag", changed=total)
    print(f"ENTITY_PROPS ok action=toggle_tag added={added} removed={removed} skipped_player={skipped}")


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
