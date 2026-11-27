"""#743: a cutscene's ``start_dialogue`` lines step on with the interact key, so ``wait_dialogue_end`` ends.

The cutscene shows its lines as owner ``"cutscene"``; the Dialogue behaviour and SequencePlayer only advance their own
boxes, and nothing advanced the cutscene's: the box stayed on its first line and the game soft-locked. Played in a real
hidden game (tests/_real_game.py) with keys sent through the window: the player stands beside a talking Elder, so the
press that closes the cutscene's last line must not also start the Elder's conversation in the same frame.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import engine.optional_arcade as optional_arcade
from tests._real_game import RealGame, author, new_project, place, real_game

pytestmark = [
    pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
    pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)"),
]

ROOM = "Square"


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    base = tmp_path_factory.mktemp("cutscene_dialogue")
    project = new_project(base / "game")
    author(project, project.add_room(ROOM), place("Elder", 160, 100) + [
        {"op": "set_dialogue_text", "entity_id": "@0", "text": "Welcome."},
        {"op": "add_line", "entity_id": "@0", "text": "Mind the well."}])
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    g = running.resume()
    g.enter(g.room(ROOM))
    g.window.cutscene_controller.stop()
    g.window.ui_controller.close_dialogue()
    g.window.set_flag("after_cutscene", False)
    g.stand_by("Elder")
    return g


def _text(g: RealGame) -> str | None:
    entry = g.window.ui_controller.dialogue_box.get_current_entry()
    return entry.get("text") if entry else None


def _play(g: RealGame, lines: list[str]) -> None:
    cc = g.window.cutscene_controller
    cc.register_cutscenes([{"id": "talk", "steps": [
        {"type": "start_dialogue", "lines": [{"speaker": "Narrator", "text": line} for line in lines]},
        {"type": "wait_dialogue_end"},
        {"type": "set_flag", "name": "after_cutscene"}]}])
    assert cc.play_cutscene("talk")
    g.frames(3)
    assert _text(g) == lines[0]
    assert g.window.player_input_blocked()


def _walks(g: RealGame) -> bool:
    hero = g.player()
    before = (hero.center_x, hero.center_y)
    g.key("S", 10)
    return (hero.center_x, hero.center_y) != before


def _finished_cleanly(g: RealGame) -> None:
    assert not g.window.ui_controller.is_dialogue_active(), f"a box is still open: {_text(g)!r}"
    assert not g.window.cutscene_controller.is_running
    assert g.flag("after_cutscene"), "the step after wait_dialogue_end ran"
    assert not g.events("dialogue_started"), "the closing press didn't also talk to the Elder"
    assert not g.window.player_input_blocked()
    assert _walks(g), "the player can move again"


def test_the_interact_key_steps_through_a_cutscenes_lines_and_the_cutscene_goes_on(game: RealGame) -> None:
    _play(game, ["Line one.", "Line two."])
    assert not _walks(game), "the player can't walk away while the cutscene talks"
    game.key("E")
    assert _text(game) == "Line two."
    assert game.window.cutscene_controller.is_running and not game.flag("after_cutscene")
    game.key("E")
    game.frames(3)
    _finished_cleanly(game)


def test_a_one_line_cutscene_dialogue_closes_on_one_press(game: RealGame) -> None:
    _play(game, ["Only line."])
    game.key("E")
    game.frames(3)
    _finished_cleanly(game)


def test_a_press_on_the_frame_the_box_opens_does_not_skip_its_first_line(game: RealGame) -> None:
    cc = game.window.cutscene_controller
    cc.register_cutscenes([{"id": "mash", "steps": [{"type": "start_dialogue", "lines": [{"text": "First."}, {"text": "Second."}]},
                                                    {"type": "wait_dialogue_end"}]}])
    assert cc.play_cutscene("mash")
    game.key("E")  # (held on the cutscene's first frame: the frame its box opens)
    assert _text(game) == "First."


def test_an_objects_conversation_still_advances_with_the_interact_key(game: RealGame) -> None:
    game.key("E")
    game.frames(2)
    assert _text(game) == "Welcome."
    game.key("E")
    assert _text(game) == "Mind the well."
    game.key("E")
    game.frames(2)
    assert not game.window.ui_controller.is_dialogue_active()
