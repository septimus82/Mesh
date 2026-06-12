from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


ACT3_CH5_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter5_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter5_PhaseField.json",
    "packs/core_regions/scenes/Act3_Chapter5_Exit.json",
]

ACT3_CH5_QUEST_IDS = {
    "quest_act3_ch5_entry",
    "quest_act3_ch5_phase_latched",
    "quest_act3_ch5_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act3_Chapter4_Exit.json",
        "ToAct3Chapter5Entry",
        "packs/core_regions/scenes/Act3_Chapter5_Entry.json",
        "act3_chapter4_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter5_Entry.json",
        "ToAct3Chapter5PhaseField",
        "packs/core_regions/scenes/Act3_Chapter5_PhaseField.json",
        "act3_ch5_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter5_PhaseField.json",
        "ToAct3Chapter5Exit",
        "packs/core_regions/scenes/Act3_Chapter5_Exit.json",
        "act3_ch5_phase_latched",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter5_PhaseField.json",
        "ToAct3Chapter5ExitBypass",
        "packs/core_regions/scenes/Act3_Chapter5_Exit.json",
        "act3_ch5_bypass_open",
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


def _apply_scene_loaded_setters(scene: dict, *, flags: set[str]) -> None:
    for cfg in _set_configs(scene):
        if cfg.get("event_type") != "scene_loaded":
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


def test_act3_ch5_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH5_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch5_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act3_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter5_entry", "act3_chapter5_phase_field", "act3_chapter5_exit"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch5_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH5_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch5_latch_console_zone_exists_and_default_phase_a_bootstrap_exists() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    assert isinstance(_find_entity(scene, name="Act3Chapter5LatchConsoleZone"), dict)
    configs = _set_configs(scene)
    defaults = []
    for cfg in configs:
        if cfg.get("event_type") != "scene_loaded":
            continue
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            continue
        if set_flags.get("act3_ch5_phase_a") is True:
            defaults.append(cfg)
    assert defaults, "missing scene-load bootstrap for default phase A"
    forbid = defaults[0].get("forbid_flags")
    assert isinstance(forbid, list)
    assert "act3_ch5_phase_a" in forbid and "act3_ch5_phase_b" in forbid


def test_act3_ch5_latch_console_toggles_have_deterministic_toasts_and_mutual_exclusivity_writes() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    latch_a_cfgs = _zone_setters(scene, zone_name="Act3Chapter5LatchConsoleZone", flag_name="act3_ch5_phase_a")
    latch_b_cfgs = _zone_setters(scene, zone_name="Act3Chapter5LatchConsoleZone", flag_name="act3_ch5_phase_b")
    assert latch_a_cfgs and latch_b_cfgs

    cfg_a = next(cfg for cfg in latch_a_cfgs if cfg.get("toast") == "Phase latched: A.")
    cfg_b = next(cfg for cfg in latch_b_cfgs if cfg.get("toast") == "Phase latched: B.")
    set_a = cfg_a.get("set_flags")
    set_b = cfg_b.get("set_flags")
    assert isinstance(set_a, dict)
    assert isinstance(set_b, dict)
    assert set_a.get("act3_ch5_phase_b") is False
    assert set_b.get("act3_ch5_phase_a") is False
    assert set_a.get("act3_ch5_phase_latched") is True
    assert set_b.get("act3_ch5_phase_latched") is True
    assert cfg_a.get("toast_seconds") == 2.0
    assert cfg_b.get("toast_seconds") == 2.0


def test_act3_ch5_hazard_layouts_reference_phase_gating_with_mutually_exclusive_intent() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)

    phase_a_hazards = []
    phase_b_hazards = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if not isinstance(cfg, dict) or not isinstance(cfg.get("DamageOnTouch"), dict):
            continue
        require = entity.get("require_flags") if isinstance(entity.get("require_flags"), list) else []
        forbid = entity.get("forbid_flags") if isinstance(entity.get("forbid_flags"), list) else []
        if "act3_ch5_phase_a" in require:
            phase_a_hazards.append((require, forbid))
        if "act3_ch5_phase_b" in require:
            phase_b_hazards.append((require, forbid))

    assert phase_a_hazards
    assert phase_b_hazards
    assert any("act3_ch5_phase_b" in forbid for _, forbid in phase_a_hazards)
    assert any("act3_ch5_phase_a" in forbid for _, forbid in phase_b_hazards)


