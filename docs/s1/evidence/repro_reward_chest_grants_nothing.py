"""S1-0 evidence: a RewardChest opened by the player grants nothing, with an EMPTY inventory.

Real hidden GameWindow, real scene loader, real interaction path (engine.interaction.perform_interaction, which
PlayerController calls on the interact key). The chest is configured like the shipped core_regions dungeons
(unlock_event + gold) plus an item. The unlock event is emitted on the game's event bus, then the player opens it.

RewardChest.on_interact only grants through ``interactor.inventory.add_item`` / ``.add_gold``; a real player sprite
has no ``inventory`` attribute (the game keeps it in game state: engine.inventory.get_or_create_inventory and the
"gold" counter), so the chest marks itself looted and emits reward_collected while granting nothing.

Also shown: the chest's looted state is not saved or remembered, so after leaving and re-entering the room it can be
opened again (harmless today, a repeatable reward once the grant works).

Exit 1 when the defect is present. Run: PYTHONPATH=<checkout> py -3.13 docs/s1/evidence/repro_reward_chest_grants_nothing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, behaviour, hidden_game, scene, sprite_named  # noqa: E402

CHEST = {"id": "chest", "name": "Chest", "x": 120, "y": 100, "sprite": PICTURE, "behaviours": ["RewardChest"],
         "behaviour_config": {"RewardChest": {"unlock_event": "vault_open", "item_id": "healing_potion", "gold": 10}}}

with hidden_game({"vault": scene("Vault", HERO, CHEST), "hall": scene("Hall", HERO)}) as (window, paths, _tmp):
    from engine.interaction import perform_interaction
    from engine.inventory import get_or_create_inventory

    gs = window.game_state_controller
    seen: list[str] = []
    window.event_bus.subscribe("reward_collected", lambda e: seen.append(e.type))
    player = window.scene_controller._find_player_sprite()
    chest = behaviour(sprite_named(window, "Chest"), "RewardChest")
    inventory = get_or_create_inventory(window.game_state.values)
    print("player sprite has an 'inventory' attribute:", hasattr(player, "inventory"))
    print("before: potions =", inventory.get_count("healing_potion"), "| gold =", gs.get_counter("gold", 0),
          "| inventory empty =", not inventory.get_count("healing_potion"))

    window.event_bus.emit("vault_open")  # what the puzzle's door/lever sends
    print("chest enabled by its unlock event:", chest.enabled)
    handled = perform_interaction(window, actor=player)  # the interact key
    potions, gold = inventory.get_count("healing_potion"), gs.get_counter("gold", 0)
    print("interaction handled:", handled, "| chest looted:", chest.looted, "| reward_collected emitted:", bool(seen))
    print("after: potions =", potions, "| gold =", gold)
    granted_nothing = chest.looted and bool(seen) and potions == 0 and gold == 0

    window.scene_controller.load_scene(paths["hall"])
    window.scene_controller.load_scene(paths["vault"])
    again = behaviour(sprite_named(window, "Chest"), "RewardChest")
    window.event_bus.emit("vault_open")
    print("after leaving and re-entering: chest looted =", again.looted, "| can be opened again =",
          again.can_interact_with(player))

print("DEFECT REPRODUCED: chest reports the reward collected but granted nothing" if granted_nothing
      else "not reproduced")
sys.exit(1 if granted_nothing else 0)
