from unittest.mock import MagicMock

from engine.quests import QuestManager


def test_reward_curve():
    # Mock window and game_state
    mock_window = MagicMock()
    mock_window.game_state.values = {}

    # Load quests
    qm = QuestManager(mock_window)

    # Define expected tiers
    # Ridge < Hollow < Ashen

    ridge_fetch = qm._definitions.get("ridge_fetch_supplies")
    ridge_kill = qm._definitions.get("ridge_kill_bandits")

    hollow_fetch = qm._definitions.get("hollow_fetch_herbs")
    hollow_kill = qm._definitions.get("hollow_kill_spiders")

    ashen_fetch = qm._definitions.get("Ashen_fetch_quest")
    ashen_kill = qm._definitions.get("Ashen_kill_quest")

    # Check existence
    assert ridge_fetch and ridge_kill
    assert hollow_fetch and hollow_kill
    assert ashen_fetch and ashen_kill

    # Check Gold Progression (Fetch)
    # Ridge: 50, Hollow: 100, Ashen: 150
    assert ridge_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0) < hollow_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0)
    assert hollow_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0) < ashen_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0)

    # Check Gold Progression (Kill)
    # Ridge: 75, Hollow: 125, Ashen: 175
    assert ridge_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0) < hollow_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0)
    assert hollow_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0) < ashen_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0)

    # Check Kill > Fetch within region
    assert ridge_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0) > ridge_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0)
    assert hollow_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0) > hollow_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0)
    assert ashen_kill.get("reward", {}).get("inc_counters", {}).get("gold", 0) > ashen_fetch.get("reward", {}).get("inc_counters", {}).get("gold", 0)
