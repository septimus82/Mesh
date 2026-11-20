"""A-05: paint_tiles refuses out-of-map, negative, non-integer and oversized edits, whole batch, file untouched.

Reached through ``AIOps.apply_job`` (console ``ai_job``) and ``tools.apply_ops`` (MCP, non-Studio folder).
"""

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from engine.ai_ops import MAX_PAINT_TILE_COORD, MAX_PAINT_TILE_NEW_LAYERS, MAX_PAINT_TILE_OPS, AIOps
from engine.mcp_server import tools

pytestmark = pytest.mark.integration  # (F13-A: filesystem)


def _job(root: Path, ops: list[dict[str, Any]]) -> dict[str, Any]:
    return AIOps(root).apply_job({"operations": [{"type": "paint_tiles", "scene_path": "scene.json", "ops": ops}]})


def _mcp(root: Path, ops: list[dict[str, Any]]) -> dict[str, Any]:
    return tools.apply_ops([{"type": "paint_tiles", "scene_path": "scene.json", "ops": ops}],
                           root=str(root), validate=False)


PATHS = [pytest.param(_job, id="apply_job"), pytest.param(_mcp, id="mcp")]


def _scene(root: Path, dims: tuple[int, int] | None = (3, 2)) -> Path:
    tilemap: dict[str, Any] = {}
    if dims:
        (root / "map.json").write_text(json.dumps({"width": dims[0], "height": dims[1]}), encoding="utf-8")
        tilemap["path"] = "map.json"
    scene = root / "scene.json"
    scene.write_text(json.dumps({"tilemap": tilemap, "entities": []}), encoding="utf-8")
    return scene


def _p(col: Any = 0, row: Any = 0, gid: Any = 1) -> dict[str, Any]:
    return {"layer": "ground", "col": col, "row": row, "gid": gid}


BAD = [
    pytest.param([_p(col=-1)], "col=-1", id="negative-col"),
    pytest.param([_p(row=-1)], "row=-1", id="negative-row"),
    pytest.param([_p(col=3)], "col=3", id="col-equals-width"),
    pytest.param([_p(row=2)], "row=2", id="row-equals-height"),
    pytest.param([_p(row=10**9)], "row=1000000000", id="huge-row"),
    pytest.param([_p(col="x")], "col='x'", id="non-numeric"),
    pytest.param([_p(col=1.5)], "col=1.5", id="float"),
    pytest.param([_p(gid=-5)], "gid=-5", id="negative-gid"),
    pytest.param([_p(col=True)], "col=True", id="bool"),
    pytest.param([_p(col=1), _p(col=-1)], "op 1", id="valid-then-invalid"),
    pytest.param([_p()] * (MAX_PAINT_TILE_OPS + 1), "limit", id="too-many-ops"),
]


@pytest.mark.parametrize("run", PATHS)
@pytest.mark.parametrize("ops,needle", BAD)
def test_bad_batch_refused_file_untouched(tmp_path: Path, run: Callable[..., Any], ops: list[dict[str, Any]],
                                          needle: str) -> None:
    scene = _scene(tmp_path)
    before = scene.read_bytes()
    out = run(tmp_path, ops)
    assert out["ok"] is False
    assert needle in json.dumps(out)
    assert scene.read_bytes() == before


@pytest.mark.parametrize("run", PATHS)
def test_unknown_dimensions_are_capped(tmp_path: Path, run: Callable[..., Any]) -> None:
    scene = _scene(tmp_path, dims=None)
    before = scene.read_bytes()
    assert run(tmp_path, [_p(row=MAX_PAINT_TILE_COORD)])["ok"] is False
    assert run(tmp_path, [_p(col=MAX_PAINT_TILE_COORD)])["ok"] is False
    assert scene.read_bytes() == before


@pytest.mark.parametrize("run", PATHS)
def test_valid_batch_paints_exactly_the_cells(tmp_path: Path, run: Callable[..., Any]) -> None:
    scene = _scene(tmp_path)
    assert run(tmp_path, [_p(0, 0, 7), _p(2, 1, 9)])["ok"] is True
    data = json.loads(scene.read_text(encoding="utf-8"))["tilemap"]["overrides"]["layers"]["ground"]
    assert data == [7, 0, 0, 0, 0, 9]


def test_valid_batch_unknown_dimensions(tmp_path: Path) -> None:
    scene = _scene(tmp_path, dims=None)
    assert _job(tmp_path, [_p(1, 0, 4)])["ok"] is True
    data = json.loads(scene.read_text(encoding="utf-8"))["tilemap"]["overrides"]["layers"]["ground"]
    assert data == [0, 4]


def _on(layer: Any, col: int = 0) -> dict[str, Any]:
    return {"layer": layer, "col": col, "row": 0, "gid": 1}


@pytest.mark.parametrize("run", PATHS)
def test_many_new_layers_refused_without_allocating(tmp_path: Path, run: Callable[..., Any]) -> None:
    scene = _scene(tmp_path)
    before = scene.read_bytes()
    out = run(tmp_path, [_on(f"a{i}") for i in range(MAX_PAINT_TILE_NEW_LAYERS + 1)])
    assert out["ok"] is False and "new layers" in json.dumps(out)
    assert scene.read_bytes() == before


@pytest.mark.parametrize("run", PATHS)
@pytest.mark.parametrize("layer", [None, {"a": 1}, ["x"], 5, ""])
def test_non_string_layer_refused(tmp_path: Path, run: Callable[..., Any], layer: Any) -> None:
    scene = _scene(tmp_path)
    before = scene.read_bytes()
    out = run(tmp_path, [_on(layer)])
    assert out["ok"] is False and "layer=" in json.dumps(out)
    assert scene.read_bytes() == before


@pytest.mark.parametrize("run", PATHS)
def test_exactly_the_new_layer_limit_works_and_existing_layers_are_free(tmp_path: Path, run: Callable[..., Any]) -> None:
    scene = _scene(tmp_path)
    names = [f"a{i}" for i in range(MAX_PAINT_TILE_NEW_LAYERS)]
    assert run(tmp_path, [_on(n) for n in names])["ok"] is True
    # all layers now exist: painting them again (plus repeats of one new name) is unlimited
    assert run(tmp_path, [_on(n, 1) for n in names] * 3 + [_on("fresh")])["ok"] is True
    layers = json.loads(scene.read_text(encoding="utf-8"))["tilemap"]["overrides"]["layers"]
    assert set(layers) == {*names, "fresh"} and layers["a0"][:2] == [1, 1]
