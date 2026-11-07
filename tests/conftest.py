import fnmatch
import importlib.abc
import inspect
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Tests never use the sound card (Milestone 13): XAudio2 raised "Critical Error" (0x80070490, the audio device went
# away) asynchronously into whichever test was running, and test sounds could play on the owner's speakers.
# Set before pyglet.media is first imported. MESH_TEST_REAL_AUDIO=1 keeps the system's driver.
if os.getenv("MESH_TEST_REAL_AUDIO") != "1" and os.getenv("MESH_TEST_BLOCK_ARCADE") != "1":
    try:
        import pyglet

        pyglet.options["audio"] = ("silent",)
    except ImportError:
        pass

from engine.behaviours import load_builtin_behaviours  # noqa: E402

# The studies' animated WebP clips are for a person to look at and nothing asserts on them; encoding them was a large
# part of the GPU lane (#422). Their frames are still drawn. MESH_REVIEW_MEDIA=1 writes them (tooling/review_media.py).
os.environ.setdefault("MESH_REVIEW_MEDIA", "0")


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
    "wheel_bundles_engine_data",
)


@pytest.fixture
def builtin_behaviours_loaded():
    """Explicitly load builtin behaviours for tests that need the registry."""
    load_builtin_behaviours()


@pytest.fixture(autouse=True)
def _autoload_builtin_behaviours_marker(request):
    if request.node.get_closest_marker("builtin_behaviours"):
        load_builtin_behaviours()


@pytest.fixture(autouse=True)
def _reset_engine_path_caches_after_test():
    yield
    try:
        from engine.paths import reset_path_caches

        reset_path_caches()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _undo_launched_project_root_pin():
    # game_launch / GameWindow / main menu pin the launch root and write
    # os.environ["MESH_REPO_ROOT"] directly; without this, later tests resolve
    # config.json from a dead tmp project.
    before = os.environ.get("MESH_REPO_ROOT")
    yield
    from engine.repo_root import clear_launched_project_root

    clear_launched_project_root()
    if before is not None:
        os.environ["MESH_REPO_ROOT"] = before


@pytest.fixture(scope="session", autouse=True)
def _no_ambient_step_budget_enforcement():
    # CI's verify-all step sets MESH_VERIFY_BUDGET_ENFORCE=1 and the fast tier it runs inherits it. Since #422 F13 an
    # enforced verify-all fails without budgets or with a budgeted step that didn't run, which every seeded test repo
    # is; tests that judge the budgets set the variable themselves.
    saved = os.environ.pop("MESH_VERIFY_BUDGET_ENFORCE", None)
    yield
    if saved is not None:
        os.environ["MESH_VERIFY_BUDGET_ENFORCE"] = saved


@pytest.fixture(scope="session", autouse=True)
def _private_recent_projects(tmp_path_factory):
    # The recent-projects list lives in the user's profile; tests must never touch the real one.
    import os

    user = tmp_path_factory.mktemp("mesh_user")
    added = {key: value for key, value in (("MESH_PROJECTS_PATH", str(user / "projects.json")),
                                           ("MESH_USER_DIR", str(user)),
                                           ("MESH_PROJECTS_DIR", str(user / "Mesh Projects")),
                                           # the game's settings (volume, fog, flicker...) save to the repo's
                                           # tracked user_settings.json otherwise
                                           ("MESH_RUNTIME_SETTINGS_PATH", str(user / "user_settings.json")))
             if not os.environ.get(key)}
    os.environ.update(added)
    yield
    for key in added:
        os.environ.pop(key, None)


