from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.interaction import get_interact_prompt


class _StubBehaviour:
    def on_interact(self, _window, _actor=None) -> None:
        return


class _StubEntity:
    def __init__(self, *, label: str) -> None:
        self.mesh_entity_data = {"name": label}
        self.mesh_behaviours_runtime = [_StubBehaviour()]


def _make_window(input_source: str):
    manager = SimpleNamespace(input_source=input_source)
    controller = SimpleNamespace(manager=manager)
    return SimpleNamespace(input_controller=controller)


@pytest.mark.fast
def test_interact_prompt_hidden_when_none() -> None:
    window = _make_window("keyboard_mouse")
    assert get_interact_prompt(window, None) is None


@pytest.mark.fast
def test_interact_prompt_keyboard_hint_and_label() -> None:
    window = _make_window("keyboard_mouse")
    entity = _StubEntity(label="Chest")
    text = get_interact_prompt(window, entity)
    assert text == "E: Interact: Chest"


@pytest.mark.fast
def test_interact_prompt_gamepad_hint() -> None:
    window = _make_window("gamepad")
    entity = _StubEntity(label="Door")
    text = get_interact_prompt(window, entity)
    assert text == "A: Interact: Door"
