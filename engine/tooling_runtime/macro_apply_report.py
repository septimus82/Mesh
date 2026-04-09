from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, cast, TypedDict

from engine.macro_specs import get_builtin_macro_spec
from engine.path_norm import normalize_scene_path
from engine.scene_controller import SceneController
from engine.tooling_runtime.macro_assets import load_macro_asset, parse_macro_asset, validate_macro_asset


@dataclass(frozen=True, slots=True)
class MacroReportResult:
    after_payload: dict[str, Any]
    report: dict[str, Any]


class MacroReportPayload(TypedDict):
    ok: bool
    scene_path: str
    macro_path: str
    args: dict[str, Any]
    will_create: int
    will_update: int
    create_ids: list[str]
    update_ids: list[str]
    entity_changes: list[dict[str, Any]]
    config_changes: list[dict[str, Any]]


def _find_player_pos(scene_payload: dict[str, Any]) -> tuple[float, float]:
    entities = scene_payload.get("entities")
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            pid = ent.get("prefab_id")
            tags = ent.get("tags")
            if pid == "player" or (isinstance(tags, list) and "player" in tags):
                try:
                    return float(ent.get("x", 0.0)), float(ent.get("y", 0.0))
                except (TypeError, ValueError):
                    return 0.0, 0.0
    return 0.0, 0.0


def _find_entity_pos(scene_payload: dict[str, Any], entity_id: str) -> tuple[float, float] | None:
    wanted = str(entity_id or "").strip()
    if not wanted:
        return None
    entities = scene_payload.get("entities")
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if str(ent.get("id") or "").strip() != wanted:
                continue
            try:
                return float(ent.get("x", 0.0)), float(ent.get("y", 0.0))
            except (TypeError, ValueError):
                return 0.0, 0.0
    return None


def _parse_kv_args(raw_args: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in raw_args or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"bad_arg {text!r} (expected k=v)")
        key, value = text.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"bad_arg {text!r} (empty key)")
        out[key] = value
    return out


