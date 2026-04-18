"""Integration tests for Episode 04: Sentry at the Causeway."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from engine.cutscene_runtime.runner import CutsceneRunner
from engine.gameplay_event_bus import GameplayEventBus
from engine.game_state_controller import GameState
from engine.quest_runtime.runner import QuestRunner
from engine.save_runtime.digest import compute_world_digest
from engine.scene_entity_gating import runtime_entity_passes_flag_gates
from engine.state_runtime import flags as state_flags

from tests.cutscene_helpers import advance_cutscene_time


SCENE_PATH = Path("scenes/episode_04_ep04.json")
PREFABS_PATH = Path("assets/prefabs.json")
CUTSCENES_PATH = Path("cutscenes.json")
QUESTS_PATH = Path("assets/data/quests.json")

QUEST_ID = "episode_04_ep04"
INTRO_CUTSCENE_ID = "ep04_intro"
OUTRO_CUTSCENE_ID = "ep04_outro"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prefab_map() -> dict[str, dict[str, Any]]:
    prefabs = _load_json(PREFABS_PATH)
    out: dict[str, dict[str, Any]] = {}
    for entry in prefabs:
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    return out


def _load_scene_entities() -> list[dict[str, Any]]:
    payload = _load_json(SCENE_PATH)
    return list(payload.get("entities", []))


def _load_cutscene_script(cutscene_id: str) -> dict[str, Any]:
    payload = _load_json(CUTSCENES_PATH)
    entries = payload.get("cutscenes", []) if isinstance(payload, dict) else []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("id") != cutscene_id:
            continue
        commands: list[dict[str, Any]] = []
        for step in entry.get("steps", []):
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type", "")).strip()
            if not step_type:
                continue
            if step_type == "emit_event":
                cmd: dict[str, Any] = {
                    "type": "emit_event",
                    "event_type": str(step.get("event", "")),
                }
                payload_data = {
                    key: value
                    for key, value in step.items()
                    if key not in {"type", "event"}
                }
                if payload_data:
                    cmd["payload"] = payload_data
                commands.append(cmd)
            else:
                commands.append(dict(step))
        return {
            "schema_version": 1,
            "id": str(entry.get("id", "")),
            "commands": commands,
        }
    raise AssertionError(f"Cutscene '{cutscene_id}' not found")


class _BridgeEventBus:
    def __init__(self, gameplay_bus: GameplayEventBus) -> None:
        self._gameplay_bus = gameplay_bus

    def emit(self, event_type: str, **payload: Any) -> None:
        if str(event_type).strip() == "died":
            name = str(payload.get("name", "")).strip()
            if not name:
                actor = payload.get("actor")
                name = str(getattr(actor, "mesh_name", "")).strip()
            routed_payload: dict[str, Any] = {"name": name}
            if name:
                routed_payload["entity"] = name
            self._gameplay_bus.emit("died", **routed_payload)
            return
        self._gameplay_bus.emit(str(event_type), **payload)


def _build_window() -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    window.get_flag = lambda name, default=False: state_flags.get_flag(game_state_ctrl.state, name, default)
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    window.scene_controller.move_entity_with_collision = lambda entity, dx, dy: (
        setattr(entity, "center_x", float(getattr(entity, "center_x", 0.0)) + float(dx)),
        setattr(entity, "center_y", float(getattr(entity, "center_y", 0.0)) + float(dy)),
    )
    window.move_entity_with_collision = window.scene_controller.move_entity_with_collision
    window.engine_config = MagicMock()
    window.engine_config.player_stats_enabled = False
    window.event_bus = _BridgeEventBus(window.gameplay_event_bus)
    return window


def _build_cutscene_runner(window: MagicMock, script: dict[str, Any]) -> CutsceneRunner:
    class _Flags:
        def __init__(self, state: Any) -> None:
            self._state = state

        def get_flag(self, name: str, default: bool = False) -> bool:
            return state_flags.get_flag(self._state, name, default)

        def set_flag(self, name: str, value: bool) -> None:
            state_flags.set_flag(self._state, name, bool(value))

    flags = _Flags(window.game_state_controller.state)
    runner = CutsceneRunner(
        event_bus=window.gameplay_event_bus,
        flag_provider=flags,
        flag_setter=flags,
    )
    errors = runner.load_script_from_data(dict(script))
    assert not errors, f"Cutscene load errors: {errors}"
    return runner


def _build_episode_context(*, start_quest: bool = True) -> dict[str, Any]:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
    from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour
    from engine.behaviours.health import Health
    from engine.behaviours.interactable import InteractableBehaviour
    from engine.behaviours.patrol_path import PatrolPathBehaviour
    from engine.behaviours.ranged_enemy_ai import RangedEnemyAI
    from engine.behaviours.shooter import Shooter
    from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

    behaviour_builders = {
        "ActionListRunner": ActionListRunnerBehaviour,
        "DialogueRunner": DialogueRunnerBehaviour,
        "Health": Health,
        "Interactable": InteractableBehaviour,
        "PatrolPath": PatrolPathBehaviour,
        "RangedEnemyAI": RangedEnemyAI,
        "Shooter": Shooter,
        "TriggerVolume": TriggerVolumeBehaviour,
    }

    window = _build_window()
    prefabs = _load_prefab_map()

    entities: dict[str, Any] = {}
    behaviours: dict[str, dict[str, Any]] = {}
    action_runners: list[Any] = []
    trigger_volumes: dict[str, Any] = {}
    interactables: dict[str, Any] = {}
    dialogue_runners: dict[str, Any] = {}
    health_behaviours: dict[str, Any] = {}

    for raw in _load_scene_entities():
        prefab_id = str(raw.get("prefab_id", ""))
        prefab = prefabs.get(prefab_id, {})
        prefab_entity = prefab.get("entity", {}) if isinstance(prefab, dict) else {}
        base_behaviours = list(prefab_entity.get("behaviours", []))
        base_cfg = prefab_entity.get("behaviour_config", {}) if isinstance(prefab_entity, dict) else {}
        override_cfg = raw.get("behaviour_config", {}) if isinstance(raw.get("behaviour_config"), dict) else {}

        entity = MagicMock()
        entity.mesh_id = str(raw.get("id", ""))
        entity.mesh_name = str(raw.get("name", entity.mesh_id))
        entity.mesh_tags = list(prefab.get("tags", [])) if isinstance(prefab.get("tags"), list) else []
        entity.mesh_tag = str(entity.mesh_tags[0]) if entity.mesh_tags else ""
        entity.center_x = float(raw.get("x", 0.0))
        entity.center_y = float(raw.get("y", 0.0))
        entity.behaviours = []
        entity.mesh_entity_data = {
            **(prefab_entity if isinstance(prefab_entity, dict) else {}),
            "require_flags": list(prefab.get("require_flags", [])) if isinstance(prefab.get("require_flags"), list) else [],
            "forbid_flags": list(prefab.get("forbid_flags", [])) if isinstance(prefab.get("forbid_flags"), list) else [],
        }

        per_entity_behaviours: dict[str, Any] = {}
        for behaviour_name in base_behaviours:
            builder = behaviour_builders.get(str(behaviour_name))
            if builder is None:
                continue
            cfg = dict(base_cfg.get(behaviour_name, {})) if isinstance(base_cfg, dict) else {}
            if isinstance(override_cfg.get(behaviour_name), dict):
                cfg.update(override_cfg[behaviour_name])
            instance = builder(entity, window, **cfg)
            entity.behaviours.append(instance)
            per_entity_behaviours[str(behaviour_name)] = instance
            if behaviour_name == "ActionListRunner":
                action_runners.append(instance)
            elif behaviour_name == "TriggerVolume":
                trigger_volumes[entity.mesh_id] = instance
            elif behaviour_name == "Interactable":
                interactables[entity.mesh_id] = instance
            elif behaviour_name == "DialogueRunner":
                dialogue_runners[entity.mesh_id] = instance
            elif behaviour_name == "Health":
                health_behaviours[entity.mesh_id] = instance

        entity.mesh_behaviours_runtime = list(entity.behaviours)
        entities[entity.mesh_id] = entity
        behaviours[entity.mesh_id] = per_entity_behaviours

    # Ensure player has saveable Health state for mid-combat save/restore checks.
    player_id = "episode_04_ep04_player"
    if player_id not in health_behaviours:
        from engine.behaviours.health import Health

        player = entities[player_id]
        player.mesh_tag = "player"
        manual_health = Health(player, window, max_hp=20.0, hp=20.0)
        player.behaviours.append(manual_health)
        player.mesh_behaviours_runtime = list(player.behaviours)
        behaviours[player_id]["Health"] = manual_health
        health_behaviours[player_id] = manual_health

    window.scene_controller.all_sprites = list(entities.values())

    quests = QuestRunner()
    quests.load_definitions(QUESTS_PATH)
    if start_quest:
        assert quests.start_quest(QUEST_ID) is True

    intro_runner = _build_cutscene_runner(window, _load_cutscene_script(INTRO_CUTSCENE_ID))
    outro_runner = _build_cutscene_runner(window, _load_cutscene_script(OUTRO_CUTSCENE_ID))

    return {
        "window": window,
        "entities": entities,
        "behaviours": behaviours,
        "action_runners": action_runners,
        "trigger_volumes": trigger_volumes,
        "interactables": interactables,
        "dialogue_runners": dialogue_runners,
        "health_behaviours": health_behaviours,
        "quest_runner": quests,
        "intro_runner": intro_runner,
        "outro_runner": outro_runner,
        "event_log": [],
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical_value(value[k]) for k in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_event(event: Any) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "payload": _canonical_value(dict(event.payload or {})),
    }


def _get_flag(ctx: dict[str, Any], flag: str) -> bool:
    return ctx["window"].game_state_controller.state.flags.get(flag) is True


def _find_entity(ctx: dict[str, Any], identifier: str):
    entities = ctx["entities"]
    if identifier in entities:
        return entities[identifier]
    for entity in entities.values():
        if getattr(entity, "mesh_name", "") == identifier:
            return entity
    return None


def _start_dialogue_from_cutscene_event(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    target_id = str(payload.get("target", "")).strip()
    dialogue_id = str(payload.get("dialogue_id", "")).strip()
    node_id = payload.get("node_id")
    target = _find_entity(ctx, target_id)
    if target is None:
        return
    for behaviour in getattr(target, "behaviours", []):
        if type(behaviour).__name__ != "DialogueRunnerBehaviour":
            continue
        if dialogue_id and getattr(behaviour, "dialogue_id", "") != dialogue_id:
            continue
        behaviour.start(node_id if isinstance(node_id, str) and node_id else None)
        return


def _drain_and_route(ctx: dict[str, Any]) -> list[Any]:
    events = ctx["window"].gameplay_event_bus.drain()
    if not events:
        return []

    for event in events:
        ctx["event_log"].append(_canonical_event(event))
        for runner in ctx["action_runners"]:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)
        if event.event_type == "ep04_intro_start" and not ctx["intro_runner"].is_running:
            ctx["intro_runner"].start()
        elif event.event_type == "ep04_outro_start" and not ctx["outro_runner"].is_running:
            ctx["outro_runner"].start()
        elif event.event_type == "cutscene_start_dialogue":
            _start_dialogue_from_cutscene_event(ctx, event.payload)

    for runner in ctx["action_runners"]:
        runner.update(0.0)

    emitted = ctx["quest_runner"].process_events(events)
    for event in emitted:
        ctx["window"].gameplay_event_bus.emit(event.event_type, **(event.payload or {}))

    return events


def _drain_until_empty(ctx: dict[str, Any]) -> list[Any]:
    collected: list[Any] = []
    for _ in range(64):
        batch = _drain_and_route(ctx)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _advance(ctx: dict[str, Any], dt: float) -> list[Any]:
    for cutscene in (ctx["intro_runner"], ctx["outro_runner"]):
        if cutscene.is_running:
            advance_cutscene_time(cutscene, dt)
    for runner in ctx["action_runners"]:
        runner.update(dt)
    for interactable in ctx["interactables"].values():
        interactable.update(dt)
    return _drain_until_empty(ctx)


def _step_on_trigger(trigger: Any, player: Any, *, off_pos: tuple[float, float] = (0.0, 0.0)) -> None:
    player.center_x = float(trigger.entity.center_x)
    player.center_y = float(trigger.entity.center_y)
    trigger.update(0.016)
    player.center_x = float(off_pos[0])
    player.center_y = float(off_pos[1])
    trigger.update(0.016)


def _interact(ctx: dict[str, Any], interactable_id: str) -> list[Any]:
    player = ctx["entities"]["episode_04_ep04_player"]
    target = ctx["entities"][interactable_id]
    behaviour = ctx["interactables"][interactable_id]
    player.center_x = float(target.center_x)
    player.center_y = float(target.center_y)
    assert behaviour.try_interact() is True
    return _drain_until_empty(ctx)


def _damage_sentry(ctx: dict[str, Any], sentry_entity_id: str, amount: float) -> list[Any]:
    health = ctx["health_behaviours"][sentry_entity_id]
    health.apply_damage(amount)
    return _drain_until_empty(ctx)


def _compute_digest(ctx: dict[str, Any], frame: int) -> str:
    entities_payload: list[dict[str, Any]] = []
    for entity_id in sorted(ctx["entities"].keys()):
        entity = ctx["entities"][entity_id]
        behaviour_state: dict[str, Any] = {}
        for behaviour_name, behaviour in sorted(ctx["behaviours"].get(entity_id, {}).items()):
            if hasattr(behaviour, "saveable_state"):
                behaviour_state[behaviour_name] = behaviour.saveable_state()
        entities_payload.append(
            {
                "entity_id": entity_id,
                "x": float(getattr(entity, "center_x", 0.0)),
                "y": float(getattr(entity, "center_y", 0.0)),
                "behaviour_state": behaviour_state,
            }
        )

    entities_payload.append(
        {
            "entity_id": "ep04_runtime_state",
            "x": 0.0,
            "y": 0.0,
            "behaviour_state": {
                "flags": dict(sorted(ctx["window"].game_state_controller.state.flags.items())),
                "quest_state": ctx["quest_runner"].get_state(),
                "intro": ctx["intro_runner"].saveable_state(),
                "outro": ctx["outro_runner"].saveable_state(),
                "event_bus": ctx["window"].gameplay_event_bus.saveable_state(),
            },
        }
    )
    return compute_world_digest(entities=entities_payload, quests=[], frame=frame)


def _snapshot_context(ctx: dict[str, Any]) -> dict[str, Any]:
    behaviour_states: dict[str, dict[str, Any]] = {}
    for entity_id, per_entity in ctx["behaviours"].items():
        for behaviour_name, behaviour in per_entity.items():
            if hasattr(behaviour, "saveable_state"):
                behaviour_states[f"{entity_id}:{behaviour_name}"] = behaviour.saveable_state()
    return {
        "flags": ctx["window"].game_state_controller.state.snapshot(),
        "bus": ctx["window"].gameplay_event_bus.saveable_state(),
        "behaviours": behaviour_states,
        "intro": ctx["intro_runner"].saveable_state(),
        "outro": ctx["outro_runner"].saveable_state(),
        "quests": ctx["quest_runner"].get_state(),
        "events": list(ctx["event_log"]),
    }


def _restore_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    ctx = _build_episode_context(start_quest=False)
    ctx["window"].game_state_controller.state.restore(snapshot["flags"])
    ctx["window"].gameplay_event_bus.restore_state(snapshot["bus"])
    for entity_id, per_entity in ctx["behaviours"].items():
        for behaviour_name, behaviour in per_entity.items():
            key = f"{entity_id}:{behaviour_name}"
            if key in snapshot["behaviours"] and hasattr(behaviour, "restore_state"):
                behaviour.restore_state(snapshot["behaviours"][key])
    ctx["intro_runner"].restore_state(snapshot["intro"])
    ctx["outro_runner"].restore_state(snapshot["outro"])
    ctx["quest_runner"].apply_state(snapshot["quests"])
    ctx["event_log"] = list(snapshot["events"])
    return ctx


def _run_episode(path: str) -> dict[str, Any]:
    ctx = _build_episode_context()
    digests: list[str] = []
    frame = 0

    def record() -> None:
        nonlocal frame
        digests.append(_compute_digest(ctx, frame))
        frame += 1

    record()
    _step_on_trigger(
        ctx["trigger_volumes"]["episode_04_ep04_entry_trigger"],
        ctx["entities"]["episode_04_ep04_player"],
    )
    _drain_until_empty(ctx)
    record()

    _advance(ctx, 0.4)
    record()

    mentor_dialogue = ctx["dialogue_runners"]["episode_04_ep04_mentor"]
    assert mentor_dialogue.is_running is True
    assert mentor_dialogue.choose(0 if path == "safe" else 1) is True
    _drain_until_empty(ctx)
    record()

    if path == "safe":
        _damage_sentry(ctx, "episode_04_ep04_sentry_easy", 4.0)
        snapshot = _snapshot_context(ctx)
        ctx = _restore_context(snapshot)
        _damage_sentry(ctx, "episode_04_ep04_sentry_easy", 6.0)
    else:
        _damage_sentry(ctx, "episode_04_ep04_sentry_hard_a", 6.0)
        snapshot = _snapshot_context(ctx)
        ctx = _restore_context(snapshot)
        _damage_sentry(ctx, "episode_04_ep04_sentry_hard_a", 6.0)
        _damage_sentry(ctx, "episode_04_ep04_sentry_hard_b", 12.0)
    record()

    _interact(ctx, "episode_04_ep04_reward_cache")
    _advance(ctx, 0.3)
    record()

    quest_state = ctx["quest_runner"].get_quest_state(QUEST_ID)
    return {
        "digests": digests,
        "events": list(ctx["event_log"]),
        "flags": dict(ctx["window"].game_state_controller.state.flags),
        "quest_status": quest_state.status if quest_state else None,
    }


class TestEpisode04Integration:
    def test_episode_04_easy_path_happy(self) -> None:
        ctx = _build_episode_context()
        assert len(_load_scene_entities()) <= 26

        _step_on_trigger(
            ctx["trigger_volumes"]["episode_04_ep04_entry_trigger"],
            ctx["entities"]["episode_04_ep04_player"],
        )
        events = _drain_until_empty(ctx)
        assert any(e.event_type == "ep04_entered" for e in events)

        _advance(ctx, 0.4)
        mentor_dialogue = ctx["dialogue_runners"]["episode_04_ep04_mentor"]
        assert mentor_dialogue.is_running is True
        assert mentor_dialogue.choose(0) is True
        _drain_until_empty(ctx)

        assert _get_flag(ctx, "ep04.easy_mode") is True
        assert _get_flag(ctx, "ep04.hard_mode") is not True
        assert _get_flag(ctx, "ep04.combat_started") is True
        assert any(evt["event_type"] == "ep04_combat_started" for evt in ctx["event_log"])

        easy_entity = ctx["entities"]["episode_04_ep04_sentry_easy"]
        hard_a_entity = ctx["entities"]["episode_04_ep04_sentry_hard_a"]
        assert runtime_entity_passes_flag_gates(easy_entity, get_flag=ctx["window"].get_flag) is True
        assert runtime_entity_passes_flag_gates(hard_a_entity, get_flag=ctx["window"].get_flag) is False

        _damage_sentry(ctx, "episode_04_ep04_sentry_easy", 10.0)
        assert _get_flag(ctx, "ep04.all_enemies_dead") is True
        assert _get_flag(ctx, "ep04.exit_unlocked") is True
        assert any(evt["event_type"] == "ep04_all_enemies_dead" for evt in ctx["event_log"])

        reward_entity = ctx["entities"]["episode_04_ep04_reward_cache"]
        door_entity = ctx["entities"]["episode_04_ep04_exit_door"]
        assert runtime_entity_passes_flag_gates(reward_entity, get_flag=ctx["window"].get_flag) is True
        assert runtime_entity_passes_flag_gates(door_entity, get_flag=ctx["window"].get_flag) is True

        _interact(ctx, "episode_04_ep04_reward_cache")
        _advance(ctx, 0.3)

        quest_state = ctx["quest_runner"].get_quest_state(QUEST_ID)
        assert quest_state is not None
        assert quest_state.status == "completed"
        assert _get_flag(ctx, "ep04.complete") is True
        assert any(evt["event_type"] == "ep04_reward_collected" for evt in ctx["event_log"])
        assert any(evt["event_type"] == "quest_ep04_complete" for evt in ctx["event_log"])

    def test_episode_04_hard_path_happy(self) -> None:
        ctx = _build_episode_context()
        _step_on_trigger(
            ctx["trigger_volumes"]["episode_04_ep04_entry_trigger"],
            ctx["entities"]["episode_04_ep04_player"],
        )
        _drain_until_empty(ctx)
        _advance(ctx, 0.4)

        mentor_dialogue = ctx["dialogue_runners"]["episode_04_ep04_mentor"]
        assert mentor_dialogue.choose(1) is True
        _drain_until_empty(ctx)

        assert _get_flag(ctx, "ep04.hard_mode") is True
        assert _get_flag(ctx, "ep04.easy_mode") is not True
        assert _get_flag(ctx, "ep04.combat_started") is True

        easy_entity = ctx["entities"]["episode_04_ep04_sentry_easy"]
        hard_a_entity = ctx["entities"]["episode_04_ep04_sentry_hard_a"]
        hard_b_entity = ctx["entities"]["episode_04_ep04_sentry_hard_b"]
        assert runtime_entity_passes_flag_gates(easy_entity, get_flag=ctx["window"].get_flag) is False
        assert runtime_entity_passes_flag_gates(hard_a_entity, get_flag=ctx["window"].get_flag) is True
        assert runtime_entity_passes_flag_gates(hard_b_entity, get_flag=ctx["window"].get_flag) is True

        _damage_sentry(ctx, "episode_04_ep04_sentry_hard_a", 12.0)
        assert _get_flag(ctx, "ep04.hard_sentry_a_dead") is True
        assert _get_flag(ctx, "ep04.all_enemies_dead") is not True

        _damage_sentry(ctx, "episode_04_ep04_sentry_hard_b", 12.0)
        assert _get_flag(ctx, "ep04.hard_sentry_b_dead") is True
        assert _get_flag(ctx, "ep04.all_enemies_dead") is True
        assert _get_flag(ctx, "ep04.exit_unlocked") is True

        _interact(ctx, "episode_04_ep04_reward_cache")
        _advance(ctx, 0.3)

        quest_state = ctx["quest_runner"].get_quest_state(QUEST_ID)
        assert quest_state is not None
        assert quest_state.status == "completed"
        assert any(evt["event_type"] == "ep04_all_enemies_dead" for evt in ctx["event_log"])
        assert any(evt["event_type"] == "quest_ep04_complete" for evt in ctx["event_log"])

    def test_episode_04_save_restore_mid_cutscene_then_complete(self) -> None:
        ctx = _build_episode_context()
        _step_on_trigger(
            ctx["trigger_volumes"]["episode_04_ep04_entry_trigger"],
            ctx["entities"]["episode_04_ep04_player"],
        )
        _drain_until_empty(ctx)
        _advance(ctx, 0.1)
        assert ctx["intro_runner"].is_running is True

        snapshot = _snapshot_context(ctx)
        restored = _restore_context(snapshot)
        assert restored["intro_runner"].is_running is True

        _advance(restored, 0.35)
        mentor_dialogue = restored["dialogue_runners"]["episode_04_ep04_mentor"]
        assert mentor_dialogue.is_running is True
        assert mentor_dialogue.choose(0) is True
        _drain_until_empty(restored)

        _damage_sentry(restored, "episode_04_ep04_sentry_easy", 10.0)
        _interact(restored, "episode_04_ep04_reward_cache")
        _advance(restored, 0.3)

        quest_state = restored["quest_runner"].get_quest_state(QUEST_ID)
        assert quest_state is not None
        assert quest_state.status == "completed"

    def test_episode_04_save_restore_mid_dialogue_and_mid_combat_hp(self) -> None:
        ctx = _build_episode_context()
        _step_on_trigger(
            ctx["trigger_volumes"]["episode_04_ep04_entry_trigger"],
            ctx["entities"]["episode_04_ep04_player"],
        )
        _drain_until_empty(ctx)
        _advance(ctx, 0.4)

        mentor_dialogue = ctx["dialogue_runners"]["episode_04_ep04_mentor"]
        assert mentor_dialogue.is_running is True
        assert mentor_dialogue.current_node == "start"

        dialogue_snapshot = _snapshot_context(ctx)
        restored_dialogue = _restore_context(dialogue_snapshot)
        dialogue_runner = restored_dialogue["dialogue_runners"]["episode_04_ep04_mentor"]
        assert dialogue_runner.is_running is True
        assert dialogue_runner.current_node == "start"
        assert dialogue_runner.choose(1) is True
        _drain_until_empty(restored_dialogue)

        player_health = restored_dialogue["health_behaviours"]["episode_04_ep04_player"]
        hard_a_health = restored_dialogue["health_behaviours"]["episode_04_ep04_sentry_hard_a"]
        player_health.apply_damage(3.0)
        _drain_until_empty(restored_dialogue)
        _damage_sentry(restored_dialogue, "episode_04_ep04_sentry_hard_a", 4.0)
        assert player_health.hp == 17.0
        assert hard_a_health.hp == 8.0

        combat_snapshot = _snapshot_context(restored_dialogue)
        restored_combat = _restore_context(combat_snapshot)
        restored_player_health = restored_combat["health_behaviours"]["episode_04_ep04_player"]
        restored_hard_a_health = restored_combat["health_behaviours"]["episode_04_ep04_sentry_hard_a"]
        assert restored_player_health.hp == 17.0
        assert restored_hard_a_health.hp == 8.0

        _damage_sentry(restored_combat, "episode_04_ep04_sentry_hard_a", 8.0)
        _damage_sentry(restored_combat, "episode_04_ep04_sentry_hard_b", 12.0)

        post_kill_snapshot = _snapshot_context(restored_combat)
        post_kill_restored = _restore_context(post_kill_snapshot)
        assert _get_flag(post_kill_restored, "ep04.all_enemies_dead") is True
        assert _get_flag(post_kill_restored, "ep04.exit_unlocked") is True

        _interact(post_kill_restored, "episode_04_ep04_reward_cache")
        _advance(post_kill_restored, 0.3)

        quest_state = post_kill_restored["quest_runner"].get_quest_state(QUEST_ID)
        assert quest_state is not None
        assert quest_state.status == "completed"

    def test_episode_04_determinism_digest_and_events(self) -> None:
        first = _run_episode("hard")
        second = _run_episode("hard")

        assert first["digests"] == second["digests"]
        assert first["events"] == second["events"]
        assert first["quest_status"] == second["quest_status"] == "completed"
