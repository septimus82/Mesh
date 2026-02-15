from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from .entity_ops import get_authored_scene_payload

if TYPE_CHECKING:
    from ...scene_controller import SceneController


def debug_build_macro_objective_zone_payload(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored scene payload with a TriggerZone + SetGameStateOnEvent pair.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ...entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415
    from ...entity_paint_mode import _format_id_number as _fmt  # noqa: PLC0415
    from ...entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    zid = str(zone_id or "").strip()
    flag = str(set_flag or "").strip()
    zid_tok = _san(zid)
    flag_tok = _san(flag)

    x = float(center_x)
    y = float(center_y)
    x_tok = _fmt(x)
    y_tok = _fmt(y)

    trigger_id = f"{stem}_macro_triggerzone_{zid_tok}_{x_tok}_{y_tok}_0_0"
    hook_id = f"{stem}_macro_setflag_{flag_tok}_{zid_tok}_{x_tok}_{y_tok}_0_0"

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            behaviours = []
            ent["behaviours"] = behaviours
        if _has_behaviour(ent, behaviour):
            return False
        behaviours.append(behaviour)
        return True

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    def _set_field(ent: dict[str, Any], key: str, value: Any) -> bool:
        if ent.get(key) == value:
            return False
        ent[key] = value
        return True

    def _apply_triggerzone(ent: dict[str, Any]) -> bool:
        changed_any = False
        changed_any = _ensure_behaviour(ent, "TriggerZone") or changed_any
        changed_any = _set_field(ent, "x", x) or changed_any
        changed_any = _set_field(ent, "y", y) or changed_any
        if zid:
            changed_any = _set_field(ent, "name", zid) or changed_any
        changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
        changed_any = _set_field(ent, "tag", ent.get("tag") or "trigger") or changed_any
        changed_any = _set_field(ent, "scale", float(ent.get("scale", 0.0) or 0.0)) or changed_any
        if require_flags is not None:
            req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
        if forbid_flags is not None:
            forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
        cfg = _ensure_cfg(ent, "TriggerZone")
        if cfg.get("zone_id") != zid:
            cfg["zone_id"] = zid
            changed_any = True
        if cfg.get("trigger_target") != "Player":
            cfg["trigger_target"] = "Player"
            changed_any = True
        if cfg.get("trigger_radius") != float(radius):
            cfg["trigger_radius"] = float(radius)
            changed_any = True
        return changed_any

    def _apply_set_flag(ent: dict[str, Any]) -> bool:
        changed_any = False
        changed_any = _ensure_behaviour(ent, "SetGameStateOnEvent") or changed_any
        changed_any = _set_field(ent, "x", x) or changed_any
        changed_any = _set_field(ent, "y", y) or changed_any
        changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
        changed_any = _set_field(ent, "tag", ent.get("tag") or "trigger") or changed_any
        changed_any = _set_field(ent, "scale", float(ent.get("scale", 0.0) or 0.0)) or changed_any
        if flag:
            changed_any = _set_field(ent, "name", ent.get("name") or f"SetFlag:{flag}") or changed_any
        if require_flags is not None:
            req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
        if forbid_flags is not None:
            forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
        cfg = _ensure_cfg(ent, "SetGameStateOnEvent")
        if cfg.get("event_type") != "entered_zone":
            cfg["event_type"] = "entered_zone"
            changed_any = True
        if cfg.get("payload_field") != "zone":
            cfg["payload_field"] = "zone"
            changed_any = True
        if cfg.get("payload_value") != zid:
            cfg["payload_value"] = zid
            changed_any = True
        if cfg.get("once") is not True:
            cfg["once"] = True
            changed_any = True
        if require_flags is not None:
            req = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            if cfg.get("require_flags") != req:
                cfg["require_flags"] = req
                changed_any = True
        if forbid_flags is not None:
            forb = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            if cfg.get("forbid_flags") != forb:
                cfg["forbid_flags"] = forb
                changed_any = True
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            set_flags = {}
            cfg["set_flags"] = set_flags
            changed_any = True
        if flag and set_flags.get(flag) is not True:
            set_flags[flag] = True
            changed_any = True
        toast_text = str(toast or "").strip()
        if toast_text:
            if cfg.get("toast") != toast_text:
                cfg["toast"] = toast_text
                changed_any = True
            if isinstance(toast_seconds, (int, float)) and float(toast_seconds) > 0.0:
                if cfg.get("toast_seconds") != float(toast_seconds):
                    cfg["toast_seconds"] = float(toast_seconds)
                    changed_any = True
            else:
                if not isinstance(cfg.get("toast_seconds"), (int, float)) or float(cfg.get("toast_seconds") or 0.0) <= 0.0:
                    cfg["toast_seconds"] = 3.0
                    changed_any = True
        else:
            if cfg.get("toast") not in (None, ""):
                cfg["toast"] = ""
                changed_any = True
        return changed_any

    trigger_ent = find_entity_by_id(entities, trigger_id)
    if trigger_ent is None:
        entities.append({"id": trigger_id})
        trigger_ent = entities[-1]
        created += 1
        if _apply_triggerzone(trigger_ent):
            updated += 0
    else:
        if isinstance(trigger_ent, dict):
            pid = trigger_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"TriggerZone"}
                and not _has_behaviour(trigger_ent, "TriggerZone")
            ):
                raise ValueError(f"prefab_mismatch id={trigger_id} prefab_id={pid.strip()!r}")
        if _apply_triggerzone(trigger_ent):
            updated += 1

    hook_ent = find_entity_by_id(entities, hook_id)
    if hook_ent is None:
        entities.append({"id": hook_id})
        hook_ent = entities[-1]
        created += 1
        if _apply_set_flag(hook_ent):
            updated += 0
    else:
        if isinstance(hook_ent, dict):
            pid = hook_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"SetGameStateOnEvent"}
                and not _has_behaviour(hook_ent, "SetGameStateOnEvent")
            ):
                raise ValueError(f"prefab_mismatch id={hook_id} prefab_id={pid.strip()!r}")
        if _apply_set_flag(hook_ent):
            updated += 1

    return authored_copy, created, updated

