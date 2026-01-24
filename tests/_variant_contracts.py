from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager
from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast


@dataclass(frozen=True, slots=True)
class GoldenSliceVariantCase:
    variant: str
    kind: str
    preset: str
    world: str
    scene: str
    quest_id: str | None
    stage_id: str | None
    start_zone: str | None
    goal_zone: str | None
    start_toast: str | None
    complete_toast: str | None
    gold: float | None
    complete_flag: str | None
    on_trigger_start: str | None
    on_trigger_goal: str | None

    intro_quest_id: str | None = None
    intro_flag: str | None = None
    choice_a_quest_id: str | None = None
    choice_b_quest_id: str | None = None
    choice_a_start_zone: str | None = None
    choice_b_start_zone: str | None = None
    choice_a_goal_zone: str | None = None
    choice_b_goal_zone: str | None = None
    choice_a_complete_flag: str | None = None
    choice_b_complete_flag: str | None = None
    choice_gold: float | None = None
    choice_a_start_toast: str | None = None
    choice_b_start_toast: str | None = None
    choice_a_complete_toast: str | None = None
    choice_b_complete_toast: str | None = None

    puzzle_unlock_event: str | None = None
    puzzle_unlocked_flag: str | None = None
    puzzle_quest_id: str | None = None
    puzzle_start_toast: str | None = None
    puzzle_complete_toast: str | None = None
    goal_quest_id: str | None = None
    goal_complete_flag: str | None = None
    goal_start_toast: str | None = None
    goal_complete_toast: str | None = None
    goal_gold: float | None = None


