from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT2_CH5_SCENES = [
    "packs/core_regions/scenes/Act2_Chapter5_Antechamber.json",
    "packs/core_regions/scenes/Act2_Chapter5_Overseer.json",
    "packs/core_regions/scenes/Act2_Chapter5_Epilogue.json",
]

ACT2_CH5_QUEST_IDS = {
    "quest_act2_ch5_ante_briefing",
    "quest_act2_ch5_overseer_defeated",
    "quest_act2_ch5_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter4_Final.json",
        "ToAct2Chapter5Antechamber",
        "packs/core_regions/scenes/Act2_Chapter5_Antechamber.json",
        "act2_chapter4_complete",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter5_Antechamber.json",
        "ToAct2Chapter5Overseer",
        "packs/core_regions/scenes/Act2_Chapter5_Overseer.json",
        "act2_ch5_briefed",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter5_Overseer.json",
        "ToAct2Chapter5Epilogue",
        "packs/core_regions/scenes/Act2_Chapter5_Epilogue.json",
        "act2_ch5_boss_defeated",
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


def test_act2_ch5_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT2_CH5_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act2_ch5_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act2_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act2_chapter5_antechamber", "act2_chapter5_overseer", "act2_chapter5_epilogue"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act2_ch5_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_CH5_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act2_ch5_overseer_has_boss_aggro_trigger_once_true() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    aggro_zone = _find_entity(scene, name="Act2Chapter5BossAggroZone")
    assert isinstance(aggro_zone, dict)
    setter = _zone_setter(scene, zone_name="Act2Chapter5BossAggroZone", flag_name="act2_ch5_boss_entered")
    assert isinstance(setter, dict)
    assert setter.get("once") is True


def test_act2_ch5_overseer_has_aoe_warn_marker_and_toast_presence() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    marker = _find_entity(scene, name="Act2Ch5AoeWarnMarker")
    assert isinstance(marker, dict)
    setter = _zone_setter(scene, zone_name="Act2Chapter5AoeWarnZone", flag_name="act2_ch5_aoe_warn_seen")
    assert isinstance(setter, dict)
    assert setter.get("toast") == "Impact in 2s..."
    assert setter.get("toast_seconds") == 2.0


def test_act2_ch5_overseer_suppression_switches_set_flag_with_deterministic_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    configs = _set_configs(scene)
    matched: list[dict] = []
    for cfg in configs:
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_field") != "zone":
            continue
        if cfg.get("payload_value") not in {
            "Act2Chapter5SuppressionSwitchZoneA",
            "Act2Chapter5SuppressionSwitchZoneB",
        }:
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch5_hazard_suppressed") is not True:
            continue
        matched.append(cfg)
    assert len(matched) >= 2
    for cfg in matched:
        assert cfg.get("toast") == "Suppression active."
        assert cfg.get("toast_seconds") == 2.0
        assert cfg.get("once") is False


def test_act2_ch5_overseer_has_shard_a_and_shard_b_payoff_presence() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)
    shard_a_found = False
    shard_b_found = False
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        require_flags = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        if "act2_ch3_reward_shard_a" in require_flags:
            shard_a_found = True
        if "act2_ch3_reward_shard_b" in require_flags:
            shard_b_found = True
    assert shard_a_found
    assert shard_b_found


def test_act2_ch5_overseer_defeat_setter_exists_with_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    setter = _zone_setter(scene, zone_name="Act2Chapter5BossDefeatZone", flag_name="act2_ch5_boss_defeated")
    assert isinstance(setter, dict)
    assert setter.get("once") is True
    assert setter.get("toast") == "Objective complete: Overseer defeated."
    assert setter.get("toast_seconds") == 2.0


def test_act2_ch5_checkpoints_exist_with_expected_toasts_and_once() -> None:
    ante = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Antechamber.json").read_text(encoding="utf-8"))
    epilogue = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Epilogue.json").read_text(encoding="utf-8"))

    ante_cfg = _zone_setter(ante, zone_name="Act2Chapter5AnteCheckpointZone", flag_name="act2_ch5_checkpoint_ante")
    assert isinstance(ante_cfg, dict)
    assert ante_cfg.get("once") is True
    assert ante_cfg.get("toast") == "Checkpoint reached: Act 2 Chapter 5 (Antechamber)"
    assert ante_cfg.get("toast_seconds") == 2.0

    end_cfg = _zone_setter(
        epilogue, zone_name="Act2Chapter5EpilogueCheckpointZone", flag_name="act2_ch5_checkpoint_end"
    )
    assert isinstance(end_cfg, dict)
    assert end_cfg.get("once") is True
    assert end_cfg.get("toast") == "Checkpoint reached: Act 2 Chapter 5 (Epilogue)"
    assert end_cfg.get("toast_seconds") == 2.0


def test_act2_ch5_overseer_has_scene_load_recheck_for_boss_defeat_gate() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    found = False
    for cfg in _set_configs(scene):
        if cfg.get("event_type") != "scene_loaded":
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch5_boss_defeated") is not True:
            continue
        require = cfg.get("require_flags")
        if isinstance(require, list) and "act2_ch5_boss_defeated" in require:
            found = True
            break
    assert found


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_ch5_no_hard_lock_transitions_have_expected_targets_and_flag_gates(
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
