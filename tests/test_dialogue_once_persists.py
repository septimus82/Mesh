"""#620 (S1 4.2, owner decision D6): an "Only once" conversation, and a "Choice once" reward, stay spent.

The once-memory lived only on the Dialogue behaviour object, and a room is rebuilt from its file on every entry: the
conversation could be had again, and the reward paid again (50 gold, then 100), after leaving and re-entering the room
or loading a save. Dialogue now keeps both as room memory facts (``FACT_FIELDS``: ``played``, ``spent_choices``),
recorded the moment they happen; a choice is remembered by its line and its own id, or its words (never its position).

A generated project (``mesh new --template adventure``: a Village and a House) whose conversations are authored through
Mesh Studio's project model and ops, played through its own ``main.py`` in a real hidden window: the interact key's
interaction (``perform_interaction``) opens a conversation, keys sent to the window pick a choice or end it.

- The Sign: an "Only once" conversation of one line.
- The Guide: a conversation had any number of times, with "Thank you" ("Choice once", gold +50) and "Goodbye".
- A Shopkeeper: an "Only once" conversation and a shop (#682, D2: once the talk is spent, E opens the shop).
- The Elder: an "Only once" conversation whose reward choice (+50 gold) isn't "Choice once", then a farewell line.

An "Only once" conversation is spent when it completes, not when it opens: one closed early or saved mid-way (the
review of #688: a save from the pause menu over the conversation lost its reward for good) can be had again. Its
choices that change something are used up the moment they're taken, so a save after the reward can't pay it twice.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

import engine.optional_arcade as optional_arcade
from engine.save_manager import SaveManager
from engine.scene_runtime import room_memory
from tests.test_project_scaffolding_data import START, _Game, _new, _play
from tests.test_shopkeeper_opens import _Shop, _talking

pytestmark = [pytest.mark.integration,  # (generated projects in temporary folders; hidden game windows)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dialogue_once" / "pre_facts_slot.json"
GUIDE = "start_guide_320_128_0_0"
SIGN = "start_sign_336_240_0_0"
PICTURE = "assets/sprites/starter_sign.png"
POTIONS = [{"item_id": "healing_potion", "price": 5, "quantity": 3}]


def _edit(root: Path, *changes: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Edits to the Village through Mesh Studio's project model, saved as Studio saves them."""
    from engine.editor import project_ownership
    from engine.studio_project import Project

    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)
        assert project.current == "start"
        for change in changes:
            project.edit_scene(change)
        project.save(owner=held)


def _author(root: Path) -> None:
    from engine import project_ops as ops

    def shopkeeper(scene: dict[str, Any]) -> dict[str, Any]:
        scene, ident = ops.place_blank(scene, "start", "Shopkeeper", 160.0, 240.0)
        scene = ops.set_picture(scene, ident, PICTURE)
        scene = ops.set_dialogue_text(scene, ident, "Fine wares, friend.")
        scene = ops.set_conversation(scene, ident, once=True)  # "Only once"
        scene = ops.add_behaviour(scene, ident, "Vendor")
        return ops.set_behaviour_param(scene, ident, "Vendor", "stock", POTIONS)

    def elder(scene: dict[str, Any]) -> dict[str, Any]:
        scene, ident = ops.place_blank(scene, "start", "Elder", 480.0, 336.0)
        scene = ops.set_picture(scene, ident, PICTURE)
        scene = ops.set_dialogue_text(scene, ident, "You saved the village. Take this.")
        scene = ops.set_conversation(scene, ident, once=True)  # "Only once"
        scene, farewell = ops.add_line(scene, ident, text="Safe travels.", link=False)
        scene = ops.add_choice(scene, ident, "root", "Thank you")
        # (not "Choice once": the conversation being "Only once" is what keeps it from paying twice)
        return ops.set_choice(scene, ident, "root", 0, add_counters="gold+50", next_line=farewell)

    _edit(root,
          lambda s: ops.set_conversation(s, SIGN, once=True),
          lambda s: ops.add_choice(s, GUIDE, "root", "Thank you"),
          lambda s: ops.set_choice(s, GUIDE, "root", 0, once=True, add_counters="gold+50"),  # "Choice once"
          lambda s: ops.add_choice(s, GUIDE, "root", "Goodbye"),
          shopkeeper, elder)


