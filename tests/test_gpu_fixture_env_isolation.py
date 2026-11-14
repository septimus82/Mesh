"""The dialogue and lighting GPU fixtures leave the process environment as they found it (repository health audit).

``tests/test_dialogue_reopen_gpu.py::report`` set ``MESH_RUNTIME_SETTINGS_PATH`` and ``MESH_STUDIO_NO_AI_BRIDGE`` and
never restored them, so every later module in the same pytest process (a GPU shard) inherited a settings file in a
finished test's temporary folder and a disabled AI bridge. ``tests/test_hd2d_lighting_controls_gpu.py::run`` set the
bridge flag at its start and popped it only in a ``finally`` near its end: a value the caller had set was deleted, and
a failure before that ``try`` (making the project, say) left the flag set.

These tests run the real fixture functions (their ``__wrapped__`` bodies), with only the heavy work they drive (the
Studio session, the project scaffold) replaced by a stand-in that records the environment it sees and returns or
raises. Each variable starts absent, set to a value, or set to an empty string (which is not the same as absent).

The sweep (#506 phase 1, then phase 2): 36 more GPU modules wrote one or both variables. Thirteen never put them
back; twenty-three deleted them on the way out, whatever the caller had set. Module fixtures now patch inside
``pytest.MonkeyPatch.context()`` around the work they feed (or around their ``yield``); test functions and function
fixtures set them through ``monkeypatch``. Each is run here as itself, its heavy work replaced. The policy tests at the
end keep every test module off raw writes of these two variables, with no exceptions."""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import tests.test_dialogue_reopen_gpu as dialogue_gpu
import tests.test_hd2d_lighting_controls_gpu as lighting_gpu

pytestmark = pytest.mark.fast

SETTINGS, BRIDGE = "MESH_RUNTIME_SETTINGS_PATH", "MESH_STUDIO_NO_AI_BRIDGE"
STARTS = {"absent": None, "set": "C:/somewhere/else/user_settings.json", "empty": ""}
BRIDGE_STARTS = {"absent": None, "set": "0", "empty": ""}


def _start(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    # (set first, so this test's monkeypatch has recorded the suite's own value and puts it back afterwards even when
    # the variable starts absent and the code under test leaks a write)
    monkeypatch.setenv(name, "")
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)


def _now(name: str) -> str | None:
    return os.environ.get(name)


class _Seen(Exception):
    """What the stand-in raises after recording the environment (a failure inside the fixture)."""


@pytest.mark.parametrize("bridge", BRIDGE_STARTS, ids=[f"bridge-{k}" for k in BRIDGE_STARTS])
@pytest.mark.parametrize("settings", STARTS, ids=[f"settings-{k}" for k in STARTS])
def test_the_dialogue_fixture_restores_both_variables_after_its_run(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, settings: str, bridge: str) -> None:
    import watchfire_r4_dialogue as r4

    _start(monkeypatch, SETTINGS, STARTS[settings])
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[bridge])
    seen: dict[str, Any] = {}

    def run(out: Path) -> dict:
        seen.update(settings=_now(SETTINGS), bridge=_now(BRIDGE), out=out)
        return {"ran": True}

    monkeypatch.setattr(r4, "run", run)
    assert dialogue_gpu.report.__wrapped__(tmp_path_factory) == {"ran": True}
    assert seen["settings"] == str(seen["out"] / "user_settings.json") and seen["bridge"] == "1", "set while it runs"
    assert (_now(SETTINGS), _now(BRIDGE)) == (STARTS[settings], BRIDGE_STARTS[bridge]), "as found, after it"


@pytest.mark.parametrize("start", ["absent", "set", "empty"])
def test_the_dialogue_fixture_restores_both_variables_when_its_run_raises(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, start: str) -> None:
    import watchfire_r4_dialogue as r4

    _start(monkeypatch, SETTINGS, STARTS[start])
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])

    def run(out: Path) -> dict:
        assert _now(BRIDGE) == "1"
        raise _Seen

    monkeypatch.setattr(r4, "run", run)
    with pytest.raises(_Seen):
        dialogue_gpu.report.__wrapped__(tmp_path_factory)
    assert (_now(SETTINGS), _now(BRIDGE)) == (STARTS[start], BRIDGE_STARTS[start])


