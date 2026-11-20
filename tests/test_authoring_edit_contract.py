"""A-03: only project_ops functions registered in authoring.EDIT_OPS can be applied as edits.

A read-only getter with an edit's shape (``room_music(scene) -> Doc``) used to be applied as an edit, replacing
the room with the getter's answer. Applying one is now refused, and a new project_ops function is never an edit
until it is registered on purpose."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from engine import authoring, authoring_session
from engine import project_ops as ops
from engine.mcp_server import tools
from engine.project_scaffold import create_project

pytestmark = [pytest.mark.integration]

GETTERS = ["room_music", "weather_sounds_of", "hd2d_camera_of", "hd2d_room_size", "hd2d_sun_of"]
_EDIT_RETURNS = ("Doc", "tuple[Doc, str]", "tuple[Doc, int]")


def _tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.relative_to(root).parts}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.mark.parametrize("op", GETTERS)
def test_a_read_only_getter_is_refused_and_nothing_changes(root: Path, op: str) -> None:
    before = _tree(root)
    result = authoring_session.apply(root, [{"op": op}])
    assert result["ok"] is False and result["reason"] == "invalid_change" and result["op"] == op
    assert "only reads" in result["message"]
    assert _tree(root) == before  # byte-identical: room and every other file


@pytest.mark.parametrize("op", GETTERS)
def test_the_mcp_apply_tool_refuses_a_getter_too(root: Path, op: str) -> None:
    before = _tree(root)
    result = tools.apply_changes([{"op": op}], root=str(root))
    assert result["ok"] is False and result["reason"] == "invalid_change"
    assert _tree(root) == before


def test_a_getter_in_a_batch_refuses_the_whole_batch(root: Path) -> None:
    before = _tree(root)
    result = authoring_session.apply(root, [{"op": "place_prefab", "prefab": "person", "x": 1, "y": 1},
                                            {"op": "room_music"}])
    assert result["ok"] is False and result["index"] == 1
    assert _tree(root) == before


@pytest.mark.parametrize("op", GETTERS)
def test_describe_and_operations_list_no_read_only_op(op: str) -> None:
    assert op not in authoring.operations()
    assert op not in {d["op"] for d in authoring.describe()}
    assert op in authoring.NOT_EDITS and op not in authoring.EDIT_OPS


def test_every_registered_edit_exists_and_has_the_edit_shape() -> None:
    assert set(authoring.EDIT_OPS) <= set(authoring.operations())
    for name in authoring.EDIT_OPS:
        func = getattr(ops, name)
        assert inspect.isfunction(func) and func.__module__ == ops.__name__
        assert next(iter(inspect.signature(func).parameters)) == "scene"
        assert str(inspect.signature(func).return_annotation) in _EDIT_RETURNS
    assert {d["op"] for d in authoring.describe() if d["scope"] == "room"} == set(authoring.EDIT_OPS)
    assert not authoring.EDIT_OPS & authoring.NOT_EDITS


def test_a_new_scene_function_is_neither_silently_an_edit_nor_silently_read_only() -> None:
    """Fails when someone adds ``def foo(scene, ...) -> Doc`` to project_ops: register it in EDIT_OPS (it edits) or
    NOT_EDITS (it only reads) on purpose."""
    unclassified = []
    for name, func in vars(ops).items():
        if name.startswith("_") or not inspect.isfunction(func) or func.__module__ != ops.__name__:
            continue
        params = list(inspect.signature(func).parameters)
        if params and params[0] == "scene" and str(inspect.signature(func).return_annotation) in _EDIT_RETURNS:
            if name not in authoring.EDIT_OPS and name not in authoring.NOT_EDITS:
                unclassified.append(name)
    assert not unclassified, f"classify in engine/authoring.py (EDIT_OPS or NOT_EDITS): {unclassified}"
