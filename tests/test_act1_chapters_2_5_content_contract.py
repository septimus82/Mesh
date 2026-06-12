from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

QUEST_OBJECTIVE_EXPECTATIONS = {
    "quest_act1_ch2_camp_briefing": "Talk to the camp leader.",
    "quest_act1_ch2_ambush_clear": "Survive the ambush. Clear the attackers.",
    "quest_act1_ch3_archive_briefing": "Search the archive for the marked note.",
    "quest_act1_ch3_courtyard_clear": "Secure the courtyard.",
    "quest_act1_ch4_bastion_briefing": "Check in at the bastion.",
    "quest_act1_ch4_bastion_clear": "Clear the bastion approach.",
    "quest_act1_ch5_gauntlet_clear": "Push through the gauntlet.",
    "quest_act1_ch5_summit_complete": "Reach the summit seal.",
}

TRANSITION_FLAG_INVARIANTS = [
    (
        "packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json",
        "ToChapter3",
        "packs/core_regions/scenes/Act1_Chapter3_Stub.json",
        "act1_ch2_ambush_cleared",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter3_Stub.json",
        "ToChapter4",
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
]

REENTRY_HINT_EXPECTATIONS = [
    (
        "packs/core_regions/scenes/Act1_Chapter2_Camp.json",
        "Ch2CampReentryProbeZone",
        "act1_ch2_camp_briefed",
        "act1_ch2_camp_reentry_1",
        "act1_ch2_camp_reentry_2",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter3_Archive.json",
        "Ch3ArchiveReentryProbeZone",
        "act1_ch3_archive_briefed",
        "act1_ch3_archive_reentry_1",
        "act1_ch3_archive_reentry_2",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter4_Bastion.json",
        "Ch4BastionReentryProbeZone",
        "act1_ch4_bastion_briefed",
        "act1_ch4_bastion_reentry_1",
        "act1_ch4_bastion_reentry_2",
    ),
    (
        "packs/core_regions/scenes/Act1_Chapter5_Gauntlet.json",
        "Ch5GauntletReentryProbeZone",
        "act1_ch5_ready_for_summit",
        "act1_ch5_gauntlet_reentry_1",
        "act1_ch5_gauntlet_reentry_2",
    ),
]


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
        switch_cfg = cfg.get("SwitchInteract")
        if isinstance(switch_cfg, dict):
            event_id = switch_cfg.get("event_id")
            if isinstance(event_id, str) and event_id:
                event_ids.add(event_id)
        dialogue_cfg = cfg.get("Dialogue")
        if isinstance(dialogue_cfg, dict):
            nodes = dialogue_cfg.get("dialogue_nodes")
            if isinstance(nodes, dict):
                for node in nodes.values():
                    if not isinstance(node, dict):
                        continue
                    choices = node.get("choices")
                    if not isinstance(choices, list):
                        continue
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        event = choice.get("event")
                        if not isinstance(event, dict):
                            continue
                        event_type = event.get("type")
                        if isinstance(event_type, str) and event_type:
                            event_ids.add(event_type)
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


@pytest.mark.parametrize(
    ("scene_path", "required_names", "required_events"),
    [
        (
            "packs/core_regions/scenes/Act1_Chapter2_Camp.json",
            {"Chapter2CampBriefingZone", "ToChapter2Ambush", "Ch2Quartermaster"},
            {"act1_ch2_camp_briefing", "act1_ch2_briefing_accept"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter2_Ambush.json",
            {"Ch2AmbushStartZone", "Ch2AmbushClearZone", "ToRuinedGateFromAmbush"},
            {"act1_ch2_ambush_start", "act1_ch2_ambush_unlock", "act1_ch2_ambush_clear"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter3_Archive.json",
            {"Chapter3ArchiveNoteZone", "ToChapter3Courtyard", "Ch3Archivist"},
            {"act1_ch3_archive_note", "act1_ch3_archive_accept", "act1_ch3_archive_unlock_event"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter3_Courtyard.json",
            {"Ch3CourtyardClearZone", "ToChapter4FromCourtyard"},
            {"act1_ch3_courtyard_clear"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter4_Bastion.json",
            {"Ch4BastionStartZone", "Ch4BastionClearZone", "Ch4ScoutRiven"},
            {"act1_ch4_bastion_start", "act1_ch4_bastion_brief", "act1_ch4_bastion_unlock", "act1_ch4_bastion_clear"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter5_Gauntlet.json",
            {"Ch5GauntletStartZone", "Ch5GauntletClearZone", "ToChapter5Summit"},
            {"act1_ch5_gauntlet_start", "act1_ch5_gauntlet_unlock", "act1_ch5_gauntlet_clear"},
        ),
        (
            "packs/core_regions/scenes/Act1_Chapter5_Summit.json",
            {"Chapter5SummitSealZone", "Ch5WardenSpirit"},
            {"act1_ch5_summit_seal", "act1_ch5_finale_accept", "act1_ch5_summit_complete"},
        ),
    ],
)
def test_act1_chapters_2_5_new_scenes_validate_and_expose_required_quest_hooks(
    scene_path: str, required_names: set[str], required_events: set[str]
) -> None:
    path = Path(scene_path)
    assert path.exists(), scene_path

    scene = json.loads(path.read_text(encoding="utf-8"))
    _assert_scene_references_resolve(scene_path, scene)
    entities = scene.get("entities")
    assert isinstance(entities, list)

    names = {
        value
        for entity in entities
        if isinstance(entity, dict)
        for value in (entity.get("name"), entity.get("mesh_name"))
        if isinstance(value, str) and value
    }
    missing_names = sorted(required_names - names)
    assert not missing_names, f"{scene_path} missing required names/ids: {missing_names}"

    event_ids = _collect_scene_event_ids(scene)
    missing_events = sorted(required_events - event_ids)
    assert not missing_events, f"{scene_path} missing required trigger/event ids: {missing_events}"


def test_act1_chapters_2_5_quest_objective_lines_present() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)

    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id, expected_line in QUEST_OBJECTIVE_EXPECTATIONS.items():
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        stage_lines: list[str] = []
        stages = quest.get("stages")
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                text = stage.get("text")
                if isinstance(text, str) and text.strip():
                    stage_lines.append(text.strip())
        assert (
            (isinstance(description, str) and description.strip())
            or stage_lines
        ), f"{quest_id} must have a non-empty objective/description line"
        description_value = description.strip() if isinstance(description, str) else ""
        assert (
            description_value == expected_line or expected_line in stage_lines
        ), f"{quest_id} must expose expected objective line"


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    TRANSITION_FLAG_INVARIANTS,
)
def test_act1_chapters_2_5_progression_transitions_have_expected_targets_and_gates(
    scene_path: str, transition_name: str, expected_target: str, required_flag: str
) -> None:
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    entity = _find_entity(scene, name=transition_name)
    assert isinstance(entity, dict), f"{scene_path} missing transition entity {transition_name}"

    cfg = entity.get("behaviour_config")
    assert isinstance(cfg, dict), f"{scene_path} transition {transition_name} missing behaviour_config"
    transition = cfg.get("SceneTransition")
    assert isinstance(transition, dict), f"{scene_path} transition {transition_name} missing SceneTransition config"
    assert transition.get("target_scene") == expected_target

    entity_require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
    transition_require = transition.get("require_flags") if isinstance(transition.get("require_flags"), list) else []
    transition_condition = transition.get("condition")

    has_no_gate = not entity_require and not transition_require and transition_condition in (None, "")
    references_required_flag = (
        required_flag in entity_require
        or required_flag in transition_require
        or (isinstance(transition_condition, str) and required_flag in transition_condition)
    )
    assert has_no_gate or references_required_flag, (
        f"{scene_path} transition {transition_name} should be unconditional or reference {required_flag}"
    )


def test_act1_chapters_2_5_checkpoint_triggers_and_flags_present() -> None:
    seen_checkpoint_flags: set[str] = set()
    for scene_path, zone_name, checkpoint_flag, checkpoint_toast in CHECKPOINT_EXPECTATIONS:
        scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
        zone_entity = _find_entity(scene, name=zone_name)
        assert isinstance(zone_entity, dict), f"{scene_path} missing {zone_name}"
        zone_cfg = zone_entity.get("behaviour_config")
        assert isinstance(zone_cfg, dict)
        trigger_cfg = zone_cfg.get("TriggerZone")
        assert isinstance(trigger_cfg, dict), f"{scene_path} {zone_name} missing TriggerZone config"

        zone_setters = _set_game_state_configs_for_zone(scene, zone_name=zone_name)
        assert zone_setters, f"{scene_path} missing SetGameStateOnEvent for {zone_name}"

        found_checkpoint_setter = False
        for setter in zone_setters:
            set_flags = setter.get("set_flags")
            if not (isinstance(set_flags, dict) and set_flags.get(checkpoint_flag) is True):
                continue
            found_checkpoint_setter = True
            seen_checkpoint_flags.add(checkpoint_flag)
            assert setter.get("once") is True
            assert setter.get("toast") == checkpoint_toast
            assert setter.get("toast_seconds") == 2.0
            forbid_flags = setter.get("forbid_flags")
            assert isinstance(forbid_flags, list)
            assert checkpoint_flag in forbid_flags
        assert found_checkpoint_setter, f"{scene_path} must set checkpoint flag {checkpoint_flag}"

    expected_checkpoint_flags = {
        "act1_ch2_checkpoint",
        "act1_ch3_checkpoint",
        "act1_ch4_checkpoint",
        "act1_ch5_checkpoint",
    }
    assert seen_checkpoint_flags == expected_checkpoint_flags


def test_act1_chapters_2_5_reentry_hint_escalation_presence_contract() -> None:
    for scene_path, zone_name, progress_flag, reentry_flag_1, reentry_flag_2 in REENTRY_HINT_EXPECTATIONS:
        scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
        zone_entity = _find_entity(scene, name=zone_name)
        assert isinstance(zone_entity, dict), f"{scene_path} missing {zone_name}"
        zone_cfg = zone_entity.get("behaviour_config")
        assert isinstance(zone_cfg, dict)
        trigger_cfg = zone_cfg.get("TriggerZone")
        assert isinstance(trigger_cfg, dict), f"{scene_path} {zone_name} missing TriggerZone config"

        zone_setters = _set_game_state_configs_for_zone(scene, zone_name=zone_name)
        assert zone_setters, f"{scene_path} missing reentry setters for {zone_name}"

        visit_setter = None
        hint_setter = None
        for setter in zone_setters:
            set_flags = setter.get("set_flags")
            if isinstance(set_flags, dict) and set_flags.get(reentry_flag_1) is True:
                visit_setter = setter
            if isinstance(set_flags, dict) and set_flags.get(reentry_flag_2) is True:
                hint_setter = setter

        assert isinstance(visit_setter, dict), f"{scene_path} missing reentry first-pass flag setter"
        assert isinstance(hint_setter, dict), f"{scene_path} missing reentry second-pass hint setter"

        visit_forbid = visit_setter.get("forbid_flags")
        assert isinstance(visit_forbid, list)
        assert progress_flag in visit_forbid
        assert reentry_flag_1 in visit_forbid

        hint_require = hint_setter.get("require_flags")
        hint_forbid = hint_setter.get("forbid_flags")
        assert isinstance(hint_require, list)
        assert isinstance(hint_forbid, list)
        assert reentry_flag_1 in hint_require
        assert progress_flag in hint_forbid
        assert reentry_flag_2 in hint_forbid
        assert isinstance(hint_setter.get("toast"), str) and hint_setter.get("toast")
