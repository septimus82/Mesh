"""S1 4.1 (D6): per-entity facts in room memory. "This already happened" stays happened.

A room is rebuilt from its file on every entry, so progress a behaviour kept on itself (a door unlocked, a chest
looted, an "Only once" line spent) was forgotten on re-entry, and on loading a save made in another room. Room memory
(engine.scene_runtime.room_memory) now also keeps, per room and authored entity id, the facts behaviours declare
(``FACT_FIELDS``) and write (``record_fact``); the factory applies them as each behaviour is built.

Checked with a real hidden GameWindow, real room files and a behaviour registered only here (FactProbe):
- a fact is written into room memory at once, and survives leaving the room and coming back;
- it survives save -> a fresh window -> load -> revisit, also when the save was made in another room;
- a save made before facts existed (``fixtures/entity_facts/pre_facts_slot.json``, written by ``make_pre_facts_save``
  on the engine at ea042428) loads, every fact as authored;
- two rooms with the same entity id keep their own facts; an entity without an authored id (spawned) and entities
  sharing one id in a room get none.
"""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours import registry
from engine.behaviours.base import Behaviour
from engine.config import EngineConfig
from engine.save_manager import SaveManager
from engine.scene_runtime import room_memory
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "entity_facts" / "pre_facts_slot.json"
YARD, SHED = "rooms/yard.json", "rooms/shed.json"
PICTURE = "assets/placeholder.png"


class FactProbe(Behaviour):
    """A behaviour with one fact: whether it was used."""

    FACT_FIELDS = ("used",)

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.used = False

    def use(self) -> None:
        if not self.used:
            self.record_fact("used", True)


@contextmanager
def probe_registered() -> Iterator[None]:
    registry.register_behaviour("FactProbe", description="test-only: one fact")(FactProbe)
    try:
        yield
    finally:
        for table in (registry.BEHAVIOUR_REGISTRY, registry._BEHAVIOUR_INFO, registry.BEHAVIOUR_PARAM_DEFS):
            table.pop("FactProbe", None)
        registry._NAME_ALIASES.pop("factprobe", None)


def _entity(entity_id: str | None, name: str, x: int, *behaviours: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "x": x, "y": 100, "sprite": PICTURE, "behaviours": list(behaviours), **extra}
    if entity_id is not None:
        out["id"] = entity_id
    return out


def build_project(root: Path) -> Path:
    """Two rooms: the Yard (a Lamp, a Coin, a Loose probe with no id, two Twins sharing an id) and the Shed (a Lamp
    with the Yard Lamp's id)."""
    hero = _entity("hero", "Hero", 40, "PlayerController", tag="player")
    yard = [hero, _entity("lamp", "Lamp", 100, "FactProbe"), _entity("coin", "Coin", 140),
            _entity(None, "Loose", 180, "FactProbe"), _entity("twin", "Twin", 220, "FactProbe"),
            _entity("twin", "Twin", 260, "FactProbe")]
    shed = [hero, _entity("lamp", "Lamp", 100, "FactProbe")]
    (root / "rooms").mkdir(parents=True)
    for path, name, entities in ((YARD, "Yard", yard), (SHED, "Shed", shed)):
        scene = {"name": name, "schema_version": 1, "version": 1, "layers": [], "entities": entities}
        (root / path).write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return root


