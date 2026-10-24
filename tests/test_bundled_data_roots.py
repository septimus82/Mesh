"""The engine finds its own bundled files in the source tree first (a checkout, or an editable install), then in a
pip install's <prefix>/share/mesh-engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import repo_root

pytestmark = pytest.mark.fast


def test_a_checkout_finds_bundled_files_in_its_own_tree_first() -> None:
    roots = repo_root.bundled_data_roots()
    assert roots[0] == repo_root.engine_source_root()
    assert all(r.parts[-2:] == repo_root.BUNDLED_SHARE for r in roots[1:]), roots
    assert repo_root.bundled_file("config.json") == repo_root.engine_source_root() / "config.json"
    assert repo_root.bundled_file("assets/no/such/file.json") is None


def test_an_install_finds_them_under_share_mesh_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    share = tmp_path.joinpath(*repo_root.BUNDLED_SHARE, "assets", "data")
    share.mkdir(parents=True)
    (share / "monster_moves.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(repo_root, "engine_source_root", lambda: tmp_path / "site-packages")  # no data beside it
    monkeypatch.setattr(repo_root.sysconfig, "get_path", lambda name, scheme=None: str(tmp_path))
    assert repo_root.bundled_file("assets/data/monster_moves.json") == share / "monster_moves.json"
