from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.interaction import get_interact_prompt, resolve_interaction_candidate
from engine.ui_overlays import hud
from engine.ui_overlays.hud import InteractPromptOverlay
from engine.ui_overlays.providers import interact_prompt_provider


class _StubBehaviour:
    def on_interact(self, _window, _actor=None) -> None:
        return


class _StubEntity:
    def __init__(self, *, label: str, x: float = 24.0, interact_label: str | None = None) -> None:
        self.center_x = x
        self.center_y = 0.0
        self.width = 16.0
        self.height = 16.0
        self.mesh_entity_data = {"id": label.lower(), "name": label}
        if interact_label is not None:
            self.mesh_entity_data["interact_label"] = interact_label
        self.mesh_behaviours_runtime = [_StubBehaviour()]


def _make_window(input_source: str):
    manager = SimpleNamespace(input_source=input_source)
    controller = SimpleNamespace(manager=manager)
    return SimpleNamespace(input_controller=controller)


def _make_runtime_window(
    *,
    player_input_blocked: bool = False,
    ui_blocked: bool = False,
    dialogue_active: bool = False,
    dialogue_blocks: bool = False,
) -> SimpleNamespace:
    actor = SimpleNamespace(
        center_x=0.0,
        center_y=0.0,
        width=16.0,
        height=16.0,
        mesh_entity_data={"id": "player", "facing": "right"},
        mesh_behaviours_runtime=[],
    )
    target = _StubEntity(label="Chest")
    manager = SimpleNamespace(input_source="keyboard_mouse")
    window = SimpleNamespace(
        input_controller=SimpleNamespace(manager=manager),
        player=actor,
        all_sprites=[actor, target],
        scene_controller=SimpleNamespace(_find_player_sprite=lambda: actor, all_sprites=[actor, target]),
        get_flag=lambda _name, default=False: default,
        player_input_blocked=lambda: player_input_blocked,
        ui_controller=SimpleNamespace(input_blocked=ui_blocked),
        dialogue_controller=SimpleNamespace(active=dialogue_active),
        dialogue_blocks_input=lambda: dialogue_blocks,
    )
    return window


@pytest.fixture
def prompt_draw_sink(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    drawn: list[str] = []
    monkeypatch.setattr(hud, "_draw_rectangle_filled", lambda **_kwargs: None)
    monkeypatch.setattr(hud, "_draw_tb_rectangle_outline", lambda *_args, **_kwargs: None)

    def _draw_text(text: str, *_args: Any, **_kwargs: Any) -> None:
        drawn.append(text)

    monkeypatch.setattr(hud.optional_arcade.arcade, "draw_text", _draw_text)
    return drawn


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


@pytest.mark.fast
def test_interact_prompt_overlay_provider_suppression_does_not_resolve_again(
    monkeypatch: pytest.MonkeyPatch,
    prompt_draw_sink: list[str],
) -> None:
    window = _make_runtime_window()

    def _unexpected_resolve(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("overlay must not resolve after provider returned None")

    monkeypatch.setattr("engine.entity_select_mode.other_authoring_modes_active", lambda _window: True)
    monkeypatch.setattr("engine.interaction.resolve_interaction_candidate", _unexpected_resolve)
    InteractPromptOverlay(window, provider=interact_prompt_provider).draw()
    assert prompt_draw_sink == []


@pytest.mark.fast
@pytest.mark.parametrize(
    "window_kwargs",
    (
        {"player_input_blocked": True},
        {"ui_blocked": True},
        {"dialogue_active": True},
        {"dialogue_blocks": True},
    ),
)
def test_interact_prompt_overlay_respects_provider_blocking_signals(
    monkeypatch: pytest.MonkeyPatch,
    prompt_draw_sink: list[str],
    window_kwargs: dict[str, bool],
) -> None:
    window = _make_runtime_window(**window_kwargs)
    monkeypatch.setattr("engine.entity_select_mode.other_authoring_modes_active", lambda _window: False)

    def _unexpected_resolve(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("blocked provider must not query a candidate")

    monkeypatch.setattr("engine.interaction.resolve_interaction_candidate", _unexpected_resolve)
    InteractPromptOverlay(window, provider=interact_prompt_provider).draw()
    assert prompt_draw_sink == []


@pytest.mark.fast
def test_interact_prompt_overlay_suppresses_provider_exception(
    monkeypatch: pytest.MonkeyPatch,
    prompt_draw_sink: list[str],
) -> None:
    window = _make_runtime_window()

    def _provider(_window: Any) -> None:
        raise ValueError("provider failed")

    def _unexpected_resolve(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("provider exception must not fall through to direct resolution")

    monkeypatch.setattr("engine.interaction.resolve_interaction_candidate", _unexpected_resolve)
    InteractPromptOverlay(window, provider=_provider).draw()
    assert prompt_draw_sink == []


@pytest.mark.fast
def test_interact_prompt_overlay_no_candidate_from_provider_does_not_resolve_twice(
    monkeypatch: pytest.MonkeyPatch,
    prompt_draw_sink: list[str],
) -> None:
    window = _make_runtime_window()
    calls = 0

    def _resolve(_window: Any) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("overlay must not query after provider returned None")
        return None

    monkeypatch.setattr("engine.entity_select_mode.other_authoring_modes_active", lambda _window: False)
    monkeypatch.setattr("engine.interaction.resolve_interaction_candidate", _resolve)
    InteractPromptOverlay(window, provider=interact_prompt_provider).draw()
    assert calls == 1
    assert prompt_draw_sink == []


@pytest.mark.fast
def test_interact_prompt_overlay_provider_payload_renders_candidate(prompt_draw_sink: list[str]) -> None:
    window = _make_window("keyboard_mouse")
    entity = _StubEntity(label="Chest")

    InteractPromptOverlay(window, provider=lambda _window: entity).draw()

    assert prompt_draw_sink == ["E: Interact: Chest"]


@pytest.mark.fast
def test_interact_prompt_overlay_without_provider_uses_legacy_direct_resolution(
    monkeypatch: pytest.MonkeyPatch,
    prompt_draw_sink: list[str],
) -> None:
    window = _make_runtime_window()
    candidate = resolve_interaction_candidate(window)
    assert candidate is not None
    monkeypatch.setattr("engine.interaction.resolve_interaction_candidate", lambda _window: candidate)

    InteractPromptOverlay(window).draw()

    assert prompt_draw_sink == ["E: Interact: Chest"]


@pytest.mark.fast
def test_generic_interact_label_falls_back_to_name_without_duplication() -> None:
    window = _make_window("keyboard_mouse")
    entity = _StubEntity(label="Chest", interact_label="Interact")

    assert get_interact_prompt(window, entity) == "E: Interact: Chest"


@pytest.mark.fast
def test_generic_interact_label_without_name_omits_object_label() -> None:
    window = _make_window("keyboard_mouse")
    entity = _StubEntity(label="ignored", interact_label="Interact")
    entity.mesh_entity_data.pop("name")
    entity.mesh_name = ""

    assert get_interact_prompt(window, entity) == "E: Interact"
