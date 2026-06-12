from __future__ import annotations

import importlib.abc
import sys
from pathlib import Path

import pytest

from tests._typing import as_any


class ArcadeBlocker(importlib.abc.MetaPathFinder):
    """Block any import starting with 'arcade' to simulate headless envs."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname == "arcade" or fullname.startswith("arcade."):
            raise ModuleNotFoundError(f"Arcade blocked for headless fast tests: {fullname}")
        return None


@pytest.mark.fast
def test_pytest_fast_headless_contract(tmp_path: Path) -> None:
    original_meta = sys.meta_path[:]
    original_modules = dict(sys.modules)
    blocker = ArcadeBlocker()

    for key in list(sys.modules):
        if key == "arcade" or key.startswith("arcade."):
            del sys.modules[key]

    sys.meta_path.insert(0, blocker)
    try:
        from engine.tooling import content_contract, validate_all
        from mesh_cli.main import create_parser

        create_parser()
        import mesh_cli.release_contract  # noqa: F401

        arcade_mod = sys.modules.get("arcade")
        if arcade_mod is not None:
            assert getattr(arcade_mod, "__mesh_headless_stub__", False)

            class _SpriteList(list):
                def __init__(self, *args: object, **kwargs: object) -> None:
                    raise AssertionError("SpriteList should not be instantiated in fast headless path")

            as_any(arcade_mod).SpriteList = _SpriteList

        scene_path = tmp_path / "headless_scene.json"
        scene_path.write_text('{"name":"Headless","entities":[]}', encoding="utf-8")

        rc = validate_all.main([scene_path.as_posix(), "--strict", "--schema-strict"])
        assert rc == 0

        assert content_contract is not None
        assert "arcade.gl" not in sys.modules
    finally:
        sys.meta_path[:] = original_meta
        sys.modules.clear()
        sys.modules.update(original_modules)
