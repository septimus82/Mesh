import argparse
import json
from pathlib import Path
from typing import Any

from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.swallowed_exceptions import _log_swallow
from mesh_cli.scene.common import (
    _dict_diffs,
    _format_placeholder_id_number,
    _sanitize_entity_id_token,
)


def _default_spawn_entity_id(scene_path: str, spawn_id: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    sid = _sanitize_entity_id_token(spawn_id)
    return f"{stem}_spawn_{sid}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _default_placeholder_entity_id(scene_path: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    return f"{stem}_themedenemy_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _default_prefab_entity_id(scene_path: str, prefab_id: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    pid = _sanitize_entity_id_token(prefab_id)
    return f"{stem}_{pid}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _default_transition_entity_id(scene_path: str, to_key: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    to_token = _sanitize_entity_id_token(to_key)
    return f"{stem}_transition_{to_token}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _handle_scene_add_placeholder(args: argparse.Namespace) -> int:
    """Append a theme_enemy_placeholder entity into an existing scene JSON."""
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("SENT-001", "mesh_cli/scene/entities.py blanket swallow", once=True)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    entities = data.get("entities")
    if entities is None:
        entities = []
        data["entities"] = entities
    if not isinstance(entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path}")
        return 1

    x = float(getattr(args, "x", 0.0))
    y = float(getattr(args, "y", 0.0))

    requested_id = getattr(args, "id", None)
    entity_id = str(requested_id).strip() if isinstance(requested_id, str) and requested_id.strip() else None
    if entity_id is None:
        entity_id = _default_placeholder_entity_id(scene_path, x, y)

    existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
    if existing is not None:
        if str(existing.get("prefab_id") or "") == "theme_enemy_placeholder":
            print(f"[Mesh][CLI] Placeholder already present: {scene_path} id={entity_id}")
            return 0
        print(f"[Mesh][CLI] Error: entity id already exists with different prefab: {scene_path} id={entity_id}")
        return 1

    entities.append(
        {
            "behaviours": ["EnemyAI"],
            "id": entity_id,
            "layer": "entities",
            "mesh_name": "ThemedEnemy",
            "prefab_id": "theme_enemy_placeholder",
            "x": float(x),
            "y": float(y),
        }
    )

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after insert: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][CLI] Added placeholder: {scene_path} id={entity_id} x={x:g} y={y:g}")
    return 0


def _handle_scene_add_entity(args: argparse.Namespace) -> int:
    """Insert or update a prefab-backed entity in a scene (idempotent)."""
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    prefab_id = str(getattr(args, "prefab_id", "") or "").strip()
    if not prefab_id:
        print("[Mesh][CLI] Error: missing --prefab-id")
        return 2

    x = float(getattr(args, "x", 0.0))
    y = float(getattr(args, "y", 0.0))

    requested_id = getattr(args, "id", None)
    entity_id = str(requested_id).strip() if isinstance(requested_id, str) and requested_id.strip() else None
    if entity_id is None:
        entity_id = _default_prefab_entity_id(scene_path, prefab_id, x, y)

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("SENT-002", "mesh_cli/scene/entities.py blanket swallow", once=True)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    # Validate prefab existence (read assets/prefabs.json via the existing resolver).
    prefabs_path = resolve_path("assets/prefabs.json")
    try:
        prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("SENT-003", "mesh_cli/scene/entities.py blanket swallow", once=True)
        print(f"[Mesh][CLI] Error: failed to read prefabs: {prefabs_path}: {exc}")
        return 1
    if not isinstance(prefabs_payload, list) or not any(
        isinstance(entry, dict) and entry.get("id") == prefab_id for entry in prefabs_payload
    ):
        print(f"[Mesh][CLI] Error: unknown prefab_id '{prefab_id}'")
        return 1

    entities = data.get("entities")
    if entities is None:
        entities = []
        data["entities"] = entities
    if not isinstance(entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path}")
        return 1

    existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
    if existing is not None and str(existing.get("prefab_id") or "") != prefab_id:
        print(
            f"[Mesh][CLI] Error: entity id already exists with different prefab: {scene_path} id={entity_id}",
        )
        return 1

    # Parse optional updates.
    mesh_name = str(getattr(args, "name", "") or "").strip() or None
    layer_value = str(getattr(args, "layer", "") or "").strip() or None
    tags_value = getattr(args, "tags", None)
    tags: list[str] | None = None
    if tags_value is not None:
        if isinstance(tags_value, list):
            tags = sorted({str(t).strip() for t in tags_value if isinstance(t, str) and t.strip()})
        else:
            tags = sorted({str(tags_value).strip()}) if str(tags_value).strip() else []

    behaviours_to_add: list[str] = []
    raw_behaviours = getattr(args, "behaviour", None)
    if isinstance(raw_behaviours, list):
        behaviours_to_add = [str(b).strip() for b in raw_behaviours if isinstance(b, str) and b.strip()]
    elif isinstance(raw_behaviours, str) and raw_behaviours.strip():
        behaviours_to_add = [raw_behaviours.strip()]

    behaviour_configs: dict[str, dict] = {}
    raw_behaviour_json = getattr(args, "behaviour_json", None)
    if raw_behaviour_json:
        items = raw_behaviour_json if isinstance(raw_behaviour_json, list) else [raw_behaviour_json]
        for item in items:
            text = str(item or "").strip()
            if "=" not in text:
                print("[Mesh][CLI] Error: --behaviour-json must be formatted as Name=<json>")
                return 2
            name, raw_json = text.split("=", 1)
            name = name.strip()
            if not name:
                print("[Mesh][CLI] Error: --behaviour-json missing behaviour name")
                return 2
            if name in behaviour_configs:
                print(f"[Mesh][CLI] Error: duplicate --behaviour-json for '{name}'")
                return 2
            try:
                parsed = json.loads(raw_json)
            except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
                _log_swallow("SENT-004", "mesh_cli/scene/entities.py blanket swallow", once=True)
                print(f"[Mesh][CLI] Error: invalid JSON for --behaviour-json '{name}': {exc}")
                return 2
            if not isinstance(parsed, dict):
                print(f"[Mesh][CLI] Error: --behaviour-json '{name}' must be a JSON object")
                return 2
            behaviour_configs[name] = parsed

    if behaviours_to_add or behaviour_configs:
        import engine.behaviours  # noqa: F401
        from engine.behaviours.registry import get_behaviour_info

        unknown = sorted(
            {b for b in behaviours_to_add if get_behaviour_info(b) is None}
            | {b for b in behaviour_configs.keys() if get_behaviour_info(b) is None}
        )
        if unknown:
            print(f"[Mesh][CLI] Error: unknown behaviour(s): {', '.join(unknown)}")
            return 1

    changed = False
    if existing is None:
        new_entity: dict[str, Any] = {
            "id": entity_id,
            "prefab_id": prefab_id,
            "x": float(x),
            "y": float(y),
        }
        if layer_value:
            new_entity["layer"] = layer_value
        if mesh_name:
            new_entity["mesh_name"] = mesh_name
        if tags is not None:
            new_entity["tags"] = tags
        if behaviours_to_add:
            new_entity["behaviours"] = [{"type": name, "params": {}} for name in behaviours_to_add]
        if behaviour_configs:
            new_entity["behaviour_config"] = dict(behaviour_configs)
            if "behaviours" not in new_entity:
                new_entity["behaviours"] = []
            for name in behaviour_configs:
                if not any(isinstance(entry, dict) and entry.get("type") == name for entry in new_entity["behaviours"]):
                    new_entity["behaviours"].append({"type": name, "params": {}})
        entities.append(new_entity)
        changed = True
    else:
        if not isinstance(existing, dict):
            print(f"[Mesh][CLI] Error: entity must be an object: {scene_path} id={entity_id}")
            return 1
        # Always keep prefab_id/x/y current for determinism.
        if existing.get("x") != float(x):
            existing["x"] = float(x)
            changed = True
        if existing.get("y") != float(y):
            existing["y"] = float(y)
            changed = True
        if existing.get("prefab_id") != prefab_id:
            existing["prefab_id"] = prefab_id
            changed = True

        if layer_value is not None and existing.get("layer") != layer_value:
            existing["layer"] = layer_value
            changed = True
        if mesh_name is not None and existing.get("mesh_name") != mesh_name:
            existing["mesh_name"] = mesh_name
            changed = True
        if tags is not None and existing.get("tags") != tags:
            existing["tags"] = tags
            changed = True

        if behaviours_to_add or behaviour_configs:
            behaviours_list = existing.get("behaviours")
            if behaviours_list is None:
                behaviours_list = []
                existing["behaviours"] = behaviours_list
                changed = True
            if not isinstance(behaviours_list, list):
                print(f"[Mesh][CLI] Error: behaviours must be a list: {scene_path} id={entity_id}")
                return 1

            existing_types: set[str] = set()
            for entry in behaviours_list:
                if isinstance(entry, str) and entry.strip():
                    existing_types.add(entry.strip())
                elif isinstance(entry, dict):
                    t = entry.get("type")
                    if isinstance(t, str) and t.strip():
                        existing_types.add(t.strip())

            for name in behaviours_to_add:
                if name in existing_types:
                    continue
                behaviours_list.append({"type": name, "params": {}})
                existing_types.add(name)
                changed = True

            if behaviour_configs:
                cfg_root = existing.get("behaviour_config")
                if cfg_root is None:
                    cfg_root = {}
                    existing["behaviour_config"] = cfg_root
                    changed = True
                if not isinstance(cfg_root, dict):
                    print(f"[Mesh][CLI] Error: behaviour_config must be an object: {scene_path} id={entity_id}")
                    return 1
                for name, cfg in behaviour_configs.items():
                    if cfg_root.get(name) != cfg:
                        cfg_root[name] = cfg
                        changed = True
                    if name not in existing_types:
                        behaviours_list.append({"type": name, "params": {}})
                        existing_types.add(name)
                        changed = True

    if not changed:
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after insert: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][CLI] Added entity: {scene_path} id={entity_id} prefab_id={prefab_id} x={x:g} y={y:g}")
    return 0


