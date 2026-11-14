"""A plan wires a scene into a world with '/' separators even when the plan was written on Windows with
backslashes: on Linux a backslash is part of a file name, so a world written with them doesn't load there."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.tooling.plan_executor import PlanExecutor

pytestmark = pytest.mark.fast


def test_wire_world_writes_portable_scene_paths(tmp_path: Path) -> None:
    world = tmp_path / "world.json"
    world.write_text(json.dumps({"scenes": {}}), encoding="utf-8")
    written: dict[Path, str] = {}
    executor = PlanExecutor(writer=lambda path, text: written.__setitem__(path, text))
    executor._wire_world({"world_path": str(world), "scene_id": "hub",
                          "scene_path": "packs\\core_regions\\scenes\\Ridge Outpost_hub.json"})
    saved = json.loads(written[world])
    assert saved["scenes"]["hub"]["path"] == "packs/core_regions/scenes/Ridge Outpost_hub.json"
