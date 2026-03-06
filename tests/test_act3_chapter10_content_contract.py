from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT3_CH10_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter10_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter10_Finalize.json",
    "packs/core_regions/scenes/Act3_Chapter10_Exit.json",
    "packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json",
]

ACT3_CH10_QUEST_IDS = {
    "quest_act3_ch10_entry",
    "quest_act3_ch10_finalize",
    "quest_act3_ch10_complete",
    "quest_act4_ch1_entry_stub",
}

FORWARD_CHAIN = [
    (
        "packs/core_regions/scenes/Act3_Chapter9_Exit.json",
        "ToAct3Chapter10Entry",
        "packs/core_regions/scenes/Act3_Chapter10_Entry.json",
        "act3_chapter9_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter10_Entry.json",
        "ToAct3Chapter10Finalize",
        "packs/core_regions/scenes/Act3_Chapter10_Finalize.json",
        "act3_ch10_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter10_Finalize.json",
        "ToAct3Chapter10Exit",
        "packs/core_regions/scenes/Act3_Chapter10_Exit.json",
        "act3_act_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter10_Exit.json",
        "ToAct4Chapter1EntryStub",
        "packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json",
        "act3_act_complete",
    ),
]


@lru_cache(maxsize=None)
def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def test_act3_ch10_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH10_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        _assert_scene_references_resolve(scene_path, _load_json(scene_path))


def test_act3_ch10_world_registry_contains_new_scenes_and_stub() -> None:
    world = _load_json("worlds/act3_chapter1_stub.json")
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in [
        "act3_chapter10_entry",
        "act3_chapter10_finalize",
        "act3_chapter10_exit",
        "act4_chapter1_entry_stub",
    ]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch10_quests_exist_and_have_objective_lines() -> None:
    quests_doc = _load_json("assets/data/quests.json")
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH10_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch10_finalize_beats_and_commit_toast_exist_with_exact_strings() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter10_Finalize.json")
    toasts = {
        cfg.get("toast")
        for cfg in _set_configs(scene)
        if isinstance(cfg.get("toast"), str)
    }
    assert "The uplink hums with a familiar pattern." in toasts
    assert "A final handshake waits for your consent." in toasts
    assert "Act 3 complete." in toasts


def test_act3_ch10_finalize_and_backup_zones_set_act_complete_with_exact_toast_and_once() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter10_Finalize.json")
    main_cfg = _zone_setter(scene, zone_name="Act3Chapter10FinalizeZone", flag_name="act3_act_complete")
    backup_cfg = _zone_setter(scene, zone_name="Act3Chapter10BackupFinalizeZone", flag_name="act3_act_complete")
    assert isinstance(main_cfg, dict)
    assert isinstance(backup_cfg, dict)
    assert main_cfg.get("once") is True
    assert backup_cfg.get("once") is True
    assert main_cfg.get("toast") == "Act 3 complete."
    assert backup_cfg.get("toast") == "Act 3 complete."
    assert main_cfg.get("toast_seconds") == 2.0
    assert backup_cfg.get("toast_seconds") == 2.0


def test_act3_ch10_exit_transitions_require_act_complete() -> None:
    finalize_scene = _load_json("packs/core_regions/scenes/Act3_Chapter10_Finalize.json")
    finalize_transition = _find_entity(finalize_scene, name="ToAct3Chapter10Exit")
    assert isinstance(finalize_transition, dict)
    finalize_require_flags = finalize_transition.get("require_flags")
    assert isinstance(finalize_require_flags, list)
    assert finalize_require_flags == ["act3_act_complete"]

    exit_scene = _load_json("packs/core_regions/scenes/Act3_Chapter10_Exit.json")
    stub_transition = _find_entity(exit_scene, name="ToAct4Chapter1EntryStub")
    assert isinstance(stub_transition, dict)
    stub_require_flags = stub_transition.get("require_flags")
    assert isinstance(stub_require_flags, list)
    assert stub_require_flags == ["act3_act_complete"]


def test_act3_ch10_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter10_Exit.json")
    cfg = _zone_setter(scene, zone_name="Act3Chapter10CheckpointZone", flag_name="act3_ch10_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 10"
    assert cfg.get("toast_seconds") == 2.0


def test_act4_stub_sets_started_with_exact_toast() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json")
    cfg = _zone_setter(scene, zone_name="Act4Chapter1EntryBriefingZone", flag_name="act4_ch1_started")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Act 4 begins."
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch10_forward_path_is_structurally_valid() -> None:
    entry = _load_json("packs/core_regions/scenes/Act3_Chapter10_Entry.json")
    finalize = _load_json("packs/core_regions/scenes/Act3_Chapter10_Finalize.json")
    started_cfg = _zone_setter(entry, zone_name="Act3Chapter10EntryBriefingZone", flag_name="act3_ch10_started")
    commit_cfg = _zone_setter(finalize, zone_name="Act3Chapter10FinalizeZone", flag_name="act3_act_complete")
    assert isinstance(started_cfg, dict)
    assert isinstance(commit_cfg, dict)

    allowed_flags = {"act3_chapter9_complete", "act3_ch10_started", "act3_act_complete"}
    for scene_path, transition_name, expected_target, required_flag in FORWARD_CHAIN:
        scene = _load_json(scene_path)
        entity = _find_entity(scene, name=transition_name)
        assert isinstance(entity, dict), f"{scene_path} missing {transition_name}"
        cfg = entity.get("behaviour_config")
        assert isinstance(cfg, dict)
        transition = cfg.get("SceneTransition")
        assert isinstance(transition, dict)
        assert transition.get("target_scene") == expected_target
        require_flags = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        assert required_flag in require_flags
        assert set(require_flags).issubset(allowed_flags)
