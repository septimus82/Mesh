from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


MAX_SETTINGS_OVERLAY_LINES = 752


def test_settings_overlay_line_count_ratcheted() -> None:
    line_count = len(Path("engine/ui_overlays/settings_overlay.py").read_text(encoding="utf-8").splitlines())
    assert line_count <= MAX_SETTINGS_OVERLAY_LINES, (
        f"settings_overlay.py grew: {line_count} lines (max {MAX_SETTINGS_OVERLAY_LINES})"
    )
