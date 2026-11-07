"""Milestone 16 Stage 5A hardening: HD-2D asset paths stay inside the project and structure numbers are finite.
One rule (engine.hd2d.settings.asset_path) shapes every path; file containment (links followed) is checked where
the project's files are known; Mesh Studio's edits and AI changes meet the same checks with the same words."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.glb import model_problem
from engine.hd2d.settings import Hd2dSettingsError, asset_path, parse_hd2d

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]
CROSSING = REPO / "tooling" / "hd2d_assets" / "stone_crossing.glb"
MODEL = "assets/models/stone_crossing.glb"


@pytest.mark.parametrize(("raw", "normal"), [
    ("assets/models/a.glb", "assets/models/a.glb"),
    ("./assets/models/a.glb", "assets/models/a.glb"),
    ("assets\\models\\a.glb", "assets/models/a.glb"),
    ("assets/./models/a.glb", "assets/models/a.glb"),
])
def test_project_relative_paths_are_kept_and_normalised(raw: str, normal: str) -> None:
    assert asset_path(raw, "model") == normal


@pytest.mark.parametrize("raw", ["../outside.glb", "assets/../../outside.glb", "/etc/outside.glb", "C:/outside.glb",
                                 "c:outside.glb", "\\\\server\\share\\outside.glb", "", "   ", "a\0b.glb"])
def test_paths_leaving_the_project_are_refused(raw: str) -> None:
    with pytest.raises(Hd2dSettingsError):
        asset_path(raw, "model")
    if raw.strip():  # a blank name with ".glb" added is a (strange) file name, not an escape
        with pytest.raises(Hd2dSettingsError):
            parse_hd2d({"structures": [{"model": raw if raw.endswith(".glb") else raw + ".glb"}]})


def test_the_ground_texture_follows_the_same_rule() -> None:
    assert parse_hd2d({"ground": {"texture": "./assets/grass.png"}}).ground.texture == "assets/grass.png"
    with pytest.raises(Hd2dSettingsError, match="ground.texture must stay inside the project"):
        parse_hd2d({"ground": {"texture": "../grass.png"}})


@pytest.mark.parametrize("raw", [
    {"structures": [{"model": "a.glb", "x": math.nan}]},
    {"structures": [{"model": "a.glb", "scale": math.inf}]},
    {"structures": [{"model": "a.glb", "rotation": -math.inf}]},
    {"ground": {"to": [math.nan, 10]}},
    {"camera": {"pitch": math.nan}},
    {"sun": [math.nan, 0, 1]},
    {"ambient": math.nan},
])
def test_non_finite_numbers_are_refused_by_the_settings(raw: dict) -> None:
    with pytest.raises(Hd2dSettingsError, match="finite"):
        parse_hd2d(raw)


def _room() -> dict:
    return {"name": "t", "entities": [], "settings": {"hd2d": {
        "structures": [{"id": "crossing", "model": MODEL, "x": 512, "y": 384}], "ground": {"to": [1024, 768]}}}}


@pytest.mark.parametrize(("change", "message"), [
    (lambda r: ops.place_structure(r, MODEL, math.nan, 1), "x must be a finite number"),
    (lambda r: ops.set_structure(r, "crossing", rotation=math.inf), "rotation must be a finite number"),
    (lambda r: ops.set_structure(r, "crossing", scale=math.nan), "scale must be a finite number"),
    (lambda r: ops.place_structure(r, "../outside.glb", 1, 1), "must stay inside the project"),
    (lambda r: ops.place_structure(r, "C:/outside.glb", 1, 1), "must stay inside the project"),
])
def test_structure_ops_refuse_non_finite_numbers_and_escaping_paths(change, message: str) -> None:
    with pytest.raises(ops.OpError, match=message):
        change(_room())


def test_a_valid_model_is_stored_normalised() -> None:
    room, sid = ops.place_structure(_room(), "./assets\\models\\stone_crossing.glb", 64, 64)
    assert ops.find_structure(room, sid)["model"] == MODEL


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    sys.path.insert(0, str(REPO / "tooling"))
    import hd2d_floors_demo

    return hd2d_floors_demo.build(tmp_path / "proj")


def _linked_model(project: Path, tmp_path: Path) -> str:
    """A model reached through a folder link in the project that points outside it (a symlink; on Windows,
    where symlinks need a privilege, a directory junction). Returns its project-relative path."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "outside.glb").write_bytes(CROSSING.read_bytes())
    link = project / "assets" / "models" / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(outside), str(link))
    return "assets/models/linked/outside.glb"


def test_model_problem_refuses_escapes_and_links_out_of_the_project(project: Path, tmp_path: Path) -> None:
    assert model_problem(project, MODEL) is None
    assert "must stay inside the project" in model_problem(project, "../outside.glb")
    assert "lies outside the project" in model_problem(project, _linked_model(project, tmp_path))


def test_studio_and_ai_meet_the_same_checks_with_the_same_words(project: Path) -> None:
    from engine.authoring_session import open_project

    project_doc = open_project(project)
    cases = [({"op": "place_structure", "model": "../outside.glb", "x": 1, "y": 1}, model_problem(project, "../outside.glb")),
             ({"op": "place_structure", "model": "assets/models/missing.glb", "x": 1, "y": 1},
              model_problem(project, "assets/models/missing.glb")),
             ({"op": "set_structure", "structure_id": "crossing", "x": math.nan}, "x must be a finite number")]
    for change, words in cases:
        with pytest.raises(authoring.ChangeError) as caught:
            authoring.apply(project_doc, [change])
        assert words and words in str(caught.value), change
    # what Mesh Studio's inspector does with a typed 'nan' (engine.studio_hd2d.Hd2dView.set_metres -> set_structure)
    with pytest.raises(ops.OpError, match="x must be a finite number"):
        ops.set_structure(project_doc.scene(), "crossing", x=float("nan"))


def test_the_runtime_refuses_a_scene_asset_linked_from_outside_its_content(project: Path, tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.hd2d import runtime

    linked = _linked_model(project, tmp_path)
    monkeypatch.setattr("engine.paths.get_content_roots", lambda: [project])
    resolve = runtime._contained(lambda rel: project / rel)
    assert resolve(MODEL) == project / MODEL
    with pytest.raises(Hd2dSettingsError, match="outside the project's content"):
        resolve(linked)
