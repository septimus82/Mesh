from unittest.mock import patch

import arcade
import pytest

from engine.behaviours.drop_table import DropTable
from engine.events import MeshEventBus
from engine.game_state_controller import GameStateController
from engine.inventory import ItemDatabase, ItemDefinition, get_or_create_inventory


class DummyWindow:
    def __init__(self):
        from engine.config import EngineConfig

        cfg = EngineConfig()
        self.engine_config = cfg
        self.width = cfg.width
        self.height = cfg.height
        self.event_bus = MeshEventBus()
        self.game_state_controller = GameStateController(self)
        self._logs: list[str] = []

    def console_log(self, message: str) -> None:
        self._logs.append(message)

    def show_notification(self, text: str, duration: float = 2.0) -> None:
        self._logs.append(text)


class DummySprite(arcade.Sprite):
    def __init__(self, name: str = "dummy"):
        super().__init__()
        self.mesh_name = name
        self.mesh_tag = "enemy"


def test_drop_table_awards_item_and_gold():
    window = DummyWindow()
    entity = DummySprite()
    behaviour = DropTable(
        entity,
        window,
        listen_event="died",
        drops=[
            {"item_id": "iron_sword", "chance": 1.0, "min_quantity": 1, "max_quantity": 1},
            {"gold": 25, "chance": 1.0},
        ],
    )
    window.event_bus.emit("died", actor=entity)
    inv = get_or_create_inventory(window.game_state_controller.state.values)
    assert inv.get_count("iron_sword") == 1
    assert window.game_state_controller.get_counter("gold") == 25
    assert any("Loot" in line for line in window._logs)


def test_drop_table_respects_chance_and_seed():
    window = DummyWindow()
    entity = DummySprite("seeded")
    behaviour = DropTable(
        entity,
        window,
        listen_event="died",
        seed=1,
        drops=[{"item_id": "healing_potion", "chance": 0.2, "min_quantity": 2, "max_quantity": 4}],
    )
    window.event_bus.emit("died", actor=entity)
    inv = get_or_create_inventory(window.game_state_controller.state.values)
    # With seed=1, roll succeeds and quantity resolves deterministically to 2
    assert inv.get_count("healing_potion") == 2


def test_drop_table_ignores_unrelated_actor():
    window = DummyWindow()
    entity = DummySprite("owner")
    other = DummySprite("other")
    behaviour = DropTable(
        entity,
        window,
        listen_event="died",
        drops=[{"item_id": "iron_sword", "chance": 1.0}],
    )
    window.event_bus.emit("died", actor=other)
    inv = get_or_create_inventory(window.game_state_controller.state.values)
    assert inv.get_count("iron_sword") == 0


@pytest.fixture(autouse=True)
def mock_item_db():
    # Reset cache
    import engine.inventory
    engine.inventory._ITEM_DB_CACHE = None

    with patch("engine.inventory.ItemDatabase.load") as mock_load:
        db = ItemDatabase({
            "iron_sword": ItemDefinition(
                id="iron_sword", name="Iron Sword", description="desc", icon=None,
                stackable=False, max_stack=1, tags=["equipment", "weapon"], effects={"damage_bonus": 1.0}
            ),
            "healing_potion": ItemDefinition(
                id="healing_potion", name="Healing Potion", description="desc", icon=None,
                stackable=True, max_stack=10, tags=["consumable"], effects={"heal": 2.0}
            )
        })
        mock_load.return_value = db
        yield

    engine.inventory._ITEM_DB_CACHE = None
