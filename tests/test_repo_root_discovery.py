import json
from pathlib import Path

import pytest

from engine.config import load_config
from engine.paths import get_content_roots, reset_path_caches, resolve_path


def _write_min_pyproject(repo_root: Path) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                "name = 'tmp-repo'",
                "version = '0.0.0'",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_load_config_defaults_to_discovered_repo_root_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_min_pyproject(repo_root)
    (repo_root / "config.json").write_text(json.dumps({"width": 1111}, sort_keys=True), encoding="utf-8")

    subdir = repo_root / "a" / "b"
    subdir.mkdir(parents=True)

    monkeypatch.chdir(subdir)
    cfg = load_config()

    assert cfg.width == 1111
    reset_path_caches()


@pytest.mark.parametrize(
    "config_payload",
    [
        # Missing content_roots entirely.
        {"title": "X"},
        # Present but empty.
        {"title": "X", "content_roots": []},
    ],
)
def test_content_roots_default_to_repo_root_when_missing_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_payload: dict
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_min_pyproject(repo_root)
    (repo_root / "config.json").write_text(json.dumps(config_payload, sort_keys=True), encoding="utf-8")

    subdir = repo_root / "deep" / "run"
    subdir.mkdir(parents=True)

    reset_path_caches()
    monkeypatch.chdir(subdir)
    roots = get_content_roots()

    assert len(roots) == 1
    assert roots[0].resolve() == repo_root.resolve()
    reset_path_caches()


def test_content_roots_explicit_relative_resolves_from_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_min_pyproject(repo_root)

    content_dir = repo_root / "content"
    content_dir.mkdir()
    (content_dir / "hello.txt").write_text("hi", encoding="utf-8")

    (repo_root / "config.json").write_text(
        json.dumps({"content_roots": ["content"]}, sort_keys=True),
        encoding="utf-8",
    )

    subdir = repo_root / "nested"
    subdir.mkdir()

    reset_path_caches()
    monkeypatch.chdir(subdir)

    resolved = resolve_path("hello.txt")
    assert resolved.resolve() == (content_dir / "hello.txt").resolve()
    assert resolved.read_text(encoding="utf-8") == "hi"
    reset_path_caches()
