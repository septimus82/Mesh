"""Golden contract for projects.json persistence."""

from __future__ import annotations

import json
from pathlib import Path

from engine.projects import add_recent_project, get_recent_projects


def _normalize_payload(payload: dict[str, object], tmp_path: Path) -> dict[str, object]:
    def _norm(value: object) -> object:
        if isinstance(value, str):
            text = value.replace("\\", "/")
            prefix = str(tmp_path).replace("\\", "/")
            if text.startswith(prefix):
                return text.replace(prefix, "<TMP>")
            return text
        if isinstance(value, list):
            return [_norm(item) for item in value]
        return value

    return {key: _norm(val) for key, val in payload.items()}


def test_projects_json_golden(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MESH_PROJECTS_PATH", str(tmp_path / "projects.json"))

    proj_a = tmp_path / "ProjA"
    proj_b = tmp_path / "ProjB"
    proj_a.mkdir()
    proj_b.mkdir()

    add_recent_project(str(proj_a))
    add_recent_project(str(proj_b))
    add_recent_project(str(proj_a))

    json_path = tmp_path / "projects.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    normalized = _normalize_payload(payload, tmp_path)

    expected = {
        "version": 1,
        "recent_roots": [
            "<TMP>/ProjA",
            "<TMP>/ProjB",
        ],
        "last_root": "<TMP>/ProjA",
    }
    assert normalized == expected
    assert get_recent_projects() == [str(proj_a.resolve()), str(proj_b.resolve())]
