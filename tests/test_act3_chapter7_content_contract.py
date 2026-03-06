from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT3_CH7_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter7_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter7_Threshold.json",
    "packs/core_regions/scenes/Act3_Chapter7_Exit.json",
]

ACT3_CH7_QUEST_IDS = {
    "quest_act3_ch7_entry",
    "quest_act3_ch7_cross_threshold",
    "quest_act3_ch7_complete",
}

FORWARD_CHAIN = [
    (
        "packs/core_regions/scenes/Act3_Chapter6_Exit.json",
        "ToAct3Chapter7Entry",
        "packs/core_regions/scenes/Act3_Chapter7_Entry.json",
        "act3_chapter6_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter7_Entry.json",
        "ToAct3Chapter7Threshold",
        "packs/core_regions/scenes/Act3_Chapter7_Threshold.json",
        "act3_ch7_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter7_Threshold.json",
        "ToAct3Chapter7Exit",
        "packs/core_regions/scenes/Act3_Chapter7_Exit.json",
        "act3_ch7_threshold_crossed",
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


def test_act3_ch7_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH7_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        _assert_scene_references_resolve(scene_path, _load_json(scene_path))


def test_act3_ch7_world_registry_contains_new_scenes() -> None:
    world = _load_json("worlds/act3_chapter1_stub.json")
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter7_entry", "act3_chapter7_threshold", "act3_chapter7_exit"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch7_quests_exist_and_have_objective_lines() -> None:
    quests_doc = _load_json("assets/data/quests.json")
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH7_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch7_warning_zone_exists_with_exact_toast_and_warned_flag_once() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter7_Threshold.json")
    cfg = _zone_setter(scene, zone_name="Act3Chapter7ThresholdWarningZone", flag_name="act3_ch7_threshold_warned")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Warning: crossing the threshold is irreversible."
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch7_cross_zone_exists_with_exact_toast_and_crossed_flag_once() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter7_Threshold.json")
    cfg = _zone_setter(scene, zone_name="Act3Chapter7ThresholdCrossZone", flag_name="act3_ch7_threshold_crossed")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Threshold crossed."
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch7_one_way_gating_references_threshold_crossed_on_return_transition() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter7_Threshold.json")
    candidates = [
        _find_entity(scene, name="ReturnToAct3Chapter7Entry"),
        _find_entity(scene, name="ReturnToAct3Chapter6Exit"),
    ]
    matched = False
    for entity in candidates:
        if not isinstance(entity, dict):
            continue
        forbid_flags = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
        if "act3_ch7_threshold_crossed" in forbid_flags:
            matched = True
            break
    assert matched, "expected a return transition to be forbidden once act3_ch7_threshold_crossed is set"


def test_act3_ch7_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter7_Exit.json")
    cfg = _zone_setter(scene, zone_name="Act3Chapter7CheckpointZone", flag_name="act3_ch7_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 7"
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch7_forward_path_is_structurally_valid_and_uses_in_chapter_flags() -> None:
    entry = _load_json("packs/core_regions/scenes/Act3_Chapter7_Entry.json")
    threshold = _load_json("packs/core_regions/scenes/Act3_Chapter7_Threshold.json")

    started_cfg = _zone_setter(entry, zone_name="Act3Chapter7EntryBriefingZone", flag_name="act3_ch7_started")
    crossed_cfg = _zone_setter(
        threshold, zone_name="Act3Chapter7ThresholdCrossZone", flag_name="act3_ch7_threshold_crossed"
    )
    assert isinstance(started_cfg, dict)
    assert isinstance(crossed_cfg, dict)

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