def _house(root: Path) -> str:
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    scenes = json.loads((root / world_file).read_text(encoding="utf-8"))["scenes"]
    return str(next(entry["path"] for key, entry in scenes.items() if key != "start"))


def _key(name: str) -> int:
    return int(getattr(optional_arcade.arcade.key, name))


class _Player:
    """The game played: talking (the interact key's interaction), choosing, leaving and coming back, saving."""

    def __init__(self, game: _Game, root: Path) -> None:
        self.game, self.root, self.house = game, root, _house(root)
        game.window.save_manager = SaveManager(game.window, save_dir=root / "saves")  # (the test's own folder)

    def talk(self, name: str) -> bool:
        """Stand beside ``name`` and interact; whether a conversation opened."""
        from engine.interaction import perform_interaction

        target, hero = self.game.named(name), self.game.sc._find_player_sprite()
        hero.center_x, hero.center_y = target.center_x - 40, target.center_y
        self.game.step(2)
        perform_interaction(self.game.window, actor=hero)
        self.game.step(3)
        return _talking(self.game)

    def choices(self) -> dict[str, bool]:
        """The open line's choices: whether each can be picked."""
        box = self.game.window.ui_controller.dialogue_box
        return {str(c["text"]): not c.get("disabled") for c in box.get_choices()}

    def choose(self, text: str) -> None:
        box = self.game.window.ui_controller.dialogue_box
        texts = [c["text"] for c in box.get_choices()]
        want = texts.index(text)
        for _ in range(len(texts)):
            if box.get_choice_cursor() == want:
                break
            self.game.press(_key("DOWN"))
        assert box.get_choice_cursor() == want
        self.game.press(_key("E"))
        self.game.step(5)

    def finish(self) -> None:
        """E on the conversation's last line (no choice left to pick): it ends."""
        self.game.press(_key("E"))
        self.game.step(5)

    def cut_off(self) -> None:
        """The conversation closed before its end (the way loading a save closes the box)."""
        self.game.window.ui_controller.reset_transient_state()
        self.game.step(10)

    def leave_and_return(self) -> None:
        self.game.sc.load_scene(self.house)
        self.game.step(3)
        self.game.sc.load_scene(START)
        self.game.step(3)

    def save(self, slot: str) -> None:
        assert self.game.window.save_manager.save_game(slot)

    def load(self, slot: str) -> None:
        """A player's Continue: the saved room loads on the next frame."""
        assert self.game.window.save_manager.load_game(slot)
        self.game.step(5)

    def gold(self) -> float:
        return float(self.game.gs.get_counter("gold", 0))

    def facts(self, entity_id: str) -> Any:
        entry = (self.game.gs.get_var(room_memory.VAR) or {}).get(START) or {}
        return ((entry.get("facts") or {}).get(entity_id) or {}).get("Dialogue")

    def facts_of(self, name: str) -> Any:
        return self.facts(self.game.named(name).mesh_id)


def _sessions(root: Path, monkeypatch: pytest.MonkeyPatch, *drives: Callable[[_Player], None]) -> None:
    """Each drive in its own run of the game (a fresh window: the game quit in between)."""
    for drive in drives:
        _play(root, monkeypatch, lambda game, d=drive: d(_Player(game, root)))


@pytest.fixture()
def game_root(tmp_path: Path) -> Path:
    root = _new(tmp_path, "adventure")
    _author(root)
    return root


# --------------------------------------------------------------------- "Only once" conversation