GOLDEN_SLICE_VARIANT_CASES: tuple[GoldenSliceVariantCase, ...] = (    GoldenSliceVariantCase(
        variant="g",
        kind="linear",
        preset="golden_slice_variant_g",
        world="worlds/golden_slice_variant_g.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_g.json",
        quest_id="ridge_variant_g_beacon",
        stage_id="reach_beacon",
        start_zone="VariantGStartZone",
        goal_zone="VariantGGoalZone",
        start_toast="Beacon: Reach the Beacon",
        complete_toast="Beacon: Complete",
        gold=25.0,
        complete_flag="ridge_variant_g_beacon_complete",
        on_trigger_start="variant_g_start",
        on_trigger_goal="variant_g_goal",
    ),
    GoldenSliceVariantCase(
        variant="h",
        kind="linear",
        preset="golden_slice_variant_h",
        world="worlds/golden_slice_variant_h.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_h.json",
        quest_id="ridge_variant_h_relay",
        stage_id="reactivate_relay",
        start_zone="VariantHStartZone",
        goal_zone="VariantHGoalZone",
        start_toast="Relay: Reactivate the Relay",
        complete_toast="Relay: Complete",
        gold=30.0,
        complete_flag="ridge_variant_h_relay_complete",
        on_trigger_start="variant_h_start",
        on_trigger_goal="variant_h_goal",
    ),
    GoldenSliceVariantCase(
        variant="i",
        kind="linear",
        preset="golden_slice_variant_i",
        world="worlds/golden_slice_variant_i.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_i.json",
        quest_id="ridge_variant_i_cache",
        stage_id="secure_cache",
        start_zone="VariantIStartZone",
        goal_zone="VariantIGoalZone",
        start_toast="Cache: Secure the Cache",
        complete_toast="Cache: Complete",
        gold=35.0,
        complete_flag="ridge_variant_i_cache_complete",
        on_trigger_start="variant_i_start",
        on_trigger_goal="variant_i_goal",
    ),
    GoldenSliceVariantCase(
        variant="j",
        kind="branching_choice",
        preset="golden_slice_variant_j",
        world="worlds/golden_slice_variant_j.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_j.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantJStartZone",
        goal_zone=None,
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start=None,
        on_trigger_goal=None,
        intro_quest_id="ridge_variant_j_intro",
        intro_flag="ridge_variant_j_intro_complete",
        choice_a_quest_id="ridge_variant_j_choice_a",
        choice_b_quest_id="ridge_variant_j_choice_b",
        choice_a_start_zone="VariantJChoiceAZone",
        choice_b_start_zone="VariantJChoiceBZone",
        choice_a_goal_zone="VariantJGoalAZone",
        choice_b_goal_zone="VariantJGoalBZone",
        choice_a_complete_flag="ridge_variant_j_choice_a_complete",
        choice_b_complete_flag="ridge_variant_j_choice_b_complete",
        choice_gold=35.0,
        choice_a_start_toast="Choice: Path A - Secure the Cache",
        choice_b_start_toast="Choice: Path B - Secure the Cache",
        choice_a_complete_toast="Choice: Path A - Complete",
        choice_b_complete_toast="Choice: Path B - Complete",
    ),
    GoldenSliceVariantCase(
        variant="k",
        kind="puzzle_lite",
        preset="golden_slice_variant_k",
        world="worlds/golden_slice_variant_k.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_k.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantKStartZone",
        goal_zone="VariantKGoalZone",
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start="variant_k_start",
        on_trigger_goal="variant_k_goal",
        puzzle_unlock_event="ridge_variant_k_unlock",
        puzzle_unlocked_flag="ridge_variant_k_unlocked",
        puzzle_quest_id="ridge_variant_k_switch",
        puzzle_start_toast="Switch: Flip the Switch",
        puzzle_complete_toast="Switch: Gate Unlocked",
        goal_quest_id="ridge_variant_k_route",
        goal_complete_flag="ridge_variant_k_route_complete",
        goal_start_toast="Switch: Reach the Exit",
        goal_complete_toast="Switch: Complete",
        goal_gold=40.0,
    ),
    GoldenSliceVariantCase(
        variant="l",
        kind="linear",
        preset="golden_slice_variant_l",
        world="worlds/golden_slice_variant_l.json",
        scene="packs/core_regions/scenes/Ridge Outpost_dungeon_variant_l.json",
        quest_id="ridge_variant_l_beacon",
        stage_id="reach_beacon",
        start_zone="VariantLStartZone",
        goal_zone="VariantLGoalZone",
        start_toast="Beacon: Reach the Beacon",
        complete_toast="Beacon: Complete",
        gold=45.0,
        complete_flag="ridge_variant_l_beacon_complete",
        on_trigger_start="variant_l_start",
        on_trigger_goal="variant_l_goal",
    ),
    GoldenSliceVariantCase(
        variant="g2",
        kind="linear",
        preset="golden_slice2_variant_g",
        world="worlds/golden_slice2_variant_g.json",
        scene="packs/core_regions/scenes/Hollowmere_outskirts_variant_g.json",
        quest_id="ridge2_variant_g_beacon",
        stage_id="reach_beacon",
        start_zone="VariantGStartZone2",
        goal_zone="VariantGGoalZone2",
        start_toast="Beacon: Reach the Outskirts Beacon",
        complete_toast="Beacon: Complete",
        gold=25.0,
        complete_flag="ridge2_variant_g_beacon_complete",
        on_trigger_start="variant_g2_start",
        on_trigger_goal="variant_g2_goal",
    ),
    GoldenSliceVariantCase(
        variant="j2",
        kind="branching_choice",
        preset="golden_slice2_variant_j",
        world="worlds/golden_slice2_variant_j.json",
        scene="packs/core_regions/scenes/Hollowmere_outskirts_variant_j.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantJStartZone2",
        goal_zone=None,
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start=None,
        on_trigger_goal=None,
        intro_quest_id="ridge2_variant_j_intro",
        intro_flag="ridge2_variant_j_intro_complete",
        choice_a_quest_id="ridge2_variant_j_choice_a",
        choice_b_quest_id="ridge2_variant_j_choice_b",
        choice_a_start_zone="VariantJChoiceAZone2",
        choice_b_start_zone="VariantJChoiceBZone2",
        choice_a_goal_zone="VariantJGoalAZone2",
        choice_b_goal_zone="VariantJGoalBZone2",
        choice_a_complete_flag="ridge2_variant_j_choice_a_complete",
        choice_b_complete_flag="ridge2_variant_j_choice_b_complete",
        choice_gold=35.0,
        choice_a_start_toast="Choice: Path A - Secure the Cache",
        choice_b_start_toast="Choice: Path B - Secure the Cache",
        choice_a_complete_toast="Choice: Path A - Complete",
        choice_b_complete_toast="Choice: Path B - Complete",
    ),
    GoldenSliceVariantCase(
        variant="k2",
        kind="puzzle_lite",
        preset="golden_slice2_variant_k",
        world="worlds/golden_slice2_variant_k.json",
        scene="packs/core_regions/scenes/Hollowmere_outskirts_variant_k.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantKStartZone2",
        goal_zone="VariantKGoalZone2",
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start="variant_k2_start",
        on_trigger_goal="variant_k2_goal",
        puzzle_unlock_event="ridge2_variant_k_unlock",
        puzzle_unlocked_flag="ridge2_variant_k_unlocked",
        puzzle_quest_id="ridge2_variant_k_switch",
        puzzle_start_toast="Switch: Flip the Switch",
        puzzle_complete_toast="Switch: Gate Unlocked",
        goal_quest_id="ridge2_variant_k_route",
        goal_complete_flag="ridge2_variant_k_route_complete",
        goal_start_toast="Switch: Reach the Exit",
        goal_complete_toast="Switch: Complete",
        goal_gold=45.0,
    ),
    GoldenSliceVariantCase(
        variant="m2",
        kind="branching_choice",
        preset="golden_slice2_variant_m",
        world="worlds/golden_slice2_variant_m.json",
        scene="packs/core_regions/scenes/Hollowmere_outskirts_variant_m.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantMStartZone2",
        goal_zone=None,
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start=None,
        on_trigger_goal=None,
        intro_quest_id="ridge2_variant_m_intro",
        intro_flag="ridge2_variant_m_intro_complete",
        choice_a_quest_id="ridge2_variant_m_choice_a",
        choice_b_quest_id="ridge2_variant_m_choice_b",
        choice_a_start_zone="VariantMChoiceAZone2",
        choice_b_start_zone="VariantMChoiceBZone2",
        choice_a_goal_zone="VariantMGoalAZone2",
        choice_b_goal_zone="VariantMGoalBZone2",
        choice_a_complete_flag="ridge2_variant_m_choice_a_complete",
        choice_b_complete_flag="ridge2_variant_m_choice_b_complete",
        choice_gold=50.0,
        choice_a_start_toast="Choice: Path A - Secure the Cache",
        choice_b_start_toast="Choice: Path B - Secure the Cache",
        choice_a_complete_toast="Choice: Path A - Complete",
        choice_b_complete_toast="Choice: Path B - Complete",
    ),
    GoldenSliceVariantCase(
        variant="n2",
        kind="puzzle_lite",
        preset="golden_slice2_variant_n",
        world="worlds/golden_slice2_variant_n.json",
        scene="packs/core_regions/scenes/Hollowmere_outskirts_variant_n.json",
        quest_id=None,
        stage_id=None,
        start_zone="VariantNStartZone2",
        goal_zone="VariantNGoalZone2",
        start_toast=None,
        complete_toast=None,
        gold=None,
        complete_flag=None,
        on_trigger_start="variant_n2_start",
        on_trigger_goal="variant_n2_goal",
        puzzle_unlock_event="ridge2_variant_n_unlock",
        puzzle_unlocked_flag="ridge2_variant_n_unlocked",
        puzzle_quest_id="ridge2_variant_n_switch",
        puzzle_start_toast="Switch: Flip the Switch",
        puzzle_complete_toast="Switch: Gate Unlocked",
        goal_quest_id="ridge2_variant_n_route",
        goal_complete_flag="ridge2_variant_n_route_complete",
        goal_start_toast="Switch: Reach the Exit",
        goal_complete_toast="Switch: Complete",
        goal_gold=55.0,
    ),
)


