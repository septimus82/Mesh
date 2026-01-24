from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine import editor_palette_thumbs


def test_thumb_cache_cap_trims_oldest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point cache trimming at tmp_path instead of the real repo.
    monkeypatch.setattr(editor_palette_thumbs, "get_repo_root", lambda *args, **kwargs: tmp_path)

    thumbs_dir = tmp_path / ".mesh" / "cache" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    # Create 6 dummy files with increasing mtimes (oldest -> newest).
    paths: list[Path] = []
    for i in range(6):
        p = thumbs_dir / f"t{i}.png"
        p.write_bytes(b"x")
        # Stagger mtimes using os.utime
        ts = 1000 + i
        os.utime(p, (ts, ts))
        paths.append(p)

    monkeypatch.setenv("MESH_EDITOR_THUMBS_MAX", "3")

    # Trigger trim logic without generating thumbs.
    processed = editor_palette_thumbs.tick_thumb_generation(max_per_frame=0)
    assert processed == 0

    remaining = sorted([p.name for p in thumbs_dir.iterdir() if p.is_file()])
    assert len(remaining) == 3

    # Newest 3 should remain (t3, t4, t5)
    assert set(remaining) == {"t3.png", "t4.png", "t5.png"}
