from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .paths import resolve_path


@dataclass(slots=True)
class PrefabInfo:
    prefab_id: str
    tags: tuple[str, ...]


FILTER_ORDER: tuple[str, ...] = ("all", "enemy", "prop", "npc", "interactable")

# Tags that belong to the known allowlist (everything in FILTER_ORDER except meta-modes).
_KNOWN_FILTER_TAGS: frozenset[str] = frozenset(FILTER_ORDER) - frozenset({"all", "other"})


@dataclass(slots=True)
class EntityPaintState:
    enabled: bool = False
    prefabs: tuple[PrefabInfo, ...] = ()
    filter_mode: str = "all"
    selected_index: int = 0
    snap_to_tile: bool = False
    persist_armed: bool = False
    last_status: str = ""
    adds: int = 0
    removes: int = 0
    moves: int = 0
    last_snippet: str = ""

    def reset_counts(self) -> None:
        self.adds = 0
        self.removes = 0
        self.moves = 0


def _sanitize_entity_id_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "x"
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_"}:
            out.append(ch)
        elif ch in {".", "-", ":", "/", "\\", " "}:
            out.append("_")
        else:
            out.append("_")
    collapsed = "".join(out)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    return collapsed.strip("_") or "x"


def _format_id_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    text = f"{float(value):g}"
    text = text.replace("-", "m").replace(".", "p")
    return text