def _handle_scene_add_triggerzone_objective(args: argparse.Namespace) -> int:
    """Insert a TriggerZone + SetGameStateOnEvent pair for objective beats."""
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("SENT-005", "mesh_cli/scene/entities.py blanket swallow", once=True)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    entities = data.get("entities")
    if entities is None:
        entities = []
        data["entities"] = entities
    if not isinstance(entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path}")
        return 1

    x = float(getattr(args, "x", 0.0))
    y = float(getattr(args, "y", 0.0))
    radius = float(getattr(args, "radius", 0.0))
    zone_id = str(getattr(args, "zone_id", "") or "").strip()
    set_flag = str(getattr(args, "set_flag", "") or "").strip()
    if not zone_id:
        print("[Mesh][CLI] Error: --zone-id is required")
        return 2
    if not set_flag:
        print("[Mesh][CLI] Error: --set-flag is required")
        return 2
    if radius <= 0.0:
        print("[Mesh][CLI] Error: --radius must be > 0")
        return 2

    require_flags = getattr(args, "require", None)
    forbid_flags = getattr(args, "forbid", None)
    req_list = sorted({str(v).strip() for v in (require_flags or []) if str(v).strip()})
    forbid_list = sorted({str(v).strip() for v in (forbid_flags or []) if str(v).strip()})

    toast = getattr(args, "toast", None)
    toast_text = str(toast).strip() if isinstance(toast, str) and str(toast).strip() else None
    toast_seconds_raw = getattr(args, "toast_seconds", None)
    toast_seconds = float(toast_seconds_raw) if isinstance(toast_seconds_raw, (int, float)) else None

    stem = Path(str(scene_path)).stem
    zid_token = _sanitize_entity_id_token(zone_id)
    flag_token = _sanitize_entity_id_token(set_flag)

    trigger_id = f"{stem}_triggerzone_{zid_token}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"
    setter_id = f"{stem}_setflag_{flag_token}_{zid_token}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"

    expected_trigger = {
        "behaviour_config": {
            "TriggerZone": {
                "on_trigger": "objective_trigger",
                "trigger_radius": float(radius),
                "trigger_target": "Player",
                "zone_id": zone_id,
            }
        },
        "behaviours": ["TriggerZone"],
        "id": trigger_id,
        "layer": "background",
        "name": zone_id,
        "scale": 0.0,
        "tag": "trigger",
        "x": float(x),
        "y": float(y),
    }

    expected_setter_cfg: dict[str, object] = {
        "event_type": "entered_zone",
        "once": True,
        "payload_field": "zone",
        "payload_value": zone_id,
        "set_flags": {set_flag: True},
    }
    if req_list:
        expected_setter_cfg["require_flags"] = req_list
    if forbid_list:
        expected_setter_cfg["forbid_flags"] = forbid_list
    if toast_text is not None:
        expected_setter_cfg["toast"] = toast_text
    if toast_seconds is not None:
        expected_setter_cfg["toast_seconds"] = float(toast_seconds)

    expected_setter = {
        "behaviour_config": {"SetGameStateOnEvent": expected_setter_cfg},
        "behaviours": ["SetGameStateOnEvent"],
        "id": setter_id,
        "layer": "background",
        "name": f"SetFlag:{set_flag}",
        "scale": 0.0,
        "x": float(x),
        "y": float(y),
    }

    def _find_entity_by_id(eid: str) -> dict | None:
        return next((e for e in entities if isinstance(e, dict) and e.get("id") == eid), None)

    changed = False

    existing_trigger = _find_entity_by_id(trigger_id)
    if existing_trigger is None:
        entities.append(expected_trigger)
        changed = True
    else:
        diffs = _dict_diffs(expected_trigger, existing_trigger)
        if diffs:
            print(f"[Mesh][CLI] Error: existing TriggerZone entity differs: id={trigger_id}")
            for d in diffs[:8]:
                print(f"[Mesh][CLI]   {d}")
            return 1

    existing_setter = _find_entity_by_id(setter_id)
    if existing_setter is None:
        entities.append(expected_setter)
        changed = True
    else:
        diffs = _dict_diffs(expected_setter, existing_setter)
        if diffs:
            print(f"[Mesh][CLI] Error: existing SetGameStateOnEvent entity differs: id={setter_id}")
            for d in diffs[:8]:
                print(f"[Mesh][CLI]   {d}")
            return 1

    if not changed:
        print(f"[Mesh][CLI] Objective trigger already present: {scene_path} zone_id={zone_id} set_flag={set_flag}")
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after insert: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][CLI] Added objective trigger: {scene_path} zone_id={zone_id} set_flag={set_flag}")
    return 0


