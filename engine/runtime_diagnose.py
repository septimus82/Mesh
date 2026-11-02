"""Why can't the player use this? (D3A, #422): an interaction explained from the running game and the authored data.

Given an entity id, ``diagnose`` reads the game running in a Mesh Studio play-test and the project as written, and
reports the conditions that decide whether the player can use the entity, each with its actual values, in the order
the engine checks them (``engine.interaction``: the same helpers, so the explanation follows the game's rules):

1. ``in_room``: whether it is in the running room. If not: another room, collected or defeated earlier (room
   memory), or kept out when the room loaded by its ``require_flags`` / ``forbid_flags``.
2. ``flag_gate``: its own ``require_flags`` / ``forbid_flags`` (``scene_entity_gating``), checked again on use.
3. ``shown``: hidden objects can't be used; "Show when" (``ConditionalActivator``) is explained flag by flag.
4. ``behaviours``: which behaviours take an interaction, and for the supported ones (``SceneTransition``,
   ``Dialogue``) each rule they check; any other behaviour's own rule is ``not_analysed``.
5. ``distance``: from the player against its interaction radius.
6. ``facing``: an object behind the player and not touching can't be used.
7. ``selection``: of all the candidates the engine would consider now, which one pressing interact uses
   (``select_interaction_candidate``, called as the game calls it), and why it wins.

A door with ``trigger_on_touch`` is used by walking into it, not with the interact key: ``touch`` reports its rules
(including that only something tagged its ``target_tag`` sets it off) and whether the player overlaps it now.
``available`` means usable now (for a touch door: the player is in its doorway); ``touch.on_contact`` says whether
walking into it would use it. A ``Dialogue`` also lists its choices: ``conditions_met`` (flags and ``once``) apart
from ``selectable_now``, which also needs the choice's node showing in an open conversation (``dialogue``).

``blocking`` is the first condition that fails; ``flags`` are the current values of every flag involved, and
``flag_sources`` the authored places that set them (dialogue choices, ``SetGameStateOnEvent``, quest rewards: what
is ``searched``). ``observed`` holds what was read; ``possible_causes`` holds hypotheses, never stated as facts. An
event's absence from the bounded event history is never taken as proof that it didn't happen.

It only reads. No frame advances, no key is pressed, and nothing is set, saved or proposed. Behaviours' own
``can_interact_with`` checks are called as the game calls them every frame for its interaction prompt.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from engine import interaction
from engine.runtime_debug import _ROOTS, plain, playtest_view
from engine.scene_entity_gating import _normalize_flag_list, is_player_entity_payload
from engine.scene_runtime import room_memory

Doc = dict[str, Any]

SUPPORTED = ("SceneTransition", "Dialogue")
CANDIDATES_MAX = 8
CHOICES_MAX = 20
SOURCES_MAX = 10
SEARCHED = ("dialogue choices' set_flags / clear_flags (every room)",
            "SetGameStateOnEvent set_flags / clear_flags (every room)", "quest rewards' set_flags")


def _cond(code: str, ok: bool | None, message: str, **detail: Any) -> Doc:
    """One condition: ``ok`` True (met), False (fails), None (not analysed)."""
    return {"code": code, "ok": ok, "message": message, **({"detail": plain(detail)} if detail else {})}


def _gate(require: list[str], forbid: list[str], flag: Any) -> tuple[bool, Doc]:
    values = {name: bool(flag(name)) for name in [*require, *forbid]}
    unmet = [name for name in require if not values[name]] + [name for name in forbid if values[name]]
    return not unmet, {"require_flags": require, "forbid_flags": forbid, "values": values, "unmet": unmet}


def _behaviour_name(behaviour: Any) -> str:
    return str(getattr(behaviour, "mesh_behaviour_type", None) or type(behaviour).__name__)


# --------------------------------------------------------------------- the project as written

def _authored(project: Any, entity_id: str) -> list[tuple[str, str, Doc]]:
    """``(room key, label, entity)`` for each room of the project holding ``entity_id``, as the person wrote it."""
    found = []
    for key, label, _path in project.rooms():
        for entity in (project.scene(key) or {}).get("entities", []) or []:
            if isinstance(entity, dict) and str(entity.get("id")) == entity_id:
                found.append((key, label, entity))
    return found


def _flag_sources(project: Any, window: Any, flags: set[str]) -> dict[str, list[Doc]]:
    """Where the project sets (or clears) each of ``flags``: the places listed in ``SEARCHED``."""
    out: dict[str, list[Doc]] = {flag: [] for flag in flags}

    def add(flag: str, value: bool, where: Doc) -> None:
        if flag in out and len(out[flag]) < SOURCES_MAX:
            out[flag].append({"sets_to": value, **where})

    for key, label, _path in project.rooms():
        for entity in (project.scene(key) or {}).get("entities", []) or []:
            if not isinstance(entity, dict):
                continue
            config = entity.get("behaviour_config") or {}
            who = {"room": key, "room_label": label, "entity_id": entity.get("id"), "entity": entity.get("name")}
            talk = (config.get("Dialogue") or {}).get("dialogue") if isinstance(config.get("Dialogue"), dict) else None
            nodes = talk.get("nodes") if isinstance(talk, dict) else None
            for node_id, node in (nodes or {}).items() if isinstance(nodes, dict) else ():
                for choice in (node or {}).get("choices") or [] if isinstance(node, dict) else []:
                    if not isinstance(choice, dict):
                        continue
                    via = {**who, "via": "dialogue choice", "node": node_id, "choice": choice.get("text")}
                    sets = choice.get("set_flags") or {}
                    for flag, value in (sets.items() if isinstance(sets, dict) else ((f, True) for f in sets)):
                        add(str(flag), bool(value), via)
                    for flag in _normalize_flag_list(choice.get("clear_flags")):
                        add(flag, False, via)
            state = config.get("SetGameStateOnEvent")
            if isinstance(state, dict):
                via = {**who, "via": "SetGameStateOnEvent", "on_event": state.get("event_type")}
                sets = state.get("set_flags") or {}
                for flag, value in (sets.items() if isinstance(sets, dict) else ((f, True) for f in sets)):
                    add(str(flag), bool(value), via)
                for flag in _normalize_flag_list(state.get("clear_flags")):
                    add(flag, False, via)
    quests = getattr(getattr(window, "quest_manager", None), "_definitions", None)
    for quest_id, quest in (quests or {}).items() if isinstance(quests, dict) else ():
        reward = (quest or {}).get("reward") or {} if isinstance(quest, dict) else {}
        for flag, value in (reward.get("set_flags") or {}).items():
            add(str(flag), bool(value), {"via": "quest reward", "quest_id": quest_id, "quest": quest.get("title")})
    return out


# --------------------------------------------------------------------- the running game

def _find_sprite(window: Any, entity_id: str) -> Any:
    for sprite in list(getattr(window.scene_controller, "all_sprites", None) or []):
        data = getattr(sprite, "mesh_entity_data", None) or {}
        if str(getattr(sprite, "mesh_id", None) or data.get("id") or "") == entity_id:
            return sprite
    return None


def _running_room(window: Any, project: Any) -> str | None:
    root = Path(project.root).resolve()
    current = str(getattr(window.scene_controller, "room_path", None)
                  or getattr(window.scene_controller, "current_scene_path", "") or "")
    for key, _label, path in project.rooms():
        candidate = Path(current)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            if candidate.resolve() == (root / path).resolve():
                return str(key)
        except OSError:
            continue
    return None


def _not_in_room(project: Any, window: Any, entity_id: str, flag: Any) -> tuple[list[Doc], list[Doc], set[str]]:
    """Why ``entity_id`` isn't in the running room: observed conditions, possible causes, flags involved."""
    observed: list[Doc] = []
    causes: list[Doc] = []
    room = _running_room(window, project)
    authored = _authored(project, entity_id)
    if not authored:
        observed.append(_cond("in_room", False, f"No object {entity_id!r} is in the running room or in any room of "
                                                 "the project.", running_room=room))
        return observed, causes, set()
    here = [item for item in authored if item[0] == room]
    if not here:
        observed.append(_cond("in_room", False, "It isn't in the running room: it is in another room.", running_room=room,
                              rooms=[{"key": k, "label": label} for k, label, _ in authored]))
        return observed, causes, set()
    _key, _label, entity = here[0]
    removed = room_memory.removed_ids(window, str(getattr(window.scene_controller, "room_path", "") or ""))
    if entity_id in removed:
        observed.append(_cond("in_room", False, "It was collected or defeated earlier in this game (the room "
                                                "remembers it), so it isn't brought back.", running_room=room))
        return observed, causes, set()
    require = _normalize_flag_list(entity.get("require_flags"))
    forbid = _normalize_flag_list(entity.get("forbid_flags"))
    ok, detail = _gate(require, forbid, flag)
    if (require or forbid) and not is_player_entity_payload(entity):
        if not ok:
            observed.append(_cond("in_room", False, "It isn't in the running room: its flags keep it out (a room "
                                                    "leaves out objects whose flags aren't met when it loads).",
                                  running_room=room, **detail))
        else:
            observed.append(_cond("in_room", False, "It isn't in the running room, though its flags are met now.",
                                  running_room=room, **detail))
            causes.append({"code": "loaded_before_flags_were_met", "message": (
                "The room may have loaded before its flags were met: a room leaves an object out when it loads, and "
                "doesn't add it later. It would appear when the room is next loaded.")})
        return observed, causes, set(require + forbid)
    observed.append(_cond("in_room", False, "It is written in this room but isn't in the running room.",
                          running_room=room))
    causes.append({"code": "not_analysed", "message": "Something not analysed removed it (another behaviour, a script)."})
    return observed, causes, set()


