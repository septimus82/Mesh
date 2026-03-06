from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT2_CH1_SCENES = [
    "packs/core_regions/scenes/Act2_Chapter1_Threshold.json",
    "packs/core_regions/scenes/Act2_Chapter1_HazardHall.json",
    "packs/core_regions/scenes/Act2_Chapter1_SafeRoom.json",
]

ACT2_CH1_QUEST_IDS = {
    "quest_act2_ch1_briefing",
    "quest_act2_ch1_hazard_clear",
    "quest_act2_ch1_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act1_Chapter7_Aftermath.json",
        "ToAct2Chapter1Threshold",
        "packs/core_regions/scenes/Act2_Chapter1_Threshold.json",
        "act1_act1_complete",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter1_Threshold.json",
        "ToAct2Chapter1HazardHall",
        "packs/core_regions/scenes/Act2_Chapter1_HazardHall.json",
        "act2_ch1_briefed",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter1_HazardHall.json",
        "ToAct2Chapter1SafeRoom",
        "packs/core_regions/scenes/Act2_Chapter1_SafeRoom.json",
        "act2_ch1_hazard_cleared",
    ),
]


def _find_entity(scene: dict, *, name: str) -> dict | None:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return None
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        if entity.get("name") == name or entity.get("mesh_name") == name:
            return entity
    return None


def _set_game_state_configs_for_zone(scene: dict, *, zone_name: str) -> list[dict]:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return []
    matches: list[dict] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        set_cfg = cfg.get("SetGameStateOnEvent")
        if not isinstance(set_cfg, dict):
            continue
        if (
            set_cfg.get("event_type") == "entered_zone"
            and set_cfg.get("payload_field") == "zone"
            and set_cfg.get("payload_value") == zone_name
        ):
            matches.append(set_cfg)
    return matches


def _collect_scene_event_ids(scene: dict) -> set[str]:
    event_ids: set[str] = set()
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return event_ids
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        trigger_cfg = cfg.get("TriggerZone")
        if isinstance(trigger_cfg, dict):
            on_trigger = trigger_cfg.get("on_trigger")
            if isinstance(on_trigger, str) and on_trigger:
                event_ids.add(on_trigger)
    return event_ids


def _assert_scene_references_resolve(scene_path: str, scene: dict) -> None:
    entities = scene.get("entities")
    assert isinstance(entities, list), f"{scene_path} must contain an entities list"
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        sprite = entity.get("sprite")
        if isinstance(sprite, str) and sprite:
            assert Path(sprite).exists(), f"{scene_path} entity[{idx}] sprite missing: {sprite}"
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        transition_cfg = cfg.get("SceneTransition")
        if isinstance(transition_cfg, dict):
            target_scene = transition_cfg.get("target_scene")
            if isinstance(target_scene, str) and target_scene:
                assert Path(target_scene).exists(), f"{scene_path} transition target missing: {target_scene}"


def test_act2_ch1_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT2_CH1_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)
        assert isinstance(scene.get("entities"), list)


