from __future__ import annotations

from pathlib import Path


def _dock_key(name: str) -> str:
    return f"{name}_dock_width"


def test_no_direct_left_right_dock_width_reads_in_engine() -> None:
    root = Path(__file__).resolve().parents[1]
    engine_root = root / "engine"
    left_key = _dock_key("left")
    right_key = _dock_key("right")
    violations: list[str] = []
    for path in engine_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if left_key in text or right_key in text:
            violations.append(str(path.relative_to(root)))
    assert not violations, f"Use editor_dock_query instead of raw dock widths: {violations}"


def test_no_direct_left_right_dock_width_reads_in_tests() -> None:
    root = Path(__file__).resolve().parents[1]
    tests_root = root / "tests"
    left_key = _dock_key("left")
    right_key = _dock_key("right")
    violations: list[str] = []
    allowlist = {
        str(Path(__file__).resolve().relative_to(root)),
    }
    for path in tests_root.rglob("*.py"):
        rel = str(path.relative_to(root))
        if rel in allowlist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if left_key in text or right_key in text:
            violations.append(rel)
    assert not violations, f"Use DockStub/editor_dock_query in tests instead of raw dock widths: {violations}"
