"""The studies' animated review clips (tooling/review_media.py): off in a test run unless asked for, written when on."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling"))
import review_media  # noqa: E402

pytestmark = pytest.mark.integration

FRAMES = [Image.new("RGB", (8, 8), (40 * i, 0, 0)) for i in range(3)]


def test_a_test_run_has_review_clips_off_unless_asked_for() -> None:
    """tests/conftest.py sets MESH_REVIEW_MEDIA=0 unless the run set it already: off by default, on with the documented
    opt-in MESH_REVIEW_MEDIA=1."""
    setting = os.environ.get("MESH_REVIEW_MEDIA")
    assert setting is not None, "a test run always has a setting (tests/conftest.py's default is 0)"
    assert review_media.wanted() is (setting != "0"), setting


def test_off_writes_nothing_and_on_writes_the_animation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_REVIEW_MEDIA", "0")
    review_media.save_clip(FRAMES, tmp_path / "off.webp", duration=50)
    assert not (tmp_path / "off.webp").exists()
    monkeypatch.setenv("MESH_REVIEW_MEDIA", "1")
    review_media.save_clip(FRAMES, tmp_path / "on.webp", duration=50, quality=80)
    with Image.open(tmp_path / "on.webp") as clip:
        assert clip.format == "WEBP" and getattr(clip, "n_frames", 1) == 3
    review_media.save_clip([], tmp_path / "empty.webp")  # (no frames: nothing to write)
    assert not (tmp_path / "empty.webp").exists()