@pytest.mark.parametrize("start", BRIDGE_STARTS)
def test_the_lighting_fixture_restores_the_bridge_flag_when_its_setup_fails(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, start: str) -> None:
    """Its setup making the project fails after the flag was set: the flag is put back as it was, not left set and
    not deleted."""
    import engine.project_scaffold as scaffold

    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])
    seen: list[str | None] = []

    def create_project(*args: Any, **kwargs: Any) -> None:
        seen.append(_now(BRIDGE))
        raise _Seen

    monkeypatch.setattr(scaffold, "create_project", create_project)
    with pytest.raises(_Seen):
        lighting_gpu.run.__wrapped__(tmp_path_factory)
    assert seen == ["1"], "set while it runs"
    assert _now(BRIDGE) == BRIDGE_STARTS[start], "as found, after it"


def test_the_lighting_fixture_never_deletes_the_callers_flag_on_its_way_out() -> None:
    """Its teardown no longer pops the flag unconditionally: the restoring is the scoped patch's, whatever happened
    (the success path drives a real Studio window: tests/test_hd2d_lighting_controls_gpu.py, run in the gpu lane)."""
    import inspect

    assert f'os.environ.pop("{BRIDGE}"' not in inspect.getsource(lighting_gpu)
    assert "MonkeyPatch.context()" in inspect.getsource(lighting_gpu.run.__wrapped__)


# --- The sweep (#506, phase 2): the 36 GPU modules that wrote these variables and did not put them back ---

ASSIGN = "assign"  # set for the run
IF_ABSENT = "if absent"  # set only when absent (the old setdefault), otherwise left as it is
BOTH = {SETTINGS: ASSIGN, BRIDGE: ASSIGN}


@dataclass(frozen=True)
class Fixture:
    """One module fixture, the heavy work it drives (module, name; ``PHASES[x]`` for an entry of that table), which
    variables it writes and how, and whether a stand-in for that work may return (``False``: the fixture would go on
    to open a real Studio window, so the stand-in only ever fails)."""
    module: str
    fixture: str
    heavy: tuple[tuple[str, str], ...]
    writes: dict[str, str]
    returns: bool = True


