"""The dialogue and lighting GPU fixtures leave the process environment as they found it (repository health audit).

``tests/test_dialogue_reopen_gpu.py::report`` set ``MESH_RUNTIME_SETTINGS_PATH`` and ``MESH_STUDIO_NO_AI_BRIDGE`` and
never restored them, so every later module in the same pytest process (a GPU shard) inherited a settings file in a
finished test's temporary folder and a disabled AI bridge. ``tests/test_hd2d_lighting_controls_gpu.py::run`` set the
bridge flag at its start and popped it only in a ``finally`` near its end: a value the caller had set was deleted, and
a failure before that ``try`` (making the project, say) left the flag set.

These tests run the real fixture functions (their ``__wrapped__`` bodies), with only the heavy work they drive (the
Studio session, the project scaffold) replaced by a stand-in that records the environment it sees and returns or
raises. Each variable starts absent, set to a value, or set to an empty string (which is not the same as absent).

Sweep phase 1 (the #505 follow-up): 13 more GPU modules wrote one or both variables and never put them back. Nine
module fixtures (assigned, or ``setdefault`` when absent: absent after any of the modules that pop the settings path)
now patch inside ``pytest.MonkeyPatch.context()`` around the run they feed; seven Studio test functions in four
modules set the bridge flag through their own ``monkeypatch``. The policy tests at the end keep every GPU module off
raw writes of these two variables, apart from the phase 2 modules still listed (which must still need fixing)."""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import types
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


# --- Sweep phase 1: the 13 GPU modules that never put the variables back ---

# module -> (its fixture, the module of the heavy work it drives, that work's function, {variable: how it is written})
# "assign": set for the run; "if absent": set only when absent (the old setdefault), otherwise left as it is.
FIXTURES: dict[str, tuple[str, str, str, dict[str, str]]] = {
    "test_ai_playtest_gpu": ("run", "d2_ai_playtest_scenario", "run", {SETTINGS: "if absent"}),
    "test_hd2d_asset_pipeline_gpu": ("run", "hd2d_asset_pipeline_demo", "check", {BRIDGE: "assign"}),
    "test_hd2d_emissive_gpu": ("run", "hd2d_emissive_demo", "check", {BRIDGE: "assign"}),
    "test_hd2d_lamp_glow_gpu": ("run", "hd2d_lamp_glow_demo", "check", {BRIDGE: "assign"}),
    "test_hd2d_starter_gpu": ("run", "hd2d_starter_demo", "check", {BRIDGE: "assign"}),
    "test_interaction_debugger_gpu": ("run", "d3a_interaction_scenario", "run", {SETTINGS: "if absent"}),
    "test_new_game_isolation_gpu": ("sessions", "watchfire_r1_sessions", "flag_sessions", {SETTINGS: "if absent"}),
    "test_runtime_debugger_gpu": ("run", "d1_debug_scenario", "run", {SETTINGS: "if absent"}),
    "test_studio_3d_selection_gpu": ("report", "watchfire_r3_selection", "run", {SETTINGS: "assign", BRIDGE: "assign"}),
}

# (module, Studio test function, the study module whose make_project is the first thing after the flag is set)
STUDIO_TESTS = [
    ("test_river_bed_gpu", "test_studio_carves_a_stream_s_bed_so_its_water_shows_undo_and_clear_its_plants",
     "r3_river_bed_study"),
    ("test_river_mouth_gpu", "test_studio_draws_one_water_surface_where_the_stream_enters_the_pond",
     "r4_river_mouth_study"),
    ("test_river_mouth_gpu", "test_no_seam_where_the_shore_crosses_the_stream_at_a_slant", "r4_river_mouth_study"),
    ("test_river_tool_gpu", "test_a_creator_draws_edits_and_plays_a_river_in_studio", "r1_river_study"),
    ("test_river_tool_gpu", "test_losing_focus_drops_a_river_being_drawn_or_a_point_being_dragged", "r1_river_study"),
    ("test_river_tool_gpu", "test_a_narrow_raised_river_is_selected_by_its_water_not_the_ground_behind_it",
     "r1_river_study"),
    ("test_water_passable_gpu", "test_studio_sets_walking_into_it_for_a_stream_and_a_pond_one_undo_step_each",
     "r4_river_mouth_study"),
]

BOTH_STARTS = {"absent": (None, None), "set": (STARTS["set"], "0"), "empty": ("", "")}


