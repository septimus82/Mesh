"""#640: TriggerZone sends the event the creator chose ("Event it sends"), and ``entered_zone`` once per entry.

It used to send only ``entered_zone`` (``on_trigger`` was printed, never sent), and through two paths onto the same
bus (``emit_gameplay_event`` and ``window.emit_signal``), so every listener got it twice: a counter went up by 2 for
one entry. Shipped content wires through ``entered_zone`` plus the zone's name, so that event stays, exactly once.

A generated project (``mesh new``), the zone and its listeners authored through Studio's project model and ops, played
in a real hidden GameWindow (``run_game``) through the real per-frame update.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; a hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

ROOM = "packs/core_regions/scenes/start.json"
ZONE_X, ZONE_Y = 400.0, 300.0


def _author(root: Path) -> None:
    """Studio: a "React when someone comes near" zone sending ``open_gate``, two counters, and a quest on entries."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.studio_project import Project

    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)

        def place(name: str, x: float, y: float) -> str:
            made: dict[str, str] = {}

            def edit(scene: dict[str, Any]) -> dict[str, Any]:
                scene, made["id"] = ops.place_blank(scene, project.current, name, x, y)
                return scene

            project.edit_scene(edit)
            return made["id"]

        def give(entity: str, behaviour: str, **params: Any) -> None:
            project.edit_scene(lambda s: ops.add_behaviour(s, entity, behaviour))
            for param, value in params.items():
                project.edit_scene(lambda s, p=param, v=value: ops.set_behaviour_param(s, entity, behaviour, p, v))

        give(place("Gate", ZONE_X, ZONE_Y), "TriggerZone", trigger_radius=40, trigger_target="Player",
             on_trigger="open_gate")
        give(place("Entries", 40, 40), "IncrementCounterOnEvent", event_type="entered_zone", payload_field="zone",
             payload_value="Gate", counter="gate_entries")
        give(place("Opened", 60, 40), "IncrementCounterOnEvent", event_type="open_gate", counter="gate_opened")
        project.save(owner=held)
    quest = {"id": "walk", "title": "Walk", "description": "",
             "stages": [{"id": f"visit{i}", "title": f"Visit {i}", "text": "Go to the gate.",
                         "complete_event": {"type": "entered_zone", "payload": {"zone": "Gate"}}} for i in (1, 2, 3)]}
    (root / "assets/data/quests.json").write_text(json.dumps({"quests": [quest]}), encoding="utf-8")


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from mesh_cli.main import main as mesh

    dest = tmp_path_factory.mktemp("p640")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert mesh(["new", "game", "--template", "blank", "--dest", str(dest)]) == 0
    root = (dest / "game").resolve()
    _author(root)
    return root


