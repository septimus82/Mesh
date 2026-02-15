from __future__ import annotations

import json
from pathlib import Path

import mesh_cli

from engine.editor.debug_bundle import DebugBundle


class _StubWindow:
    def __init__(self, *args, **kwargs) -> None:
        self._loaded = None

    def load_scene(self, scene_path: str) -> None:
        self._loaded = scene_path

    def close(self) -> None:
        return None


def test_cli_debug_export_writes_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(mesh_cli.debug, "load_config", lambda: type("C", (), {
        "width": 1,
        "height": 1,
        "title": "t",
        "fullscreen": False,
        "vsync": False,
        "start_scene": "scenes/test.json",
    })())
    monkeypatch.setattr(mesh_cli.debug, "GameWindow", _StubWindow)

    bundle = DebugBundle(
        world={"current": "abc", "recent": []},
        lighting={"plan_digest": "", "cache_flags": {"layer_dirty": None, "shadows_dirty": None}},
        render=None,
        quests={"inspector_state": None, "diagnostics": []},
        cutscene={"inspector_state": None, "summary": {"is_running": False}, "commands": [], "recent_events": []},
        events={
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 0,
            "total_events": 0,
            "filtered_count": 0,
            "rows": [],
        },
        hud={"health": {"hp": 0.0, "max_hp": 0.0, "dead": True, "last_damage_time": None, "last_damage_amount": None}, "feed": []},
        selected_entity={"entity_id": None, "behaviours": []},
        created_at=None,
        engine_version="test",
    )

    def _stub_build_bundle(_window, _editor, *, deterministic=False):
        assert deterministic is True
        return bundle

    monkeypatch.setattr("engine.editor.debug_bundle.build_debug_bundle", _stub_build_bundle)

    out_path = tmp_path / "bundle.json"
    assert mesh_cli.main(["debug", "export", "--out", str(out_path), "--deterministic"]) == 0

    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert data["meta"]["deterministic"] is True
    assert data["world"]["current"] == "abc"
    assert "quests" in data

    assert Path(out_path).read_bytes().endswith(b"\n")