def get_golden_slice_variant_case(variant: str) -> GoldenSliceVariantCase:
    needle = str(variant or "").strip().lower()
    for case in GOLDEN_SLICE_VARIANT_CASES:
        if case.variant == needle:
            return case
    raise AssertionError(f"Missing golden slice variant case: {needle!r}")


def load_scene_and_assert_valid(scene_path: str) -> None:
    loader = SceneLoader()
    report = loader.validate_scene_file(scene_path, strict=True)
    assert report.ok, f"Scene validation failed: {report.errors}"


class _StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
        self.toasts.append(str(message))


class _StubWindow:
    def __init__(self, *, with_hud: bool) -> None:
        self.listeners: dict[str, list] = {}
        if with_hud:
            self.player_hud = _StubHUD()
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None

        self.game_state_controller.quests = None
        self.game_state_controller.quests = QuestManager(self)

    def emit_signal(self, event_name: str, **payload) -> None:
        event = MeshEvent(event_name, payload)
        if event_name in self.listeners:
            for callback in list(self.listeners[event_name]):
                callback(event)

        qm = self.game_state_controller.quests
        if qm and hasattr(qm, "handle_event"):
            qm.handle_event(event)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


def drive_zone_to_zone_quest(
    *,
    quest_id: str,
    stage_id: str,
    start_zone_id: str,
    goal_zone_id: str,
    expected_flag: str,
    expected_gold: float,
) -> None:
    window = _StubWindow(with_hud=False)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    assert quest_id in qm._definitions
    assert not qm.is_quest_active(quest_id)
    assert not qm.is_quest_completed(quest_id)

    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(quest_id)
    assert qm.get_current_stage(quest_id)["id"] == stage_id

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(quest_id)
    assert window.get_flag(expected_flag) is True
    assert window.get_counter("gold", 0.0) == gold_before + float(expected_gold)