def _behaviour_rules(behaviour: Any, actor: Any, flag: Any) -> tuple[Doc, set[str]]:
    """What a behaviour says to an interaction now, and for a supported one, why."""
    name = _behaviour_name(behaviour)
    takes = callable(getattr(behaviour, "on_interact", None))
    if not takes:
        return {"behaviour": name, "takes_interaction": False}, set()
    allowed = interaction._behaviour_can_interact(behaviour, actor)
    out: Doc = {"behaviour": name, "takes_interaction": True, "allows": allowed}
    flags: set[str] = set()
    if name == "SceneTransition":
        ok, detail = _gate(_normalize_flag_list((behaviour.entity.mesh_entity_data or {}).get("require_flags")),
                           _normalize_flag_list((behaviour.entity.mesh_entity_data or {}).get("forbid_flags")), flag)
        out["rules"] = [
            _cond("interact_allowed", bool(behaviour.allow_interact), "It is used with the interact key." if
                  behaviour.allow_interact else "It isn't used with the interact key (allow_interact is off)."),
            _cond("has_target", bool(behaviour.target_scene), f"It leads to {behaviour.target_scene!r}." if
                  behaviour.target_scene else "It leads nowhere (no target scene)."),
            _cond("not_used_up", not (behaviour.once and behaviour._triggered),
                  "It works only once and has been used." if behaviour.once and behaviour._triggered else
                  "It isn't used up."),
            _cond("flags", ok, "Its flags are met." if ok else "Its flags aren't met.", **detail)]
        flags |= set(detail["values"])
    elif name == "Dialogue":
        ok, detail = _gate(list(behaviour.require_flags), list(behaviour.forbid_flags), flag)
        has_lines = bool(behaviour._script or behaviour._graph_nodes)
        open_now = bool(behaviour._is_box_active())
        out["rules"] = [
            _cond("conversation_open", open_now, "Its conversation is on screen (it takes the key to go on)." if
                  open_now else "Its conversation isn't on screen."),
            _cond("has_lines", has_lines, "It has lines." if has_lines else "It has no lines."),
            _cond("flags", ok, "Its conversation's flags are met." if ok else "Its conversation's flags aren't met.",
                  **detail),
            _cond("not_used_up", not (behaviour.once and behaviour._has_played),
                  "It speaks only once and has spoken." if behaviour.once and behaviour._has_played else
                  "It isn't used up.")]
        flags |= set(detail["values"])
    else:
        out["rules"] = [_cond("own_rule", None, f"{name} decides by a rule of its own, not analysed here.")]
    return out, flags


