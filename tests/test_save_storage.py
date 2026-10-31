"""#422 H9: an exported game saves per player, outside its installation; a project keeps saving in its folder.

An exported game saved to ``saves`` in the folder it ran in - its installation - so installed read-only (Program Files,
/opt) it could not save, nor even start (the save folder was made as the window opened). The installed, exported games
are tested in tests/test_wheel_bundles_engine_data.py; these tests take the rules one at a time, in temporary folders
(a player's data folder is always moved into one: no test touches a real one).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameStateController
from engine.save_manager import SaveManager
from engine.save_runtime import storage

pytestmark = pytest.mark.fast

GAME_ID = "my-game-1a2b3c4d"


class Window:
    """Enough of a game window to save and load (as tests/test_save_load_roundtrip.py's), started from ``root``."""

    def __init__(self, root: Path, **config: Any) -> None:
        self.width, self.height = 800, 600
        self.game_state_controller = GameStateController(self)
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = "packs/core_regions/scenes/start.json"
        self.scene_controller.build_scene_snapshot.return_value = {"entities": [], "settings": {"camera": {}}}
        self.request_scene_change = MagicMock()
        self.camera_controller = MagicMock()
        self.camera_controller.zoom_state.current = self.camera_controller.zoom_state.target = 1.0
        self.camera_controller.zoom_state.speed, self.camera_controller.zoom_state.min_zoom = 0.1, 0.5
        self.camera_controller.zoom_state.max_zoom = 2.0
        self.player_hud = MagicMock()
        values = {"game_id": GAME_ID, "title": "My Game", "start_scene": "packs/core_regions/scenes/start.json",
                  "world_file": "packs/core_regions/worlds/main.json", **config}
        self.engine_config = SimpleNamespace(_config_base_dir=str(root), **values)

    @property
    def gold(self) -> Any:
        return self.game_state_controller.state.counters.get("gold")

    def toasts(self) -> list[str]:
        return [c.args[0] for c in self.player_hud.enqueue_toast.call_args_list]


def _install(folder: Path, *, exported: bool = True) -> Path:
    """A game folder: an export (with the manifest only ``mesh export build`` writes) or a project."""
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps({"title": "My Game", "game_id": GAME_ID}), encoding="utf-8")
    if exported:
        (folder / storage.EXPORT_MARKER).write_text("{}", encoding="utf-8")
    return folder


@pytest.fixture
def player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This player's application-data folder, in the test's own folder, on whatever platform runs the test."""
    data = tmp_path / "Benutzer Daten é"  # (a profile path with a space and an accent)
    monkeypatch.setenv("APPDATA", str(data))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.delenv(storage.SAVE_DIR_ENV, raising=False)
    return data if sys.platform != "darwin" else tmp_path / "home" / "Library" / "Application Support"


def _saves(player: Path, game_id: str = GAME_ID) -> Path:
    return player / storage.PUBLISHER_DIR / game_id / "saves"


# --------------------------------------------------------------------------- where


@pytest.mark.parametrize(("platform", "env", "expected"), [
    ("win32", {"APPDATA": "{tmp}/Roaming"}, "{tmp}/Roaming"),
    ("win32", {"APPDATA": ""}, "{home}/AppData/Roaming"),
    ("win32", {"APPDATA": "relative/path"}, "{home}/AppData/Roaming"),
    ("darwin", {}, "{home}/Library/Application Support"),
    ("linux", {"XDG_DATA_HOME": "{tmp}/xdg"}, "{tmp}/xdg"),
    ("linux", {"XDG_DATA_HOME": ""}, "{home}/.local/share"),
    ("linux", {"XDG_DATA_HOME": "not/absolute"}, "{home}/.local/share"),  # (the XDG spec: a relative one is ignored)
])
def test_the_platform_s_per_user_data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str,
                                              env: dict[str, str], expected: str) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(storage.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    for key in ("APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value.format(tmp=tmp_path.as_posix()))
    assert storage.user_data_home() == Path(expected.format(tmp=tmp_path.as_posix(), home=home.as_posix()))


def test_an_exported_game_saves_in_its_player_s_folder_not_its_installation(tmp_path: Path, player: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect: started from its installation (main.py runs there), the game saved into it."""
    install = _install(tmp_path / "Program Files" / "My Game")
    monkeypatch.chdir(install)
    window = Window(install)
    window.game_state_controller.state.counters["gold"] = 7
    manager = SaveManager(window)
    assert manager.save_dir == _saves(player) and manager.legacy_dir == install / "saves"
    assert manager.save_game("slot1") and window.toasts() == ["Game saved"]
    assert (_saves(player) / "slot1.json").is_file() and not (install / "saves").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions; the installed lane runs this on Windows (an ACL)")
