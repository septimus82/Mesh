from __future__ import annotations

from pathlib import Path

from engine.tooling_runtime.discovery import discover_scene_paths, discover_world_paths


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_discover_scene_paths_sorted(tmp_path) -> None:
    _touch(tmp_path / "scenes" / "z.json")
    _touch(tmp_path / "scenes" / "a.json")
    _touch(tmp_path / "scenes" / "sub" / "m.json")
    _touch(tmp_path / "packs" / "b_pack" / "scenes" / "b.json")
    _touch(tmp_path / "packs" / "a_pack" / "scenes" / "c.json")
    _touch(tmp_path / "packs" / "a_pack" / "scenes" / "sub" / "aa.json")

    found = [p.relative_to(tmp_path).as_posix() for p in discover_scene_paths(tmp_path)]

    assert found == sorted(found)
    assert found == [
        "packs/a_pack/scenes/c.json",
        "packs/a_pack/scenes/sub/aa.json",
        "packs/b_pack/scenes/b.json",
        "scenes/a.json",
        "scenes/sub/m.json",
        "scenes/z.json",
    ]


def test_discover_world_paths_sorted(tmp_path) -> None:
    _touch(tmp_path / "worlds" / "zzz.json")
    _touch(tmp_path / "worlds" / "aaa.json")
    _touch(tmp_path / "worlds" / "mmm.json")

    found = [p.relative_to(tmp_path).as_posix() for p in discover_world_paths(tmp_path)]

    assert found == ["worlds/aaa.json", "worlds/mmm.json", "worlds/zzz.json"]

