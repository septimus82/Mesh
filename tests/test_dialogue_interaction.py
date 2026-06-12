import engine.optional_arcade as optional_arcade
from engine.behaviours.dialogue import Dialogue
from engine.input import InputManager


class DummyWindow:
    def __init__(self) -> None:
        self.width = 800
        self.height = 600
        self.input = InputManager()
        self.input.bind("interact", optional_arcade.arcade.key.E)
        self.dialogue_box = StubDialogueBox()

    def emit_signal(self, *_args, **_kwargs) -> None:  # pragma: no cover - stub
        return


class StubDialogueBox:
    def __init__(self) -> None:
        self._queue: list[dict] = []
        self._owner: str | None = None
        self._visible = False
        self._current_entry: dict | None = None

    def is_active(self) -> bool:
        return self._visible

    def is_active_for(self, owner: str) -> bool:
        return self._visible and self._owner == owner

    def get_current_entry(self) -> dict | None:
        if not self._visible or self._current_entry is None:
            return None
        return dict(self._current_entry)

    def has_choices(self) -> bool:
        if not self._visible or self._current_entry is None:
            return False
        choices = self._current_entry.get("choices")
        return bool(choices)

    def play(self, entries, *, owner: str) -> bool:
        entries = [dict(entry) for entry in entries or [] if isinstance(entry, dict) and entry.get("text")]
        if not entries:
            self.clear(owner=owner)
            return False
        self._owner = owner
        self._visible = True
        self._current_entry = entries[0]
        self._queue = entries[1:]
        return True

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

    def clear(self, *, owner: str | None = None) -> None:
        if owner is not None and owner != self._owner:
            return
        self._queue = []
        self._owner = None
        self._visible = False
        self._current_entry = None


class DummyEntity:
    def __init__(self, name: str, dialogue_lines: list[str]) -> None:
        self.mesh_name = name
        self.mesh_entity_data = {"dialogue_lines": dialogue_lines}


def _tap_interact(window: DummyWindow, behaviour: Dialogue) -> None:
    window.input.press(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    behaviour.update(0.016)
    window.input.release(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    behaviour.update(0.016)


def test_dialogue_advances_with_interact_while_active():
    window = DummyWindow()
    entity = DummyEntity("Guide", ["Hello there.", "Good luck."])
    behaviour = Dialogue(entity, window)

    window.input.press(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    actor = DummyEntity("Player", [])
    behaviour.on_interact(window, actor)
    behaviour.update(0.016)
    assert window.dialogue_box.is_active() is True
    assert window.dialogue_box.get_current_entry()["text"] == "Hello there."

    window.input.release(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    behaviour.update(0.016)

    _tap_interact(window, behaviour)
    assert window.dialogue_box.is_active() is True
    assert window.dialogue_box.get_current_entry()["text"] == "Good luck."

    _tap_interact(window, behaviour)
    assert window.dialogue_box.is_active() is False


def test_dialogue_does_not_autoadvance_on_start_press():
    window = DummyWindow()
    entity = DummyEntity("Guide", ["Hello there.", "Good luck."])
    behaviour = Dialogue(entity, window)

    window.input.press(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    behaviour.on_interact(window, DummyEntity("Player", []))
    behaviour.update(0.016)

    assert window.dialogue_box.is_active() is True
    assert window.dialogue_box.get_current_entry()["text"] == "Hello there."

    window.input.release(optional_arcade.arcade.key.E)
    window.input.update(0.016)
    behaviour.update(0.016)
