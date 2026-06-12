from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT4_CH1_SCENES = [
    "packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json",
    "packs/core_regions/scenes/Act4_Chapter1_Entry.json",
    "packs/core_regions/scenes/Act4_Chapter1_Teach.json",
    "packs/core_regions/scenes/Act4_Chapter1_Exit.json",
]

ACT4_CH1_QUEST_IDS = {
    "quest_act4_ch1_entry",
    "quest_act4_ch1_taught",
    "quest_act4_ch1_complete",
}

FORWARD_CHAIN = [
    (
        "packs/core_regions/scenes/Act3_Chapter10_Exit.json",
        "ToAct4Chapter1EntryStub",
        "packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json",
        "act3_act_complete",
    ),
    (
        "packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json",
        "ToAct4Chapter1Entry",
        "packs/core_regions/scenes/Act4_Chapter1_Entry.json",
        "act4_ch1_started",
    ),
    (
        "packs/core_regions/scenes/Act4_Chapter1_Entry.json",
        "ToAct4Chapter1Teach",
        "packs/core_regions/scenes/Act4_Chapter1_Teach.json",
        "act4_ch1_started",
    ),
    (
        "packs/core_regions/scenes/Act4_Chapter1_Teach.json",
        "ToAct4Chapter1Exit",
        "packs/core_regions/scenes/Act4_Chapter1_Exit.json",
        "act4_ch1_authorized",
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


def test_act4_ch1_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT4_CH1_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        _assert_scene_references_resolve(scene_path, _load_json(scene_path))

    # Bridge source must remain valid.
    bridge_source = "packs/core_regions/scenes/Act3_Chapter10_Exit.json"
    assert Path(bridge_source).exists()
    _assert_scene_references_resolve(bridge_source, _load_json(bridge_source))


def test_act4_ch1_world_registry_contains_scene_entries_and_stub_bridge() -> None:
    world = _load_json("worlds/act3_chapter1_stub.json")
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in [
        "act4_chapter1_entry_stub",
        "act4_chapter1_entry",
        "act4_chapter1_teach",
        "act4_chapter1_exit",
    ]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act4_ch1_quests_exist_and_have_objective_lines() -> None:
    quests_doc = _load_json("assets/data/quests.json")
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT4_CH1_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act4_ch1_induction_terminal_sets_authorized_and_taught_with_exact_toast() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Teach.json")
    cfg = _zone_setter(scene, zone_name="Act4Chapter1InductionTerminalZone", flag_name="act4_ch1_authorized")
    assert isinstance(cfg, dict)
    set_flags = cfg.get("set_flags")
    assert isinstance(set_flags, dict)
    assert set_flags.get("act4_ch1_authorized") is True
    assert set_flags.get("act4_ch1_taught") is True
    assert cfg.get("toast") == "Authorization granted."
    assert cfg.get("once") is True


def test_act4_ch1_backup_authorization_exists_with_same_toast() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Teach.json")
    cfg = _zone_setter(scene, zone_name="Act4Chapter1BackupAuthorizationZone", flag_name="act4_ch1_authorized")
    assert isinstance(cfg, dict)
    assert cfg.get("toast") == "Authorization granted."
    assert cfg.get("once") is True


def test_act4_ch1_exit_transition_requires_authorized() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Teach.json")
    transition = _find_entity(scene, name="ToAct4Chapter1Exit")
    assert isinstance(transition, dict)
    require_flags = transition.get("require_flags")
    assert isinstance(require_flags, list)
    assert require_flags == ["act4_ch1_authorized"]


def test_act4_ch1_checkpoint_exists_with_exact_toast_once_and_seconds() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Exit.json")
    cfg = _zone_setter(scene, zone_name="Act4Chapter1CheckpointZone", flag_name="act4_ch1_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 4 Chapter 1"
    assert cfg.get("toast_seconds") == 2.0


def test_act4_ch1_safe_mode_warning_exists_with_exact_toast_and_flag() -> None:
    scene = _load_json("packs/core_regions/scenes/Act4_Chapter1_Entry.json")
    cfg = _zone_setter(scene, zone_name="Act4Chapter1SafeModeWarningZone", flag_name="act4_safe_mode")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Warning: prior completion state missing. Proceeding in safe mode."
    assert cfg.get("toast_seconds") == 2.0


def test_act4_ch1_forward_path_is_structurally_valid_and_not_hard_locked() -> None:
    stub = _load_json("packs/core_regions/scenes/Act4_Chapter1_Entry_Stub.json")
    teach = _load_json("packs/core_regions/scenes/Act4_Chapter1_Teach.json")
    started_cfg = _zone_setter(stub, zone_name="Act4Chapter1EntryBriefingZone", flag_name="act4_ch1_started")
    auth_cfg = _zone_setter(teach, zone_name="Act4Chapter1InductionTerminalZone", flag_name="act4_ch1_authorized")
    assert isinstance(started_cfg, dict)
    assert isinstance(auth_cfg, dict)

    allowed_flags = {"act3_act_complete", "act4_ch1_started", "act4_ch1_authorized"}
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
