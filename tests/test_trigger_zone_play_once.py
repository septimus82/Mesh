"""#745: TriggerZone's "Play once" (``play_once``): a zone's events fire once per playthrough.

By default a zone fires once per room load (the room is rebuilt on entry, so re-entering arms it again). With Play
once it records the room-memory fact ``fired`` (``engine.scene_runtime.room_memory``, keyed by room and authored id)
when it sends its events, and stays silent after re-entry and after a save is loaded in a fresh window. A save without
the fact loads as "not fired yet". An object without its own authored id falls back to once per room load, warned.

Real hidden GameWindows and real room files (the harness of tests/test_entity_facts.py); the zones' settings are
written by the authoring ops (``project_ops.add_behaviour`` / ``set_behaviour_param``) that Studio, MCP and the CLI use.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.scene_runtime import room_memory
from tests._game_window_live import dispose_game_window
from tests.test_entity_facts import _entity, _load, _Log, _step, _window

pytestmark = [pytest.mark.integration,  # (room files in a temporary folder; hidden game windows)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

YARD, SHED = "rooms/yard.json", "rooms/shed.json"
SPOTS = {"Gate": 200.0, "Echo": 270.0, "Loose": 130.0}  # x of each zone (y 100); the Hero starts at x 40
FIRED = {"gate": {"TriggerZoneBehaviour": {"fired": True}}}  # (facts are keyed by the class name)


def _zones(scene: dict[str, Any]) -> dict[str, Any]:
    """The Yard's zones, set up through the authoring ops: Gate (Play once), Echo (default), Loose (Play once, no
    id: given one for the ops, then stripped)."""
    from engine import project_ops as ops

    for ident, name in (("gate", "Gate"), ("echo", "Echo"), ("loose", "Loose")):
        scene = ops.add_behaviour(scene, ident, "TriggerZone")
        for param, value in (("trigger_radius", 20), ("trigger_target", "Hero"), ("on_trigger", f"{ident}_event")):
            scene = ops.set_behaviour_param(scene, ident, "TriggerZone", param, value)
        if name != "Echo":
            scene = ops.set_behaviour_param(scene, ident, "TriggerZone", "play_once", "on")
    for entity in scene["entities"]:
        if entity["id"] == "loose":
            del entity["id"]
    return scene


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "game"
    hero = _entity("hero", "Hero", 40, "PlayerController", tag="player")
    yard = [hero] + [_entity(name.lower(), name, int(x)) for name, x in SPOTS.items()]
    (root / "rooms").mkdir(parents=True)
    for path, name, entities in ((YARD, "Yard", yard), (SHED, "Shed", [hero])):
        scene = {"name": name, "schema_version": 1, "version": 1, "layers": [], "entities": entities}
        if path == YARD:
            scene = _zones(scene)
        (root / path).write_text(json.dumps(scene, indent=2), encoding="utf-8")
    monkeypatch.chdir(root)  # (room paths project-relative, as a game's are)
    return root


class _Game:
    """A hidden window counting each zone's events (``entered_zone`` by its payload's zone, and ``<id>_event``)."""

    def __init__(self, project: Path) -> None:
        self.window = _window(project)
        self.seen: dict[str, int] = {}
        for name in ("entered_zone", "gate_event", "echo_event", "loose_event"):
            self.window.event_bus.subscribe(name, self._count)

    def _count(self, event: Any) -> None:
        key = f"entered_zone:{event.payload.get('zone')}" if event.type == "entered_zone" else event.type
        self.seen[key] = self.seen.get(key, 0) + 1

    def fired(self, zone: str) -> tuple[int, int]:
        """How often ``zone`` sent entered_zone and its own event in this window."""
        return self.seen.get(f"entered_zone:{zone}", 0), self.seen.get(f"{zone.lower()}_event", 0)

    def walk_to(self, x: float) -> None:
        hero = self.window.scene_controller._find_player_sprite()
        hero.center_x, hero.center_y = x, 100.0
        _step(self.window)

    def enter(self, zone: str) -> None:
        """Step into ``zone``, then back to the start."""
        self.walk_to(SPOTS[zone])
        self.walk_to(40.0)

    def room(self, path: str) -> None:
        self.window.scene_controller.load_scene(path)
        _step(self.window)

    def facts(self) -> Any:
        entry = (self.window.game_state_controller.get_var(room_memory.VAR) or {}).get(YARD) or {}
        return entry.get("facts")


@contextmanager
def _game(project: Path, room: str | None = YARD) -> Iterator[_Game]:
    game = _Game(project)
    try:
        if room:
            game.room(room)
        yield game
    finally:
        dispose_game_window(game.window)


@pytest.mark.parametrize("saved_in", [YARD, SHED])
def test_play_once_fires_once_per_playthrough(project: Path, saved_in: str) -> None:
    with _game(project) as game:
        assert game.fired("Gate") == (0, 0), "the Hero starts away from the zone"
        game.enter("Gate")
        assert game.fired("Gate") == (1, 1), "first entry: entered_zone and its own event, once each"
        assert game.facts() == FIRED, "recorded in room memory the moment it fired"
        game.enter("Gate")
        assert game.fired("Gate") == (1, 1), "stepping out and back in sends nothing more"
        game.room(SHED)
        game.room(YARD)
        game.enter("Gate")
        assert game.fired("Gate") == (1, 1), "re-entering the room does not re-arm a Play once zone"
        game.room(saved_in)
        assert game.window.save_manager.save_game("slot")
    saved = json.loads((project / "saves" / "slot.json").read_text(encoding="utf-8"))
    assert saved["game_state"]["variables"][room_memory.VAR][YARD]["facts"] == FIRED
    with _game(project, room=None) as game:  # (the game quit: a fresh window loads the save)
        _load(game.window, "slot")
        assert str(game.window.scene_controller.room_path) == saved_in
        if saved_in != YARD:
            game.room(YARD)
        game.enter("Gate")
        assert game.fired("Gate") == (0, 0), "after loading the save it stays spent"
        game.enter("Echo")
        assert game.fired("Echo") == (1, 1), "(the zones do run in this window)"


def test_default_fires_again_each_time_the_room_loads(project: Path) -> None:
    with _game(project) as game:
        game.enter("Echo")
        game.enter("Echo")
        assert game.fired("Echo") == (1, 1), "once per room load"
        game.room(SHED)
        game.room(YARD)
        game.enter("Echo")
        assert game.fired("Echo") == (2, 2), "re-entering the room arms it again, as before Play once existed"
        assert "echo" not in (game.facts() or {}), "the default records nothing"


def test_a_save_without_the_fact_loads_and_the_zone_fires_once(project: Path) -> None:
    with _game(project) as game:
        assert game.window.save_manager.save_game("old")  # (before the zone fired: no fact, as in older saves)
    saved = json.loads((project / "saves" / "old.json").read_text(encoding="utf-8"))
    assert not (saved["game_state"]["variables"].get(room_memory.VAR) or {}).get(YARD, {}).get("facts")
    with _game(project, room=None) as game:
        _load(game.window, "old")
        game.enter("Gate")
        assert game.fired("Gate") == (1, 1), "missing fact = not fired yet"
        game.room(SHED)
        game.room(YARD)
        game.enter("Gate")
        assert game.fired("Gate") == (1, 1), "and from then on it is spent"


def test_play_once_without_an_authored_id_fires_once_per_room_load_and_warns(project: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.behaviours import trigger_zone

    log = _Log()
    monkeypatch.setattr(trigger_zone, "logger", log)
    with _game(project) as game:
        game.enter("Loose")
        assert game.fired("Loose") == (1, 1)
        assert len(log.warning_lines) == 1 and "Loose" in log.warning_lines[0]
        game.room(SHED)
        game.room(YARD)
        game.enter("Loose")
        assert game.fired("Loose") == (2, 2), "no id, no fact: falls back to once per room load"
        assert not game.facts()


def test_studio_and_the_authoring_ops_offer_play_once() -> None:
    """Studio's settings rows come from ``behaviour_catalog`` through the guide (a bool shows as an On/Off button
    under its label); the authoring ops check settings against the same fields."""
    from engine import behaviour_guide
    from engine import project_ops as ops

    (info,) = [b for b in ops.behaviour_catalog() if b["name"] == "TriggerZone"]
    (field,) = [f for f in info["fields"] if f["name"] == "play_once"]
    assert (field["type"], field["default"]) == ("bool", False)
    basics, _more = behaviour_guide.visible_fields("TriggerZone", info["fields"])
    assert "play_once" in [f["name"] for f in basics]
    assert behaviour_guide.setting_label("TriggerZone", "play_once") == "Play once"
    scene = {"name": "Room", "schema_version": 1, "version": 1, "layers": [],
             "entities": [_entity("zone", "Zone", 100)]}
    scene = ops.add_behaviour(scene, "zone", "TriggerZone")
    assert scene["entities"][0]["behaviour_config"]["TriggerZone"]["play_once"] is False
    scene = ops.set_behaviour_param(scene, "zone", "TriggerZone", "play_once", True)
    assert scene["entities"][0]["behaviour_config"]["TriggerZone"]["play_once"] is True
