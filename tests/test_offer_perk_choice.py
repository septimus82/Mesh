
import arcade

from engine.behaviours.offer_perk_choice import OfferPerkChoice
from engine.events import MeshEvent
from engine.input import InputManager
from engine.perks import PerkManager


class StubDialogueBox:
    def __init__(self) -> None:
        self._owner: str | None = None
        self._visible = False
        self._current_entry: dict | None = None
        self._queue: list[dict] = []
        self._choice_index = 0

    def is_active_for(self, owner: str) -> bool:
        return self._visible and self._owner == owner

    def play(self, entries, *, owner: str) -> bool:
        entries = [dict(entry) for entry in entries or [] if isinstance(entry, dict) and entry.get("text")]
        if not entries:
            self.clear(owner=owner)
            return False
        self._owner = owner
        self._visible = True
        self._current_entry = entries[0]
        self._queue = entries[1:]
        self._choice_index = 0
        return True

    def clear(self, *, owner: str | None = None) -> None:
        if owner is not None and owner != self._owner:
            return
        self._owner = None
        self._visible = False
        self._current_entry = None
        self._queue = []
        self._choice_index = 0

    def has_choices(self) -> bool:
        if not self._visible or self._current_entry is None:
            return False
        return bool(self._current_entry.get("choices"))

    def move_choice_cursor(self, delta: int, *, owner: str | None = None) -> int | None:  # noqa: ARG002
        if not self.has_choices():
            return None
        choices = self._current_entry.get("choices") or []
        if not choices:
            return None
        self._choice_index = (self._choice_index + int(delta)) % len(choices)
        return self._choice_index

    def submit_choice(self, *, owner: str | None = None) -> dict | None:  # noqa: ARG002
        if not self.has_choices():
            return None
        choices = self._current_entry.get("choices") or []
        if not choices:
            return None
        choice = choices[self._choice_index]
        if bool(choice.get("disabled")):
            return None
        return dict(choice)

    def advance(self, *, owner: str | None = None) -> bool:
        if owner is not None and owner != self._owner:
            return False
        if not self._visible:
            return False
        if self.has_choices():
            return False
        if self._queue:
            self._current_entry = self._queue.pop(0)
            return True
        self.clear(owner=owner)
        return False


class StubUIController:
    def __init__(self) -> None:
        self.dialogue_box = StubDialogueBox()


class StubGameState:
    def __init__(self, perk_manager: PerkManager) -> None:
        self.perk_manager = perk_manager
        self._perks: set[str] = set()

    def has_perk(self, perk_id: str) -> bool:
        return perk_id in self._perks

    def add_perk(self, perk_id: str) -> None:
        self._perks.add(str(perk_id))


class StubWindow:
    def __init__(self, perk_manager: PerkManager) -> None:
        self.game_state_controller = StubGameState(perk_manager)
        self.ui_controller = StubUIController()
        self.input = InputManager()
        self.input.bind("interact", arcade.key.E)
        self.input.bind("move_up", arcade.key.W)
        self.input.bind("move_down", arcade.key.S)

    def show_dialogue(self, entries, *, owner: str) -> bool:
        return self.ui_controller.dialogue_box.play(entries, owner=owner)

    def close_dialogue(self, *, owner: str | None = None) -> None:
        self.ui_controller.dialogue_box.clear(owner=owner)


class DummyEntity:
    def __init__(self) -> None:
        self.mesh_name = "PerkShrine"
        self.mesh_entity_data = {}


class DummyActor:
    def __init__(self) -> None:
        self.mesh_name = "Player"


def _tap(window: StubWindow, behaviour: OfferPerkChoice, key: int, *, dt: float = 0.25) -> None:
    window.input.press(key)
    window.input.update(0.016)
    behaviour.update(dt)
    window.input.release(key)
    window.input.update(0.016)
    behaviour.update(0.016)


def test_offer_perk_choice_interact_signature_starts_dialogue_and_allows_selection():
    perks = PerkManager()
    perks.register_perk({"id": "vitality_boost", "name": "Vitality", "description": "More HP"})
    window = StubWindow(perks)
    entity = DummyEntity()
    behaviour = OfferPerkChoice(entity, window, pool=["vitality_boost"])

    behaviour.on_interact(window, DummyActor())
    assert window.ui_controller.dialogue_box.is_active_for(behaviour._owner_id)

    _tap(window, behaviour, arcade.key.E, dt=0.25)
    assert window.ui_controller.dialogue_box.is_active_for(behaviour._owner_id) is False
    assert window.game_state_controller.has_perk("vitality_boost") is True


def test_offer_perk_choice_on_event_accepts_mesh_event():
    perks = PerkManager()
    window = StubWindow(perks)
    entity = DummyEntity()
    behaviour = OfferPerkChoice(entity, window, start_event="offer_perk")
    behaviour.on_event(MeshEvent(type="enemy_attack", payload={}))
    assert window.ui_controller.dialogue_box._visible is False


def test_offer_perk_choice_message_only_can_close_with_interact():
    perks = PerkManager()
    window = StubWindow(perks)
    entity = DummyEntity()
    behaviour = OfferPerkChoice(entity, window, pool=[])

    behaviour.on_interact(window, DummyActor())
    assert window.ui_controller.dialogue_box.is_active_for(behaviour._owner_id)
    assert window.ui_controller.dialogue_box.has_choices() is False

    _tap(window, behaviour, arcade.key.E, dt=0.25)
    assert window.ui_controller.dialogue_box.is_active_for(behaviour._owner_id) is False
