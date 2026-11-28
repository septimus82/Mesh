"""#422 H9.1: an exported game keeps its player's settings beside their saves, never in its installation.

The settings (volumes, fog, calmer flickering) of an exported game were read from and written to
``<installation>/user_settings.json``: changed in a read-only installation's menu, the write raised out of the menu.
Now an exported game's are in ``<per-user data>/MeshMind Studios/<game id>/user_settings.json`` (H9's folder for that
game); an older export's file in its installation is read, never written. The installed, exported games are tested in
tests/test_wheel_bundles_engine_data.py; these take the rules one at a time in temporary folders (a player's data folder
is always moved into one).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.runtime_settings import RuntimeSettings
from engine.runtime_settings_storage import load_runtime_settings, resolve_runtime_settings_path, save_runtime_settings
from engine.save_runtime import storage
from tooling.installed_product_check import read_only

pytestmark = pytest.mark.fast

GAME_ID = "my-game-1a2b3c4d"


def _install(folder: Path, *, exported: bool = True, game_id: str = GAME_ID) -> Path:
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps({"title": "My Game", "game_id": game_id}), encoding="utf-8")
    if exported:
        (folder / storage.EXPORT_MARKER).write_text("{}", encoding="utf-8")
    return folder


@pytest.fixture
def player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This player's application-data folder, in the test's own folder; the game's folder is set per test."""
    data = tmp_path / "Benutzer Daten é"
    monkeypatch.setenv("APPDATA", str(data))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.delenv("MESH_RUNTIME_SETTINGS_PATH", raising=False)  # (the tests' conftest sets one)
    monkeypatch.delenv(storage.SAVE_DIR_ENV, raising=False)
    return data if sys.platform != "darwin" else tmp_path / "home" / "Library" / "Application Support"


def _running(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """The game in ``root`` is the one running (an exported game's engine is in its own folder)."""
    monkeypatch.setenv("MESH_REPO_ROOT", str(root))


def _settings(player: Path, game_id: str = GAME_ID) -> Path:
    return player / storage.PUBLISHER_DIR / game_id / "user_settings.json"


def _write(path: Path, **values: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, **values}), encoding="utf-8")
    return path