def _dialogue_choices(behaviour: Any, flag: Any) -> tuple[Doc, set[str]]:
    """Every choice of a conversation (``CHOICES_MAX``): whether its conditions are met (``Dialogue._choice_is_available``:
    flags and ``once``), and whether it can be picked now, which also needs its node showing in an open conversation
    (``Dialogue._handle_submitted_choice``)."""
    choices: list[Doc] = []
    flags: set[str] = set()
    showing = behaviour._current_node_id if behaviour._graph_active else None
    for node_id, node in list((behaviour._graph_nodes or {}).items()):
        for choice in node.get("choices", []) if isinstance(node, dict) else []:
            require, forbid = list(choice.get("require_flags") or []), list(choice.get("forbid_flags") or [])
            ok, detail = _gate(require, forbid, flag)
            used = bool(choice.get("once") and choice.get("id") in behaviour._choice_history)
            flags |= set(detail["values"])
            if len(choices) < CHOICES_MAX:
                met = bool(behaviour._choice_is_available(choice))
                choices.append({"node": node_id, "choice": choice.get("text"), "id": choice.get("id"),
                                "conditions_met": met, "selectable_now": met and node_id == showing, "used_up": used,
                                **({k: v for k, v in detail.items() if k != "values"} if require or forbid else {})})
    return {"choices": plain(choices), "conversation_open": showing is not None, "current_node": plain(showing)}, flags


