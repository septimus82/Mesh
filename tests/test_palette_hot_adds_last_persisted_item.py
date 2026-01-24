from __future__ import annotations

import json
from pathlib import Path

from engine.paths import get_content_roots, set_content_roots


def test_palette_hot_adds_last_persisted_item(monkeypatch, tmp_path: Path) -> None:
    from engine.palette_mode import get_state
    from engine.tooling_runtime.capture_persist import persist_capture_payload

    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        out_dir = tmp_path / "packs" / "p"
        monkeypatch.setenv("MESH_CAPTURE_OUT_DIR", str(out_dir))

        payload = {"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[7]]}
        result = persist_capture_payload("brush", payload)
        assert result.ok is True
        assert result.rel_path == "packs/p/brushes/capture_brush_1x1.json"

        state = get_state()
        state.reset()
        state.enabled = True
        state.mode = "STAMPS"
        state.stamps = []
        state.brushes = []

        item = state.hot_add_item(rel_path=result.rel_path)
        assert item is not None
        assert item.type == "brush"
        assert item.path == "packs/p/brushes/capture_brush_1x1.json"
        assert state.mode == "BRUSHES"
        assert state.selected_item is not None
        assert state.selected_item.path == item.path
        assert state.last_saved_display == "p/brushes/capture_brush_1x1.json"

        # No duplicates on repeat.
        state.hot_add_item(rel_path=result.rel_path)
        assert len([b for b in state.brushes if b.path == item.path]) == 1

        written = tmp_path / "packs" / "p" / "brushes" / "capture_brush_1x1.json"
        assert json.loads(written.read_text(encoding="utf-8"))["metadata"]["source"] == "capture_mode"
    finally:
        set_content_roots(original_roots)

