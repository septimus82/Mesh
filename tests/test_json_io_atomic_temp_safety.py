"""A-08: write_text_atomic uses an exclusive, unique temp file (never a creator's file, never a link)."""

from __future__ import annotations

import os
import stat

import pytest

from engine import json_io

pytestmark = [pytest.mark.integration]


def _temps(folder):
    return [p for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_existing_dot_tmp_user_file_survives(tmp_path) -> None:
    target = tmp_path / "scene.json"
    user = tmp_path / "scene.json.tmp"
    user.write_bytes(b"creator notes\r\n")
    json_io.write_text_atomic(target, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"
    assert user.read_bytes() == b"creator notes\r\n"
    assert _temps(tmp_path) == [user]


def test_symlink_at_dot_tmp_is_not_followed(tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"victim")
    folder = tmp_path / "proj"
    folder.mkdir()
    link = folder / "scene.json.tmp"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (Windows without privilege)")
    json_io.write_text_atomic(folder / "scene.json", "new\n")
    assert outside.read_bytes() == b"victim"
    assert link.is_symlink()
    assert (folder / "scene.json").read_text(encoding="utf-8") == "new\n"


def test_failed_replace_leaves_no_temp_and_original_intact(tmp_path, monkeypatch) -> None:
    target = tmp_path / "scene.json"
    target.write_bytes(b"original\n")

    def _boom(*_a, **_k):
        raise OSError("replace failed")

    monkeypatch.setattr(json_io.os, "replace", _boom)
    with pytest.raises(OSError, match="replace failed"):
        json_io.write_text_atomic(target, "new\n")
    assert target.read_bytes() == b"original\n"
    assert _temps(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits; the Linux lane runs this on Linux")
def test_mode_preserved_for_existing_and_umask_for_new(tmp_path) -> None:
    target = tmp_path / "scene.json"
    target.write_text("old\n")
    target.chmod(0o664)
    json_io.write_text_atomic(target, "new\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o664
    old_umask = os.umask(0o022)
    try:
        fresh = tmp_path / "fresh.json"
        json_io.write_text_atomic(fresh, "x\n")
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o644


def test_content_and_newlines_unchanged(tmp_path) -> None:
    target = tmp_path / "a.txt"
    json_io.write_text_atomic(target, "a\nb\n")
    assert target.read_bytes() == b"a\nb\n"
    json_io.write_json_atomic(tmp_path / "b.json", {"k": 1})
    assert (tmp_path / "b.json").read_bytes() == b'{\n  "k": 1\n}\n'
    assert _temps(tmp_path) == []