def _window(project: Path) -> Any:
    from engine.game import GameWindow

    cfg = EngineConfig(width=320, height=200, title="Entity facts", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    window.save_manager = SaveManager(window, save_dir=project / "saves")
    window._allow_dispatch_event = True
    return window


def _step(window: Any, frames: int = 3) -> None:
    for _ in range(frames):
        window.dispatch_event("on_update", 1 / 60)


def _sprites(window: Any, name: str) -> list[Any]:
    return [s for s in window.scene_controller.all_sprites if getattr(s, "mesh_name", None) == name]


def _probes(window: Any, name: str) -> list[FactProbe]:
    return [b for s in _sprites(window, name) for b in s.mesh_behaviours_runtime if isinstance(b, FactProbe)]


def _probe(window: Any, name: str = "Lamp") -> FactProbe:
    (probe,) = _probes(window, name)
    return probe


def _facts(window: Any, room: str = YARD) -> Any:
    entry = (window.game_state_controller.get_var(room_memory.VAR) or {}).get(room) or {}
    return entry.get("facts")


def _room_of(window: Any) -> str:
    return str(window.scene_controller.room_path)


def make_pre_facts_save(dest: Path, work: Path) -> None:
    """How the committed fixture was made (on the engine before facts): in the Yard, the Coin is collected, the
    player goes to the Shed and back, and the game is saved to a slot. Run in ``work``, an empty folder; the cwd and
    the behaviour registry are restored after."""
    import os

    project = build_project(work / "game")
    cwd = os.getcwd()
    os.chdir(project)
    window = None
    try:
        with probe_registered():
            window = _window(project)
            window.scene_controller.load_scene(YARD)
            _sprites(window, "Coin")[0].remove_from_sprite_lists()
            window.scene_controller.load_scene(SHED)
            window.scene_controller.load_scene(YARD)
            assert window.save_manager.save_game("slot")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / "saves" / "slot.json", dest)
    finally:
        if window is not None:
            dispose_game_window(window)
        os.chdir(cwd)


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = build_project(tmp_path / "game")
    monkeypatch.chdir(root)  # (room paths project-relative, as a game's are)
    with probe_registered():
        yield root


@pytest.fixture()
def game(project: Path) -> Iterator[Any]:
    window = _window(project)
    try:
        window.scene_controller.load_scene(YARD)
        yield window
    finally:
        dispose_game_window(window)


@contextmanager
def _fresh(project: Path) -> Iterator[Any]:
    window = _window(project)
    try:
        yield window
    finally:
        dispose_game_window(window)


def _load(window: Any, slot: str) -> None:
    """A player's Continue: load the slot; the saved room loads on the next frame."""
    assert window.save_manager.load_game(slot)
    _step(window)


# --------------------------------------------------------------------- room exit and re-entry

def test_a_fact_is_written_at_once_and_survives_leaving_and_coming_back(game: Any) -> None:
    _probe(game).use()
    assert _facts(game) == {"lamp": {"FactProbe": {"used": True}}}  # (in room memory now: a save at any time has it)
    _sprites(game, "Coin")[0].remove_from_sprite_lists()  # (leaving rewrites the room's removed list: facts stay)
    game.scene_controller.load_scene(SHED)
    assert _probe(game).used is False  # (the Shed's Lamp: same id, another room)
    game.scene_controller.load_scene(YARD)
    assert _probe(game).used is True  # (applied as it was built, before its first update)
    assert not _sprites(game, "Coin")
    assert room_memory.removed_ids(game, YARD) == {"coin"} and _facts(game) == {"lamp": {"FactProbe": {"used": True}}}


def test_two_rooms_with_the_same_id_keep_their_own_facts(game: Any) -> None:
    game.scene_controller.load_scene(SHED)
    _probe(game).use()
    game.scene_controller.load_scene(YARD)
    assert _probe(game).used is False and _facts(game) is None
    game.scene_controller.load_scene(SHED)
    assert _probe(game).used is True and _facts(game, SHED) == {"lamp": {"FactProbe": {"used": True}}}


# --------------------------------------------------------------------- saves

@pytest.mark.parametrize("saved_in", [YARD, SHED])
def test_a_fact_survives_save_a_fresh_window_load_and_a_revisit(project: Path, saved_in: str) -> None:
    with _fresh(project) as window:
        window.scene_controller.load_scene(YARD)
        _probe(window).use()
        window.scene_controller.load_scene(saved_in)
        assert window.save_manager.save_game("slot")
    saved = json.loads((project / "saves" / "slot.json").read_text(encoding="utf-8"))
    memory = saved["game_state"]["variables"][room_memory.VAR]
    assert memory[YARD]["facts"] == {"lamp": {"FactProbe": {"used": True}}}
    with _fresh(project) as window:  # (the game quit: nothing of the first window is left)
        _load(window, "slot")
        assert _room_of(window) == saved_in
        if saved_in != YARD:
            window.scene_controller.load_scene(YARD)
        assert _probe(window).used is True