def _touch(sprite: Any, actor: Any, transition: Any, flag: Any) -> Doc:
    """A door used by walking into it: its rules (``SceneTransition.update`` / ``_trigger_transition``) and overlap."""
    import engine.optional_arcade as optional_arcade  # noqa: PLC0415

    data = sprite.mesh_entity_data or {}
    ok, detail = _gate(_normalize_flag_list(data.get("require_flags")), _normalize_flag_list(data.get("forbid_flags")),
                       flag)
    if transition.area[0] > 0 and transition.area[1] > 0:
        x, y = float(sprite.center_x), float(sprite.bottom if transition.area_at == "base" else sprite.center_y)
        hw, hh = transition.area[0] / 2, transition.area[1] / 2
        overlapping = (actor.left < x + hw and actor.right > x - hw and actor.bottom < y + hh and actor.top > y - hh)
    else:
        overlapping = bool(optional_arcade.arcade.check_for_collision(sprite, actor))
    tag, target = str(getattr(actor, "mesh_tag", "") or ""), transition.target_tag
    return {"by_touch": True, "rules": [
        _cond("has_target", bool(transition.target_scene), "It leads somewhere." if transition.target_scene else
              "It leads nowhere (no target scene)."),
        _cond("not_used_up", not (transition.once and transition._triggered), "It isn't used up." if not
              (transition.once and transition._triggered) else "It works only once and has been used."),
        _cond("flags", ok, "Its flags are met." if ok else "Its flags aren't met.", **detail),
        _cond("triggered_by", tag == target, f"The player sets it off (it reacts to '{target}')." if tag == target else
              f"Only something tagged '{target}' sets it off; the player is tagged '{tag}'.", target_tag=target,
              player_tag=tag),
        _cond("overlapping", overlapping, "The player is in its doorway now." if overlapping else
              "The player isn't in its doorway: walk into it.")],
        # (verified: SceneTransition's touch trigger doesn't check "Show when"; a hidden door still works by touch)
        "checks_show_when": False}


def diagnose(studio: Any, entity_id: str) -> Doc:
    """Whether the player can use ``entity_id`` in the running play-test, and why (see the module's docstring)."""
    project = studio.project
    entity_id = str(entity_id or "").strip()
    out: Doc = {"ok": True, "mode": "live_studio", "entity_id": entity_id, "searched": list(SEARCHED)}
    window = studio.window
    playtest = getattr(studio, "playtest", None)
    if not entity_id:
        return {"ok": False, "mode": "live_studio", "reason": "invalid_request",
                "message": "debug_interaction needs an entity_id (the id a snapshot's `nearby` lists)."}
    if studio.mode != "play" or not isinstance(playtest, dict):
        authored = _authored(project, entity_id)
        return {**out, "status": "not_playing", "authored_in": [{"room": k, "label": label} for k, label, _ in authored],
                "message": "Mesh Studio is editing: nothing runs, so nothing can be used. Start a play-test (Play, "
                           "or debug_start_playtest if allowed) and ask again."}
    root = getattr(project, "root", None)
    token = _ROOTS.set((str(Path(root).resolve()), str(root)) if root else ())
    try:
        return _diagnose_playing(out, studio, window, project, entity_id, playtest)
    finally:
        _ROOTS.reset(token)


