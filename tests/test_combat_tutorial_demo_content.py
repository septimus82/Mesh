from __future__ import annotations

import json
from pathlib import Path


def _find_entity_by_id(payload: dict, entity_id: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def _get_chase_cfg(payload: dict, entity_id: str) -> dict:
    ent = _find_entity_by_id(payload, entity_id)
    cfg_root = ent.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    chase = cfg_root.get("ChaseTarget")
    assert isinstance(chase, dict)
    return chase


def test_combat_tutorial_demo_v2_has_two_dummies_phase_zones_and_reward() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "combat_tutorial_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    chase_a = _get_chase_cfg(payload, "combat_tutorial_demo_trainingdummy_208_128_0_0")
    assert chase_a.get("target_tag") == "player"
    assert chase_a.get("stop_range_tiles") == 1
    assert chase_a.get("los_required") is False

    chase_b = _get_chase_cfg(payload, "combat_tutorial_demo_trainingdummyb_304_128_0_0")
    assert chase_b.get("target_tag") == "player"
    assert chase_b.get("stop_range_tiles") == 1
    assert chase_b.get("los_required") is True

    phase1 = _find_entity_by_id(payload, "combat_tutorial_demo_completezone_336_208_0_0")
    cfg_root = phase1.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "CombatTutorialV2Phase1Zone"

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_field") == "zone"
    assert sgs.get("payload_value") == "CombatTutorialV2Phase1Zone"
    assert sgs.get("set_flags") == {"demo.combat_tutorial_v2_phase1_done": True}

    phase2 = _find_entity_by_id(payload, "combat_tutorial_demo_phase2zone_336_80_0_0")
    cfg_root = phase2.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "CombatTutorialV2Phase2Zone"

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_field") == "zone"
    assert sgs.get("payload_value") == "CombatTutorialV2Phase2Zone"
    assert sgs.get("require_flags") == ["demo.combat_tutorial_v2_phase1_done"]
    assert sgs.get("set_flags") == {"demo.combat_tutorial_v2_phase2_done": True}

    complete = _find_entity_by_id(payload, "combat_tutorial_demo_v2completezone_144_208_0_0")
    cfg_root = complete.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "CombatTutorialV2CompleteZone"

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_field") == "zone"
    assert sgs.get("payload_value") == "CombatTutorialV2CompleteZone"
    assert sgs.get("require_flags") == ["demo.combat_tutorial_v2_phase2_done"]
    assert sgs.get("set_flags") == {"demo.combat_tutorial_complete": True, "demo.combat_tutorial_v2_complete": True}

    chest = _find_entity_by_id(payload, "combat_tutorial_demo_rewardchest_112_176_0_0")
    assert chest.get("require_flags") == ["demo.combat_tutorial_v2_complete"]
    forbid = chest.get("forbid_flags")
    assert isinstance(forbid, list)
    assert "demo.combat_tutorial_reward_claimed" in forbid
    assert "demo.combat_tutorial_v3_failed" in forbid

    claimed = _find_entity_by_id(payload, "combat_tutorial_demo_rewardclaimed_144_176_0_0")
    assert claimed.get("require_flags") == ["demo.combat_tutorial_reward_claimed"]

    tilemap = payload.get("tilemap")
    assert isinstance(tilemap, dict)
    overrides = tilemap.get("overrides")
    assert isinstance(overrides, dict)
    layers = overrides.get("layers")
    assert isinstance(layers, dict)
    platforms = layers.get("platforms")
    assert isinstance(platforms, list)
    assert any(v for v in platforms)


def test_combat_tutorial_demo_v3_has_fail_zone_and_reset_button() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "combat_tutorial_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    fail = _find_entity_by_id(payload, "combat_tutorial_demo_failzone_240_128_0_0")
    assert "demo.combat_tutorial_v3_failed" in (fail.get("forbid_flags") or [])
    cfg_root = fail.get("behaviour_config")
    assert isinstance(cfg_root, dict)

    tz = cfg_root.get("TriggerZone")
    assert isinstance(tz, dict)
    assert tz.get("trigger_target") == "Player"
    assert tz.get("zone_id") == "CombatTutorialFailZone"

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "entered_zone"
    assert sgs.get("payload_field") == "zone"
    assert sgs.get("payload_value") == "CombatTutorialFailZone"
    assert sgs.get("set_flags") == {"demo.combat_tutorial_v3_failed": True}
    assert "demo.combat_tutorial_v3_failed" in (sgs.get("forbid_flags") or [])

    phase2 = _find_entity_by_id(payload, "combat_tutorial_demo_phase2zone_336_80_0_0")
    assert "demo.combat_tutorial_v3_failed" in (phase2.get("forbid_flags") or [])

    complete = _find_entity_by_id(payload, "combat_tutorial_demo_v2completezone_144_208_0_0")
    assert "demo.combat_tutorial_v3_failed" in (complete.get("forbid_flags") or [])

    reset = _find_entity_by_id(payload, "combat_tutorial_demo_resetbutton_144_80_0_0")
    assert "demo.combat_tutorial_v3_failed" in (reset.get("require_flags") or [])
    cfg_root = reset.get("behaviour_config")
    assert isinstance(cfg_root, dict)

    dlg = cfg_root.get("Dialogue")
    assert isinstance(dlg, dict)
    dialogue = dlg.get("dialogue")
    assert isinstance(dialogue, dict)
    nodes = dialogue.get("nodes")
    assert isinstance(nodes, dict)
    root = nodes.get("root")
    assert isinstance(root, dict)
    choices = root.get("choices")
    assert isinstance(choices, list)
    assert any(isinstance(c, dict) and c.get("id") == "reset_combat_tutorial_run" for c in choices)

    sgs = cfg_root.get("SetGameStateOnEvent")
    assert isinstance(sgs, dict)
    assert sgs.get("event_type") == "dialogue_choice"
    assert sgs.get("payload_field") == "choice_id"
    assert sgs.get("payload_value") == "reset_combat_tutorial_run"
    clear_flags = sgs.get("clear_flags")
    assert isinstance(clear_flags, list)
    for flag in [
        "demo.combat_tutorial_v3_failed",
        "demo.combat_tutorial_v2_phase1_done",
        "demo.combat_tutorial_v2_phase2_done",
        "demo.combat_tutorial_v2_complete",
        "demo.combat_tutorial_complete",
    ]:
        assert flag in clear_flags

    transition = cfg_root.get("SceneTransition")
    assert isinstance(transition, dict)
    assert transition.get("event_type") == "dialogue_choice"
    assert transition.get("event_field") == "choice_id"
    assert transition.get("event_value") == "reset_combat_tutorial_run"
    assert transition.get("target_scene") == "scenes/combat_tutorial_demo.json"
    assert transition.get("spawn_id") == "default"