def assert_reward_toast_idempotent(
    *,
    quest_id: str,
    start_zone_id: str,
    goal_zone_id: str,
    start_toast: str,
    complete_toast: str,
    expected_gold: float,
) -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(quest_id)

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [start_toast]

    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [start_toast]

    qm.load_definitions()
    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [start_toast]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(quest_id)
    assert window.get_counter("gold", 0.0) == gold_before + float(expected_gold)

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        start_toast,
        complete_toast,
    ]

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [
        start_toast,
        complete_toast,
    ]


def assert_content_invariants(
    *,
    scene_json_path: str,
    quest_id: str,
    start_zone_id: str,
    goal_zone_id: str,
    expected_gold: float,
    expected_flag: str,
    expected_start_toast: str,
    expected_complete_toast: str,
    on_trigger_start: str,
    on_trigger_goal: str,
) -> None:
    scene_path = Path(scene_json_path)
    assert scene_path.exists()
    scene = json.loads(scene_path.read_text(encoding="utf-8"))

    entities = scene.get("entities", [])
    assert isinstance(entities, list)

    start_entities = [e for e in entities if isinstance(e, dict) and e.get("name") == start_zone_id]
    goal_entities = [e for e in entities if isinstance(e, dict) and e.get("name") == goal_zone_id]

    assert len(start_entities) == 1
    assert len(goal_entities) == 1

    def _assert_trigger_zone(ent: dict, expected_zone: str) -> None:
        behaviours = ent.get("behaviours", [])
        assert "TriggerZone" in behaviours
        cfg = (ent.get("behaviour_config") or {}).get("TriggerZone") or {}
        assert cfg.get("trigger_target") == "Player"
        assert cfg.get("on_trigger") in {on_trigger_start, on_trigger_goal}
        assert cfg.get("trigger_radius") is not None
        assert expected_zone == ent.get("name")

    _assert_trigger_zone(start_entities[0], start_zone_id)
    _assert_trigger_zone(goal_entities[0], goal_zone_id)

    quests_path = Path("assets/data/quests.json")
    assert quests_path.exists()
    quests_root = json.loads(quests_path.read_text(encoding="utf-8")).get("quests", [])
    assert isinstance(quests_root, list)

    quest = next((q for q in quests_root if isinstance(q, dict) and q.get("id") == quest_id), None)
    assert quest is not None

    assert quest.get("start_toast") == expected_start_toast
    assert quest.get("complete_toast") == expected_complete_toast

    stages = quest.get("stages", [])
    assert isinstance(stages, list)
    assert len(stages) == 1

    stage = stages[0]
    start_on = stage.get("start_on_event") or {}
    complete_on = stage.get("complete_on") or {}

    assert start_on.get("type") == "entered_zone"
    assert (start_on.get("payload") or {}).get("zone") == start_zone_id
    assert complete_on.get("type") == "entered_zone"
    assert (complete_on.get("payload") or {}).get("zone") == goal_zone_id

    reward = quest.get("reward")
    assert isinstance(reward, dict)
    assert set(reward.keys()) == {"set_flags", "inc_counters"}

    set_flags = reward.get("set_flags")
    inc_counters = reward.get("inc_counters")
    assert isinstance(set_flags, dict)
    assert isinstance(inc_counters, dict)

    assert set(set_flags.keys()) == {expected_flag}
    assert set_flags[expected_flag] is True

    assert set(inc_counters.keys()) == {"gold"}
    assert inc_counters["gold"] == float(expected_gold)