def test_act2_ch1_world_registry_exists_and_points_to_scenes() -> None:
    world_path = Path("worlds/act2_chapter1_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act2_chapter1_threshold"
    for key in ["act2_chapter1_threshold", "act2_chapter1_hazard_hall", "act2_chapter1_safe_room"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict)
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act2_ch1_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_CH1_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act2_ch1_hazard_zone_exists_and_has_damage_action() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_HazardHall.json").read_text(encoding="utf-8"))
    hazard_zone = _find_entity(scene, name="Act2Chapter1HazardWarnZone")
    assert isinstance(hazard_zone, dict), "missing hazard warning trigger zone"

    event_ids = _collect_scene_event_ids(scene)
    assert "act2_ch1_hazard_warn" in event_ids

    entities = scene.get("entities")
    assert isinstance(entities, list)
    hazard_damage_entities = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        dot_cfg = cfg.get("DamageOnTouch")
        if not isinstance(dot_cfg, dict):
            continue
        damage = dot_cfg.get("damage")
        if isinstance(damage, (int, float)) and float(damage) > 0.0:
            hazard_damage_entities.append(dot_cfg)

    assert hazard_damage_entities, "hazard hall must include at least one positive DamageOnTouch action"
    assert any(cfg.get("target_name") == "Player" for cfg in hazard_damage_entities)
    assert all(cfg.get("once") is True for cfg in hazard_damage_entities)


def test_act2_ch1_hazard_warning_sign_and_toast_exist() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_HazardHall.json").read_text(encoding="utf-8"))
    sign = _find_entity(scene, name="Act2Ch1HazardWarningSign")
    assert isinstance(sign, dict), "missing hazard warning sign entity"

    setters = _set_game_state_configs_for_zone(scene, zone_name="Act2Chapter1HazardWarnZone")
    assert setters, "missing hazard warning state sync"
    found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch1_hazard_warned") is True:
            found = True
            assert setter.get("once") is True
            assert setter.get("toast") == "Hazard: stay out of the red zone."
            assert setter.get("toast_seconds") == 2.0
    assert found, "hazard warning setter must set act2_ch1_hazard_warned"

    grace_setter_found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch1_hazard_warn_seen") is True:
            grace_setter_found = True
            assert setter.get("once") is True
            assert setter.get("toast") == "Warning: damage ticks every 1s. Step out to recover."
            assert setter.get("toast_seconds") == 2.0
    assert grace_setter_found, "missing grace cue setter for act2_ch1_hazard_warn_seen"


def test_act2_ch1_hazard_clear_toast_is_deterministic() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_HazardHall.json").read_text(encoding="utf-8"))
    for zone_name in ("Act2Chapter1HazardClearZone", "Act2Chapter1HazardClearFallbackZone"):
        setters = _set_game_state_configs_for_zone(scene, zone_name=zone_name)
        assert setters, f"missing hazard clear setter for {zone_name}"
        found = False
        for setter in setters:
            set_flags = setter.get("set_flags")
            if not isinstance(set_flags, dict):
                continue
            if set_flags.get("act2_ch1_hazard_cleared") is True:
                found = True
                assert setter.get("once") is True
                assert setter.get("toast") == "Objective complete: Hazard cleared."
                assert setter.get("toast_seconds") == 2.0
        assert found, f"missing act2_ch1_hazard_cleared setter for {zone_name}"


def test_act2_ch1_checkpoint_exists_and_toast_once() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_SafeRoom.json").read_text(encoding="utf-8"))
    zone_entity = _find_entity(scene, name="Act2Chapter1CheckpointZone")
    assert isinstance(zone_entity, dict), "missing Act2Chapter1CheckpointZone"
    setters = _set_game_state_configs_for_zone(scene, zone_name="Act2Chapter1CheckpointZone")
    assert setters, "missing checkpoint state sync"
    found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch1_checkpoint") is True:
            found = True
            assert setter.get("once") is True
            assert setter.get("toast") == "Checkpoint reached: Act 2 Chapter 1"
            assert setter.get("toast_seconds") == 2.0
    assert found, "checkpoint setter must set act2_ch1_checkpoint"


def test_act2_ch1_safe_room_transition_has_recheck_or_unconditional_enable_path() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_HazardHall.json").read_text(encoding="utf-8"))
    transition = _find_entity(scene, name="ToAct2Chapter1SafeRoom")
    assert isinstance(transition, dict), "missing ToAct2Chapter1SafeRoom transition"
    require_flags = transition.get("require_flags") if isinstance(transition.get("require_flags"), list) else []
    has_flag_gate = "act2_ch1_hazard_cleared" in require_flags

    has_scene_load_recheck = False
    entities = scene.get("entities")
    assert isinstance(entities, list)
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        set_cfg = cfg.get("SetGameStateOnEvent")
        if not isinstance(set_cfg, dict):
            continue
        if set_cfg.get("event_type") != "scene_loaded":
            continue
        set_flags = set_cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch1_hazard_cleared") is not True:
            continue
        require = set_cfg.get("require_flags")
        if isinstance(require, list) and "act2_ch1_hazard_cleared" in require:
            has_scene_load_recheck = True
            break

    assert has_flag_gate or has_scene_load_recheck


def test_act2_ch1_threshold_reentry_hint_escalation_gating_contract() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter1_Threshold.json").read_text(encoding="utf-8"))
    zone_entity = _find_entity(scene, name="Act2Chapter1ThresholdReentryProbeZone")
    assert isinstance(zone_entity, dict), "missing threshold reentry probe zone"
    setters = _set_game_state_configs_for_zone(scene, zone_name="Act2Chapter1ThresholdReentryProbeZone")
    assert setters, "missing threshold reentry setters"

    first_visit = None
    second_hint = None
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch1_threshold_reentry_1") is True:
            first_visit = setter
        if set_flags.get("act2_ch1_threshold_reentry_2") is True:
            second_hint = setter

    assert isinstance(first_visit, dict)
    assert isinstance(second_hint, dict)

    first_forbid = first_visit.get("forbid_flags")
    assert first_visit.get("once") is True
    assert isinstance(first_forbid, list)
    assert "act2_ch1_briefed" in first_forbid
    assert "act2_ch1_threshold_reentry_1" in first_forbid

    second_require = second_hint.get("require_flags")
    second_forbid = second_hint.get("forbid_flags")
    assert second_hint.get("once") is True
    assert isinstance(second_require, list)
    assert "act2_ch1_threshold_reentry_1" in second_require
    assert isinstance(second_forbid, list)
    assert "act2_ch1_briefed" in second_forbid
    assert "act2_ch1_threshold_reentry_2" in second_forbid


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_ch1_no_hard_lock_transitions_have_expected_targets_and_flag_gates(
    scene_path: str, transition_name: str, expected_target: str, required_flag: str
) -> None:
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    entity = _find_entity(scene, name=transition_name)
    assert isinstance(entity, dict), f"{scene_path} missing transition entity {transition_name}"
    cfg = entity.get("behaviour_config")
    assert isinstance(cfg, dict)
    transition = cfg.get("SceneTransition")
    assert isinstance(transition, dict), f"{scene_path} missing SceneTransition for {transition_name}"
    assert transition.get("target_scene") == expected_target
    assert Path(expected_target).exists(), f"missing transition target scene {expected_target}"

    entity_require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
    transition_require = transition.get("require_flags") if isinstance(transition.get("require_flags"), list) else []
    transition_condition = transition.get("condition")
    references_required_flag = required_flag in entity_require or required_flag in transition_require
    if not references_required_flag and isinstance(transition_condition, str):
        references_required_flag = required_flag in transition_condition
    assert references_required_flag, (
        f"{scene_path} {transition_name} must reference required gate flag {required_flag}"
    )
