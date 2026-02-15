"""Headless campaign replay harness.

Runs a deterministic scripted playthrough of a campaign using the same
infrastructure as the integration tests, records digest traces at each
milestone and checkpoint debug bundles, and supports diffing two runs to
detect nondeterminism regressions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from engine.behaviours.health import Health
from engine.events import MeshEventBus
from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.save_runtime.digest import DigestTracker, compute_world_digest
from engine.state_runtime import flags as state_flags

# ---------------------------------------------------------------------------
# Path defaults
# ---------------------------------------------------------------------------

_DEFAULT_SCRIPT_DIR = Path("tests/fixtures/campaign_scripts")
_PREFABS_PATH = Path("assets/prefabs.json")
_QUESTS_PATH = Path("assets/data/quests.json")


# ---------------------------------------------------------------------------
# Helpers (adapted from test_mini_campaign_01_integration)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    result: Any = json.loads(path.read_text(encoding="utf-8"))
    return result


def _load_prefab(prefab_id: str) -> Dict[str, Any]:
    prefabs = _load_json(_PREFABS_PATH)
    for entry in prefabs:
        if entry.get("id") == prefab_id:
            result: Dict[str, Any] = entry
            return result
    raise ValueError(f"Prefab '{prefab_id}' not found")


def _load_scene_entities(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    return list(payload.get("entities", []))


class _MockDayNight:
    def __init__(self, start_hour: float = 8.0) -> None:
        self._hour = float(start_hour) % 24.0

    @property
    def hour(self) -> float:
        return self._hour

    def set_hour(self, h: float) -> None:
        self._hour = float(h) % 24.0

    def saveable_state(self) -> dict[str, Any]:
        return {"hour": self._hour}

    def restore_state(self, state: dict[str, Any]) -> None:
        self._hour = float(state.get("hour", 12.0))


def _build_window(start_hour: float = 8.0) -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    window.event_bus = MeshEventBus()
    window.day_night = _MockDayNight(start_hour)
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
    window._scene_changes = []  # list[tuple[str, str | None]]

    def _capture(scene_path: str, spawn_id: str | None = None, **kw: Any) -> None:
        window._scene_changes.append((scene_path, spawn_id))

    window.queue_scene_change = _capture
    return window


def _build_action_runners(
    window: MagicMock, scene_path: Path, controller_prefab_ids: set[str],
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


def _build_scene_exits(window: MagicMock, scene_path: Path) -> List[Any]:
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


def _build_trigger(window: MagicMock, prefab_id: str, mesh_id: str, mesh_name: str, x: float, y: float) -> Any:
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
    return list(events)


def _drain_until_empty(window: MagicMock, runners: List[Any]) -> List[Any]:
    collected: List[Any] = []
    for _ in range(20):
        batch = _drain_and_route(window, runners)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _step_on_trigger(trigger: Any, player: Any) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = 0.0
    player.center_y = 0.0
    trigger.update(0.016)


def _process_quest_events(
    window: MagicMock, runners: List[Any], quests: QuestRunner,
    events: List[Any],
) -> List[Any]:
    """Full quest-event routing cycle used after quest-completing actions."""
    quest_events = quests.process_events(events)
    all_extra: List[Any] = list(quest_events)
    # Re-emit quest events on gameplay bus for ActionListRunners
    for qe in quest_events:
        window.gameplay_event_bus.emit(qe.event_type, **(qe.payload or {}))
    drained = _drain_until_empty(window, runners)
    campaign_events = quests.process_events(drained + list(quest_events))
    all_extra.extend(drained)
    all_extra.extend(campaign_events)
    # Bridge to MeshEventBus so SceneExit behaviours fire
    for ev in drained:
        window.event_bus.emit(ev.event_type)
    for ce in campaign_events:
        window.event_bus.emit(ce.event_type)
    return all_extra


# ---------------------------------------------------------------------------
# Scene setup factories
# ---------------------------------------------------------------------------

def _setup_town(window: MagicMock) -> Dict[str, Any]:
    from engine.behaviours.npc_schedule import NpcSchedule
    from engine.behaviours.time_of_day_gate import TimeOfDayGate

    runners = _build_action_runners(
        window, Path("scenes/town_schedule_01.json"),
        {"town_controller", "campaign_controller", "town_schedule_ctrl"},
    )
    scene_exits = _build_scene_exits(window, Path("scenes/town_schedule_01.json"))
    _install_town_event_bridge(window)

    # NPC schedule
    prefab = _load_prefab("town_vendor_npc")
    npc_cfg = prefab.get("entity", {}).get("behaviour_config", {}).get("NpcSchedule", {})
    npc_entity = MagicMock()
    npc_entity.mesh_id = "vendor_npc"
    npc_entity.mesh_name = "VendorNpc"
    npc_entity.mesh_tag = "npc"
    npc_entity.mesh_tags = ["npc", "vendor"]
    npc_entity.mesh_entity_data = {}
    npc_entity.mesh_behaviours_runtime = []
    npc_entity.center_x = 200.0
    npc_entity.center_y = 256.0
    npc_schedule = NpcSchedule(npc_entity, window, **npc_cfg)

    # Time gate
    gate_prefab = _load_prefab("town_night_gate")
    gate_cfg = gate_prefab.get("entity", {}).get("behaviour_config", {}).get("TimeOfDayGate", {})
    gate_entity = MagicMock()
    gate_entity.mesh_id = "night_gate"
    gate_entity.mesh_name = "NightGate"
    gate_entity.mesh_tags = ["gate"]
    gate_entity.visible = True
    time_gate = TimeOfDayGate(gate_entity, window, **gate_cfg)

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 64.0
    player.center_y = 256.0

    entry_trigger = _build_trigger(
        window, "town_entry_trigger", "town_entry_trigger", "TownEntryTrigger", 128.0, 256.0,
    )
    secret_trigger = _build_trigger(
        window, "town_secret_trigger", "secret_trigger", "SecretTrigger", 550.0, 256.0,
    )
    window.scene_controller.all_sprites = [player, npc_entity, gate_entity]

    return {
        "window": window,
        "runners": runners,
        "scene_exits": scene_exits,
        "npc_schedule": npc_schedule,
        "time_gate": time_gate,
        "player": player,
        "entry_trigger": entry_trigger,
        "secret_trigger": secret_trigger,
        "triggers": {
            "town_entry_trigger": entry_trigger,
            "town_secret_trigger": secret_trigger,
        },
    }


def _setup_puzzle(window: MagicMock) -> Dict[str, Any]:
    from engine.behaviours.timer import TimerBehaviour

    runners = _build_action_runners(
        window, Path("scenes/puzzle_room_03.json"),
        {"puzzle_controller", "campaign_controller", "puzzle_room_ctrl"},
    )
    scene_exits = _build_scene_exits(window, Path("scenes/puzzle_room_03.json"))

    timer_prefab = _load_prefab("puzzle3_timer")
    timer_cfg = timer_prefab.get("entity", {}).get("behaviour_config", {}).get("Timer", {})
    timer_entity = MagicMock()
    timer_entity.mesh_id = "puzzle_room_03_timer"
    timer_entity.mesh_name = "PuzzleTimer03"
    timer_entity.mesh_tags = []
    timer_entity.behaviours = []
    timer_beh = TimerBehaviour(timer_entity, window, **timer_cfg)

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
        "timer": timer_beh,
        "player": player,
        "entry_trigger": entry_trigger,
        "rune_center": rune_center,
        "triggers": {
            "puzzle_entry_trigger": entry_trigger,
            "rune_center": rune_center,
        },
    }


def _setup_combat(window: MagicMock) -> Dict[str, Any]:
    runners = _build_action_runners(
        window, Path("scenes/combat_vignette_01.json"),
        {"cv_controller", "campaign_controller"},
    )
    scene_exits = _build_scene_exits(window, Path("scenes/combat_vignette_01.json"))

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 64.0
    player.center_y = 256.0

    _, player_health = _build_health(window, "player", "Player", "player", 20.0)
    _, enemy_health = _build_health(window, "sentry_archer", "SentryArcher", "enemy", 10.0)

    entry_trigger = _build_trigger(
        window, "cv_entry_trigger", "cv_entry_trigger", "CombatEntryTrigger", 128.0, 256.0,
    )
    window.scene_controller.all_sprites = [player]

    return {
        "window": window,
        "runners": runners,
        "scene_exits": scene_exits,
        "player": player,
        "player_health": player_health,
        "enemy_health": enemy_health,
        "entry_trigger": entry_trigger,
        "triggers": {
            "cv_entry_trigger": entry_trigger,
        },
    }


def _setup_episode_chain_scene(
    window: MagicMock,
    *,
    scene_path: Path,
    controller_prefab_ids: set[str],
    player_id: str,
    player_name: str,
    player_pos: tuple[float, float],
) -> Dict[str, Any]:
    """Set up a lightweight episode scene for campaign chaining."""
    runners = _build_action_runners(window, scene_path, controller_prefab_ids)
    scene_exits = _build_scene_exits(window, scene_path)

    player = MagicMock()
    player.mesh_id = player_id
    player.mesh_name = player_name
    player.mesh_tags = ["player"]
    player.center_x = float(player_pos[0])
    player.center_y = float(player_pos[1])

    window.scene_controller.all_sprites = [player]
    return {
        "window": window,
        "runners": runners,
        "scene_exits": scene_exits,
        "player": player,
        "triggers": {},
    }


def _setup_ep01(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_01_intro.json"),
        controller_prefab_ids={"ep01_controller", "campaign_controller"},
        player_id="episode_01_player",
        player_name="Episode01Player",
        player_pos=(64.0, 192.0),
    )


def _setup_ep02(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_02_ep02.json"),
        controller_prefab_ids={"ep02_controller", "campaign_controller"},
        player_id="episode_02_ep02_player",
        player_name="Episode02Player",
        player_pos=(72.0, 208.0),
    )


def _setup_ep03(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_03_ep03.json"),
        controller_prefab_ids={"ep03_controller", "campaign_controller"},
        player_id="episode_03_ep03_player",
        player_name="Episode03Player",
        player_pos=(88.0, 224.0),
    )


def _setup_ep04(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_04_ep04.json"),
        controller_prefab_ids={"ep04_controller", "campaign_controller"},
        player_id="episode_04_ep04_player",
        player_name="Episode04Player",
        player_pos=(96.0, 220.0),
    )




def _setup_ep05(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_05_ep05.json"),
        controller_prefab_ids={"ep05_controller", "campaign_controller"},
        player_id="episode_05_ep05_player",
        player_name="Episode05Player",
        player_pos=(72.0, 224.0),
    )


def _setup_ep06(window: MagicMock) -> Dict[str, Any]:
    return _setup_episode_chain_scene(
        window,
        scene_path=Path("scenes/episode_06_ep06.json"),
        controller_prefab_ids={"ep06_controller", "campaign_controller"},
        player_id="episode_06_ep06_player",
        player_name="Episode06Player",
        player_pos=(72.0, 224.0),
    )


# Mapping scene_id -> setup function
_SCENE_SETUP_MAP = {
    "town": _setup_town,
    "puzzle": _setup_puzzle,
    "combat": _setup_combat,
    "ep01": _setup_ep01,
    "ep02": _setup_ep02,
    "ep03": _setup_ep03,
    "ep04": _setup_ep04,
    "ep05": _setup_ep05,
    "ep06": _setup_ep06,
}


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _snapshot_state(window: MagicMock) -> Dict[str, Any]:
    """Capture flags + bus state as a deterministic dict."""
    flags = dict(sorted(window.game_state_controller.state.flags.items()))
    pc = window.gameplay_event_bus.pending_count
    if callable(pc):
        pc = pc()
    return {
        "flags": flags,
        "bus_pending": int(pc),
    }


def _state_digest(state: Dict[str, Any]) -> str:
    blob = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Campaign runner
# ---------------------------------------------------------------------------

class CampaignReplayResult:
    """Result of a single campaign replay run."""

    def __init__(self) -> None:
        self.tracker = DigestTracker(seed=0)
        self.checkpoints: Dict[str, Dict[str, Any]] = {}
        self.milestone_log: List[Dict[str, Any]] = []
        self.event_types: List[str] = []
        self.final_flags: Dict[str, Any] = {}
        self.tick = 0

    def to_trace_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.tracker.seed,
            "digests": {str(k): v for k, v in sorted(self.tracker.digests.items())},
            "milestones": self.milestone_log,
            "event_types": list(self.event_types),
            "final_flags": dict(sorted(self.final_flags.items())),
        }


def _extend_event_types(result: CampaignReplayResult, events: List[Any]) -> None:
    for event in events:
        event_type = str(getattr(event, "event_type", "")).strip()
        if event_type:
            result.event_types.append(event_type)


def run_campaign_replay(script: Dict[str, Any]) -> CampaignReplayResult:
    """Execute one deterministic campaign playthrough from a script definition.

    Args:
        script: Parsed campaign script JSON (from fixture file).

    Returns:
        CampaignReplayResult with digest trace and checkpoint bundles.
    """
    result = CampaignReplayResult()
    quests = QuestRunner()
    quests.load_definitions(_QUESTS_PATH)

    # Start quests
    for qid in script.get("quests", []):
        quests.start_quest(qid)

    prev_snapshot: Optional[Dict[str, Any]] = None

    for scene_def in script.get("scenes", []):
        scene_id: str = scene_def["scene_id"]
        start_hour: float = scene_def.get("start_hour", 12.0)

        # Build window, optionally carry forward state
        window = _build_window(start_hour)
        if prev_snapshot is not None:
            window.game_state_controller.state.restore(prev_snapshot)
        else:
            # Set initial flags
            for flag in script.get("initial_flags", []):
                state_flags.set_flag(window.game_state_controller.state, flag, True)

        # Setup scene
        setup_fn = _SCENE_SETUP_MAP.get(scene_id)
        if setup_fn is None:
            raise ValueError(f"Unknown scene_id '{scene_id}'")
        ctx = setup_fn(window)

        # Execute steps
        for step in scene_def.get("steps", []):
            _execute_step(step, ctx, quests, result)

        # Save state for next scene
        prev_snapshot = window.game_state_controller.state.snapshot()

    # Record final state
    if prev_snapshot:
        result.final_flags = {
            k: v for k, v in sorted(prev_snapshot.get("flags", {}).items())
        }

    return result


def _execute_step(
    step: Dict[str, Any],
    ctx: Dict[str, Any],
    quests: QuestRunner,
    result: CampaignReplayResult,
) -> None:
    """Execute a single step from the campaign script."""
    action = step["action"]
    window = ctx["window"]
    runners = ctx["runners"]

    if action == "set_hour":
        window.day_night.set_hour(step["hour"])

    elif action == "update_schedule":
        dt = step.get("dt", 0.016)
        if "npc_schedule" in ctx:
            ctx["npc_schedule"].update(dt)
        if "time_gate" in ctx:
            ctx["time_gate"].update(dt)

    elif action == "step_trigger":
        trigger_name = step["trigger"]
        trigger = ctx.get("triggers", {}).get(trigger_name)
        if trigger is None:
            trigger = ctx.get(trigger_name)
        if trigger is None:
            raise ValueError(f"Trigger '{trigger_name}' not found in context")
        ctx["player"].center_x = step.get("player_x", 128.0)
        ctx["player"].center_y = step.get("player_y", 256.0)
        _step_on_trigger(trigger, ctx["player"])

    elif action == "drain":
        events = _drain_until_empty(window, runners)
        _extend_event_types(result, events)
        extra = _process_quest_events(window, runners, quests, events)
        _extend_event_types(result, extra)
        result.tick += 1
        # Record milestone digest
        state = _snapshot_state(window)
        digest = _state_digest(state)
        result.tracker.record(result.tick, digest)
        result.milestone_log.append({
            "tick": result.tick,
            "digest": digest,
            "flags_snapshot": dict(sorted(window.game_state_controller.state.flags.items())),
        })

    elif action == "emit":
        payload = step.get("payload", {})
        window.gameplay_event_bus.emit(step["event_type"], **payload)

    elif action == "damage_enemy":
        amount = step["amount"]
        ctx["enemy_health"].apply_damage(amount)
        if ctx["enemy_health"]._dead:
            window.gameplay_event_bus.emit(
                "cv_enemy_dead",
                source_entity="sentry_archer",
                source_behaviour="Health",
                entity="sentry_archer",
            )

    elif action == "process_quests":
        # Full quest routing cycle: drain → quest events → re-emit → drain again
        events = _drain_until_empty(window, runners)
        extra = _process_quest_events(window, runners, quests, events)
        _extend_event_types(result, events)
        _extend_event_types(result, extra)
        result.tick += 1
        state = _snapshot_state(window)
        digest = _state_digest(state)
        result.tracker.record(result.tick, digest)
        result.milestone_log.append({
            "tick": result.tick,
            "digest": digest,
            "flags_snapshot": dict(sorted(window.game_state_controller.state.flags.items())),
        })

    elif action == "save_restore_boundary":
        snapshot = window.game_state_controller.state.snapshot()
        bus_state = window.gameplay_event_bus.saveable_state()
        window.game_state_controller.state.restore(snapshot)
        window.gameplay_event_bus.restore_state(bus_state)
        result.tick += 1
        state = _snapshot_state(window)
        digest = _state_digest(state)
        result.tracker.record(result.tick, digest)
        result.milestone_log.append({
            "tick": result.tick,
            "digest": digest,
            "flags_snapshot": dict(sorted(window.game_state_controller.state.flags.items())),
        })

    elif action == "checkpoint":
        label = step["label"]
        state = _snapshot_state(window)
        digest = _state_digest(state)
        result.checkpoints[label] = {
            "label": label,
            "tick": result.tick,
            "digest": digest,
            "flags": dict(sorted(window.game_state_controller.state.flags.items())),
            "quest_state": quests.get_state(),
            "scene_changes": [
                {"scene": str(scene), "spawn": spawn}
                for scene, spawn in list(getattr(window, "_scene_changes", []))
            ],
        }

    else:
        raise ValueError(f"Unknown action '{action}'")


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def diff_traces(
    trace_a: Dict[str, Any],
    trace_b: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare two digest trace dicts and return diff summary.

    Returns a dict with:
        - identical: bool
        - first_divergence_tick: int | None
        - mismatches: list of {tick, digest_a, digest_b}
        - summary: str
    """
    digests_a = trace_a.get("digests", {})
    digests_b = trace_b.get("digests", {})
    all_ticks = sorted(set(int(k) for k in digests_a) | set(int(k) for k in digests_b))

    mismatches: List[Dict[str, Any]] = []
    first_divergence: Optional[int] = None

    for tick in all_ticks:
        da = digests_a.get(str(tick), "<missing>")
        db = digests_b.get(str(tick), "<missing>")
        if da != db:
            if first_divergence is None:
                first_divergence = tick
            mismatches.append({
                "tick": tick,
                "digest_a": da,
                "digest_b": db,
            })

    identical = len(mismatches) == 0
    summary_parts: List[str] = []
    if identical:
        summary_parts.append(f"Traces identical ({len(all_ticks)} ticks)")
    else:
        summary_parts.append(f"DIVERGENCE at tick {first_divergence}")
        summary_parts.append(f"{len(mismatches)} / {len(all_ticks)} ticks differ")

    return {
        "identical": identical,
        "first_divergence_tick": first_divergence,
        "mismatches": mismatches,
        "total_ticks": len(all_ticks),
        "summary": "; ".join(summary_parts),
    }


