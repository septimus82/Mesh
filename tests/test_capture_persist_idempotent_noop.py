from __future__ import annotations

import json


def test_capture_persist_idempotent_noop(monkeypatch, tmp_path) -> None:
    from engine.tooling_runtime.capture_persist import persist_capture_payload

    monkeypatch.setenv("MESH_CAPTURE_OUT_DIR", str(tmp_path))

    payload = {"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}
    r1 = persist_capture_payload("brush", payload)
    assert r1.ok is True
    assert r1.wrote is True

    r2 = persist_capture_payload("brush", payload)
    assert r2.ok is True
    assert r2.wrote is False

    out_path = tmp_path / "brushes" / "capture_brush_1x1.json"
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["id"] == "capture_brush_1x1"
    assert loaded["metadata"]["source"] == "capture_mode"
