"""SL-4: ``set_entity_fields`` is usable through the authoring API as ``{"op": ..., "fields": {...}}``.

Before: ``fields`` (the op's ``**fields``) was passed on as one field called "fields" and the scene schema refused it;
the keyword form was refused as an unknown setting. Reached through ``authoring.apply`` and the MCP ``apply_changes``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (files on disk, the real paths)
SCENE = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    scene = path / SCENE
    doc = json.loads(scene.read_text(encoding="utf-8"))
    doc.setdefault("entities", []).append({"id": "Warden", "name": "Warden", "x": 10, "y": 10})
    scene.write_bytes(json.dumps(doc, indent=2).encode("utf-8"))
    return path


def _warden(root: Path) -> dict:
    doc = json.loads((root / SCENE).read_text(encoding="utf-8"))
    return next(e for e in doc["entities"] if e["id"] == "Warden")


def _files(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".mesh" not in p.parts}


def _change(fields: dict) -> dict:
    return {"op": "set_entity_fields", "entity_id": "Warden", "fields": fields}


def test_authoring_apply_sets_tags_and_scale(root: Path) -> None:
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    authoring.apply(project, [_change({"scale": 1.2, "tags": ["enemy"]})])
    project.save()
    assert (_warden(root)["scale"], _warden(root)["tags"]) == (1.2, ["enemy"])


def test_mcp_apply_changes_sets_tags_and_scale(root: Path) -> None:
    result = tools.apply_changes([_change({"scale": 1.2, "tags": ["enemy"]})], root=str(root))
    assert result["ok"], result
    assert (_warden(root)["scale"], _warden(root)["tags"]) == (1.2, ["enemy"])


@pytest.mark.parametrize("change", [
    _change({"id": "Other"}), _change({"behaviours": []}), _change({"bogus_field": 1}), _change({"scale": "big"}),
    _change({"entity_id": "x"}), {"op": "set_entity_fields", "entity_id": "Warden", "fields": 5},
])
def test_mcp_refuses_a_bad_field_and_leaves_files_untouched(root: Path, change: dict) -> None:
    before = _files(root)
    result = tools.apply_changes([change], root=str(root))
    assert not result["ok"], result
    assert _files(root) == before


def test_describe_shows_fields_as_an_object() -> None:
    entry = next(o for o in authoring.describe() if o["op"] == "set_entity_fields")
    assert {p["name"]: p["type"] for p in entry["params"]}["fields"] == "object"
