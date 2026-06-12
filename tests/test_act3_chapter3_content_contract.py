from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT3_CH3_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter3_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter3_Commit.json",
    "packs/core_regions/scenes/Act3_Chapter3_Outcome.json",
]

ACT3_CH3_QUEST_IDS = {
    "quest_act3_ch3_entry",
    "quest_act3_ch3_commit",
    "quest_act3_ch3_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act3_Chapter2_Exit.json",
        "ToAct3Chapter3Entry",
        "packs/core_regions/scenes/Act3_Chapter3_Entry.json",
        "act3_chapter2_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter3_Entry.json",
        "ToAct3Chapter3Commit",
        "packs/core_regions/scenes/Act3_Chapter3_Commit.json",
        "act3_ch3_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter3_Commit.json",
        "ToAct3Chapter3Outcome",
        "packs/core_regions/scenes/Act3_Chapter3_Outcome.json",
        "act3_ch3_committed",
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


def test_act3_ch3_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH3_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch3_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act3_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter3_entry", "act3_chapter3_commit", "act3_chapter3_outcome"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch3_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH3_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch3_commit_zones_exist_with_expected_toasts_and_exclusive_writes() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Commit.json").read_text(encoding="utf-8"))
    commit_a_zone = _find_entity(scene, name="Act3Chapter3CommitAZone")
    commit_b_zone = _find_entity(scene, name="Act3Chapter3CommitBZone")
    assert isinstance(commit_a_zone, dict)
    assert isinstance(commit_b_zone, dict)

    commit_a_cfg = _zone_setter(scene, zone_name="Act3Chapter3CommitAZone", flag_name="act3_ch3_committed")
    commit_b_cfg = _zone_setter(scene, zone_name="Act3Chapter3CommitBZone", flag_name="act3_ch3_committed")
    assert isinstance(commit_a_cfg, dict)
    assert isinstance(commit_b_cfg, dict)
    assert commit_a_cfg.get("toast") == "Committed: Route A."
    assert commit_b_cfg.get("toast") == "Committed: Route B."
    assert commit_a_cfg.get("toast_seconds") == 2.0
    assert commit_b_cfg.get("toast_seconds") == 2.0

    set_flags_a = commit_a_cfg.get("set_flags")
    set_flags_b = commit_b_cfg.get("set_flags")
    assert isinstance(set_flags_a, dict)
    assert isinstance(set_flags_b, dict)
    assert set_flags_a.get("act3_ch3_affinity_a") is True
    assert set_flags_a.get("act3_ch3_affinity_b") is False
    assert set_flags_b.get("act3_ch3_affinity_b") is True
    assert set_flags_b.get("act3_ch3_affinity_a") is False


def test_act3_ch3_neutral_failsafe_exists_with_warning_and_commit_toasts() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Commit.json").read_text(encoding="utf-8"))

    warning_cfg = _zone_setter(scene, zone_name="Act3Chapter3NeutralProbeZone", flag_name="act3_ch3_neutral_warning_seen")
    neutral_cfg = _zone_setter(scene, zone_name="Act3Chapter3NeutralCommitZone", flag_name="act3_ch3_affinity_neutral")
    assert isinstance(warning_cfg, dict)
    assert isinstance(neutral_cfg, dict)

    warning_forbid = warning_cfg.get("forbid_flags")
    assert isinstance(warning_forbid, list)
    assert "act3_ch2_route_a" in warning_forbid
    assert "act3_ch2_route_b" in warning_forbid
    assert warning_cfg.get("toast") == "Warning: route history missing. Neutral commitment available."
    assert warning_cfg.get("toast_seconds") == 2.0

    neutral_set_flags = neutral_cfg.get("set_flags")
    assert isinstance(neutral_set_flags, dict)
    assert neutral_set_flags.get("act3_ch3_affinity_neutral") is True
    assert neutral_set_flags.get("act3_ch3_committed") is True
    assert neutral_cfg.get("toast") == "Committed: Neutral."
    assert neutral_cfg.get("toast_seconds") == 2.0


def test_act3_ch3_outcome_has_affinity_a_and_b_reactive_gating_and_neutral_traversal() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Outcome.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)
    has_affinity_a = False
    has_affinity_b = False
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        require_flags = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        if "act3_ch3_affinity_a" in require_flags:
            has_affinity_a = True
        if "act3_ch3_affinity_b" in require_flags:
            has_affinity_b = True
    assert has_affinity_a
    assert has_affinity_b

    completion_cfg = _zone_setter(scene, zone_name="Act3Chapter3CompleteZone", flag_name="act3_chapter3_complete")
    assert isinstance(completion_cfg, dict)
    require_flags = completion_cfg.get("require_flags")
    assert isinstance(require_flags, list)
    assert "act3_ch3_committed" in require_flags


def test_act3_ch3_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Outcome.json").read_text(encoding="utf-8"))
    checkpoint_cfg = _zone_setter(scene, zone_name="Act3Chapter3CheckpointZone", flag_name="act3_ch3_checkpoint")
    assert isinstance(checkpoint_cfg, dict)
    assert checkpoint_cfg.get("once") is True
    assert checkpoint_cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 3"
    assert checkpoint_cfg.get("toast_seconds") == 2.0


def test_act3_ch3_no_hard_lock_path_exists_for_route_a_route_b_and_neutral_to_completion() -> None:
    exit_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_Exit.json").read_text(encoding="utf-8"))
    entry_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Entry.json").read_text(encoding="utf-8"))
    commit_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Commit.json").read_text(encoding="utf-8"))
    outcome_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter3_Outcome.json").read_text(encoding="utf-8"))

    def evaluate(initial_flags: set[str], route_mode: str) -> bool:
        flags = set(initial_flags)
        assert _transition_enabled(exit_scene, transition_name="ToAct3Chapter3Entry", flags=flags)

        _apply_zone_setters(entry_scene, zone_name="Act3Chapter3EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry_scene, transition_name="ToAct3Chapter3Commit", flags=flags)

        if route_mode == "a":
            _apply_zone_setters(commit_scene, zone_name="Act3Chapter3CommitAZone", flags=flags)
        elif route_mode == "b":
            _apply_zone_setters(commit_scene, zone_name="Act3Chapter3CommitBZone", flags=flags)
        else:
            _apply_zone_setters(commit_scene, zone_name="Act3Chapter3NeutralProbeZone", flags=flags)
            _apply_zone_setters(commit_scene, zone_name="Act3Chapter3NeutralCommitZone", flags=flags)

        assert _transition_enabled(commit_scene, transition_name="ToAct3Chapter3Outcome", flags=flags)
        _apply_zone_setters(outcome_scene, zone_name="Act3Chapter3CompleteZone", flags=flags)
        return "act3_chapter3_complete" in flags

    assert evaluate({"act3_chapter2_complete", "act3_ch2_route_a"}, route_mode="a")
    assert evaluate({"act3_chapter2_complete", "act3_ch2_route_b"}, route_mode="b")
    assert evaluate({"act3_chapter2_complete"}, route_mode="neutral")


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch3_no_hard_lock_transitions_have_expected_targets_and_flags(
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
