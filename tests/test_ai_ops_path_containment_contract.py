from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.ai_ops import AIOps


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("op_type", "path_key", "extra"),
    [
        ("delete_entity", "scene_path", {"entity_id": "missing"}),
        ("add_world_scene", "world_path", {"scene_key": "intro", "path": "scenes/intro.json"}),
        ("add_cutscene", "cutscenes_path", {"id": "intro", "steps": []}),
    ],
)
def test_ai_ops_reject_relative_path_escape(
    tmp_path: Path,
    op_type: str,
    path_key: str,
    extra: dict[str, object],
) -> None:
    base_dir = tmp_path / "workspace"
    base_dir.mkdir()
    _write_json(tmp_path / "escape.json", {"entities": [], "scenes": {}, "links": []})

    job = {"operations": [{"type": op_type, path_key: "../escape.json", **extra}]}

    result = AIOps(base_dir).apply_job(job)

    assert result["ok"] is False
    assert result["results"][0]["ok"] is False
    assert "path escapes workspace: ../escape.json" in result["results"][0]["message"]


@pytest.mark.parametrize(
    ("op_type", "path_key", "extra"),
    [
        ("delete_entity", "scene_path", {"entity_id": "missing"}),
        ("add_world_scene", "world_path", {"scene_key": "intro", "path": "scenes/intro.json"}),
        ("add_cutscene", "cutscenes_path", {"id": "intro", "steps": []}),
    ],
)
def test_ai_ops_reject_absolute_path_outside_workspace(
    tmp_path: Path,
    op_type: str,
    path_key: str,
    extra: dict[str, object],
) -> None:
    base_dir = tmp_path / "workspace"
    base_dir.mkdir()
    outside = tmp_path / "absolute_escape.json"
    _write_json(outside, {"entities": [], "scenes": {}, "links": []})

    job = {"operations": [{"type": op_type, path_key: str(outside), **extra}]}

    result = AIOps(base_dir).apply_job(job)

    assert result["ok"] is False
    assert result["results"][0]["ok"] is False
    assert f"path escapes workspace: {outside}" in result["results"][0]["message"]


def test_ai_ops_allow_normal_relative_paths_inside_workspace(tmp_path: Path) -> None:
    base_dir = tmp_path / "workspace"
    ops = AIOps(base_dir)
    scene_path = base_dir / "scenes" / "inside.json"
    world_path = base_dir / "worlds" / "main_world.json"
    cutscene_path = base_dir / "cutscenes.json"
    _write_json(scene_path, {"entities": [], "lights": []})
    _write_json(world_path, {"scenes": {}, "links": []})

    scene_result = ops.add_light("scenes/inside.json", {"x": 1, "y": 2})
    world_result = ops.add_world_scene(
        "inside",
        "scenes/inside.json",
        world_path="worlds/main_world.json",
    )
    cutscene_result = ops.add_or_update_cutscene(
        "intro",
        [{"type": "wait", "duration": 1.0}],
        cutscenes_path="cutscenes.json",
    )

    assert scene_result.ok is True
    assert world_result.ok is True
    assert cutscene_result.ok is True
    assert json.loads(scene_path.read_text(encoding="utf-8"))["lights"][0]["x"] == 1.0
    assert json.loads(world_path.read_text(encoding="utf-8"))["scenes"]["inside"]["path"] == "scenes/inside.json"
    assert json.loads(cutscene_path.read_text(encoding="utf-8"))["cutscenes"][0]["id"] == "intro"
