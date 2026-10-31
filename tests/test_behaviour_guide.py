"""Behaviours as a creator meets them (Milestone 11): plain names, categories, settings, problems."""

from __future__ import annotations

import pytest

from engine import behaviour_guide as g
from engine import project_ops as ops

pytestmark = pytest.mark.fast


def test_every_registered_behaviour_has_a_place() -> None:
    catalog = ops.behaviour_catalog()
    shown = {e["name"] for e in g.entries(catalog, advanced=True)}
    assert shown == {b["name"] for b in catalog}  # nothing disappears, nothing is renamed
    assert all(e["category"] in g.CATEGORIES for e in g.entries(catalog, advanced=True))


def test_the_beginner_list_is_plain_language_and_leaves_plumbing_out() -> None:
    beginner = {e["name"]: e for e in g.entries(ops.behaviour_catalog())}
    assert beginner["Patrol"]["label"] == "Walk between points" and beginner["Patrol"]["category"] == "Movement"
    assert beginner["NpcSchedule"]["label"] == "Follow a daily schedule"
    assert beginner["LightSource"]["label"] == "Carry a light" and beginner["LightSource"]["category"] == "Lighting"
    assert beginner["TriggerVolume"]["label"] == "React when something enters an area"
    assert not {"ActionListRunner", "EventLogger", "MainMenuBehaviour", "PlayerController"} & set(beginner)


def test_searching_finds_by_plain_words_and_includes_advanced() -> None:
    catalog = ops.behaviour_catalog()
    assert "Patrol" in {e["name"] for e in g.entries(catalog, "walk")}
    assert {e["name"] for e in g.entries(catalog, "actionlistrunner")} == {"ActionListRunner"}


def test_aliases_are_hidden_and_main_settings_come_first() -> None:
    fields = next(b for b in ops.behaviour_catalog() if b["name"] == "Patrol")["fields"]
    basics, more = g.visible_fields("Patrol", fields)
    assert [f["name"] for f in basics] == ["patrol_points", "patrol_speed"] and more == []
    assert g.setting_label("Patrol", "patrol_points") == "Route"
    assert g.setting_label("Wander", "max_path_attempts") == "Max path attempts"  # unknown: made readable


def test_a_patrol_without_a_route_says_so_instead_of_silently_doing_nothing() -> None:
    """Hollowmere: Patrol with a mangled point list disabled itself and nothing said why."""
    assert g.problems("Patrol", {"patrol_points": []})[0].startswith("It needs at least two points")
    assert g.problems("Patrol", {"patrol_points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}) == []
    assert g.problems("ChaseTarget", {}) and not g.problems("ChaseTarget", {"target_tag": "player"})


def test_a_behaviour_the_guide_does_not_know_still_shows() -> None:
    entries = g.entries([{"name": "MyPluginThing", "description": "Does a plugin thing."}], advanced=True)
    assert entries == [{"name": "MyPluginThing", "label": "My plugin thing", "summary": "Does a plugin thing.",
                        "category": "Advanced"}]