def _play(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Enter the zone, step out and back in, then come back to the room and enter again; record after each."""
    from engine.game import GameWindow
    from engine.public_api import run_game

    seen: dict[str, Any] = {}

    def play(window: Any) -> None:  # (in place of window.run())
        try:
            sc = window.scene_controller
            bus: dict[str, int] = {}
            for name in ("entered_zone", "open_gate"):
                window.event_bus.subscribe(name, lambda e: bus.__setitem__(e.type, bus.get(e.type, 0) + 1))
            queued: list[str] = []  # what the per-frame delivery hands every on_event listener (and quests)
            deliver = sc._deliver_events_to_behaviours
            monkeypatch.setattr(sc, "_deliver_events_to_behaviours",
                                lambda events: (queued.extend(e.type for e in events), deliver(events))[1])

            def frames(n: int = 4) -> None:
                for _ in range(n):
                    window.on_update(1 / 60)  # the real frame update (as arcade's clock calls it)

            def go(x: float, y: float) -> None:
                hero = sc._find_player_sprite()
                hero.center_x, hero.center_y = x, y
                frames()

            def snapshot() -> dict[str, Any]:
                gs = window.game_state_controller
                state = window.quest_manager._ensure_state("walk")
                return {"bus": dict(bus), "queued_entered_zone": queued.count("entered_zone"),
                        "queued_open_gate": queued.count("open_gate"),
                        "gate_entries": gs.get_counter("gate_entries", 0), "gate_opened": gs.get_counter("gate_opened", 0),
                        "quest_done": sorted(state.get("completed_stages") or [])}

            frames()
            seen["start"] = snapshot()
            go(ZONE_X, ZONE_Y)
            seen["entered"] = snapshot()
            go(ZONE_X + 200, ZONE_Y)
            go(ZONE_X, ZONE_Y)
            seen["stepped_out_and_back"] = snapshot()
            sc.load_scene(str(sc.current_scene_path))  # back to the room: a new zone
            frames()
            go(ZONE_X, ZONE_Y)
            seen["room_again"] = snapshot()
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", play)
    run_game(ROOM, project_root=project)
    return seen


def test_trigger_zone_sends_its_event_and_entered_zone_once_per_entry(project: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _play(project, monkeypatch)
    assert seen["start"] == {"bus": {}, "queued_entered_zone": 0, "queued_open_gate": 0, "gate_entries": 0,
                             "gate_opened": 0, "quest_done": []}, "the player starts away from the zone"

    entered = seen["entered"]
    assert entered["bus"].get("open_gate", 0) == 1, "the creator's event ('Event it sends') fires once"
    assert entered["gate_opened"] == 1, "a listener on the creator's event reacts once"
    assert entered["bus"].get("entered_zone", 0) == 1, "a bus subscriber sees entered_zone once"
    assert entered["queued_entered_zone"] == 1, "the per-frame delivery (on_event listeners) hands it over once"
    assert entered["queued_open_gate"] == 1
    assert entered["gate_entries"] == 1, "IncrementCounterOnEvent on entered_zone adds 1 per entry"
    assert entered["quest_done"] == ["visit1"], "two consecutive entered_zone stages: one stage per entry"

    # The zone fires once (its "Sends an event once"): stepping out and back in sends nothing more.
    assert seen["stepped_out_and_back"] == entered

    again = seen["room_again"]  # coming back to the room makes a new zone: it fires once more
    assert again["bus"] == {"entered_zone": 2, "open_gate": 2}
    assert (again["gate_entries"], again["gate_opened"]) == (2, 2)
    assert again["quest_done"] == ["visit1", "visit2"]


def test_entered_zone_payload_is_unchanged() -> None:
    """Listeners keyed on ``entered_zone`` plus the zone's name see the payload they always did; the creator's event
    carries the same zone/actor payload."""
    from types import SimpleNamespace

    from engine.behaviours import load_builtin_behaviours
    from engine.behaviours.registry import create_behaviour
    from engine.events import MeshEventBus

    load_builtin_behaviours()
    bus = MeshEventBus()
    got: list[tuple[str, dict[str, Any]]] = []
    bus.subscribe_all(lambda e: got.append((e.type, dict(e.payload))))
    hero = SimpleNamespace(mesh_name="Player", center_x=10.0, center_y=0.0)
    window = SimpleNamespace(event_bus=bus, find_sprite_by_name=lambda name: hero if name == "Player" else None)
    zone = SimpleNamespace(mesh_name="Gate", mesh_id="gate_1", center_x=0.0, center_y=0.0)
    behaviour = create_behaviour("TriggerZone", zone, window,
                                 config={"trigger_radius": 20, "trigger_target": "Player", "on_trigger": "open_gate"})
    behaviour.update(1 / 60)
    behaviour.update(1 / 60)
    payload = {"zone": "Gate", "actor": "Player", "position": (0.0, 0.0)}
    assert got == [("entered_zone", payload), ("open_gate", payload)]

    got.clear()  # without a chosen event: only entered_zone, as before
    create_behaviour("TriggerZone", zone, window, config={"trigger_radius": 20, "trigger_target": "Player"}).update(0)
    assert got == [("entered_zone", payload)]
