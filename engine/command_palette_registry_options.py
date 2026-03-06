"""Options-provider helpers for command palette commands.

Extracted from ``engine.command_palette_registry`` to keep that module focused
on command wiring while preserving behavior through thin wrappers.
"""

from __future__ import annotations

from typing import Any, Callable


def options_all_scenes(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

    paths = iter_known_scene_paths()
    return [(p, p) for p in paths]


def options_recent_scenes(w: Any) -> list[tuple[str, str]]:
    """Return recent scene paths as options."""
    getter = getattr(w, "get_recent_scenes", None)
    recent = getter() if callable(getter) else []
    if not isinstance(recent, list):
        recent = []
    out: list[tuple[str, str]] = []
    for p in recent:
        if isinstance(p, str) and p.strip():
            out.append((p.strip(), p.strip()))
    return out


def options_prefab_ids(
    _w: Any,
    *,
    list_prefab_ids: Callable[[], tuple[str, ...]],
) -> list[tuple[str, str]]:
    """Return all prefab IDs as options."""
    ids = list_prefab_ids()
    return [(pid, pid) for pid in ids]


def options_behaviour_names(
    _w: Any,
    *,
    list_behaviour_names: Callable[[], tuple[str, ...]],
) -> list[tuple[str, str]]:
    """Return all behaviour names as options."""
    names = list_behaviour_names()
    return [(n, n) for n in names]


def options_behaviours_in_selection(
    w: Any,
    *,
    get_authored_payload: Callable[[Any], dict[str, Any] | None],
    get_selection_ids_and_primary: Callable[[Any], tuple[list[str], str]],
) -> list[tuple[str, str]]:
    """Return behaviours present in selected entities as options."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    authored = get_authored_payload(w)
    if authored is None:
        return []
    selected_ids, _primary = get_selection_ids_and_primary(w)
    entities = ensure_entities_list(authored)

    names: set[str] = set()
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            continue
        for b in behaviours:
            if isinstance(b, str) and b.strip():
                names.add(b.strip())
            elif isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip():
                    names.add(bt.strip())
    return [(n, n) for n in sorted(names)]


def options_scene_paths(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options (alias for options_all_scenes)."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

    return [(p, p) for p in iter_known_scene_paths()]


def options_dialogue_speakers(
    w: Any,
    *,
    get_authored_payload: Callable[[Any], dict[str, Any] | None],
    entity_has_behaviour: Callable[[dict[str, Any], str], bool],
) -> list[tuple[str, str]]:
    """Return entity IDs of dialogue speakers in scene."""
    from engine.entity_paint_mode import ensure_entities_list  # noqa: PLC0415

    authored = get_authored_payload(w)
    if authored is None:
        return []
    entities = ensure_entities_list(authored)
    out: list[tuple[str, str]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if not entity_has_behaviour(ent, "Dialogue"):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            out.append((entity_id.strip(), entity_id.strip()))
    out.sort(key=lambda pair: pair[0])
    return out


def options_macro_anchor(
    w: Any,
    *,
    get_selection_ids_and_primary: Callable[[Any], tuple[list[str], str]],
) -> list[tuple[str, str]]:
    """Return anchor options for macros."""
    selected_ids, _primary_id = get_selection_ids_and_primary(w)
    base = [("cursor", "cursor"), ("player", "player")]
    if selected_ids:
        return [("primary", "primary"), *base]
    return base

