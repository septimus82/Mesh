from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest

pytestmark = [pytest.mark.fast]


def test_template_game_main_parses_and_calls_run_game(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import examples.template_game.main as template_main

    called: dict[str, object] = {}

    def _fake_run_game(scene: Path, *, project_root: Path | None = None) -> None:
        called["scene"] = scene
        called["project_root"] = project_root

    monkeypatch.setattr(template_main, "run_game", _fake_run_game)

    rc = template_main.main(
        [
            "--project-root",
            str(tmp_path),
            "--scene",
            "scenes/cellar.json",
        ]
    )
    assert rc == 0
    assert called["scene"] == Path("scenes/cellar.json")
    assert called["project_root"] == tmp_path.resolve()


def test_resolve_asset_path_uses_project_root(tmp_path: Path) -> None:
    from engine.public_api.assets import resolve_asset_path

    resolved = resolve_asset_path("scenes/cellar.json", project_root=tmp_path)
    assert resolved == (tmp_path / "scenes" / "cellar.json").resolve()


def test_run_game_does_not_call_os_chdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from engine.public_api.runtime import run_game

    fake_config = ModuleType("engine.config")
    fake_config.load_config = lambda _path=None: SimpleNamespace(
        width=1,
        height=1,
        title="x",
        fullscreen=False,
        vsync=False,
    )

    captured: dict[str, object] = {}

    class _FakeWindow:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def load_scene(self, scene_path: str) -> None:
            captured["scene"] = scene_path

        def run(self) -> None:
            captured["ran"] = True

    fake_game = ModuleType("engine.game")
    fake_game.GameWindow = _FakeWindow

    monkeypatch.setitem(sys.modules, "engine.config", fake_config)
    monkeypatch.setitem(sys.modules, "engine.game", fake_game)

    def _fail_chdir(_path: str) -> None:
        raise AssertionError("run_game must not call os.chdir")

    monkeypatch.setattr("os.chdir", _fail_chdir)

    run_game(Path("scenes/cellar.json"), project_root=tmp_path)
    init_kwargs = captured["init"]
    assert isinstance(init_kwargs, dict)
    assert str((tmp_path / "config.json").resolve()) == init_kwargs["config_path"]
    assert captured["scene"] == "scenes/cellar.json"
    assert captured["ran"] is True

