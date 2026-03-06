from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT2_CH2_SCENES = [
    "packs/core_regions/scenes/Act2_Chapter2_SwitchRoom.json",
    "packs/core_regions/scenes/Act2_Chapter2_HazardRun.json",
    "packs/core_regions/scenes/Act2_Chapter2_Sanctum.json",
]

ACT2_CH2_QUEST_IDS = {
    "quest_act2_ch2_switch_learned",
    "quest_act2_ch2_hazard_run_clear",
    "quest_act2_ch2_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter1_SafeRoom.json",
        "ToAct2Chapter2SwitchRoom",
        "packs/core_regions/scenes/Act2_Chapter2_SwitchRoom.json",
        "act2_chapter1_complete",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter2_SwitchRoom.json",
        "ToAct2Chapter2HazardRun",
        "packs/core_regions/scenes/Act2_Chapter2_HazardRun.json",
        "act2_ch2_switch_pulled",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter2_HazardRun.json",
        "ToAct2Chapter2Sanctum",
        "packs/core_regions/scenes/Act2_Chapter2_Sanctum.json",
        "act2_ch2_run_clear",
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


def _set_state_configs(scene: dict) -> list[dict]:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return []
    configs: list[dict] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        state_cfg = cfg.get("SetGameStateOnEvent")
        if isinstance(state_cfg, dict):
            configs.append(state_cfg)
    return configs


def test_act2_ch2_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT2_CH2_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)
        assert isinstance(scene.get("entities"), list)


def test_act2_ch2_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act2_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act2_chapter2_switch_room", "act2_chapter2_hazard_run", "act2_chapter2_sanctum"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists(), f"missing scene file for {key}"


def test_act2_ch2_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_CH2_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act2_ch2_switch_sets_hazard_suppression_flags_with_deterministic_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter2_SwitchRoom.json").read_text(encoding="utf-8"))
    switch = _find_entity(scene, name="Act2Ch2HazardControlSwitch")
    assert isinstance(switch, dict), "missing switch interactable"

    setters = _set_state_configs(scene)
    target = None
    for setter in setters:
        if setter.get("event_type") != "act2_ch2_switch_pull":
            continue
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch2_hazard_suppressed") is True:
            target = setter
            break
    assert isinstance(target, dict), "missing switch state sync for hazard suppression"
    set_flags = target.get("set_flags")
    assert isinstance(set_flags, dict)
    assert set_flags.get("act2_ch2_hazard_suppressed") is True
    assert set_flags.get("act2_ch2_hazard_suppressed_until") is True
    assert target.get("once") is True
    assert target.get("toast") == "Hazard suppression active."
    assert target.get("toast_seconds") == 2.0


def test_act2_ch2_hazard_damage_entities_reference_suppression_gating() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter2_HazardRun.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)
    hazard_entities: list[dict] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        touch = cfg.get("DamageOnTouch")
        if not isinstance(touch, dict):
            continue
        damage = touch.get("damage")
        if isinstance(damage, (int, float)) and float(damage) > 0.0:
            hazard_entities.append(entity)

    assert hazard_entities, "hazard run must contain damage entities"
    for entity in hazard_entities:
        require_flags = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        forbid_flags = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
        assert (
            "act2_ch2_hazard_suppressed" in require_flags
            or "act2_ch2_hazard_suppressed" in forbid_flags
        ), "hazard entity missing suppression gating reference"


def test_act2_ch2_checkpoint_exists_with_expected_toast_once() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter2_Sanctum.json").read_text(encoding="utf-8"))
    checkpoint_zone = _find_entity(scene, name="Act2Chapter2CheckpointZone")
    assert isinstance(checkpoint_zone, dict), "missing Act2Chapter2CheckpointZone"

    setters = _set_state_configs(scene)
    target = None
    for setter in setters:
        if setter.get("event_type") != "entered_zone":
            continue
        if setter.get("payload_value") != "Act2Chapter2CheckpointZone":
            continue
        set_flags = setter.get("set_flags")
        if isinstance(set_flags, dict) and set_flags.get("act2_ch2_checkpoint") is True:
            target = setter
            break
    assert isinstance(target, dict), "missing checkpoint state sync"
    assert target.get("once") is True
    assert target.get("toast") == "Checkpoint reached: Act 2 Chapter 2"
    assert target.get("toast_seconds") == 2.0


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_ch2_no_hard_lock_transitions_have_expected_targets_and_flag_gates(
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