def _diagnose_playing(out: Doc, studio: Any, window: Any, project: Any, entity_id: str, playtest: Doc) -> Doc:
    getter = getattr(window, "get_flag", None)
    seen: dict[str, bool] = {}

    def flag(name: str) -> bool:
        seen[name] = bool(getter(name, False)) if callable(getter) else False
        return seen[name]

    out.update(status="playing", playtest=playtest_view(playtest))
    observed: list[Doc] = []
    causes: list[Doc] = []
    not_analysed: list[Doc] = []
    flags: set[str] = set()
    sprite = _find_sprite(window, entity_id)
    actor = interaction._find_actor(window)
    if sprite is None:
        observed, causes, flags = _not_in_room(project, window, entity_id, flag)
    else:
        data = sprite.mesh_entity_data or {}
        out["entity"] = {"name": plain(getattr(sprite, "mesh_name", None)), "x": plain(float(sprite.center_x)),
                         "y": plain(float(sprite.center_y)),
                         "behaviours": [_behaviour_name(b) for b in interaction._behaviour_list(sprite)]}
        observed.append(_cond("in_room", True, "It is in the running room."))
        ok, detail = _gate(_normalize_flag_list(data.get("require_flags")), _normalize_flag_list(data.get("forbid_flags")),
                           flag)
        observed.append(_cond("flag_gate", ok, "Its own flags are met." if ok else "Its own flags aren't met.", **detail))
        present = interaction._present(sprite)
        activator = next((b for b in interaction._behaviour_list(sprite) if _behaviour_name(b) == "ConditionalActivator"),
                         None)
        shown: Doc = {"present": present}
        if activator is not None:
            a_ok, a_detail = _gate(list(activator.require_flags), list(activator.forbid_flags), flag)
            shown["show_when"] = a_detail
            flags |= set(a_detail["values"])
        observed.append(_cond("shown", present, "It is there to use." if present else
                              ("It is hidden by its \"Show when\" flags." if activator is not None and not
                               _gate(list(activator.require_flags), list(activator.forbid_flags), flag)[0] else
                               "It is hidden (a hidden object can't be used)."), **shown))
        flags |= set(detail["values"])
        rules = []
        for behaviour in interaction._behaviour_list(sprite):
            info, more = _behaviour_rules(behaviour, actor, flag)
            flags |= more
            if info["takes_interaction"]:
                rules.append(info)
                if _behaviour_name(behaviour) not in SUPPORTED:
                    not_analysed.append({"behaviour": info["behaviour"], "why": "its own rule decides; not analysed"})
            if _behaviour_name(behaviour) == "Dialogue":
                out["dialogue"], more = _dialogue_choices(behaviour, flag)
                flags |= more
            if _behaviour_name(behaviour) == "SceneTransition" and behaviour.trigger_on_touch and actor is not None:
                out["touch"] = _touch(sprite, actor, behaviour, flag)
        eligible = [r for r in rules if r.get("allows")]
        message = (f"{', '.join(r['behaviour'] for r in eligible)} would take the interaction." if eligible else
                   "No behaviour of it takes the interaction now." if rules else
                   "It has no behaviour that takes an interaction.")
        # (its rules are plain already, made by _cond: not passed through plain again, which would cut them short)
        observed.append({"code": "behaviours", "ok": bool(eligible), "message": message, "detail": {"behaviours": rules}})
        if actor is not None and present and eligible and ok:
            observed += _reach_and_selection(window, sprite, actor)
    touch = out.get("touch")
    by_interact = any(r.get("allows") for c in observed if c["code"] == "behaviours"
                      for r in (c.get("detail") or {}).get("behaviours", []))
    if touch is not None and not by_interact:  # (a door used by walking into it: its own rules decide)
        out["how"] = "touch"
        fails = [c for c in observed if c["code"] == "in_room" and c["ok"] is False]
        fails += [r for r in touch["rules"] if r["ok"] is False]
        first = fails[0] if fails else None
        out["available"] = first is None  # (now: the player is in its doorway, so the next frame uses it)
        touch["on_contact"] = all(r["code"] == "overlapping" for r in fails)  # (walking into it would use it)
        hidden = next((c for c in observed if c["code"] == "shown"), None)
        if touch["on_contact"] and hidden is not None and hidden["ok"] is False:
            out["notes"] = [{"code": "hidden_but_touch_works", "message": (
                "It is hidden, yet walking into it still takes the player through: its touch trigger "
                "(SceneTransition) doesn't check whether it is shown.")}]
    else:
        out["how"] = "interact"
        first = next((c for c in observed if c["ok"] is False), None)
        out["available"] = first is None and any(c["code"] == "selection" and c["ok"] for c in observed)
    out["blocking"] = None if first is None else {"code": first["code"], "message": first["message"]}
    out["observed"] = observed
    out["possible_causes"] = causes
    out["not_analysed"] = not_analysed
    for name in flags:
        flag(name)
    out["flags"] = dict(sorted(seen.items()))
    out["flag_sources"] = {flag: [plain(source) for source in sources]
                           for flag, sources in _flag_sources(project, window, set(seen)).items()}
    return out  # (each part made plain where it is built: once more from here would cut its nested lists short)