def make_entity_id(scene_path: str, prefab_id: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    pid = _sanitize_entity_id_token(prefab_id)
    return f"{stem}_{pid}_{_format_id_number(x)}_{_format_id_number(y)}_0_0"


def load_prefab_infos() -> tuple[PrefabInfo, ...]:
    """
    Load prefab IDs and tags from assets/prefabs.json.

    Runtime-safe: uses engine.paths.resolve_path and json parsing only.
    """
    path = resolve_path("assets/prefabs.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ()
    if not isinstance(data, list):
        return ()

    prefabs: list[PrefabInfo] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        pid = pid.strip()
        tags_raw = entry.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if isinstance(t, str) and t.strip()]
        elif isinstance(tags_raw, str) and tags_raw.strip():
            tags = [tags_raw.strip()]
        prefabs.append(PrefabInfo(prefab_id=pid, tags=tuple(tags)))

    # Exclude player from placement lists.
    prefabs = [p for p in prefabs if p.prefab_id != "player"]
    prefabs.sort(key=lambda p: p.prefab_id)
    return tuple(prefabs)


def _prefabs_for_filter(prefabs: Iterable[PrefabInfo], filter_mode: str) -> list[PrefabInfo]:
    mode = str(filter_mode or "").strip().lower()
    if mode in ("", "all"):
        return list(prefabs)
    if mode == "other":
        return [p for p in prefabs if p.tags and not any(t in _KNOWN_FILTER_TAGS for t in p.tags)]
    tag = mode
    out: list[PrefabInfo] = []
    for p in prefabs:
        if tag in p.tags:
            out.append(p)
    return out


def get_filtered_prefab_ids(state: EntityPaintState) -> list[str]:
    prefabs = _prefabs_for_filter(state.prefabs, state.filter_mode)
    if not prefabs and state.filter_mode != "all":
        prefabs = list(state.prefabs)
    return [p.prefab_id for p in prefabs]


def get_available_filters(prefabs: Iterable[PrefabInfo]) -> list[str]:
    """Return filter modes with matching prefabs, in stable FILTER_ORDER order.

    Always starts with ``"all"``.  Appends ``"other"`` when prefabs exist
    whose tags are entirely outside the known allowlist.
    """
    prefab_list = list(prefabs)
    available: list[str] = ["all"]
    for mode in FILTER_ORDER:
        if mode == "all":
            continue
        if _prefabs_for_filter(prefab_list, mode):
            available.append(mode)
    if _prefabs_for_filter(prefab_list, "other"):
        available.append("other")
    return available


def cycle_filter_mode(state: EntityPaintState, *, direction: int) -> None:
    available = get_available_filters(state.prefabs)
    current = str(state.filter_mode or "all").strip().lower() or "all"
    if current not in available:
        current = "all"
    idx = available.index(current)
    step = 1 if int(direction) >= 0 else -1
    idx = (idx + step) % len(available)
    state.filter_mode = available[idx]
    state.selected_index = 0


def cycle_selected_prefab(state: EntityPaintState, *, direction: int) -> None:
    ids = get_filtered_prefab_ids(state)
    if not ids:
        state.selected_index = 0
        return
    idx = int(state.selected_index) if isinstance(state.selected_index, int) else 0
    idx %= len(ids)
    step = 1 if int(direction) >= 0 else -1
    state.selected_index = (idx + step) % len(ids)


def get_selected_prefab_id(state: EntityPaintState) -> str | None:
    ids = get_filtered_prefab_ids(state)
    if not ids:
        return None
    idx = int(state.selected_index) if isinstance(state.selected_index, int) else 0
    return ids[idx % len(ids)]


def select_prefab_id(state: EntityPaintState, prefab_id: str) -> bool:
    wanted = str(prefab_id or "").strip()
    if not wanted:
        return False
    ids = get_filtered_prefab_ids(state)
    if wanted not in ids:
        # Fall back to "all" to keep selection deterministic even under filters.
        state.filter_mode = "all"
        state.selected_index = 0
        ids = get_filtered_prefab_ids(state)
    if wanted not in ids:
        return False
    state.selected_index = ids.index(wanted)
    return True


def ensure_entities_list(scene_payload: dict[str, Any]) -> list[dict[str, Any]]:
    entities = scene_payload.get("entities")
    if entities is None:
        entities = []
        scene_payload["entities"] = entities
    if not isinstance(entities, list):
        raise TypeError("scene.entities must be a list")
    if all(isinstance(entry, dict) for entry in entities):
        return entities

    out: list[dict[str, Any]] = [entry for entry in entities if isinstance(entry, dict)]
    scene_payload["entities"] = out
    return out


def find_entity_by_id(entities: Iterable[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    wanted = str(entity_id or "").strip()
    if not wanted:
        return None
    for entry in entities:
        if str(entry.get("id") or "") == wanted:
            return entry
    return None


def is_player_entity(entity_payload: dict[str, Any]) -> bool:
    prefab_id = entity_payload.get("prefab_id")
    if isinstance(prefab_id, str) and prefab_id.strip() == "player":
        return True
    tag = entity_payload.get("tag")
    if isinstance(tag, str) and tag.strip().lower() == "player":
        return True
    tags = entity_payload.get("tags")
    if isinstance(tags, list) and any(isinstance(t, str) and t.strip().lower() == "player" for t in tags):
        return True
    return False


def apply_add_entity(
    scene_payload: dict[str, Any],
    *,
    scene_path: str,
    prefab_id: str,
    x: float,
    y: float,
    layer: str = "entities",
) -> tuple[bool, str]:
    entities = ensure_entities_list(scene_payload)
    entity_id = make_entity_id(scene_path, prefab_id, x, y)
    existing = find_entity_by_id(entities, entity_id)
    if existing is not None:
        return False, entity_id
    entities.append(
        {
            "id": entity_id,
            "prefab_id": str(prefab_id),
            "x": float(x),
            "y": float(y),
            "layer": str(layer),
        }
    )
    return True, entity_id


def apply_remove_entity(scene_payload: dict[str, Any], *, entity_id: str) -> bool:
    entities = ensure_entities_list(scene_payload)
    wanted = str(entity_id or "").strip()
    if not wanted:
        return False
    for idx, entry in enumerate(list(entities)):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id") or "") != wanted:
            continue
        if is_player_entity(entry):
            return False
        del entities[idx]
        return True
    return False


def apply_move_entity(scene_payload: dict[str, Any], *, entity_id: str, x: float, y: float) -> bool:
    entities = ensure_entities_list(scene_payload)
    entry = find_entity_by_id(entities, entity_id)
    if entry is None or is_player_entity(entry):
        return False
    changed = False
    if entry.get("x") != float(x):
        entry["x"] = float(x)
        changed = True
    if entry.get("y") != float(y):
        entry["y"] = float(y)
        changed = True
    return changed


def build_add_snippet(*, prefab_id: str, entity_id: str, x: float, y: float) -> str:
    return f"ENTITY_ADD --prefab-id {prefab_id} --x {float(x):.1f} --y {float(y):.1f} --id {entity_id}"


def build_remove_snippet(*, entity_id: str) -> str:
    return f"ENTITY_REMOVE --id {entity_id}"


def build_move_snippet(*, entity_id: str, x: float, y: float) -> str:
    return f"ENTITY_MOVE --id {entity_id} --x {float(x):.1f} --y {float(y):.1f}"