def test_a_save_from_before_facts_loads_with_every_fact_as_authored(project: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    memory = raw["game_state"]["variables"][room_memory.VAR]
    assert memory == {YARD: {"removed": ["coin"]}}  # (the old shape: removed objects only)
    (project / "saves").mkdir()
    shutil.copyfile(FIXTURE, project / "saves" / "old.json")
    with _fresh(project) as window:
        _load(window, "old")
        assert _room_of(window) == YARD
        assert _probe(window).used is False and not _sprites(window, "Coin")  # (as authored; removed still honoured)
        _probe(window).use()  # (and from here it records as any game does)
        window.scene_controller.load_scene(SHED)
        assert window.save_manager.save_game("new")
    with _fresh(project) as window:
        _load(window, "new")
        window.scene_controller.load_scene(YARD)
        assert _probe(window).used is True and not _sprites(window, "Coin")


# --------------------------------------------------------------------- what gets no facts

class _Log:
    def __init__(self) -> None:
        self.debug_lines: list[str] = []
        self.warning_lines: list[str] = []

    def debug(self, message: str, *args: Any) -> None:
        self.debug_lines.append(message % args)

    def warning(self, message: str, *args: Any) -> None:
        self.warning_lines.append(message % args)


def test_an_entity_without_an_authored_id_writes_nothing(game: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    log = _Log()
    monkeypatch.setattr(room_memory, "logger", log)
    loose = _probe(game, "Loose")
    loose.use()
    loose.record_fact("used", True)  # (again: still said once)
    assert loose.used is True and _facts(game) is None
    assert len(log.debug_lines) == 1 and "Loose" in log.debug_lines[0]
    # Spawned during play with an id the room file doesn't have: not the room's, so no facts either.
    sprite = game.scene_controller._create_sprite(_entity("newcomer", "Newcomer", 300, "FactProbe"))
    (spawned,) = [b for b in sprite.mesh_behaviours_runtime if isinstance(b, FactProbe)]
    spawned.use()
    assert _facts(game) is None
    game.scene_controller.load_scene(SHED)
    game.scene_controller.load_scene(YARD)
    assert _probe(game, "Loose").used is False


def test_entities_sharing_an_id_in_a_room_get_no_facts(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = _Log()
    monkeypatch.setattr(room_memory, "logger", log)
    with _fresh(project) as window:
        window.scene_controller.load_scene(YARD)
        assert any("twin" in line for line in log.warning_lines)
        twins = _probes(window, "Twin")
        twins[0].use()
        assert _facts(window) is None  # (one Twin's fact would apply to both)
        window.scene_controller.load_scene(SHED)
        window.scene_controller.load_scene(YARD)
        assert [t.used for t in _probes(window, "Twin")] == [False, False]


def test_an_undeclared_fact_is_refused(game: Any) -> None:
    with pytest.raises(ValueError, match="FACT_FIELDS"):
        _probe(game).record_fact("colour", "red")
    with pytest.raises(ValueError, match="JSON"):
        _probe(game).record_fact("used", object())
    assert _facts(game) is None


def test_facts_belong_to_the_game_that_loaded_the_room(game: Any) -> None:
    lamp = _probe(game)
    game.game_state_controller.replace_state({})  # (New Game: a new game ...)
    lamp.use()  # (... and the old room's object, still on screen for a frame, changes)
    assert _facts(game) is None


def test_facts_are_applied_through_the_behaviours_own_hook(game: Any) -> None:
    seen: list[dict[str, Any]] = []
    _probe(game).use()
    original = FactProbe.apply_facts

    def spy(self: FactProbe, facts: Any) -> None:
        seen.append(dict(facts))
        original(self, facts)

    FactProbe.apply_facts = spy  # type: ignore[method-assign]
    try:
        game.scene_controller.load_scene(SHED)
        game.scene_controller.load_scene(YARD)
    finally:
        FactProbe.apply_facts = original  # type: ignore[method-assign]
    assert seen == [{"used": True}]  # (only an entity with a record: the Shed's Lamp has none)
