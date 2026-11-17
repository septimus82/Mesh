"""Milestone 21C1: a sound emitter set to be quieter behind walls is, while a wall stands between it and the listener.

Headless, as tests/test_sound_emitters.py: a stand-in window, the audio manager on a stand-in backend that counts every
player made and released, and stand-in walls (a navigation grid's wall tiles for a 2D room, ``engine.hd2d.world.Wall``
boxes for an HD-2D one). Nothing is played aloud. The real-window check is tests/test_sound_occlusion_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.audio as audio_mod
import engine.project_ops as ops
from engine import sound_emitters as se
from engine import sound_occlusion as occ
from engine.hd2d.world import Wall, _wall
from engine.pathfinding.nav_grid import NavGrid
from tests.test_audio_buses_and_scene_music import Backend
from tests.test_sound_emitters import BIRDS, WATER, _emit, _run, _sprite, _window

pytestmark = pytest.mark.fast

KEY = "emitter:room:machine"


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    return _backend(monkeypatch)


def _backend(monkeypatch: pytest.MonkeyPatch, missing: tuple[str, ...] = ()) -> Backend:
    fake = Backend(missing)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    return fake


CLEAR = 0.8  # an emitter's default volume, inside its full-strength radius
BEHIND = CLEAR * se.OCCLUDED


def _wall_box(x0: float, y0: float, x1: float, y1: float, top: float = 2.5, bottom: float = 0.0) -> Wall:
    return Wall("test/col_wall", (x0, y0, bottom), (x1, y1, top))


def _hd2d(window: Any, *walls: Wall) -> Any:
    """The window's room is an HD-2D one with these wall colliders (m)."""
    window.hd2d_world = SimpleNamespace(walls=list(walls))
    return window.hd2d_world


def _grid(walls: set[tuple[int, int]], width: int = 40, height: int = 20) -> NavGrid:
    return NavGrid(width=width, height=height, tile_w=32, tile_h=32, blocked=frozenset(y * width + x for x, y in walls))


def _two_d(window: Any, walls: set[tuple[int, int]]) -> None:
    """The window's room is a 2D one with these wall tiles."""
    grid = _grid(walls)
    window.scene_controller.get_nav_grid = lambda: grid


def _machine(window: Any, x: float = 320.0, y: float = 0.0, **cfg: Any) -> Any:
    """A humming machine 10 m east of the origin, heard at full strength for 12 m and up to 30 m."""
    return _emit(window, "machine", x, y, **{"radius": 384, "distance": 960, "fade_in": 0.0, "occlusion": True, **cfg})


def _level(window: Any, key: str = KEY) -> float:
    track = window.audio._loops.get(key)
    return track.volume if track is not None else 0.0


def _pan(window: Any, key: str = KEY) -> float:
    return window.audio._loops[key].pan or 0.0


# ---------------------------------------------------------------- the setting
def test_the_setting_is_off_unless_set_and_checked_with_a_reason() -> None:
    assert se.parse_emitter({"sound": WATER}).occlusion is False  # a room made before Milestone 21C1
    assert se.parse_emitter({"sound": WATER, "occlusion": True}).occlusion is True
    with pytest.raises(se.EmitterError, match="occlusion must be true or false"):
        se.parse_emitter({"sound": WATER, "occlusion": "walls"})


# ---------------------------------------------------------------- the question, in a 2D room
def test_a_wall_tile_on_the_line_is_in_the_way_and_the_two_ends_own_tiles_are_not() -> None:
    wall = ("2d", _grid({(5, y) for y in range(0, 6)}))  # a wall along x = 5 tiles, 6 tiles tall
    here = (48.0, 48.0, 0.0)
    assert occ.blocked(wall, [], here, (304.0, 48.0, 0.0))  # straight through it
    assert not occ.blocked(wall, [], here, (112.0, 48.0, 0.0))  # this side of it
    assert not occ.blocked(wall, [], (48.0, 300.0, 0.0), (304.0, 300.0, 0.0))  # past its end (row 9)
    assert not occ.blocked(wall, [], here, (176.0, 48.0, 0.0))  # a machine set in the wall itself: heard in front
    assert not occ.blocked(wall, [], (176.0, 48.0, 0.0), (304.0, 48.0, 0.0))  # a listener standing in a wall tile
    assert not occ.blocked(wall, [], here, (-500.0, 48.0, 0.0))  # outside the map: no wall there
    assert not occ.blocked(None, [], here, (304.0, 48.0, 0.0))  # a room with no walls