def test_a_read_only_installation_starts_saves_and_loads(tmp_path: Path, player: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    install = _install(tmp_path / "opt" / "my-game")
    monkeypatch.chdir(install)
    install.chmod(0o555)
    try:
        window = Window(install)  # (the save folder was made as the window opened: a PermissionError, no game)
        window.game_state_controller.state.counters["gold"] = 3
        manager = SaveManager(window)
        assert manager.save_game("slot1")
        window.game_state_controller.state.counters["gold"] = 0
        assert manager.load_game("slot1") and window.gold == 3
    finally:
        install.chmod(0o755)


def test_a_project_keeps_saving_in_its_folder(tmp_path: Path, player: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _install(tmp_path / "Mesh Projects" / "My Game", exported=False)
    monkeypatch.chdir(project)
    manager = SaveManager(Window(project))
    assert manager.save_dir == Path("saves") and manager.legacy_dir is None
    assert manager.save_game("dev") and (project / "saves" / "dev.json").is_file() and not player.exists()


def test_a_given_save_folder_is_used_as_given(tmp_path: Path, player: Path) -> None:
    install = _install(tmp_path / "game")
    manager = SaveManager(Window(install), save_dir=str(tmp_path / "test saves"))
    assert manager.save_dir == tmp_path / "test saves" and manager.legacy_dir is None


def test_mesh_save_dir_names_the_folder(tmp_path: Path, player: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(storage.SAVE_DIR_ENV, str(tmp_path / "automation"))
    manager = SaveManager(Window(_install(tmp_path / "game")))
    assert manager.save_dir == tmp_path / "automation" and manager.save_game("a") and not player.exists()


# --------------------------------------------------------------------------- whose


def test_the_game_id_is_the_configured_one_or_a_stable_derived_one() -> None:
    assert storage.game_identity({"game_id": GAME_ID, "title": "Anything"}) == GAME_ID
    old = {"title": "My Game", "start_scene": "packs/a/scenes/start.json", "world_file": "packs/a/worlds/main.json"}
    derived = storage.game_identity(old)
    assert derived == storage.game_identity(dict(old)) and derived.startswith("my-game-")  # (the same, every launch)
    assert storage.game_identity({**old, "start_scene": "scenes/other.json"}) != derived
    for unsafe in ("../../etc", "Has Space", "UPPER", "", "x" * 65, None, 5):
        assert storage.game_identity({**old, "game_id": unsafe}) == derived, unsafe
    assert storage.GAME_ID_PATTERN.match(storage.game_identity({"title": "魔法の森"}))  # (no letters to keep: "game-…")


def test_two_new_games_with_the_same_title_never_share_saves() -> None:
    first, second = storage.new_game_id("My Game"), storage.new_game_id("My Game")
    assert first != second and first.startswith("my-game-") and storage.GAME_ID_PATTERN.match(first)
    assert storage.new_game_id("Café Ünïcode").startswith("cafe-unicode-")


def test_each_game_sees_only_its_own_slots(tmp_path: Path, player: Path) -> None:
    mine = SaveManager(Window(_install(tmp_path / "a")))
    theirs = SaveManager(Window(_install(tmp_path / "b"), game_id="my-game-ffff0000"))  # (the same title)
    assert mine.save_game("slot1") and theirs.list_saves() == [] and mine.list_saves() == ["slot1"]


def test_moving_or_reinstalling_keeps_the_saves(tmp_path: Path, player: Path) -> None:
    first = SaveManager(Window(_install(tmp_path / "C" / "Games" / "My Game")))
    assert first.save_game("slot1")
    for again in (tmp_path / "C" / "Games" / "My Game", tmp_path / "D" / "Moved here", tmp_path / "reinstalled"):
        if not again.exists():
            _install(again)
        assert SaveManager(Window(again)).list_saves() == ["slot1"]


def test_a_new_project_gets_a_game_id_that_its_config_keeps(tmp_path: Path) -> None:
    from engine.config import load_config, save_config
    from engine.project_scaffold import create_project

    create_project(tmp_path / "game", "My Game", "blank")
    game_id = json.loads((tmp_path / "game" / "config.json").read_text(encoding="utf-8"))["game_id"]
    config = load_config(str(tmp_path / "game" / "config.json"))
    assert config.game_id == game_id and storage.GAME_ID_PATTERN.match(game_id)
    save_config(config, str(tmp_path / "game" / "config.json"))  # (Studio and the console write config.json whole)
    assert json.loads((tmp_path / "game" / "config.json").read_text(encoding="utf-8"))["game_id"] == game_id


# --------------------------------------------------------------------------- older exports' saves


def _legacy(install: Path, slot: str, gold: int) -> Path:
    """A save as an export before H9 wrote it: in ``<installation>/saves``."""
    window = Window(install)
    window.game_state_controller.state.counters["gold"] = gold
    assert SaveManager(window, save_dir=str(install / "saves")).save_game(slot)
    return install / "saves" / f"{slot}.json"


def test_an_older_export_s_saves_are_listed_and_load_and_are_never_changed(tmp_path: Path, player: Path) -> None:
    install = _install(tmp_path / "game")
    old = _legacy(install, "old", 50)
    kept = old.read_bytes()
    window = Window(install)
    manager = window.save_manager = SaveManager(window)
    assert manager.list_saves() == ["old"]
    assert manager.load_game("old") and window.gold == 50
    assert window.request_scene_change.call_args.args[0] == str(old)
    from engine.scene_runtime.room_memory import is_save_slot

    assert is_save_slot(window, str(old)), "loading it replaces the game state, as any save"
    window.game_state_controller.state.counters["gold"] = 60
    assert manager.save_game("old")  # (saved again: into the player's folder)
    assert (_saves(player) / "old.json").is_file() and old.read_bytes() == kept
    window.game_state_controller.state.counters["gold"] = 0
    assert manager.load_game("old") and window.gold == 60, "the newer, per-player copy"
    assert sorted(p.name for p in old.parent.iterdir()) == ["old.json"], "nothing written next to it"


def test_a_slot_in_both_places_loads_the_player_s_copy_unless_it_is_broken(tmp_path: Path, player: Path) -> None:
    install = _install(tmp_path / "game")
    old = _legacy(install, "slot1", 100)
    window = Window(install)
    window.game_state_controller.state.counters["gold"] = 200
    manager = SaveManager(window)
    assert manager.save_game("slot1")
    window.game_state_controller.state.counters["gold"] = 0
    assert manager.load_game("slot1") and window.gold == 200, "the per-player copy wins: never the older one"
    newer = _saves(player) / "slot1.json"
    newer.write_text("{ not a save", encoding="utf-8")
    window.game_state_controller.state.counters["gold"] = 0
    assert manager.load_game("slot1") and window.gold == 100, "a broken per-player copy: the older one, still there"
    assert newer.read_text(encoding="utf-8") == "{ not a save" and old.is_file()


def test_a_broken_older_save_fails_to_load_and_stays_untouched(tmp_path: Path, player: Path) -> None:
    install = _install(tmp_path / "game")
    (install / "saves").mkdir()
    broken = install / "saves" / "slot1.json"
    broken.write_text('{"meta": "corrupt"', encoding="utf-8")
    window = Window(install)
    window.game_state_controller.state.counters["gold"] = 9
    assert not SaveManager(window).load_game("slot1") and window.gold == 9
    assert broken.read_text(encoding="utf-8") == '{"meta": "corrupt"'
    assert sorted(p.name for p in broken.parent.iterdir()) == ["slot1.json"], "no diagnostics files in the installation"


# --------------------------------------------------------------------------- when it can't


def test_an_unwritable_player_folder_says_the_save_failed(tmp_path: Path, player: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "not a folder"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setenv(storage.SAVE_DIR_ENV, str(blocker / "saves"))
    window = Window(_install(tmp_path / "game"))
    manager = SaveManager(window)  # (the game still starts)
    assert not manager.save_game("slot1")
    assert window.toasts() and window.toasts()[-1].startswith("Couldn't save the game"), window.toasts()
    assert "Game saved" not in window.toasts()


# --------------------------------------------------------------------------- quicksave, quick snapshots


def test_quicksave_and_quick_snapshots_go_to_the_player_s_folder(tmp_path: Path, player: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import savegame

    install = _install(tmp_path / "game")
    monkeypatch.chdir(install)
    window = Window(install)
    window.save_manager = SaveManager(window)
    assert window.save_manager.save_game("quicksave") and "quicksave" in window.save_manager.list_saves()
    assert savegame.save_quick_snapshot(window)
    assert (_saves(player) / "quick.json").is_file() and not (install / "saves").exists()
    assert savegame.load_quick_snapshot(window)


def test_an_older_export_s_quick_snapshot_still_loads(tmp_path: Path, player: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import savegame

    install = _install(tmp_path / "game")
    monkeypatch.chdir(install)
    window = Window(install)
    window.save_manager = SaveManager(window, save_dir=str(install / "saves"))
    assert savegame.save_quick_snapshot(window)  # (where an export before H9 put it)
    window.save_manager = SaveManager(window)
    assert savegame.load_quick_snapshot(window) and not (_saves(player) / "quick.json").exists()


# --------------------------------------------------------------------------- quick snapshots: older exports' (review)


def _snapshot(path: Path, gold: int) -> Path:
    from engine import savegame

    window = Window(path.parent)
    window.game_state_controller.state.counters["gold"] = gold
    assert savegame.save_quick_snapshot(window, path)
    return path


def _player_window(install: Path) -> Window:
    window = Window(install)
    window.game_state_controller.state.counters["gold"] = 1
    window.save_manager = SaveManager(window)
    return window


def _inject(monkeypatch: pytest.MonkeyPatch, outcome: str) -> list[Any]:
    """The snapshot's application reports a warning (and still applies) or fails, as a real one can."""
    from engine import savegame
    from engine.diagnostics import Diagnostic

    applied: list[Any] = []

    def apply(window: Any, payload: Any, *, diagnostics: Any, **_: Any) -> bool:
        applied.append(payload)
        level = "warning" if outcome == "warning" else "error"
        diagnostics.add([Diagnostic(level=level, code="test.injected", message=f"injected {outcome}")])
        return outcome == "warning"

    monkeypatch.setattr(savegame.save_payloads, "apply_loaded_payload", apply)
    return applied


@pytest.mark.parametrize("outcome", ["warning", "failure"])
def test_an_older_export_s_quick_snapshot_gets_no_diagnostics_beside_it(
        tmp_path: Path, player: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        outcome: str) -> None:
    """Applying it can warn or fail; what is said about that goes to the log, never into the (read-only) installation."""
    from engine import savegame
    from tooling.installed_product_check import read_only

    install = _install(tmp_path / "game")
    monkeypatch.chdir(install)
    legacy = _snapshot(install / "saves" / "quick.json", 100)
    kept = legacy.read_bytes()
    window = _player_window(install)
    _inject(monkeypatch, outcome)
    with read_only(install / "saves"):  # (truly: POSIX permissions, a Windows deny-write entry)
        loaded = savegame.load_quick_snapshot(window)  # (a PermissionError used to escape from here)
    assert loaded is (outcome == "warning")
    assert sorted(p.name for p in legacy.parent.iterdir()) == ["quick.json"] and legacy.read_bytes() == kept
    if outcome == "failure":
        assert "[Mesh][Snapshot]" in capsys.readouterr().err, "the failure is still reported"


@pytest.mark.parametrize("outcome", ["warning", "failure"])
def test_a_player_s_own_quick_snapshot_keeps_its_diagnostics(tmp_path: Path, player: Path,
                                                             monkeypatch: pytest.MonkeyPatch, outcome: str) -> None:
    from engine import savegame

    install = _install(tmp_path / "game")
    monkeypatch.chdir(install)
    own = _snapshot(_saves(player) / "quick.json", 200)
    window = _player_window(install)
    _inject(monkeypatch, outcome)
    assert savegame.load_quick_snapshot(window) is (outcome == "warning")
    assert (own.parent / "quick.json.diagnostics.json").is_file(), "written beside the player's own snapshot"


def _malformed(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"version": 1, "game_state": ', encoding="utf-8")


def _schema_invalid(path: Path) -> None:
    payload = json.loads(_snapshot(path, 300).read_text(encoding="utf-8"))
    payload["game_state"] = "not an object"  # (valid JSON the save validator rejects)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(("own", "older", "gold"), [
    ("valid", "valid", 200),          # the player's own wins
    ("missing", "valid", 100),
    ("malformed", "valid", 100),      # a broken own copy: the older one, still valid
    ("schema-invalid", "valid", 100),
    ("valid", "malformed", 200),
    ("malformed", "schema-invalid", None),  # neither: it fails, nothing applied
    ("missing", "malformed", None),
])
def test_a_quick_snapshot_loads_the_first_valid_copy(tmp_path: Path, player: Path, monkeypatch: pytest.MonkeyPatch,
                                                     own: str, older: str, gold: int | None) -> None:
    from engine import savegame
    from tooling.installed_product_check import read_only

    install = _install(tmp_path / "game")
    monkeypatch.chdir(install)
    for state, path, value in ((own, _saves(player) / "quick.json", 200), (older, install / "saves" / "quick.json", 100)):
        if state == "valid":
            _snapshot(path, value)
        elif state == "malformed":
            _malformed(path)
        elif state == "schema-invalid":
            _schema_invalid(path)
    files = {p: p.read_bytes() for p in (_saves(player) / "quick.json", install / "saves" / "quick.json") if p.exists()}
    window = _player_window(install)
    applied: list[Any] = []
    original = savegame.save_payloads.apply_loaded_payload
    monkeypatch.setattr(savegame.save_payloads, "apply_loaded_payload",
                        lambda *a, **k: applied.append(1) or original(*a, **k))
    with read_only(install / "saves"):
        loaded = savegame.load_quick_snapshot(window)
    assert loaded is (gold is not None) and window.gold == (gold if gold is not None else 1)
    assert len(applied) == (1 if gold is not None else 0), "validated first: only the chosen copy is applied"
    assert {p: p.read_bytes() for p in files} == files, "neither copy is changed, repaired or replaced"
    assert sorted(p.name for p in (install / "saves").iterdir()) == ["quick.json"]
