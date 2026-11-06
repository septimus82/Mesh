"""#460 Phase B: an HD-2D room's depth of field set with Mesh Studio's own controls (hidden windows): Camera and sun...
> Depth of field: on (Subtle), Most blur 3, undo / redo; the editing view is unchanged until Preview here; previewing,
the world blurs and Studio's lines are the very same pixels (drawn after it, sharp); the panel says when software
rendering bypasses it; the interior says why the effect is slight there; saved, reopened, played, exported, and
the exported game draws it (on a software rasteriser: bypassed and said). GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

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


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import dof_studio

    out = tmp_path_factory.mktemp("dof_studio")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        return dof_studio.studio(out, export=True)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_it_is_off_until_turned_on_and_then_subtle(run: dict) -> None:
    assert run["before"]["enabled"] is False and run["before"]["error"] is None
    on = run["turned_on"]
    assert on["stored"] == {"enabled": True} and on["renderer_active"]
    if run["software_renderer"]:  # (CI's Mesa: turning it on says why it isn't shown here)
        assert on["message"].startswith("Depth of field is off on this computer: it is drawing with software"), on
    else:
        assert on["message"] == "Depth of field on.", on
    assert run["max_blur_set_undo_redo"] == [3.0, 2.5, 3.0]


def test_the_editing_view_is_unchanged_until_previewed(run: dict) -> None:
    assert run["editing_view_still"], "the comparison needs a still view"
    assert run["editing_view_unchanged_without_preview"] and not run["editing_view_drawn"]


def test_previewing_blurs_the_world_but_not_studio_s_lines(run: dict) -> None:
    preview = run["preview"]
    assert preview["drawn"] and preview["world_changed_share"] > 0.05, preview
    off, on = preview["line_pixels"]
    assert off > 1000 and abs(on - off) <= off * 0.01, preview  # (the lines: drawn after the blur, the same pixels;
    assert preview["line_pixels_same_share"] >= 0.99, preview  # a faint line over a pale world may round either way)


def test_software_rendering_is_said_in_the_panel_and_not_drawn(run: dict) -> None:
    assert run["software_label"] and "software rendering" in run["software_label"][0]
    assert run["software_drawn"] is False


def test_the_interior_says_why_the_effect_is_slight(run: dict) -> None:
    indoor = run["indoor"]
    assert indoor["room"] == "cottage" and indoor["indoor"] and indoor["enabled"] is False
    assert indoor["note"], indoor


def test_it_saves_reopens_plays_and_exports_as_set(run: dict) -> None:
    assert run["saved"].startswith("Saved") and run["in_the_saved_file"] == {"enabled": True, "max_blur": 3.0}
    assert run["reopened"] == {"same": True, "unsaved": []}
    play, export = run["in_play"], run["export"]
    assert play["mode"] == "play" and play["max_blur"] == 3.0
    assert export["code"] == 0 and export["scene_setting"] == {"enabled": True, "max_blur": 3.0}
    bundle = export["bundle_run"]
    assert "failed" not in bundle, bundle
    assert "export" in Path(bundle["engine_from"]).parts, bundle  # (the exported game's own engine)
    assert bundle["max_blur"] == 3.0
    if run["software_renderer"]:  # (a software rasteriser: bypassed, and the room's load says so)
        for seen in (play, bundle):
            assert seen["status"][0] == "unavailable" and not seen["drawn"], seen
        assert play["load_message"] and "software rendering" in play["load_message"]
        assert bundle["message"] and "software rendering" in bundle["message"]
    else:
        for seen in (play, bundle):
            assert seen["status"] == ["on", None] and seen["drawn"], seen
        assert play["radius"] == pytest.approx(3.0)  # (Studio's window is 720 lines tall)