def assert_preset_targets_world(preset_name: str, world_path: str) -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    preset = (config.get("presets") or {}).get(preset_name)
    assert isinstance(preset, dict)

    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    assert len(steps) >= 1

    pipeline_steps = [s for s in steps if isinstance(s, dict) and s.get("cmd") == "pipeline"]
    assert pipeline_steps

    for step in pipeline_steps:
        args = step.get("args", [])
        assert isinstance(args, list)
        assert "--world" in args
        idx = args.index("--world")
        assert idx + 1 < len(args)
        assert args[idx + 1] == world_path


def assert_branching_choice_content_invariants(
    *,
    scene_json_path: str,
    start_zone_id: str,
    intro_quest_id: str,
    intro_flag: str,
    choice_a_quest_id: str,
    choice_b_quest_id: str,
    choice_a_start_zone: str,
    choice_b_start_zone: str,
    choice_a_goal_zone: str,
    choice_b_goal_zone: str,
    choice_a_complete_flag: str,
    choice_b_complete_flag: str,
    choice_gold: float,
    choice_a_start_toast: str,
    choice_b_start_toast: str,
    choice_a_complete_toast: str,
    choice_b_complete_toast: str,
) -> None:
    scene_path = Path(scene_json_path)
    assert scene_path.exists()
    scene = json.loads(scene_path.read_text(encoding="utf-8"))

    entities = scene.get("entities", [])
    assert isinstance(entities, list)

    zone_names = {
        start_zone_id,
        choice_a_start_zone,
        choice_b_start_zone,
        choice_a_goal_zone,
        choice_b_goal_zone,
    }
    for name in sorted(zone_names):
        matches = [e for e in entities if isinstance(e, dict) and e.get("name") == name]
        assert len(matches) == 1
        ent = matches[0]
        behaviours = ent.get("behaviours", [])
        assert "TriggerZone" in behaviours
        cfg = (ent.get("behaviour_config") or {}).get("TriggerZone") or {}
        assert cfg.get("trigger_target") == "Player"
        assert cfg.get("trigger_radius") is not None

    quests_path = Path("assets/data/quests.json")
    assert quests_path.exists()
    quests_root = json.loads(quests_path.read_text(encoding="utf-8")).get("quests", [])
    assert isinstance(quests_root, list)
    by_id = {q.get("id"): q for q in quests_root if isinstance(q, dict) and q.get("id")}

    intro = by_id.get(intro_quest_id)
    assert isinstance(intro, dict)
    reward = intro.get("reward")
    assert isinstance(reward, dict)
    assert set(reward.keys()) == {"set_flags", "inc_counters"}
    assert reward.get("set_flags") == {intro_flag: True}
    assert reward.get("inc_counters") == {}

    for quest_id, start_zone, goal_zone, complete_flag, blocked_flag, start_toast, complete_toast in (
        (
            choice_a_quest_id,
            choice_a_start_zone,
            choice_a_goal_zone,
            choice_a_complete_flag,
            choice_b_complete_flag,
            choice_a_start_toast,
            choice_a_complete_toast,
        ),
        (
            choice_b_quest_id,
            choice_b_start_zone,
            choice_b_goal_zone,
            choice_b_complete_flag,
            choice_a_complete_flag,
            choice_b_start_toast,
            choice_b_complete_toast,
        ),
    ):
        quest = by_id.get(quest_id)
        assert isinstance(quest, dict)
        assert quest.get("requires_flags") == [intro_flag]
        assert quest.get("blocks_flags") == [blocked_flag]
        assert quest.get("start_toast") == start_toast
        assert quest.get("complete_toast") == complete_toast

        stages = quest.get("stages", [])
        assert isinstance(stages, list)
        assert len(stages) == 1
        stage = stages[0]
        start_on = stage.get("start_on_event") or {}
        complete_on = stage.get("complete_on") or {}
        assert start_on.get("type") == "entered_zone"
        assert (start_on.get("payload") or {}).get("zone") == start_zone
        assert complete_on.get("type") == "entered_zone"
        assert (complete_on.get("payload") or {}).get("zone") == goal_zone

        reward = quest.get("reward")
        assert isinstance(reward, dict)
        assert set(reward.keys()) == {"set_flags", "inc_counters"}
        assert reward.get("set_flags") == {complete_flag: True}
        assert reward.get("inc_counters") == {"gold": float(choice_gold)}


