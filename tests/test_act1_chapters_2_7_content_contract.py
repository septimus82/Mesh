from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


NEW_SCENES = [
    "packs/core_regions/scenes/Act1_Chapter6_Approach.json",
    "packs/core_regions/scenes/Act1_Chapter6_Warden.json",
    "packs/core_regions/scenes/Act1_Chapter7_Aftermath.json",
]

ACT1_OBJECTIVE_QUEST_IDS = {
    "quest_act1_ch2_camp_briefing",
    "quest_act1_ch2_ambush_clear",
    "quest_act1_ch3_archive_briefing",
    "quest_act1_ch3_courtyard_clear",
    "quest_act1_ch4_bastion_briefing",
    "quest_act1_ch4_bastion_clear",
    "quest_act1_ch5_gauntlet_clear",
    "quest_act1_ch5_summit_complete",
    "quest_act1_ch6_approach_briefing",
    "quest_act1_ch6_warden_defeated",
    "quest_act1_ch7_after_resolve",
}

CHECKLIST_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act1_Chapter2_Ambush.json",
        "ToRuinedGateFromAmbush",
        "packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json",
        "act1_ch2_ambush_cleared",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json",
        "ToChapter3",
        "packs/core_regions/scenes/Act1_Chapter3_Stub.json",
        "act1_ch2_ambush_cleared",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter3_Courtyard.json",
        "ToChapter4FromCourtyard",
        "packs/core_regions/scenes/Act1_Chapter4_Stub.json",
        "act1_ch3_courtyard_cleared",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter4_Fork.json",
        "ToChapter5",
        "packs/core_regions/scenes/Act1_Chapter5_Stub.json",
        "act1_ch4_bastion_cleared",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter5_Gauntlet.json",
        "ToChapter5Summit",
        "packs/core_regions/scenes/Act1_Chapter5_Summit.json",
        "act1_ch5_ready_for_summit",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter5_Summit.json",
        "ToChapter6Approach",
        "packs/core_regions/scenes/Act1_Chapter6_Approach.json",
        "act1_chapter5_complete",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter6_Approach.json",
        "ToChapter6Warden",
        "packs/core_regions/scenes/Act1_Chapter6_Warden.json",
        "act1_ch6_briefed",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter6_Warden.json",
        "ToChapter7Aftermath",
        "packs/core_regions/scenes/Act1_Chapter7_Aftermath.json",
        "act1_ch6_warden_defeated",
    ),
]

CHECKPOINT_EXPECTATIONS = [
    (
        "packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json",
        "Ch2CheckpointZone",
        "act1_ch2_checkpoint",
        "Checkpoint reached: Chapter 2",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter3_Courtyard.json",
        "Ch3CheckpointZone",
        "act1_ch3_checkpoint",
        "Checkpoint reached: Chapter 3",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter4_Fork.json",
        "Ch4CheckpointZone",
        "act1_ch4_checkpoint",
        "Checkpoint reached: Chapter 4",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter5_Summit.json",
        "Ch5CheckpointZone",
        "act1_ch5_checkpoint",
        "Checkpoint reached: Chapter 5",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter6_Warden.json",
        "Ch6CheckpointZone",
        "act1_ch6_checkpoint",
        "Checkpoint reached: Chapter 6",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter7_Aftermath.json",
        "Ch7CheckpointZone",
        "act1_ch7_checkpoint",
        "Checkpoint reached: Chapter 7",
    ),
]

