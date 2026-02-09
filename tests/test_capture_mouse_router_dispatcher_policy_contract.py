from __future__ import annotations

from pathlib import Path


def test_capture_mouse_router_size_ratchet() -> None:
    path = Path("engine/input_runtime/capture_mouse_router.py")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) <= 150  # Increased for paint/select handler splits


def test_capture_mouse_router_has_no_handler_defs() -> None:
    source = Path("engine/input_runtime/capture_mouse_router.py").read_text(encoding="utf-8")
    assert "def _handle_" not in source


def test_capture_mouse_router_no_editor_actions_import() -> None:
    source = Path("engine/input_runtime/capture_mouse_router.py").read_text(encoding="utf-8")
    assert "editor_actions" not in source