def debug_build_macro_door_transition_payload(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored scene payload that ensures a SceneTransition exists or is updated.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ...entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415
    from ...entity_paint_mode import _format_id_number as _fmt  # noqa: PLC0415
    from ...entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    tgt = str(target_scene or "").strip()
    sp = str(spawn_id or "").strip()

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            behaviours = []
            ent["behaviours"] = behaviours
        if _has_behaviour(ent, behaviour):
            return False
        behaviours.append(behaviour)
        return True

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    def _set_field(ent: dict[str, Any], key: str, value: Any) -> bool:
        if ent.get(key) == value:
            return False
        ent[key] = value
        return True

    # If primary is a SceneTransition, patch it in-place.
    pid = str(primary_id or "").strip()
    if pid:
        ent = find_entity_by_id(entities, pid)
        if isinstance(ent, dict) and not is_player_entity(ent) and _has_behaviour(ent, "SceneTransition"):
            changed_any = False
            changed_any = _ensure_behaviour(ent, "SceneTransition") or changed_any
            cfg = _ensure_cfg(ent, "SceneTransition")
            if cfg.get("target_scene") != tgt:
                cfg["target_scene"] = tgt
                changed_any = True
            if cfg.get("spawn_id") != sp:
                cfg["spawn_id"] = sp
                changed_any = True
            if cfg.get("spawn_point") != sp:
                cfg["spawn_point"] = sp
                changed_any = True
            if require_flags is not None:
                req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
                changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
            if forbid_flags is not None:
                forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
                changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
            if changed_any:
                updated = 1
            return authored_copy, 0, updated

    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    target_stem = _san(Path(tgt).stem if tgt else "target")
    x = float(center_x)
    y = float(center_y)
    entity_id = f"{stem}_macro_transition_{target_stem}_{_fmt(x)}_{_fmt(y)}_0_0"

    ent = find_entity_by_id(entities, entity_id)
    if ent is None:
        entities.append({"id": entity_id})
        ent = entities[-1]
        created = 1
    else:
        if isinstance(ent, dict):
            existing_pid = ent.get("prefab_id")
            if (
                isinstance(existing_pid, str)
                and existing_pid.strip()
                and existing_pid.strip() not in {"SceneTransition"}
                and not _has_behaviour(ent, "SceneTransition")
            ):
                raise ValueError(f"prefab_mismatch id={entity_id} prefab_id={existing_pid.strip()!r}")

    changed_any = False
    changed_any = _ensure_behaviour(ent, "SceneTransition") or changed_any
    changed_any = _set_field(ent, "x", x) or changed_any
    changed_any = _set_field(ent, "y", y) or changed_any
    changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
    if require_flags is not None:
        req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
        changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
    if forbid_flags is not None:
        forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
        changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
    cfg = _ensure_cfg(ent, "SceneTransition")
    if cfg.get("target_scene") != tgt:
        cfg["target_scene"] = tgt
        changed_any = True
    if cfg.get("spawn_id") != sp:
        cfg["spawn_id"] = sp
        changed_any = True
    if cfg.get("spawn_point") != sp:
        cfg["spawn_point"] = sp
        changed_any = True
    if changed_any and created == 0:
        updated = 1
    return authored_copy, created, updated

def debug_build_macro_dialogue_choice_flag_payload(
    controller: "SceneController",
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored payload that ensures a Dialogue choice and a SetGameStateOnEvent hook exist.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ...entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415
    from ...entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    sid = str(speaker_id or "").strip()
    cid = str(choice_id or "").strip()
    ctext = str(choice_text or "").strip()
    flag = str(set_flag or "").strip()
    toast_text = str(toast or "").strip()

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    # Update speaker dialogue choice.
    speaker_ent = find_entity_by_id(entities, sid)
    if isinstance(speaker_ent, dict) and _has_behaviour(speaker_ent, "Dialogue"):
        changed_any = False
        cfg = _ensure_cfg(speaker_ent, "Dialogue")
        dialogue = cfg.get("dialogue")
        if not isinstance(dialogue, dict):
            dialogue = {"nodes": {"root": {"text": "", "choices": []}}, "start": "root", "speaker": ""}
            cfg["dialogue"] = dialogue
            changed_any = True
        nodes = dialogue.get("nodes")
        if not isinstance(nodes, dict):
            nodes = {}
            dialogue["nodes"] = nodes
            changed_any = True
        start_key = str(dialogue.get("start") or "root")
        start_node = nodes.get(start_key)
        if not isinstance(start_node, dict):
            start_node = {"text": "", "choices": []}
            nodes[start_key] = start_node
            changed_any = True
        choices = start_node.get("choices")
        if not isinstance(choices, list):
            choices = []
            start_node["choices"] = choices
            changed_any = True
        found = None
        for entry in choices:
            if isinstance(entry, dict) and str(entry.get("id") or "").strip() == cid:
                found = entry
                break
        if found is None:
            choices.append({"id": cid, "text": ctext, "next": None, "once": True})
            changed_any = True
        else:
            if found.get("text") != ctext:
                found["text"] = ctext
                changed_any = True
            if "id" not in found:
                found["id"] = cid
                changed_any = True
        if changed_any:
            updated += 1

    # Ensure hook entity exists.
    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    hook_id = f"{stem}_macro_choiceflag_{_san(flag)}_{_san(cid)}_0_0"
    hook_ent = find_entity_by_id(entities, hook_id)
    if hook_ent is None:
        entities.append({"id": hook_id})
        hook_ent = entities[-1]
        created += 1
    else:
        if isinstance(hook_ent, dict):
            pid = hook_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"SetGameStateOnEvent"}
                and not _has_behaviour(hook_ent, "SetGameStateOnEvent")
            ):
                raise ValueError(f"prefab_mismatch id={hook_id} prefab_id={pid.strip()!r}")

    changed_any = False
    behaviours = hook_ent.get("behaviours")
    if not isinstance(behaviours, list):
        behaviours = []
        hook_ent["behaviours"] = behaviours
        changed_any = True
    if not any(
        (isinstance(b, str) and b.strip() == "SetGameStateOnEvent")
        or (isinstance(b, dict) and str(b.get("type") or "").strip() == "SetGameStateOnEvent")
        for b in behaviours
    ):
        behaviours.append("SetGameStateOnEvent")
        changed_any = True

    cfg = _ensure_cfg(hook_ent, "SetGameStateOnEvent")
    if cfg.get("event_type") != "dialogue_choice":
        cfg["event_type"] = "dialogue_choice"
        changed_any = True
    if cfg.get("payload_field") != "choice_id":
        cfg["payload_field"] = "choice_id"
        changed_any = True
    if cfg.get("payload_value") != cid:
        cfg["payload_value"] = cid
        changed_any = True
    if cfg.get("once") is not True:
        cfg["once"] = True
        changed_any = True
    set_flags = cfg.get("set_flags")
    if not isinstance(set_flags, dict):
        set_flags = {}
        cfg["set_flags"] = set_flags
        changed_any = True
    if flag and set_flags.get(flag) is not True:
        set_flags[flag] = True
        changed_any = True
    if toast_text:
        if cfg.get("toast") != toast_text:
            cfg["toast"] = toast_text
            changed_any = True
        if not isinstance(cfg.get("toast_seconds"), (int, float)) or float(cfg.get("toast_seconds") or 0.0) <= 0.0:
            cfg["toast_seconds"] = 3.0
            changed_any = True
    else:
        if cfg.get("toast") not in (None, ""):
            cfg["toast"] = ""
            changed_any = True

    if changed_any and created == 0:
        updated += 1

    return authored_copy, created, updated

