"""Milestone 5 authoring operations: pictures, animation, collision, conversations,
conditions and trigger zones, each mapped onto the runtime's existing data."""

from __future__ import annotations

import pytest

from engine import project_ops as ops
from engine.behaviours.dialogue import Dialogue

pytestmark = pytest.mark.fast

PLAYER = {
    "id": "start_player", "name": "Player", "tag": "player", "x": 128.0, "y": 128.0,
    "sprite": "assets/sprites/animated_player.png", "behaviours": ["PlayerController"],
    "sprite_sheet": {"columns": 4, "rows": 2, "frame_width": 64, "frame_height": 64},
    "animations": {"idle": {"fps": 4, "frames": [0, 1, 2, 3], "loop": True}},
}


def _scene() -> dict:
    return {"name": "Start", "schema_version": 1, "version": 1, "entities": [dict(PLAYER)]}


def _with_grave() -> tuple[dict, str]:
    return ops.place_blank(_scene(), "start", "Grave", 320, 200)


def test_blank_objects_get_unique_names_and_a_picture_later() -> None:
    scene, first = _with_grave()
    scene, second = ops.place_blank(scene, "start", "Grave", 400, 200)
    assert first != second and ops.find_entity(scene, second)["name"] == "Grave 2"
    scene = ops.set_picture(scene, first, "assets/sprites/grave.png")
    scene = ops.set_look(scene, first, scale=2, flip_x=True)
    grave = ops.find_entity(scene, first)
    assert (grave["sprite"], grave["scale"], grave["flip_x"]) == ("assets/sprites/grave.png", 2.0, True)
    assert "flip_x" not in ops.find_entity(ops.set_look(scene, first, flip_x=False), first)
    with pytest.raises(ops.OpError, match="size"):
        ops.set_look(scene, first, scale=0)


def test_changing_or_removing_the_picture_never_loses_the_animation() -> None:
    # The My Game1 case: picture taken away, then chosen again: the animation is back.
    scene = ops.set_picture(_scene(), "start_player", None)
    scene = ops.set_picture(scene, "start_player", "assets/sprites/animated_player.png")
    player = ops.find_entity(scene, "start_player")
    assert player["animations"] == PLAYER["animations"] and player["sprite_sheet"] == PLAYER["sprite_sheet"]
    assert ops.animation_fit(player, (256, 128)) is None
    # A picture with a different layout: kept, but reported, and resettable.
    scene = ops.set_picture(scene, "start_player", "assets/sprites/small.png")
    player = ops.find_entity(scene, "start_player")
    assert "256x128" in ops.animation_fit(player, (32, 32))
    player = ops.find_entity(ops.reset_animation(scene, "start_player"), "start_player")
    assert "animations" not in player and "sprite_sheet" not in player


def test_animator_clips_follow_a_new_picture_only_when_asked() -> None:
    clips = ops.character_clips("assets/sprites/hero.png", 32, 48, 3, {"down": 0, "right": 2, "up": 3})
    scene = ops.set_picture(_scene(), "start_player", "assets/sprites/hero.png")
    scene = ops.set_animation(scene, "start_player", clips)
    kept = ops.set_picture(scene, "start_player", "assets/sprites/hero_red.png")
    assert "hero.png" in ops.animation_fit(ops.find_entity(kept, "start_player"), (96, 192))
    followed = ops.set_picture(scene, "start_player", "assets/sprites/hero_red.png", follow=True)
    assert ops.animation_fit(ops.find_entity(followed, "start_player"), (96, 192)) is None
    assert ops.animation_fit(ops.find_entity(ops.animation_use_picture(kept, "start_player"), "start_player"), (96, 192)) is None


def test_colliders_box_circle_or_the_whole_picture() -> None:
    scene, grave = _with_grave()
    scene = ops.set_collider(scene, grave, "box", w=40, h=12, offset_y=-20)
    assert ops.collider_of(ops.find_entity(scene, grave)) == {"kind": "box", "offset_x": 0.0, "offset_y": -20.0, "w": 40.0, "h": 12.0}
    scene = ops.set_collider(scene, grave, "circle", r=10)
    assert ops.collider_of(ops.find_entity(scene, grave))["r"] == 10.0
    scene = ops.set_collider(scene, grave, "picture")
    assert "components" not in ops.find_entity(scene, grave)
    with pytest.raises(ops.OpError, match="width"):
        ops.set_collider(scene, grave, "box", w=0)
    assert ops.find_entity(ops.set_solid(scene, grave, True), grave)["solid"] is True