REENTRY_ESCALATION_EXPECTATIONS = [
    (
        "packs/core_regions/scenes/Act1_Chapter2_Camp.json",
        "Ch2CampReentryProbeZone",
        "act1_ch2_camp_reentry_1",
        "act1_ch2_camp_reentry_2",
        "act1_ch2_camp_briefed",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter3_Archive.json",
        "Ch3ArchiveReentryProbeZone",
        "act1_ch3_archive_reentry_1",
        "act1_ch3_archive_reentry_2",
        "act1_ch3_archive_briefed",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter4_Bastion.json",
        "Ch4BastionReentryProbeZone",
        "act1_ch4_bastion_reentry_1",
        "act1_ch4_bastion_reentry_2",
        "act1_ch4_bastion_briefed",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter5_Gauntlet.json",
        "Ch5GauntletReentryProbeZone",
        "act1_ch5_gauntlet_reentry_1",
        "act1_ch5_gauntlet_reentry_2",
        "act1_ch5_ready_for_summit",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter6_Approach.json",
        "Ch6ApproachReentryProbeZone",
        "act1_ch6_approach_reentry_1",
        "act1_ch6_approach_reentry_2",
        "act1_ch6_briefed",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter6_Warden.json",
        "Ch6WardenReentryProbeZone",
        "act1_ch6_warden_reentry_1",
        "act1_ch6_warden_reentry_2",
        "act1_ch6_warden_defeated",
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


def test_act1_ch6_ch7_scene_files_parse_and_references_resolve() -> None:
    for scene_path in NEW_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)
        assert isinstance(scene.get("entities"), list)


def test_act1_ch2_ch7_objective_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT1_OBJECTIVE_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act1_ch6_warden_required_trigger_identifiers_present() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter6_Warden.json").read_text(encoding="utf-8"))
    event_ids = _collect_scene_event_ids(scene)
    assert "act1_ch6_warden_aggro" in event_ids
    assert "act1_ch6_warden_aoe_warn" in event_ids
    assert "act1_ch6_warden_defeat" in event_ids


def test_act1_ch6_warden_aoe_warning_has_marker_and_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter6_Warden.json").read_text(encoding="utf-8"))
    marker = _find_entity(scene, name="Ch6WardenAoeWarnMarker")
    assert isinstance(marker, dict), "missing visible AoE warning marker entity"

    setters = _set_game_state_configs_for_zone(scene, zone_name="Ch6WardenAoeWarnZone")
    assert setters, "missing AoE warning setter for Ch6WardenAoeWarnZone"
    found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act1_ch6_aoe_warning_seen") is True:
            found = True
            assert setter.get("toast") == "Warning: Heavy strike radius. Impact in 2s. Reposition now."
            assert setter.get("once") is True
    assert found, "AoE warning setter must set act1_ch6_aoe_warning_seen"


def test_act1_ch6_warden_defeat_setter_has_flags_and_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter6_Warden.json").read_text(encoding="utf-8"))
    setters = _set_game_state_configs_for_zone(scene, zone_name="Ch6WardenDefeatZone")
    assert setters, "missing defeat setter for Ch6WardenDefeatZone"
    found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act1_ch6_warden_defeated") is True and set_flags.get("act1_ch6_key_fragment") is True:
            found = True
            assert setter.get("toast") == "Objective complete: Warden defeated. Fragment secured."
            assert setter.get("once") is True
    assert found, "defeat setter must set both act1_ch6_warden_defeated and act1_ch6_key_fragment"


@pytest.mark.parametrize(
    ("scene_path", "zone_name", "checkpoint_flag", "checkpoint_toast"),
    CHECKPOINT_EXPECTATIONS,
)
def test_act1_ch6_ch7_checkpoints_exist_and_toast_once(
    scene_path: str, zone_name: str, checkpoint_flag: str, checkpoint_toast: str
) -> None:
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    zone_entity = _find_entity(scene, name=zone_name)
    assert isinstance(zone_entity, dict), f"{scene_path} missing {zone_name}"

    setters = _set_game_state_configs_for_zone(scene, zone_name=zone_name)
    assert setters, f"{scene_path} missing checkpoint state sync for {zone_name}"
    found = False
    for setter in setters:
        set_flags = setter.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get(checkpoint_flag) is True:
            found = True
            assert setter.get("once") is True
            assert setter.get("toast") == checkpoint_toast
            assert setter.get("toast_seconds") == 2.0
    assert found, f"{scene_path} missing checkpoint flag setter for {checkpoint_flag}"


def test_act1_ch2_ch7_reentry_hint_escalation_gating_contracts() -> None:
    for scene_path, zone_name, flag_1, flag_2, completion_flag in REENTRY_ESCALATION_EXPECTATIONS:
        scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
        zone_entity = _find_entity(scene, name=zone_name)
        assert isinstance(zone_entity, dict), f"{scene_path} missing {zone_name}"
        setters = _set_game_state_configs_for_zone(scene, zone_name=zone_name)
        assert setters, f"{scene_path} missing setters for {zone_name}"
        first_visit_setter = None
        second_hint_setter = None
        for setter in setters:
            set_flags = setter.get("set_flags")
            if not isinstance(set_flags, dict):
                continue
            if set_flags.get(flag_1) is True:
                first_visit_setter = setter
            if set_flags.get(flag_2) is True:
                second_hint_setter = setter

        assert isinstance(first_visit_setter, dict), f"{scene_path} missing first reentry flag setter {flag_1}"
        assert isinstance(second_hint_setter, dict), f"{scene_path} missing second reentry hint flag setter {flag_2}"

        first_forbid = first_visit_setter.get("forbid_flags")
        first_require = first_visit_setter.get("require_flags")
        assert first_visit_setter.get("once") is True
        assert isinstance(first_forbid, list)
        assert flag_1 in first_forbid
        assert completion_flag in first_forbid
        assert first_require in (None, [])

        second_forbid = second_hint_setter.get("forbid_flags")
        second_require = second_hint_setter.get("require_flags")
        assert second_hint_setter.get("once") is True
        assert isinstance(second_forbid, list)
        assert flag_2 in second_forbid
        assert completion_flag in second_forbid
        assert isinstance(second_require, list)
        assert flag_1 in second_require


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    CHECKLIST_TRANSITIONS,
)
def test_act1_ch2_to_ch7_checklist_transitions_have_expected_targets_and_flag_gates(
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
