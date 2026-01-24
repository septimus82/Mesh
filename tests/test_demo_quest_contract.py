from __future__ import annotations

from types import SimpleNamespace

from engine.behaviours.quest_progress import QuestProgressOnEvent
from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent
from engine.events import MeshEvent, MeshEventBus
from engine.quests import QuestManager


class _StubGameStateController:
    def __init__(self) -> None:
        self.state = SimpleNamespace(values={})
        self._flags: dict[str, bool] = {}
        self._counters: dict[str, float] = {}

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self._flags.get(name, default)

    def set_flag(self, name: str, value: bool) -> None:
        self._flags[str(name)] = bool(value)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        key = str(name)
        self._counters[key] = self._counters.get(key, 0.0) + float(amount)
        return self._counters[key]

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return float(self._counters.get(str(name), default))

    def get_quest_counter(self, quest_id: str, counter: str) -> float:  # noqa: ARG002
        return 0.0

    def add_xp(self, amount: float) -> None:
        self.inc_counter("xp", float(amount))


class _StubWindow:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self.game_state_controller = _StubGameStateController()
        self._signals: list[MeshEvent] = []
        self.quest_manager = QuestManager(self)

    @property
    def game_state(self):
        return self.game_state_controller.state

    def emit_signal(self, event_type: str, **payload):
        self._signals.append(MeshEvent(type=str(event_type), payload=dict(payload)))

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def set_flag(self, name: str, value: bool) -> None:
        self.game_state_controller.set_flag(name, value)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


class _StubEntity:
    def __init__(self) -> None:
        self.mesh_entity_data = {}


def test_demo_ridge_intro_contract() -> None:
    window = _StubWindow()
    quest_id = "demo_ridge_intro"
    assert quest_id in window.quest_manager._definitions

    entity = _StubEntity()
    start = QuestProgressOnEvent(
        entity,
        window,
        quest_id=quest_id,
        action="start",
        stage_id="find_key",
        event_type="dialogue_choice",
        payload_equals={"entity": "RidgeScout", "choice_id": "demo_ridge_intro_start"},
        once=True,
    )
    pickup_progress = QuestProgressOnEvent(
        entity,
        window,
        quest_id=quest_id,
        action="complete_stage",
        stage_id="find_key",
        event_type="collected",
        payload_field="collectible",
        payload_value="RustedKey",
        once=True,
    )
    turnin = QuestProgressOnEvent(
        entity,
        window,
        quest_id=quest_id,
        action="complete_stage",
        stage_id="return_key",
        event_type="dialogue_choice",
        payload_equals={"entity": "RidgeScout", "choice_id": "demo_ridge_intro_turnin"},
        once=True,
    )
    set_flag = SetGameStateOnEvent(
        entity,
        window,
        event_type="collected",
        payload_field="collectible",
        payload_value="RustedKey",
        set_flags={"demo_ridge_found_key": True},
    )

    start_event = MeshEvent(
        type="dialogue_choice",
        payload={"entity": "RidgeScout", "choice_id": "demo_ridge_intro_start"},
    )
    start.on_event(start_event)
    assert window.quest_manager.is_quest_active(quest_id)
    stage = window.quest_manager.get_current_stage(quest_id)
    assert stage is not None
    assert stage["id"] == "find_key"

    pickup_event = MeshEvent(type="collected", payload={"collectible": "RustedKey"})
    set_flag.on_event(pickup_event)
    pickup_progress.on_event(pickup_event)
    assert window.get_flag("demo_ridge_found_key", False) is True
    stage = window.quest_manager.get_current_stage(quest_id)
    assert stage is not None
    assert stage["id"] == "return_key"

    turnin_event = MeshEvent(
        type="dialogue_choice",
        payload={"entity": "RidgeScout", "choice_id": "demo_ridge_intro_turnin"},
    )
    turnin.on_event(turnin_event)
    assert window.quest_manager.is_quest_completed(quest_id)
    assert window.get_flag("demo_ridge_intro_complete", False) is True
