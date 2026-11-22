"""HD-2D online M3-1: the renderer follows an explicitly set sprite (``Hd2dRenderer.follow_target``) and otherwise the
first sprite with the camera's tag; a net client's SceneView sets its own avatar. The unit cases need no graphics; the
real-window case builds the floors demo's crossing in a hidden window. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import optional_arcade
from engine.hd2d.renderer import PIXELS_PER_METRE, Hd2dRenderer

REPO = Path(__file__).resolve().parents[1]


def sprite(tag: str | None) -> Any:
    return SimpleNamespace(mesh_tag=tag, visible=True)


def renderer(sprites: list[Any], target: Any = None) -> Any:
    """What ``followed`` reads: the scene's sprites (the drawable ones) and the camera's tag."""
    window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=sprites))
    return SimpleNamespace(settings=SimpleNamespace(camera=SimpleNamespace(follow="player")), window=window,
                           follow_target=target, _sprites=lambda: [s for s in sprites if s.visible])


@pytest.mark.fast
def test_unset_target_follows_the_first_tagged_sprite() -> None:
    first, second = sprite("player"), sprite("player")
    assert Hd2dRenderer.followed(renderer([sprite(None), first, second])) is first
    assert Hd2dRenderer.followed(renderer([sprite(None)])) is None


@pytest.mark.fast
def test_an_explicit_target_wins_over_the_tag() -> None:
    first, second = sprite("player"), sprite("player")
    assert Hd2dRenderer.followed(renderer([first, second], second)) is second
    other = sprite(None)  # (it need not carry the tag)
    assert Hd2dRenderer.followed(renderer([first, other], other)) is other


@pytest.mark.fast
def test_a_removed_target_falls_back_to_the_tag() -> None:
    first, gone = sprite("player"), sprite("player")
    assert Hd2dRenderer.followed(renderer([first], gone)) is first
    assert Hd2dRenderer.followed(renderer([], gone)) is None


GL = pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                        reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)")


def crossing_files() -> dict[str, bytes]:
    import json

    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        built = hd2d_floors_demo.build(Path(tmp) / "proj")
        files = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    config = json.loads(files["config.json"])
    files["config.json"] = json.dumps({**config, "master_volume": 0.0}).encode()  # (never heard)
    return files


def hidden_view(files: dict[str, bytes], body: Any) -> None:
    """``body(window, view)`` for a hidden window holding the crossing, as a client's SceneView presents it."""
    from unittest.mock import patch

    from mesh_net.demo import open_arena
    from mesh_net.scene_client import SceneView
    from mesh_net.scene_room import SceneRoom

    original = optional_arcade.arcade.Window.__init__

    def hidden(window: Any, *args: Any, **kwargs: Any) -> None:
        original(window, *args, **{**kwargs, "visible": False})

    def make(window: Any, arcade: Any, root: Path, scene: str) -> Any:
        return SceneView(window, arcade, SceneRoom(root / scene, root))

    with patch.object(optional_arcade.arcade.Window, "__init__", hidden), open_arena(files, (640, 480), make) as view:
        body(view.window, view)


@pytest.mark.integration
@GL
@pytest.mark.parametrize("own", [1, 2])
def test_a_client_window_follows_its_own_avatar(own: int) -> None:
    """Two player-tagged avatars far apart in one HD-2D room: the window of the client that is ``own`` looks at its
    own, whichever is first (and a client with no avatar of its own yet gets the tag's, as single-player does)."""
    pytest.importorskip("arcade")
    positions = {1: (160.0, 300.0), 2: (700.0, 300.0)}

    def check(window: Any, view: Any) -> None:
        renderer = window.hd2d_renderer
        assert renderer is not None and renderer.follow_target is None
        view.sync(None, positions, None, 0.1)
        view.scene.entities.apply_pending_ops(view.scene)  # (what the client's draw does next)
        assert renderer.follow_target is None
        assert renderer.followed() is view.avatars[1], "no explicit target: the first tagged avatar"
        view.sync(None, positions, own, 0.1)
        mine, other = view.avatars[own], view.avatars[3 - own]
        mine_x, other_x = mine.center_x / PIXELS_PER_METRE, other.center_x / PIXELS_PER_METRE
        assert renderer.follow_target is mine and renderer.followed() is mine
        for _ in range(80):  # (the smoothed camera settles on its goal)
            renderer.update(0.1)
        assert renderer.camera.target[0] == pytest.approx(mine_x, abs=0.05)
        assert abs(renderer.camera.target[0] - other_x) > 5
        view.scene.entities.enqueue_despawn(mine)  # (destroyed under the renderer, still set: the tag's, no stale sprite)
        view.scene.entities.apply_pending_ops(view.scene)
        assert renderer.follow_target is mine and renderer.followed() is other
        view.sync(None, {3 - own: positions[3 - own]}, own, 0.1)  # (and the client drops it: unset)
        assert renderer.follow_target is None and renderer.followed() is other

    hidden_view(crossing_files(), check)

