import json

import pytest
import engine.inventory as inventory_module
from engine.inventory import Inventory, ItemDatabase, ItemDefinition, clear_item_database_cache, load_item_database

# Mock the item database to avoid file I/O and dependency on assets
@pytest.fixture
def mock_item_db(monkeypatch):
    mock_items = {
        "potion": ItemDefinition(
            id="potion", name="Potion", description="Heals", icon=None,
            stackable=True, max_stack=10, tags=[], effects={}
        ),
        "sword": ItemDefinition(
            id="sword", name="Sword", description="Sharp", icon=None,
            stackable=False, max_stack=1, tags=[], effects={}
        )
    }
    
    class MockDB:
        def __init__(self, items):
            self.items = items
        def get(self, item_id):
            return self.items.get(item_id)
        @classmethod
        def load(cls, root=None):
            return MockDB(mock_items)

    monkeypatch.setattr("engine.inventory.ItemDatabase", MockDB)
    monkeypatch.setattr("engine.inventory.load_item_database", MockDB.load)

def test_inventory_add_item(mock_item_db):
    data = {}
    inv = Inventory(data)
    
    # Add stackable item
    assert inv.add_item("potion", 5)
    assert inv.get_count("potion") == 5
    assert data["items"]["potion"] == 5
    
    # Add more
    assert inv.add_item("potion", 3)
    assert inv.get_count("potion") == 8

def test_inventory_max_stack(mock_item_db):
    data = {}
    inv = Inventory(data)
    
    # Max stack is 10
    inv.add_item("potion", 8)
    # Adding 5 should cap at 10
    inv.add_item("potion", 5)
    
    assert inv.get_count("potion") == 10

def test_inventory_remove_item(mock_item_db):
    data = {}
    inv = Inventory(data)
    
    inv.add_item("potion", 5)
    assert inv.remove_item("potion", 2)
    assert inv.get_count("potion") == 3
    
    # Remove remaining
    assert inv.remove_item("potion", 3)
    assert inv.get_count("potion") == 0
    assert "potion" not in data["items"]

def test_inventory_non_stackable(mock_item_db):
    data = {}
    inv = Inventory(data)
    
    inv.add_item("sword", 1)
    assert inv.get_count("sword") == 1
    
    # Try to add another sword (max stack 1)
    # Note: The current implementation of add_item returns True if new_total > bucket.
    # If bucket is 1 and max_stack is 1, new_total is 1. 1 > 1 is False.
    assert not inv.add_item("sword", 1)
    assert inv.get_count("sword") == 1


@pytest.mark.integration
def test_clear_item_database_cache_forces_fresh_load(tmp_path, monkeypatch):
    data_dir = tmp_path / "assets" / "data"
    data_dir.mkdir(parents=True)
    items_path = data_dir / "items.json"
    items_path.write_text(json.dumps({"items": [{"id": "old", "name": "Old"}]}), encoding="utf-8")
    monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", None)

    first = load_item_database(tmp_path)
    items_path.write_text(json.dumps({"items": [{"id": "new", "name": "New"}]}), encoding="utf-8")

    assert load_item_database(tmp_path) is first
    clear_item_database_cache()
    second = load_item_database(tmp_path)

    assert second is not first
    assert list(second.items) == ["new"]
    assert inventory_module._ITEM_DB_CACHE is second
