from __future__ import annotations

import json
import types
from pathlib import Path

from engine.behaviours.scene_transition import SceneTransition
from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent
from engine.events import MeshEvent, MeshEventBus
from engine.savegame import SaveGameV1, load_savegame, save_savegame
from engine.ui import compute_objective_tracker_lines


class _Window:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self._flags: dict[str, bool] = {}
        self.flag_calls: list[tuple[str, bool]] = []
        self.player_hud = types.SimpleNamespace(toasts=[])
        self.player_hud.enqueue_toast = lambda message, *, seconds=4.0: self.player_hud.toasts.append(str(message))  # type: ignore[assignment]  # noqa: ARG005
        self.next_spawn: str | None = None
        self.scene_changes: list[str] = []

    @property
    def game_state(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(flags=dict(self._flags))

    def set_next_spawn_point(self, spawn_id: str) -> None:
        self.next_spawn = str(spawn_id)

    def request_scene_change(self, scene_path: str) -> None:
        self.scene_changes.append(str(scene_path))

    def emit_event(self, event) -> None:  # noqa: ANN001
        self.event_bus.emit_event(event)

    def emit_signal(self, event_type: str, **payload) -> None:  # noqa: ANN003
        from engine.event_runtime.emit import emit_event

        emit_event(self, event_type, dict(payload))

    def set_flag(self, name: str, value: bool = True) -> None:
        key = str(name)
        val = bool(value)
        self._flags[key] = val
        self.flag_calls.append((key, val))

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(str(name), default))


def _load_scene(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_entity(scene: dict, predicate) -> dict:  # noqa: ANN001
    for entity in scene.get("entities", []):
        if predicate(entity):
            return entity
    raise AssertionError("matching entity not found")


def test_upper_hall_lever_sets_flag_once_and_unlocks_vault_transition(tmp_path: Path) -> None:
    scene = _load_scene("scenes/upper_hall.json")

    lever = _find_entity(scene, lambda e: e.get("name") == "UpperHallLever")
    lever_nodes = lever["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    assert any(
        choice.get("id") == "demo_upper_hall_pull_lever"
        for choice in lever_nodes["root"]["choices"]
        if isinstance(choice, dict)
    )

    lever_hook = _find_entity(
        scene,
        lambda e: (
            isinstance(e.get("behaviour_config"), dict)
            and isinstance(e["behaviour_config"].get("SetGameStateOnEvent"), dict)
            and e["behaviour_config"]["SetGameStateOnEvent"].get("event_type") == "dialogue_choice"
            and e["behaviour_config"]["SetGameStateOnEvent"].get("payload_value") == "demo_upper_hall_pull_lever"
        ),
    )
    lever_hook_cfg = lever_hook["behaviour_config"]["SetGameStateOnEvent"]

    window = _Window()
    hook_entity = types.SimpleNamespace(mesh_entity_data=lever_hook, mesh_name=lever_hook.get("name", "Hook"))
    SetGameStateOnEvent(hook_entity, window, **lever_hook_cfg)

    assert window.get_flag("demo.upper_hall_lever_pulled") is False
    window.emit_signal("dialogue_choice", entity="UpperHallLever", choice_id="demo_upper_hall_pull_lever")
    assert window.get_flag("demo.upper_hall_lever_pulled") is True
    assert [k for k, _ in window.flag_calls].count("demo.upper_hall_lever_pulled") == 1
    assert window.player_hud.toasts == ["Pulled the lever"]

    window.emit_signal("dialogue_choice", entity="UpperHallLever", choice_id="demo_upper_hall_pull_lever")
    assert [k for k, _ in window.flag_calls].count("demo.upper_hall_lever_pulled") == 1
    assert window.player_hud.toasts == ["Pulled the lever"]

    door = _find_entity(scene, lambda e: e.get("name") == "UpperHallVaultDoor")
    door_dialogue = door["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    root_choices = [c for c in door_dialogue["root"]["choices"] if isinstance(c, dict)]
    open_choice = next(c for c in root_choices if c.get("id") == "demo_upper_hall_vault_open")
    locked_choice = next(c for c in root_choices if c.get("id") == "demo_upper_hall_vault_locked")
    assert open_choice.get("require_flags") == ["demo.upper_hall_lever_pulled"]
    assert locked_choice.get("forbid_flags") == ["demo.upper_hall_lever_pulled"]
    assert locked_choice.get("next") == "locked"
    assert "locked" in str(door_dialogue["locked"]["text"]).lower()

    transition_cfg = door["behaviour_config"]["SceneTransition"]

    def _choice_available(choice: dict, flags: dict[str, bool]) -> bool:
        for flag in choice.get("require_flags") or []:
            if not bool(flags.get(str(flag), False)):
                return False
        for flag in choice.get("forbid_flags") or []:
            if bool(flags.get(str(flag), False)):
                return False
        return True

    assert _choice_available(open_choice, {"demo.upper_hall_lever_pulled": False}) is False
    assert _choice_available(locked_choice, {"demo.upper_hall_lever_pulled": False}) is True
    assert _choice_available(open_choice, {"demo.upper_hall_lever_pulled": True}) is True
    assert _choice_available(locked_choice, {"demo.upper_hall_lever_pulled": True}) is False

    door_window = _Window()
    door_sprite = types.SimpleNamespace(mesh_entity_data=door, mesh_name=door.get("name", "Door"))
    transition = SceneTransition(door_sprite, door_window, **transition_cfg)

    transition.on_event(MeshEvent(type="dialogue_choice", payload={"choice_id": "demo_upper_hall_vault_locked"}))
    assert door_window.scene_changes == []

    door_window.set_flag("demo.upper_hall_lever_pulled", True)
    transition.on_event(MeshEvent(type="dialogue_choice", payload={"choice_id": "demo_upper_hall_vault_open"}))
    assert door_window.next_spawn == "vault_entry"
    assert door_window.scene_changes == ["scenes/upper_hall_vault.json"]

    vault_scene = _load_scene("scenes/upper_hall_vault.json")
    vault_marker = _find_entity(vault_scene, lambda e: e.get("spawn_id") == "vault_entry")
    assert vault_marker.get("tag") == "spawn_point"

    tracker_window = _Window()
    tracker_window.set_flag("demo.objective_upper_started", True)
    assert compute_objective_tracker_lines(tracker_window.get_flag) == ["Optional: Visit the upper hall"]

    tracker_window.set_flag("demo.reached_upper_hall", True)
    assert compute_objective_tracker_lines(tracker_window.get_flag) == ["Optional: Pull the lever"]

    tracker_window.set_flag("demo.upper_hall_lever_pulled", True)
    assert compute_objective_tracker_lines(tracker_window.get_flag) == ["Optional: Enter the vault"]

    tracker_window.set_flag("demo.reached_upper_hall_vault", True)
    assert compute_objective_tracker_lines(tracker_window.get_flag) == []

    save_path = tmp_path / "savegame.json"
    save = SaveGameV1(
        scene_path="scenes/upper_hall.json",
        player_x=1.0,
        player_y=2.0,
        flags={
            "demo.objective_upper_started": True,
            "demo.upper_hall_lever_pulled": True,
        },
    )
    save_savegame(save_path, save)
    loaded = load_savegame(save_path)
    assert loaded is not None
    assert loaded.flags["demo.objective_upper_started"] is True
    assert loaded.flags["demo.upper_hall_lever_pulled"] is True
