"""Integration tests for the Town Schedule 01 content wiring.

Covers:
- NpcSchedule transitions happen deterministically at expected times
- Vendor interact works only while open (morning)
- TimeOfDayGate opens only at night; secret trigger gated behind it
- Save/restore mid-day preserves time, flags, schedule, gate, quest
- Determinism: same dt schedule -> identical events/flags
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.behaviours.npc_schedule import NpcSchedule
from engine.behaviours.time_of_day_gate import TimeOfDayGate
from engine.events import MeshEventBus
from engine.game_state_controller import GameState
from engine.gameplay_event_bus import GameplayEventBus
from engine.quest_runtime.runner import QuestRunner
from engine.state_runtime import flags as state_flags

SCENE_PATH = Path("scenes/town_schedule_01.json")
PREFABS_PATH = Path("assets/prefabs.json")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prefab(prefab_id: str) -> Dict[str, Any]:
    prefabs = _load_json(PREFABS_PATH)
    for entry in prefabs:
        if entry.get("id") == prefab_id:
            return entry
    raise AssertionError(f"Prefab '{prefab_id}' not found")


def _load_scene_entities() -> List[Dict[str, Any]]:
    payload = _load_json(SCENE_PATH)
    return list(payload.get("entities", []))


# ---------------------------------------------------------------------------
# Mock DayNight controller — provides .hour for NpcSchedule & TimeOfDayGate
# ---------------------------------------------------------------------------

class MockDayNight:
    """Simple deterministic clock with a settable hour."""

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
# Window / environment builders
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
    return window


def _build_action_runners(window: MagicMock) -> List[Any]:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour

    runners: List[Any] = []
    for entity in _load_scene_entities():
        if entity.get("prefab_id") != "town_controller":
            continue
        config = (entity.get("behaviour_config") or {}).get("ActionListRunner", {})
        runner_entity = MagicMock()
        runner_entity.mesh_id = entity.get("id", "")
        runner_entity.mesh_name = entity.get("name", "")
        runner_entity.mesh_tags = []
        runner_entity.behaviours = []
        runner = ActionListRunnerBehaviour(runner_entity, window, **config)
        runners.append(runner)
    return runners


def _build_npc_schedule(window: MagicMock) -> tuple[MagicMock, NpcSchedule]:
    """Build vendor NPC with NpcSchedule behaviour."""
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


def _build_time_gate(window: MagicMock) -> tuple[MagicMock, TimeOfDayGate]:
    """Build the night gate with TimeOfDayGate behaviour."""
    prefab = _load_prefab("town_night_gate")
    cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("TimeOfDayGate", {})

    entity = MagicMock()
    entity.mesh_id = "night_gate"
    entity.mesh_name = "NightGate"
    entity.mesh_tags = ["gate"]
    entity.visible = True

    gate = TimeOfDayGate(entity, window, **cfg)
    return entity, gate


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
# Event routing: bridge NpcSchedule/TimeOfDayGate events (MeshEventBus)
# into GameplayEventBus so ActionListRunners pick them up.
# ---------------------------------------------------------------------------

_BRIDGE_EVENTS = {"vendor_opened", "vendor_closed", "gate_opened"}


def _install_event_bridge(window: MagicMock) -> None:
    """Subscribe to key MeshEventBus events and re-emit on GameplayEventBus."""
    for evt_type in _BRIDGE_EVENTS:
        def _make_handler(et: str):
            def _handler(event):
                window.gameplay_event_bus.emit(
                    et,
                    source_entity=str(getattr(event, "payload", {}).get("entity", "")),
                    source_behaviour="bridge",
                    entity=str(getattr(event, "payload", {}).get("entity", "")),
                )
            return _handler
        window.event_bus.subscribe(evt_type, _make_handler(evt_type))


# ---------------------------------------------------------------------------
# Event drain / routing (same pattern as other integration tests)
# ---------------------------------------------------------------------------

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
    for _ in range(12):
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
# Full town setup
# ---------------------------------------------------------------------------

def _setup_town(start_hour: float = 8.0):
    """Build the full town fixture and return all components."""
    window = _build_window(start_hour)
    runners = _build_action_runners(window)
    _install_event_bridge(window)
    vendor_entity, npc_schedule = _build_npc_schedule(window)
    gate_entity, time_gate = _build_time_gate(window)

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 0.0
    player.center_y = 0.0

    entry_trigger = _build_trigger(
        window, "town_entry_trigger",
        "town_entry_trigger", "TownEntryTrigger",
        128.0, 256.0,
    )
    secret_trigger = _build_trigger(
        window, "town_secret_trigger",
        "secret_trigger", "SecretTrigger",
        550.0, 256.0,
    )

    window.scene_controller.all_sprites = [player, vendor_entity, gate_entity]

    return {
        "window": window,
        "runners": runners,
        "player": player,
        "vendor_entity": vendor_entity,
        "npc_schedule": npc_schedule,
        "gate_entity": gate_entity,
        "time_gate": time_gate,
        "entry_trigger": entry_trigger,
        "secret_trigger": secret_trigger,
    }


def _set_time(ctx: Dict[str, Any], hour: float) -> List[Any]:
    """Set clock to hour, update schedule + gate, and drain cascaded events."""
    ctx["window"].day_night.set_hour(hour)
    ctx["npc_schedule"].update(0.0)
    ctx["time_gate"].update(0.0)
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _enter_town(ctx: Dict[str, Any]) -> List[Any]:
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _interact_vendor(ctx: Dict[str, Any]) -> List[Any]:
    """Emit vendor_interact_attempt on gameplay_event_bus and drain."""
    ctx["window"].gameplay_event_bus.emit(
        "vendor_interact_attempt",
        source_entity="vendor_npc",
        source_behaviour="Interactable",
        interactor="player",
    )
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _step_on_secret(ctx: Dict[str, Any]) -> List[Any]:
    _step_on_trigger(ctx["secret_trigger"], ctx["player"])
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _get_flag(ctx: Dict[str, Any], flag: str) -> bool:
    return ctx["window"].game_state_controller.state.flags.get(flag) is True


# =============================================================================
# Tests
# =============================================================================

class TestTownSchedule01Integration:
    # -----------------------------------------------------------------
    # SCHEDULE TRANSITIONS
    # -----------------------------------------------------------------
    def test_schedule_transitions_deterministic(self) -> None:
        """Morning/afternoon/night transitions emit expected events."""
        ctx = _setup_town(start_hour=5.0)  # before morning

        # Transition to morning (hour=8)
        events = _set_time(ctx, 8.0)
        assert any(e.event_type == "vendor_opened" for e in events)
        assert _get_flag(ctx, "vendor.open")
        assert ctx["vendor_entity"].center_x == 200.0

        # Transition to afternoon (hour=14)
        events = _set_time(ctx, 14.0)
        assert any(e.event_type == "vendor_closed" for e in events)
        assert not _get_flag(ctx, "vendor.open")
        assert ctx["vendor_entity"].center_x == 400.0

        # Transition to night (hour=21)
        events = _set_time(ctx, 21.0)
        assert ctx["vendor_entity"].center_x == 100.0
        # No enter_event on night schedule block — no new vendor event
        assert not _get_flag(ctx, "vendor.open")

    # -----------------------------------------------------------------
    # VENDOR INTERACTION: OPEN VS CLOSED
    # -----------------------------------------------------------------
    def test_vendor_interact_only_when_open(self) -> None:
        """Vendor interaction succeeds during morning, fails during afternoon."""
        ctx = _setup_town(start_hour=8.0)
        _enter_town(ctx)

        # Ensure morning transition fires (set to 8 again to trigger event)
        _set_time(ctx, 8.0)
        assert _get_flag(ctx, "vendor.open")

        # Interact while open → vendor.met = True
        events = _interact_vendor(ctx)
        assert _get_flag(ctx, "vendor.met")
        assert any(e.event_type == "vendor_interacted" for e in events)

        # Move to afternoon — vendor closes
        _set_time(ctx, 14.0)
        assert not _get_flag(ctx, "vendor.open")

        # Clear vendor.met to test re-interaction
        ctx["window"].game_state_controller.state.flags.pop("vendor.met", None)

        # Interact while closed → vendor.met stays False
        events = _interact_vendor(ctx)
        assert not _get_flag(ctx, "vendor.met")
        assert not any(e.event_type == "vendor_interacted" for e in events)

    # -----------------------------------------------------------------
    # GATE + SECRET AT NIGHT
    # -----------------------------------------------------------------
    def test_gate_opens_only_at_night(self) -> None:
        """TimeOfDayGate is inactive during day, active during night."""
        ctx = _setup_town(start_hour=12.0)

        # During day — gate inactive
        assert not ctx["time_gate"]._active
        assert not _get_flag(ctx, "gate.open")

        # Move to night (hour=21) — gate opens
        events = _set_time(ctx, 21.0)
        assert ctx["time_gate"]._active
        assert any(e.event_type == "gate_opened" for e in events)
        assert _get_flag(ctx, "gate.open")

    def test_secret_only_at_night(self) -> None:
        """Secret trigger only registers when gate is open (night)."""
        ctx = _setup_town(start_hour=12.0)
        _enter_town(ctx)

        # During day — step on secret trigger
        _step_on_secret(ctx)
        assert not _get_flag(ctx, "secret.found")

        # Move to night — gate opens
        _set_time(ctx, 21.0)
        assert _get_flag(ctx, "gate.open")

        # Now step on secret
        # Need to re-create the trigger since one_shot consumed it
        ctx["secret_trigger"] = _build_trigger(
            ctx["window"], "town_secret_trigger",
            "secret_trigger", "SecretTrigger",
            550.0, 256.0,
        )
        events = _step_on_secret(ctx)
        assert _get_flag(ctx, "secret.found")

    # -----------------------------------------------------------------
    # FULL QUEST SUCCESS PATH
    # -----------------------------------------------------------------
    def test_full_quest_path(self) -> None:
        """Enter (morning) → interact vendor → night → secret → quest complete."""
        ctx = _setup_town(start_hour=5.0)
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("town_schedule_01") is True

        # Set to morning, enter town
        events = _set_time(ctx, 8.0)
        quests.process_events(events)
        events = _enter_town(ctx)
        quests.process_events(events)
        assert _get_flag(ctx, "town.entered")
        state = quests.get_quest_state("town_schedule_01")
        assert state is not None
        assert state.current_stage == "step1"

        # Interact with vendor during morning
        events = _interact_vendor(ctx)
        quests.process_events(events)
        assert _get_flag(ctx, "vendor.met")
        state = quests.get_quest_state("town_schedule_01")
        assert state is not None
        assert state.current_stage == "step2"

        # Advance to night — gate opens
        events = _set_time(ctx, 21.0)
        quests.process_events(events)
        assert _get_flag(ctx, "gate.open")

        # Step on secret
        events = _step_on_secret(ctx)
        emitted = quests.process_events(events)
        assert _get_flag(ctx, "secret.found")
        assert any(e.event_type == "quest_town_complete" for e in emitted)
        state = quests.get_quest_state("town_schedule_01")
        assert state is not None
        assert state.status == "completed"

    # -----------------------------------------------------------------
    # SAVE / RESTORE MID-DAY
    # -----------------------------------------------------------------
    def test_save_restore_mid_day(self) -> None:
        """Save during morning after vendor interaction, restore, advance to night → complete."""
        ctx = _setup_town(start_hour=5.0)
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        quests.start_quest("town_schedule_01")

        # Morning: enter + interact
        _set_time(ctx, 8.0)
        events = _enter_town(ctx)
        quests.process_events(events)
        events = _interact_vendor(ctx)
        quests.process_events(events)
        assert _get_flag(ctx, "vendor.met")

        # --- Save ---
        saved_flags = ctx["window"].game_state_controller.state.snapshot()
        saved_bus = ctx["window"].gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in ctx["runners"]}
        saved_clock = ctx["window"].day_night.saveable_state()

        # --- Restore into fresh town ---
        new_ctx = _setup_town(start_hour=8.0)
        new_ctx["window"].game_state_controller.state.restore(saved_flags)
        new_ctx["window"].gameplay_event_bus.restore_state(saved_bus)
        for runner in new_ctx["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)
        new_ctx["window"].day_night.restore_state(saved_clock)

        # Verify preserved state
        assert _get_flag(new_ctx, "town.entered")
        assert _get_flag(new_ctx, "vendor.met")
        assert new_ctx["window"].day_night.hour == 8.0

        # Advance to night in restored context
        events = _set_time(new_ctx, 21.0)
        quests.process_events(events)
        assert _get_flag(new_ctx, "gate.open")

        # Find secret
        events = _step_on_secret(new_ctx)
        emitted = quests.process_events(events)
        assert _get_flag(new_ctx, "secret.found")
        assert any(e.event_type == "quest_town_complete" for e in emitted)
        state = quests.get_quest_state("town_schedule_01")
        assert state is not None
        assert state.status == "completed"

    # -----------------------------------------------------------------
    # DETERMINISM
    # -----------------------------------------------------------------
    def test_deterministic_time_progression(self) -> None:
        """Same hour sequence → identical events and flags both runs."""
        hour_schedule = [8.0, 14.0, 21.0]

        results: list[dict] = []
        for _ in range(2):
            ctx = _setup_town(start_hour=5.0)
            _enter_town(ctx)

            all_events: list[str] = []
            for h in hour_schedule:
                events = _set_time(ctx, h)
                all_events.extend(e.event_type for e in events)

            results.append({
                "events": all_events,
                "flags": dict(ctx["window"].game_state_controller.state.flags),
                "vendor_x": ctx["vendor_entity"].center_x,
            })

        assert results[0]["events"] == results[1]["events"]
        assert results[0]["flags"] == results[1]["flags"]
        assert results[0]["vendor_x"] == results[1]["vendor_x"]

    # -----------------------------------------------------------------
    # NPC POSITION TRACKING
    # -----------------------------------------------------------------
    def test_npc_position_follows_schedule(self) -> None:
        """Vendor entity position updates with schedule transitions."""
        ctx = _setup_town(start_hour=5.0)

        # Morning → stall (200, 256)
        _set_time(ctx, 8.0)
        assert ctx["vendor_entity"].center_x == 200.0

        # Afternoon → plaza (400, 256)
        _set_time(ctx, 14.0)
        assert ctx["vendor_entity"].center_x == 400.0

        # Night → home (100, 256)
        _set_time(ctx, 21.0)
        assert ctx["vendor_entity"].center_x == 100.0

        # Back to morning → stall (200, 256)
        _set_time(ctx, 8.0)
        assert ctx["vendor_entity"].center_x == 200.0