def _debug_preview_diff(controller: "SceneController", before_payload: Dict[str, Any], after_payload: Dict[str, Any]) -> Dict[str, Any]:
    from ...entity_paint_mode import ensure_entities_list  # noqa: PLC0415

    before_entities = ensure_entities_list(before_payload)
    after_entities = ensure_entities_list(after_payload)

    before_by_id: dict[str, dict[str, Any]] = {}
    for ent in before_entities:
        if not isinstance(ent, dict):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            before_by_id[entity_id.strip()] = ent
    after_by_id: dict[str, dict[str, Any]] = {}
    for ent in after_entities:
        if not isinstance(ent, dict):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            after_by_id[entity_id.strip()] = ent

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())
    create_ids = sorted(after_ids - before_ids)
    update_ids = sorted([eid for eid in (after_ids & before_ids) if before_by_id.get(eid) != after_by_id.get(eid)])

    return {
        "will_create": int(len(create_ids)),
        "will_update": int(len(update_ids)),
        "create_ids": create_ids,
        "update_ids": update_ids,
    }

def debug_preview_macro_objective_zone(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_objective_zone_payload(
        controller,
        center_x=float(center_x),
        center_y=float(center_y),
        zone_id=zone_id,
        set_flag=set_flag,
        radius=float(radius),
        toast=toast,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )
    return _debug_preview_diff(controller, before, after)

def debug_preview_macro_door_transition(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_door_transition_payload(
        controller,
        center_x=float(center_x),
        center_y=float(center_y),
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id,
    )
    return _debug_preview_diff(controller, before, after)

def debug_preview_macro_dialogue_choice_flag(
    controller: "SceneController",
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_dialogue_choice_flag_payload(
        controller,
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast,
    )
    return _debug_preview_diff(controller, before, after)

