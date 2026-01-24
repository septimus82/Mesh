import pytest

from engine.game_state_controller import GameStateController


class MockWindow:
    pass


def test_flags_set_get_toggle():
    controller = GameStateController(MockWindow())
    assert controller.get_flag("door_open") is False
    controller.set_flag("door_open", True)
    assert controller.get_flag("door_open") is True
    toggled = controller.toggle_flag("door_open")
    assert toggled is False
    assert controller.get_flag("door_open") is False


def test_counters_set_add_get():
    controller = GameStateController(MockWindow())
    assert controller.get_counter("kills") == 0.0
    controller.set_counter("kills", 5)
    assert controller.get_counter("kills") == 5.0
    new_val = controller.add_counter("kills", 3)
    assert new_val == 8.0
    assert controller.get_counter("kills") == 8.0


def test_export_import_roundtrip():
    controller = GameStateController(MockWindow())
    controller.set_flag("quest_started", True)
    controller.set_counter("coins", 10)
    controller.set_var("key_item", "amulet")
    controller.set_chapter(2)
    controller.set_main_quest("mq1")
    controller.update(1.5)

    snapshot = controller.export_state()

    other = GameStateController(MockWindow())
    other.import_state(snapshot)

    assert other.get_flag("quest_started") is True
    assert other.get_counter("coins") == pytest.approx(10.0)
    assert other.get_var("key_item") == "amulet"
    assert other.get_chapter() == 2
    assert other.get_main_quest() == "mq1"
    assert other.get_playtime_seconds() == pytest.approx(controller.get_playtime_seconds())


def test_playtime_accumulates():
    controller = GameStateController(MockWindow())
    controller.update(0.5)
    controller.update(0.5)
    assert controller.get_playtime_seconds() == pytest.approx(1.0)
