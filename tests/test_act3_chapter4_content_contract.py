from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT3_CH4_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter4_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter4_Split.json",
    "packs/core_regions/scenes/Act3_Chapter4_Exit.json",
]

ACT3_CH4_QUEST_IDS = {
    "quest_act3_ch4_entry",
    "quest_act3_ch4_tokens",
    "quest_act3_ch4_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act3_Chapter3_Outcome.json",
        "ToAct3Chapter4Entry",
        "packs/core_regions/scenes/Act3_Chapter4_Entry.json",
        "act3_chapter3_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter4_Entry.json",
        "ToAct3Chapter4Split",
        "packs/core_regions/scenes/Act3_Chapter4_Split.json",
        "act3_ch4_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter4_Split.json",
        "ToAct3Chapter4Exit",
        "packs/core_regions/scenes/Act3_Chapter4_Exit.json",
        "act3_ch4_tokens_ready",
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


def test_act3_ch4_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH4_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch4_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act3_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter4_entry", "act3_chapter4_split", "act3_chapter4_exit"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch4_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH4_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch4_token_pickups_exist_with_exact_toasts_and_expected_flags() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Split.json").read_text(encoding="utf-8"))

    token_a_cfgs = _zone_setters(scene, zone_name="Act3Chapter4TokenAZone", flag_name="act3_ch4_token_a")
    token_b_cfgs = _zone_setters(scene, zone_name="Act3Chapter4TokenBZone", flag_name="act3_ch4_token_b")
    assert len(token_a_cfgs) == 1
    assert len(token_b_cfgs) == 1
    assert token_a_cfgs[0].get("toast") == "Signal token acquired: A."
    assert token_b_cfgs[0].get("toast") == "Signal token acquired: B."
    assert token_a_cfgs[0].get("once") is True
    assert token_b_cfgs[0].get("once") is True
    assert token_a_cfgs[0].get("toast_seconds") == 2.0
    assert token_b_cfgs[0].get("toast_seconds") == 2.0


def test_act3_ch4_lock_console_requires_both_tokens_and_sets_tokens_ready_with_unlock_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Split.json").read_text(encoding="utf-8"))
    lock_cfgs = _zone_setters(scene, zone_name="Act3Chapter4LockConsoleZone", flag_name="act3_ch4_tokens_ready")
    assert len(lock_cfgs) == 1
    cfg = lock_cfgs[0]
    require_flags = cfg.get("require_flags")
    assert isinstance(require_flags, list)
    assert "act3_ch4_token_a" in require_flags
    assert "act3_ch4_token_b" in require_flags
    assert cfg.get("toast") == "Lock released. Exit unlocked."
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch4_exit_transition_requires_tokens_ready() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Split.json").read_text(encoding="utf-8"))
    transition = _find_entity(scene, name="ToAct3Chapter4Exit")
    assert isinstance(transition, dict)
    require_flags = transition.get("require_flags")
    assert isinstance(require_flags, list)
    assert require_flags == ["act3_ch4_tokens_ready"]


def test_act3_ch4_recovery_fail_safe_exists_with_warning_toast_and_missing_token_gating() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Split.json").read_text(encoding="utf-8"))

    recovery_open_cfgs = _zone_setters(scene, zone_name="Act3Chapter4LockConsoleZone", flag_name="act3_ch4_recovery_open")
    assert len(recovery_open_cfgs) >= 2
    for cfg in recovery_open_cfgs:
        assert cfg.get("toast") == "Warning: incomplete token set. Recovery route opened."
        assert cfg.get("toast_seconds") == 2.0
        require_flags = cfg.get("require_flags")
        forbid_flags = cfg.get("forbid_flags")
        assert isinstance(require_flags, list)
        assert isinstance(forbid_flags, list)
        assert "act3_ch4_tokens_ready" in forbid_flags

    recovery_a_cfgs = _zone_setters(scene, zone_name="Act3Chapter4RecoveryTokenAZone", flag_name="act3_ch4_token_a")
    recovery_b_cfgs = _zone_setters(scene, zone_name="Act3Chapter4RecoveryTokenBZone", flag_name="act3_ch4_token_b")
    assert len(recovery_a_cfgs) == 1
    assert len(recovery_b_cfgs) == 1

    recovery_a_require = recovery_a_cfgs[0].get("require_flags")
    recovery_b_require = recovery_b_cfgs[0].get("require_flags")
    recovery_a_forbid = recovery_a_cfgs[0].get("forbid_flags")
    recovery_b_forbid = recovery_b_cfgs[0].get("forbid_flags")
    assert isinstance(recovery_a_require, list)
    assert isinstance(recovery_b_require, list)
    assert isinstance(recovery_a_forbid, list)
    assert isinstance(recovery_b_forbid, list)
    assert "act3_ch4_recovery_open" in recovery_a_require
    assert "act3_ch4_recovery_open" in recovery_b_require
    assert "act3_ch4_token_b" in recovery_a_require
    assert "act3_ch4_token_a" in recovery_b_require
    assert "act3_ch4_token_a" in recovery_a_forbid
    assert "act3_ch4_token_b" in recovery_b_forbid


def test_act3_ch4_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Exit.json").read_text(encoding="utf-8"))
    cfgs = _zone_setters(scene, zone_name="Act3Chapter4CheckpointZone", flag_name="act3_ch4_checkpoint")
    assert len(cfgs) == 1
    cfg = cfgs[0]
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 4"
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch4_no_hard_lock_path_exists_for_token_orders_and_recovery_paths() -> None:
    outcome_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Outcome.json").read_text(encoding="utf-8"))
    entry_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Entry.json").read_text(encoding="utf-8"))
    split_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Split.json").read_text(encoding="utf-8"))
    exit_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Exit.json").read_text(encoding="utf-8"))

    def evaluate(initial_route: str) -> bool:
        flags = {"act3_chapter3_complete"}
        assert _transition_enabled(outcome_scene, transition_name="ToAct3Chapter4Entry", flags=flags)

        _apply_zone_setters(entry_scene, zone_name="Act3Chapter4EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry_scene, transition_name="ToAct3Chapter4Split", flags=flags)

        if initial_route == "a_then_b":
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenAZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenBZone", flags=flags)
        elif initial_route == "b_then_a":
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenBZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenAZone", flags=flags)
        elif initial_route == "a_then_recovery":
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenAZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4LockConsoleZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4RecoveryTokenBZone", flags=flags)
        else:
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4TokenBZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4LockConsoleZone", flags=flags)
            _apply_zone_setters(split_scene, zone_name="Act3Chapter4RecoveryTokenAZone", flags=flags)

        _apply_zone_setters(split_scene, zone_name="Act3Chapter4LockConsoleZone", flags=flags)
        assert _transition_enabled(split_scene, transition_name="ToAct3Chapter4Exit", flags=flags)
        _apply_zone_setters(exit_scene, zone_name="Act3Chapter4CompleteZone", flags=flags)
        return "act3_chapter4_complete" in flags

    assert evaluate("a_then_b")
    assert evaluate("b_then_a")
    assert evaluate("a_then_recovery")
    assert evaluate("b_then_recovery")


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch4_no_hard_lock_transitions_have_expected_targets_and_flags(
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
