from __future__ import annotations

import json
from pathlib import Path


def _find_by_name(payload: dict, name: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("name") == name), None)
    assert isinstance(ent, dict)
    return ent


def test_upper_hall_reset_demos_station_clears_all_demo_flags_and_reloads() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    station = _find_by_name(payload, "ResetDemosStation")
    behaviours = station.get("behaviours")
    assert isinstance(behaviours, list)
    assert "Dialogue" in behaviours
    assert "SetGameStateOnEvent" in behaviours
    assert "SceneTransition" in behaviours

    behaviour_config = station.get("behaviour_config")
    assert isinstance(behaviour_config, dict)

    dialogue_cfg = behaviour_config.get("Dialogue")
    assert isinstance(dialogue_cfg, dict)
    dialogue = dialogue_cfg.get("dialogue")
    assert isinstance(dialogue, dict)
    nodes = dialogue.get("nodes")
    assert isinstance(nodes, dict)
    root = nodes.get("root")
    assert isinstance(root, dict)
    choices = root.get("choices")
    assert isinstance(choices, list)
    assert any(isinstance(c, dict) and c.get("id") == "reset_all_demos_confirm" for c in choices)

    sgs = behaviour_config.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "dialogue_choice"
    assert sgs.get("payload_field") == "choice_id"
    assert sgs.get("payload_value") == "reset_all_demos_confirm"

    clear_flags = sgs.get("clear_flags")
    assert isinstance(clear_flags, list)
    expected_flags = [
        "demo.guard_patrol_demo_hint_seen",
        "demo.guard_patrol_demo_spotted",
        "demo.guard_patrol_demo_complete",
        "demo.guard_patrol_demo_reward_claimed",
        "demo.guard_patrol_chase_duo_demo_hint_seen",
        "demo.guard_patrol_chase_duo_demo_spotted",
        "demo.guard_patrol_chase_duo_demo_complete",
        "demo.guard_patrol_chase_duo_demo_reward_claimed",
        "demo.micro_stealth_ultimate_reward_claimed",
        "demo.combat_tutorial_hint_seen",
        "demo.combat_tutorial_complete",
        "demo.combat_tutorial_reward_claimed",
        "demo.combat_tutorial_v2_phase1_done",
        "demo.combat_tutorial_v2_phase2_done",
        "demo.combat_tutorial_v2_complete",
        "demo.combat_tutorial_v3_failed",
    ]
    for flag in expected_flags:
        assert flag in clear_flags

    transition = behaviour_config.get("SceneTransition")
    assert isinstance(transition, dict)
    assert transition.get("event_type") == "dialogue_choice"
    assert transition.get("event_field") == "choice_id"
    assert transition.get("event_value") == "reset_all_demos_confirm"
    assert transition.get("target_scene") == "scenes/upper_hall.json"
    assert transition.get("spawn_id") == "upper_return"
