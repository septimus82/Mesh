from __future__ import annotations

import json
from pathlib import Path


def _find_entity_by_id(payload: dict, entity_id: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def test_guard_patrol_chase_demo_has_one_time_hint_hook() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    ent = _find_entity_by_id(payload, "guard_patrol_chase_demo_hintzone_80_80_0_0")
    assert ent.get("mesh_name") == "GuardPatrolDemoHintZone"
    assert ent.get("forbid_flags") == ["demo.guard_patrol_demo_hint_seen"]

    behaviours = ent.get("behaviours")
    assert isinstance(behaviours, list)
    assert "TriggerZone" in behaviours
    assert "SetGameStateOnEvent" in behaviours

    cfg_root = ent.get("behaviour_config")
    assert isinstance(cfg_root, dict)

    tzcfg = cfg_root.get("TriggerZone")
    assert isinstance(tzcfg, dict)
    assert tzcfg.get("trigger_target") == "Guard"
    assert float(tzcfg.get("trigger_radius")) > 0.0

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_field") == "zone"
    assert sgs.get("payload_value") == "GuardPatrolDemoHintZone"
    assert sgs.get("once") is True
    assert sgs.get("forbid_flags") == ["demo.guard_patrol_demo_hint_seen"]
    assert sgs.get("set_flags") == {"demo.guard_patrol_demo_hint_seen": True}
    assert isinstance(sgs.get("toast"), str) and sgs.get("toast")


def test_upper_hall_has_completion_and_reward_markers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    complete = _find_entity_by_id(payload, "upper_hall_guardpatrolchasedemo_complete_272_64_0_0")
    assert complete.get("require_flags") == ["demo.guard_patrol_demo_complete"]

    claimed = _find_entity_by_id(payload, "upper_hall_guardpatrolchasedemo_reward_288_64_0_0")
    assert claimed.get("require_flags") == ["demo.guard_patrol_demo_reward_claimed"]

