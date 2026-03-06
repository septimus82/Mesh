from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT3_CH6_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter6_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json",
    "packs/core_regions/scenes/Act3_Chapter6_Exit.json",
]

ACT3_CH6_QUEST_IDS = {
    "quest_act3_ch6_entry",
    "quest_act3_ch6_shortcut",
    "quest_act3_ch6_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act3_Chapter5_Exit.json",
        "ToAct3Chapter6Entry",
        "packs/core_regions/scenes/Act3_Chapter6_Entry.json",
        "act3_chapter5_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter6_Entry.json",
        "ToAct3Chapter6Shortcuts",
        "packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json",
        "act3_ch6_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json",
        "ToAct3Chapter6Exit",
        "packs/core_regions/scenes/Act3_Chapter6_Exit.json",
        "act3_ch6_started",
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


@lru_cache(maxsize=None)
def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def _zone_setters(scene: dict, *, zone_name: str, flag_name: str) -> list[dict]:
    out: list[dict] = []
    for cfg in _set_configs(scene):
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_field") != "zone":
            continue
        if cfg.get("payload_value") != zone_name:
            continue
        set_flags = cfg.get("set_flags")
        if isinstance(set_flags, dict) and set_flags.get(flag_name) is True:
            out.append(cfg)
    return out


def _flag_rule_allows(flags: set[str], *, require_flags: list[str], forbid_flags: list[str]) -> bool:
    return all(flag in flags for flag in require_flags) and all(flag not in flags for flag in forbid_flags)


def _apply_zone_setters(scene: dict, *, zone_name: str, flags: set[str]) -> None:
    for cfg in _set_configs(scene):
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_field") != "zone":
            continue
        if cfg.get("payload_value") != zone_name:
            continue
        require_flags = cfg.get("require_flags") if isinstance(cfg.get("require_flags"), list) else []
        forbid_flags = cfg.get("forbid_flags") if isinstance(cfg.get("forbid_flags"), list) else []
        if not _flag_rule_allows(flags, require_flags=require_flags, forbid_flags=forbid_flags):
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        for key, value in set_flags.items():
            if value is True:
                flags.add(key)
            elif value is False and key in flags:
                flags.remove(key)


def _transition_enabled(scene: dict, *, transition_name: str, flags: set[str]) -> bool:
    entity = _find_entity(scene, name=transition_name)
    if not isinstance(entity, dict):
        return False
    entity_require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
    entity_forbid = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
    if not _flag_rule_allows(flags, require_flags=entity_require, forbid_flags=entity_forbid):
        return False
    cfg = entity.get("behaviour_config")
    if not isinstance(cfg, dict):
        return False
    transition = cfg.get("SceneTransition")
    if not isinstance(transition, dict):
        return False
    transition_require = transition.get("require_flags") if isinstance(transition.get("require_flags"), list) else []
    transition_forbid = transition.get("forbid_flags") if isinstance(transition.get("forbid_flags"), list) else []
    return _flag_rule_allows(flags, require_flags=transition_require, forbid_flags=transition_forbid)


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


def test_act3_ch6_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH6_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = _load_json(scene_path)
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch6_world_registry_contains_new_scenes() -> None:
    world = _load_json("worlds/act3_chapter1_stub.json")
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter6_entry", "act3_chapter6_shortcuts", "act3_chapter6_exit"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch6_quests_exist_and_have_objective_lines() -> None:
    quests_doc = _load_json("assets/data/quests.json")
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH6_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch6_shortcut_a_presence_with_affinity_gating_toast_and_shortcut_flag_setter() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json")
    shortcut_zone = _find_entity(scene, name="Act3Chapter6ShortcutAZone")
    assert isinstance(shortcut_zone, dict)
    require_flags = shortcut_zone.get("require_flags")
    assert isinstance(require_flags, list)
    assert "act3_ch3_affinity_a" in require_flags

    setter_cfgs = _zone_setters(scene, zone_name="Act3Chapter6ShortcutAZone", flag_name="act3_ch6_shortcut_used")
    assert len(setter_cfgs) == 1
    cfg = setter_cfgs[0]
    assert cfg.get("toast") == "Shortcut opened: A."
    assert cfg.get("toast_seconds") == 2.0
    cfg_require = cfg.get("require_flags")
    assert isinstance(cfg_require, list)
    assert "act3_ch3_affinity_a" in cfg_require


def test_act3_ch6_shortcut_b_presence_with_affinity_gating_toast_and_shortcut_flag_setter() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json")
    shortcut_zone = _find_entity(scene, name="Act3Chapter6ShortcutBZone")
    assert isinstance(shortcut_zone, dict)
    require_flags = shortcut_zone.get("require_flags")
    assert isinstance(require_flags, list)
    assert "act3_ch3_affinity_b" in require_flags

    setter_cfgs = _zone_setters(scene, zone_name="Act3Chapter6ShortcutBZone", flag_name="act3_ch6_shortcut_used")
    assert len(setter_cfgs) == 1
    cfg = setter_cfgs[0]
    assert cfg.get("toast") == "Shortcut opened: B."
    assert cfg.get("toast_seconds") == 2.0
    cfg_require = cfg.get("require_flags")
    assert isinstance(cfg_require, list)
    assert "act3_ch3_affinity_b" in cfg_require


def test_act3_ch6_neutral_hint_exists_with_exact_toast_and_once_hint_flag() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json")
    cfgs = _zone_setters(scene, zone_name="Act3Chapter6NeutralHintZone", flag_name="act3_ch6_hint_seen")
    assert len(cfgs) == 1
    cfg = cfgs[0]
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Notice: your doctrine cannot open these shortcuts. Proceed via the main route."
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch6_affinity_outcome_entities_exist_for_a_and_b() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json")
    pickup_a = _find_entity(scene, name="Act3Ch6AffinityAPickup")
    pickup_b = _find_entity(scene, name="Act3Ch6AffinityBPickup")
    assert isinstance(pickup_a, dict)
    assert isinstance(pickup_b, dict)
    require_a = pickup_a.get("require_flags")
    require_b = pickup_b.get("require_flags")
    assert isinstance(require_a, list)
    assert isinstance(require_b, list)
    assert "act3_ch3_affinity_a" in require_a
    assert "act3_ch3_affinity_b" in require_b


def test_act3_ch6_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Exit.json")
    cfgs = _zone_setters(scene, zone_name="Act3Chapter6CheckpointZone", flag_name="act3_ch6_checkpoint")
    assert len(cfgs) == 1
    cfg = cfgs[0]
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 6"
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch6_no_hard_lock_path_exists_for_affinity_a_b_neutral_and_missing_state() -> None:
    ch5_exit_scene = _load_json("packs/core_regions/scenes/Act3_Chapter5_Exit.json")
    entry_scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Entry.json")
    shortcuts_scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Shortcuts.json")
    exit_scene = _load_json("packs/core_regions/scenes/Act3_Chapter6_Exit.json")

    def evaluate(initial_affinity_flags: set[str], route: str) -> bool:
        flags = {"act3_chapter5_complete"} | set(initial_affinity_flags)
        assert _transition_enabled(ch5_exit_scene, transition_name="ToAct3Chapter6Entry", flags=flags)

        _apply_zone_setters(entry_scene, zone_name="Act3Chapter6EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry_scene, transition_name="ToAct3Chapter6Shortcuts", flags=flags)

        if route == "a":
            _apply_zone_setters(shortcuts_scene, zone_name="Act3Chapter6ShortcutAZone", flags=flags)
        elif route == "b":
            _apply_zone_setters(shortcuts_scene, zone_name="Act3Chapter6ShortcutBZone", flags=flags)
        else:
            _apply_zone_setters(shortcuts_scene, zone_name="Act3Chapter6NeutralHintZone", flags=flags)
            _apply_zone_setters(shortcuts_scene, zone_name="Act3Chapter6MainRouteProgressZone", flags=flags)

        assert _transition_enabled(shortcuts_scene, transition_name="ToAct3Chapter6Exit", flags=flags)
        _apply_zone_setters(exit_scene, zone_name="Act3Chapter6CompleteZone", flags=flags)
        return "act3_chapter6_complete" in flags

    assert evaluate({"act3_ch3_affinity_a"}, route="a")
    assert evaluate({"act3_ch3_affinity_b"}, route="b")
    assert evaluate({"act3_ch3_affinity_neutral"}, route="main")
    assert evaluate(set(), route="main")


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch6_no_hard_lock_transitions_have_expected_targets_and_flags(
    scene_path: str, transition_name: str, expected_target: str, required_flag: str
) -> None:
    scene = _load_json(scene_path)
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
