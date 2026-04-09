from __future__ import annotations

from tests._typing import as_any


def test_capture_persist_validation_blocks_write(monkeypatch, tmp_path) -> None:
    from engine.tooling_runtime.capture_persist import persist_capture_payload

    monkeypatch.setenv("MESH_CAPTURE_OUT_DIR", str(tmp_path))
    payload = {"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": "nope"}
    r = persist_capture_payload("brush", as_any(payload))
    assert r.ok is False
    assert r.wrote is False
    assert (tmp_path / "brushes" / "capture_brush_1x1.json").exists() is False
