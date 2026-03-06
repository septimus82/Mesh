from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


ACT3_CH2_SCENES = [
    "packs/core_regions/scenes/Act3_Chapter2_Entry.json",
    "packs/core_regions/scenes/Act3_Chapter2_RouteHub.json",
    "packs/core_regions/scenes/Act3_Chapter2_Exit.json",
]

ACT3_CH2_QUEST_IDS = {
    "quest_act3_ch2_entry",
    "quest_act3_ch2_route_power",
    "quest_act3_ch2_complete",
}

NO_HARD_LOCK_TRANSITIONS = [
    (
        "packs/core_regions/scenes/Act3_Chapter1_Relay.json",
        "ToAct3Chapter2Entry",
        "packs/core_regions/scenes/Act3_Chapter2_Entry.json",
        "act3_chapter1_complete",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter2_Entry.json",
        "ToAct3Chapter2RouteHub",
        "packs/core_regions/scenes/Act3_Chapter2_RouteHub.json",
        "act3_ch2_started",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter2_RouteHub.json",
        "ToAct3Chapter2Exit",
        "packs/core_regions/scenes/Act3_Chapter2_Exit.json",
        "act3_ch2_power_routed",
    ),
    (
        "packs/core_regions/scenes/Act3_Chapter2_RouteHub.json",
        "ToAct3Chapter2ExitBypass",
        "packs/core_regions/scenes/Act3_Chapter2_Exit.json",
        "act3_ch2_bypass_open",
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


def test_act3_ch2_scene_files_parse_and_references_resolve() -> None:
    for scene_path in ACT3_CH2_SCENES:
        path = Path(scene_path)
        assert path.exists(), scene_path
        scene = json.loads(path.read_text(encoding="utf-8"))
        _assert_scene_references_resolve(scene_path, scene)


def test_act3_ch2_world_registry_contains_new_scenes() -> None:
    world = json.loads(Path("worlds/act3_chapter1_stub.json").read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    for key in ["act3_chapter2_entry", "act3_chapter2_route_hub", "act3_chapter2_exit"]:
        entry = scenes.get(key)
        assert isinstance(entry, dict), f"missing world scene entry {key}"
        scene_path = entry.get("path")
        assert isinstance(scene_path, str) and scene_path
        assert Path(scene_path).exists()


def test_act3_ch2_quests_exist_and_have_objective_lines() -> None:
    quests_doc = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = quests_doc.get("quests")
    assert isinstance(quests, list)
    by_id = {
        quest.get("id"): quest
        for quest in quests
        if isinstance(quest, dict) and isinstance(quest.get("id"), str)
    }
    for quest_id in ACT3_CH2_QUEST_IDS:
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict), f"missing quest {quest_id}"
        description = quest.get("description")
        assert isinstance(description, str) and description.strip(), f"{quest_id} missing objective/description line"


def test_act3_ch2_route_consoles_exist_with_deterministic_toasts_and_flags() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_RouteHub.json").read_text(encoding="utf-8"))
    route_a_console = _find_entity(scene, name="Act3Chapter2RouteAConsoleZone")
    route_b_console = _find_entity(scene, name="Act3Chapter2RouteBConsoleZone")
    assert isinstance(route_a_console, dict)
    assert isinstance(route_b_console, dict)

    route_a_cfg = _zone_setter(scene, zone_name="Act3Chapter2RouteAConsoleZone", flag_name="act3_ch2_route_a")
    route_b_cfg = _zone_setter(scene, zone_name="Act3Chapter2RouteBConsoleZone", flag_name="act3_ch2_route_b")
    assert isinstance(route_a_cfg, dict)
    assert isinstance(route_b_cfg, dict)
    assert route_a_cfg.get("toast") == "Route A engaged."
    assert route_b_cfg.get("toast") == "Route B engaged."
    assert route_a_cfg.get("toast_seconds") == 2.0
    assert route_b_cfg.get("toast_seconds") == 2.0
    set_flags_a = route_a_cfg.get("set_flags")
    set_flags_b = route_b_cfg.get("set_flags")
    assert isinstance(set_flags_a, dict)
    assert isinstance(set_flags_b, dict)
    assert set_flags_a.get("act3_ch2_route_b") is False
    assert set_flags_b.get("act3_ch2_route_a") is False


def test_act3_ch2_gate_entities_are_gated_by_power_routed() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_RouteHub.json").read_text(encoding="utf-8"))
    gate = _find_entity(scene, name="ToAct3Chapter2Exit")
    assert isinstance(gate, dict)
    require_flags = gate.get("require_flags")
    assert isinstance(require_flags, list)
    assert "act3_ch2_power_routed" in require_flags


def test_act3_ch2_checkpoint_exists_with_expected_once_toast_and_seconds() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_Exit.json").read_text(encoding="utf-8"))
    cfg = _zone_setter(scene, zone_name="Act3Chapter2CheckpointZone", flag_name="act3_ch2_checkpoint")
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("toast") == "Checkpoint reached: Act 3 Chapter 2"
    assert cfg.get("toast_seconds") == 2.0


def test_act3_ch2_no_hard_lock_path_exists_with_and_without_route_engagement() -> None:
    relay = json.loads(Path("packs/core_regions/scenes/Act3_Chapter1_Relay.json").read_text(encoding="utf-8"))
    entry = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_Entry.json").read_text(encoding="utf-8"))
    hub = json.loads(Path("packs/core_regions/scenes/Act3_Chapter2_RouteHub.json").read_text(encoding="utf-8"))

    def evaluate(initial_flags: set[str], engage_route: bool) -> tuple[bool, bool]:
        flags = set(initial_flags)
        assert _transition_enabled(relay, transition_name="ToAct3Chapter2Entry", flags=flags)

        _apply_zone_setters(entry, zone_name="Act3Chapter2EntryBriefingZone", flags=flags)
        assert _transition_enabled(entry, transition_name="ToAct3Chapter2RouteHub", flags=flags)

        if engage_route:
            _apply_zone_setters(hub, zone_name="Act3Chapter2RouteAConsoleZone", flags=flags)
            _apply_zone_setters(hub, zone_name="Act3Chapter2PowerJunctionZone", flags=flags)
        else:
            _apply_zone_setters(hub, zone_name="Act3Chapter2BypassProbeZone", flags=flags)

        direct = _transition_enabled(hub, transition_name="ToAct3Chapter2Exit", flags=flags)
        bypass = _transition_enabled(hub, transition_name="ToAct3Chapter2ExitBypass", flags=flags)
        return direct, bypass

    direct_with_route, bypass_with_route = evaluate({"act3_chapter1_complete"}, engage_route=True)
    assert direct_with_route
    assert not bypass_with_route

    direct_without_route, bypass_without_route = evaluate({"act3_chapter1_complete"}, engage_route=False)
    assert not direct_without_route
    assert bypass_without_route


@pytest.mark.parametrize(
    ("scene_path", "transition_name", "expected_target", "required_flag"),
    NO_HARD_LOCK_TRANSITIONS,
)
def test_act3_ch2_no_hard_lock_transitions_have_expected_targets_and_flags(
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
