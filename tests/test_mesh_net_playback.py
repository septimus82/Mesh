import pytest

from mesh_net.playback import Playback
from mesh_net.study import study

pytestmark = pytest.mark.fast


def state(t, *rows):
    return {"v": 1, "type": "state", "tick": t, "players": list(rows), "enemy_hp": 2, "pickup": False, "holder": None}


def test_interpolation_tracks_real_motion_and_never_extrapolates():
    view = Playback()
    for tick in range(5):
        assert view.push(state(tick, [1, tick * 4, 30]), tick / 20)
    assert view.positions(0.225)[1] == pytest.approx((10, 30))
    assert not view.push(state(3, [1, 400, 200]), 1)
    assert view.positions(1)[1] == (16, 30)
    assert view.push(state(8, [2, 40, 80]), 1.1)
    assert view.positions(1.1) == {2: (40, 80)}


def test_disruption_converges_and_the_study_is_reproducible():
    result = study(jitter_ms=110)
    assert result == study(jitter_ms=110)
    assert result["dropped_messages"] and result["old_snapshots_discarded"]
    assert result["max_display_error_px"] > 0 and result["final_error_px"] == 0


def test_demo_displays_latest_owner_and_interpolated_peer():
    from types import SimpleNamespace

    from mesh_net.demo import OTHER, OWN, Arena

    circles = []
    keys = SimpleNamespace(**{name: i for i, name in enumerate(
        "W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    graphics = SimpleNamespace(key=keys, draw_circle_filled=lambda *args: circles.append(args))
    scene = SimpleNamespace(draw=lambda: None)
    camera = SimpleNamespace(use=lambda: None)
    window = SimpleNamespace(push_handlers=lambda **kwargs: None, clear=lambda **kwargs: None,
                             scene_controller=scene, default_camera=camera)
    arena = Arena(window, graphics)
    arena.client = SimpleNamespace(entity=1, state=state(4, [1, 216, 30], [2, 56, 30]))
    for tick in range(5):
        arena.playback.push(state(tick, [1, 200 + tick * 4, 30], [2, 40 + tick * 4, 30]), tick / 20)
    arena.draw(0.2)
    assert (216, 30, 4, OWN) in circles
    assert (48, 30, 4, OTHER) in circles
