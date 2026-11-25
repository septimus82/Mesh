"""#652 (owner decision D7), #655, #656, #657: what a new project needs to work, through the real entry points.

#652: no project Mesh made had ``assets/data/items.json``, and the item database raised without it, so in every new
game a pickup gave nothing, a shopkeeper's Vendor was never built and a defeated enemy's drop (and the gold in the same
entry) was lost for good. Every template now writes a small starter item list (never over one it has), and a missing
list is an empty one with one warning: every grant refuses an unknown item and takes nothing for it. A pickup the
inventory can't take (unknown, or a full stack) stays in the world; a drop grants its gold and says what it couldn't.

Each game here is made with ``mesh new``, its objects placed with ``mesh author apply``, and played through its own
``main.py`` in a hidden window, with keys sent to the window (as tests/test_project_root_resolver.py does).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.project_scaffold import ITEMS_FILE, STARTER_ITEMS, create_project
from engine.project_templates import list_templates
from tests._game_window_live import dispose_game_window

pytestmark = pytest.mark.integration  # (mesh new, exports and hidden game windows in temporary folders)

TEMPLATES = [t.id for t in list_templates()]
START = "packs/core_regions/scenes/start.json"
SIGN = "assets/sprites/starter_sign.png"
_WINDOW = pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
# The HD-2D starter builds its 3D village on load: the gpu lane's GL context, not the default run's.
_GL = pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                         reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)")


def _mesh(*argv: str) -> tuple[int, str]:
    from mesh_cli.main import main as mesh

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = mesh(list(argv))
    return code, out.getvalue()


def _new(tmp_path: Path, template: str) -> Path:
    assert _mesh("new", "game", "--template", template, "--dest", str(tmp_path))[0] == 0
    return tmp_path / "game"


def _author(root: Path) -> None:
    """Pickups, a shopkeeper and two enemies who drop a potion and 7 gold, beside the player (``mesh author apply``),
    where every 2D template's room is open ground (the row below the starter Guide, clear of the village's fence)."""
    start = json.loads((root / START).read_text(encoding="utf-8"))
    player = next(e for e in start["entities"] if e.get("prefab_id") == "player" or e.get("tag") == "player")
    px, py = float(player["x"]), float(player["y"])
    drops = [{"item_id": "healing_potion", "gold": 7}]
    objects = [
        ("Potion", (320, -32), [("PickupCollectible", {"item_id": "healing_potion", "item_amount": 1})]),
        ("Gem", (448, -32), [("PickupCollectible", {"item_id": "mystery_gem", "item_amount": 1})]),
        ("Merchant", (576, -32), [("Vendor", {"stock": [{"item_id": "healing_potion", "price": 5, "quantity": 3}]}),
                                  ("Interactable", {"interact_event": "open_shop"})]),
        ("Potion2", (64, -32), [("PickupCollectible", {"item_id": "healing_potion", "item_amount": 1})]),
        ("Wolf", (320, 64), [("Health", {}), ("DropTable", {"drops": drops})]),
        ("Wolf2", (448, 64), [("Health", {}), ("DropTable", {"drops": drops})]),
    ]
    changes: list[dict[str, Any]] = []
    for name, (dx, dy), setup in objects:
        ref = f"@{len(changes)}"
        changes += [{"op": "place_blank", "room": "start", "name": name, "x": px + dx, "y": py + dy},
                    {"op": "set_picture", "room": "start", "entity_id": ref, "sprite": SIGN}]
        for behaviour, params in setup:
            changes.append({"op": "add_behaviour", "room": "start", "entity_id": ref, "behaviour": behaviour})
            changes += [{"op": "set_behaviour_param", "room": "start", "entity_id": ref, "behaviour": behaviour,
                         "param": key, "value": value} for key, value in params.items()]
    plan = root.parent / "changes.json"
    plan.write_text(json.dumps(changes), encoding="utf-8")
    code, out = _mesh("author", "apply", str(plan), "--project", str(root))
    assert code == 0 and json.loads(out)["ok"], out


class _Game:
    """The running game, driven as a player: keys to the window, frames by on_update."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self.sc = window.scene_controller
        self.gs = window.game_state_controller
        window._allow_dispatch_event = True
        window.audio.set_master_volume(0.0)
        self.step(5)

    def step(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.window.dispatch_event("on_update", 1 / 60)

    def press(self, key: int) -> None:
        self.window.dispatch_event("on_key_press", key, 0)
        self.step(1)
        self.window.dispatch_event("on_key_release", key, 0)
        self.step(3)

    def named(self, name: str) -> Any:
        return next((s for s in self.sc.all_sprites if getattr(s, "mesh_name", "") == name), None)

    def behaviour(self, name: str, kind: str) -> Any:
        sprite = self.named(name)
        return next((b for b in (sprite.mesh_behaviours_runtime if sprite else []) if type(b).__name__ == kind), None)

    def use(self, name: str) -> None:
        """Walk up to ``name`` from just left of it and press E."""
        target, hero = self.named(name), self.sc._find_player_sprite()
        hero.center_x, hero.center_y = target.center_x - 52, target.center_y
        self.step(2)
        right = optional_arcade.arcade.key.RIGHT
        self.window.dispatch_event("on_key_press", right, 0)
        self.step(6)
        self.window.dispatch_event("on_key_release", right, 0)
        self.step(2)
        self.press(optional_arcade.arcade.key.E)

    def defeat(self, name: str) -> None:
        self.behaviour(name, "Health").apply_damage(99.0, source_entity="player")
        self.step(10)

    def count(self, item: str = "healing_potion") -> int:
        from engine.inventory import get_or_create_inventory

        return get_or_create_inventory(self.gs.state.values).get_count(item)

    def toasts(self) -> list[str]:
        return list(self.window.player_hud.active_toasts())


def _play(root: Path, monkeypatch: pytest.MonkeyPatch, drive: Callable[[_Game], None]) -> None:
    """Run the game's own ``main.py`` (it changes into its folder; the test's folder comes back), ``drive`` in place
    of the window's run loop."""
    import engine.dpi_bootstrap
    from engine.game import GameWindow

    monkeypatch.chdir(root.parent)
    # (process-wide and once only: it would rescale every later window of the test run)
    monkeypatch.setattr(engine.dpi_bootstrap, "set_process_dpi_unaware", lambda: None)
    failures: list[BaseException] = []

    def run(window: Any) -> None:
        try:
            drive(_Game(window))
        except BaseException as exc:  # (re-raised below, after the window is gone)
            failures.append(exc)
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", run)
    runpy.run_path(str(root / "main.py"), run_name="__main__")
    if failures:
        raise failures[0]


# ------------------------------------------------------------------------------------------------ the scaffold
@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_writes_the_starter_items_and_a_room_that_loads(tmp_path: Path, template: str) -> None:
    """#652 and #656: ``mesh new`` with every template writes the starter list in the engine's format, and its start
    room passes the game's own scene loader (two templates wrote a format the game refused)."""
    from engine.inventory import ItemDatabase
    from engine.scene_loader import SceneLoader

    root = _new(tmp_path, template)
    assert json.loads((root / ITEMS_FILE).read_text(encoding="utf-8")) == {"items": STARTER_ITEMS}
    items = ItemDatabase.load(root).items
    assert items["healing_potion"].stackable and items["healing_potion"].max_stack == 10
    assert not items["rusty_sword"].stackable and "weapon" in items["rusty_sword"].tags
    report = SceneLoader().validate_scene_file(str(root / START))
    assert not report.errors, report.errors


def test_studio_s_create_project_writes_it_and_never_replaces_a_template_s_own(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """The launcher and Studio make projects with ``create_project`` (as ``mesh new`` does); a list a template wrote
    itself is kept."""
    import engine.project_templates as templates

    create_project(tmp_path / "studio", "Studio", template_id="adventure")
    assert json.loads((tmp_path / "studio" / ITEMS_FILE).read_text(encoding="utf-8")) == {"items": STARTER_ITEMS}
    own = {"items": [{"id": "relic", "name": "Relic"}]}
    real = templates.apply_template

    def with_own_items(root: Path, template_id: str) -> None:
        real(root, template_id)
        (root / ITEMS_FILE).write_text(json.dumps(own), encoding="utf-8")

    monkeypatch.setattr(templates, "apply_template", with_own_items)
    create_project(tmp_path / "own", "Own", template_id="blank")
    assert json.loads((tmp_path / "own" / ITEMS_FILE).read_text(encoding="utf-8")) == own


def test_a_retired_template_is_refused_not_turned_into_another(tmp_path: Path) -> None:
    """#656: demo_slice wrote a room the game couldn't start; it is retired, and asking for it makes nothing."""
    code, _ = _mesh("new", "game", "--template", "demo_slice", "--dest", str(tmp_path))
    assert code == 1 and not (tmp_path / "game").exists()


# ---------------------------------------------------------------------------------- items in the running game
@_WINDOW
@pytest.mark.parametrize("template", [pytest.param(t, marks=_GL) if t == "hd2d_rpg" else t for t in TEMPLATES])
def test_pickups_shops_and_drops_work_in_every_new_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         template: str) -> None:
    """Every template's game (which also proves it starts, #656): a potion pickup, a purchase, an enemy's drop; then
    a full stack: the next potion stays where it is, and an enemy's potion is refused out loud, its gold still paid."""
    root = _new(tmp_path, template)
    _author(root)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        game.use("Potion")
        seen["pickup"] = (game.count(), game.named("Potion") is None)
        game.use("Gem")  # (an id the list doesn't have)
        seen["unknown"] = (game.count("mystery_gem"), game.named("Gem") is not None)
        seen["vendor"] = game.behaviour("Merchant", "Vendor") is not None
        game.use("Merchant")
        panel = game.window.ui_controller.shop_panel
        seen["shop_open"] = bool(panel.visible)
        game.gs.set_counter("gold", 50)
        game.press(optional_arcade.arcade.key.ENTER)
        seen["purchase"] = (game.gs.get_counter("gold", 0), game.count())
        panel.close()
        game.step(2)
        game.gs.set_counter("gold", 0)
        game.defeat("Wolf")
        seen["drop"] = (game.count(), game.gs.get_counter("gold", 0))
        from engine.inventory import get_or_create_inventory

        get_or_create_inventory(game.gs.state.values).add_item("healing_potion", 10)  # (the stack is full: 10)
        game.use("Potion2")
        seen["full_pickup"] = (game.count(), game.named("Potion2") is not None, game.toasts())
        game.defeat("Wolf2")
        seen["full_drop"] = (game.count(), game.gs.get_counter("gold", 0), game.toasts())

    _play(root, monkeypatch, drive)
    assert seen["pickup"] == (1, True)
    assert seen["unknown"] == (0, True), "an unknown item stays in the world"
    assert seen["vendor"] and seen["shop_open"]
    assert seen["purchase"] == (45, 2)
    assert seen["drop"] == (3, 7)
    count, still_there, toasts = seen["full_pickup"]
    assert (count, still_there) == (10, True) and "Can't carry any more Healing Potion" in toasts
    assert seen["full_drop"][:2] == (10, 14), "the drop's gold arrives though its potion can't"
    assert seen["full_drop"][2].count("Can't carry any more Healing Potion") == 2, "the drop says so too"


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@_WINDOW
def test_a_game_without_an_item_list_degrades_and_keeps_the_gold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An older project (or one whose list was deleted): one warning, nothing raises, the pickup stays, the Vendor is
    built and charges nothing for an item it can't give, and the defeated enemy's gold arrives."""
    root = _new(tmp_path, "starter")
    _author(root)
    (root / ITEMS_FILE).unlink()
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        game.use("Potion")
        seen["pickup"] = (game.count(), game.named("Potion") is not None, game.toasts())
        seen["vendor"] = game.behaviour("Merchant", "Vendor") is not None
        game.use("Merchant")
        game.gs.set_counter("gold", 50)
        game.press(optional_arcade.arcade.key.ENTER)
        seen["purchase"] = (game.gs.get_counter("gold", 0), game.count())
        game.window.ui_controller.shop_panel.close()
        game.step(2)
        game.gs.set_counter("gold", 0)
        game.defeat("Wolf")
        seen["drop"] = (game.count(), game.gs.get_counter("gold", 0), game.named("Wolf") is None)

    # The item database's warning, and where the failures went before: the event bus's "ERROR delivering 'died' to
    # DropTable" and the interaction's "PickupCollectible failed" (engine loggers don't propagate: caplog can't see).
    records = _Records()
    loggers = [logging.getLogger(name) for name in ("engine.inventory", "engine.events", "engine.interaction")]
    for logger in loggers:
        logger.addHandler(records)
    try:
        _play(root, monkeypatch, drive)
    finally:
        for logger in loggers:
            logger.removeHandler(records)
    assert seen["pickup"][:2] == (0, True)
    assert any("Unknown item 'healing_potion'" in toast for toast in seen["pickup"][2])
    assert seen["vendor"] and seen["purchase"] == (50, 0)
    assert seen["drop"] == (0, 7, True)
    messages = [(r.name, r.levelno, r.getMessage()) for r in records.records]
    missing = [m for m in messages if "Item database not found" in m[2]]
    assert len(missing) == 1 and missing[0][:2] == ("engine.inventory", logging.WARNING), messages
    assert len(messages) == 1, messages


def test_a_missing_item_list_is_empty_and_read_once_it_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import inventory

    monkeypatch.delenv("MESH_REPO_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)  # (the game project: a folder with no item list)
    assert inventory.load_item_database().items == {}
    assert inventory.Inventory({}).add_item("healing_potion") is False
    (tmp_path / "assets" / "data").mkdir(parents=True)
    (tmp_path / ITEMS_FILE).write_text(json.dumps({"items": STARTER_ITEMS}), encoding="utf-8")
    assert inventory.Inventory({}).add_item("healing_potion") is True  # (the empty answer wasn't cached)


# --------------------------------------------------------------------------------------------------- export
PROBE = r'''
import json, sys
sys.path.insert(0, ".")
import engine
from engine.inventory import Inventory
inventory = Inventory({})
print("MESH-ITEMS " + json.dumps({"engine": engine.__file__, "added": inventory.add_item("healing_potion", 3),
                                  "count": inventory.get_count("healing_potion")}))
'''


def test_an_exported_game_ships_its_items_and_uses_them(tmp_path: Path) -> None:
    from engine.tooling.export_bundle import build_bundle

    root = _new(tmp_path, "starter")
    bundle = tmp_path / "bundle"
    assert build_bundle(root, bundle, deterministic=True)[0] == 0
    listed = {f["path"] for f in json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))["files"]}
    assert ITEMS_FILE in listed
    env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_") and k != "PYTHONPATH"}
    out = subprocess.run([sys.executable, "-I", "-c", PROBE], cwd=bundle, capture_output=True, text=True,
                         timeout=120, env=env)
    line = next((t for t in out.stdout.splitlines() if t.startswith("MESH-ITEMS ")), None)
    assert out.returncode == 0 and line is not None, out.stdout + out.stderr
    played = json.loads(line[len("MESH-ITEMS "):])
    assert Path(played["engine"]).resolve().is_relative_to(bundle.resolve())  # (the game's own engine)
    assert (played["added"], played["count"]) == (True, 3)


# ---------------------------------------------------------------------------------------- #655 and #657
def _quests(root: Path) -> set[str]:
    """The quests the game's own quest manager loads from the project."""
    from engine.quests import QuestManager

    window = MagicMock()
    window.game_state.values = {}
    window.get_flag.return_value = False
    manager = QuestManager(window, data_path=str(root / "assets/data/quests.json"))
    return {quest.id for quest in manager.get_all_quests()}


def test_a_new_project_gets_its_first_quest_from_mcp_and_from_mesh_new_quest(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """#655: MCP add_quest_definition needed an existing quests.json; ``mesh new-quest`` crashed without --target and
    wrote a bare list (which the game ignores) with it. Both now make the list the game loads."""
    from engine.mcp_server import tools

    root = _new(tmp_path, "starter")
    monkeypatch.chdir(root)  # (as a creator runs mesh new-quest; the quest manager reads this project's packs too)
    assert not (root / "assets/data/quests.json").exists()
    quest = {"title": "The Vault", "stages": [{"id": "find", "title": "Find the vault"}]}
    result = tools.apply_ops([{"type": "add_quest_definition", "quest_id": "vault_quest", "quest": quest}],
                             root=str(root), validate=False)
    assert result["ok"], result
    assert _quests(root) == {"vault_quest"}

    assert _mesh("new-quest", "Find The Cat")[0] == 0
    assert _quests(root) == {"vault_quest", "find_the_cat"}

    other = _new(tmp_path / "other", "blank")  # mesh new-quest first, then MCP
    monkeypatch.chdir(other)
    assert _mesh("new-quest", "First")[0] == 0
    result = tools.apply_ops([{"type": "add_quest_definition", "quest_id": "second", "quest": quest}],
                             root=str(other), validate=False)
    assert result["ok"], result
    assert _quests(other) == {"first", "second"}


def test_mesh_new_quest_moves_an_older_bare_list_into_the_loaded_form(tmp_path: Path) -> None:
    from engine.tooling import scaffold

    quests = tmp_path / "quests.json"
    quests.write_text(json.dumps([{"id": "old", "title": "Old", "stages": [{"id": "a"}]}]), encoding="utf-8")
    assert scaffold.create_quest("New One", quests)
    assert [q["id"] for q in json.loads(quests.read_text(encoding="utf-8"))["quests"]] == ["old", "new_one"]


def test_mcp_list_scenes_names_a_new_project_s_rooms(tmp_path: Path) -> None:
    """#657: list_scenes looked in scenes/ only, so a ``mesh new`` project (rooms in packs/) listed nothing."""
    from engine.mcp_server import tools

    root = _new(tmp_path, "adventure")
    scenes = tools.list_scenes(str(root))
    assert scenes[0] == START and len(scenes) == 2 and all((root / s).is_file() for s in scenes)
