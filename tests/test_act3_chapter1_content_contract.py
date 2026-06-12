from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT3_CH1_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter1_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter1_FieldGate.json",
    "packs/core_regions/scenes/Act3_Chapter1_Relay.json",
]

ACT3_CH1_QUEST_IDS = {
    "quest_act3_ch1_entry",
    "quest_act3_ch1_field_disabled",
    "quest_act3_ch1_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act2_Chapter5_Epilogue.json",
        "ToAct3Chapter1Entry",
        "packs/core_regions/scenes/Act3_Chapter1_Entry.json",
        "act2_act_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter1_Entry.json",
        "ToAct3Chapter1FieldGate",
        "packs/core_regions/scenes/Act3_Chapter1_FieldGate.json",
        "act3_ch1_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter1_FieldGate.json",
        "ToAct3Chapter1Relay",
        "packs/core_regions/scenes/Act3_Chapter1_Relay.json",
        "act3_ch1_field_disabled",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter1_FieldGate.json",
        "ToAct3Chapter1RelayBypass",
        "packs/core_regions/scenes/Act3_Chapter1_Relay.json",
        "act3_ch1_bypass_open",
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


def test_act3_ch1_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH1_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch1_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act3_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter1_entry", "act3_chapter1_field_gate", "act3_chapter1_relay"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch1_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH1_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch1_shard_console_trigger_exists_and_references_shard_flags() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))
    console_zone = _find_entity(scene, name="Act3Chapter1ShardConsoleZone")
    assert isinstance(console_zone, dict)

    configs = _set_configs(scene)
    has_shard_a = False
    has_shard_b = False
    for cfg in configs:
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_value") != "Act3Chapter1ShardConsoleZone":
            continue
        require = cfg.get("require_flags") if isinstance(cfg.get("require_flags"), list) else []
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act3_ch1_field_disabled") is not True:
            continue
        if "act2_ch3_reward_shard_a" in require:
            has_shard_a = True
        if "act2_ch3_reward_shard_b" in require:
            has_shard_b = True
    assert has_shard_a
    assert has_shard_b


def test_act3_ch1_field_disable_sets_expected_flag_with_deterministic_toast() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))
    configs = _set_configs(scene)
    matches = 0
    for cfg in configs:
        if cfg.get("event_type") != "entered_zone":
            continue
        if cfg.get("payload_value") != "Act3Chapter1ShardConsoleZone":
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act3_ch1_field_disabled") is not True:
            continue
        matches += 1
        assert cfg.get("toast") == "Field disabled."
        assert cfg.get("toast_seconds") == 2.0
        assert cfg.get("once") is True
    assert matches >= 2


def test_act3_ch1_field_hazard_entities_are_gated_by_field_disabled() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)
    hazards = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict):
            continue
        touch_cfg = cfg.get("DamageOnTouch")
        if isinstance(touch_cfg, dict):
            hazards.append(entity)
    assert hazards
    for entity in hazards:
        forbid = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
        require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        assert "act3_ch1_field_disabled" in forbid or "act3_ch1_field_disabled" in require


def test_act3_ch1_field_disabled_state_suppresses_hazard_strips_by_intent() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)

    def active_hazards(current_flags: set[str]) -> list[dict]:
        out: list[dict] = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            cfg = entity.get("behaviour_config")
            if not isinstance(cfg, dict) or not isinstance(cfg.get("DamageOnTouch"), dict):
                continue
            require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
            forbid = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
            if _flag_rule_allows(current_flags, require_flags=require, forbid_flags=forbid):
                out.append(entity)
        return out

    assert active_hazards(set()), "hazards should be active before field disable"
    assert not active_hazards({"act3_ch1_field_disabled"}), "hazards should be suppressed when field is disabled"


def test_act3_ch1_bypass_transition_and_fallback_warning_contract() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))
    bypass = _find_entity(scene, name="ToAct3Chapter1RelayBypass")
    assert isinstance(bypass, dict)
    require = bypass.get("require_flags")
    assert isinstance(require, list)
    assert require == ["act3_ch1_bypass_open"]

    fallback_cfg = _zone_setter(scene, zone_name="Act3Chapter1ShardConsoleZone", flag_name="act3_ch1_bypass_open")
    assert isinstance(fallback_cfg, dict)
    forbid = fallback_cfg.get("forbid_flags")
    assert isinstance(forbid, list)
    assert "act2_ch3_reward_shard_a" in forbid
    assert "act2_ch3_reward_shard_b" in forbid
    assert fallback_cfg.get("toast") == "Warning: shard signature missing. Bypass route opened."
    assert fallback_cfg.get("toast_seconds") == 2.0


def test_act3_ch1_no_hard_lock_path_exists_with_and_without_shard_flags() -> None:
    epilogue = json.loads(Path("packs/core_regions/scenes/Act2_Chapter5_Epilogue.json").read_text(encoding="utf-8"))
    entry = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_Entry.json").read_text(encoding="utf-8"))
    field_gate = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_FieldGate.json").read_text(encoding="utf-8"))

    def evaluate(initial_flags: set[str]) -> tuple[bool, bool]:
        flags = set(initial_flags)
        assert _transition_enabled(epilogue, transition_name="ToAct3Chapter1Entry", flags=flags)

        _apply_zone_setters(entry, zone_name="Act3Chapter1EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry, transition_name="ToAct3Chapter1FieldGate", flags=flags)

        _apply_zone_setters(field_gate, zone_name="Act3Chapter1ShardConsoleZone", flags=flags)
        direct = _transition_enabled(field_gate, transition_name="ToAct3Chapter1Relay", flags=flags)
        bypass = _transition_enabled(field_gate, transition_name="ToAct3Chapter1RelayBypass", flags=flags)
        return direct, bypass

    direct_with_shard, bypass_with_shard = evaluate({"act2_act_complete", "act2_ch3_reward_shard_a"})
    assert direct_with_shard
    assert not bypass_with_shard

    direct_without_shard, bypass_without_shard = evaluate({"act2_act_complete"})
    assert not direct_without_shard
    assert bypass_without_shard


def test_act3_ch1_checkpoint_exists_with_once_and_expected_toast_seconds() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_Relay.json").read_text(encoding="utf-8"))
    cfg = _zone_setter(scene, zone_name="Act3Chapter1CheckpointZone", flag_name="act3_ch1_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 1"
    assert cfg.get("toast_seconds") == 2.0


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch1_no_hard_lock_invariants_from_act2_bridge_to_relay(
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
