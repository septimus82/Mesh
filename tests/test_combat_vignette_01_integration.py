"""Integration tests for the Combat Vignette 01 content wiring.

Covers:
- Success path: enter → damage enemy to death → collect reward → quest complete
- HealthBehaviour save/restore correctness through mid-combat saves
- Save/restore after enemy killed but before reward collected
- Deterministic combat progression (same damage schedule → same outcomes)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.behaviours.health import Health
from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.scene_entity_gating import runtime_entity_passes_flag_gates
from engine.state_runtime import flags as state_flags


SCENE_PATH = Path("scenes/combat_vignette_01.json")
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
# Window / environment builders
# ---------------------------------------------------------------------------

def _build_window() -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    window.get_flag = lambda name, default=False: state_flags.get_flag(
        game_state_ctrl.state, name, default
    )
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    # For Health behaviour: disable player_stats lookup by default
    window.engine_config = MagicMock()
    window.engine_config.player_stats_enabled = False
    # event_bus for Health's "died" emission
    window.event_bus = MagicMock()
    return window


def _build_action_runners(window: MagicMock) -> List[Any]:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour

    runners: List[Any] = []
    for entity in _load_scene_entities():
        if entity.get("prefab_id") != "cv_controller":
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


def _build_health(
    window: MagicMock,
    mesh_id: str,
    mesh_name: str,
    mesh_tag: str,
    max_hp: float,
) -> tuple[MagicMock, Health]:
    """Build a Health behaviour attached to a mock entity."""
    entity = MagicMock()
    entity.mesh_id = mesh_id
    entity.mesh_name = mesh_name
    entity.mesh_tag = mesh_tag
    entity.mesh_tags = [mesh_tag] if mesh_tag else []
    entity.mesh_entity_data = {}  # empty so config kwargs take precedence
    health = Health(entity, window, max_hp=max_hp, hp=max_hp)
    return entity, health


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
# Event routing helpers (same pattern as puzzle room tests)
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
# Full arena setup
# ---------------------------------------------------------------------------

def _setup_arena():
    """Build the full combat vignette fixture and return all components."""
    window = _build_window()
    runners = _build_action_runners(window)

    _, player_health = _build_health(window, "player", "Player", "player", max_hp=20)
    enemy_entity, enemy_health = _build_health(window, "sentry_archer", "SentryArcher", "enemy", max_hp=10)

    player = MagicMock()
    player.mesh_id = "player"
    player.mesh_name = "Player"
    player.mesh_tags = ["player"]
    player.center_x = 0.0
    player.center_y = 0.0

    window.scene_controller.all_sprites = [player, enemy_entity]

    entry_trigger = _build_trigger(
        window, "cv_entry_trigger",
        "cv_entry_trigger", "ArenaEntryTrigger",
        128.0, 256.0,
    )

    return {
        "window": window,
        "runners": runners,
        "player": player,
        "player_health": player_health,
        "enemy_entity": enemy_entity,
        "enemy_health": enemy_health,
        "entry_trigger": entry_trigger,
    }


def _enter_arena(ctx: Dict[str, Any]) -> List[Any]:
    """Step on entry trigger and drain events."""
    _step_on_trigger(ctx["entry_trigger"], ctx["player"])
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _deal_damage_to_enemy(ctx: Dict[str, Any], amount: float) -> List[Any]:
    """Apply damage to enemy; if dead, emit cv_enemy_dead on gameplay bus."""
    ctx["enemy_health"].apply_damage(amount)
    if ctx["enemy_health"]._dead:
        ctx["window"].gameplay_event_bus.emit(
            "cv_enemy_dead",
            source_entity="sentry_archer",
            source_behaviour="Health",
            entity="sentry_archer",
        )
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _collect_reward(ctx: Dict[str, Any]) -> List[Any]:
    """Emit reward_collected on gameplay bus simulating chest interaction."""
    ctx["window"].gameplay_event_bus.emit(
        "reward_collected",
        source_entity="chest_reward_cv",
        source_behaviour="Interactable",
        source="chest_reward_cv",
        item_id="",
        gold=50,
    )
    return _drain_until_empty(ctx["window"], ctx["runners"])


def _get_flag(ctx: Dict[str, Any], flag: str) -> bool:
    return ctx["window"].game_state_controller.state.flags.get(flag) is True


# =============================================================================
# Tests
# =============================================================================

class TestCombatVignette01Integration:
    # -----------------------------------------------------------------
    # FULL SUCCESS PATH
    # -----------------------------------------------------------------
    def test_success_path(self) -> None:
        """Enter → damage enemy to death → collect reward → quest completes."""
        ctx = _setup_arena()
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        assert quests.start_quest("combat_vignette_01") is True

        # --- Step 0: Enter arena ---
        events = _enter_arena(ctx)
        quests.process_events(events)
        assert _get_flag(ctx, "cv.started")
        assert any(e.event_type == "cv_combat_started" for e in events)
        state = quests.get_quest_state("combat_vignette_01")
        assert state is not None
        assert state.current_stage == "step1"

        # --- Step 1: Kill enemy (3 hits of 4 damage each) ---
        _deal_damage_to_enemy(ctx, 4.0)
        assert not ctx["enemy_health"]._dead
        assert ctx["enemy_health"].hp == 6.0

        _deal_damage_to_enemy(ctx, 4.0)
        assert not ctx["enemy_health"]._dead
        assert ctx["enemy_health"].hp == 2.0
        events = _deal_damage_to_enemy(ctx, 4.0)
        assert ctx["enemy_health"]._dead
        assert ctx["enemy_health"].hp <= 0
        quests.process_events(events)
        assert _get_flag(ctx, "cv.enemy_dead")
        assert _get_flag(ctx, "cv.reward_unlocked")
        assert any(e.event_type == "cv_reward_unlocked" for e in events)
        state = quests.get_quest_state("combat_vignette_01")
        assert state is not None
        assert state.current_stage == "step2"

        # Door/chest gate check — chest_reward_cv require_flags=["cv.reward_unlocked"]
        chest_prefab = _load_prefab("chest_reward_cv")
        chest_mock = MagicMock()
        chest_mock.mesh_entity_data = chest_prefab.get("entity", {})
        chest_mock.mesh_entity_data["require_flags"] = chest_prefab.get("require_flags", [])
        assert runtime_entity_passes_flag_gates(
            chest_mock, get_flag=ctx["window"].get_flag
        ) is True

        # --- Step 2: Collect reward ---
        events = _collect_reward(ctx)
        emitted = quests.process_events(events)
        assert _get_flag(ctx, "cv.completed")
        assert any(e.event_type == "cv_complete" for e in events)
        assert any(e.event_type == "quest_combat_vignette_complete" for e in emitted)
        state = quests.get_quest_state("combat_vignette_01")
        assert state is not None
        assert state.status == "completed"

    # -----------------------------------------------------------------
    # HEALTH SAVE / RESTORE MID-COMBAT
    # -----------------------------------------------------------------
    def test_health_save_restore_mid_combat(self) -> None:
        """Damage enemy partially, save health, restore, continue → same outcome."""
        ctx = _setup_arena()
        _enter_arena(ctx)

        # Deal partial damage (two hits of 3)
        _deal_damage_to_enemy(ctx, 3.0)
        _deal_damage_to_enemy(ctx, 3.0)
        assert ctx["enemy_health"].hp == 4.0
        assert not ctx["enemy_health"]._dead

        # Save both health states
        saved_enemy = ctx["enemy_health"].saveable_state()
        saved_player = ctx["player_health"].saveable_state()

        # Deal more damage after save (should not affect restored state)
        _deal_damage_to_enemy(ctx, 2.0)
        assert ctx["enemy_health"].hp == 2.0

        # Restore enemy health to saved state
        ctx["enemy_health"].restore_state(saved_enemy)
        assert ctx["enemy_health"].hp == 4.0
        assert not ctx["enemy_health"]._dead

        # Restore player health
        ctx["player_health"].restore_state(saved_player)
        assert ctx["player_health"].hp == 20.0

        # Continue combat from restored state: kill with remaining HP
        _deal_damage_to_enemy(ctx, 4.0)
        assert ctx["enemy_health"].hp == 0.0
        events = _deal_damage_to_enemy(ctx, 1.0)
        # Already dead from previous hit — no double-death
        assert ctx["enemy_health"]._dead

    # -----------------------------------------------------------------
    # FULL SAVE / RESTORE MID-COMBAT (all components)
    # -----------------------------------------------------------------
    def test_save_restore_full_mid_combat(self) -> None:
        """Save all state mid-combat, restore into fresh arena, continue to completion."""
        ctx = _setup_arena()
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        quests.start_quest("combat_vignette_01")

        events = _enter_arena(ctx)
        quests.process_events(events)

        # Partial damage
        _deal_damage_to_enemy(ctx, 5.0)
        assert ctx["enemy_health"].hp == 5.0

        # --- Save all state ---
        saved_flags = ctx["window"].game_state_controller.state.snapshot()
        saved_bus = ctx["window"].gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in ctx["runners"]}
        saved_enemy_hp = ctx["enemy_health"].saveable_state()
        saved_player_hp = ctx["player_health"].saveable_state()

        # --- Restore into fresh arena ---
        new_ctx = _setup_arena()
        new_ctx["window"].game_state_controller.state.restore(saved_flags)
        new_ctx["window"].gameplay_event_bus.restore_state(saved_bus)
        for runner in new_ctx["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)
        new_ctx["enemy_health"].restore_state(saved_enemy_hp)
        new_ctx["player_health"].restore_state(saved_player_hp)

        # Verify restored state
        assert _get_flag(new_ctx, "cv.started")
        assert new_ctx["enemy_health"].hp == 5.0
        assert new_ctx["player_health"].hp == 20.0

        # Continue combat in restored arena
        events = _deal_damage_to_enemy(new_ctx, 5.0)
        assert new_ctx["enemy_health"]._dead
        quests.process_events(events)
        assert _get_flag(new_ctx, "cv.enemy_dead")
        assert _get_flag(new_ctx, "cv.reward_unlocked")

        # Collect reward
        events = _collect_reward(new_ctx)
        emitted = quests.process_events(events)
        assert _get_flag(new_ctx, "cv.completed")
        assert any(e.event_type == "quest_combat_vignette_complete" for e in emitted)

    # -----------------------------------------------------------------
    # SAVE / RESTORE AFTER KILL, BEFORE COLLECT
    # -----------------------------------------------------------------
    def test_save_restore_after_kill_before_collect(self) -> None:
        """Enemy dead + chest unlocked; save, restore, collect → quest complete."""
        ctx = _setup_arena()
        quests = QuestRunner()
        quests.load_definitions(Path("assets/data/quests.json"))
        quests.start_quest("combat_vignette_01")

        # Enter and kill enemy
        events = _enter_arena(ctx)
        quests.process_events(events)
        events = _deal_damage_to_enemy(ctx, 10.0)
        quests.process_events(events)
        assert _get_flag(ctx, "cv.enemy_dead")
        assert _get_flag(ctx, "cv.reward_unlocked")

        # --- Save ---
        saved_flags = ctx["window"].game_state_controller.state.snapshot()
        saved_bus = ctx["window"].gameplay_event_bus.saveable_state()
        saved_runners = {r.entity.mesh_id: r.saveable_state() for r in ctx["runners"]}

        # --- Restore ---
        new_ctx = _setup_arena()
        new_ctx["window"].game_state_controller.state.restore(saved_flags)
        new_ctx["window"].gameplay_event_bus.restore_state(saved_bus)
        for runner in new_ctx["runners"]:
            state = saved_runners.get(runner.entity.mesh_id)
            if state is not None:
                runner.restore_state(state)

        # Verify flags preserved
        assert _get_flag(new_ctx, "cv.started")
        assert _get_flag(new_ctx, "cv.enemy_dead")
        assert _get_flag(new_ctx, "cv.reward_unlocked")

        # Chest gate still satisfied after restore
        chest_prefab = _load_prefab("chest_reward_cv")
        chest_mock = MagicMock()
        chest_mock.mesh_entity_data = {
            **chest_prefab.get("entity", {}),
            "require_flags": chest_prefab.get("require_flags", []),
        }
        assert runtime_entity_passes_flag_gates(
            chest_mock, get_flag=new_ctx["window"].get_flag
        ) is True

        # Collect reward after restore
        events = _collect_reward(new_ctx)
        emitted = quests.process_events(events)
        assert _get_flag(new_ctx, "cv.completed")
        assert any(e.event_type == "quest_combat_vignette_complete" for e in emitted)
        state = quests.get_quest_state("combat_vignette_01")
        assert state is not None
        assert state.status == "completed"

    # -----------------------------------------------------------------
    # PLAYER HEALTH PERSISTENCE
    # -----------------------------------------------------------------
    def test_player_health_save_restore(self) -> None:
        """Damage player, save, restore → HP preserved exactly."""
        ctx = _setup_arena()

        # Player takes damage
        ctx["player_health"].apply_damage(7.0)
        assert ctx["player_health"].hp == 13.0
        ctx["player_health"].apply_damage(5.0)
        assert ctx["player_health"].hp == 8.0

        saved = ctx["player_health"].saveable_state()
        assert saved["hp"] == 8.0
        assert saved["max_hp"] == 20.0
        assert saved["dead"] is False

        # Restore into a fresh health instance
        new_ctx = _setup_arena()
        assert new_ctx["player_health"].hp == 20.0  # starts full
        new_ctx["player_health"].restore_state(saved)
        assert new_ctx["player_health"].hp == 8.0
        assert new_ctx["player_health"].max_hp == 20.0
        assert not new_ctx["player_health"]._dead

    # -----------------------------------------------------------------
    # DETERMINISTIC DAMAGE SEQUENCE
    # -----------------------------------------------------------------
    def test_deterministic_damage_sequence(self) -> None:
        """Same damage schedule → identical flags and events both times."""
        damage_schedule = [3.0, 3.0, 2.0, 2.0]

        results: list[dict] = []
        for _ in range(2):
            ctx = _setup_arena()
            _enter_arena(ctx)

            all_events: list[str] = []
            for dmg in damage_schedule:
                events = _deal_damage_to_enemy(ctx, dmg)
                all_events.extend(e.event_type for e in events)

            results.append({
                "events": all_events,
                "hp": ctx["enemy_health"].hp,
                "dead": ctx["enemy_health"]._dead,
                "flags": dict(ctx["window"].game_state_controller.state.flags),
            })

        # Both runs must produce identical outcomes
        assert results[0]["events"] == results[1]["events"]
        assert results[0]["hp"] == results[1]["hp"]
        assert results[0]["dead"] == results[1]["dead"]
        assert results[0]["flags"] == results[1]["flags"]

    # -----------------------------------------------------------------
    # CHEST NOT ACCESSIBLE BEFORE KILL
    # -----------------------------------------------------------------
    def test_chest_locked_before_kill(self) -> None:
        """Chest require_flags gate fails before enemy is dead."""
        ctx = _setup_arena()
        _enter_arena(ctx)

        # Enemy still alive — cv.reward_unlocked not set
        assert not _get_flag(ctx, "cv.reward_unlocked")

        chest_prefab = _load_prefab("chest_reward_cv")
        chest_mock = MagicMock()
        chest_mock.mesh_entity_data = {
            **chest_prefab.get("entity", {}),
            "require_flags": chest_prefab.get("require_flags", []),
        }
        assert runtime_entity_passes_flag_gates(
            chest_mock, get_flag=ctx["window"].get_flag
        ) is False
