import pytest
from unittest.mock import patch
from engine.inventory import ItemDatabase, ItemDefinition

from engine.config import EngineConfig
from engine.game_state_controller import GameStateController
from engine.inventory import get_or_create_inventory


class DummyWindow:
    def __init__(self) -> None:
        self.engine_config = EngineConfig()


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


def test_equip_weapon_adds_attack_bonus():
    window = DummyWindow()
    gs = GameStateController(window)
    inv = get_or_create_inventory(gs.state.values)
    inv.add_item("iron_sword", 1)

    base_attack = gs.get_player_stats()["attack"]
    result = gs.equip_item("iron_sword")
    assert result["ok"] is True
    assert gs.get_equipment()["weapon"] == "iron_sword"
    with_weapon = gs.get_player_stats()["attack"]
    assert with_weapon == pytest.approx(base_attack + 1.0)

    gs.unequip("weapon")
    assert gs.get_equipment()["weapon"] is None
    reset_attack = gs.get_player_stats()["attack"]
    assert reset_attack == pytest.approx(base_attack)


def test_equip_requires_ownership():
    window = DummyWindow()
    gs = GameStateController(window)
    result = gs.equip_item("iron_sword")
    assert result["ok"] is False
    assert result["reason"] == "not_owned"


def test_equipment_round_trips_in_state():
    window = DummyWindow()
    gs = GameStateController(window)
    inv = get_or_create_inventory(gs.state.values)
    inv.add_item("iron_sword", 1)
    gs.equip_item("iron_sword")

    snapshot = gs.export_state()
    new_window = DummyWindow()
    gs_loaded = GameStateController(new_window)
    gs_loaded.import_state(snapshot)
    assert gs_loaded.get_equipment().get("weapon") == "iron_sword"
    assert gs_loaded.get_player_stats()["attack"] >= gs.get_player_stats()["attack"]


def test_non_equippable_item_rejected():
    window = DummyWindow()
    gs = GameStateController(window)
    inv = get_or_create_inventory(gs.state.values)
    inv.add_item("healing_potion", 1)
    result = gs.equip_item("healing_potion", slot="weapon")
    assert result["ok"] is False
    assert result["reason"] == "not_equippable"