FIXTURES = {
    # Phase 1: never put back.
    "test_ai_playtest_gpu": Fixture("test_ai_playtest_gpu", "run", (("d2_ai_playtest_scenario", "run"),), {SETTINGS: IF_ABSENT}),
    "test_hd2d_asset_pipeline_gpu": Fixture("test_hd2d_asset_pipeline_gpu", "run",
                                            (("hd2d_asset_pipeline_demo", "check"),), {BRIDGE: ASSIGN}),
    "test_hd2d_emissive_gpu": Fixture("test_hd2d_emissive_gpu", "run", (("hd2d_emissive_demo", "check"),), {BRIDGE: ASSIGN}),
    "test_hd2d_lamp_glow_gpu": Fixture("test_hd2d_lamp_glow_gpu", "run", (("hd2d_lamp_glow_demo", "check"),), {BRIDGE: ASSIGN}),
    "test_hd2d_starter_gpu": Fixture("test_hd2d_starter_gpu", "run", (("hd2d_starter_demo", "check"),), {BRIDGE: ASSIGN}),
    "test_interaction_debugger_gpu": Fixture("test_interaction_debugger_gpu", "run",
                                             (("d3a_interaction_scenario", "run"),), {SETTINGS: IF_ABSENT}),
    "test_new_game_isolation_gpu": Fixture("test_new_game_isolation_gpu", "sessions",
                                           (("watchfire_r1_sessions", "flag_sessions"),), {SETTINGS: IF_ABSENT}),
    "test_runtime_debugger_gpu": Fixture("test_runtime_debugger_gpu", "run", (("d1_debug_scenario", "run"),), {SETTINGS: IF_ABSENT}),
    "test_studio_3d_selection_gpu": Fixture("test_studio_3d_selection_gpu", "report",
                                            (("watchfire_r3_selection", "run"),), BOTH),
    # Phase 2: set, then deleted on the way out whatever was there before.
    "test_dof_studio_gpu": Fixture("test_dof_studio_gpu", "run", (("dof_studio", "studio"),), BOTH),
    "test_hd2d_bloom_gpu": Fixture("test_hd2d_bloom_gpu", "studio", (("hd2d_bloom_studio", "studio"),), BOTH),
    "test_hd2d_composite_gpu": Fixture("test_hd2d_composite_gpu", "report", (("hd2d_composite_study", "study"),), BOTH),
    "test_hd2d_haze_gpu": Fixture("test_hd2d_haze_gpu", "studio", (("hd2d_haze_studio", "studio"),), BOTH),
    "test_hd2d_post_gpu": Fixture("test_hd2d_post_gpu", "studio", (("hd2d_post_studio", "studio"),), BOTH),
    "test_hd2d_room_expand_gpu": Fixture("test_hd2d_room_expand_gpu", "run", (("hd2d_room_expand_studio", "studio"),), BOTH),
    "test_hd2d_room_studio_gpu": Fixture("test_hd2d_room_studio_gpu", "run", (("hd2d_room_studio", "studio"),), BOTH),
    "test_river_falls_gpu": Fixture("test_river_falls_gpu", "studio", (("w1_waterfall_checks", "studio"),), BOTH),
    "test_scatter_diagnostics_gpu": Fixture("test_scatter_diagnostics_gpu", "run",
                                            (("scatter_diagnostics_studio", "studio"),), BOTH),
    "test_settings_ui_gpu": Fixture("test_settings_ui_gpu", "run", (("settings_ui_check", "check"),), {SETTINGS: ASSIGN}),
    "test_soundscape_studio_gpu": Fixture("test_soundscape_studio_gpu", "run",
                                          (("soundscape_studio", "setup2d"), ("soundscape_studio", "studio2d")), BOTH),
    "test_start_room_music_gpu": Fixture("test_start_room_music_gpu", "run", tuple(
        ("m23d_start_music_studio", f"PHASES[{phase}]") for phase in ("creator", "game", "saves")), BOTH),
    "test_studio_workflow_polish_gpu:ctrl_s": Fixture("test_studio_workflow_polish_gpu", "ctrl_s",
                                                      (("studio_workflow_polish", "ctrl_s"),), BOTH),
    "test_studio_workflow_polish_gpu:left": Fixture("test_studio_workflow_polish_gpu", "left",
                                                    (("studio_workflow_polish", "left"),), BOTH),
    "test_studio_workflow_polish_gpu:navigation": Fixture("test_studio_workflow_polish_gpu", "navigation",
                                                          (("studio_workflow_polish", "navigation"),), BOTH),
    "test_studio_workspace_gpu:run": Fixture("test_studio_workspace_gpu", "run", (("studio_workspace", "creator"),), BOTH),
    "test_studio_workspace_gpu:safety": Fixture("test_studio_workspace_gpu", "safety",
                                                (("studio_workspace", "safety"),), BOTH),
    "test_weather_authoring_gpu": Fixture("test_weather_authoring_gpu", "creator",
                                          (("m23c_weather_studio", "PHASES[creator]"),), BOTH),
    # These two build their own Studio session: the stand-in fails where it would start (the lighting fixture's case).
    "test_hd2d_shadow_allocation_gpu": Fixture("test_hd2d_shadow_allocation_gpu", "run",
                                               (("engine.project_scaffold", "create_project"),), {BRIDGE: ASSIGN}, returns=False),
    "test_state_lifecycle_gpu": Fixture("test_state_lifecycle_gpu", "cycles", (("hd2d_studio_demo", "StudioDriver"),),
                                        {SETTINGS: IF_ABSENT, BRIDGE: ASSIGN}, returns=False),
}

# Test functions that set the variables themselves: (module, test, the heavy work's module and name, what it writes).
STUDIO_TESTS = [
    ("test_river_bed_gpu", "test_studio_carves_a_stream_s_bed_so_its_water_shows_undo_and_clear_its_plants",
     "r3_river_bed_study", "make_project", {BRIDGE: ASSIGN}),
    ("test_river_mouth_gpu", "test_studio_draws_one_water_surface_where_the_stream_enters_the_pond",
     "r4_river_mouth_study", "make_project", {BRIDGE: ASSIGN}),
    ("test_river_mouth_gpu", "test_no_seam_where_the_shore_crosses_the_stream_at_a_slant", "r4_river_mouth_study",
     "make_project", {BRIDGE: ASSIGN}),
    ("test_river_tool_gpu", "test_a_creator_draws_edits_and_plays_a_river_in_studio", "r1_river_study", "make_project",
     {BRIDGE: ASSIGN}),
    ("test_river_tool_gpu", "test_losing_focus_drops_a_river_being_drawn_or_a_point_being_dragged", "r1_river_study",
     "make_project", {BRIDGE: ASSIGN}),
    ("test_river_tool_gpu", "test_a_narrow_raised_river_is_selected_by_its_water_not_the_ground_behind_it",
     "r1_river_study", "make_project", {BRIDGE: ASSIGN}),
    ("test_water_passable_gpu", "test_studio_sets_walking_into_it_for_a_stream_and_a_pond_one_undo_step_each",
     "r4_river_mouth_study", "make_project", {BRIDGE: ASSIGN}),
    ("test_weather_collisions_gpu", "test_studio_previews_the_weather_as_play_shows_it", "m18_particles_study",
     "make_project", {BRIDGE: ASSIGN}),
    ("test_weather_collisions_gpu", "test_studio_says_what_is_wrong_with_a_room_s_weather", "m18_particles_study",
     "make_project", {BRIDGE: ASSIGN}),
    ("test_start_room_music_gpu", "test_an_older_projects_absent_and_null_music_and_missing_start_room_are_kept",
     "m23d_start_music_studio", "older", BOTH),
]

