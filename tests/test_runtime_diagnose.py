"""D3A (#422): "why can't the player use this?" (``engine.runtime_diagnose``), against a real hidden GameWindow.

A Studio project's room, loaded into a real game window, with real behaviours (``SceneTransition``, ``Dialogue``,
``ConditionalActivator``, ``ToggleSwitch``). Each case puts the game in one state and checks the diagnosis against
it, and where the game decides something itself (which object pressing interact uses), against the game:
- kept out of the room by its flags, the flag's value, and the dialogue choice that sets it; its flags met later
  (a possible cause, not a fact); not in the project; in another room; collected earlier;
- its own flags; hidden by "Show when"; a door used up; a conversation's flags and its choices;
- too far; behind the player; another object chosen instead; available (and the game's own pick agrees);
- a door used by walking into it, hidden by "Show when" yet still working by touch;
- a behaviour whose rule isn't analysed;
- reading changes nothing; answers are bounded; and the way in over MCP, with its refusals.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from urllib import error, request

import pytest

import engine.optional_arcade as optional_arcade
from engine import interaction, runtime_diagnose
from engine.config import EngineConfig
from engine.editor.live_session_bridge import read_live_session_file
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

WORLD = "packs/core_regions/worlds/main.json"
PICTURE = "assets/placeholder.png"
HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 100, "y": 100, "sprite": PICTURE,
        "behaviours": ["PlayerController"]}
DOOR = {"id": "door", "name": "Door", "x": 150, "y": 100, "sprite": PICTURE, "behaviours": ["SceneTransition"],
        "behaviour_config": {"SceneTransition": {"target_scene": "cellar", "allow_interact": True,
                                                 "trigger_on_touch": False}}}
GUIDE = {"id": "guide", "name": "Guide", "x": 600, "y": 400, "sprite": PICTURE, "behaviours": ["Dialogue"],
         "behaviour_config": {"Dialogue": {"once": False, "dialogue": {"speaker": "Guide", "start": "root", "nodes": {
             "root": {"text": "Hello.", "choices": [
                 {"id": "key", "text": "Give me the key.", "set_flags": {"has_key": True}, "next": "bye"},
                 {"id": "secret", "text": "Tell me a secret.", "require_flags": ["trusted"], "next": "bye"}]},
             "bye": {"text": "Bye."}}}}}}


@pytest.fixture()
def made(tmp_path: Path) -> Iterator[Any]:
    """A Studio project; ``made(*entities)`` writes its start room and loads it into a real game window."""
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    windows: list[Any] = []

    def build(*entities: dict[str, Any], other_room: list[dict[str, Any]] | None = None) -> SimpleNamespace:
        from engine.game import GameWindow

        project = Project.open(root, WORLD)
        assert project is not None
        path = root / project.path(project.current)
        scene = json.loads(path.read_text(encoding="utf-8"))
        scene["entities"] = [copy.deepcopy(e) for e in entities]
        path.write_text(json.dumps(scene), encoding="utf-8")
        if other_room is not None:
            from engine import authoring

            authoring.apply(project, [{"op": "add_room", "label": "Cellar"}])
            project.save()
            cellar = root / project.path("cellar")
            other = json.loads(cellar.read_text(encoding="utf-8"))
            other["entities"] += other_room
            cellar.write_text(json.dumps(other), encoding="utf-8")
        project = Project.open(root, WORLD)
        cfg = EngineConfig(width=640, height=480, title="D3A", vsync=False, start_scene="", world_file=None,
                           main_menu_scene=None)
        window = GameWindow(width=640, height=480, title=cfg.title, vsync=False, config=cfg)
        windows.append(window)
        window.scene_controller.load_scene(str(path))
        return SimpleNamespace(project=project, window=window, mode="play", path=str(path),
                               playtest={"id": "t", "number": 1, "started_at": time.time(), "started_by": "person"})

    yield build
    for window in windows:
        dispose_game_window(window)


def _diag(studio: SimpleNamespace, entity_id: str) -> dict[str, Any]:
    out = runtime_diagnose.diagnose(studio, entity_id)
    json.dumps(out, allow_nan=False)
    return out


def _observed(out: dict[str, Any], code: str) -> dict[str, Any]:
    return next(c for c in out["observed"] if c["code"] == code)


def _sprite(studio: SimpleNamespace, entity_id: str) -> Any:
    return next(s for s in studio.window.scene_controller.all_sprites if getattr(s, "mesh_id", None) == entity_id)


def _place(studio: SimpleNamespace, x: float, y: float, facing: str = "right") -> None:
    hero = _sprite(studio, "hero")
    hero.center_x, hero.center_y = x, y
    hero.mesh_entity_data["facing"] = facing


# --------------------------------------------------------------------- not in the running room

def test_kept_out_by_its_flags_with_the_flags_value_and_where_the_project_sets_it(made: Any) -> None:
    studio = made(HERO, dict(DOOR, require_flags=["has_key"]), GUIDE)
    out = _diag(studio, "door")
    assert out["available"] is False and out["blocking"]["code"] == "in_room" and "flags keep it out" in \
        out["blocking"]["message"]
    assert _observed(out, "in_room")["detail"]["unmet"] == ["has_key"] and out["flags"] == {"has_key": False}
    assert out["flag_sources"]["has_key"] == [{"sets_to": True, "room": studio.project.current, "room_label": "Start",
                                               "entity_id": "guide", "entity": "Guide", "via": "dialogue choice",
                                               "node": "root", "choice": "Give me the key."}]
    assert out["possible_causes"] == []
    studio.window.set_flag("has_key", True)  # (met now, but the room loaded without it)
    later = _diag(studio, "door")
    assert later["blocking"]["code"] == "in_room" and later["flags"] == {"has_key": True}
    assert [c["code"] for c in later["possible_causes"]] == ["loaded_before_flags_were_met"]  # (a cause, not a fact)
    studio.window.scene_controller.load_scene(studio.path)  # (the room again: now it is there)
    assert _observed(_diag(studio, "door"), "in_room")["ok"] is True


def test_not_in_the_project_in_another_room_or_collected_earlier(made: Any) -> None:
    studio = made(HERO, DOOR, {"id": "coin", "name": "Coin", "x": 300, "y": 300, "sprite": PICTURE},
                  other_room=[{"id": "lamp", "name": "Lamp", "x": 50, "y": 50, "sprite": PICTURE}])
    assert "No object 'ghost'" in _diag(studio, "ghost")["blocking"]["message"]
    elsewhere = _diag(studio, "lamp")
    assert "another room" in elsewhere["blocking"]["message"]
    assert _observed(elsewhere, "in_room")["detail"]["rooms"] == [{"key": "cellar", "label": "Cellar"}]
    _sprite(studio, "coin").remove_from_sprite_lists()  # (collected)
    studio.window.scene_controller.load_scene(studio.path)  # (the room again: it remembers)
    assert "collected or defeated earlier" in _diag(studio, "coin")["blocking"]["message"]


# --------------------------------------------------------------------- its own conditions

def test_its_own_flags_hidden_by_show_when_and_a_door_used_up(made: Any) -> None:
    shown = dict(DOOR, behaviours=["SceneTransition", "ConditionalActivator"])
    shown["behaviour_config"] = dict(DOOR["behaviour_config"], ConditionalActivator={"require_flags": ["lights_on"]})
    studio = made(HERO, shown)
    studio.window.on_update(1 / 60)
    out = _diag(studio, "door")
    assert out["blocking"]["code"] == "shown" and "Show when" in out["blocking"]["message"]
    assert _observed(out, "shown")["detail"]["show_when"]["unmet"] == ["lights_on"] and out["flags"]["lights_on"] is False
    studio.window.set_flag("lights_on", True)
    studio.window.on_update(1 / 60)
    door = _sprite(studio, "door")
    door.mesh_entity_data["forbid_flags"] = ["alarm"]  # (its own flags, checked again on use)
    studio.window.set_flag("alarm", True)
    gated = _diag(studio, "door")
    assert gated["blocking"]["code"] == "flag_gate" and _observed(gated, "flag_gate")["detail"]["unmet"] == ["alarm"]
    studio.window.set_flag("alarm", False)
    transition = next(b for b in door.mesh_behaviours_runtime if type(b).__name__ == "SceneTransition")
    transition.once, transition._triggered = True, True
    used = _diag(studio, "door")
    assert used["blocking"]["code"] == "behaviours"
    rules = _observed(used, "behaviours")["detail"]["behaviours"][0]["rules"]
    assert next(r for r in rules if r["code"] == "not_used_up")["ok"] is False


def test_a_conversations_flags_and_its_choices(made: Any) -> None:
    studio = made(HERO, dict(GUIDE, x=150, y=100, behaviour_config={"Dialogue": dict(
        GUIDE["behaviour_config"]["Dialogue"], require_flags=["met"])}))
    out = _diag(studio, "guide")
    assert out["blocking"]["code"] == "behaviours"
    rules = _observed(out, "behaviours")["detail"]["behaviours"][0]["rules"]
    assert next(r for r in rules if r["code"] == "flags")["detail"]["unmet"] == ["met"]
    choices = {c["id"]: c for c in out["dialogue"]["choices"]}
    assert choices["key"]["available"] is True and choices["secret"]["available"] is False
    assert choices["secret"]["unmet"] == ["trusted"] and out["flags"]["trusted"] is False
    studio.window.set_flag("met", True)
    studio.window.set_flag("trusted", True)
    after = _diag(studio, "guide")
    assert after["available"] is True and {c["id"]: c["available"] for c in after["dialogue"]["choices"]} == {
        "key": True, "secret": True}


# --------------------------------------------------------------------- reach and selection

def test_too_far_behind_the_player_another_chosen_then_available_as_the_game_picks(made: Any) -> None:
    studio = made(HERO, DOOR, {"id": "sign", "name": "Sign", "x": 130, "y": 100, "sprite": PICTURE,
                               "behaviours": ["Dialogue"], "behaviour_config": {"Dialogue": {
                                   "once": False, "dialogue": {"start": "a", "nodes": {"a": {"text": "Hi."}}}}}})
    _place(studio, 400, 100)
    far = _diag(studio, "door")
    assert far["blocking"]["code"] == "distance" and _observed(far, "distance")["detail"] == {"distance": 250.0,
                                                                                             "radius": 72.0}
    _place(studio, 220, 100, facing="right")  # (the door is behind, 70 px away: within reach, past touching)
    behind = _diag(studio, "door")
    assert behind["blocking"]["code"] == "facing" and _observed(behind, "facing")["detail"]["alignment"] == -1.0
    _place(studio, 100, 100, facing="right")  # (the Sign is nearer, the same way)
    crowded = _diag(studio, "door")
    selection = _observed(crowded, "selection")
    assert crowded["blocking"]["code"] == "selection" and selection["detail"]["chosen"] == "sign"
    assert [c["entity_id"] for c in selection["detail"]["candidates"]] == ["sign", "door"]
    assert interaction.resolve_interaction_candidate(studio.window).entity_id == "sign"  # (the game agrees)
    _place(studio, 190, 100, facing="left")  # (beyond the door, facing it: the Sign is out of reach)
    clear = _diag(studio, "door")
    assert clear["available"] is True and clear["blocking"] is None and clear["how"] == "interact"
    assert interaction.resolve_interaction_candidate(studio.window).entity_id == "door"


# --------------------------------------------------------------------- a door used by walking into it

def test_a_touch_door_hidden_by_show_when_still_works_by_touch_and_says_so(made: Any) -> None:
    touch = dict(DOOR, behaviours=["SceneTransition", "ConditionalActivator"])
    touch["behaviour_config"] = {"SceneTransition": {"target_scene": "cellar", "allow_interact": False,
                                                     "trigger_on_touch": True},
                                 "ConditionalActivator": {"require_flags": ["has_key"]}}
    studio = made(dict(HERO, x=400), touch)  # (well away: the game updates here, and touching would use the door)
    studio.window.on_update(1 / 60)
    out = _diag(studio, "door")
    assert out["how"] == "touch" and out["available"] is True and out["blocking"] is None
    assert [n["code"] for n in out["notes"]] == ["hidden_but_touch_works"] and out["touch"]["checks_show_when"] is False
    overlapping = next(r for r in out["touch"]["rules"] if r["code"] == "overlapping")
    assert overlapping["ok"] is False and "walk into it" in overlapping["message"]
    _place(studio, 150, 100)
    assert next(r for r in _diag(studio, "door")["touch"]["rules"] if r["code"] == "overlapping")["ok"] is True


def test_a_behaviour_with_its_own_rule_is_not_analysed(made: Any) -> None:
    studio = made(HERO, {"id": "lever", "name": "Lever", "x": 150, "y": 100, "sprite": PICTURE,
                         "behaviours": ["ToggleSwitch"]})
    out = _diag(studio, "lever")
    assert out["not_analysed"] == [{"behaviour": "ToggleSwitch", "why": "its own rule decides; not analysed"}]
    rule = _observed(out, "behaviours")["detail"]["behaviours"][0]["rules"][0]
    assert rule["ok"] is None and rule["code"] == "own_rule"


# --------------------------------------------------------------------- read only, bounded

def test_reading_changes_nothing(made: Any) -> None:
    studio = made(HERO, DOOR, GUIDE, dict(DOOR, id="gated", require_flags=["has_key"]))
    window = studio.window
    hero = _sprite(studio, "hero")

    def state() -> Any:
        dialogue = next(b for b in _sprite(studio, "guide").mesh_behaviours_runtime if type(b).__name__ == "Dialogue")
        return (dict(window.game_state_controller.state.flags), dict(window.game_state_controller.state.counters),
                dict(window.game_state_controller.state.values), window.event_bus.emitted,
                len(window._mesh_event_queue), (hero.center_x, hero.center_y), dialogue._has_played,
                sorted(dialogue._choice_history), len(list(window.scene_controller.all_sprites)))

    before = state()
    for entity_id in ("door", "guide", "gated", "ghost"):
        _diag(studio, entity_id)
    assert state() == before


def test_answers_are_bounded(made: Any) -> None:
    crowd = [{"id": f"s{i:02}", "name": "C:\\Users\\ann\\private\\sign.png", "x": 120 + i, "y": 100,
              "sprite": PICTURE, "behaviours": ["Dialogue"],
              "behaviour_config": {"Dialogue": {"once": False, "dialogue": {"start": "a", "nodes": {"a": {
                  "text": "Hi.", "choices": [{"id": f"c{j}", "text": "x" * 500, "require_flags": [f"f{j}"]}
                                             for j in range(40)]}}}}}} for i in range(30)]
    studio = made(HERO, *crowd)
    out = _diag(studio, "s05")
    assert len(_observed(out, "selection")["detail"]["candidates"]) == runtime_diagnose.CANDIDATES_MAX
    assert len(out["dialogue"]["choices"]) == runtime_diagnose.CHOICES_MAX
    said = json.dumps(out)
    assert "ann" not in said and len(said) < 100_000


# --------------------------------------------------------------------- the way in

def test_over_mcp_editing_playing_no_studio_and_no_token(made: Any, tmp_path: Path) -> None:
    studio = made(HERO, dict(DOOR, require_flags=["has_key"]))
    studio.on_ai_proposal = studio.on_ai_decided = lambda *_: None
    host = StudioAIHost(studio)
    host.start()
    stop = threading.Event()
    thread = threading.Thread(target=lambda: [host.drain() or time.sleep(0.002) for _ in iter(stop.is_set, True)],
                              daemon=True)
    thread.start()
    root = str(studio.project.root)
    try:
        studio.mode = "edit"
        assert tools.debug_interaction("door", root=root)["status"] == "not_playing"
        studio.mode = "play"
        out = tools.debug_interaction("door", root=root)
        assert out["status"] == "playing" and out["blocking"]["code"] == "in_room" and out["flags"] == {"has_key": False}
        assert tools.debug_interaction("", root=root)["reason"] == "invalid_request"
        info = read_live_session_file(root)
        assert info is not None
        req = request.Request(f"http://127.0.0.1:{info['port']}/live/debug/interaction?entity=door",
                              headers={"Authorization": "Bearer wrong"})
        with pytest.raises(error.HTTPError) as caught:
            request.urlopen(req, timeout=2)  # noqa: S310 - loopback
        assert caught.value.code == 401
        caught.value.close()
    finally:
        stop.set()
        thread.join(timeout=2)
        host.stop()
    assert tools.debug_interaction("door", root=str(tmp_path))["reason"] in ("studio_not_open", "not_a_project")
