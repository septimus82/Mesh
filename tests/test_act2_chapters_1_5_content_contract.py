from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT2_QUEST_IDS = {
    "quest_act2_ch1_briefing",
    "quest_act2_ch1_hazard_clear",
    "quest_act2_ch1_complete",
    "quest_act2_ch2_switch_learned",
    "quest_act2_ch2_hazard_run_clear",
    "quest_act2_ch2_complete",
    "quest_act2_ch3_choose_route",
    "quest_act2_ch3_route_a_clear",
    "quest_act2_ch3_route_b_clear",
    "quest_act2_ch3_complete",
    "quest_act2_ch4_enter_hub",
    "quest_act2_ch4_path_clear",
    "quest_act2_ch4_complete",
    "quest_act2_ch5_ante_briefing",
    "quest_act2_ch5_overseer_defeated",
    "quest_act2_ch5_complete",
}

CHECKPOINT_EXPECTATIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter1_SafeRoom.json",
        "Act2Chapter1CheckpointZone",
        "act2_ch1_checkpoint",
        "Checkpoint reached: Act 2 Chapter 1",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter2_Sanctum.json",
        "Act2Chapter2CheckpointZone",
        "act2_ch2_checkpoint",
        "Checkpoint reached: Act 2 Chapter 2",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_Rejoin.json",
        "Act2Chapter3CheckpointZone",
        "act2_ch3_checkpoint",
        "Checkpoint reached: Act 2 Chapter 3",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter4_Final.json",
        "Act2Chapter4CheckpointZone",
        "act2_ch4_checkpoint",
        "Checkpoint reached: Act 2 Chapter 4",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter5_Antechamber.json",
        "Act2Chapter5AnteCheckpointZone",
        "act2_ch5_checkpoint_ante",
        "Checkpoint reached: Act 2 Chapter 5 (Antechamber)",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter5_Epilogue.json",
        "Act2Chapter5EpilogueCheckpointZone",
        "act2_ch5_checkpoint_end",
        "Checkpoint reached: Act 2 Chapter 5 (Epilogue)",
    ),
]

REENTRY_EXPECTATIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter1_Threshold.json",
        "Act2Chapter1ThresholdReentryProbeZone",
        "act2_ch1_threshold_reentry_1",
        "act2_ch1_threshold_reentry_2",
        "act2_ch1_briefed",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter2_SwitchRoom.json",
        "Act2Chapter2SwitchRoomReentryProbeZone",
        "act2_ch2_switchroom_reentry_1",
        "act2_ch2_switchroom_reentry_2",
        "act2_ch2_switch_pulled",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter3_Fork.json",
        "Act2Chapter3ForkReentryProbeZone",
        "act2_ch3_fork_reentry_1",
        "act2_ch3_fork_reentry_2",
        "act2_ch3_route_chosen",
    ),
    (
        "packs/core_regions/scenes/Act2_Chapter5_Antechamber.json",
        "Act2Chapter5AnteReentryProbeZone",
        "act2_ch5_ante_reentry_1",
        "act2_ch5_ante_reentry_2",
        "act2_ch5_boss_entered",
    ),
]

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


def test_act2_ch1_to_ch5_quests_have_non_empty_objective_text() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT2_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


@pytest.mark.parametrize(("scene_path", "zone_name", "flag_name", "expected_toast"), CHECKPOINT_EXPECTATIONS)
def test_act2_ch1_to_ch5_checkpoint_flags_have_once_and_toast(
    scene_path: str, zone_name: str, flag_name: str, expected_toast: str
) -> None:
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    cfg = _zone_setter(scene, zone_name=zone_name, flag_name=flag_name)
    assert isinstance(cfg, dict), f"missing checkpoint setter {flag_name} in {scene_path}"
    assert cfg.get("once") is True
    assert cfg.get("toast") == expected_toast
    assert cfg.get("toast_seconds") == 2.0


@pytest.mark.parametrize(("scene_path", "zone_name", "first_flag", "second_flag", "done_flag"), REENTRY_EXPECTATIONS)
def test_act2_reentry_escalation_contract_presence(
    scene_path: str, zone_name: str, first_flag: str, second_flag: str, done_flag: str
) -> None:
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    first_cfg = _zone_setter(scene, zone_name=zone_name, flag_name=first_flag)
    second_cfg = _zone_setter(scene, zone_name=zone_name, flag_name=second_flag)
    assert isinstance(first_cfg, dict), f"missing first reentry setter {first_flag}"
    assert isinstance(second_cfg, dict), f"missing second reentry setter {second_flag}"
    assert first_cfg.get("once") is True
    assert second_cfg.get("once") is True
    first_forbid = first_cfg.get("forbid_flags") if isinstance(first_cfg.get("forbid_flags"), list) else []
    second_require = second_cfg.get("require_flags") if isinstance(second_cfg.get("require_flags"), list) else []
    second_forbid = second_cfg.get("forbid_flags") if isinstance(second_cfg.get("forbid_flags"), list) else []
    assert done_flag in first_forbid
    assert second_flag in second_forbid
    assert done_flag in second_forbid
    assert first_flag in second_require


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act2_no_hard_lock_transition_chain_references_expected_flags(
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


def test_act2_ch5_boss_readability_invariants() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))

    marker = _find_entity(scene, name="Act2Ch5AoeWarnMarker")
    assert isinstance(marker, dict)

    warn_cfg = _zone_setter(scene, zone_name="Act2Chapter5AoeWarnZone", flag_name="act2_ch5_aoe_warn_seen")
    assert isinstance(warn_cfg, dict)
    warn_toast = warn_cfg.get("toast")
    assert isinstance(warn_toast, str) and "Impact in 2s" in warn_toast

    switch_a = _zone_setter(
        scene, zone_name="Act2Chapter5SuppressionSwitchZoneA", flag_name="act2_ch5_hazard_suppressed"
    )
    switch_b = _zone_setter(
        scene, zone_name="Act2Chapter5SuppressionSwitchZoneB", flag_name="act2_ch5_hazard_suppressed"
    )
    assert isinstance(switch_a, dict)
    assert isinstance(switch_b, dict)
    assert switch_a.get("toast") == "Suppression active."
    assert switch_b.get("toast") == "Suppression active."

    entities = scene.get("entities")
    assert isinstance(entities, list)
    has_shard_a_gated = False
    has_shard_b_gated = False
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        if "act2_ch3_reward_shard_a" in require:
            has_shard_a_gated = True
        if "act2_ch3_reward_shard_b" in require:
            has_shard_b_gated = True
    assert has_shard_a_gated
    assert has_shard_b_gated


def test_act2_ch5_defeat_and_epilogue_resolution_flags_present() -> None:
    overseer = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Overseer.json").read_text(encoding="utf-8"))
    defeat_cfg = _zone_setter(overseer, zone_name="Act2Chapter5BossDefeatZone", flag_name="act2_ch5_boss_defeated")
    assert isinstance(defeat_cfg, dict)

    epilogue = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Epilogue.json").read_text(encoding="utf-8"))
    complete_cfg = _zone_setter(epilogue, zone_name="Act2Chapter5CompleteZone", flag_name="act2_chapter5_complete")
    assert isinstance(complete_cfg, dict)
    set_flags = complete_cfg.get("set_flags")
    assert isinstance(set_flags, dict)
    assert set_flags.get("act2_act_complete") is True