def _handle_scene_add_dialogue_choice_flag(args: argparse.Namespace) -> int:
    """Wire a Dialogue choice to a SetGameStateOnEvent flag setter."""
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    speaker_id = str(getattr(args, "speaker_id", "") or "").strip()
    choice_id = str(getattr(args, "choice_id", "") or "").strip()
    choice_text = str(getattr(args, "choice_text", "") or "").strip()
    set_flag = str(getattr(args, "set_flag", "") or "").strip()

    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2
    if not speaker_id:
        print("[Mesh][CLI] Error: --speaker-id is required")
        return 2
    if not choice_id:
        print("[Mesh][CLI] Error: --choice-id is required")
        return 2
    if not choice_text:
        print("[Mesh][CLI] Error: --choice-text is required")
        return 2
    if not set_flag:
        print("[Mesh][CLI] Error: --set-flag is required")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("SENT-006", "mesh_cli/scene/entities.py blanket swallow", once=True)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    entities = data.get("entities")
    if entities is None:
        entities = []
        data["entities"] = entities
    if not isinstance(entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path}")
        return 1

    speaker = next((e for e in entities if isinstance(e, dict) and e.get("id") == speaker_id), None)
    if speaker is None:
        print(f"[Mesh][CLI] Error: speaker entity not found: id={speaker_id}")
        return 1

    behaviour_config = speaker.get("behaviour_config")
    if behaviour_config is None:
        behaviour_config = {}
        speaker["behaviour_config"] = behaviour_config
    if not isinstance(behaviour_config, dict):
        print(f"[Mesh][CLI] Error: speaker.behaviour_config must be an object: id={speaker_id}")
        return 1

    dialogue_cfg = behaviour_config.get("Dialogue")
    if dialogue_cfg is None:
        dialogue_cfg = {}
        behaviour_config["Dialogue"] = dialogue_cfg
    if not isinstance(dialogue_cfg, dict):
        print(f"[Mesh][CLI] Error: speaker Dialogue config must be an object: id={speaker_id}")
        return 1

    dialogue = dialogue_cfg.get("dialogue")
    if dialogue is None:
        dialogue = {"nodes": {}, "start": "intro"}
        dialogue_cfg["dialogue"] = dialogue
    if not isinstance(dialogue, dict):
        print(f"[Mesh][CLI] Error: Dialogue.dialogue must be an object: id={speaker_id}")
        return 1

    nodes = dialogue.get("nodes")
    if nodes is None:
        nodes = {}
        dialogue["nodes"] = nodes
    if not isinstance(nodes, dict):
        print(f"[Mesh][CLI] Error: Dialogue.dialogue.nodes must be an object: id={speaker_id}")
        return 1

    start_node = dialogue.get("start")
    if not isinstance(start_node, str) or not start_node.strip():
        start_node = "intro"
        dialogue["start"] = start_node
    start_node = str(start_node).strip()

    node = nodes.get(start_node)
    if node is None:
        node = {"text": "", "choices": []}
        nodes[start_node] = node
    if not isinstance(node, dict):
        print(f"[Mesh][CLI] Error: Dialogue node must be an object: node={start_node!r} id={speaker_id}")
        return 1

    choices = node.get("choices")
    if choices is None:
        choices = []
        node["choices"] = choices
    if not isinstance(choices, list):
        print(f"[Mesh][CLI] Error: Dialogue node choices must be a list: node={start_node!r} id={speaker_id}")
        return 1

    changed = False
    existing_choice = next((c for c in choices if isinstance(c, dict) and c.get("id") == choice_id), None)
    if existing_choice is None:
        choices.append({"id": choice_id, "text": choice_text, "end": True})
        changed = True
    else:
        if existing_choice.get("text") != choice_text:
            existing_choice["text"] = choice_text
            changed = True

    require_flags = getattr(args, "require", None)
    forbid_flags = getattr(args, "forbid", None)
    req_list = sorted({str(v).strip() for v in (require_flags or []) if str(v).strip()})
    forbid_list = sorted({str(v).strip() for v in (forbid_flags or []) if str(v).strip()})

    toast = getattr(args, "toast", None)
    toast_text = str(toast).strip() if isinstance(toast, str) and str(toast).strip() else None
    toast_seconds_raw = getattr(args, "toast_seconds", None)
    toast_seconds = float(toast_seconds_raw) if isinstance(toast_seconds_raw, (int, float)) else None

    stem = Path(str(scene_path)).stem
    flag_token = _sanitize_entity_id_token(set_flag)
    choice_token = _sanitize_entity_id_token(choice_id)
    hook_id = f"{stem}_choiceflag_{flag_token}_{choice_token}_0_0"

    expected_cfg: dict[str, object] = {
        "event_type": "dialogue_choice",
        "once": True,
        "payload_field": "choice_id",
        "payload_value": choice_id,
        "set_flags": {set_flag: True},
    }
    if req_list:
        expected_cfg["require_flags"] = req_list
    if forbid_list:
        expected_cfg["forbid_flags"] = forbid_list
    if toast_text is not None:
        expected_cfg["toast"] = toast_text
    if toast_seconds is not None:
        expected_cfg["toast_seconds"] = float(toast_seconds)

    expected_hook = {
        "behaviour_config": {"SetGameStateOnEvent": expected_cfg},
        "behaviours": ["SetGameStateOnEvent"],
        "id": hook_id,
        "layer": "background",
        "name": "DialogueChoiceFlagHook",
        "scale": 0.0,
        "x": 0.0,
        "y": 0.0,
    }

    existing_hook = next((e for e in entities if isinstance(e, dict) and e.get("id") == hook_id), None)
    if existing_hook is None:
        entities.append(expected_hook)
        changed = True
    else:
        diffs = _dict_diffs(expected_hook, existing_hook)
        if diffs:
            print(f"[Mesh][CLI] Error: existing hook entity differs: id={hook_id}")
            for d in diffs[:8]:
                print(f"[Mesh][CLI]   {d}")
            return 1

    if not changed:
        print(f"[Mesh][CLI] Choice+hook already present: {scene_path} speaker_id={speaker_id} choice_id={choice_id}")
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after edit: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][CLI] Added dialogue choice flag hook: {scene_path} speaker_id={speaker_id} choice_id={choice_id}")
    return 0