def test_a_line_does_not_squeeze_between_two_wall_tiles_that_meet_at_their_corners() -> None:
    corner = ("2d", _grid({(4, 5), (5, 4)}))  # a wall's corner drawn in two tiles: (4,4)-(5,5) passes between them
    assert occ.blocked(corner, [], (4 * 32 + 16.0, 4 * 32 + 16.0, 0.0), (5 * 32 + 16.0, 5 * 32 + 16.0, 0.0))
    assert occ.blocked(corner, [], (2 * 32 + 16.0, 2 * 32 + 16.0, 0.0), (7 * 32 + 16.0, 7 * 32 + 16.0, 0.0))
    one = ("2d", _grid({(4, 5)}))  # one of them alone: the way past it is open
    assert not occ.blocked(one, [], (2 * 32 + 16.0, 2 * 32 + 16.0, 0.0), (7 * 32 + 16.0, 7 * 32 + 16.0, 0.0))


# ---------------------------------------------------------------- the question, in an HD-2D room
def test_only_walls_a_person_cant_see_over_and_that_arent_posts_are_in_a_sounds_way() -> None:
    wall, fence, rail = _wall_box(0, 0, 2, 0.2), _wall_box(0, 0, 2, 0.12, top=1.0), _wall_box(0, 0, 6, 0.12, 2.65, 2.0)
    post, table, lintel = _wall_box(0, 0, 0.24, 0.24, top=2.85), _wall_box(0, 0, 1.2, 0.8, top=0.85), _wall_box(0, 0, 1.2, 0.2, 2.5, 2.0)
    kept = occ.acoustic_walls(("3d", None, [wall, fence, rail, post, table, lintel]))
    assert kept == [wall]
    assert occ.acoustic_walls(None) == [] and occ.acoustic_walls(("2d", _grid(set()))) == []


def test_a_wall_is_in_the_way_only_of_a_line_through_it() -> None:
    wall = _wall_box(5.0, -2.0, 5.2, 2.0)  # 4 m long, 2.5 m tall, 5 m east
    what = ("3d", None, [wall])
    feet = (0.0, 0.0, 0.0)
    assert occ.blocked(what, [wall], feet, (320.0, 0.0, 0.0))  # 10 m east, on the ground: through it
    assert not occ.blocked(what, [wall], feet, (128.0, 0.0, 0.0))  # 4 m east: this side of it
    assert not occ.blocked(what, [wall], feet, (320.0, 200.0, 0.0))  # 10 m east, 6.25 m north: round its end
    assert not occ.blocked(what, [wall], feet, (320.0, 0.0, 192.0))  # 6 m up (a plateau): over its top
    assert occ.blocked(what, [wall], feet, (320.0, 0.0, 64.0))  # 2 m up: still behind it
    assert not occ.blocked(what, [wall], (0.0, 0.0, 96.0), (320.0, 0.0, 96.0))  # both 3 m up (on a deck): over it


def test_a_doorway_lets_the_sound_through_under_its_lintel() -> None:
    west, east = _wall_box(-2.5, 5.0, -0.6, 5.2), _wall_box(0.6, 5.0, 2.5, 5.2)  # a cottage's south wall, its door open
    lintel = _wall_box(-0.6, 5.0, 0.6, 5.2, top=2.5, bottom=2.0)
    walls = occ.acoustic_walls(("3d", None, [west, east, lintel]))
    assert lintel not in walls
    what = ("3d", None, [west, east, lintel])
    assert not occ.blocked(what, walls, (0.0, 0.0, 0.0), (0.0, 320.0, 0.0))  # through the doorway
    assert occ.blocked(what, walls, (48.0, 0.0, 0.0), (48.0, 320.0, 0.0))  # 1.5 m to its side: the wall