def _parse_arg_value(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text[:1] in "[{\"" or text in {"true", "false", "null"}:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text


def _normalize_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return sorted(set(items))
    text = str(value).strip()
    if not text:
        return []
    return [text]


def _behaviour_set(ent: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    raw = ent.get("behaviours")
    if not isinstance(raw, list):
        return out
    for b in raw:
        if isinstance(b, str) and b.strip():
            out.add(b.strip())
        elif isinstance(b, dict):
            t = b.get("type")
            if isinstance(t, str) and t.strip():
                out.add(t.strip())
    return out


def _infer_prefab_id(ent: dict[str, Any]) -> str | None:
    pid = ent.get("prefab_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    behaviours = _behaviour_set(ent)
    for known in ("SceneTransition", "TriggerZone", "SetGameStateOnEvent"):
        if known in behaviours:
            return known
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def compute_scene_macro_report(
    *,
    scene_payload: dict[str, Any],
    scene_path: str,
    macro_path: str,
    raw_args: list[str] | None,
    anchor_override: str | None,
    cursor_world_pos: tuple[float, float] | None = None,
    primary_entity_id: str | None = None,
) -> MacroReportResult:
    scene_path_norm = normalize_scene_path(scene_path)
    macro_path_norm = normalize_scene_path(macro_path)

    macro_payload = load_macro_asset(macro_path)
    issues = validate_macro_asset(macro_payload, rel_path=macro_path_norm)
    if issues:
        first = issues[0]
        raise ValueError(f"{first.path} :: {first.code} :: {first.detail}")
    asset = parse_macro_asset(macro_payload, rel_path=macro_path_norm)

    merged_args: dict[str, Any] = dict(asset.defaults or {})
    for k, v in _parse_kv_args(raw_args).items():
        merged_args[k] = _parse_arg_value(v)
    if anchor_override is not None:
        merged_args["anchor"] = str(anchor_override).strip()

    macro_id = str(asset.macro_id or "").strip()
    spec = get_builtin_macro_spec(macro_id)
    if spec is None:
        raise ValueError(f"unknown macro_id {macro_id!r}")

    allowed_keys = set(spec.allowed_keys)
    for key in sorted(merged_args.keys()):
        if key not in allowed_keys:
            raise ValueError(f"unknown_arg {key!r}")

    # Validate required keys are present (asset validation can also do this, but CLI may override defaults).
    for req in spec.required_keys:
        if req not in merged_args:
            raise ValueError(f"missing_arg {req!r}")
        if isinstance(merged_args.get(req), str) and not str(merged_args.get(req)).strip():
            raise ValueError(f"missing_arg {req!r}")

    anchor = str(merged_args.get("anchor") or "cursor").strip().lower() or "cursor"
    player_pos = _find_player_pos(scene_payload)
    if anchor == "primary":
        if not primary_entity_id:
            raise ValueError("no_selection (anchor=primary requires a selected entity)")
        pos = _find_entity_pos(scene_payload, primary_entity_id)
        if pos is None:
            raise ValueError("no_selection (primary entity not found)")
    elif anchor == "player":
        pos = player_pos
    else:
        pos = cursor_world_pos if cursor_world_pos is not None else player_pos

    before_payload = copy.deepcopy(scene_payload)

    # Avoid SceneController.__init__ (it loads prefabs/variants and prints to stdout).
    sc = SceneController.__new__(SceneController)
    sc.current_scene_path = str(scene_path)
    sc._loaded_scene_source_data = before_payload

    after_payload: dict[str, Any]
    if macro_id == "macro.objective_zone":
        zone_id = str(merged_args.get("zone_id") or "").strip()
        set_flag = str(merged_args.get("set_flag") or "").strip()
        radius_raw = merged_args.get("radius")
        try:
            radius = float(cast(Any, radius_raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bad_args radius={radius_raw!r}") from exc
        toast = merged_args.get("toast")
        toast_text = str(toast).strip() if isinstance(toast, str) else ""
        toast_val = toast_text if toast_text else None
        require_flags = merged_args.get("require_flags")
        forbid_flags = merged_args.get("forbid_flags")
        toast_seconds = merged_args.get("toast_seconds")
        toast_seconds_val: float | None
        if toast_seconds is None or toast_seconds == "":
            toast_seconds_val = None
        else:
            try:
                toast_seconds_val = float(toast_seconds)
            except (TypeError, ValueError):
                toast_seconds_val = None
        after_payload, created, updated = sc.debug_build_macro_objective_zone_payload(
            center_x=float(pos[0]),
            center_y=float(pos[1]),
            zone_id=zone_id,
            set_flag=set_flag,
            radius=float(radius),
            toast=toast_val,
            require_flags=_normalize_str_list(require_flags) if require_flags is not None else None,
            forbid_flags=_normalize_str_list(forbid_flags) if forbid_flags is not None else None,
            toast_seconds=toast_seconds_val,
        )
    elif macro_id == "macro.door_transition":
        target_scene = str(merged_args.get("target_scene") or "").strip()
        spawn_id = str(merged_args.get("spawn_id") or "").strip()
        require_flags_gate = merged_args.get("require_flags") if "require_flags" in merged_args else None
        forbid_flags_gate = merged_args.get("forbid_flags") if "forbid_flags" in merged_args else None
        after_payload, created, updated = sc.debug_build_macro_door_transition_payload(
            center_x=float(pos[0]),
            center_y=float(pos[1]),
            target_scene=target_scene,
            spawn_id=spawn_id,
            primary_id=str(primary_entity_id).strip() if primary_entity_id else None,
            require_flags=_normalize_str_list(require_flags_gate) if require_flags_gate is not None else None,
            forbid_flags=_normalize_str_list(forbid_flags_gate) if forbid_flags_gate is not None else None,
        )
    elif macro_id == "macro.dialogue_choice_flag":
        speaker_id = str(merged_args.get("speaker_id") or "").strip()
        choice_id = str(merged_args.get("choice_id") or "").strip()
        choice_text = str(merged_args.get("choice_text") or "").strip()
        set_flag = str(merged_args.get("set_flag") or "").strip()
        toast = merged_args.get("toast")
        toast_text = str(toast).strip() if isinstance(toast, str) else ""
        toast_val = toast_text if toast_text else None
        after_payload, created, updated = sc.debug_build_macro_dialogue_choice_flag_payload(
            speaker_id=speaker_id,
            choice_id=choice_id,
            choice_text=choice_text,
            set_flag=set_flag,
            toast=toast_val,
        )
    else:
        raise ValueError(f"unknown macro_id {macro_id!r}")

    diff = sc._debug_preview_diff(before_payload, after_payload)  # noqa: SLF001
    before_by_id: dict[str, dict[str, Any]] = {}
    for ent in before_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        ent_id = ent.get("id")
        if isinstance(ent_id, str) and ent_id.strip():
            before_by_id[ent_id.strip()] = ent
    after_by_id: dict[str, dict[str, Any]] = {}
    for ent in after_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        ent_id = ent.get("id")
        if isinstance(ent_id, str) and ent_id.strip():
            after_by_id[ent_id.strip()] = ent

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())
    create_ids = sorted(after_ids - before_ids)
    update_ids = sorted([eid for eid in (after_ids & before_ids) if before_by_id.get(eid) != after_by_id.get(eid)])

    def _entity_change_row(eid: str, action: str) -> dict[str, Any]:
        before_ent = before_by_id.get(eid) or {}
        after_ent = after_by_id.get(eid) or {}
        before_beh = _behaviour_set(before_ent)
        after_beh = _behaviour_set(after_ent)
        prefab_id = _infer_prefab_id(after_ent)
        tags = after_ent.get("tags")
        tags_out = sorted({str(t).strip() for t in (tags or []) if isinstance(t, str) and t.strip()}) if isinstance(tags, list) else None
        name = after_ent.get("name")
        name_out = str(name).strip() if isinstance(name, str) and name.strip() else None
        require_flags = after_ent.get("require_flags")
        require_flags_out = (
            sorted({str(v).strip() for v in require_flags if isinstance(v, str) and v.strip()})
            if isinstance(require_flags, list)
            else None
        )
        forbid_flags = after_ent.get("forbid_flags")
        forbid_flags_out = (
            sorted({str(v).strip() for v in forbid_flags if isinstance(v, str) and v.strip()})
            if isinstance(forbid_flags, list)
            else None
        )
        x = float(after_ent.get("x", 0.0) or 0.0)
        y = float(after_ent.get("y", 0.0) or 0.0)
        return {
            "id": eid,
            "action": action,
            "prefab_id": prefab_id,
            "name": name_out,
            "tags": tags_out,
            "require_flags": require_flags_out,
            "forbid_flags": forbid_flags_out,
            "x": x,
            "y": y,
            "behaviours_added": sorted(after_beh - before_beh),
            "behaviours_removed": sorted(before_beh - after_beh),
        }

    entity_changes: list[dict[str, Any]] = [_entity_change_row(eid, "add") for eid in create_ids] + [
        _entity_change_row(eid, "update") for eid in update_ids
    ]
    entity_changes.sort(key=lambda r: str(r.get("id") or ""))

    config_changes: list[dict[str, Any]] = []

    def _get_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = _as_dict(ent.get("behaviour_config"))
        return _as_dict(root.get(behaviour))

    def _add_cfg_change(eid: str, behaviour: str, field: str, before: Any, after: Any) -> None:
        if before == after:
            return
        config_changes.append({"id": eid, "behaviour": behaviour, "field": field, "before": before, "after": after})

    for eid in sorted(set(create_ids + update_ids)):
        b = before_by_id.get(eid) or {}
        a = after_by_id.get(eid) or {}

        for field in ("require_flags", "forbid_flags"):
            _add_cfg_change(eid, "Entity", field, b.get(field), a.get(field))

        if macro_id == "macro.door_transition":
            bcfg = _get_cfg(b, "SceneTransition")
            acfg = _get_cfg(a, "SceneTransition")
            for field in ("target_scene", "spawn_id", "spawn_point"):
                _add_cfg_change(eid, "SceneTransition", field, bcfg.get(field), acfg.get(field))

        if macro_id == "macro.objective_zone":
            btz = _get_cfg(b, "TriggerZone")
            atz = _get_cfg(a, "TriggerZone")
            for field in ("zone_id", "trigger_target", "trigger_radius"):
                _add_cfg_change(eid, "TriggerZone", field, btz.get(field), atz.get(field))

            bsgs = _get_cfg(b, "SetGameStateOnEvent")
            asgs = _get_cfg(a, "SetGameStateOnEvent")
            for field in ("event_type", "payload_field", "payload_value", "once", "toast", "toast_seconds"):
                _add_cfg_change(eid, "SetGameStateOnEvent", field, bsgs.get(field), asgs.get(field))
            for field in ("require_flags", "forbid_flags"):
                _add_cfg_change(eid, "SetGameStateOnEvent", field, bsgs.get(field), asgs.get(field))
            flag = str(merged_args.get("set_flag") or "").strip()
            bset_value = bsgs.get("set_flags")
            aset_value = asgs.get("set_flags")
            bset: dict[str, Any] = bset_value if isinstance(bset_value, dict) else {}
            aset: dict[str, Any] = aset_value if isinstance(aset_value, dict) else {}
            if flag:
                _add_cfg_change(eid, "SetGameStateOnEvent", f"set_flags.{flag}", bset.get(flag), aset.get(flag))

        if macro_id == "macro.dialogue_choice_flag":
            bsgs = _get_cfg(b, "SetGameStateOnEvent")
            asgs = _get_cfg(a, "SetGameStateOnEvent")
            for field in ("event_type", "payload_field", "payload_value", "once", "toast", "toast_seconds"):
                _add_cfg_change(eid, "SetGameStateOnEvent", field, bsgs.get(field), asgs.get(field))
            flag = str(merged_args.get("set_flag") or "").strip()
            bset_value = bsgs.get("set_flags")
            aset_value = asgs.get("set_flags")
            bset_dlg: dict[str, Any] = bset_value if isinstance(bset_value, dict) else {}
            aset_dlg: dict[str, Any] = aset_value if isinstance(aset_value, dict) else {}
            if flag:
                _add_cfg_change(eid, "SetGameStateOnEvent", f"set_flags.{flag}", bset_dlg.get(flag), aset_dlg.get(flag))

            # Speaker dialogue changes (stable fields for the specific choice).
            speaker_id = str(merged_args.get("speaker_id") or "").strip()
            if speaker_id and eid == speaker_id:
                bdlg = _get_cfg(b, "Dialogue")
                adlg = _get_cfg(a, "Dialogue")
                bdlg_root = _as_dict(bdlg.get("dialogue"))
                adlg_root = _as_dict(adlg.get("dialogue"))
                bnodes = _as_dict(bdlg_root.get("nodes"))
                anodes = _as_dict(adlg_root.get("nodes"))
                bstart = str(bdlg_root.get("start") or "root") or "root"
                astart = str(adlg_root.get("start") or "root") or "root"
                bchoices = _as_dict(bnodes.get(bstart)).get("choices", [])
                achoices = _as_dict(anodes.get(astart)).get("choices", [])
                bchoice_ids = sorted({str(c.get("id") or "").strip() for c in bchoices if isinstance(c, dict) and str(c.get("id") or "").strip()})
                achoice_ids = sorted({str(c.get("id") or "").strip() for c in achoices if isinstance(c, dict) and str(c.get("id") or "").strip()})
                _add_cfg_change(eid, "Dialogue", "choice_ids", bchoice_ids, achoice_ids)
                wanted_choice = str(merged_args.get("choice_id") or "").strip()
                if wanted_choice:
                    btext = next((c.get("text") for c in bchoices if isinstance(c, dict) and str(c.get("id") or "").strip() == wanted_choice), None)
                    atext = next((c.get("text") for c in achoices if isinstance(c, dict) and str(c.get("id") or "").strip() == wanted_choice), None)
                    _add_cfg_change(eid, "Dialogue", f"choice_text.{wanted_choice}", btext, atext)

    config_changes.sort(key=lambda r: (str(r.get("id") or ""), str(r.get("behaviour") or ""), str(r.get("field") or "")))

    report: MacroReportPayload = {
        "ok": True,
        "scene_path": scene_path_norm,
        "macro_path": macro_path_norm,
        "args": json.loads(json.dumps(merged_args, sort_keys=True)),
        "will_create": int(len(create_ids)),
        "will_update": int(len(update_ids)),
        "create_ids": list(create_ids),
        "update_ids": list(update_ids),
        "entity_changes": entity_changes,
        "config_changes": config_changes,
    }

    return MacroReportResult(after_payload=after_payload, report=report)
