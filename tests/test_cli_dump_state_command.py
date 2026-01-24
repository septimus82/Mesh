from __future__ import annotations

import json
from pathlib import Path

import mesh_cli
import mesh_cli.legacy_impl as mesh_cli_legacy


class _StubWindow:
    def __init__(self, *args, **kwargs):
        self._loaded = None

    def load_scene(self, scene_path: str):
        self._loaded = scene_path

    def close(self):
        return None


def test_cli_dump_state_prints_json_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: type("C", (), {
        "width": 1,
        "height": 1,
        "title": "t",
        "fullscreen": False,
        "vsync": False,
        "start_scene": "scenes/test.json",
    })())
    monkeypatch.setattr(mesh_cli_legacy, "GameWindow", _StubWindow)
    monkeypatch.setattr(mesh_cli.state_dump, "dump_state", lambda _w: {"b": 2, "a": 1})

    assert mesh_cli.main(["dump-state"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": 2}


def test_cli_dump_state_writes_file_when_out_provided(monkeypatch, tmp_path):
    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: type("C", (), {
        "width": 1,
        "height": 1,
        "title": "t",
        "fullscreen": False,
        "vsync": False,
        "start_scene": "scenes/test.json",
    })())
    monkeypatch.setattr(mesh_cli_legacy, "GameWindow", _StubWindow)
    monkeypatch.setattr(mesh_cli.state_dump, "dump_state", lambda _w: {"b": 2, "a": 1})

    out_path = tmp_path / "state.json"
    assert mesh_cli.main(["dump-state", "--out", str(out_path)]) == 0

    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert data == {"a": 1, "b": 2}

    # Enforced newline policy via persistence_io.
    assert Path(out_path).read_bytes().endswith(b"\n")
