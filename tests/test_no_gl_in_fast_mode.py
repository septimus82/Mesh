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
    # (taken out for the check and put back after it: a later test's real window needs the arcade.gl it was built
    # with, not a second copy whose classes don't match the first's)
    removed = {key: sys.modules.pop(key) for key in list(sys.modules)
               if key == "arcade.gl" or key.startswith("arcade.gl.")}
    sys.meta_path.insert(0, blocker)
    try:
        import engine.tooling.content_contract  # noqa: F401
        import engine.tooling.validate_all  # noqa: F401
        assert "arcade.gl" not in sys.modules
    finally:
        sys.meta_path[:] = original_meta
        sys.modules.update(removed)
