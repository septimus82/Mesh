from __future__ import annotations

import importlib.abc
import sys

import pytest


class ArcadeGLBlocker(importlib.abc.MetaPathFinder):
    """Fail if arcade.gl is imported during fast tests."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname == "arcade.gl" or fullname.startswith("arcade.gl."):
            raise ModuleNotFoundError(f"arcade.gl blocked for fast tests: {fullname}")
        return None


@pytest.mark.fast
def test_no_arcade_gl_in_fast_mode() -> None:
    blocker = ArcadeGLBlocker()
    original_meta = sys.meta_path[:]
    for key in list(sys.modules):
        if key == "arcade.gl" or key.startswith("arcade.gl."):
            del sys.modules[key]
    sys.meta_path.insert(0, blocker)
    try:
        import engine.tooling.validate_all  # noqa: F401
        import engine.tooling.content_contract  # noqa: F401
    finally:
        sys.meta_path[:] = original_meta

    assert "arcade.gl" not in sys.modules
