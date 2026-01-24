from __future__ import annotations

import json
from pathlib import Path


def _find_entity(payload: dict, entity_id: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def _dialogue_choice_ids(ent: dict) -> set[str]:
    cfg_root = ent.get("behaviour_config")
    cfg = cfg_root.get("Dialogue") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    dialogue_root = cfg.get("dialogue")
    assert isinstance(dialogue_root, dict)
    nodes = dialogue_root.get("nodes")
    assert isinstance(nodes, dict)
    root = nodes.get("root")
    assert isinstance(root, dict)
    choices = root.get("choices")
    assert isinstance(choices, list)
    ids: set[str] = set()
    for c in choices:
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            ids.add(c["id"])
    return ids


def test_guard_patrol_demo_spotted_zone_and_reset_exist_and_gate_completion() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    spotted_id = "guard_patrol_chase_demo_spottedzone_160_80_0_0"
    lever_id = "guard_patrol_chase_demo_objectivelever_336_208_0_0"
    reset_id = "guard_patrol_chase_demo_resetbutton_112_80_0_0"

    spotted = _find_entity(payload, spotted_id)
    assert spotted.get("forbid_flags") == ["demo.guard_patrol_demo_spotted"]
    cfg_root = spotted.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "GuardPatrolDemoSpottedZone"
    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_value") == "GuardPatrolDemoSpottedZone"
    assert sgs.get("set_flags") == {"demo.guard_patrol_demo_spotted": True}
    assert sgs.get("forbid_flags") == ["demo.guard_patrol_demo_spotted"]

    lever = _find_entity(payload, lever_id)
    assert lever.get("forbid_flags") == ["demo.guard_patrol_demo_complete", "demo.guard_patrol_demo_spotted"]

    reset = _find_entity(payload, reset_id)
    assert reset.get("require_flags") == ["demo.guard_patrol_demo_spotted"]
    assert "reset_guard_patrol_demo" in _dialogue_choice_ids(reset)
    cfg_root = reset.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("clear_flags") == ["demo.guard_patrol_demo_spotted"]
    st = cfg_root.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "scenes/guard_patrol_chase_demo.json"
    assert st.get("spawn_id") == "default"


def test_guard_patrol_duo_demo_spotted_zone_and_reset_exist_and_gate_completion() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_duo_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    spotted_id = "guard_patrol_chase_duo_demo_spottedzone_160_112_0_0"
    lever_id = "guard_patrol_chase_duo_demo_objectivelever_336_208_0_0"
    reset_id = "guard_patrol_chase_duo_demo_resetbutton_112_80_0_0"

    spotted = _find_entity(payload, spotted_id)
    assert spotted.get("forbid_flags") == ["demo.guard_patrol_chase_duo_demo_spotted"]
    cfg_root = spotted.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "GuardPatrolChaseDuoDemoSpottedZone"
    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_value") == "GuardPatrolChaseDuoDemoSpottedZone"
    assert sgs.get("set_flags") == {"demo.guard_patrol_chase_duo_demo_spotted": True}
    assert sgs.get("forbid_flags") == ["demo.guard_patrol_chase_duo_demo_spotted"]

    lever = _find_entity(payload, lever_id)
    assert lever.get("forbid_flags") == [
        "demo.guard_patrol_chase_duo_demo_complete",
        "demo.guard_patrol_chase_duo_demo_spotted",
    ]

    reset = _find_entity(payload, reset_id)
    assert reset.get("require_flags") == ["demo.guard_patrol_chase_duo_demo_spotted"]
    assert "reset_guard_patrol_duo_demo" in _dialogue_choice_ids(reset)
    cfg_root = reset.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("clear_flags") == ["demo.guard_patrol_chase_duo_demo_spotted"]
    st = cfg_root.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "scenes/guard_patrol_chase_duo_demo.json"
    assert st.get("spawn_id") == "default"