def _fixture_with_stand_in(monkeypatch: pytest.MonkeyPatch, module: str, raises: bool) -> tuple[Any, list[dict]]:
    """The module's real fixture function, with the heavy work it drives replaced by a stand-in that records the two
    variables (and the folder it was given) and returns a report or raises."""
    mod = importlib.import_module(f"tests.{module}")
    fixture, heavy, func, _how = FIXTURES[module]
    seen: list[dict] = []

    def stand_in(where: Path, *args: Any, **kwargs: Any) -> dict:
        seen.append({SETTINGS: _now(SETTINGS), BRIDGE: _now(BRIDGE), "where": Path(where)})
        if raises:
            raise _Seen
        return {"steps": [], "performance": {}, "gl": {}, "timings": {}}

    monkeypatch.setattr(importlib.import_module(heavy), func, stand_in)
    if module == "test_new_game_isolation_gpu":  # (it makes its project with `mesh_cli new` first: a folder will do)
        def made(argv: list[str], **kwargs: Any) -> Any:
            project = Path(argv[argv.index("--dest") + 1]) / "r1"
            project.mkdir(parents=True)
            (project / "config.json").write_text("{}", encoding="utf-8")
            (project / "main.py").write_text("", encoding="utf-8")
            return types.SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(mod, "subprocess", types.SimpleNamespace(run=made))
    return getattr(mod, fixture).__wrapped__, seen


def _while_running(module: str, start: dict[str, str | None], seen: dict) -> None:
    """What the heavy work saw: each variable the fixture writes as it writes it, the other one untouched."""
    how = FIXTURES[module][3]
    for name in (SETTINGS, BRIDGE):
        if how.get(name) == "assign" or (how.get(name) == "if absent" and start[name] is None):
            want = "1" if name == BRIDGE else None
            if want is None:  # (a settings file in the fixture's own temporary folder)
                assert seen[name] and Path(seen[name]).name == "user_settings.json", seen
                assert seen["where"] in (Path(seen[name]).parent, Path(seen[name]).parent / "r1"), seen
            else:
                assert seen[name] == want, seen
        else:
            assert seen[name] == start[name], (name, seen)


@pytest.mark.parametrize("start", BOTH_STARTS)
@pytest.mark.parametrize("module", FIXTURES)
def test_each_module_fixture_puts_both_variables_back_after_its_run(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, module: str, start: str) -> None:
    values = dict(zip((SETTINGS, BRIDGE), BOTH_STARTS[start]))
    for name, value in values.items():
        _start(monkeypatch, name, value)
    fixture, seen = _fixture_with_stand_in(monkeypatch, module, raises=False)
    fixture(tmp_path_factory)
    assert len(seen) == 1, "the fixture drove its work once"
    _while_running(module, values, seen[0])
    assert {name: _now(name) for name in values} == values, "as found, after it"


@pytest.mark.parametrize("start", BOTH_STARTS)
@pytest.mark.parametrize("module", FIXTURES)
def test_each_module_fixture_puts_both_variables_back_when_its_run_raises(
        monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, module: str, start: str) -> None:
    values = dict(zip((SETTINGS, BRIDGE), BOTH_STARTS[start]))
    for name, value in values.items():
        _start(monkeypatch, name, value)
    fixture, seen = _fixture_with_stand_in(monkeypatch, module, raises=True)
    with pytest.raises(_Seen):
        fixture(tmp_path_factory)
    _while_running(module, values, seen[0])
    assert {name: _now(name) for name in values} == values, "as found, after it"


@pytest.mark.parametrize("start", BRIDGE_STARTS)
@pytest.mark.parametrize(("module", "test", "study"), STUDIO_TESTS, ids=[f"{m}::{t[:40]}" for m, t, _s in STUDIO_TESTS])
def test_each_studio_test_sets_the_bridge_flag_only_through_its_own_monkeypatch(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, module: str, test: str, study: str, start: str) -> None:
    """The real test function runs until its project is made (a stand-in that records the flag, then fails, as a
    broken setup would). It is given a scoped patch as its ``monkeypatch``, exactly as pytest gives it one: whatever it
    set that way is undone when the patch ends, so the flag must be back as it was; a raw write would outlive it."""
    _start(monkeypatch, BRIDGE, BRIDGE_STARTS[start])
    func = getattr(importlib.import_module(f"tests.{module}"), test)
    seen: list[str | None] = []

    def make_project(*args: Any, **kwargs: Any) -> Path:
        seen.append(_now(BRIDGE))
        raise _Seen

    monkeypatch.setattr(importlib.import_module(study), "make_project", make_project)
    params = inspect.signature(func).parameters
    with pytest.MonkeyPatch.context() as given:
        kwargs: dict[str, Any] = {"tmp_path": tmp_path}
        if "monkeypatch" in params:
            kwargs["monkeypatch"] = given
        if "record_testsuite_property" in params:
            kwargs["record_testsuite_property"] = lambda name, value: None
        with pytest.raises(_Seen):
            func(**kwargs)
    assert seen == ["1"], "set while its Studio session is made"
    assert _now(BRIDGE) == BRIDGE_STARTS[start], "as found, after it"


