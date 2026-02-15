import os
import sys
import importlib.abc
from unittest.mock import patch, MagicMock

import pytest

from engine.behaviours import load_builtin_behaviours


class _ArcadeBlocker(importlib.abc.MetaPathFinder):
    """Block arcade imports for headless-fast enforcement."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname == "arcade" or fullname.startswith("arcade."):
            raise ModuleNotFoundError(f"No module named '{fullname}'")
        return None


if os.getenv("MESH_TEST_BLOCK_ARCADE") == "1":
    for key in list(sys.modules):
        if key == "arcade" or key.startswith("arcade."):
            del sys.modules[key]
    sys.meta_path.insert(0, _ArcadeBlocker())

_FAST_TEST_NODEIDS = (
    "test_behaviour_loading_contract.py",
    "test_optional_arcade_is_centralized.py",
    "test_tooling_no_runtime_entrypoints.py",
    "test_tooling_test_tiers_cli.py",
    "test_no_arcade_static_imports_policy.py",
)
_INTEGRATION_NODEID_PARTS = (
    "perf_run",
    "replay_",
    "guard_patrol",
    "combat_tutorial",
    "micro_stealth",
    "world_links",
    "scene_loader",
)
_SLOW_NODEID_PARTS = (
    "help_regressions",
    "release_contract",
    "wheel_includes_pack_data",
)


@pytest.fixture
def builtin_behaviours_loaded():
    """Explicitly load builtin behaviours for tests that need the registry."""
    load_builtin_behaviours()


@pytest.fixture(autouse=True)
def _autoload_builtin_behaviours_marker(request):
    if request.node.get_closest_marker("builtin_behaviours"):
        load_builtin_behaviours()


@pytest.fixture(scope="session")
def unmarked_test_nodeids(pytestconfig):
    return list(getattr(pytestconfig, "_mesh_unmarked_nodeids", []))


def pytest_collection_modifyitems(config, items):
    unmarked: list[str] = []
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        if any(part in nodeid for part in _FAST_TEST_NODEIDS):
            item.add_marker(pytest.mark.fast)
        if any(part in nodeid for part in _INTEGRATION_NODEID_PARTS):
            item.add_marker(pytest.mark.integration)
        if any(part in nodeid for part in _SLOW_NODEID_PARTS):
            item.add_marker(pytest.mark.slow)
        has_explicit = any(
            marker.name in {"fast", "integration", "slow", "e2e"}
            for marker in item.iter_markers()
        )
        if not has_explicit:
            unmarked.append(nodeid)
    config._mesh_unmarked_nodeids = sorted(unmarked)


@pytest.fixture
def mock_arcade_lighting():
    """
    Fixture to mock out Arcade's lighting classes.
    This ensures we never try to instantiate real Light/LightLayer objects
    which require an active window/context.
    """
    with patch("engine.lighting._LightLayer") as mock_layer, \
         patch("engine.lighting._Light") as mock_light:
        yield {"layer": mock_layer, "light": mock_light}

@pytest.fixture
def mock_arcade_window(monkeypatch):
    """
    Patch arcade.get_window to return a mock.
    Useful for tests that trigger code paths calling arcade.get_window().
    """
    import engine.optional_arcade as oa

    # If arcade is missing, ensure we use the engine fallback for constants.
    if not oa.has_arcade():
        from engine import arcade_fallback
        monkeypatch.setattr(oa, "arcade", arcade_fallback)

    # Also patch BufferDescription to prevent ValueError: buffer parameter must be an arcade.gl.Buffer
    # if the real SpriteList somehow runs.
    if oa.arcade_gl:
         mock_buffer_desc = MagicMock()
         monkeypatch.setattr(oa.arcade_gl, "BufferDescription", mock_buffer_desc)

    with patch.object(oa.arcade, "get_window") as mock_get:

        yield mock_get

@pytest.fixture
def mock_arcade_background():
    """
    Patch arcade.set_background_color to no-op.
    Useful for tests that trigger code paths setting the background color.
    """
    with patch("arcade.set_background_color") as mock_bg:
        yield mock_bg
