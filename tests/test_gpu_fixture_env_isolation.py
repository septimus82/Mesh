"""The dialogue and lighting GPU fixtures leave the process environment as they found it (repository health audit).

``tests/test_dialogue_reopen_gpu.py::report`` set ``MESH_RUNTIME_SETTINGS_PATH`` and ``MESH_STUDIO_NO_AI_BRIDGE`` and
never restored them, so every later module in the same pytest process (a GPU shard) inherited a settings file in a
finished test's temporary folder and a disabled AI bridge. ``tests/test_hd2d_lighting_controls_gpu.py::run`` set the
bridge flag at its start and popped it only in a ``finally`` near its end: a value the caller had set was deleted, and
a failure before that ``try`` (making the project, say) left the flag set.

These tests run the real fixture functions (their ``__wrapped__`` bodies), with only the heavy work they drive (the
Studio session, the project scaffold) replaced by a stand-in that records the environment it sees and returns or
raises. Each variable starts absent, set to a value, or set to an empty string (which is not the same as absent)."""

from __future__ import annotations

import os
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
    if value is None:
        monkeypatch.delenv(name, raising=False)
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