def assert_branching_choice_paths(
    *,
    intro_quest_id: str,
    intro_flag: str,
    start_zone_id: str,
    choice_a_quest_id: str,
    choice_b_quest_id: str,
    choice_a_start_zone: str,
    choice_b_start_zone: str,
    choice_a_goal_zone: str,
    choice_b_goal_zone: str,
    choice_a_complete_flag: str,
    choice_b_complete_flag: str,
    choice_gold: float,
    choice_a_start_toast: str,
    choice_b_start_toast: str,
    choice_a_complete_toast: str,
    choice_b_complete_toast: str,
) -> None:
    def _run_path(
        *,
        chosen_quest_id: str,
        chosen_start_zone: str,
        chosen_goal_zone: str,
        chosen_start_toast: str,
        chosen_complete_toast: str,
        chosen_flag: str,
        blocked_quest_id: str,
        blocked_start_zone: str,
        blocked_flag: str,
    ) -> None:
        window = _StubWindow(with_hud=True)
        qm = window.game_state_controller.quests
        qm.load_definitions()

        maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
        window.player_hud.toasts.clear()

        window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
        assert qm.is_quest_completed(intro_quest_id) is True
        assert window.get_flag(intro_flag) is True

        window.emit_signal("entered_zone", zone=chosen_start_zone, actor="Player", position=(0.0, 0.0))
        assert qm.is_quest_active(chosen_quest_id) is True
        did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
        assert did_toast is True
        assert window.player_hud.toasts == [chosen_start_toast]

        gold_before = window.get_counter("gold", 0.0)
        window.emit_signal("entered_zone", zone=chosen_goal_zone, actor="Player", position=(0.0, 0.0))
        assert qm.is_quest_completed(chosen_quest_id) is True
        assert window.get_counter("gold", 0.0) == gold_before + float(choice_gold)
        assert window.get_flag(chosen_flag) is True

        did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
        assert did_toast is True
        assert window.player_hud.toasts == [chosen_start_toast, chosen_complete_toast]

        gold_after = window.get_counter("gold", 0.0)
        window.emit_signal("entered_zone", zone=chosen_goal_zone, actor="Player", position=(0.0, 0.0))
        assert window.get_counter("gold", 0.0) == gold_after
        did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
        assert did_toast is False

        window.emit_signal("entered_zone", zone=blocked_start_zone, actor="Player", position=(0.0, 0.0))
        assert qm.is_quest_completed(blocked_quest_id) is False
        assert qm.is_quest_active(blocked_quest_id) is False
        assert window.get_flag(blocked_flag) is False
        assert window.get_counter("gold", 0.0) == gold_after

        did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
        assert did_toast is False

        qm.load_definitions()
        window.emit_signal("entered_zone", zone=blocked_start_zone, actor="Player", position=(0.0, 0.0))
        assert qm.is_quest_active(blocked_quest_id) is False
        assert window.get_counter("gold", 0.0) == gold_after
        assert window.player_hud.toasts == [chosen_start_toast, chosen_complete_toast]

    _run_path(
        chosen_quest_id=choice_a_quest_id,
        chosen_start_zone=choice_a_start_zone,
        chosen_goal_zone=choice_a_goal_zone,
        chosen_start_toast=choice_a_start_toast,
        chosen_complete_toast=choice_a_complete_toast,
        chosen_flag=choice_a_complete_flag,
        blocked_quest_id=choice_b_quest_id,
        blocked_start_zone=choice_b_start_zone,
        blocked_flag=choice_b_complete_flag,
    )
    _run_path(
        chosen_quest_id=choice_b_quest_id,
        chosen_start_zone=choice_b_start_zone,
        chosen_goal_zone=choice_b_goal_zone,
        chosen_start_toast=choice_b_start_toast,
        chosen_complete_toast=choice_b_complete_toast,
        chosen_flag=choice_b_complete_flag,
        blocked_quest_id=choice_a_quest_id,
        blocked_start_zone=choice_a_start_zone,
        blocked_flag=choice_a_complete_flag,
    )


