"""#654 (owner decision D2): Studio's "Shopkeeper" (Vendor) opens on E; on an object that also talks, the shop opens
once the conversation E started completes.

Vendor used to open only on an ``open_shop`` event that nothing Studio authors sends, so E on a Shopkeeper did nothing
and a talking Shopkeeper never sold anything. The working route (a second "React when the player presses E" sending
``open_shop``) opened the shop together with the conversation on one E (#663 item 2).

A generated project (``mesh new``) authored through Mesh Studio's project model and ops (the picker's "Shopkeeper",
"Talk" and "React when the player presses E", the inspector's settings), played through its own ``main.py`` in a real
hidden window with the interact key sent to it. The shipped merchants are played in this checkout the same way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window
from tests.test_project_scaffolding_data import START, _Game, _new, _play

pytestmark = [pytest.mark.integration,  # (generated projects in temporary folders; hidden game windows)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

SIGN = "assets/sprites/starter_sign.png"
GUIDE = "start_guide_320_128_0_0"  # (the starter template's talking Guide: a Person)
POTIONS = [{"item_id": "healing_potion", "price": 5, "quantity": 3}]
SWORD = [{"item_id": "rusty_sword", "price": 10, "quantity": 1}]
REPO = Path(__file__).resolve().parents[1]


def _key(name: str) -> int:
    return int(getattr(optional_arcade.arcade.key, name))


def _author(root: Path, *, once: bool = False, event_only: bool = False) -> None:
    """The starter Guide (a Person who talks) becomes a Shopkeeper too; beside the player: a Shopkeeper selling
    potions, one selling a sword (shop id "smithy"), and a Trader who talks, sells, and has the old workaround (a
    "React when the player presses E" sending ``open_shop``). ``event_only``: the Guide is set to ``open_on: "event"``,
    and a Counter (a Shopkeeper who doesn't talk, shop id "counter") likewise."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.studio_project import Project

    start = json.loads((root / START).read_text(encoding="utf-8"))
    player = next(e for e in start["entities"] if e.get("prefab_id") == "player" or e.get("tag") == "player")
    px, py = float(player["x"]), float(player["y"])
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)

        def edit(change: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
            project.edit_scene(change)

        def place(name: str, dx: float, dy: float) -> str:
            made: dict[str, str] = {}

            def put(scene: dict[str, Any]) -> dict[str, Any]:
                scene, made["id"] = ops.place_blank(scene, project.current, name, px + dx, py + dy)
                return scene

            edit(put)
            edit(lambda s: ops.set_picture(s, made["id"], SIGN))
            return made["id"]

        def shopkeeper(ident: str, stock: list[dict[str, Any]], **settings: Any) -> None:
            edit(lambda s: ops.add_behaviour(s, ident, "Vendor"))
            edit(lambda s: ops.set_behaviour_param(s, ident, "Vendor", "stock", stock))
            for name, value in settings.items():
                edit(lambda s, n=name, v=value: ops.set_behaviour_param(s, ident, "Vendor", n, v))

        shopkeeper(GUIDE, POTIONS, **({"open_on": "event"} if event_only else {}))
        if event_only:
            shopkeeper(place("Counter", 192, 96), SWORD, shop_id="counter", open_on="event")
        if once:
            edit(lambda s: ops.set_behaviour_param(s, GUIDE, "Dialogue", "once", True))  # "Only once"
        shopkeeper(place("Shopkeeper", 320, -32), POTIONS)
        shopkeeper(place("Smith", 448, -32), SWORD, shop_id="smithy")
        trader = place("Trader", 576, -32)
        edit(lambda s: ops.add_behaviour(s, trader, "Dialogue"))
        edit(lambda s: ops.set_dialogue_text(s, trader, "Fine wares, friend."))
        shopkeeper(trader, POTIONS)
        edit(lambda s: ops.add_behaviour(s, trader, "Interactable"))
        edit(lambda s: ops.set_behaviour_param(s, trader, "Interactable", "interact_event", "open_shop"))
        project.save(owner=held)


class _Shop:
    """The shop panel, and every time something opened a shop."""

    def __init__(self, window: Any) -> None:
        self.ui = window.ui_controller
        self.opens: list[Any] = []
        real = self.ui.open_shop

        def counted(vendor: Any, items: list[dict[str, Any]]) -> None:
            self.opens.append(vendor)
            real(vendor, items)

        self.ui.open_shop = counted

    @property
    def vendor(self) -> Any:
        panel = self.ui.shop_panel
        return panel.vendor if panel.visible else None

    def stock(self) -> list[str]:
        return [str(entry.get("item_id")) for entry in (self.vendor.stock if self.vendor else [])]

    def close(self) -> None:
        self.ui.shop_panel.close()


def _talking(game: _Game) -> bool:
    box = game.window.ui_controller.dialogue_box
    return bool(box is not None and box.is_active())


def test_e_opens_each_shopkeeper_s_own_stock_and_a_purchase_works(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    root = _new(tmp_path, "starter")
    _author(root)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        shop = _Shop(game.window)
        game.use("Shopkeeper")
        seen["shopkeeper"] = (shop.vendor is game.behaviour("Shopkeeper", "Vendor"), shop.stock())
        game.gs.set_counter("gold", 50)
        game.press(_key("ENTER"))
        seen["purchase"] = (game.gs.get_counter("gold", 0), game.count())
        shop.close()
        game.step(2)
        game.use("Smith")
        seen["smith"] = (shop.vendor is game.behaviour("Smith", "Vendor"), shop.stock())
        seen["opens"] = len(shop.opens)

    _play(root, monkeypatch, drive)
    assert seen["shopkeeper"] == (True, ["healing_potion"]), "E on a Studio-authored Shopkeeper opens its shop"
    assert seen["purchase"] == (45, 1), "gold paid, potion carried"
    assert seen["smith"] == (True, ["rusty_sword"]), "the other shopkeeper in the room opens its own stock"
    assert seen["opens"] == 2


def test_a_talking_shopkeeper_talks_first_and_opens_its_shop_once_the_talk_completes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D2: E starts the conversation, not the shop; finishing it opens the shop exactly once. The Trader also has the
    old workaround (its own "React when the player presses E" sends ``open_shop`` on the same E): still one shop, after
    the conversation (#663 item 2)."""
    root = _new(tmp_path, "starter")
    _author(root)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        shop = _Shop(game.window)
        for name in ("Guide", "Trader"):
            game.use(name)
            game.step(10)
            seen[f"{name} first E"] = (_talking(game), shop.vendor is not None)
            game.press(_key("E"))  # (the only line: the conversation ends)
            game.step(10)
            seen[f"{name} talk done"] = (_talking(game), shop.vendor is game.behaviour(name, "Vendor"), len(shop.opens))
            shop.close()
            shop.opens.clear()
            game.step(2)

    _play(root, monkeypatch, drive)
    for name in ("Guide", "Trader"):
        assert seen[f"{name} first E"] == (True, False), f"{name}: E opens the conversation, not the shop"
        assert seen[f"{name} talk done"] == (False, True, 1), f"{name}: the shop opens once the conversation ends"


def test_a_spent_only_once_talk_lets_e_open_the_shop_and_the_event_route_still_works(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _new(tmp_path, "starter")
    _author(root, once=True)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        shop = _Shop(game.window)
        game.use("Guide")
        game.press(_key("E"))
        game.step(10)
        seen["first talk"] = shop.vendor is game.behaviour("Guide", "Vendor")
        shop.close()
        game.step(2)
        game.use("Guide")  # (it has nothing more to say)
        seen["spent"] = (_talking(game), shop.vendor is game.behaviour("Guide", "Vendor"))
        shop.close()
        game.step(2)
        game.window.emit_signal("open_shop", shop_id="smithy")  # (what a choice or another object sends)
        game.step(2)
        seen["event"] = (shop.vendor is game.behaviour("Smith", "Vendor"), shop.stock())

    _play(root, monkeypatch, drive)
    assert seen["first talk"], "the conversation, then the shop"
    assert seen["spent"] == (False, True), "an \"Only once\" talk already had: E opens the shop straight away"
    assert seen["event"] == (True, ["rusty_sword"]), "open_shop naming a shop id opens that shop"


def test_a_conversation_closed_before_it_completes_opens_no_shop(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """D2 is "after the conversation completes": one cut off (here the way loading a save closes the conversation
    box) opens nothing. The next one, finished, does."""
    root = _new(tmp_path, "starter")
    _author(root)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        shop = _Shop(game.window)
        game.use("Guide")
        seen["talking"] = _talking(game)
        game.window.ui_controller.reset_transient_state()  # (engine/save_runtime/payloads.py on a load)
        game.step(10)
        seen["cut off"] = (_talking(game), shop.vendor is not None, len(shop.opens))
        game.use("Guide")
        game.press(_key("E"))
        game.step(10)
        seen["finished"] = (shop.vendor is game.behaviour("Guide", "Vendor"), len(shop.opens))

    _play(root, monkeypatch, drive)
    assert seen["talking"], "E started the conversation"
    assert seen["cut off"] == (False, False, 0), "a conversation that didn't complete opens no shop"
    assert seen["finished"] == (True, 1)


def test_open_on_event_leaves_e_alone_and_the_event_opens_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``open_on: "event"`` (the choice-driven option): E on a Shopkeeper who doesn't talk opens nothing, nor does
    finishing a conversation or E once an "Only once" conversation is spent; ``open_shop`` still opens it."""
    root = _new(tmp_path, "starter")
    _author(root, once=True, event_only=True)
    seen: dict[str, Any] = {}

    def drive(game: _Game) -> None:
        shop = _Shop(game.window)
        game.use("Counter")
        seen["counter E"] = (shop.vendor is not None, len(shop.opens))
        game.use("Guide")
        seen["talking"] = _talking(game)
        game.press(_key("E"))  # (its only line: the conversation completes)
        game.step(10)
        seen["talk done"] = (shop.vendor is not None, len(shop.opens))
        game.use("Guide")  # (it has nothing more to say)
        seen["spent E"] = (_talking(game), shop.vendor is not None, len(shop.opens))
        game.window.emit_signal("open_shop", shop_id="counter")
        game.step(2)
        seen["event"] = (shop.vendor is game.behaviour("Counter", "Vendor"), len(shop.opens))

    _play(root, monkeypatch, drive)
    assert seen["counter E"] == (False, 0), "E doesn't open an open_on: event shop"
    assert seen["talking"], "E still talks"
    assert seen["talk done"] == (False, 0), "nor does the end of the conversation"
    assert seen["spent E"] == (False, False, 0), "nor E once the conversation is spent"
    assert seen["event"] == (True, 1), "open_shop opens it"


def test_the_shipped_merchants_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ashen's and Hollow Grove's merchants (Dialogue with nothing to say + Vendor) open on E; the showcase merchant
    (whose stock was under a key Vendor doesn't read) after its talk; Ridge's and the door interior's on their
    conversation's trade choice only (``open_on: "event"``), not after its other choice."""
    from engine.game import GameWindow
    from engine.interaction import perform_interaction
    from engine.public_api import run_game

    monkeypatch.delenv("MESH_REPO_ROOT", raising=False)
    monkeypatch.chdir(REPO)
    seen: dict[str, Any] = {}

    def play(window: Any) -> None:
        try:
            game = _Game(window)

            def enter(path: str) -> _Shop:
                window.load_scene(path)
                menu = getattr(window, "main_menu_overlay", None)
                if menu is not None and menu.visible:
                    menu.close()
                game.step(3)
                return _Shop(window)

            for path, merchant in (("packs/core_regions/scenes/Ashen_hub.json", "Ashen_Merchant"),
                                   ("packs/core_regions/scenes/Hollow Grove_hub.json", "Hollow Grove_Merchant")):
                shop = enter(path)
                game.use(merchant)
                seen[merchant] = (shop.vendor is game.behaviour(merchant, "Vendor"), shop.stock())
            # The showcase interior has no player of its own (one walks in through its door): the interact key's
            # interaction, by someone standing beside the merchant, through its four lines.
            shop = enter("scenes/showcase_interior.json")
            merchant = game.named("Showcase Merchant")
            visitor = optional_arcade.arcade.Sprite()
            visitor.center_x, visitor.center_y = merchant.center_x, merchant.center_y - 20
            for _ in range(6):
                if shop.vendor is not None:
                    break
                perform_interaction(window, actor=visitor)
                game.step(5)
            seen["Showcase Merchant"] = (shop.vendor is game.behaviour("Showcase Merchant", "Vendor"), shop.stock())
            for path, merchant, trade, other in (
                    ("packs/core_regions/scenes/Ridge Outpost_hub.json", "RidgeMerchant", ("DOWN", "DOWN"), ("DOWN",)),
                    ("scenes/door_interior.json", "Merchant", ("DOWN", "UP"), ("DOWN",))):
                for keys, label in ((other, "other choice"), (trade, "trade choice")):
                    shop = enter(path)  # (afresh: the door interior's merchant talks only once)
                    if merchant == "RidgeMerchant":
                        game.use(merchant)
                    else:  # the door interior's merchant has no picture, so E can't reach it: its conversation directly
                        game.behaviour(merchant, "Dialogue").on_interact(window, game.sc._find_player_sprite())
                        game.step(2)
                    for key in (*keys, "E"):
                        game.press(_key(key))
                    game.step(10)
                    seen[f"{merchant} {label}"] = (shop.vendor is game.behaviour(merchant, "Vendor"), len(shop.opens))
                    shop.close()
                    game.step(5)
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", play)
    run_game("packs/core_regions/scenes/Ashen_hub.json", project_root=REPO)
    assert seen["Ashen_Merchant"] == (True, ["iron_sword", "chain_coif", "healing_potion"])
    assert seen["Hollow Grove_Merchant"][0] and len(seen["Hollow Grove_Merchant"][1]) == 5
    assert seen["Showcase Merchant"] == (True, ["healing_potion", "rusty_sword"])
    for merchant in ("RidgeMerchant", "Merchant"):
        assert seen[f"{merchant} other choice"] == (False, 0), f"{merchant}: only the trade choice opens the shop"
        assert seen[f"{merchant} trade choice"] == (True, 1), f"{merchant}: the trade choice opens it, once"
