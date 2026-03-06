from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT2_CH3_SCENES = [
    "packs/core_regions/scenes/Act2_Chapter3_Fork.json",
    "packs/core_regions/scenes/Act2_Chapter3_RouteA_Run.json",
    "packs/core_regions/scenes/Act2_Chapter3_RouteB_Safe.json",
    "packs/core_regions/scenes/Act2_Chapter3_Rejoin.json",
]

ACT2_CH3_QUEST_IDS = {
    "quest_act2_ch3_choose_route",
    "quest_act2_ch3_route_a_clear",
    "quest_act2_ch3_route_b_clear",
    "quest_act2_ch3_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter2_Sanctum.json",
        "ToAct2Chapter3Fork",
        "packs/core_regions/scenes/Act2_Chapter3_Fork.json",
        "act2_chapter2_complete",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_Fork.json",
        "ToAct2Chapter3RouteA",
        "packs/core_regions/scenes/Act2_Chapter3_RouteA_Run.json",
        "act2_ch3_route_a_selected",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_Fork.json",
        "ToAct2Chapter3RouteB",
        "packs/core_regions/scenes/Act2_Chapter3_RouteB_Safe.json",
        "act2_ch3_route_b_selected",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_RouteA_Run.json",
        "ToAct2Chapter3RejoinFromA",
        "packs/core_regions/scenes/Act2_Chapter3_Rejoin.json",
        "act2_ch3_route_a_clear",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_RouteB_Safe.json",
        "ToAct2Chapter3RejoinFromB",
        "packs/core_regions/scenes/Act2_Chapter3_Rejoin.json",
        "act2_ch3_route_b_clear",
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


def test_act2_ch3_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT2_CH3_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act2_ch3_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act2_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act2_chapter3_fork", "act2_chapter3_route_a_run", "act2_chapter3_route_b_safe", "act2_chapter3_rejoin"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act2_ch3_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_CH3_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act2_ch3_fork_route_selection_flags_are_set() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter3_Fork.json").read_text(encoding="utf-8"))

    route_a_setter = _zone_setter(scene, zone_name="Act2Chapter3RouteASelectZone", flag_name="act2_ch3_route_a_selected")
    route_b_setter = _zone_setter(scene, zone_name="Act2Chapter3RouteBSelectZone", flag_name="act2_ch3_route_b_selected")
    assert isinstance(route_a_setter, dict)
    assert isinstance(route_b_setter, dict)

    set_flags_a = route_a_setter.get("set_flags")
    set_flags_b = route_b_setter.get("set_flags")
    assert isinstance(set_flags_a, dict)
    assert isinstance(set_flags_b, dict)
    assert set_flags_a.get("act2_ch3_route_chosen") is True
    assert set_flags_b.get("act2_ch3_route_chosen") is True


def test_act2_ch3_route_clear_triggers_set_expected_flags() -> None:
    route_a = json.loads(Path("packs/core_regions/scenes/Act2_Chapter3_RouteA_Run.json").read_text(encoding="utf-8"))
    route_b = json.loads(Path("packs/core_regions/scenes/Act2_Chapter3_RouteB_Safe.json").read_text(encoding="utf-8"))

    a_clear = _zone_setter(route_a, zone_name="Act2Chapter3RouteAClearZone", flag_name="act2_ch3_route_a_clear")
    b_clear = _zone_setter(route_b, zone_name="Act2Chapter3RouteBClearZone", flag_name="act2_ch3_route_b_clear")
    assert isinstance(a_clear, dict)
    assert isinstance(b_clear, dict)


def test_act2_ch3_rejoin_references_route_a_or_route_b_and_sets_completion() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter3_Rejoin.json").read_text(encoding="utf-8"))
    set_cfgs = _set_configs(scene)

    ready_from_a = False
    ready_from_b = False
    for cfg in set_cfgs:
        if cfg.get("event_type") != "scene_loaded":
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act2_ch3_rejoin_ready") is not True:
            continue
        require_flags = cfg.get("require_flags") if isinstance(cfg.get("require_flags"), list) else []
        if "act2_ch3_route_a_clear" in require_flags:
            ready_from_a = True
        if "act2_ch3_route_b_clear" in require_flags:
            ready_from_b = True

    assert ready_from_a and ready_from_b

    complete_cfg = _zone_setter(scene, zone_name="Act2Chapter3CompleteZone", flag_name="act2_chapter3_complete")
    assert isinstance(complete_cfg, dict)
    require = complete_cfg.get("require_flags")
    assert isinstance(require, list)
    assert "act2_ch3_rejoin_ready" in require


def test_act2_ch3_checkpoint_exists_with_expected_toast_once() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter3_Rejoin.json").read_text(encoding="utf-8"))
    zone_entity = _find_entity(scene, name="Act2Chapter3CheckpointZone")
    assert isinstance(zone_entity, dict)
    checkpoint_cfg = _zone_setter(scene, zone_name="Act2Chapter3CheckpointZone", flag_name="act2_ch3_checkpoint")
    assert isinstance(checkpoint_cfg, dict)
    assert checkpoint_cfg.get("once") is True
    assert checkpoint_cfg.get("toast") == "Checkpoint reached: Act 2 Chapter 3"
    assert checkpoint_cfg.get("toast_seconds") == 2.0


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_ch3_no_hard_lock_transitions_have_expected_targets_and_flag_gates(
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
