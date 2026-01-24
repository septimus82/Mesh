import types

from engine.behaviours.vendor import Vendor
from engine.events import MeshEventBus
from engine.game_state_controller import GameStateController
from engine.ui import ShopPanel


class StubItemDef:
    def __init__(self, item_id, name):
        self.id = item_id
        self.name = name
        self.description = ""
        self.icon = None
        self.stackable = False
        self.max_stack = 1
        self.tags = []
        self.effects = {}


class StubItemDB:
    def __init__(self):
        self._map = {"potion": StubItemDef("potion", "Potion")}

    def get(self, item_id):
        return self._map.get(item_id)


class StubAudio:
    def __init__(self):
        self.played = []

    def play_sound(self, path: str):
        self.played.append(path)


class StubWindow:
    def __init__(self):
        self.event_bus = MeshEventBus()
        self.game_state_controller = GameStateController(self)
        self.ui_controller = types.SimpleNamespace(open_shop=lambda vendor, items: None)
        self.audio = StubAudio()


def test_vendor_buy_success(monkeypatch):
    window = StubWindow()
    # seed currency
    window.game_state_controller.set_counter("gold", 100)
    # patch item db
    monkeypatch.setattr("engine.behaviours.vendor.load_item_database", lambda: StubItemDB())
    monkeypatch.setattr("engine.inventory.load_item_database", lambda root=None: StubItemDB())
    vendor = Vendor(
        entity=types.SimpleNamespace(mesh_name="Shopkeep"),
        window=window,
        stock=[{"item_id": "potion", "price": 50, "quantity": 2}],
    )
    item = vendor.stock[0]
    result = vendor.handle_buy_request(item)
    assert result.ok is True
    # Note: Case sensitivity may vary depending on item DB stub format
    assert result.message.lower() == "bought potion x1 (-50g)"
    assert window.game_state_controller.get_counter("gold") == 50
    inv = window.game_state_controller.state.values["inventory"]["items"]
    assert inv.get("potion") == 1
    assert item["quantity"] == 1


def test_vendor_buy_fail_insufficient(monkeypatch):
    window = StubWindow()
    window.game_state_controller.set_counter("gold", 10)
    monkeypatch.setattr("engine.behaviours.vendor.load_item_database", lambda: StubItemDB())
    monkeypatch.setattr("engine.inventory.load_item_database", lambda root=None: StubItemDB())
    vendor = Vendor(
        entity=types.SimpleNamespace(mesh_name="Shopkeep"),
        window=window,
        stock=[{"item_id": "potion", "price": 50, "quantity": 1}],
        fail_sound="fail.wav",
    )
    result = vendor.handle_buy_request(vendor.stock[0])
    assert result.ok is False
    assert result.message == "Not enough gold"
    # currency unchanged
    assert window.game_state_controller.get_counter("gold") == 10
    assert not window.audio.played or window.audio.played[-1] == "fail.wav"


def test_vendor_sell_success(monkeypatch):
    window = StubWindow()
    monkeypatch.setattr("engine.behaviours.vendor.load_item_database", lambda: StubItemDB())
    monkeypatch.setattr("engine.inventory.load_item_database", lambda root=None: StubItemDB())
    vendor = Vendor(
        entity=types.SimpleNamespace(mesh_name="Shopkeep"),
        window=window,
        stock=[{"item_id": "potion", "price": 50, "quantity": 2}],
    )
    inv = window.game_state_controller.state.values.setdefault("inventory", {}).setdefault("items", {})
    inv["potion"] = 2
    result = vendor.handle_sell_request({"item_id": "potion"})
    assert result.ok is True
    assert result.message.lower() == "sold potion x1 (+25g)"
    assert window.game_state_controller.get_counter("gold") == 25  # 50 * 0.5 sell_rate
    assert inv.get("potion") == 1


def test_vendor_sell_filtered(monkeypatch):
    window = StubWindow()
    monkeypatch.setattr("engine.behaviours.vendor.load_item_database", lambda: StubItemDB())
    monkeypatch.setattr("engine.inventory.load_item_database", lambda root=None: StubItemDB())
    vendor = Vendor(
        entity=types.SimpleNamespace(mesh_name="Shopkeep"),
        window=window,
        stock=[{"item_id": "potion", "price": 50, "quantity": 2}],
        sell_blacklist=["potion"],
    )
    inv = window.game_state_controller.state.values.setdefault("inventory", {}).setdefault("items", {})
    inv["potion"] = 1
    result = vendor.handle_sell_request({"item_id": "potion"})
    assert result.ok is False
    assert result.message == "Cannot sell that item"
    # no payout
    assert window.game_state_controller.get_counter("gold") == 0


def test_shop_panel_cursor_and_confirm():
    window = types.SimpleNamespace(
        width=800,
        height=600,
        game_state_controller=None,
    )
    panel = ShopPanel(window)  # type: ignore[arg-type]
    called = []

    class StubVendor:
        def handle_buy_request(self, item):
            called.append(item["item_id"])

    vendor = StubVendor()
    items = [{"item_id": "a"}, {"item_id": "b"}]
    panel.open(vendor, items)
    panel.move_cursor(1)
    panel.confirm_purchase()
    assert called == ["b"]


def test_shop_panel_sell_mode_calls_vendor(monkeypatch):
    window = types.SimpleNamespace(
        width=800,
        height=600,
        game_state_controller=None,
    )
    panel = ShopPanel(window)  # type: ignore[arg-type]
    called = []

    class StubVendor:
        def handle_sell_request(self, item):
            called.append(item["item_id"])

        def get_sellable_items(self, values):
            return [{"item_id": "c"}]

    vendor = StubVendor()
    panel.open(vendor, [], mode="sell")
    panel.set_mode("sell")
    panel.confirm_purchase()
    assert called == ["c"]


def test_shop_panel_enqueues_toast_from_vendor_result():
    window = types.SimpleNamespace(
        width=800,
        height=600,
        game_state_controller=None,
    )
    received: list[str] = []

    class StubHUD:
        def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
            received.append(message)

    class StubVendor:
        def handle_buy_request(self, item):
            assert item["item_id"] == "a"
            return {"ok": True, "message": "Bought A x1 (-1g)"}

    window.player_hud = StubHUD()
    panel = ShopPanel(window)  # type: ignore[arg-type]
    panel.open(StubVendor(), [{"item_id": "a"}])
    panel.confirm_purchase()
    assert received == ["Bought A x1 (-1g)"]