def test_act3_ch5_main_exit_requires_phase_latched() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    transition = _find_entity(scene, name="ToAct3Chapter5Exit")
    assert isinstance(transition, dict)
    require_flags = transition.get("require_flags")
    assert isinstance(require_flags, list)
    assert require_flags == ["act3_ch5_phase_latched"]


def test_act3_ch5_bypass_fail_safe_exists_with_warning_and_bypass_transition_requires_exact_flag() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    bypass_cfgs = _zone_setters(scene, zone_name="Act3Chapter5BypassProbeZone", flag_name="act3_ch5_bypass_open")
    assert len(bypass_cfgs) == 1
    cfg = bypass_cfgs[0]
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Warning: phase not latched. Bypass opened."
    assert cfg.get("toast_seconds") == 2.0

    bypass_transition = _find_entity(scene, name="ToAct3Chapter5ExitBypass")
    assert isinstance(bypass_transition, dict)
    require_flags = bypass_transition.get("require_flags")
    assert require_flags == ["act3_ch5_bypass_open"]


def test_act3_ch5_checkpoint_exists_with_expected_toast_once_and_seconds() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_Exit.json").read_text(encoding="utf-8"))
    cfgs = _zone_setters(scene, zone_name="Act3Chapter5CheckpointZone", flag_name="act3_ch5_checkpoint")
    assert len(cfgs) == 1
    cfg = cfgs[0]
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 5"
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch5_no_hard_lock_path_exists_for_phase_a_phase_b_and_never_latched() -> None:
    ch4_exit_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter4_Exit.json").read_text(encoding="utf-8"))
    entry_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_Entry.json").read_text(encoding="utf-8"))
    field_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_PhaseField.json").read_text(encoding="utf-8"))
    exit_scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter5_Exit.json").read_text(encoding="utf-8"))

    def evaluate(mode: str) -> bool:
        flags = {"act3_chapter4_complete"}
        assert _transition_enabled(ch4_exit_scene, transition_name="ToAct3Chapter5Entry", flags=flags)

        _apply_zone_setters(entry_scene, zone_name="Act3Chapter5EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry_scene, transition_name="ToAct3Chapter5PhaseField", flags=flags)

        _apply_scene_loaded_setters(field_scene, flags=flags)
        if mode == "phase_a":
            _apply_zone_setters(field_scene, zone_name="Act3Chapter5LatchConsoleZone", flags=flags)
            _apply_zone_setters(field_scene, zone_name="Act3Chapter5LatchConsoleZone", flags=flags)
            assert _transition_enabled(field_scene, transition_name="ToAct3Chapter5Exit", flags=flags)
        elif mode == "phase_b":
            _apply_zone_setters(field_scene, zone_name="Act3Chapter5LatchConsoleZone", flags=flags)
            assert _transition_enabled(field_scene, transition_name="ToAct3Chapter5Exit", flags=flags)
        else:
            _apply_zone_setters(field_scene, zone_name="Act3Chapter5BypassProbeZone", flags=flags)
            assert _transition_enabled(field_scene, transition_name="ToAct3Chapter5ExitBypass", flags=flags)

        _apply_zone_setters(exit_scene, zone_name="Act3Chapter5CompleteZone", flags=flags)
        return "act3_chapter5_complete" in flags

    assert evaluate("phase_a")
    assert evaluate("phase_b")
    assert evaluate("never_latched")


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch5_no_hard_lock_transitions_have_expected_targets_and_flags(
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
