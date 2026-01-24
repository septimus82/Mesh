from __future__ import annotations

import json


def test_capture_persist_existing_diff_errors(monkeypatch, tmp_path) -> None:
    from engine.tooling_runtime.capture_persist import persist_capture_payload

    monkeypatch.setenv("MESH_CAPTURE_OUT_DIR", str(tmp_path))
    out_path = tmp_path / "brushes" / "capture_brush_1x1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[2]], "metadata": {"source": "capture_mode"}}),
        encoding="utf-8",
    )

    payload = {"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}
    r = persist_capture_payload("brush", payload)
    assert r.ok is False
    assert r.wrote is False
    assert "exists_different" in r.errors
    assert json.loads(out_path.read_text(encoding="utf-8"))["tiles"] == [[2]]