def test_four_way_character_clips_mirror_right_for_left_and_replace_the_old_animation() -> None:
    clips = ops.character_clips("assets/sprites/hero.png", 32, 48, 3, {"down": 0, "right": 2, "up": 3},
                                walk_first=0, walk_count=3, idle_first=1, idle_count=1)
    assert clips["walk_right"]["start"] == 6 and clips["idle_down"]["start"] == 1
    assert clips["walk_left"]["flip_x"] is True and clips["walk_left"]["start"] == clips["walk_right"]["start"]
    assert ops.clip_position(clips["walk_up"], 3) == (3, 0)
    scene = ops.set_animation(_scene(), "start_player", clips)
    player = ops.find_entity(scene, "start_player")
    animator = player["behaviour_config"]["Animator"]
    assert "animations" not in player  # the frame-list animation would fight the Animator
    assert animator["directional_mode"] == "4-way" and animator["enable_auto_state"] is True
    assert animator["animation_state"] == "idle_down"
    scene = ops.set_clip(scene, "start_player", "walk_up", None)
    assert ops.find_entity(scene, "start_player")["behaviour_config"]["Animator"]["directional_mode"] == "none"
    assert "Animator" not in ops.entity_behaviours(ops.find_entity(ops.set_animation(scene, "start_player", {}), "start_player"))
    with pytest.raises(ops.OpError, match="don't fit"):
        ops.clip_spec("hero.png", 32, 32, 3, 0, 2, 3, 8)


def test_a_conversation_built_line_by_line_with_choices_runs_in_the_dialogue_behaviour() -> None:
    scene, grave = _with_grave()
    scene, bare = ops.add_line(scene, grave, text="I cannot dig with my bare hands.")
    scene, dig = ops.add_line(scene, grave, text="Start digging?")
    scene, done = ops.add_line(scene, grave, text="The earth gives way.")
    assert ops.conversation(ops.find_entity(scene, grave))["nodes"][bare]["next"] == dig  # appended in order
    scene = ops.set_line(scene, grave, bare, next_line="")
    scene = ops.add_choice(scene, grave, dig, "Dig")
    scene = ops.add_choice(scene, grave, dig, "Leave it")
    scene = ops.set_choice(scene, grave, dig, 0, next_line=done, require_flags="has_shovel",
                           set_flags="grave_open", add_counters="graves_dug")
    scene = ops.set_start_rules(scene, grave, [{"node": done, "require_flags": ["grave_open"]},
                                               {"node": dig, "require_flags": ["has_shovel"]}])
    talk = ops.conversation(ops.find_entity(scene, grave))
    choice = talk["nodes"][dig]["choices"][0]
    assert choice == {"text": "Dig", "next": done, "require_flags": ["has_shovel"],
                      "set_flags": {"grave_open": True}, "inc_counters": {"graves_dug": 1.0}}
    assert talk["once"] is False and talk["start"] == bare

    entity = type("E", (), {"mesh_name": "Grave", "mesh_entity_data": {}})()
    behaviour = Dialogue(entity, None, **ops.find_entity(scene, grave)["behaviour_config"]["Dialogue"])
    assert behaviour._graph_nodes[dig]["choices"][0]["set_flags"] == {"grave_open": True}
    assert [rule["node"] for rule in behaviour._graph_starts] == [done, dig]


def test_removing_a_line_splices_its_flow_and_forgets_rules_that_used_it() -> None:
    scene, grave = _with_grave()
    scene, a = ops.add_line(scene, grave, text="A")
    scene, b = ops.add_line(scene, grave, text="B")
    scene, c = ops.add_line(scene, grave, text="C")
    scene = ops.set_start_rules(scene, grave, [{"node": b, "require_flags": ["x"]}])
    scene = ops.remove_line(scene, grave, b)
    talk = ops.conversation(ops.find_entity(scene, grave))
    assert talk["nodes"][a]["next"] == c and talk["starts"] == []
    with pytest.raises(ops.OpError, match="no line"):
        ops.set_line(scene, grave, a, next_line="nowhere")
    with pytest.raises(ops.OpError, match="flag name"):
        ops.set_conversation(scene, grave, require_flags="has shovel")