def test_a_turned_wall_is_in_the_way_where_it_stands_not_where_its_box_reaches() -> None:
    turned = _wall("test/col_wall", (-3.0, -0.1, 0.0), (3.0, 0.1, 2.5), (5.0, 0.0, 0.0), 45.0, 1.0)  # 6 m, south-west to north-east
    assert turned.turned is not None
    what = ("3d", None, [turned])
    assert occ.blocked(what, [turned], (4.0 * 32, 2.0 * 32, 0.0), (7.0 * 32, 0.0, 0.0))  # across it
    # inside the box round its corners (x 2.9 to 7.1, y -2.1 to 2.1) but along its north-west side: clear
    assert not occ.blocked(what, [turned], (3.0 * 32, 1.5 * 32, 0.0), (5.5 * 32, 2.0 * 32, 0.0))


def test_a_wall_one_end_stands_in_does_not_count() -> None:
    wall = _wall_box(5.0, -2.0, 5.2, 2.0)
    what = ("3d", None, [wall])
    assert not occ.blocked(what, [wall], (0.0, 0.0, 0.0), (5.1 * 32, 0.0, 16.0))  # a machine set into the wall


# ---------------------------------------------------------------- heard: clear, behind a wall, and between
def test_behind_a_wall_it_is_quieter_and_heard_less_from_its_side(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _machine(window)
    _run(window, 1.0)
    clear, side = _level(window), _pan(window)
    assert clear == pytest.approx(CLEAR, abs=0.005) and side == pytest.approx(se.pan(320, 320, se.parse_emitter({"radius": 384, "distance": 960})))
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))  # a wall between them now
    player.center_x = 8.0
    _run(window, 3.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005)
    assert _pan(window) == pytest.approx(se.pan(312, 312, se.parse_emitter({"radius": 384, "distance": 960})) * se.OCCLUDED_PAN, abs=0.01)
    assert 0 < _pan(window) < side  # still from its side, less so
    assert window.soundscape.diagnostics()["behind_walls"] == [KEY]
    assert len(backend.players) == 1 and len(backend.live()) == 1  # the same loop throughout


def test_distance_still_counts_behind_a_wall(backend: Backend) -> None:
    player = _sprite(-320, 0)  # 20 m from it: between full strength (12 m) and silence (30 m)
    window = _window(player)
    _machine(window)
    emitter = se.parse_emitter({"radius": 384, "distance": 960})
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 2.0)
    far = _level(window)
    assert far == pytest.approx(0.8 * se.gain(640, emitter) * se.OCCLUDED, abs=0.005) and 0.02 < far < BEHIND
    player.center_x = 96.0  # 7 m from it, still behind the wall
    _run(window, 2.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005)


def test_going_behind_a_wall_and_out_again_eases_with_no_jump_and_no_restart(backend: Backend) -> None:
    player = _sprite(0, 200)  # north of the wall's end: a clear line
    window = _window(player)
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 1.0)
    assert _level(window) == pytest.approx(CLEAR, abs=0.005)
    heard = []
    for leg in (range(200, -1, -4), [0] * 90, range(0, 201, 4), [200] * 90):  # walk behind it, stand, walk out, stand
        for y in leg:
            player.center_y = float(y)
            _run(window, 1 / 60)
            heard.append(_level(window))
    assert min(heard) == pytest.approx(BEHIND, abs=0.01) and heard[-1] == pytest.approx(CLEAR, abs=0.01)
    steps = [abs(a - b) for a, b in zip(heard, heard[1:])]
    assert max(steps) < 0.02, "no frame changes its loudness by more than 2 % of full"
    low = heard.index(min(heard))
    assert all(a + 1e-6 >= b for a, b in zip(heard[:low], heard[1:low + 1]))  # only falling on the way behind
    assert all(a <= b + 1e-6 for a, b in zip(heard[low:], heard[low + 1:]))  # only rising on the way out
    assert len(backend.players) == 1 and not backend.players[0].released  # one player: never stopped or restarted