# Function-scoped fixtures that hand a live Studio driver to their test: module -> the bridge flag while it lives
# ("1": off; None: taken away, for the test that needs the live session).
DRIVERS: dict[str, str | None] = {
    "test_room_file_ownership_gpu": "1",
    "test_studio_ai_write_set_gpu": "1",
    "test_studio_room_undo_save_gpu": "1",
    "test_live_bridge_request_states_gpu": None,
}

BOTH_STARTS = {"absent": (None, None), "set": (STARTS["set"], "0"), "empty": ("", "")}


def _starting(monkeypatch: pytest.MonkeyPatch, start: str) -> dict[str, str | None]:
    values = dict(zip((SETTINGS, BRIDGE), BOTH_STARTS[start]))
    for name, value in values.items():
        _start(monkeypatch, name, value)
    return values


def _replace(monkeypatch: pytest.MonkeyPatch, module: str, name: str, stand_in: Any) -> None:
    heavy = importlib.import_module(module)
    if name.startswith("PHASES["):
        monkeypatch.setitem(heavy.PHASES, name[len("PHASES["):-1], stand_in)
    else:
        monkeypatch.setattr(heavy, name, stand_in)


def _fixture_with_stand_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: Fixture,
                           raises: bool) -> tuple[Any, list[dict]]:
    """The module's real fixture function, with the heavy work it drives replaced by a stand-in that records the two
    variables (and the folder it was given) and returns a report or raises. Nothing of the stand-in's reaches the
    repository: what a module keeps of its report goes nowhere or to ``tmp_path``."""
    mod = importlib.import_module(f"tests.{case.module}")
    seen: list[dict] = []

    def stand_in(where: Path, *args: Any, **kwargs: Any) -> dict:
        seen.append({SETTINGS: _now(SETTINGS), BRIDGE: _now(BRIDGE), "where": Path(where)})
        if raises:
            raise _Seen
        return {"steps": [], "performance": {}, "gl": {}, "timings": {}}

    for heavy, name in case.heavy:
        _replace(monkeypatch, heavy, name, stand_in)
    if hasattr(mod, "_keep"):  # (a copy of the report under artifacts/)
        monkeypatch.setattr(mod, "_keep", lambda name, found: None)
    if case.module == "test_hd2d_composite_gpu":  # (it writes that copy itself, under REPO)
        monkeypatch.setattr(mod, "REPO", tmp_path)
    if case.module == "test_new_game_isolation_gpu":  # (it makes its project with `mesh_cli new` first: a folder will do)
        def made(argv: list[str], **kwargs: Any) -> Any:
            project = Path(argv[argv.index("--dest") + 1]) / "r1"
            project.mkdir(parents=True)
            (project / "config.json").write_text("{}", encoding="utf-8")
            (project / "main.py").write_text("", encoding="utf-8")
            return types.SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(mod, "subprocess", types.SimpleNamespace(run=made))
    if case.module == "test_state_lifecycle_gpu":  # (it edits the room its project is built with: an empty one will do)
        def build(project: Path) -> None:
            (project / mod.START).parent.mkdir(parents=True)
            (project / mod.START).write_text('{"entities": []}', encoding="utf-8")

        monkeypatch.setattr(importlib.import_module("d1_debug_scenario"), "build", build)
    return getattr(mod, case.fixture).__wrapped__, seen