def assert_puzzle_lite_paths(
    *,
    start_zone_id: str,
    goal_zone_id: str,
    unlock_event: str,
    unlocked_flag: str,
    puzzle_quest_id: str,
    puzzle_start_toast: str,
    puzzle_complete_toast: str,
    goal_quest_id: str,
    goal_complete_flag: str,
    goal_start_toast: str,
    goal_complete_toast: str,
    goal_gold: float,
) -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone=start_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(puzzle_quest_id) is True
    assert qm.is_quest_active(goal_quest_id) is False

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [puzzle_start_toast]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(goal_quest_id) is False
    assert window.get_counter("gold", 0.0) == gold_before
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [puzzle_start_toast]

    window.emit_signal(unlock_event, actor="Player")
    assert window.get_flag(unlocked_flag) is True
    assert qm.is_quest_completed(puzzle_quest_id) is True
    assert qm.is_quest_active(goal_quest_id) is True

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        puzzle_start_toast,
        puzzle_complete_toast,
        goal_start_toast,
    ]

    gold_mid = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(goal_quest_id) is True
    assert window.get_flag(goal_complete_flag) is True
    assert window.get_counter("gold", 0.0) == gold_mid + float(goal_gold)

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        puzzle_start_toast,
        puzzle_complete_toast,
        goal_start_toast,
        goal_complete_toast,
    ]

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal(unlock_event, actor="Player")
    window.emit_signal("entered_zone", zone=goal_zone_id, actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [
        puzzle_start_toast,
        puzzle_complete_toast,
        goal_start_toast,
        goal_complete_toast,
    ]


def assert_puzzle_lite_content_invariants(
    *,
    scene_json_path: str,
    start_zone_id: str,
    goal_zone_id: str,
    on_trigger_start: str,
    on_trigger_goal: str,
    unlock_event: str,
    unlocked_flag: str,
    puzzle_quest_id: str,
    puzzle_start_toast: str,
    puzzle_complete_toast: str,
    goal_quest_id: str,
    goal_start_toast: str,
    goal_complete_toast: str,
    goal_complete_flag: str,
    goal_gold: float,
) -> None:
    scene_path = Path(scene_json_path)
    assert scene_path.exists()
    scene = json.loads(scene_path.read_text(encoding="utf-8"))

    entities = scene.get("entities", [])
    assert isinstance(entities, list)

    def _find_one(name: str) -> dict:
        matches = [e for e in entities if isinstance(e, dict) and e.get("name") == name]
        assert len(matches) == 1
        assert isinstance(matches[0], dict)
        return matches[0]

    start_ent = _find_one(start_zone_id)
    goal_ent = _find_one(goal_zone_id)

    for ent, expected_on_trigger in (
        (start_ent, on_trigger_start),
        (goal_ent, on_trigger_goal),
    ):
        behaviours = ent.get("behaviours", [])
        assert "TriggerZone" in behaviours
        cfg = (ent.get("behaviour_config") or {}).get("TriggerZone") or {}
        assert cfg.get("trigger_target") == "Player"
        assert cfg.get("on_trigger") == expected_on_trigger
        assert cfg.get("trigger_radius") is not None

    switch_ent = _find_one("ridge_variant_k_switch")
    switch_behaviours = switch_ent.get("behaviours", [])
    assert "SwitchInteract" in switch_behaviours
    switch_cfg = (switch_ent.get("behaviour_config") or {}).get("SwitchInteract") or {}
    assert switch_cfg.get("event_id") == unlock_event

    quests_path = Path("assets/data/quests.json")
    assert quests_path.exists()
    quests_root = json.loads(quests_path.read_text(encoding="utf-8")).get("quests", [])
    assert isinstance(quests_root, list)
    by_id = {q.get("id"): q for q in quests_root if isinstance(q, dict) and q.get("id")}

    puzzle = by_id.get(puzzle_quest_id)
    assert isinstance(puzzle, dict)
    assert puzzle.get("start_toast") == puzzle_start_toast
    assert puzzle.get("complete_toast") == puzzle_complete_toast
    stages = puzzle.get("stages", [])
    assert isinstance(stages, list)
    assert len(stages) == 1
    stage = stages[0]
    assert (stage.get("start_on_event") or {}).get("type") == "entered_zone"
    assert ((stage.get("start_on_event") or {}).get("payload") or {}).get("zone") == start_zone_id
    assert (stage.get("complete_on") or {}).get("type") == unlock_event
    reward = puzzle.get("reward")
    assert isinstance(reward, dict)
    assert reward.get("set_flags") == {unlocked_flag: True}
    assert reward.get("inc_counters") == {}

    goal = by_id.get(goal_quest_id)
    assert isinstance(goal, dict)
    assert goal.get("requires_flags") == [unlocked_flag]
    assert goal.get("start_toast") == goal_start_toast
    assert goal.get("complete_toast") == goal_complete_toast
    stages = goal.get("stages", [])
    assert isinstance(stages, list)
    assert len(stages) == 1
    stage = stages[0]
    assert (stage.get("start_on_event") or {}).get("type") == unlock_event
    assert (stage.get("complete_on") or {}).get("type") == "entered_zone"
    assert ((stage.get("complete_on") or {}).get("payload") or {}).get("zone") == goal_zone_id
    reward = goal.get("reward")
    assert isinstance(reward, dict)
    assert reward.get("set_flags") == {goal_complete_flag: True}
    assert reward.get("inc_counters") == {"gold": float(goal_gold)}