def _reach_and_selection(window: Any, sprite: Any, actor: Any) -> list[Doc]:
    behaviours = interaction._eligible_behaviours(sprite, actor)
    radius = interaction._effective_radius(sprite, behaviours, interaction.DEFAULT_INTERACT_MAX_DIST)
    at, me = interaction._position(sprite), interaction._position(actor)
    if at is None or me is None:
        return [_cond("distance", None, "Its position or the player's can't be read.")]
    dx, dy = at[0] - me[0], at[1] - me[1]
    distance = math.hypot(dx, dy)
    found = [_cond("distance", distance <= radius, (
        f"The player is {distance:.0f} px away; it can be used within {radius:.0f} px." if distance <= radius else
        f"The player is too far: {distance:.0f} px away, and it can be used within {radius:.0f} px."),
        distance=round(distance, 1), radius=round(radius, 1))]
    if distance > radius:
        return found
    facing = interaction._facing_vector(actor)
    contact = interaction._contact_threshold(actor, sprite)
    alignment = ((dx / distance) * facing[0] + (dy / distance) * facing[1]) if facing and distance > 0 else 1.0
    behind = alignment < 0.0 and distance > contact
    found.append(_cond("facing", not behind, "The player faces away from it and isn't touching it." if behind else
                       "The player can reach it from where they face.", alignment=round(alignment, 3),
                       contact_distance=round(contact, 1)))
    if behind:
        return found
    getter = getattr(window, "get_flag", None)
    entities = list(interaction._iter_scene_entities(window))
    winner = interaction.select_interaction_candidate(entities, actor=actor, get_flag=getter if callable(getter) else None)
    ranked: list[Doc] = []
    for entity in entities:
        candidate = interaction._candidate_from_entity(entity, actor=actor, actor_pos=me,
                                                       max_dist=interaction.DEFAULT_INTERACT_MAX_DIST,
                                                       get_flag=getter if callable(getter) else None)
        if candidate is not None:
            ranked.append({"entity_id": candidate.entity_id, "name": getattr(entity, "mesh_name", None),
                           "priority": candidate.priority, "facing_alignment": round(candidate.facing_alignment, 3),
                           "distance": round(candidate.distance, 1)})
    ranked.sort(key=lambda c: (-int(c["priority"]), -float(c["facing_alignment"]), float(c["distance"]),
                               str(c["entity_id"])))  # (the engine's own order: select_interaction_candidate)
    target = interaction._entity_id(sprite)
    wins = winner is not None and winner.entity is sprite
    found.append(_cond("selection", wins, (
        "Pressing interact now uses it." if wins else
        f"Pressing interact now uses {plain(getattr(winner.entity, 'mesh_name', None) or winner.entity_id)!r} instead: "
        "candidates are ranked by priority, then how directly the player faces them, then distance."
        if winner is not None else "No candidate would be chosen."),
        chosen=getattr(winner, "entity_id", None), this=target, candidates=ranked[:CANDIDATES_MAX]))
    return found


# --------------------------------------------------------------------- from outside (the MCP tool)

def request(root: str | Path, entity_id: str) -> Doc:
    from urllib import parse  # noqa: PLC0415

    from engine import authoring_session  # noqa: PLC0415

    info, failure = authoring_session._studio(root)
    query = parse.urlencode({"entity": str(entity_id or "")})
    return failure or authoring_session._call(info, "GET", f"/live/debug/interaction?{query}")