def _while_running(writes: dict[str, str], start: dict[str, str | None], seen: dict) -> None:
    """What the heavy work saw: each variable its caller writes as it writes it, the other one untouched."""
    for name in (SETTINGS, BRIDGE):
        if writes.get(name) == ASSIGN or (writes.get(name) == IF_ABSENT and start[name] is None):
            if name == BRIDGE:
                assert seen[name] == "1", seen
            else:  # (a settings file of the caller's own: in the folder its work is given, or the one above it)
                assert seen[name] and Path(seen[name]).name == "user_settings.json", seen
                assert Path(seen[name]).parent in (seen["where"], seen["where"].parent), seen
        else:
            assert seen[name] == start[name], (name, seen)


@pytest.mark.parametrize("start", BOTH_STARTS)
@pytest.mark.parametrize("case", [key for key, case in FIXTURES.items() if case.returns])
def test_each_module_fixture_puts_both_variables_back_after_its_run(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, tmp_path: Path, case: str,
        start: str) -> None:
    values = _starting(monkeypatch, start)
    fixture, seen = _fixture_with_stand_in(monkeypatch, tmp_path, FIXTURES[case], raises=False)
    fixture(tmp_path_factory)
    assert len(seen) == len(FIXTURES[case].heavy), "the fixture drove each piece of its work once"
    for saw in seen:
        _while_running(FIXTURES[case].writes, values, saw)
    assert {name: _now(name) for name in values} == values, "as found, after it"


@pytest.mark.parametrize("start", BOTH_STARTS)
@pytest.mark.parametrize("case", FIXTURES)
def test_each_module_fixture_puts_both_variables_back_when_its_run_raises(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, tmp_path: Path, case: str,
        start: str) -> None:
    values = _starting(monkeypatch, start)
    fixture, seen = _fixture_with_stand_in(monkeypatch, tmp_path, FIXTURES[case], raises=True)
    with pytest.raises(_Seen):
        fixture(tmp_path_factory)
    _while_running(FIXTURES[case].writes, values, seen[0])
    assert {name: _now(name) for name in values} == values, "as found, after it"


@pytest.mark.parametrize("start", BOTH_STARTS)
@pytest.mark.parametrize(("module", "test", "heavy", "name", "writes"), STUDIO_TESTS,
                         ids=[f"{m}::{t[:40]}" for m, t, *_rest in STUDIO_TESTS])
def test_each_studio_test_sets_the_variables_only_for_itself(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, module: str,
        test: str, heavy: str, name: str, writes: dict[str, str], start: str) -> None:
    """The real test function runs until its first heavy call (a stand-in that records the variables, then fails, as
    a broken setup would). It is given a scoped patch as its ``monkeypatch``, exactly as pytest gives it one: whatever
    it set that way is undone when the patch ends, so the variables must be back as they were; a raw write would
    outlive it."""
    values = _starting(monkeypatch, start)
    func = getattr(importlib.import_module(f"tests.{module}"), test)
    seen: list[dict] = []

    def stand_in(where: Path, *args: Any, **kwargs: Any) -> Any:
        seen.append({SETTINGS: _now(SETTINGS), BRIDGE: _now(BRIDGE), "where": Path(where)})
        raise _Seen

    _replace(monkeypatch, heavy, name, stand_in)
    with pytest.MonkeyPatch.context() as given:
        given_to = {"tmp_path": tmp_path, "tmp_path_factory": tmp_path_factory, "monkeypatch": given,
                    "record_testsuite_property": lambda name, value: None}
        with pytest.raises(_Seen):
            func(**{name: given_to[name] for name in inspect.signature(func).parameters})
    _while_running(writes, values, seen[0])
    assert {name: _now(name) for name in values} == values, "as found, after it"


class _FakeDriver:
    """In place of ``StudioDriver`` (a real hidden Studio window): notes the bridge flag as it opens and as it closes."""
    opened: list[str | None] = []
    closed: list[str | None] = []

    def __init__(self, project: Path) -> None:
        self.opened.append(_now(BRIDGE))

    def close(self) -> None:
        self.closed.append(_now(BRIDGE))