# --- Policy: no raw writes of these two variables in GPU test modules ---

TESTS = Path(__file__).resolve().parent

# The modules phase 2 corrects (they pop a variable unconditionally). Each must still write raw, so a fixed module has
# to leave the list, and phase 2 ends with it empty: no permanent exemptions.
PHASE_2 = frozenset({
    "test_dof_studio_gpu", "test_hd2d_bloom_gpu", "test_hd2d_composite_gpu", "test_hd2d_haze_gpu",
    "test_hd2d_post_gpu", "test_hd2d_room_expand_gpu", "test_hd2d_room_studio_gpu", "test_hd2d_shadow_allocation_gpu",
    "test_hd2d_studio_gpu", "test_live_bridge_request_states_gpu", "test_river_falls_gpu",
    "test_room_file_ownership_gpu", "test_scatter_diagnostics_gpu", "test_settings_ui_gpu",
    "test_soundscape_studio_gpu", "test_start_room_music_gpu", "test_state_lifecycle_gpu",
    "test_studio_ai_write_set_gpu", "test_studio_room_undo_save_gpu", "test_studio_workflow_polish_gpu",
    "test_studio_workspace_gpu", "test_weather_authoring_gpu", "test_weather_collisions_gpu",
})


def _is_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name)
            and node.value.id == "os")


def _raw_writes(source: str) -> list[int]:
    """Lines writing either variable straight into ``os.environ``: item assignment or deletion, or any of its methods
    other than ``get`` given the name (``setdefault``, ``pop``, ``update``...)."""
    names = {SETTINGS, BRIDGE}
    lines = []
    for node in ast.walk(ast.parse(source)):
        targets = (node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AugAssign)
                   else node.targets if isinstance(node, ast.Delete) else [])
        if any(isinstance(t, ast.Subscript) and _is_environ(t.value) and isinstance(t.slice, ast.Constant)
               and t.slice.value in names for t in targets):
            lines.append(node.lineno)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _is_environ(node.func.value)
                and node.func.attr != "get"
                and any(isinstance(c, ast.Constant) and c.value in names for a in node.args for c in ast.walk(a))):
            lines.append(node.lineno)
    return sorted(lines)


def _gpu_modules_writing_raw() -> dict[str, list[int]]:
    found = {path.stem: _raw_writes(path.read_text(encoding="utf-8")) for path in sorted(TESTS.glob("test_*_gpu.py"))}
    return {name: lines for name, lines in found.items() if lines}


def test_the_raw_write_check_sees_each_kind_of_write_and_nothing_else() -> None:
    for raw in (f'os.environ["{BRIDGE}"] = "1"', f'os.environ.setdefault("{SETTINGS}", "x")',
                f'os.environ.pop("{BRIDGE}", None)', f'del os.environ["{SETTINGS}"]',
                f'os.environ.update({{"{BRIDGE}": "1"}})', f'os.environ["{BRIDGE}"] += "1"'):
        assert _raw_writes(raw) == [1], raw
    for fine in (f'os.environ.get("{BRIDGE}")', f'env.setenv("{BRIDGE}", "1")', f'monkeypatch.delenv("{SETTINGS}")',
                 'os.environ["MESH_USER_DIR"] = "x"', f'x = {{"{BRIDGE}": "1"}}'):
        assert _raw_writes(fine) == [], fine


def test_no_gpu_module_writes_these_variables_raw_beyond_the_phase_2_list() -> None:
    raw = _gpu_modules_writing_raw()
    assert {name: lines for name, lines in raw.items() if name not in PHASE_2} == {}, (
        "set them through monkeypatch (a test) or pytest.MonkeyPatch.context() (a wider fixture) instead")
    assert {*FIXTURES, *(m for m, _t, _s in STUDIO_TESTS)}.isdisjoint(raw)


def test_every_module_on_the_phase_2_list_still_needs_fixing() -> None:
    assert sorted(PHASE_2 - set(_gpu_modules_writing_raw())) == [], "fixed: take it off the PHASE_2 list"
