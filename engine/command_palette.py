from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
import engine.optional_arcade as optional_arcade


@functools.lru_cache(maxsize=1)
def _list_prefab_ids_from_assets() -> tuple[str, ...]:
    try:
        from engine.paths import resolve_path  # noqa: PLC0415

        path = resolve_path("assets/prefabs.json")
        if not Path(path).exists():
            return ()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ()

    ids: list[str] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            pid = entry.get("id")
            if isinstance(pid, str) and pid.strip():
                ids.append(pid.strip())
    elif isinstance(raw, dict):
        for pid in raw.keys():
            if isinstance(pid, str) and pid.strip():
                ids.append(pid.strip())
    return tuple(sorted(set(ids)))


def _list_behaviour_names() -> tuple[str, ...]:
    try:
        from engine.behaviours import BEHAVIOUR_REGISTRY  # noqa: PLC0415

        return tuple(sorted({str(k).strip() for k in BEHAVIOUR_REGISTRY.keys() if isinstance(k, str) and str(k).strip()}))
    except Exception:  # noqa: BLE001
        return ()


@dataclass(frozen=True, slots=True)
class PromptSpec:
    kind: str  # "text" | "pick"
    placeholder: str
    default_value_fn: Callable[[Any], str]
    options_provider: Callable[[Any], list[tuple[str, str]]] | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    id: str
    title: str
    section: str
    keywords: tuple[str, ...]
    is_enabled: Callable[[Any], tuple[bool, str]]
    prompt: PromptSpec | None
    action: Callable[[Any, str | None], None]
    prompts: tuple[PromptSpec, ...] | None = None
    hotkey_hint: str | None = None
    repeat_macro_id: str | None = None
    macro_id: str | None = None
    macro_asset_path: str | None = None
    macro_defaults: dict[str, Any] | None = None


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def filter_commands(commands: Iterable[CommandSpec], query: str) -> list[CommandSpec]:
    q = _normalize_query(query)
    out: list[tuple[tuple[int, int, str, str], CommandSpec]] = []
    for cmd in commands:
        title = str(cmd.title or "").strip()
        if not title:
            continue
        title_l = title.lower()

        if not q:
            out.append(((0, 0, title_l, str(cmd.id)), cmd))
            continue

        rank = 999
        pos = 999
        if title_l.startswith(q):
            rank = 0
            pos = 0
        else:
            p = title_l.find(q)
            if p >= 0:
                rank = 1
                pos = p
            else:
                kw_pos = None
                for kw in (cmd.keywords or ()):
                    kw_l = str(kw).strip().lower()
                    if not kw_l:
                        continue
                    kp = kw_l.find(q)
                    if kp >= 0:
                        kw_pos = kp if kw_pos is None else min(kw_pos, kp)
                if kw_pos is not None:
                    rank = 2
                    pos = int(kw_pos)

        if rank != 999:
            out.append(((int(rank), int(pos), title_l, str(cmd.id)), cmd))

    out.sort(key=lambda pair: pair[0])
    return [cmd for _score, cmd in out]


