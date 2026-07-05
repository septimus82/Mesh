"""Battle narration templates: rendering, overrides, and clone-phrasing denylist."""

from __future__ import annotations

import pytest

from engine.monster.battle_terms import DEFAULT_BATTLE_TERMS, POKEMON_CLONE_DENYLIST
from engine.monster.data_load import KNOWN_BATTLE_TERM_KEYS, parse_battle_terms

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("method", "kwargs", "expected"),
    [
        ("format_intro_wild", {"name": "Blosskit"}, "Blosskit blocks your path!"),
        ("format_intro_companion", {"name": "Sproutling"}, "Go, Sproutling! Your companion stands ready."),
        ("format_player_recall", {"name": "A"}, "Come back, A!"),
        ("format_player_send_out", {"name": "B"}, "B takes the field!"),
        ("format_opponent_send_out", {"name": "C"}, "C joins the fight!"),
        ("format_ko", {"name": "D"}, "D is down!"),
        ("format_ko_foe", {"name": "E"}, "Foe E is down!"),
        ("format_capture_success", {"name": "F"}, "F was captured!"),
        ("format_sent_to_party", {"name": "G"}, "Added G to your party!"),
        ("format_threw_capture_item", {"opponent_name": "H"}, "You threw a Pocket Ball! H slipped free!"),
        ("format_move_hit", {"actor": "I", "move": "tackle", "target": "J", "damage": 12}, "I used tackle! J took 12 damage."),
        ("format_move_miss", {"actor": "K", "move": "tackle"}, "K used tackle, but it missed!"),
        ("format_xp_gain", {"name": "L", "xp": 40}, "L gained 40 XP!"),
        ("format_level_up", {"name": "M", "level": 11}, "M reached Lv 11!"),
        ("format_learn_move", {"name": "N", "move": "ember"}, "N learned ember!"),
        ("format_egg_hatched", {"name": "Hatchling"}, "The egg stirs... Hatchling emerges!"),
    ],
)
def test_default_templates_render_placeholders(method: str, kwargs: dict[str, object], expected: str) -> None:
    terms = DEFAULT_BATTLE_TERMS
    assert getattr(terms, method)(**kwargs) == expected


def test_parse_battle_terms_applies_narration_overrides() -> None:
    terms, result = parse_battle_terms(
        {
            "intro_wild_named": "A {name} rustles out of the blossoms!",
            "ko": "{name} crumples!",
            "capture_success": "{name} couldn't break free!",
        },
    )
    assert result.ok is True
    assert terms.format_intro_wild(name="Blosskit") == "A Blosskit rustles out of the blossoms!"
    assert terms.format_ko(name="Blosskit") == "Blosskit crumples!"
    assert terms.format_capture_success(name="Blosskit") == "Blosskit couldn't break free!"


def test_default_terms_contain_no_pokemon_clone_phrasing() -> None:
    combined = " ".join(DEFAULT_BATTLE_TERMS.all_template_values()).lower()
    for forbidden in POKEMON_CLONE_DENYLIST:
        assert forbidden not in combined, f"default battle terms contain forbidden phrase: {forbidden!r}"


def test_breeding_term_keys_are_known_and_denylist_clean() -> None:
    for key in (
        "egg_created",
        "egg_hatched",
        "breeding_not_enough_bonded",
        "breeding_egg_waiting",
        "breeding_cooldown",
    ):
        assert key in KNOWN_BATTLE_TERM_KEYS
    combined = " ".join(
        str(getattr(DEFAULT_BATTLE_TERMS, key))
        for key in (
            "egg_created",
            "egg_hatched",
            "breeding_not_enough_bonded",
            "breeding_egg_waiting",
            "breeding_cooldown",
        )
    ).lower()
    for forbidden in POKEMON_CLONE_DENYLIST:
        assert forbidden not in combined, f"breeding defaults contain forbidden phrase: {forbidden!r}"


def test_parse_battle_terms_applies_breeding_overrides() -> None:
    terms, result = parse_battle_terms(
        {
            "egg_created": "Petals swirl... a warm egg rests beneath the sakura tree.",
            "egg_hatched": "The egg stirs among fallen petals... {name} emerges!",
        },
    )
    assert result.ok is True
    assert "sakura" in terms.egg_created
    assert terms.format_egg_hatched(name="Blosskit") == "The egg stirs among fallen petals... Blosskit emerges!"


def test_wild_appeared_pattern_not_in_defaults() -> None:
    combined = " ".join(DEFAULT_BATTLE_TERMS.all_template_values()).lower()
    assert "wild" not in combined or "appeared" not in combined