def _driver_fixture(monkeypatch: pytest.MonkeyPatch, module: str, tmp_path: Path, given: pytest.MonkeyPatch,
                    build: Any) -> Any:
    """The module's real ``driver`` fixture (a generator), its project builder and its Studio window replaced."""
    monkeypatch.setattr(importlib.import_module("hd2d_floors_demo"), "build", build)
    monkeypatch.setattr(importlib.import_module("hd2d_studio_demo"), "StudioDriver", _FakeDriver)
    monkeypatch.setattr(_FakeDriver, "opened", [])
    monkeypatch.setattr(_FakeDriver, "closed", [])
    fixture = importlib.import_module(f"tests.{module}").driver.__wrapped__
    given_to = {"tmp_path": tmp_path, "monkeypatch": given}
    return fixture(**{name: given_to[name] for name in inspect.signature(fixture).parameters})


@pytest.mark.parametrize("start", BRIDGE_STARTS)
@pytest.mark.parametrize("module", DRIVERS)
def test_each_driver_fixture_holds_the_bridge_flag_for_its_test_and_puts_it_back(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, module: str, start: str) -> None:
    """Set up, the test's turn, torn down: the flag is as the session needs it from the window opening to its
    closing, and as it was once the test's own patch ends."""
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])
    with pytest.MonkeyPatch.context() as given:
        held = _driver_fixture(monkeypatch, module, tmp_path, given, build=lambda where: where)
        assert isinstance(next(held), _FakeDriver)
        assert _now(BRIDGE) == DRIVERS[module], "while the test runs"
        with pytest.raises(StopIteration):
            next(held)
        assert (_FakeDriver.opened, _FakeDriver.closed) == ([DRIVERS[module]], [DRIVERS[module]])
    assert _now(BRIDGE) == BRIDGE_STARTS[start], "as found, after it"


@pytest.mark.parametrize("start", BRIDGE_STARTS)
@pytest.mark.parametrize("module", DRIVERS)
def test_each_driver_fixture_puts_the_bridge_flag_back_when_its_setup_fails(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, module: str, start: str) -> None:
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])
    seen: list[str | None] = []

    def build(where: Path) -> Path:
        seen.append(_now(BRIDGE))
        raise _Seen

    with pytest.MonkeyPatch.context() as given:
        with pytest.raises(_Seen):
            next(_driver_fixture(monkeypatch, module, tmp_path, given, build))
    assert seen == [DRIVERS[module]], "as the session would need it, while it is made"
    assert _now(BRIDGE) == BRIDGE_STARTS[start], "as found, after it"


@pytest.mark.parametrize("start", BRIDGE_STARTS)
def test_the_studio_modules_bridge_fixture_holds_the_flag_until_its_teardown(
        monkeypatch: pytest.MonkeyPatch, start: str) -> None:
    """``tests/test_hd2d_studio_gpu.py::monkeypatch_module`` yields to the module's session fixture: the flag stays
    off until pytest resumes it, then is as it was (not deleted)."""
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])
    held = importlib.import_module("tests.test_hd2d_studio_gpu").monkeypatch_module.__wrapped__()
    next(held)
    assert _now(BRIDGE) == "1"
    with pytest.raises(StopIteration):
        next(held)
    assert _now(BRIDGE) == BRIDGE_STARTS[start]


# --- Policy: no test module writes these two variables straight into the environment ---

TESTS = Path(__file__).resolve().parent


