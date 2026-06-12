from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _nonempty_line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_scene_controller_facade_stays_thin() -> None:
    path = Path("engine/scene_controller.py")
    text = path.read_text(encoding="utf-8")
    assert _nonempty_line_count(path) <= 30
    assert 'sys.modules[__name__] = _impl' in text


def test_entity_ops_facade_stays_thin() -> None:
    path = Path("engine/scene_runtime/authoring/entity_ops.py")
    text = path.read_text(encoding="utf-8")
    assert _nonempty_line_count(path) <= 40
    assert 'sys.modules[__name__] = _impl' in text


def test_hotspot_modules_do_not_regrow_unchecked() -> None:
    budgets = {
        "engine/command_palette_registry.py": (474, 40, 540),
        "engine/editor_controller.py": (1142, 50, 1195),
        "mesh_cli/release.py": (1797, 50, 1845),
    }
    for relpath, (baseline, max_growth, budget) in budgets.items():
        path = Path(relpath)
        nonempty = _nonempty_line_count(path)
        assert nonempty <= budget, f"{relpath} exceeded budget: {nonempty} > {budget}"
        assert nonempty <= baseline + max_growth, (
            f"{relpath} regrew unexpectedly: {nonempty} > {baseline} + {max_growth}"
        )