def test_old_one_list_dialogue_becomes_a_chain_of_lines() -> None:
    scene, grave = _with_grave()
    scene = ops.add_behaviour(scene, grave, "Dialogue")
    entity = ops.find_entity(scene, grave)
    entity["behaviour_config"]["Dialogue"] = {"dialogue_lines": ["Hello.", "Goodbye."]}
    scene, extra = ops.add_line(scene, grave, text="One more thing.")
    talk = ops.conversation(ops.find_entity(scene, grave))
    texts = [node["text"] for node in talk["nodes"].values()]
    assert texts == ["Hello.", "Goodbye.", "One more thing."]


def test_show_when_and_picture_rules_map_onto_existing_behaviours_and_clear_away() -> None:
    scene, grave = _with_grave()
    scene = ops.set_show_when(scene, grave, "", "grave_open")
    assert ops.show_when(ops.find_entity(scene, grave)) == ([], ["grave_open"])
    scene = ops.set_picture_rules(scene, grave, [{"sprite": "assets/sprites/open.png", "require_flags": "grave_open"}])
    assert ops.picture_rules(ops.find_entity(scene, grave))[0]["require_flags"] == ["grave_open"]
    scene = ops.set_show_when(scene, grave, [], [])
    scene = ops.set_picture_rules(scene, grave, [])
    assert ops.entity_behaviours(ops.find_entity(scene, grave)) == []


def test_a_trigger_zone_starts_its_conversation_and_sets_flags_through_existing_behaviours() -> None:
    scene, zone = ops.place_blank(_scene(), "start", "Gate", 300, 300)
    with pytest.raises(ops.OpError, match="conversation first"):
        ops.set_trigger_zone(scene, zone, width=96, height=64, start_conversation=True)
    scene, _ = ops.add_line(scene, zone, text="A cold wind.")
    scene = ops.set_trigger_zone(scene, zone, width=96, height=64, start_conversation=True, set_flags="entered")
    entity = ops.find_entity(scene, zone)
    event = ops.zone_event(zone)
    assert entity["behaviour_config"]["TriggerVolume"]["on_enter_event"] == event
    assert entity["behaviour_config"]["TriggerVolume"]["target_tags"] == ["player"]
    assert entity["behaviour_config"]["Dialogue"]["start_event"] == event
    assert entity["behaviour_config"]["SetGameStateOnEvent"]["set_flags"] == {"entered": True}
    assert ops.trigger_zone(entity) == {"width": 96.0, "height": 64.0, "once": True, "set_flags": ["entered"],
                                        "start_conversation": True}
    scene = ops.remove_trigger_zone(scene, zone)
    entity = ops.find_entity(scene, zone)
    assert ops.trigger_zone(entity) is None and "start_event" not in entity["behaviour_config"]["Dialogue"]
    assert ops.entity_behaviours(entity) == ["Dialogue"]


def test_flag_uses_lists_every_flag_with_where_it_is_set_or_checked() -> None:
    scene, grave = _with_grave()
    scene, line = ops.add_line(scene, grave, text="Dig?")
    scene = ops.add_choice(scene, grave, line, "Dig")
    scene = ops.set_choice(scene, grave, line, 0, require_flags="has_shovel", set_flags="grave_open")
    scene = ops.set_show_when(scene, grave, "", "grave_open")
    uses = ops.flag_uses({"start": ("Cemetery", scene)})
    assert list(uses) == ["grave_open", "has_shovel"]
    assert uses["grave_open"] == ["Cemetery: Grave sets it", "Cemetery: Grave checks it"]
    assert ops.counter_steps("graves, gold+5, lives-1") == {"graves": 1.0, "gold": 5.0, "lives": -1.0}


def test_a_new_clip_guesses_frames_from_the_sheet_never_the_whole_picture() -> None:
    from engine.studio_inspector import _guess_frame  # noqa: PLC0415

    assert _guess_frame((256, 128)) == (64, 64)  # the starter sheet: 4 across, square frames
    assert _guess_frame((96, 192)) == (32, 32)  # 3 across: a 3x4 character sheet with square frames
    assert _guess_frame((384, 512)) == (128, 128)
    assert _guess_frame(None) == (32, 32)