def format_diff_text(diff: Dict[str, Any]) -> str:
    """Format a diff result as human-readable text."""
    lines: List[str] = []
    lines.append(f"Campaign Replay Diff")
    lines.append(f"====================")
    lines.append(f"Result: {'IDENTICAL' if diff['identical'] else 'DIVERGENT'}")
    lines.append(f"Total ticks: {diff['total_ticks']}")

    if not diff["identical"]:
        lines.append(f"First divergence: tick {diff['first_divergence_tick']}")
        lines.append(f"Mismatches: {len(diff['mismatches'])}")
        lines.append("")
        for m in diff["mismatches"]:
            lines.append(f"  tick {m['tick']}:")
            lines.append(f"    run_1: {m['digest_a']}")
            lines.append(f"    run_2: {m['digest_b']}")
    else:
        lines.append("No mismatches found.")

    lines.append("")
    return "\n".join(lines)


def load_campaign_script(campaign_id: str) -> Dict[str, Any]:
    """Load a campaign script from the fixtures directory."""
    script_path = _DEFAULT_SCRIPT_DIR / f"{campaign_id}.json"
    return load_campaign_script_from_path(script_path)


def load_campaign_script_from_path(script_path: Path | str) -> Dict[str, Any]:
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Campaign script not found: {path}")
    result = _load_json(path)
    if not isinstance(result, dict):
        raise ValueError(f"Campaign script must be a JSON object: {path}")
    return result
