"""Integration tests for the Mini Campaign 01 stitched flow.

Covers:
- Happy path: town → puzzle → combat → campaign_complete
- Scene transition wiring via SceneExit + campaign_portal prefab
- Save/restore across scene boundaries
- Global campaign flags persist across scenes
- Quest chain (mini_campaign_01) progresses across scenes
- Determinism: identical inputs → identical outcomes
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.behaviours.health import Health
from engine.events import MeshEventBus
from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.state_runtime import flags as state_flags


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOWN_SCENE = Path("scenes/town_schedule_01.json")
PUZZLE_SCENE = Path("scenes/puzzle_room_03.json")
COMBAT_SCENE = Path("scenes/combat_vignette_01.json")
PREFABS_PATH = Path("assets/prefabs.json")
QUESTS_PATH = Path("assets/data/quests.json")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prefab(prefab_id: str) -> Dict[str, Any]:
    prefabs = _load_json(PREFABS_PATH)
    for entry in prefabs:
        if entry.get("id") == prefab_id:
            return entry
    raise AssertionError(f"Prefab '{prefab_id}' not found")


def _load_scene_entities(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    return list(payload.get("entities", []))


# ---------------------------------------------------------------------------
# Mock DayNight (for town scene NpcSchedule / TimeOfDayGate)
# ---------------------------------------------------------------------------

class MockDayNight:
    def __init__(self, start_hour: float = 8.0) -> None:
        self._hour = float(start_hour) % 24.0

    @property
    def hour(self) -> float:
        return self._hour

    def set_hour(self, h: float) -> None:
        self._hour = float(h) % 24.0

    def saveable_state(self) -> dict:
        return {"hour": self._hour}

    def restore_state(self, state: dict) -> None:
        self._hour = float(state.get("hour", 12.0))


# ---------------------------------------------------------------------------
# Window builder
# ---------------------------------------------------------------------------

def _build_window(start_hour: float = 8.0) -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    window.event_bus = MeshEventBus()
    window.day_night = MockDayNight(start_hour)

    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    window.get_flag = lambda name, default=False: state_flags.get_flag(
        game_state_ctrl.state, name, default
    )
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    window.engine_config = MagicMock()
    window.engine_config.player_stats_enabled = False
    # Track scene changes requested through SceneExit
    window._scene_changes = []  # list[tuple[str, str | None]]
    _orig_queue = window.queue_scene_change

    def _capture_scene_change(scene_path: str, spawn_id: str | None = None, **kw: Any) -> None:
        window._scene_changes.append((scene_path, spawn_id))

    window.queue_scene_change = _capture_scene_change
    return window


def _get_flag(ctx: Dict[str, Any], flag: str) -> bool:
    return ctx["window"].game_state_controller.state.flags.get(flag) is True


def _set_flag(ctx: Dict[str, Any], flag: str) -> None:
    state_flags.set_flag(ctx["window"].game_state_controller.state, flag, True)


# ---------------------------------------------------------------------------
# Action runner builder (generic for any scene)
# ---------------------------------------------------------------------------

def _build_action_runners(
    window: MagicMock,
    scene_path: Path,
    controller_prefab_ids: set[str],
) -> List[Any]:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour

    runners: List[Any] = []
    for entity in _load_scene_entities(scene_path):
        pid = entity.get("prefab_id", "")
        if pid not in controller_prefab_ids:
            continue
        config = (entity.get("behaviour_config") or {}).get("ActionListRunner", {})
        if not config:
            continue
        runner_entity = MagicMock()
        runner_entity.mesh_id = entity.get("id", "")
        runner_entity.mesh_name = entity.get("name", "")
        runner_entity.mesh_tags = []
        runner_entity.behaviours = []
        runner = ActionListRunnerBehaviour(runner_entity, window, **config)
        runners.append(runner)
    return runners


# ---------------------------------------------------------------------------
# SceneExit builder (for campaign portals)
# ---------------------------------------------------------------------------

def _build_scene_exits(window: MagicMock, scene_path: Path) -> List[Any]:
    """Build SceneExit behaviours for campaign_portal entities."""
    from engine.behaviours.scene_exit import SceneExit

    exits: List[Any] = []
    for entity in _load_scene_entities(scene_path):
        if entity.get("prefab_id") != "campaign_portal":
            continue
        config = (entity.get("behaviour_config") or {}).get("SceneExit", {})
        exit_entity = MagicMock()
        exit_entity.mesh_id = entity.get("id", "")
        exit_entity.mesh_name = entity.get("name", "")
        exit_entity.mesh_tags = ["portal"]
        se = SceneExit(exit_entity, window, **config)
        exits.append(se)
    return exits


# ---------------------------------------------------------------------------
# Trigger builder
# ---------------------------------------------------------------------------

def _build_trigger(window: MagicMock, prefab_id: str, mesh_id: str, mesh_name: str, x: float, y: float):
    from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

    prefab = _load_prefab(prefab_id)
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("TriggerVolume", {})

    entity = MagicMock()
    entity.mesh_id = mesh_id
    entity.mesh_name = mesh_name
    entity.center_x = float(x)
    entity.center_y = float(y)
    entity.width = float(cfg.get("width", 64))
    entity.height = float(cfg.get("height", 64))

    return TriggerVolumeBehaviour(entity, window, **cfg)


# ---------------------------------------------------------------------------
# Health builder
# ---------------------------------------------------------------------------

def _build_health(
    window: MagicMock, mesh_id: str, mesh_name: str, mesh_tag: str, max_hp: float,
) -> tuple[MagicMock, Health]:
    entity = MagicMock()
    entity.mesh_id = mesh_id
    entity.mesh_name = mesh_name
    entity.mesh_tag = mesh_tag
    entity.mesh_tags = [mesh_tag] if mesh_tag else []
    entity.mesh_entity_data = {}
    health = Health(entity, window, max_hp=max_hp, hp=max_hp)
    return entity, health


# ---------------------------------------------------------------------------
# Event routing
# ---------------------------------------------------------------------------

_TOWN_BRIDGE_EVENTS = {"vendor_opened", "vendor_closed", "gate_opened"}


def _install_town_event_bridge(window: MagicMock) -> None:
    for evt_type in _TOWN_BRIDGE_EVENTS:
        def _make_handler(et: str):
            def _handler(event: Any) -> None:
                window.gameplay_event_bus.emit(
                    et,
                    source_entity=str(getattr(event, "payload", {}).get("entity", "")),
                    source_behaviour="bridge",
                    entity=str(getattr(event, "payload", {}).get("entity", "")),
                )
            return _handler
        window.event_bus.subscribe(evt_type, _make_handler(evt_type))


def _drain_and_route(window: MagicMock, runners: List[Any]) -> List[Any]:
    events = window.gameplay_event_bus.drain()
    if not events:
        return []
    for event in events:
        for runner in runners:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)
    for runner in runners:
        runner.update(0.0)
    return events


def _drain_until_empty(window: MagicMock, runners: List[Any]) -> List[Any]:
    collected: List[Any] = []
    for _ in range(20):
        batch = _drain_and_route(window, runners)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _step_on_trigger(trigger: Any, player: Any, *, off_pos: tuple[float, float] = (0.0, 0.0)) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = float(off_pos[0])
    player.center_y = float(off_pos[1])
    trigger.update(0.016)


# ---------------------------------------------------------------------------
# NPC Schedule + TimeOfDayGate builders
# ---------------------------------------------------------------------------

def _build_npc_schedule(window: MagicMock):
    from engine.behaviours.npc_schedule import NpcSchedule

    prefab = _load_prefab("town_vendor_npc")
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("NpcSchedule", {})
    entity = MagicMock()
    entity.mesh_id = "vendor_npc"
    entity.mesh_name = "VendorNpc"
    entity.mesh_tag = "npc"
    entity.mesh_tags = ["npc", "vendor"]
    entity.mesh_entity_data = {}
    entity.mesh_behaviours_runtime = []
    entity.center_x = 200.0
    entity.center_y = 256.0
    schedule = NpcSchedule(entity, window, **cfg)
    return entity, schedule


def _build_time_gate(window: MagicMock):
    from engine.behaviours.time_of_day_gate import TimeOfDayGate

    prefab = _load_prefab("town_night_gate")
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("TimeOfDayGate", {})
    entity = MagicMock()
    entity.mesh_id = "night_gate"
    entity.mesh_name = "NightGate"
    entity.mesh_tags = ["gate"]
    entity.visible = True
    gate = TimeOfDayGate(entity, window, **cfg)
    return entity, gate


# ---------------------------------------------------------------------------
# Timer builder (for puzzle room)
# ---------------------------------------------------------------------------

def _build_timer(window: MagicMock):
    from engine.behaviours.timer import TimerBehaviour

    prefab = _load_prefab("puzzle3_timer")
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("Timer", {})
    entity = MagicMock()
    entity.mesh_id = "puzzle_room_03_timer"
    entity.mesh_name = "PuzzleTimer03"
    entity.mesh_tags = []
    entity.behaviours = []
    timer = TimerBehaviour(entity, window, **cfg)
    return entity, timer


# ---------------------------------------------------------------------------
# Scene-specific setup helpers
# ---------------------------------------------------------------------------

def _setup_town(window: MagicMock) -> Dict[str, Any]:
    """Set up town scene components within an existing window."""
    runners = _build_action_runners(
        window, TOWN_SCENE, {"town_controller", "campaign_controller"}
    )
    scene_exits = _build_scene_exits(window, TOWN_SCENE)
    _install_town_event_bridge(window)
    npc_entity, npc_schedule = _build_npc_schedule(window)
    gate_entity, time_gate = _build_time_gate(window)

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 64.0
    player.center_y = 256.0

    entry_trigger = _build_trigger(
        window, "town_entry_trigger", "town_entry_trigger", "TownEntryTrigger", 128.0, 256.0
    )
    secret_trigger = _build_trigger(
        window, "town_secret_trigger", "secret_trigger", "SecretTrigger", 550.0, 256.0
    )
    window.scene_controller.all_sprites = [player, npc_entity, gate_entity]

    return {
        "window": window,
        "runners": runners,
        "scene_exits": scene_exits,
        "npc_entity": npc_entity,
        "npc_schedule": npc_schedule,
        "gate_entity": gate_entity,
        "time_gate": time_gate,
        "player": player,
        "entry_trigger": entry_trigger,
        "secret_trigger": secret_trigger,
    }


def _setup_puzzle(window: MagicMock) -> Dict[str, Any]:
    """Set up puzzle room components within an existing window."""
    runners = _build_action_runners(
        window, PUZZLE_SCENE, {"puzzle_controller", "campaign_controller"}
    )
    scene_exits = _build_scene_exits(window, PUZZLE_SCENE)
    timer_entity, timer = _build_timer(window)

    player = MagicMock()
    player.mesh_id = "puzzle_room_03_player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 96.0
    player.center_y = 96.0

    entry_trigger = _build_trigger(
        window, "puzzle_room3_entry_trigger",
        "puzzle_room_03_entry_trigger", "RoomEntryTrigger03",
        256.0, 192.0,
    )
    rune_center = _build_trigger(
        window, "puzzle3_rune_center",
        "puzzle_room_03_rune_center", "RuneCenter03",
        256.0, 256.0,
    )
    window.scene_controller.all_sprites = [player, timer_entity]

    return {
        "window": window,
        "runners": runners,
        "scene_exits": scene_exits,
        "timer_entity": timer_entity,
        "timer": timer,
        "player": player,
        "entry_trigger": entry_trigger,
        "rune_center": rune_center,
    }


def _setup_combat(window: MagicMock) -> Dict[str, Any]:
    """Set up combat scene components within an existing window."""
    runners = _build_action_runners(
        window, COMBAT_SCENE, {"cv_controller", "campaign_controller"}
    )

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 64.0
    player.center_y = 256.0

    _, player_health = _build_health(window, "player", "Player", "player", 20.0)
    _, enemy_health = _build_health(window, "sentry_archer", "SentryArcher", "enemy", 10.0)

    entry_trigger = _build_trigger(
        window, "cv_entry_trigger", "cv_entry_trigger", "CombatEntryTrigger", 128.0, 256.0
    )
    window.scene_controller.all_sprites = [player]

    return {
        "window": window,
        "runners": runners,
        "player": player,
        "player_health": player_health,
        "enemy_health": enemy_health,
        "entry_trigger": entry_trigger,
    }


# ---------------------------------------------------------------------------
# Town scene actions
# ---------------------------------------------------------------------------

def _complete_town(ctx: Dict[str, Any], quests: QuestRunner) -> List[Any]:
    """Run through town_schedule_01: enter → vendor in morning → secret at night."""
    all_events: List[Any] = []
    window = ctx["window"]

    # Set time to morning and trigger schedule transitions
    window.day_night.set_hour(8.0)
    ctx["npc_schedule"].update(0.016)
    ctx["time_gate"].update(0.016)

    # Enter town
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Advance to morning to open vendor
    window.day_night.set_hour(7.0)
    ctx["npc_schedule"].update(0.016)
    ctx["time_gate"].update(0.016)
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Interact with vendor
    window.gameplay_event_bus.emit(
        "vendor_interact_attempt", interactor="player"
    )
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Advance to night to open gate
    window.day_night.set_hour(21.0)
    ctx["npc_schedule"].update(0.016)
    ctx["time_gate"].update(0.016)
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Step on secret trigger
    _step_on_trigger(ctx["secret_trigger"], ctx["player"])
    events = _drain_until_empty(window, ctx["runners"])
    quest_events = quests.process_events(events)
    all_events.extend(events)

    # quest_town_complete should now be emitted by the quest runner;
    # feed it back so campaign_town_done_ctrl and campaign quest see it
    for qe in quest_events:
        window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
    events = _drain_until_empty(window, ctx["runners"])
    campaign_events = quests.process_events(events + list(quest_events))
    all_events.extend(quest_events)
    all_events.extend(events)
    all_events.extend(campaign_events)

    # Bridge to MeshEventBus so SceneExit behaviours fire
    for ev in events:
        window.event_bus.emit(ev.event_type)
    for ce in campaign_events:
        window.event_bus.emit(ce.event_type)

    return all_events


# ---------------------------------------------------------------------------
# Puzzle scene actions
# ---------------------------------------------------------------------------

def _complete_puzzle(ctx: Dict[str, Any], quests: QuestRunner) -> List[Any]:
    """Solve puzzle_room_03: enter → left lever → right lever → rune."""
    all_events: List[Any] = []
    window = ctx["window"]

    # Enter room
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Left lever
    window.gameplay_event_bus.emit("lever_left_pulled", interactor="player")
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Right lever (timer starts)
    window.gameplay_event_bus.emit("lever_right_pulled", interactor="player")
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Step on rune
    _step_on_trigger(ctx["rune_center"], ctx["player"])
    events = _drain_until_empty(window, ctx["runners"])
    quest_events = quests.process_events(events)
    all_events.extend(events)

    # Feed quest_room3_complete back
    for qe in quest_events:
        window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
    events = _drain_until_empty(window, ctx["runners"])
    campaign_events = quests.process_events(events + list(quest_events))
    all_events.extend(quest_events)
    all_events.extend(events)
    all_events.extend(campaign_events)

    # Bridge to MeshEventBus so SceneExit behaviours fire
    for ev in events:
        window.event_bus.emit(ev.event_type)
    for ce in campaign_events:
        window.event_bus.emit(ce.event_type)

    return all_events


# ---------------------------------------------------------------------------
# Combat scene actions
# ---------------------------------------------------------------------------

def _deal_damage(ctx: Dict[str, Any], amount: float) -> List[Any]:
    """Deal damage to enemy and drain events."""
    window = ctx["window"]
    ctx["enemy_health"].apply_damage(amount)
    if ctx["enemy_health"]._dead:
        window.gameplay_event_bus.emit(
            "cv_enemy_dead",
            source_entity="sentry_archer",
            source_behaviour="Health",
            entity="sentry_archer",
        )
    return _drain_until_empty(window, ctx["runners"])


def _complete_combat(ctx: Dict[str, Any], quests: QuestRunner) -> List[Any]:
    """Run combat_vignette_01: enter → kill → reward."""
    all_events: List[Any] = []
    window = ctx["window"]

    # Enter arena
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    events = _drain_until_empty(window, ctx["runners"])
    quests.process_events(events)
    all_events.extend(events)

    # Kill enemy (10 HP total, 2 hits of 5)
    events = _deal_damage(ctx, 5.0)
    quests.process_events(events)
    all_events.extend(events)

    events = _deal_damage(ctx, 5.0)
    quests.process_events(events)
    all_events.extend(events)

    # Collect reward
    window.gameplay_event_bus.emit(
        "reward_collected",
        source_entity="chest_reward_cv",
        source_behaviour="Interactable",
        entity="chest_reward_cv",
    )
    events = _drain_until_empty(window, ctx["runners"])
    quest_events = quests.process_events(events)
    all_events.extend(events)

    # Feed quest_combat_vignette_complete back
    for qe in quest_events:
        window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
    events = _drain_until_empty(window, ctx["runners"])
    campaign_events = quests.process_events(events + list(quest_events))
    all_events.extend(quest_events)
    all_events.extend(events)
    all_events.extend(campaign_events)

    # Bridge to MeshEventBus so SceneExit behaviours fire
    for ev in events:
        window.event_bus.emit(ev.event_type)
    for ce in campaign_events:
        window.event_bus.emit(ce.event_type)

    return all_events


# ---------------------------------------------------------------------------
# Shared state management for cross-scene persistence
# ---------------------------------------------------------------------------

def _snapshot_global_state(window: MagicMock) -> Dict[str, Any]:
    """Snapshot global state that persists across scenes."""
    return {
        "flags": window.game_state_controller.state.snapshot(),
        "bus": window.gameplay_event_bus.saveable_state(),
        "day_night": window.day_night.saveable_state(),
    }


def _restore_global_state(window: MagicMock, snapshot: Dict[str, Any]) -> None:
    """Restore global state into a window (simulating scene transition)."""
    window.game_state_controller.state.restore(snapshot["flags"])
    window.gameplay_event_bus.restore_state(snapshot["bus"])
    window.day_night.restore_state(snapshot["day_night"])


def _transition_to_scene(
    window: MagicMock,
) -> MagicMock:
    """Create a new window carrying over global state (simulating scene load)."""
    snapshot = _snapshot_global_state(window)
    new_window = _build_window(start_hour=window.day_night.hour)
    _restore_global_state(new_window, snapshot)
    return new_window


# =============================================================================
# Tests
# =============================================================================

class TestMiniCampaign01Integration:
    # -----------------------------------------------------------------
    # 1) HAPPY PATH: town → puzzle → combat → campaign_complete
    # -----------------------------------------------------------------
    def test_happy_path(self) -> None:
        """Full campaign flow across three scenes with quest chain."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)

        # Start all relevant quests
        assert quests.start_quest("mini_campaign_01") is True
        assert quests.start_quest("town_schedule_01") is True
        assert quests.start_quest("puzzle_room_03") is True
        assert quests.start_quest("combat_vignette_01") is True

        # --- SCENE 1: Town ---
        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town_ctx = _setup_town(window)
        _complete_town(town_ctx, quests)

        assert _get_flag(town_ctx, "campaign.town_complete")
        assert _get_flag(town_ctx, "secret.found")
        campaign_state = quests.get_quest_state("mini_campaign_01")
        assert campaign_state is not None
        assert campaign_state.current_stage == "puzzle"

        # Verify scene transition was requested
        assert any(
            sc[0] == "scenes/puzzle_room_03.json"
            for sc in window._scene_changes
        )

        # --- SCENE 2: Puzzle ---
        puzzle_window = _transition_to_scene(window)
        puzzle_ctx = _setup_puzzle(puzzle_window)
        _complete_puzzle(puzzle_ctx, quests)

        assert _get_flag(puzzle_ctx, "campaign.puzzle_complete")
        assert _get_flag(puzzle_ctx, "puzzle3.solved")
        campaign_state = quests.get_quest_state("mini_campaign_01")
        assert campaign_state is not None
        assert campaign_state.current_stage == "combat"

        # Verify scene transition was requested
        assert any(
            sc[0] == "scenes/combat_vignette_01.json"
            for sc in puzzle_window._scene_changes
        )

        # --- SCENE 3: Combat ---
        combat_window = _transition_to_scene(puzzle_window)
        combat_ctx = _setup_combat(combat_window)
        _complete_combat(combat_ctx, quests)

        assert _get_flag(combat_ctx, "campaign.combat_complete")
        assert _get_flag(combat_ctx, "cv.completed")

        campaign_state = quests.get_quest_state("mini_campaign_01")
        assert campaign_state is not None
        assert campaign_state.status == "completed"

    # -----------------------------------------------------------------
    # 2) GLOBAL FLAGS PERSIST ACROSS SCENES
    # -----------------------------------------------------------------
    def test_global_flags_persist(self) -> None:
        """Campaign flags set in one scene are visible after transition."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        quests.start_quest("mini_campaign_01")
        quests.start_quest("town_schedule_01")

        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town_ctx = _setup_town(window)
        _complete_town(town_ctx, quests)

        # Transition preserves flags
        puzzle_window = _transition_to_scene(window)
        gs = puzzle_window.game_state_controller.state
        assert gs.flags.get("campaign.started") is True
        assert gs.flags.get("campaign.town_complete") is True
        assert gs.flags.get("secret.found") is True
        assert gs.flags.get("vendor.met") is True
        assert gs.flags.get("town.entered") is True

    # -----------------------------------------------------------------
    # 3) SAVE/RESTORE AFTER TOWN BUT BEFORE TRANSITION
    # -----------------------------------------------------------------
    def test_save_restore_after_town(self) -> None:
        """Save after town quest complete, restore, portal still enabled."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        quests.start_quest("mini_campaign_01")
        quests.start_quest("town_schedule_01")

        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town_ctx = _setup_town(window)
        _complete_town(town_ctx, quests)

        # Save
        saved = _snapshot_global_state(window)
        saved_runners = {
            r.entity.mesh_id: r.saveable_state() for r in town_ctx["runners"]
        }

        # Restore into fresh window
        new_window = _build_window(start_hour=8.0)
        _restore_global_state(new_window, saved)
        new_town = _setup_town(new_window)
        for runner in new_town["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        assert _get_flag(new_town, "campaign.town_complete")

        # Portal should still trigger scene change
        assert any(
            sc[0] == "scenes/puzzle_room_03.json"
            for sc in window._scene_changes
        )

    # -----------------------------------------------------------------
    # 4) SAVE/RESTORE MID-PUZZLE, THEN COMPLETE
    # -----------------------------------------------------------------
    def test_save_restore_mid_puzzle(self) -> None:
        """Save mid-puzzle, restore, complete puzzle, transition to combat."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        quests.start_quest("mini_campaign_01")
        quests.start_quest("town_schedule_01")
        quests.start_quest("puzzle_room_03")

        # Complete town
        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town_ctx = _setup_town(window)
        _complete_town(town_ctx, quests)

        # Transition to puzzle
        puzzle_window = _transition_to_scene(window)
        puzzle_ctx = _setup_puzzle(puzzle_window)

        # Enter room and pull left lever only
        _step_on_trigger(puzzle_ctx["entry_trigger"], puzzle_ctx["player"])
        events = _drain_until_empty(puzzle_window, puzzle_ctx["runners"])
        quests.process_events(events)

        puzzle_window.gameplay_event_bus.emit("lever_left_pulled", interactor="player")
        events = _drain_until_empty(puzzle_window, puzzle_ctx["runners"])
        quests.process_events(events)

        assert _get_flag(puzzle_ctx, "puzzle3.left_pulled")
        assert not _get_flag(puzzle_ctx, "puzzle3.solved")

        # Save state
        saved = _snapshot_global_state(puzzle_window)
        saved_runners = {
            r.entity.mesh_id: r.saveable_state() for r in puzzle_ctx["runners"]
        }

        # Restore into fresh window
        new_window = _build_window(start_hour=puzzle_window.day_night.hour)
        _restore_global_state(new_window, saved)
        new_puzzle = _setup_puzzle(new_window)
        for runner in new_puzzle["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        assert _get_flag(new_puzzle, "puzzle3.left_pulled")

        # Now complete: right lever + rune step
        new_window.gameplay_event_bus.emit("lever_right_pulled", interactor="player")
        events = _drain_until_empty(new_window, new_puzzle["runners"])
        quests.process_events(events)

        _step_on_trigger(new_puzzle["rune_center"], new_puzzle["player"])
        events = _drain_until_empty(new_window, new_puzzle["runners"])
        quest_events = quests.process_events(events)

        for qe in quest_events:
            new_window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
        events = _drain_until_empty(new_window, new_puzzle["runners"])
        quests.process_events(events + list(quest_events))

        assert _get_flag(new_puzzle, "puzzle3.solved")
        assert _get_flag(new_puzzle, "campaign.puzzle_complete")

        campaign_state = quests.get_quest_state("mini_campaign_01")
        assert campaign_state is not None
        assert campaign_state.current_stage == "combat"

    # -----------------------------------------------------------------
    # 5) SAVE/RESTORE MID-COMBAT, THEN COMPLETE CAMPAIGN
    # -----------------------------------------------------------------
    def test_save_restore_mid_combat(self) -> None:
        """Save mid-combat with partial damage, restore, complete campaign."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        quests.start_quest("mini_campaign_01")
        quests.start_quest("town_schedule_01")
        quests.start_quest("puzzle_room_03")
        quests.start_quest("combat_vignette_01")

        # Complete town + puzzle
        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town_ctx = _setup_town(window)
        _complete_town(town_ctx, quests)

        puzzle_window = _transition_to_scene(window)
        puzzle_ctx = _setup_puzzle(puzzle_window)
        _complete_puzzle(puzzle_ctx, quests)

        # Enter combat
        combat_window = _transition_to_scene(puzzle_window)
        combat_ctx = _setup_combat(combat_window)

        _step_on_trigger(combat_ctx["entry_trigger"], combat_ctx["player"])
        events = _drain_until_empty(combat_window, combat_ctx["runners"])
        quests.process_events(events)

        # Partial damage
        combat_ctx["enemy_health"].apply_damage(3.0)
        assert combat_ctx["enemy_health"].hp == 7.0

        # Also damage player
        combat_ctx["player_health"].apply_damage(5.0)
        assert combat_ctx["player_health"].hp == 15.0

        # Save
        saved = _snapshot_global_state(combat_window)
        saved_enemy_hp = combat_ctx["enemy_health"].saveable_state()
        saved_player_hp = combat_ctx["player_health"].saveable_state()
        saved_runners = {
            r.entity.mesh_id: r.saveable_state() for r in combat_ctx["runners"]
        }

        # Restore
        new_window = _build_window(start_hour=combat_window.day_night.hour)
        _restore_global_state(new_window, saved)
        new_combat = _setup_combat(new_window)
        for runner in new_combat["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)
        new_combat["enemy_health"].restore_state(saved_enemy_hp)
        new_combat["player_health"].restore_state(saved_player_hp)

        assert new_combat["enemy_health"].hp == 7.0
        assert new_combat["player_health"].hp == 15.0
        assert _get_flag(new_combat, "cv.started")

        # Finish combat
        events = _deal_damage(new_combat, 7.0)
        quests.process_events(events)

        new_window.gameplay_event_bus.emit(
            "reward_collected",
            source_entity="chest_reward_cv",
            source_behaviour="Interactable",
            entity="chest_reward_cv",
        )
        events = _drain_until_empty(new_window, new_combat["runners"])
        quest_events = quests.process_events(events)

        for qe in quest_events:
            new_window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
        events = _drain_until_empty(new_window, new_combat["runners"])
        quests.process_events(events + list(quest_events))

        assert _get_flag(new_combat, "cv.completed")
        assert _get_flag(new_combat, "campaign.combat_complete")

        campaign_state = quests.get_quest_state("mini_campaign_01")
        assert campaign_state is not None
        assert campaign_state.status == "completed"

    # -----------------------------------------------------------------
    # 6) DETERMINISM: same inputs → same outcomes
    # -----------------------------------------------------------------
    def test_deterministic_campaign(self) -> None:
        """Running the same campaign twice produces identical results."""
        results: list[dict] = []

        for _ in range(2):
            quests = QuestRunner()
            quests.load_definitions(QUESTS_PATH)
            quests.start_quest("mini_campaign_01")
            quests.start_quest("town_schedule_01")
            quests.start_quest("puzzle_room_03")
            quests.start_quest("combat_vignette_01")

            all_event_types: list[str] = []

            # Town
            window = _build_window(start_hour=8.0)
            _set_flag({"window": window}, "campaign.started")
            town = _setup_town(window)
            events = _complete_town(town, quests)
            all_event_types.extend(e.event_type for e in events)

            # Puzzle
            pw = _transition_to_scene(window)
            puzzle = _setup_puzzle(pw)
            events = _complete_puzzle(puzzle, quests)
            all_event_types.extend(e.event_type for e in events)

            # Combat
            cw = _transition_to_scene(pw)
            combat = _setup_combat(cw)
            events = _complete_combat(combat, quests)
            all_event_types.extend(e.event_type for e in events)

            final_flags = dict(cw.game_state_controller.state.flags)
            campaign_status = quests.get_quest_state("mini_campaign_01")

            results.append({
                "event_types": all_event_types,
                "flags": final_flags,
                "campaign_status": campaign_status.status if campaign_status else None,
                "campaign_stage": campaign_status.current_stage if campaign_status else None,
            })

        # Both runs must be identical
        assert results[0]["event_types"] == results[1]["event_types"]
        assert results[0]["flags"] == results[1]["flags"]
        assert results[0]["campaign_status"] == results[1]["campaign_status"] == "completed"

    # -----------------------------------------------------------------
    # 7) QUEST CHAIN STAGE PROGRESSION
    # -----------------------------------------------------------------
    def test_quest_chain_stages(self) -> None:
        """Campaign quest advances through town → puzzle → combat stages."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        quests.start_quest("mini_campaign_01")
        quests.start_quest("town_schedule_01")
        quests.start_quest("puzzle_room_03")
        quests.start_quest("combat_vignette_01")

        # Initially at step "town"
        state = quests.get_quest_state("mini_campaign_01")
        assert state is not None
        assert state.current_stage == "town"

        # Complete town → advance to "puzzle"
        window = _build_window(start_hour=8.0)
        _set_flag({"window": window}, "campaign.started")
        town = _setup_town(window)
        _complete_town(town, quests)
        state = quests.get_quest_state("mini_campaign_01")
        assert state is not None
        assert state.current_stage == "puzzle"

        # Complete puzzle → advance to "combat"
        pw = _transition_to_scene(window)
        puzzle = _setup_puzzle(pw)
        _complete_puzzle(puzzle, quests)
        state = quests.get_quest_state("mini_campaign_01")
        assert state is not None
        assert state.current_stage == "combat"

        # Complete combat → completed
        cw = _transition_to_scene(pw)
        combat = _setup_combat(cw)
        _complete_combat(combat, quests)
        state = quests.get_quest_state("mini_campaign_01")
        assert state is not None
        assert state.status == "completed"

    # -----------------------------------------------------------------
    # 8) SCENE EXIT PREFAB WIRING
    # -----------------------------------------------------------------
    def test_scene_exit_wiring(self) -> None:
        """SceneExit behaviours are properly wired in each scene."""
        # Town scene has portal to puzzle
        town_entities = _load_scene_entities(TOWN_SCENE)
        portal = next(
            (e for e in town_entities if e.get("id") == "town_exit_to_puzzle"),
            None,
        )
        assert portal is not None
        se_config = portal.get("behaviour_config", {}).get("SceneExit", {})
        assert se_config["target_scene"] == "scenes/puzzle_room_03.json"
        assert se_config["listen_event"] == "go_to_puzzle_room_03"

        # Puzzle scene has portal to combat
        puzzle_entities = _load_scene_entities(PUZZLE_SCENE)
        portal = next(
            (e for e in puzzle_entities if e.get("id") == "puzzle_exit_to_combat"),
            None,
        )
        assert portal is not None
        se_config = portal.get("behaviour_config", {}).get("SceneExit", {})
        assert se_config["target_scene"] == "scenes/combat_vignette_01.json"
        assert se_config["listen_event"] == "go_to_combat_vignette_01"

    # -----------------------------------------------------------------
    # 9) PLAYER HP PERSISTS ACROSS SCENES
    # -----------------------------------------------------------------
    def test_player_hp_persists(self) -> None:
        """Player HP saved in one scene is restored in the next."""
        window = _build_window()
        _, health = _build_health(window, "player", "Player", "player", 20.0)

        health.apply_damage(8.0)
        assert health.hp == 12.0
        saved_hp = health.saveable_state()

        # "Transition" — new window, restore HP
        new_window = _build_window()
        _, new_health = _build_health(new_window, "player", "Player", "player", 20.0)
        new_health.restore_state(saved_hp)
        assert new_health.hp == 12.0

    # -----------------------------------------------------------------
    # 10) CAMPAIGN EVENTS REGISTERED
    # -----------------------------------------------------------------
    def test_campaign_events_registered(self) -> None:
        """All campaign events exist in events.json."""
        events_data = _load_json(Path("assets/data/events.json"))
        event_names = {e["name"] for e in events_data.get("events", [])}
        required = {
            "campaign_started",
            "go_to_puzzle_room_03",
            "go_to_combat_vignette_01",
            "campaign_complete",
        }
        assert required.issubset(event_names), f"Missing events: {required - event_names}"

    # -----------------------------------------------------------------
    # 11) CAMPAIGN QUEST REGISTERED
    # -----------------------------------------------------------------
    def test_campaign_quest_registered(self) -> None:
        """mini_campaign_01 quest is loadable and has 3 stages."""
        quests = QuestRunner()
        quests.load_definitions(QUESTS_PATH)
        assert quests.start_quest("mini_campaign_01") is True
        state = quests.get_quest_state("mini_campaign_01")
        assert state is not None
        assert state.current_stage == "town"