@pytest.fixture(scope="session", autouse=True)
def _repo_projects_json_untouched():
    # Tests have leaked last_root into the tracked projects.json three times, and settings into the tracked
    # user_settings.json; fail loudly instead of shipping either.
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    paths = [root / "projects.json", root / "user_settings.json"]
    before = [path.read_bytes() if path.exists() else None for path in paths]
    yield
    for path, was in zip(paths, before):
        if (path.read_bytes() if path.exists() else None) != was:
            pytest.fail(f"test session modified {path}; write to tmp_path instead", pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def _windows_never_shown():
    # Tests that need a real GL window (a GameWindow, the shadow bench) get a hidden one: a test run never puts a
    # window on the owner's desktop or takes focus from what they are doing (Milestone 13). A shown window
    # also failed one test intermittently, when the owner's own clicks reached it. MESH_TEST_SHOW_WINDOWS=1
    # shows them, for debugging.
    if os.getenv("MESH_TEST_SHOW_WINDOWS") == "1" or os.getenv("MESH_TEST_BLOCK_ARCADE") == "1":
        yield
        return
    try:
        import pyglet.window
    except ImportError:  # no arcade/pyglet: nothing opens windows
        yield
        return
    original = pyglet.window.Window.__init__

    def hidden(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        kwargs["visible"] = False
        original(self, *args, **kwargs)

    pyglet.window.Window.__init__ = hidden
    yield
    pyglet.window.Window.__init__ = original


@pytest.fixture(scope="session")
def unmarked_test_nodeids(pytestconfig):
    return list(getattr(pytestconfig, "_mesh_unmarked_nodeids", []))


@pytest.fixture(scope="session")
def fast_tests_outside_rule(pytestconfig):
    return list(getattr(pytestconfig, "_mesh_fast_tests_outside_rule", []))


@pytest.fixture(scope="session")
def gl_opt_in_unmarked(pytestconfig):
    return list(getattr(pytestconfig, "_mesh_gl_opt_in_unmarked", []))


@pytest.fixture(scope="session")
def never_runs_nodeids(pytestconfig):
    return list(getattr(pytestconfig, "_mesh_never_runs", []))


@pytest.fixture(scope="session")
def exception_policy_scan():
    """One exception-policy scan of the repository, shared by the tests that only read it (a scan takes seconds)."""
    from pathlib import Path

    from tooling.scan_exception_policies import scan

    return scan(["engine", "mesh_cli", "tooling"], repo_root=Path(__file__).resolve().parent.parent)


def _may_hold_fast_tests(path, seen: dict) -> bool:
    """Whether a test module can contain fast tests: it says "fast" somewhere (any case: marks, aliases, base classes),
    or it is one of the modules marked fast below. The full run checks this for every test (see the hook below)."""
    if path not in seen:
        rel = path.as_posix()
        seen[path] = any(part in rel for part in _FAST_TEST_NODEIDS) or b"fast" in path.read_bytes().lower()
    return seen[path]


def pytest_ignore_collect(collection_path, config):
    # The fast tier (``-m fast``, as tooling/pytest_fast.py and verify-all run it) imported all ~1,800 test modules to
    # deselect over half of their tests (#422 F13): modules that can't hold a fast test aren't collected for it. Only
    # for exactly ``-m fast``; every other run collects everything.
    if config.getoption("markexpr") != "fast" or collection_path.suffix != ".py":
        return None
    if not any(fnmatch.fnmatch(collection_path.name, pattern) for pattern in config.getini("python_files")):
        return None
    if _may_hold_fast_tests(collection_path, config.__dict__.setdefault("_mesh_fast_rule", {})):
        return None
    return True


def pytest_collection_modifyitems(config, items):
    unmarked: list[str] = []
    fast_rule = config.__dict__.setdefault("_mesh_fast_rule", {})
    outside_rule: set[str] = set()
    gl_unmarked: set[str] = set()
    never_runs: set[str] = set()
    sources: dict = {}
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        if any(part in nodeid for part in _FAST_TEST_NODEIDS):
            item.add_marker(pytest.mark.fast)
        if item.get_closest_marker("fast") is not None and not _may_hold_fast_tests(item.path, fast_rule):
            outside_rule.add(nodeid)
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
        if _requires_gl(item):
            item.add_marker(pytest.mark.gl)
        elif _GL_OPT_IN in _test_source(item, sources) and item.path.name not in _GL_MENTION_EXEMPT:
            gl_unmarked.add(nodeid)
        if _never_runs(item):
            never_runs.add(nodeid)
    config._mesh_unmarked_nodeids = sorted(unmarked)
    config._mesh_fast_tests_outside_rule = sorted(outside_rule)
    config._mesh_gl_opt_in_unmarked = sorted(gl_unmarked)
    config._mesh_never_runs = sorted(never_runs)


# Test lanes (H6, #422): tooling/test_tiers.py runs each test somewhere. A test needs a real GL context when it opts
# in the one way the suite does, a skipif naming MESH_GL_SMOKE, whatever its file is called (a test_*_gpu.py glob
# missed tests/test_background_layers_render_contract.py); it gets the `gl` marker and runs in the gpu lane.
_GL_OPT_IN = "MESH_GL_SMOKE"
_GL_MENTION_EXEMPT = ("test_tooling_test_tiers_cli.py", "test_test_lanes_contract.py")  # name the variable, need no GL
# Skips a lane satisfies: the gpu lane sets MESH_GL_SMOKE=1; CI sets CI=true for the packaging-hygiene checks; a
# platform-only test names the lane that runs it ("... lane runs this on Windows").
_LANE_SATISFIED_SKIPS = (_GL_OPT_IN, "run with CI=true", "lane runs this on ")


def _requires_gl(item) -> bool:
    return any(_GL_OPT_IN in str(mark.kwargs.get("reason", "")) for mark in item.iter_markers("skipif"))


def _test_source(item, sources: dict) -> str:
    """The test function's own source: a GL gate inside it (say a pytest.skip naming MESH_GL_SMOKE) is one the
    capability rule can't see. Module-wide gates (pytestmark) reach the rule as skipif marks already."""
    function = getattr(item, "function", None)
    if function is None:
        return ""
    if function not in sources:
        try:
            sources[function] = inspect.getsource(function)
        except (OSError, TypeError):
            sources[function] = ""
    return sources[function]


def _never_runs(item) -> bool:
    """Skipped unconditionally, or for a reason no lane satisfies: such a test runs nowhere (it must be listed)."""
    if any(True for _ in item.iter_markers("skip")):
        return True
    for mark in item.iter_markers("skipif"):
        condition = mark.args[0] if mark.args else mark.kwargs.get("condition")
        reason = str(mark.kwargs.get("reason", ""))
        if condition is True and not any(part in reason for part in _LANE_SATISFIED_SKIPS):
            return True
    return False


@pytest.fixture(autouse=True)
def _physical_gpu_only(request):
    # tooling/test_tiers.py sets MESH_GL_SOFTWARE=1 when the gpu lane's renderer is a software one (CI's Mesa):
    # a test that needs a physical GPU says so in the lane's skip list instead of failing or passing there.
    if os.getenv("MESH_GL_SOFTWARE") == "1" and request.node.get_closest_marker("gpu_hardware") is not None:
        pytest.skip("needs a physical GPU: this lane's GL is a software renderer")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # In the gpu lane (MESH_REQUIRE_GL=1) a GL test skipped by its opt-in gate (no MESH_GL_SMOKE, or no arcade) is a
    # failure, not a quiet pass. Other skips (a renderer without some feature) stay skips, listed by the lane.
    outcome = yield
    report = outcome.get_result()
    if os.getenv("MESH_REQUIRE_GL") == "1" and report.skipped and item.get_closest_marker("gl") is not None:
        reason = str(report.longrepr[-1]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
        if _GL_OPT_IN in reason:
            report.outcome = "failed"
            report.longrepr = f"GL test skipped by its opt-in gate in the gpu lane (no GL, or no arcade): {reason}"


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

@pytest.fixture(autouse=True)
def _clear_battle_clip_sheet_texture_cache() -> None:
    from engine.monster.battle_sprite_view import clear_clip_sheet_texture_cache

    clear_clip_sheet_texture_cache()
    yield
    clear_clip_sheet_texture_cache()


@pytest.fixture
def mock_arcade_background():
    """
    Patch arcade.set_background_color to no-op.
    Useful for tests that trigger code paths setting the background color.
    """
    with patch("arcade.set_background_color") as mock_bg:
        yield mock_bg
