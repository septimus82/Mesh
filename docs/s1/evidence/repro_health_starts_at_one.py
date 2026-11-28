"""S1-0 part D: a Health whose "hp" is not written in the scene starts at 1 HP (and the player ignores its stats).

    py -3.13 docs/s1/evidence/repro_health_starts_at_one.py        (PYTHONPATH = this checkout)

Health means "hp not given -> start full": engine/behaviours/health.py sets hp = max_hp only when "hp" is not an
explicit param, and takes max_hp from the player's stats (level-based) when the config has none. But the scene factory
builds every behaviour through engine.behaviours.registry.create_behaviour, whose normalize_config fills every declared
field's default first (fill_defaults=True): hp 1.0 and max_hp 1.0 always arrive as explicit params. Studio's
add_behaviour (project_ops) also writes those defaults into the file.

Real hidden GameWindow:
 1. Studio-authored: add_behaviour Health + max_hp 50 on an enemy and on the player (Studio's picker shows "Health"
    = max_hp first; "Starts with" = hp is under More).
 2. Hand-written as most shipped scenes are: {"max_hp": 50} with no hp; and a player with Health and no config.
 3. Shipped content: Act1_Chapter2_Ambush (its Player has Health with no config) and scenes/cellar.json (Rat1:
    {"max_hp": 10}). Plus the count of shipped Health configs without "hp".

Also printed: the player's Combat damage against the stats' attack (combat.py uses the stats only when "damage" is not
explicit: the same pattern). Exits 1 when any of these start below max_hp, or the player's Health ignores the player's stats (EngineConfig
player_base_max_hp).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, REPO, hidden_game, scene  # noqa: E402


def shipped_without_hp() -> tuple[int, int]:
    total = without = 0
    for path in [*REPO.glob("scenes/*.json"), *REPO.glob("packs/**/*.json")]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for entity in doc.get("entities") or [] if isinstance(doc, dict) and isinstance(doc.get("entities"), list) else []:
            names = [b if isinstance(b, str) else (b or {}).get("type") for b in entity.get("behaviours") or []]
            if "Health" in names:
                total += 1
                config = (entity.get("behaviour_config") or {}).get("Health")
                without += not (isinstance(config, dict) and "hp" in config)
    return total, without


def main() -> int:
    from engine import project_ops as ops

    studio = scene("Studio", dict(HERO), {"id": "wolf", "name": "Wolf", "x": 200, "y": 100, "sprite": PICTURE,
                                          "tag": "enemy"})
    for target in ("wolf", "hero"):
        studio = ops.add_behaviour(studio, target, "Health")
        studio = ops.set_behaviour_param(studio, target, "Health", "max_hp", 50)
    print("1. written by add_behaviour + max_hp=50:",
          {e["id"]: e["behaviour_config"]["Health"] for e in studio["entities"] if "Health" in e.get("behaviours", [])})
    by_hand = scene("ByHand", dict(HERO, behaviours=["PlayerController", "Health", "Combat"]),
                    {"id": "bear", "name": "Bear", "x": 260, "y": 100, "sprite": PICTURE, "tag": "enemy",
                     "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 50}}})
    low: list[str] = []
    with hidden_game({"studio": studio, "by_hand": by_hand}) as (window, paths, _tmp):
        stats = window.game_state_controller.get_player_stats()
        print("   the player's stats say max_hp:", stats.get("max_hp"), "| attack:", stats.get("attack"))

        def report(label: str, path: str) -> None:
            window.load_scene(path)
            for sprite in window.scene_controller.all_sprites:
                health = next((b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health"), None)
                combat = next((b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Combat"), None)
                if combat is not None and getattr(sprite, "mesh_tag", "") == "player":
                    print(f"{label} {sprite.mesh_name}: Combat damage {combat.damage} (stats attack {stats.get('attack')}; "
                          f"'damage' explicit: {'damage' in combat._explicit_params})")
                if health is None:
                    continue
                player = getattr(sprite, "mesh_tag", "") == "player"
                print(f"{label} {sprite.mesh_name}: hp {health.hp} / max_hp {health.max_hp}"
                      f"{' (player)' if player else ''}")
                if health.hp < health.max_hp or (player and health.max_hp < float(stats.get("max_hp") or 0)
                                                 and not (sprite.mesh_entity_data.get("behaviour_config") or {})
                                                 .get("Health", {}).get("max_hp")):
                    low.append(f"{Path(path).name}:{sprite.mesh_name}")

        report("1.", paths["studio"])
        report("2.", paths["by_hand"])
        report("3.", "packs/core_regions/scenes/Act1_Chapter2_Ambush.json")
        report("3.", "scenes/cellar.json")
    total, without = shipped_without_hp()
    print(f"3. shipped Health configs: {total}, without an 'hp': {without}")
    if low:
        print("DEFECT REPRODUCED: Health starts at 1 HP / ignores the player's stats:", low)
        return 1
    print("not reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