def _raw_writes(source: str) -> list[int]:
    """Lines that write either variable straight into the process environment: ``os.environ`` item assignment or
    deletion, any of its methods but ``get`` given the name (``setdefault``, ``pop``, ``update`` with a dict or a
    keyword...), ``os.putenv`` and ``os.unsetenv``. Seen through the usual disguises: ``import os as o``, ``from os
    import environ``, ``env = os.environ``, and the name held in a module constant.

    Not seen: a name that only reaches the write through other data (a dict built elsewhere and passed to
    ``update``, a loop variable). The suite's own session default, ``tests/conftest.py::_private_recent_projects``,
    is written that way: it sets what is absent for the whole run and takes back exactly what it set."""
    tree = ast.parse(source)
    names = {SETTINGS, BRIDGE}
    constants: dict[str, str] = {}  # module-level NAME = "MESH_..." (also from a tuple assignment)
    os_names, environ_names, direct = {"os"}, set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_names |= {a.asname or a.name for a in node.names if a.name == "os"}
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            environ_names |= {a.asname or a.name for a in node.names if a.name == "environ"}
            direct.update({a.asname or a.name: a.name for a in node.names if a.name in ("putenv", "unsetenv")})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                pairs = (zip(target.elts, node.value.elts)
                         if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) else [(target, node.value)])
                for name, value in pairs:
                    if isinstance(name, ast.Name) and isinstance(value, ast.Constant) and value.value in names:
                        constants[name.id] = value.value

    def is_os(node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in os_names

    def is_environ(node: ast.AST) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ" and is_os(node.value)) or (
            isinstance(node, ast.Name) and node.id in environ_names)

    for node in ast.walk(tree):  # (env = os.environ: another name for it)
        if isinstance(node, ast.Assign) and is_environ(node.value):
            environ_names |= {t.id for t in node.targets if isinstance(t, ast.Name)}

    def named(node: ast.AST) -> bool:
        return any((isinstance(n, ast.Constant) and n.value in names) or (isinstance(n, ast.Name) and n.id in constants)
                   for n in ast.walk(node))

    lines = []
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, (ast.Assign, ast.Delete))
                   else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
        if any(isinstance(t, ast.Subscript) and is_environ(t.value) and named(t.slice) for t in targets):
            lines.append(node.lineno)
        if isinstance(node, ast.Call):
            func = node.func
            method = isinstance(func, ast.Attribute) and is_environ(func.value) and func.attr != "get"
            putenv = (isinstance(func, ast.Attribute) and is_os(func.value) and func.attr in ("putenv", "unsetenv")) or (
                isinstance(func, ast.Name) and func.id in direct)
            given = any(named(a) for a in node.args) or any(k.arg in names or named(k.value) for k in node.keywords)
            if (method or putenv) and given:
                lines.append(node.lineno)
    return sorted(set(lines))


def _modules_writing_raw() -> dict[str, list[int]]:
    found = {}
    for path in sorted(TESTS.rglob("*.py")):
        if path == Path(__file__).resolve():  # (this file spells the writes out, as text, for the checks below)
            continue
        source = path.read_text(encoding="utf-8-sig")
        if SETTINGS in source or BRIDGE in source:  # (only a file that names one can write it by name: parse those)
            found[path.relative_to(TESTS).as_posix()] = _raw_writes(source)
    return {name: lines for name, lines in found.items() if lines}


RAW = [
    'os.environ["{B}"] = "1"', 'os.environ.setdefault("{S}", "x")', 'os.environ.pop("{B}", None)', 'del os.environ["{S}"]',
    'os.environ.update({{"{B}": "1"}})', 'os.environ["{B}"] += "1"', 'os.environ.update({B}="1")',
    'os.environ.update(**{{"{S}": "x"}})', 'os.putenv("{B}", "1")', 'os.unsetenv("{S}")',
    'import os as o\no.environ["{B}"] = "1"', 'from os import environ\nenviron["{B}"] = "1"',
    'from os import environ as e\ne.pop("{S}")', 'env = os.environ\nenv["{B}"] = "1"',
    'env = os.environ\nenv.update({B}="1")', 'from os import putenv\nputenv("{B}", "1")',
    'NAME = "{B}"\nos.environ[NAME] = "1"', 'A, NAME = "x", "{S}"\nos.environ.pop(NAME, None)',
]
FINE = [
    'os.environ.get("{B}")', 'x = os.environ["{S}"]', '"{B}" in os.environ', 'env.setenv("{B}", "1")',
    'monkeypatch.delenv("{S}")', 'os.environ["MESH_USER_DIR"] = "x"', 'x = {{"{B}": "1"}}',
    'subprocess.run(cmd, env={{**os.environ, "{B}": "1"}})', 'env = dict(os.environ)\nenv["{B}"] = "1"',
    'env = os.environ.copy()\nenv["{S}"] = "x"',
]


@pytest.mark.parametrize("raw", RAW)
def test_the_raw_write_check_sees_each_kind_of_write(raw: str) -> None:
    source = raw.format(B=BRIDGE, S=SETTINGS)
    assert _raw_writes(source) == [len(source.splitlines())], source


@pytest.mark.parametrize("fine", FINE)
def test_the_raw_write_check_leaves_reads_copies_and_scoped_patches_alone(fine: str) -> None:
    source = fine.format(B=BRIDGE, S=SETTINGS)
    assert _raw_writes(source) == [], source


def test_no_test_module_writes_these_variables_raw() -> None:
    """Set them through ``monkeypatch`` (a test, a function fixture) or ``pytest.MonkeyPatch.context()`` (a wider
    fixture): both put back exactly what was there. No exceptions among the test modules."""
    assert _modules_writing_raw() == {}