def test_an_only_once_conversation_stays_spent_after_reentry_and_after_save_load(
        game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def first(play: _Player) -> None:
        seen["first"] = play.talk("Sign")
        seen["fact while open"] = play.facts(SIGN)  # (not spent until it completes)
        play.finish()
        seen["fact at once"] = play.facts(SIGN)  # (before leaving: a save made now has it)
        play.save("in room")  # (made in the room, without leaving it)
        play.leave_and_return()
        seen["after re-entry"] = play.talk("Sign")

    def second(play: _Player) -> None:
        play.load("in room")
        seen["after load"] = play.talk("Sign")
        play.leave_and_return()
        seen["after load and a revisit"] = play.talk("Sign")

    _sessions(game_root, monkeypatch, first, second)
    assert seen["first"], "the first E opens the conversation"
    assert seen["fact while open"] is None, "an open conversation isn't spent yet"
    assert seen["fact at once"] == {"played": True}, "recorded the moment it completes"
    assert seen["after re-entry"] is False, "not again after leaving and coming back"
    assert seen["after load"] is False, "not again after loading a save made in the room"
    assert seen["after load and a revisit"] is False


def test_an_only_once_conversation_saved_mid_way_is_had_again_and_its_reward_pays_exactly_once(
        game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Elder: "Only once", its reward choice (+50 gold, then "Safe travels.") not marked "Choice once". A save made
    mid-conversation (as from the pause menu over it) before the reward lets the whole conversation, reward included,
    be had again; one made after the reward, before the end, lets it be finished but not paid again."""
    seen: dict[str, Any] = {}

    def first(play: _Player) -> None:
        play.talk("Elder")
        play.save("before reward")  # (the choice on screen)
        play.choose("Thank you")
        seen["mid-way facts"] = play.facts_of("Elder")
        play.save("after reward")  # ("Safe travels." on screen)
        play.finish()
        seen["first gold"] = play.gold()

    def from_before(play: _Player) -> None:
        play.load("before reward")
        seen["before: talk"] = play.talk("Elder")
        seen["before: choices"] = play.choices()
        play.choose("Thank you")
        play.finish()
        play.leave_and_return()
        seen["before: again"] = play.talk("Elder")
        seen["before: gold"] = play.gold()

    def from_after(play: _Player) -> None:
        play.load("after reward")
        seen["after: talk"] = play.talk("Elder")
        seen["after: choices"] = play.choices()
        play.finish()  # (nothing left to pick: E ends it)
        play.leave_and_return()
        seen["after: again"] = play.talk("Elder")
        seen["after: gold"] = play.gold()

    _sessions(game_root, monkeypatch, first, from_before, from_after)
    assert seen["first gold"] == 50.0
    assert "played" not in seen["mid-way facts"] and len(seen["mid-way facts"]["spent_choices"]) == 1, \
        "mid-way: not yet spent, but its reward is"
    assert seen["before: talk"] and seen["before: choices"] == {"Thank you": True}, "saved before: had again"
    assert seen["before: again"] is False and seen["before: gold"] == 50.0, "paid once, then spent"
    assert seen["after: talk"], "saved mid-way: it can still be finished"
    assert seen["after: choices"] == {"Thank you": False}, "but its reward, taken before the save, not again"
    assert seen["after: again"] is False and seen["after: gold"] == 50.0, "paid exactly once"


def test_an_only_once_conversation_closed_early_is_not_spent(game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def play_it(play: _Player) -> None:
        seen["opened"] = play.talk("Elder")
        play.cut_off()
        seen["again at once"] = play.talk("Elder")  # (the same visit)
        play.cut_off()
        play.leave_and_return()
        seen["re-entry"] = play.talk("Elder")
        seen["facts"] = play.facts_of("Elder")
        play.choose("Thank you")
        play.finish()
        play.leave_and_return()
        seen["finished"] = play.talk("Elder")

    _sessions(game_root, monkeypatch, play_it)
    assert seen["opened"] and seen["again at once"], "closed before its end: it can be had again at once"
    assert seen["re-entry"] and seen["facts"] is None, "and after re-entry; nothing was recorded"
    assert seen["finished"] is False, "had to its end: spent"


# --------------------------------------------------------------------- "Choice once" reward

def test_a_choice_once_reward_pays_exactly_once_across_reentry_and_save_load(
        game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def first(play: _Player) -> None:
        play.talk("Guide")
        seen["offered"] = play.choices()
        play.choose("Thank you")
        seen["paid"] = play.gold()
        seen["fact at once"] = play.facts(GUIDE)
        play.save("paid")  # (in the room, without leaving it)
        play.leave_and_return()
        seen["re-entry talk"] = play.talk("Guide")  # (the conversation itself can be had again)
        seen["re-entry choices"] = play.choices()
        play.choose("Goodbye")
        seen["re-entry gold"] = play.gold()

    def second(play: _Player) -> None:
        play.load("paid")
        play.talk("Guide")
        seen["load choices"] = play.choices()
        play.choose("Goodbye")
        play.leave_and_return()
        play.talk("Guide")
        seen["revisit choices"] = play.choices()
        play.choose("Goodbye")
        seen["final gold"] = play.gold()

    _sessions(game_root, monkeypatch, first, second)
    assert seen["offered"] == {"Thank you": True, "Goodbye": True}
    assert seen["paid"] == 50.0
    assert seen["fact at once"] is not None and len(seen["fact at once"]["spent_choices"]) == 1
    assert seen["re-entry talk"], "a conversation not marked Only once is had again"
    assert seen["re-entry choices"] == {"Thank you": False, "Goodbye": True}, "the reward stays taken after re-entry"
    assert seen["re-entry gold"] == 50.0
    assert seen["load choices"] == {"Thank you": False, "Goodbye": True}, "and after loading a save made in the room"
    assert seen["revisit choices"] == {"Thank you": False, "Goodbye": True}
    assert seen["final gold"] == 50.0, "paid exactly once"


def test_reordering_the_choices_keeps_a_taken_reward_taken(game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A choice is remembered by its line and words, not its position: the creator moving "Thank you" below
    "Goodbye" after it was taken doesn't offer it again."""
    seen: dict[str, Any] = {}

    def pay(play: _Player) -> None:
        play.talk("Guide")
        play.choose("Thank you")
        play.save("paid")

    def after(play: _Player) -> None:
        play.load("paid")
        play.talk("Guide")
        seen["choices"] = play.choices()
        play.choose("Goodbye")
        seen["gold"] = play.gold()

    def reorder(scene: dict[str, Any]) -> dict[str, Any]:
        scene = json.loads(json.dumps(scene))
        guide = next(e for e in scene["entities"] if e.get("id") == GUIDE)
        choices = guide["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["choices"]
        choices.reverse()
        return scene

    _sessions(game_root, monkeypatch, pay)
    _edit(game_root, reorder)
    _sessions(game_root, monkeypatch, after)
    assert list(seen["choices"]) == ["Goodbye", "Thank you"], "the choices were reordered"
    assert seen["choices"] == {"Goodbye": True, "Thank you": False}, "the taken reward stays taken"
    assert seen["gold"] == 50.0


def test_spent_choices_are_saved_sorted(game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``spent_choices`` is one deterministic list whatever order the choices were taken in (taken here in the reverse
    of it), so the same progress always saves the same."""
    from engine import project_ops as ops
    from engine.behaviours.dialogue import Dialogue

    extra = ["A tale", "A song", "A riddle"]
    _edit(game_root, *[lambda s, t=t: ops.add_choice(s, GUIDE, "root", t) for t in extra],
          *[lambda s, i=i: ops.set_choice(s, GUIDE, "root", i, once=True) for i in (2, 3, 4)])
    keys = {text: Dialogue._once_key("root", {"text": text}) for text in ["Thank you", *extra]}
    order = sorted(keys, key=keys.__getitem__, reverse=True)
    seen: dict[str, Any] = {}

    def take_all(play: _Player) -> None:
        for text in order:
            play.talk("Guide")
            play.choose(text)
        seen["recorded"] = play.facts(GUIDE)["spent_choices"]
        play.save("all")

    _sessions(game_root, monkeypatch, take_all)
    saved = json.loads((game_root / "saves" / "all.json").read_text(encoding="utf-8"))
    memory = saved["game_state"]["variables"][room_memory.VAR]
    assert seen["recorded"] == sorted(keys.values()), "sorted, not in the order taken"
    assert memory[START]["facts"][GUIDE]["Dialogue"]["spent_choices"] == sorted(keys.values())


# --------------------------------------------------------------------- a save from before facts

def make_pre_facts_save(dest: Path, work: Path) -> None:
    """How the committed fixture was made, on the engine before #620's fix (7e391681): in a game authored as here, the
    Guide's reward is taken (50 gold) and the Sign's conversation had, then the game is saved in the Village. Run with
    ``work`` an empty folder."""
    monkeypatch = pytest.MonkeyPatch()
    root = _new(work, "adventure")
    _author(root)

    def drive(play: _Player) -> None:
        play.talk("Guide")
        play.choose("Thank you")
        play.talk("Sign")
        play.finish()
        play.save("slot")

    try:
        _sessions(root, monkeypatch, drive)
    finally:
        monkeypatch.undo()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "saves" / "slot.json", dest)


def test_a_save_from_before_the_fix_loads_and_its_once_state_is_had_once_more(
        game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Documented: a save made before the fix carries no facts, so what it had already spent (the Sign's talk, the
    Guide's 50 gold) is available one more time after the upgrade, and from then on stays spent."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    variables = raw["game_state"]["variables"]
    assert raw["game_state"]["counters"]["gold"] == 50.0
    assert not any("facts" in entry for entry in (variables.get(room_memory.VAR) or {}).values())
    (game_root / "saves").mkdir()
    shutil.copyfile(FIXTURE, game_root / "saves" / "old.json")
    seen: dict[str, Any] = {}

    def upgraded(play: _Player) -> None:
        play.load("old")
        seen["gold"] = play.gold()
        seen["sign"] = play.talk("Sign")
        play.finish()
        play.talk("Guide")
        seen["choices"] = play.choices()
        play.choose("Thank you")
        seen["paid again"] = play.gold()
        play.leave_and_return()
        seen["sign after"] = play.talk("Sign")
        play.talk("Guide")
        seen["choices after"] = play.choices()
        play.choose("Goodbye")
        play.save("new")

    def later(play: _Player) -> None:
        play.load("new")
        seen["sign later"] = play.talk("Sign")
        play.talk("Guide")
        seen["choices later"] = play.choices()
        play.choose("Goodbye")
        seen["gold later"] = play.gold()

    _sessions(game_root, monkeypatch, upgraded, later)
    assert seen["gold"] == 50.0, "the old save loads"
    assert seen["sign"] is True and seen["choices"]["Thank you"] is True, "no facts: as authored, once more"
    assert seen["paid again"] == 100.0, "the documented one extra payout"
    assert seen["sign after"] is False and seen["choices after"]["Thank you"] is False, "then spent"
    assert seen["sign later"] is False and seen["choices later"]["Thank you"] is False and seen["gold later"] == 100.0


# --------------------------------------------------------------------- the Shopkeeper (#682, D2)

def test_a_spent_only_once_talk_lets_e_open_the_shop_after_reentry_and_load(
        game_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def first(play: _Player) -> None:
        shop = _Shop(play.game.window)
        seen["talk"] = play.talk("Shopkeeper")
        play.finish()
        seen["shop after talk"] = shop.vendor is play.game.behaviour("Shopkeeper", "Vendor")
        shop.close()
        play.game.step(2)
        play.save("spent")
        play.leave_and_return()
        shop = _Shop(play.game.window)
        seen["re-entry"] = (play.talk("Shopkeeper"), shop.vendor is play.game.behaviour("Shopkeeper", "Vendor"))

    def second(play: _Player) -> None:
        play.load("spent")
        play.leave_and_return()
        shop = _Shop(play.game.window)
        seen["load"] = (play.talk("Shopkeeper"), shop.vendor is play.game.behaviour("Shopkeeper", "Vendor"))

    _sessions(game_root, monkeypatch, first, second)
    assert seen["talk"] and seen["shop after talk"], "E talks first; the shop opens once the talk completes"
    assert seen["re-entry"] == (False, True), "the talk stays spent after re-entry: E opens the shop straight away"
    assert seen["load"] == (False, True), "and after a save, a fresh window, a load and a revisit"