def filter_options(options: Iterable[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    q = _normalize_query(query)
    scored: list[tuple[tuple[int, int, str, str], tuple[str, str]]] = []
    for value, label in options:
        v = str(value or "").strip()
        l = str(label or "").strip()
        if not v and not l:
            continue
        l_l = l.lower()
        v_l = v.lower()
        if not q:
            scored.append(((0, 0, l_l, v_l), (v, l or v)))
            continue

        rank = 999
        pos = 999
        if l_l.startswith(q) or v_l.startswith(q):
            rank = 0
            pos = 0
        else:
            p = l_l.find(q)
            if p >= 0:
                rank = 1
                pos = p
            else:
                p2 = v_l.find(q)
                if p2 >= 0:
                    rank = 1
                    pos = p2
        if rank != 999:
            scored.append(((int(rank), int(pos), l_l, v_l), (v, l or v)))

    scored.sort(key=lambda pair: pair[0])
    return [opt for _score, opt in scored]


def build_default_commands(window: Any) -> list[CommandSpec]:

    def _enabled_always(_w: Any) -> tuple[bool, str]:
        return True, ""

    def _enabled_has_scene(w: Any) -> tuple[bool, str]:
        sc = getattr(w, "scene_controller", None)
        scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
        if not scene_path:
            return False, "no_scene"
        return True, ""

    def _enabled_has_scene_and_authored_payload(w: Any) -> tuple[bool, str]:
        ok, reason = _enabled_has_scene(w)
        if not ok:
            return ok, reason
        if _get_authored_payload(w) is None:
            return False, "no_authored_payload"
        return True, ""

    def _enabled_scene_persist_armed(w: Any) -> tuple[bool, str]:
        ok, reason = _enabled_has_scene(w)
        if not ok:
            return ok, reason
        if not bool(getattr(w, "scene_persist_armed", False)):
            return False, "not_armed"
        return True, ""

    def _enabled_persist_armed_only(w: Any) -> tuple[bool, str]:
        if not bool(getattr(w, "scene_persist_armed", False)):
            return False, "not_armed"
        return True, ""

    def _toggle_tile_paint(w: Any, _arg: str | None) -> None:
        state = getattr(w, "tile_paint_state", None)
        if state is None:
            return
        state.enabled = not bool(getattr(state, "enabled", False))
        if bool(getattr(state, "enabled", False)) and not str(getattr(state, "layer_id", "") or "").strip():
            sc = getattr(w, "scene_controller", None)
            payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
            tilemap_value = payload.get("tilemap") if isinstance(payload, dict) else None
            tilemap = tilemap_value if isinstance(tilemap_value, dict) else {}
            from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415

            tile_layers = tilemap.get("tile_layers")
            tile_layers_list = tile_layers if isinstance(tile_layers, list) else []
            state.layer_id = cycle_layer_id(tile_layers=tile_layers_list, current="", direction=1)

    def _toggle_entity_paint(w: Any, _arg: str | None) -> None:
        from engine.entity_paint_mode import EntityPaintState, load_prefab_infos  # noqa: PLC0415

        state = getattr(w, "entity_paint_state", None)
        if not isinstance(state, EntityPaintState):
            return
        state.enabled = not bool(getattr(state, "enabled", False))
        if state.enabled and not getattr(state, "prefabs", ()):
            state.prefabs = load_prefab_infos()
            state.selected_index = 0
        if not state.enabled:
            state.persist_armed = False

    def _toggle_palette_mode(_w: Any, _arg: str | None) -> None:
        from engine.palette_mode import toggle_palette  # noqa: PLC0415

        toggle_palette()

    def _toggle_capture(w: Any, _arg: str | None) -> None:
        from engine.capture_mode import CaptureState, iter_layer_ids_sorted_by_z_id  # noqa: PLC0415

        state = getattr(w, "capture_state", None)
        if not isinstance(state, CaptureState):
            state = CaptureState()
            w.capture_state = state
        state.enabled = not bool(getattr(state, "enabled", False))
        state.drag_anchor = None
        state.rect = None
        if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
            sc = getattr(w, "scene_controller", None)
            payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
            if isinstance(payload, dict):
                ids = iter_layer_ids_sorted_by_z_id(payload)
                state.layer_id = ids[0] if ids else ""

    def _toggle_ghost_originals(w: Any, _arg: str | None) -> None:
        editor = getattr(w, "editor_controller", None)
        if editor is None:
            return
        toggler = getattr(editor, "toggle_ghost_originals", None)
        if callable(toggler):
            toggler()

    def _scene_reload(w: Any, _arg: str | None) -> None:
        reloader = getattr(w, "reload_scene_from_disk", None)
        ok = bool(reloader()) if callable(reloader) else False
        print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")

    def _scene_toggle_persist_armed(w: Any, _arg: str | None) -> None:
        w.scene_persist_armed = not bool(getattr(w, "scene_persist_armed", False))
        print(f"SCENE_PERSIST_ARMED {'on' if w.scene_persist_armed else 'off'}")

    def _scene_persist(w: Any, _arg: str | None) -> None:
        if not bool(getattr(w, "scene_persist_armed", False)):
            print("SCENE_PERSIST (not armed)")
            return
        persister = getattr(w, "persist_scene_to_disk", None)
        result = persister() if callable(persister) else None
        ok = bool(getattr(result, "ok", False))
        path = str(getattr(result, "path", "") or "").strip()
        print(f"SCENE_PERSIST {'ok' if ok else 'fail'} path={path or '-'}")

    def _scene_save_as(w: Any, arg: str | None) -> None:
        saver = getattr(w, "save_scene_as", None)
        new_path = str(arg or "").strip()
        result = saver(new_path) if callable(saver) else None
        ok = bool(getattr(result, "ok", False))
        out_path = str(getattr(result, "path", "") or "").strip()
        if ok and out_path:
            print(f"TIP: python -m mesh_cli world add-scene worlds/main_world.json --key <key> --path {out_path}")

    def _scene_create(w: Any, arg: str | None) -> None:
        from engine.tooling_runtime.scene_create import create_empty_scene_file  # noqa: PLC0415

        path = str(arg or "").strip()
        if not path:
            print("SCENE_CREATE fail path=- reason=empty_path")
            return
        name = Path(path).stem
        result = create_empty_scene_file(path, name=name)
        reason = ",".join(result.errors) if result.errors else "-"
        print(f"SCENE_CREATE {'ok' if result.ok else 'fail'} path={result.path} reason={reason}")

    def _default_save_as(_w: Any) -> str:
        return ""

    def _default_scene_create(w: Any) -> str:
        sc = getattr(w, "scene_controller", None)
        scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
        if not scene_path:
            return "scenes/new_scene.json"
        base = Path(scene_path)
        return str(base.parent / f"{base.stem}__new.json")

    def _go_to_scene(w: Any, arg: str | None) -> None:
        sc = getattr(w, "scene_controller", None)
        if sc is None:
            return
        path = str(arg or "").strip()
        if not path:
            return
        sc.request_scene_change(path)

    def _recent_scene(w: Any, arg: str | None) -> None:
        return _go_to_scene(w, arg)

    def _enabled_scene_index_nonempty(_w: Any) -> tuple[bool, str]:
        from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

        paths = iter_known_scene_paths()
        if not paths:
            return False, "no_scenes"
        return True, ""

    def _enabled_recent_nonempty(w: Any) -> tuple[bool, str]:
        getter = getattr(w, "get_recent_scenes", None)
        recent = getter() if callable(getter) else []
        if not isinstance(recent, list) or not recent:
            return False, "empty"
        return True, ""

    def _options_all_scenes(_w: Any) -> list[tuple[str, str]]:
        from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

        paths = iter_known_scene_paths()
        return [(p, p) for p in paths]

    def _options_recent_scenes(w: Any) -> list[tuple[str, str]]:
        getter = getattr(w, "get_recent_scenes", None)
        recent = getter() if callable(getter) else []
        if not isinstance(recent, list):
            recent = []
        out: list[tuple[str, str]] = []
        for p in recent:
            if isinstance(p, str) and p.strip():
                out.append((p.strip(), p.strip()))
        return out

    def _get_selection_ids_and_primary(w: Any) -> tuple[list[str], str]:
        state = getattr(w, "entity_select_state", None)
        ids = getattr(state, "selected_ids", None) if state is not None else None
        if not isinstance(ids, list):
            ids = []
        selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
        primary_id = getattr(state, "primary_id", None) if state is not None else None
        primary_id = str(primary_id).strip() if isinstance(primary_id, str) and str(primary_id).strip() else (selected_ids[0] if selected_ids else "")
        return selected_ids, primary_id

    def _get_authored_payload(w: Any) -> dict[str, Any] | None:
        sc = getattr(w, "scene_controller", None)
        getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
        payload = getter() if callable(getter) else None
        return payload if isinstance(payload, dict) else None

    def _selection_non_player_ids(w: Any, selected_ids: list[str]) -> tuple[list[str], bool]:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        authored = _get_authored_payload(w)
        if authored is None:
            return ([], False)
        entities = ensure_entities_list(authored)
        non_player: list[str] = []
        saw_player = False
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict):
                continue
            if is_player_entity(ent):
                saw_player = True
                continue
            non_player.append(entity_id)
        return (sorted(set(non_player)), saw_player)

    def _enabled_selection_has_non_player(w: Any) -> tuple[bool, str]:
        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            return False, "no_selection"
        if _get_authored_payload(w) is None:
            return False, "no_authored_payload"
        non_player, saw_player = _selection_non_player_ids(w, selected_ids)
        if not non_player and saw_player:
            return False, "only_player"
        if not non_player:
            return False, "no_selection"
        return True, ""

    def _enabled_selection_has_primary_non_player(w: Any) -> tuple[bool, str]:
        selected_ids, primary_id = _get_selection_ids_and_primary(w)
        if not selected_ids:
            return False, "no_selection"
        if _get_authored_payload(w) is None:
            return False, "no_authored_payload"
        non_player, saw_player = _selection_non_player_ids(w, selected_ids)
        if not non_player and saw_player:
            return False, "only_player"
        if not non_player:
            return False, "no_selection"
        if primary_id in non_player:
            return True, ""
        # Primary might be the player; still allow since we can deterministically pick a non-player primary.
        return True, ""

    def _options_prefab_ids(_w: Any) -> list[tuple[str, str]]:
        ids = _list_prefab_ids_from_assets()
        return [(pid, pid) for pid in ids]

    def _options_behaviour_names(_w: Any) -> list[tuple[str, str]]:
        names = _list_behaviour_names()
        return [(n, n) for n in names]

    def _options_behaviours_in_selection(w: Any) -> list[tuple[str, str]]:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        authored = _get_authored_payload(w)
        if authored is None:
            return []
        selected_ids, _primary = _get_selection_ids_and_primary(w)
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

    def _set_last_props_action(w: Any, *, action: str, changed: int) -> None:
        try:
            w.last_props_action = str(action)
            w.last_props_changed = int(changed)
            w.last_props_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
        except Exception:  # noqa: BLE001
            pass

    def _set_last_config_action(w: Any, *, action: str, changed: int) -> None:
        try:
            w.last_config_action = str(action)
            w.last_config_changed = int(changed)
            w.last_config_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
        except Exception:  # noqa: BLE001
            pass

    def _parse_float(text: str) -> float | None:
        try:
            return float(str(text).strip())
        except Exception:  # noqa: BLE001
            return None

    def _props_set_prefab_id(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_PROPS noop reason=no_selection")
            return
        wanted = str(arg or "").strip()
        if not wanted:
            print("ENTITY_PROPS noop reason=empty_prefab_id")
            return
        if wanted not in _list_prefab_ids_from_assets():
            print("ENTITY_PROPS noop reason=unknown_prefab")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_PROPS noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)
        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if ent.get("prefab_id") != wanted:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_props_prefab")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_set_prefab_id", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_PROPS noop reason=no_scene_controller")
            return
        changed, skipped = setter(selected_ids, wanted)
        if changed <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_props_prefab")
        _set_last_props_action(w, action="set_prefab_id", changed=int(changed))
        print(f"ENTITY_PROPS ok action=set_prefab_id changed={int(changed)} skipped_player={int(skipped)}")

    def _props_add_behaviour(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_PROPS noop reason=no_selection")
            return
        wanted = str(arg or "").strip()
        if not wanted:
            print("ENTITY_PROPS noop reason=empty_behaviour")
            return
        if wanted not in _list_behaviour_names():
            print("ENTITY_PROPS noop reason=unknown_behaviour")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_PROPS noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)
        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            behaviours = ent.get("behaviours")
            existing: set[str] = set()
            if isinstance(behaviours, list):
                for b in behaviours:
                    if isinstance(b, str) and b.strip():
                        existing.add(b.strip())
                    elif isinstance(b, dict):
                        bt = b.get("type")
                        if isinstance(bt, str) and bt.strip():
                            existing.add(bt.strip())
            if wanted not in existing:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_props_add_behaviour")
        sc = getattr(w, "scene_controller", None)
        adder = getattr(sc, "debug_add_behaviour", None) if sc is not None else None
        if not callable(adder):
            print("ENTITY_PROPS noop reason=no_scene_controller")
            return
        changed, skipped = adder(selected_ids, wanted)
        if changed <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_props_add_behaviour")
        _set_last_props_action(w, action="add_behaviour", changed=int(changed))
        print(f"ENTITY_PROPS ok action=add_behaviour changed={int(changed)} skipped_player={int(skipped)}")

    def _props_remove_behaviour(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_PROPS noop reason=no_selection")
            return
        wanted = str(arg or "").strip()
        if not wanted:
            print("ENTITY_PROPS noop reason=empty_behaviour")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_PROPS noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)
        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            behaviours = ent.get("behaviours")
            if not isinstance(behaviours, list):
                continue
            for b in behaviours:
                if isinstance(b, str) and b.strip() == wanted:
                    change_count += 1
                    break
                if isinstance(b, dict):
                    bt = b.get("type")
                    if isinstance(bt, str) and bt.strip() == wanted:
                        change_count += 1
                        break
        if change_count <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_props_remove_behaviour")
        sc = getattr(w, "scene_controller", None)
        remover = getattr(sc, "debug_remove_behaviour", None) if sc is not None else None
        if not callable(remover):
            print("ENTITY_PROPS noop reason=no_scene_controller")
            return
        changed, skipped = remover(selected_ids, wanted)
        if changed <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_props_remove_behaviour")
        _set_last_props_action(w, action="remove_behaviour", changed=int(changed))
        print(f"ENTITY_PROPS ok action=remove_behaviour changed={int(changed)} skipped_player={int(skipped)}")

    def _props_set_name(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, primary_id = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_PROPS noop reason=no_selection")
            return
        wanted = str(arg or "").strip()
        if not wanted:
            print("ENTITY_PROPS noop reason=empty_name")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_PROPS noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)
        primary_ent = find_entity_by_id(entities, primary_id)
        if not isinstance(primary_ent, dict) or is_player_entity(primary_ent):
            primary_id = ""
            for candidate in selected_ids:
                ent = find_entity_by_id(entities, candidate)
                if isinstance(ent, dict) and not is_player_entity(ent):
                    primary_id = candidate
                    primary_ent = ent
                    break
        if not primary_id or not isinstance(primary_ent, dict):
            print("ENTITY_PROPS noop reason=only_player")
            return
        if primary_ent.get("name") == wanted:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_props_name")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_set_name", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_PROPS noop reason=no_scene_controller")
            return
        changed, skipped = setter(primary_id, wanted)
        if changed <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_props_name")
        _set_last_props_action(w, action="set_name", changed=int(changed))
        print(f"ENTITY_PROPS ok action=set_name changed={int(changed)} skipped_player={int(skipped)}")

    def _props_add_tag(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_PROPS noop reason=no_selection")
            return
        wanted = str(arg or "").strip()
        if not wanted:
            print("ENTITY_PROPS noop reason=empty_tag")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_PROPS noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)
        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            tags = ent.get("tags")
            existing = {str(t).strip() for t in tags if isinstance(t, str) and str(t).strip()} if isinstance(tags, list) else set()
            if wanted not in existing:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_props_tag")
        sc = getattr(w, "scene_controller", None)
        adder = getattr(sc, "debug_add_tag", None) if sc is not None else None
        if not callable(adder):
            print("ENTITY_PROPS noop reason=no_scene_controller")
            return
        changed, skipped = adder(selected_ids, wanted)
        if changed <= 0:
            print("ENTITY_PROPS noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_props_tag")
        _set_last_props_action(w, action="add_tag", changed=int(changed))
        print(f"ENTITY_PROPS ok action=add_tag changed={int(changed)} skipped_player={int(skipped)}")

    def _config_tz_set_zone_id(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        zone_id = str(arg or "").strip()
        if not zone_id:
            print("ENTITY_CONFIG noop reason=empty_zone_id")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "TriggerZone"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("TriggerZone")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            if cfg.get("zone_id") != zone_id:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_tz_zone_id")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_triggerzone_set_zone_id", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, zone_id)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_tz_zone_id")
        _set_last_config_action(w, action="tz_set_zone_id", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=tz_set_zone_id "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _config_tz_set_radius(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        radius_text = str(arg or "").strip()
        radius = _parse_float(radius_text)
        if radius is None:
            print("ENTITY_CONFIG noop reason=bad_float")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "TriggerZone"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("TriggerZone")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            before = cfg.get("trigger_radius")
            if not isinstance(before, (int, float)) or float(before) != float(radius):
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_tz_radius")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_triggerzone_set_radius", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, float(radius))
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_tz_radius")
        _set_last_config_action(w, action="tz_set_radius", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=tz_set_radius "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _parse_toast_and_seconds(arg: str | None) -> tuple[str, float | None] | None:
        raw = str(arg or "").strip()
        if not raw:
            return None
        if "|" not in raw:
            return (raw, None)
        toast_part, seconds_part = raw.rsplit("|", 1)
        toast = toast_part.strip()
        seconds_raw = seconds_part.strip()
        if not toast:
            return None
        if not seconds_raw:
            return (toast, None)
        seconds = _parse_float(seconds_raw)
        if seconds is None:
            return None
        return (toast, float(seconds))

    def _config_sgs_set_toast(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        parsed = _parse_toast_and_seconds(arg)
        if parsed is None:
            print("ENTITY_CONFIG noop reason=bad_toast")
            return
        toast, seconds = parsed
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SetGameStateOnEvent")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            before_toast = cfg.get("toast")
            before_s = cfg.get("toast_seconds")
            before_s_val = float(before_s) if isinstance(before_s, (int, float)) else None
            if seconds is None:
                new_s = before_s_val if isinstance(before_s_val, float) and before_s_val > 0.0 else 3.0
            else:
                new_s = float(seconds)
            if before_toast != toast:
                change_count += 1
                continue
            if before_s_val is None or before_s_val <= 0.0:
                if float(new_s) != float(before_s_val or 0.0):
                    change_count += 1
                    continue
            elif float(before_s_val) != float(new_s):
                change_count += 1
                continue
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_sgs_toast")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_set_game_state_set_toast", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, toast=toast, toast_seconds=seconds)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_sgs_toast")
        _set_last_config_action(w, action="sgs_set_toast", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=sgs_set_toast "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _config_sgs_add_require_flag(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        flag = str(arg or "").strip()
        if not flag:
            print("ENTITY_CONFIG noop reason=empty_flag")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SetGameStateOnEvent")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            req = cfg.get("require_flags")
            existing = {str(v).strip() for v in req if isinstance(v, str) and str(v).strip()} if isinstance(req, list) else set()
            if flag not in existing:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_sgs_require")
        sc = getattr(w, "scene_controller", None)
        adder = getattr(sc, "debug_config_set_game_state_add_require_flag", None) if sc is not None else None
        if not callable(adder):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = adder(selected_ids, flag)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_sgs_require")
        _set_last_config_action(w, action="sgs_add_require_flag", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=sgs_add_require_flag "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _config_sgs_add_forbid_flag(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        flag = str(arg or "").strip()
        if not flag:
            print("ENTITY_CONFIG noop reason=empty_flag")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SetGameStateOnEvent")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            forbid = cfg.get("forbid_flags")
            existing = {str(v).strip() for v in forbid if isinstance(v, str) and str(v).strip()} if isinstance(forbid, list) else set()
            if flag not in existing:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_sgs_forbid")
        sc = getattr(w, "scene_controller", None)
        adder = getattr(sc, "debug_config_set_game_state_add_forbid_flag", None) if sc is not None else None
        if not callable(adder):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = adder(selected_ids, flag)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_sgs_forbid")
        _set_last_config_action(w, action="sgs_add_forbid_flag", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=sgs_add_forbid_flag "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _config_sgs_set_flag_true(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        flag = str(arg or "").strip()
        if not flag:
            print("ENTITY_CONFIG noop reason=empty_flag")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SetGameStateOnEvent"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SetGameStateOnEvent")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            flags = cfg.get("set_flags")
            before = flags.get(flag) if isinstance(flags, dict) else None
            if before is not True:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_sgs_set_flag_true")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_set_game_state_set_flag_true", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, flag)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_sgs_set_flag_true")
        _set_last_config_action(w, action="sgs_set_flag_true", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=sgs_set_flag_true "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _options_scene_paths(_w: Any) -> list[tuple[str, str]]:
        from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

        return [(p, p) for p in iter_known_scene_paths()]

    def _config_st_set_target_scene(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        target_scene = str(arg or "").strip()
        if not target_scene:
            print("ENTITY_CONFIG noop reason=empty_scene")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SceneTransition"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SceneTransition")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            if cfg.get("target_scene") != target_scene:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_st_target_scene")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_scene_transition_set_target_scene", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, target_scene)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_st_target_scene")
        _set_last_config_action(w, action="st_set_target_scene", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=st_set_target_scene "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _config_st_set_spawn_id(w: Any, arg: str | None) -> None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

        selected_ids, _primary = _get_selection_ids_and_primary(w)
        if not selected_ids:
            print("ENTITY_CONFIG noop reason=no_selection")
            return
        spawn_id = str(arg or "").strip()
        if not spawn_id:
            print("ENTITY_CONFIG noop reason=empty_spawn_id")
            return
        authored = _get_authored_payload(w)
        if authored is None:
            print("ENTITY_CONFIG noop reason=no_authored_payload")
            return
        entities = ensure_entities_list(authored)

        change_count = 0
        for entity_id in selected_ids:
            ent = find_entity_by_id(entities, entity_id)
            if not isinstance(ent, dict) or is_player_entity(ent):
                continue
            if not getattr(w.scene_controller, "_debug_config_entity_has_behaviour", lambda *_a: False)(ent, "SceneTransition"):
                continue
            root_value = ent.get("behaviour_config")
            root = root_value if isinstance(root_value, dict) else {}
            cfg_value = root.get("SceneTransition")
            cfg = cfg_value if isinstance(cfg_value, dict) else {}
            if cfg.get("spawn_id") != spawn_id or cfg.get("spawn_point") != spawn_id:
                change_count += 1
        if change_count <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_config_st_spawn_id")
        sc = getattr(w, "scene_controller", None)
        setter = getattr(sc, "debug_config_scene_transition_set_spawn_id", None) if sc is not None else None
        if not callable(setter):
            print("ENTITY_CONFIG noop reason=no_scene_controller")
            return
        changed, skipped_player, skipped_no_behaviour = setter(selected_ids, spawn_id)
        if changed <= 0:
            print("ENTITY_CONFIG noop reason=no_changes")
            return
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_config_st_spawn_id")
        _set_last_config_action(w, action="st_set_spawn_id", changed=int(changed))
        print(
            "ENTITY_CONFIG ok action=st_set_spawn_id "
            f"changed={int(changed)} skipped_player={int(skipped_player)} skipped_no_behaviour={int(skipped_no_behaviour)}"
        )

    def _get_player_pos_from_authored(w: Any) -> tuple[float, float] | None:
        from engine.entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

        authored = _get_authored_payload(w)
        if authored is None:
            return None
        entities = ensure_entities_list(authored)
        for ent in entities:
            if not isinstance(ent, dict) or not is_player_entity(ent):
                continue
            try:
                x = float(ent.get("x", 0.0))
            except Exception:  # noqa: BLE001
                x = 0.0
            try:
                y = float(ent.get("y", 0.0))
            except Exception:  # noqa: BLE001
                y = 0.0
            return float(x), float(y)
        return None

    def _get_entity_pos_from_authored(w: Any, entity_id: str) -> tuple[float, float] | None:
        from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415

        authored = _get_authored_payload(w)
        if authored is None:
            return None
        entities = ensure_entities_list(authored)
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            return None
        try:
            x = float(ent.get("x", 0.0))
        except Exception:  # noqa: BLE001
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001
            y = 0.0
        return float(x), float(y)

    def _entity_has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            return False
        for b in behaviours:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _options_dialogue_speakers(w: Any) -> list[tuple[str, str]]:
        from engine.entity_paint_mode import ensure_entities_list  # noqa: PLC0415

        authored = _get_authored_payload(w)
        if authored is None:
            return []
        entities = ensure_entities_list(authored)
        out: list[tuple[str, str]] = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if not _entity_has_behaviour(ent, "Dialogue"):
                continue
            entity_id = ent.get("id")
            if isinstance(entity_id, str) and entity_id.strip():
                out.append((entity_id.strip(), entity_id.strip()))
        out.sort(key=lambda pair: pair[0])
        return out

    def _options_macro_anchor(w: Any) -> list[tuple[str, str]]:
        selected_ids, _primary_id = _get_selection_ids_and_primary(w)
        base = [("cursor", "cursor"), ("player", "player")]
        if selected_ids:
            return [("primary", "primary"), *base]
        return base

    def _get_cursor_world_pos(w: Any) -> tuple[float, float] | None:
        input_ctrl = getattr(w, "input_controller", None)
        mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
        my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
        to_world = getattr(w, "screen_to_world", None)
        if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
            try:
                x, y = to_world(float(mx), float(my))
            except Exception:  # noqa: BLE001
                return None
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return float(x), float(y)
        return None

    def _resolve_macro_anchor_pos(w: Any, anchor: str) -> tuple[tuple[float, float] | None, str]:
        a = str(anchor or "").strip().lower()
        if a == "primary":
            selected_ids, primary_id = _get_selection_ids_and_primary(w)
            if not selected_ids or not primary_id:
                return None, "no_selection"
            pos = _get_entity_pos_from_authored(w, primary_id)
            if pos is None:
                return None, "no_selection"
            return pos, ""
        if a == "player":
            pos = _get_player_pos_from_authored(w)
            if pos is None:
                return (0.0, 0.0), ""
            return pos, ""
        # Default: cursor (fallback to player).
        pos = _get_cursor_world_pos(w)
        if pos is not None:
            return pos, ""
        pos = _get_player_pos_from_authored(w)
        if pos is None:
            return (0.0, 0.0), ""
        return pos, ""

    def _macro_objective_zone(w: Any, arg: str | None) -> None:
        sc = getattr(w, "scene_controller", None)
        if sc is None:
            print("AUTHOR_MACRO noop reason=no_scene")
            return
        if _get_authored_payload(w) is None:
            print("AUTHOR_MACRO noop reason=no_authored_payload")
            return

        try:
            data = json.loads(str(arg or "") or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}

        anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
        zone_id = str(data.get("zone_id") or "").strip()
        set_flag = str(data.get("set_flag") or "").strip()
        radius_raw = str(data.get("radius") or "").strip()
        toast = str(data.get("toast") or "")
        toast = toast.strip() if isinstance(toast, str) else ""
        toast_val = toast if toast else None
        req_raw = data.get("require_flags")
        forb_raw = data.get("forbid_flags")
        toast_seconds_raw = data.get("toast_seconds")
        require_flags = [str(v).strip() for v in (req_raw or []) if isinstance(req_raw, list) and str(v).strip()] if isinstance(req_raw, list) else None
        forbid_flags = [str(v).strip() for v in (forb_raw or []) if isinstance(forb_raw, list) and str(v).strip()] if isinstance(forb_raw, list) else None
        toast_seconds: float | None
        if toast_seconds_raw is None or toast_seconds_raw == "":
            toast_seconds = None
        else:
            try:
                toast_seconds = float(toast_seconds_raw)
            except Exception:  # noqa: BLE001
                toast_seconds = None
        try:
            radius = float(radius_raw)
        except Exception:  # noqa: BLE001
            print("AUTHOR_MACRO noop reason=bad_args")
            return
        if not zone_id or not set_flag:
            print("AUTHOR_MACRO noop reason=bad_args")
            return

        pos, reason = _resolve_macro_anchor_pos(w, anchor)
        if reason:
            print(f"AUTHOR_MACRO noop reason={reason}")
            return
        if pos is None:
            pos = (0.0, 0.0)

        payload_new, created, updated = sc.debug_build_macro_objective_zone_payload(
            center_x=float(pos[0]),
            center_y=float(pos[1]),
            zone_id=zone_id,
            set_flag=set_flag,
            radius=float(radius),
            toast=toast_val,
            require_flags=require_flags,
            forbid_flags=forbid_flags,
            toast_seconds=toast_seconds,
        )
        authored = sc.get_authored_scene_payload()
        if payload_new == authored:
            print("AUTHOR_MACRO noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_macro_objective_zone")
        sc.debug_apply_authored_scene_payload(payload_new)
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("macro_objective_zone")
        last_args = getattr(w, "last_macro_args", None)
        if isinstance(last_args, dict):
            stored: dict[str, Any] = {
                "anchor": anchor,
                "zone_id": zone_id,
                "set_flag": set_flag,
                "radius": float(radius),
                "toast": toast,
            }
            if "toast_seconds" in data:
                stored["toast_seconds"] = float(toast_seconds) if isinstance(toast_seconds, (int, float)) else ""
            if "require_flags" in data:
                stored["require_flags"] = require_flags or []
            if "forbid_flags" in data:
                stored["forbid_flags"] = forbid_flags or []
            last_args["macro.objective_zone"] = stored
        print(f"AUTHOR_MACRO ok action=objective_zone created={int(created)} updated={int(updated)}")

    def _macro_door_transition(w: Any, arg: str | None) -> None:
        sc = getattr(w, "scene_controller", None)
        if sc is None:
            print("AUTHOR_MACRO noop reason=no_scene")
            return
        if _get_authored_payload(w) is None:
            print("AUTHOR_MACRO noop reason=no_authored_payload")
            return

        try:
            data = json.loads(str(arg or "") or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}

        anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
        target_scene = str(data.get("target_scene") or "").strip()
        spawn_id = str(data.get("spawn_id") or "").strip()
        if not target_scene or not spawn_id:
            print("AUTHOR_MACRO noop reason=bad_args")
            return

        _selected_ids, primary_id = _get_selection_ids_and_primary(w)
        pos, reason = _resolve_macro_anchor_pos(w, anchor)
        if reason:
            print(f"AUTHOR_MACRO noop reason={reason}")
            return
        if pos is None:
            pos = (0.0, 0.0)
        payload_new, created, updated = sc.debug_build_macro_door_transition_payload(
            center_x=float(pos[0]),
            center_y=float(pos[1]),
            target_scene=target_scene,
            spawn_id=spawn_id,
            primary_id=primary_id if primary_id else None,
        )
        authored = sc.get_authored_scene_payload()
        if payload_new == authored:
            print("AUTHOR_MACRO noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_macro_door_transition")
        sc.debug_apply_authored_scene_payload(payload_new)
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("macro_door_transition")
        last_args = getattr(w, "last_macro_args", None)
        if isinstance(last_args, dict):
            last_args["macro.door_transition"] = {
                "anchor": anchor,
                "target_scene": target_scene,
                "spawn_id": spawn_id,
            }
        print(f"AUTHOR_MACRO ok action=door_transition created={int(created)} updated={int(updated)}")

    def _macro_dialogue_choice_flag(w: Any, arg: str | None) -> None:
        sc = getattr(w, "scene_controller", None)
        if sc is None:
            print("AUTHOR_MACRO noop reason=no_scene")
            return
        if _get_authored_payload(w) is None:
            print("AUTHOR_MACRO noop reason=no_authored_payload")
            return

        try:
            data = json.loads(str(arg or "") or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}

        speaker_id = str(data.get("speaker_id") or "").strip()
        choice_id = str(data.get("choice_id") or "").strip()
        choice_text = str(data.get("choice_text") or "").strip()
        set_flag = str(data.get("set_flag") or "").strip()
        toast = str(data.get("toast") or "")
        toast = toast.strip() if isinstance(toast, str) else ""
        toast_val = toast if toast else None
        if not speaker_id or not choice_id or not choice_text or not set_flag:
            print("AUTHOR_MACRO noop reason=bad_args")
            return

        payload_new, created, updated = sc.debug_build_macro_dialogue_choice_flag_payload(
            speaker_id=speaker_id,
            choice_id=choice_id,
            choice_text=choice_text,
            set_flag=set_flag,
            toast=toast_val,
        )
        authored = sc.get_authored_scene_payload()
        if payload_new == authored:
            print("AUTHOR_MACRO noop reason=no_changes")
            return

        pusher = getattr(w, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_macro_dialogue_choice_flag")
        sc.debug_apply_authored_scene_payload(payload_new)
        marker = getattr(w, "mark_scene_dirty", None)
        if callable(marker):
            marker("macro_dialogue_choice_flag")
        last_args = getattr(w, "last_macro_args", None)
        if isinstance(last_args, dict):
            last_args["macro.dialogue_choice_flag"] = {
                "speaker_id": speaker_id,
                "choice_id": choice_id,
                "choice_text": choice_text,
                "set_flag": set_flag,
                "toast": toast,
            }
        print(f"AUTHOR_MACRO ok action=dialogue_choice_flag created={int(created)} updated={int(updated)}")

    macro_runners = {
        "macro.objective_zone": _macro_objective_zone,
        "macro.door_transition": _macro_door_transition,
        "macro.dialogue_choice_flag": _macro_dialogue_choice_flag,
    }

    def _macro_asset_prompt_specs(*, asset: Any) -> tuple[PromptSpec, ...]:
        defaults = getattr(asset, "defaults", None)
        defaults = defaults if isinstance(defaults, dict) else {}
        steps = getattr(asset, "steps", None)
        steps = steps if isinstance(steps, list) else []
        macro_id = str(getattr(asset, "macro_id", "") or "").strip()

        # Default prompt sequences (match built-in macros).
        default_steps: list[dict[str, Any]] = []
        if macro_id == "macro.objective_zone":
            default_steps = [
                {"key": "anchor", "kind": "pick", "options": ["primary", "cursor", "player"]},
                {"key": "zone_id", "kind": "text"},
                {"key": "set_flag", "kind": "text"},
                {"key": "radius", "kind": "text"},
                {"key": "toast", "kind": "text"},
            ]
        elif macro_id == "macro.door_transition":
            default_steps = [
                {"key": "anchor", "kind": "pick", "options": ["primary", "cursor", "player"]},
                {"key": "target_scene", "kind": "pick", "source": "known_scenes"},
                {"key": "spawn_id", "kind": "text"},
            ]
        elif macro_id == "macro.dialogue_choice_flag":
            default_steps = [
                {"key": "speaker_id", "kind": "pick", "source": "dialogue_speakers"},
                {"key": "choice_id", "kind": "text"},
                {"key": "choice_text", "kind": "text"},
                {"key": "set_flag", "kind": "text"},
                {"key": "toast", "kind": "text"},
            ]

        wanted_steps = steps if steps else default_steps

        prompt_specs: list[PromptSpec] = []
        for step in wanted_steps:
            if not isinstance(step, dict):
                continue
            key = str(step.get("key") or "").strip()
            kind = str(step.get("kind") or "").strip().lower()
            if not key or kind not in {"text", "pick"}:
                continue

            placeholder = key
            if key == "radius":
                placeholder = "radius (float)"
            if key == "target_scene":
                placeholder = "target_scene"
            if key == "spawn_id":
                placeholder = "spawn_id"

            def _default_for(_w: Any, *, _k: str = key) -> str:
                v = defaults.get(_k, "")
                if isinstance(v, (int, float)):
                    return str(v)
                return str(v or "")

            options_provider: Callable[[Any], list[tuple[str, str]]] | None = None
            if kind == "pick":
                src = str(step.get("source") or "").strip()
                if src == "known_scenes":
                    options_provider = _options_all_scenes
                elif src == "dialogue_speakers":
                    options_provider = _options_dialogue_speakers
                else:
                    opts = step.get("options")
                    if isinstance(opts, list):
                        raw = [str(v).strip() for v in opts if isinstance(v, str) and str(v).strip()]

                        raw_values = raw

                        def _provider(w: Any) -> list[tuple[str, str]]:
                            selected_ids, _p = _get_selection_ids_and_primary(w)
                            out = []
                            for v in raw_values:
                                if v == "primary" and not selected_ids:
                                    continue
                                out.append((v, v))
                            return out

                        options_provider = _provider

            prompt_specs.append(
                PromptSpec(
                    kind=kind,
                    placeholder=placeholder,
                    default_value_fn=_default_for,
                    options_provider=options_provider,
                    field=key,
                )
            )

        return tuple(prompt_specs)

    def _macro_asset_commands(w: Any) -> list[CommandSpec]:
        try:
            from engine.tooling_runtime.macro_assets import iter_macro_paths, load_macro_asset, parse_macro_asset, validate_macro_asset  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return []

        out: list[tuple[tuple[str, str, str], CommandSpec]] = []
        for rel_path in iter_macro_paths():
            try:
                payload = load_macro_asset(rel_path)
            except Exception:  # noqa: BLE001
                continue
            if validate_macro_asset(payload, rel_path=rel_path):
                continue
            try:
                asset = parse_macro_asset(payload, rel_path=rel_path)
            except Exception:  # noqa: BLE001
                continue
            if not asset.id or not asset.macro_id:
                continue
            runner = macro_runners.get(asset.macro_id)
            if runner is None:
                continue

            def _action(w2: Any, arg: str | None, *, _asset=asset, _runner=runner) -> None:
                try:
                    overrides = json.loads(str(arg or "") or "{}")
                except Exception:  # noqa: BLE001
                    overrides = {}
                if not isinstance(overrides, dict):
                    overrides = {}
                merged: dict[str, Any] = dict(_asset.defaults or {})
                merged.update(overrides)
                _runner(w2, json.dumps(merged, sort_keys=True))

            cmd = CommandSpec(
                id=f"macro_asset.{asset.pack_id}.{asset.id}",
                title=f"Macro: {asset.pack_id}/{asset.id}",
                section="Authoring / Macro Assets",
                keywords=("macro", asset.pack_id, asset.id, asset.macro_id),
                is_enabled=_enabled_has_scene_and_authored_payload,
                prompt=None,
                prompts=_macro_asset_prompt_specs(asset=asset),
                action=_action,
                hotkey_hint=None,
                repeat_macro_id=asset.macro_id,
                macro_id=asset.macro_id,
                macro_asset_path=asset.path,
                macro_defaults=dict(asset.defaults or {}),
            )
            out.append(((asset.pack_id, asset.id, asset.path), cmd))
        out.sort(key=lambda pair: pair[0])
        return [cmd for _k, cmd in out]

    cmds = [
        CommandSpec(
            id="mode.tile_paint.toggle",
            title="Toggle Tile Paint",
            section="Modes",
            keywords=("tile", "paint", "tiles", "f11"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_toggle_tile_paint,
            hotkey_hint="F11",
        ),
        CommandSpec(
            id="mode.entity_paint.toggle",
            title="Toggle Entity Paint",
            section="Modes",
            keywords=("entity", "paint", "prefab", "home"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_toggle_entity_paint,
            hotkey_hint="HOME",
        ),
        CommandSpec(
            id="mode.palette.toggle",
            title="Toggle Palette Mode",
            section="Modes",
            keywords=("palette", "stamp", "brush", "f3"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_toggle_palette_mode,
            hotkey_hint="F3",
        ),
        CommandSpec(
            id="mode.capture.toggle",
            title="Toggle Capture Mode",
            section="Modes",
            keywords=("capture", "stamp", "brush", "f2"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_toggle_capture,
            hotkey_hint="F2",
        ),
        CommandSpec(
            id="view.ghost_originals.toggle",
            title="Toggle Ghost Originals",
            section="View",
            keywords=("ghost", "originals", "alt", "dup", "duplicate", "dim", "fade"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_toggle_ghost_originals,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="scene.reload",
            title="Reload Scene",
            section="Scene",
            keywords=("scene", "reload", "r"),
            is_enabled=_enabled_has_scene,
            prompt=None,
            action=_scene_reload,
            hotkey_hint="Ctrl+R",
        ),
        CommandSpec(
            id="scene.goto",
            title="Go To Scene",
            section="Scene",
            keywords=("scene", "go", "goto", "open"),
            is_enabled=_enabled_scene_index_nonempty,
            prompt=PromptSpec(
                kind="pick",
                placeholder="Scene path",
                default_value_fn=lambda _w: "",
                options_provider=_options_all_scenes,
            ),
            action=_go_to_scene,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="scene.recent",
            title="Open Recent Scene",
            section="Scene",
            keywords=("scene", "recent", "open"),
            is_enabled=_enabled_recent_nonempty,
            prompt=PromptSpec(
                kind="pick",
                placeholder="Recent scene",
                default_value_fn=lambda _w: "",
                options_provider=_options_recent_scenes,
            ),
            action=_recent_scene,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="scene.persist_arm.toggle",
            title="Toggle Scene Persist Armed",
            section="Scene",
            keywords=("scene", "persist", "armed", "save", "s"),
            is_enabled=_enabled_always,
            prompt=None,
            action=_scene_toggle_persist_armed,
            hotkey_hint="Ctrl+Shift+S",
        ),
        CommandSpec(
            id="scene.persist",
            title="Persist Scene",
            section="Scene",
            keywords=("scene", "persist", "save", "s"),
            is_enabled=_enabled_scene_persist_armed,
            prompt=None,
            action=_scene_persist,
            hotkey_hint="Ctrl+S",
        ),
        CommandSpec(
            id="scene.save_as",
            title="Save Scene As (auto version)",
            section="Scene",
            keywords=("scene", "save", "saveas", "copy", "branch", "a"),
            is_enabled=_enabled_scene_persist_armed,
            prompt=PromptSpec(kind="text", placeholder="scene path (blank=auto)", default_value_fn=_default_save_as),
            action=_scene_save_as,
            hotkey_hint="Ctrl+Shift+A",
        ),
        CommandSpec(
            id="scene.create",
            title="Scene Create",
            section="Scene",
            keywords=("scene", "create", "new"),
            is_enabled=_enabled_persist_armed_only,
            prompt=PromptSpec(kind="text", placeholder="new scene path", default_value_fn=_default_scene_create),
            action=_scene_create,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.set_prefab_id",
            title="Selection: Set Prefab ID...",
            section="Selection",
            keywords=("selection", "prefab", "set", "id"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="pick", placeholder="prefab id", default_value_fn=lambda _w: "", options_provider=_options_prefab_ids),
            action=_props_set_prefab_id,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.add_behaviour",
            title="Selection: Add Behaviour...",
            section="Selection",
            keywords=("selection", "behaviour", "behavior", "add"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="pick", placeholder="behaviour", default_value_fn=lambda _w: "", options_provider=_options_behaviour_names),
            action=_props_add_behaviour,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.remove_behaviour",
            title="Selection: Remove Behaviour...",
            section="Selection",
            keywords=("selection", "behaviour", "behavior", "remove"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="pick", placeholder="behaviour", default_value_fn=lambda _w: "", options_provider=_options_behaviours_in_selection),
            action=_props_remove_behaviour,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.set_name",
            title="Selection: Set Name (primary)...",
            section="Selection",
            keywords=("selection", "name", "set"),
            is_enabled=_enabled_selection_has_primary_non_player,
            prompt=PromptSpec(kind="text", placeholder="name", default_value_fn=lambda _w: ""),
            action=_props_set_name,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.set_tag",
            title="Selection: Set Tag...",
            section="Selection",
            keywords=("selection", "tag", "set"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="tag", default_value_fn=lambda _w: ""),
            action=_props_add_tag,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.tz_set_zone_id",
            title="TriggerZone: Set zone_id...",
            section="Selection / Config",
            keywords=("selection", "config", "triggerzone", "zone_id"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="zone_id", default_value_fn=lambda _w: ""),
            action=_config_tz_set_zone_id,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.tz_set_radius",
            title="TriggerZone: Set radius...",
            section="Selection / Config",
            keywords=("selection", "config", "triggerzone", "radius"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="trigger_radius (float)", default_value_fn=lambda _w: ""),
            action=_config_tz_set_radius,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.sgs_set_toast",
            title="SetGameStateOnEvent: Set toast...",
            section="Selection / Config",
            keywords=("selection", "config", "setgamestateonevent", "toast"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="toast[|seconds]", default_value_fn=lambda _w: ""),
            action=_config_sgs_set_toast,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.sgs_add_require_flag",
            title="SetGameStateOnEvent: Add require flag...",
            section="Selection / Config",
            keywords=("selection", "config", "setgamestateonevent", "require"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="flag key", default_value_fn=lambda _w: ""),
            action=_config_sgs_add_require_flag,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.sgs_add_forbid_flag",
            title="SetGameStateOnEvent: Add forbid flag...",
            section="Selection / Config",
            keywords=("selection", "config", "setgamestateonevent", "forbid"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="flag key", default_value_fn=lambda _w: ""),
            action=_config_sgs_add_forbid_flag,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.sgs_set_flag_true",
            title="SetGameStateOnEvent: Set flag true...",
            section="Selection / Config",
            keywords=("selection", "config", "setgamestateonevent", "set_flags"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="flag key", default_value_fn=lambda _w: ""),
            action=_config_sgs_set_flag_true,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.st_set_target_scene",
            title="SceneTransition: Set target scene...",
            section="Selection / Config",
            keywords=("selection", "config", "scenetransition", "target_scene"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="pick", placeholder="target scene", default_value_fn=lambda _w: "", options_provider=_options_scene_paths),
            action=_config_st_set_target_scene,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="selection.st_set_spawn_id",
            title="SceneTransition: Set spawn id...",
            section="Selection / Config",
            keywords=("selection", "config", "scenetransition", "spawn_id"),
            is_enabled=_enabled_selection_has_non_player,
            prompt=PromptSpec(kind="text", placeholder="spawn id", default_value_fn=lambda _w: ""),
            action=_config_st_set_spawn_id,
            hotkey_hint=None,
        ),
        CommandSpec(
            id="macro.objective_zone",
            title="Macro: Objective Zone...",
            section="Authoring / Macros",
            keywords=("macro", "objective", "zone", "triggerzone", "setgamestateonevent"),
            is_enabled=_enabled_has_scene_and_authored_payload,
            prompt=None,
            prompts=(
                PromptSpec(
                    kind="pick",
                    placeholder="anchor",
                    default_value_fn=lambda _w: "cursor",
                    options_provider=_options_macro_anchor,
                    field="anchor",
                ),
                PromptSpec(kind="text", placeholder="zone_id", default_value_fn=lambda _w: "", field="zone_id"),
                PromptSpec(kind="text", placeholder="set_flag", default_value_fn=lambda _w: "", field="set_flag"),
                PromptSpec(kind="text", placeholder="radius (float)", default_value_fn=lambda _w: "72", field="radius"),
                PromptSpec(kind="text", placeholder="toast (optional)", default_value_fn=lambda _w: "", field="toast"),
            ),
            action=_macro_objective_zone,
            hotkey_hint=None,
            repeat_macro_id="macro.objective_zone",
            macro_id="macro.objective_zone",
        ),
        CommandSpec(
            id="macro.door_transition",
            title="Macro: Door Transition...",
            section="Authoring / Macros",
            keywords=("macro", "door", "transition", "scenetransition"),
            is_enabled=_enabled_has_scene_and_authored_payload,
            prompt=None,
            prompts=(
                PromptSpec(
                    kind="pick",
                    placeholder="anchor",
                    default_value_fn=lambda _w: "cursor",
                    options_provider=_options_macro_anchor,
                    field="anchor",
                ),
                PromptSpec(
                    kind="pick",
                    placeholder="target_scene",
                    default_value_fn=lambda _w: "",
                    options_provider=_options_all_scenes,
                    field="target_scene",
                ),
                PromptSpec(kind="text", placeholder="spawn_id", default_value_fn=lambda _w: "", field="spawn_id"),
            ),
            action=_macro_door_transition,
            hotkey_hint=None,
            repeat_macro_id="macro.door_transition",
            macro_id="macro.door_transition",
        ),
        CommandSpec(
            id="macro.dialogue_choice_flag",
            title="Macro: Dialogue Choice Flag...",
            section="Authoring / Macros",
            keywords=("macro", "dialogue", "choice", "flag", "setgamestateonevent"),
            is_enabled=_enabled_has_scene_and_authored_payload,
            prompt=None,
            prompts=(
                PromptSpec(
                    kind="pick",
                    placeholder="speaker_id",
                    default_value_fn=lambda _w: "",
                    options_provider=_options_dialogue_speakers,
                    field="speaker_id",
                ),
                PromptSpec(kind="text", placeholder="choice_id", default_value_fn=lambda _w: "", field="choice_id"),
                PromptSpec(kind="text", placeholder="choice_text", default_value_fn=lambda _w: "", field="choice_text"),
                PromptSpec(kind="text", placeholder="set_flag", default_value_fn=lambda _w: "", field="set_flag"),
                PromptSpec(kind="text", placeholder="toast (optional)", default_value_fn=lambda _w: "", field="toast"),
            ),
            action=_macro_dialogue_choice_flag,
            hotkey_hint=None,
            repeat_macro_id="macro.dialogue_choice_flag",
            macro_id="macro.dialogue_choice_flag",
        ),
    ]

    cmds.extend(_macro_asset_commands(window))
    return cmds