def test_crossing_a_walls_edge_again_and_again_keeps_one_loop_and_never_cuts_it(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    heard, before = [], _level(window)
    for i in range(240):  # 4 s: a step out from behind the wall and back, every 5 frames
        player.center_y = 200.0 if (i // 5) % 2 else 0.0
        _run(window, 1 / 60)
        heard.append(_level(window))
        assert abs(heard[-1] - before) < 0.02 or len(heard) == 1
        before = heard[-1]
    assert all(BEHIND - 0.01 <= level <= CLEAR + 0.01 for level in heard[1:])
    assert len(backend.players) == 1 and len(backend.live()) == 1


def test_it_comes_into_reach_behind_a_wall_already_quiet(backend: Backend) -> None:
    player = _sprite(-1200, 0)  # out of reach
    window = _window(player)
    _machine(window, fade_in=0.0)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 0.5)
    assert backend.players == [] and window.soundscape.wall_asks == 0  # out of reach: nothing played, nothing asked
    player.center_x = 0.0  # 10 m from it, behind the wall
    loudest = 0.0
    for _ in range(120):
        _run(window, 1 / 60)
        loudest = max(loudest, _level(window))
    assert loudest == pytest.approx(BEHIND, abs=0.005)  # never loud first and then turned down
    player.center_x = -1200.0  # away again: it stops, and is asked afresh when back
    _run(window, 3.0)
    assert KEY not in window.audio._loops and window.soundscape.emitters[0].asked is None


def test_each_emitter_has_its_own_answer(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _machine(window)  # east, behind the wall
    _emit(window, "birds", -320, 0, sound=BIRDS, radius=384, distance=960, fade_in=0.0, occlusion=True)  # west: clear
    _emit(window, "open", 320, 64, radius=384, distance=960, fade_in=0.0)  # behind it too, but not set to mind walls
    _hd2d(window, _wall_box(5.0, -4.0, 5.2, 4.0))
    _run(window, 3.0)
    scale = window.soundscape.headroom
    assert _level(window) == pytest.approx(BEHIND * scale, abs=0.005)
    assert _level(window, "emitter:room:birds") == pytest.approx(CLEAR * scale, abs=0.005)
    assert _level(window, "emitter:room:open") == pytest.approx(CLEAR * scale, abs=0.005)
    assert window.soundscape.diagnostics()["behind_walls"] == [KEY]


# ---------------------------------------------------------------- compatibility: rooms made before this
def test_an_emitter_not_set_to_mind_walls_is_heard_exactly_as_before(backend: Backend) -> None:
    def walk(walls: bool) -> tuple[list[tuple[float, float]], int]:
        player = _sprite(0, 0)
        window = _window(player)
        _emit(window, "machine", 320, 0, radius=64, distance=640, fade_in=0.0)  # as M21B saved it: no occlusion key
        if walls:
            _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
        out = []
        for x in range(0, 640, 16):
            player.center_x = float(x)
            _run(window, 0.1)
            out.append((round(_level(window), 6), round(_pan(window), 6)))
        return out, window.soundscape.wall_asks

    with_walls, asks = walk(True)
    without, _ = walk(False)
    assert with_walls == without and asks == 0  # the same levels and pans, and the walls were never looked at


# ---------------------------------------------------------------- the cost: when the question is asked
def test_the_question_is_asked_only_when_someone_has_moved_and_never_of_one_out_of_reach(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _machine(window)
    for i in range(20):  # twenty more, set to mind walls, all out of reach
        _emit(window, f"far{i}", 4000 + 40 * i, 0, occlusion=True)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    scape = window.soundscape
    _run(window, 2.0)
    assert scape.wall_asks == 1  # 120 updates standing still: asked once
    player.center_x = 3.0  # moved, within the same cell (8 px)
    _run(window, 0.5)
    assert scape.wall_asks == 1
    player.center_x = 9.0  # into the next cell
    _run(window, 0.5)
    assert scape.wall_asks == 2
    assert all(live.asked is None for live in scape.emitters[1:])  # none of the far ones


def test_at_most_a_few_are_asked_in_one_update_and_none_starts_before_its_answer(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    for i in range(10):  # ten machines behind the wall (five sounds, so that all ten may play)
        sprite = _sprite(320 + 8 * i, -40 + 8 * i, eid=f"m{i}")
        se.soundscape_of(window).register(sprite, se.parse_emitter(
            {"sound": f"assets/ambience/hum_{i % 5}.wav", "radius": 384, "distance": 960, "fade_in": 0.0, "occlusion": True}))
    _hd2d(window, _wall_box(5.0, -4.0, 5.2, 4.0))
    scape = window.soundscape
    asked, loudest = [], 0.0
    for _ in range(30):
        before = scape.wall_asks
        _run(window, 1 / 60)
        asked.append(scape.wall_asks - before)
        loudest = max([loudest] + [p.volume for p in backend.live()])
    assert max(asked) <= se.OCCLUSION_ASKS and sum(asked) == 10 and asked[3:] == [0] * 27  # 4, 4, 2, then none
    assert len(backend.live()) == 10 and loudest <= BEHIND + 0.005  # every one started already quiet
    player.center_x = 16.0  # the listener moves on: all ten are asked again, over three updates, the longest unasked first
    order = []
    for _ in range(3):
        _run(window, 1 / 60)
        order.append(sorted(live.key for live in scape.emitters if live.asked_at == scape.updates))
    assert [len(batch) for batch in order] == [4, 4, 2] and len({k for batch in order for k in batch}) == 10


def test_one_that_must_wait_its_turn_to_be_asked_starts_only_once_it_has_been(backend: Backend) -> None:
    """Ten streams of one sound behind a wall: three may play (the nearest), and they are the last in the room, so
    their turn to be asked comes after the others'. None of them starts loud and is then turned down."""
    window = _window(_sprite(0, 0))
    for i in range(10):  # the further ones first; the last three within their full-strength radius
        x = 900.0 - 60.0 * i if i < 7 else 320.0 + 8.0 * i
        _emit(window, f"s{i}", x, 0.0, radius=384, distance=960, fade_in=0.0, occlusion=True)
    _hd2d(window, _wall_box(5.0, -4.0, 5.2, 4.0))
    scape = window.soundscape
    loudest, started_unasked = 0.0, []
    for _ in range(12):
        _run(window, 1 / 60)
        loudest = max([loudest] + [p.volume for p in backend.live()])
        started_unasked += [live.key for live in scape.emitters if live.playing and live.asked is None]
    assert sorted(k.rsplit(":", 1)[1] for k in window.audio._loops) == ["s7", "s8", "s9"]
    assert started_unasked == [] and loudest <= BEHIND + 0.005


# ---------------------------------------------------------------- the room's walls change
def test_a_wall_put_up_or_taken_down_is_heard_without_anyone_moving(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _machine(window)
    world = _hd2d(window)  # an HD-2D room with no wall yet
    _run(window, 1.0)
    assert _level(window) == pytest.approx(CLEAR, abs=0.005)
    world.walls = [_wall_box(5.0, -2.0, 5.2, 2.0)]  # (as World.set_scatter does: a new list of walls)
    _run(window, 2.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005)
    world.walls = []
    heard = []
    for _ in range(120):
        _run(window, 1 / 60)
        heard.append(_level(window))
    assert heard[-1] == pytest.approx(CLEAR, abs=0.005) and max(abs(a - b) for a, b in zip(heard, heard[1:])) < 0.02
    assert len(backend.players) == 1


def test_another_room_has_its_own_walls_and_the_last_rooms_loop_stops(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 2.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005)
    se.reset(window, "cellar", {})  # through a door: another room, no walls between
    window.hd2d_world = None
    sprite = _sprite(320, 0, eid="machine")
    se.soundscape_of(window).register(sprite, se.parse_emitter(
        {"sound": WATER, "radius": 384, "distance": 960, "fade_in": 0.0, "occlusion": True}))
    assert window.soundscape.blockers is None and window.soundscape.walls == []  # the last room's walls let go
    _run(window, 3.0)
    assert _level(window, "emitter:cellar:machine") == pytest.approx(CLEAR, abs=0.005)
    assert KEY not in window.audio._loops and len(backend.live()) == 1  # the first room's loop faded and was released
    se.reset(window, "room", {})  # the same room loaded again (a reload): its emitter is back, asked afresh
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _machine(window)
    _run(window, 3.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005) and len(backend.live()) == 1


# ---------------------------------------------------------------- a 2D room
def test_in_a_2d_room_its_wall_tiles_are_the_walls(backend: Backend) -> None:
    player = _sprite(48, 48)
    window = _window(player)
    _machine(window, x=304.0, y=48.0)
    _two_d(window, {(5, y) for y in range(0, 4)})  # a wall four tiles tall
    _run(window, 2.0)
    assert _level(window) == pytest.approx(BEHIND, abs=0.005)
    player.center_y = 300.0  # north of it: the line passes the wall's end
    heard = []
    for _ in range(120):
        _run(window, 1 / 60)
        heard.append(_level(window))
    emitter = se.parse_emitter({"radius": 384, "distance": 960})
    assert heard[-1] == pytest.approx(0.8 * se.gain(((304 - 48) ** 2 + 252 ** 2) ** 0.5, emitter), abs=0.005)
    assert max(abs(a - b) for a, b in zip(heard, heard[1:])) < 0.02 and len(backend.players) == 1
    _two_d(window, set())  # the room's tiles edited (another navigation grid): no walls left
    player.center_y = 48.0
    _run(window, 2.0)
    assert _level(window) == pytest.approx(CLEAR, abs=0.005)


# ---------------------------------------------------------------- volumes, muting, the editor, play and stop
def test_the_ambience_and_master_volumes_and_muting_apply_as_ever(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 2.0)
    player = backend.live()[0]
    assert player.volume == pytest.approx(BEHIND, abs=0.005)
    window.audio.set_ambience_volume(0.5)
    assert player.volume == pytest.approx(BEHIND * 0.5, abs=0.005)  # at once, the loop not restarted
    window.audio.set_master_volume(0.5)
    assert player.volume == pytest.approx(BEHIND * 0.25, abs=0.005)
    window.audio.set_muted(True)
    _run(window, 0.5)
    assert player.volume == 0.0
    window.audio.set_muted(False)
    _run(window, 0.5)
    assert player.volume == pytest.approx(BEHIND * 0.25, abs=0.005) and len(backend.players) == 1


def test_the_editor_hears_nothing_and_asks_nothing(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    window.audio.scene_music = False  # Mesh Studio's editor
    _run(window, 1.0)
    assert backend.players == [] and window.soundscape.wall_asks == 0


def test_playing_and_stopping_again_and_again_leaves_no_player_behind(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    for _ in range(5):  # a play-test started and stopped: the room loaded, heard, left
        se.reset(window, "room", {})
        _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
        _machine(window)
        _run(window, 1.0)
        assert len(backend.live()) == 1
        se.reset(window, "", {})
        _run(window, 2.0)
        assert backend.live() == []
    assert len(backend.players) == 5  # one each time, as without walls
    window.audio.shutdown()
    assert backend.live() == []


def test_a_sound_file_that_cant_be_played_is_silent_and_harmless(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _backend(monkeypatch, missing=(WATER,))
    player = _sprite(0, 0)
    window = _window(player)
    _machine(window)
    _hd2d(window, _wall_box(5.0, -2.0, 5.2, 2.0))
    _run(window, 1.0)
    player.center_x = 40.0
    _run(window, 1.0)
    assert broken.players == [] and window.audio.loops() == {}  # nothing plays; nothing raised


# ---------------------------------------------------------------- authoring: the op, undo, save, AI tools, export
def _room() -> dict[str, Any]:
    return {"name": "Room", "settings": {}, "entities": []}


def test_the_op_sets_it_and_off_is_no_setting_at_all() -> None:
    scene, eid = ops.place_blank(_room(), "room", "Sound", 320, 240)
    scene = ops.set_sound_emitter(scene, eid, sound=WATER)
    assert ops.sound_emitter_of(ops.find_entity(scene, eid))["occlusion"] is False
    assert "occlusion" not in ops.find_entity(scene, eid)["behaviour_config"]["SoundEmitter"]
    on = ops.set_sound_emitter(scene, eid, occlusion=True)
    assert ops.find_entity(on, eid)["behaviour_config"]["SoundEmitter"]["occlusion"] is True
    assert ops.sound_emitter_of(ops.find_entity(on, eid))["occlusion"] is True
    off = ops.set_sound_emitter(on, eid, occlusion=False)
    assert ops.find_entity(off, eid) == ops.find_entity(scene, eid)  # the room as it was before it was ever set
    with pytest.raises(ops.OpError, match="occlusion must be true or false"):
        ops.set_sound_emitter(scene, eid, occlusion="walls")
    generic = ops.set_behaviour_param(scene, eid, "SoundEmitter", "occlusion", True)  # the generic setting path too
    assert ops.sound_emitter_of(ops.find_entity(generic, eid))["occlusion"] is True


def test_an_ai_tool_sets_it_and_it_is_undone_redone_saved_and_read_back(tmp_path: Path) -> None:
    from engine import authoring
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    project = Project(root, world)
    authoring.apply(project, [{"op": "place_blank", "name": "Hum", "x": 96, "y": 96},
                              {"op": "set_sound_emitter", "entity_id": "@0", "sound": WATER, "occlusion": True}])
    hum = next(e for e in project.scene()["entities"] if e.get("name") == "Hum")

    def setting() -> Any:
        entity = next((e for e in project.scene()["entities"] if e.get("name") == "Hum"), None)
        return None if entity is None else entity["behaviour_config"]["SoundEmitter"].get("occlusion")

    assert setting() is True
    project.edit_scene(lambda room: ops.set_sound_emitter(room, hum["id"], occlusion=False))  # the person turns it off
    assert setting() is None
    project.undo()
    assert setting() is True
    project.redo()
    assert setting() is None
    project.undo()
    project.save()
    reopened = Project(root, world)
    saved = next(e for e in reopened.scene()["entities"] if e.get("name") == "Hum")
    assert saved["behaviour_config"]["SoundEmitter"] == {"sound": WATER, "occlusion": True}
    with pytest.raises(authoring.ChangeError, match="true or false"):
        authoring.apply(reopened, [{"op": "set_sound_emitter", "entity_id": hum["id"], "occlusion": "yes"}])


def test_the_scene_loader_and_the_export_take_a_room_with_it(tmp_path: Path) -> None:
    from engine.scene_loader import SceneLoader
    from engine.tooling.asset_manifest import _extract_refs_from_scene

    scene, eid = ops.place_blank(_room(), "room", "Sound", 320, 240)
    scene = ops.set_sound_emitter(scene, eid, sound=WATER, occlusion=True)
    path = tmp_path / "room.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    loaded = SceneLoader().load_scene(str(path))
    assert loaded["entities"][0]["behaviour_config"]["SoundEmitter"]["occlusion"] is True
    refs = {r.asset_id: r.field_path for r in _extract_refs_from_scene(scene, "room.json")}
    assert refs == {WATER: refs[WATER]} and refs[WATER].endswith("behaviour_config.SoundEmitter.sound")
