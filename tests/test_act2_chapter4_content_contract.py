from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT2_CH4_SCENES = [
    "packs/core_regions/scenes/Act2_Chapter4_Hub.json",
    "packs/core_regions/scenes/Act2_Chapter4_PathA.json",
    "packs/core_regions/scenes/Act2_Chapter4_PathB.json",
    "packs/core_regions/scenes/Act2_Chapter4_Final.json",
]

ACT2_CH4_QUEST_IDS = {
    "quest_act2_ch4_enter_hub",
    "quest_act2_ch4_path_clear",
    "quest_act2_ch4_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter3_Rejoin.json",
        "ToAct2Chapter4Hub",
        "packs/core_regions/scenes/Act2_Chapter4_Hub.json",
        "act2_chapter3_complete",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter4_Hub.json",
        "ToAct2Chapter4PathA",
        "packs/core_regions/scenes/Act2_Chapter4_PathA.json",
        "act2_ch3_reward_shard_a",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter4_Hub.json",
        "ToAct2Chapter4PathB",
        "packs/core_regions/scenes/Act2_Chapter4_PathB.json",
        "act2_ch3_reward_shard_b",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter4_PathA.json",
        "ToAct2Chapter4FinalFromA",
        "packs/core_regions/scenes/Act2_Chapter4_Final.json",
        "act2_ch4_path_clear",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter4_PathB.json",
        "ToAct2Chapter4FinalFromB",
        "packs/core_regions/scenes/Act2_Chapter4_Final.json",
        "act2_ch4_path_clear",
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


def _set_configs(scene: dict) -> list[dict]:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return []
    out: list[dict] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        set_cfg = cfg.get("SetGameStateOnEvent")
        if isinstance(set_cfg, dict):
            out.append(set_cfg)
    return out


def _zone_setter(scene: dict, *, zone_name: str, flag_name: str) -> dict | None:
    for cfg in _set_configs(scene):
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_field") != "zone":
            continue
        if cfg.get("payload_value") != zone_name:
            continue
        set_flags = cfg.get("set_flags")
        if isinstance(set_flags, dict) and set_flags.get(flag_name) is True:
            return cfg
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


def test_act2_ch4_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT2_CH4_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act2_ch4_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act2_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act2_chapter4_hub", "act2_chapter4_path_a", "act2_chapter4_path_b", "act2_chapter4_final"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act2_ch4_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_CH4_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act2_ch4_hub_has_two_shard_gated_exits() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter4_Hub.json").read_text(encoding="utf-8"))
    door_a = _find_entity(scene, name="ToAct2Chapter4PathA")
    door_b = _find_entity(scene, name="ToAct2Chapter4PathB")
    assert isinstance(door_a, dict)
    assert isinstance(door_b, dict)

    req_a = door_a.get("require_flags") if isinstance(door_a.get("require_flags"), list) else []
    req_b = door_b.get("require_flags") if isinstance(door_b.get("require_flags"), list) else []
    assert "act2_ch3_reward_shard_a" in req_a
    assert "act2_ch3_reward_shard_b" in req_b


def test_act2_ch4_hub_has_shard_specific_entry_hint_toasts() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter4_Hub.json").read_text(encoding="utf-8"))
    configs = _set_configs(scene)

    found_a = False
    found_b = False
    for cfg in configs:
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_value") != "Act2Chapter4HubEntryZone":
            continue
        require = cfg.get("require_flags") if isinstance(cfg.get("require_flags"), list) else []
        toast = cfg.get("toast")
        if "act2_ch3_reward_shard_a" in require and toast == "The A Door hums in your hand.":
            found_a = True
        if "act2_ch3_reward_shard_b" in require and toast == "The B Door answers your touch.":
            found_b = True

    assert found_a
    assert found_b


def test_act2_ch4_path_clear_setter_exists_with_deterministic_toast() -> None:
    expected_toast = "Objective complete: Path cleared."
    for scene_path in [
        "packs/core_regions/scenes/Act2_Chapter4_PathA.json",
        "packs/core_regions/scenes/Act2_Chapter4_PathB.json",
    ]:
        scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
        cfg = _zone_setter(scene, zone_name="Act2Chapter4PathClearZone", flag_name="act2_ch4_path_clear")
        assert isinstance(cfg, dict), f"missing path clear setter in {scene_path}"
        assert cfg.get("once") is True
        assert cfg.get("toast") == expected_toast
        assert cfg.get("toast_seconds") == 2.0


def test_act2_ch4_final_checkpoint_exists_with_expected_toast_once() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter4_Final.json").read_text(encoding="utf-8"))
    zone_entity = _find_entity(scene, name="Act2Chapter4CheckpointZone")
    assert isinstance(zone_entity, dict)

    cfg = _zone_setter(scene, zone_name="Act2Chapter4CheckpointZone", flag_name="act2_ch4_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 2 Chapter 4"
    assert cfg.get("toast_seconds") == 2.0


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_ch4_no_hard_lock_transitions_have_expected_targets_and_flag_gates(
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
