"""M17-L3 C2: in Mesh Studio (hidden window, worked through window input events), an HD-2D room's lighting panel says
which lights have one of the room's two shadow maps and which are set to cast shadows but get none, and that is what
the renderer draws: its lamps' shadow slots agree, before and after a light's shadows are switched off (its map
handed on) and undone. The limit (2) and its order are unchanged. Set MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SCENE = "packs/core_regions/scenes/start.json"


def _slots(renderer: Any) -> list[int]:
    return list(renderer.lighting.lamp_slots)


def _lit_allocation(scene: dict) -> list[str]:
    from engine.hd2d import settings as S

    return [s for s in S.shadow_allocation(scene.get("lights"))
            if s in (S.SHADOW_MAP, S.NO_SHADOWS, S.OVER_SHADOW_LIMIT)]


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    # (the AI bridge off for the session only, then as it was: absent stays absent, a value comes back, also when the
    # session fails part way)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        return _allocation_session(tmp_path_factory)


def _allocation_session(tmp_path_factory: pytest.TempPathFactory) -> dict:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.hd2d import settings as S
    from engine.project_scaffold import create_project

    project = tmp_path_factory.mktemp("alloc") / "Shadow maps"
    create_project(project, "Shadow maps", "hd2d_rpg")
    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))  # the template's sky light and its two lamp posts' lamps
    for x in (400.0, 880.0, 960.0):
        scene, index = ops.add_light(scene, x, 400.0, color="Warm", radius=160)
    scene = ops.set_light(scene, index, shadows=False)  # the last: set not to cast shadows
    path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
    out: dict = {}
    d = StudioDriver(project)
    try:
        studio = d.studio
        out["allocation"] = S.shadow_allocation(ops.lights(studio.project.scene()))
        out["slots"] = _slots(d.renderer)
        out["lit"] = _lit_allocation(studio.project.scene())
        d.button("Lighting")
        out["panel"] = d.texts()
        d.button("Light 4:", prefix=True)  # the first lamp set to cast shadows without a map
        d._scroll_panels(lambda: any("earlier in the list" in t for t in d.texts()))  # (its inspector, scrolled to)
        out["light4"] = d.texts()
        d.button("Light 2:", prefix=True)  # the first lamp post's lamp: switch its shadows off
        d.button("Casts shadows: On")
        out["after_off"] = {"allocation": S.shadow_allocation(ops.lights(studio.project.scene())),
                            "slots": _slots(d.renderer), "lit": _lit_allocation(studio.project.scene()),
                            "texts": d.texts()}
        d.key(d.arcade.key.Z, d.arcade.key.MOD_CTRL)
        out["after_undo"] = {"allocation": S.shadow_allocation(ops.lights(studio.project.scene())),
                             "slots": _slots(d.renderer), "lit": _lit_allocation(studio.project.scene())}
    finally:
        d.close()
    return out


def _agrees(lit: list[str], slots: list[int]) -> bool:
    from engine.hd2d import settings as S

    return len(lit) == len(slots) and all((status == S.SHADOW_MAP) == (slot >= 0) for status, slot in zip(lit, slots))


def test_the_rooms_lights_and_what_each_gets(run: dict) -> None:
    from engine.hd2d import settings as S

    assert run["allocation"] == [S.AMBIENT, S.SHADOW_MAP, S.SHADOW_MAP, S.OVER_SHADOW_LIMIT, S.OVER_SHADOW_LIMIT,
                                 S.NO_SHADOWS]
    assert run["slots"] == [0, 1, -1, -1, -1]  # (the renderer: two shadow maps, to the first two that ask)


def test_studio_shows_what_the_renderer_draws(run: dict) -> None:
    assert _agrees(run["lit"], run["slots"])
    panel = run["panel"]
    assert any("Shadow maps: 2 of 2 in use. 2 more lights set to cast shadows get none and shine through walls."
               in t for t in panel), panel
    assert any(t.startswith("Light 2:") and t.endswith(" - shadows") for t in panel)
    assert any(t.startswith("Light 4:") and t.endswith(" - no shadow map") for t in panel)
    assert any("lights earlier in the list have them" in t for t in run["light4"]), run["light4"]


def test_switching_a_lights_shadows_off_hands_its_map_on_in_studio_and_the_renderer(run: dict) -> None:
    from engine.hd2d import settings as S

    after = run["after_off"]
    assert after["allocation"][1:5] == [S.NO_SHADOWS, S.SHADOW_MAP, S.SHADOW_MAP, S.OVER_SHADOW_LIMIT]
    assert after["slots"] == [-1, 0, 1, -1, -1] and _agrees(after["lit"], after["slots"])
    assert any("1 more light set to cast shadows gets none" in t for t in after["texts"])
    undone = run["after_undo"]
    assert undone["slots"] == run["slots"] and undone["allocation"] == run["allocation"]
    assert _agrees(undone["lit"], undone["slots"])
