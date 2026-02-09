from __future__ import annotations

from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_capture_focus_snapshot_built_only_via_query() -> None:
    root = Path("engine/input_runtime")
    forbidden = []
    for path in root.rglob("*.py"):
        text = _read(path)
        if "build_focus_snapshot" in text:
            forbidden.append(str(path))
    assert not forbidden, f"build_focus_snapshot found in: {forbidden}"


def test_capture_runtime_uses_query() -> None:
    text = _read(Path("engine/input_runtime/capture_runtime.py"))
    assert "get_capture_focus_snapshot" in text


def test_router_does_not_build_focus_snapshot() -> None:
    for path in (
        Path("engine/input_runtime/capture_key_router.py"),
        Path("engine/input_runtime/capture_mouse_router.py"),
    ):
        text = _read(path)
        assert "get_capture_focus_snapshot" not in text
        assert "build_focus_snapshot" not in text


def test_focus_model_line_count_ratchet() -> None:
    path = Path("engine/input_runtime/capture_runtime_focus_model.py")
    lines = [line for line in _read(path).splitlines() if line.strip()]
    baseline = 137
    assert len(lines) <= baseline, f"capture_runtime_focus_model.py grew to {len(lines)} lines"