def test_a_read_only_exported_game_saves_its_settings_in_its_player_s_folder(
        tmp_path: Path, player: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect: they went to <installation>/user_settings.json, and a read-only installation raised."""
    install = _install(tmp_path / "Program Files" / "My Game")
    _running(monkeypatch, install)
    assert resolve_runtime_settings_path() == _settings(player)
    with read_only(install):
        assert save_runtime_settings(None, RuntimeSettings(music_volume=0.3)) is True
    assert json.loads(_settings(player).read_text(encoding="utf-8"))["music_volume"] == pytest.approx(0.3)
    assert sorted(p.name for p in install.iterdir()) == ["bundle_manifest.json", "config.json"]
    assert _settings(player).parent / "saves" != _settings(player), "beside the saves folder, not in it"
    assert load_runtime_settings(None).music_volume == pytest.approx(0.3)


def test_the_menus_say_when_settings_could_not_be_saved(tmp_path: Path, player: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """A save that fails is reported (not "Settings saved"); the game keeps running with the change in effect."""
    from engine.ui_overlays.main_menu_overlay import MainMenuOverlay
    from engine.ui_overlays.pause_menu import PauseMenu

    blocker = tmp_path / "not a folder"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    for menu_class in (PauseMenu, MainMenuOverlay):
        hud = MagicMock()
        hud.active_toasts.return_value = []
        window = SimpleNamespace(runtime_settings=RuntimeSettings(music_volume=0.25), player_hud=hud,
                                 runtime_settings_path=blocker / "user_settings.json", editor=None)
        menu = menu_class.__new__(menu_class)
        menu.window = window
        menu._save_runtime_settings()  # (raised before)
        toasts = [c.args[0] for c in hud.enqueue_toast.call_args_list]
        assert toasts == ["Settings not saved"], (menu_class.__name__, toasts)
        assert window.runtime_settings.music_volume == pytest.approx(0.25), "still in effect"


def test_a_project_and_the_overrides_keep_their_settings_file(tmp_path: Path, player: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    project = _install(tmp_path / "Mesh Projects" / "My Game", exported=False)
    _running(monkeypatch, project)
    assert resolve_runtime_settings_path() == project / "user_settings.json", "a project: as before"
    exported = _install(tmp_path / "game")
    _running(monkeypatch, exported)
    assert resolve_runtime_settings_path(tmp_path / "given.json") == tmp_path / "given.json", "a given path first"
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(tmp_path / "env.json"))
    assert resolve_runtime_settings_path() == tmp_path / "env.json", "then MESH_RUNTIME_SETTINGS_PATH"
    monkeypatch.delenv("MESH_RUNTIME_SETTINGS_PATH")
    monkeypatch.setenv(storage.SAVE_DIR_ENV, str(tmp_path / "saves elsewhere"))
    assert resolve_runtime_settings_path() == _settings(player), "MESH_SAVE_DIR moves saves, not settings"


@pytest.mark.parametrize(("platform", "env", "base"), [
    ("win32", {"APPDATA": "{tmp}/Roaming"}, "{tmp}/Roaming"),
    ("darwin", {}, "{home}/Library/Application Support"),  # (macOS: unit-tested only; CI has no macOS runner)
    ("linux", {"XDG_DATA_HOME": "{tmp}/xdg"}, "{tmp}/xdg"),
    ("linux", {}, "{home}/.local/share"),
])
def test_each_platform_s_settings_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str,
                                         env: dict[str, str], base: str) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(storage.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    for key in ("APPDATA", "XDG_DATA_HOME", "MESH_RUNTIME_SETTINGS_PATH"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value.format(tmp=tmp_path.as_posix()))
    _running(monkeypatch, _install(tmp_path / "game"))
    expected = Path(base.format(tmp=tmp_path.as_posix(), home=home.as_posix())) / storage.PUBLISHER_DIR / GAME_ID
    assert resolve_runtime_settings_path() == expected / "user_settings.json"


def test_two_games_keep_their_own_settings_and_moving_keeps_them(tmp_path: Path, player: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    _running(monkeypatch, _install(tmp_path / "C" / "My Game"))
    assert save_runtime_settings(None, RuntimeSettings(sfx_volume=0.1))
    _running(monkeypatch, _install(tmp_path / "other", game_id="my-game-ffff0000"))  # (the same title)
    assert load_runtime_settings(None).sfx_volume == pytest.approx(RuntimeSettings().sfx_volume)
    _running(monkeypatch, _install(tmp_path / "D" / "Moved here"))  # (the first game, moved or reinstalled)
    assert load_runtime_settings(None).sfx_volume == pytest.approx(0.1)


@pytest.mark.parametrize(("own", "older", "music"), [
    ("valid", "valid", 0.2),          # the player's own wins
    ("missing", "valid", 0.7),        # an older export's, read in place
    ("malformed", "valid", 0.7),
    ("wrong version", "valid", 0.7),
    ("valid", "malformed", 0.2),
    ("malformed", "malformed", None),  # neither: the defaults
    ("missing", "missing", None),
])
def test_an_older_export_s_settings_are_read_never_written(tmp_path: Path, player: Path,
                                                           monkeypatch: pytest.MonkeyPatch, own: str, older: str,
                                                           music: float | None) -> None:
    install = _install(tmp_path / "game")
    _running(monkeypatch, install)
    for state, path, value in ((own, _settings(player), 0.2), (older, install / "user_settings.json", 0.7)):
        if state == "valid":
            _write(path, music_volume=value)
        elif state == "malformed":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"version": 1, "music_volume": ', encoding="utf-8")
        elif state == "wrong version":
            _write(path, music_volume=0.9).write_text(json.dumps({"version": 99, "music_volume": 0.9}), encoding="utf-8")
    kept = {p: p.read_bytes() for p in (_settings(player), install / "user_settings.json") if p.exists()}
    with read_only(install):
        loaded = load_runtime_settings(None)
        expected = RuntimeSettings().music_volume if music is None else music
        assert loaded.music_volume == pytest.approx(expected)
        assert {p: p.read_bytes() for p in kept} == kept, "reading changes nothing"
        assert save_runtime_settings(None, RuntimeSettings(music_volume=0.5)), "a change goes to the player's folder"
    assert json.loads(_settings(player).read_text(encoding="utf-8"))["music_volume"] == pytest.approx(0.5)
    legacy = install / "user_settings.json"
    if legacy in kept:
        assert legacy.read_bytes() == kept[legacy], "the installation's file is never written"
    assert not [p for p in install.iterdir() if p.name.startswith("user_settings.json.")], "no files beside it"
    if own in ("malformed", "wrong version"):  # (kept, not overwritten: set aside beside the new file)
        assert (_settings(player).parent / "user_settings.json.invalid").read_bytes() == kept[_settings(player)]
    assert load_runtime_settings(None).music_volume == pytest.approx(0.5)


def test_an_unwritable_player_folder_reports_the_failure(tmp_path: Path, player: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    install = _install(tmp_path / "game")
    _running(monkeypatch, install)
    _write(_settings(player), music_volume=0.6)
    before = _settings(player).read_bytes()
    with read_only(_settings(player).parent):
        assert save_runtime_settings(None, RuntimeSettings(music_volume=0.1)) is False  # (no exception)
    assert _settings(player).read_bytes() == before, "the player's last settings are kept, not corrupted"
