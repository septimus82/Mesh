from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path

_KNOWN_TOP_LEVEL_ORDER: tuple[str, ...] = (
    "save_format_version",
    "save_schema_version",
    "version",
    "meta",
    "world_file",
    "world_id",
    "scene_path",
    "scene_id",
    "spawn_zone_id",
    "gold",
    "flags",
    "game_state",
    "state",
    "saved_flags",
    "saved_entities",
    "saved_quests",
    "saved_runners",
    "saved_time",
)

_DEFAULTS: dict[str, Any] = {
    "saved_flags": {},
    "saved_entities": {"schema_version": 1, "entities": []},
    "saved_quests": {"schema_version": 1, "quests": {}},
    "saved_runners": {},
    "saved_time": {},
}

_SAVE_HINT_KEYS: frozenset[str] = frozenset(
    {
        "save_format_version",
        "save_schema_version",
        "game_state",
        "state",
        "saved_entities",
        "saved_quests",
        "flags",
        "gold",
        "world_file",
        "scene_id",
        "scene_path",
        "scene",
        "meta",
    }
)


def _diag(
    *,
    code: str,
    message: str,
    source: str,
    pointer: str,
    hint: str | None = None,
    context_extra: dict[str, Any] | None = None,
) -> Diagnostic:
    context: dict[str, Any] = {
        "source": normalize_path(source),
        "pointer": pointer,
    }
    if context_extra:
        for key in sorted(context_extra.keys()):
            context[str(key)] = context_extra[key]
    return Diagnostic(
        level=DiagnosticLevel.WARN,
        code=code,
        message=message,
        context=context,
        hint=hint,
    )


def _deep_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _is_save_payload(payload: Mapping[str, Any]) -> bool:
    return any(str(key) in _SAVE_HINT_KEYS for key in payload.keys())


def _ordered_known_first(data: Mapping[str, Any], known_order: tuple[str, ...]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    known_set = set(known_order)
    for key in known_order:
        if key in data:
            ordered[key] = data[key]
    for key in sorted(str(k) for k in data.keys() if str(k) not in known_set):
        ordered[key] = data[key]
    return ordered


def _sorted_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in sorted(str(k) for k in data.keys())}


def _entity_sort_key(item: dict[str, Any], index: int) -> tuple[str, str, int]:
    entity_id = str(item.get("entity_id", "") or "")
    legacy_id = str(item.get("id", "") or "")
    label = entity_id or legacy_id
    return (label, entity_id, index)


def _normalize_saved_entities(
    data: dict[str, Any],
    *,
    source: str,
    diagnostics: list[Diagnostic],
) -> None:
    raw = data.get("saved_entities")
    if not isinstance(raw, Mapping):
        return
    container = {str(k): _deep_copy(v) for k, v in raw.items()}

    entities = container.get("entities")
    if isinstance(entities, list):
        dict_items = [item for item in entities if isinstance(item, Mapping)]
        if len(dict_items) == len(entities):
            original = [_deep_copy(item) for item in entities]
            indexed = [({str(k): _deep_copy(v) for k, v in item.items()}, index) for index, item in enumerate(dict_items)]
            sorted_entities = [item for item, index in sorted(indexed, key=lambda pair: _entity_sort_key(pair[0], pair[1]))]
            if original != sorted_entities:
                diagnostics.append(
                    _diag(
                        code="NORMALIZED_DICT_ORDER",
                        message="Normalized entity list ordering by entity_id.",
                        source=source,
                        pointer="/saved_entities/entities",
                        hint="Entity ordering is canonicalized for deterministic diffs.",
                    )
                )
            container["entities"] = sorted_entities

    ordered = _ordered_known_first(container, ("schema_version", "entities"))
    if list(container.keys()) != list(ordered.keys()):
        diagnostics.append(
            _diag(
                code="NORMALIZED_DICT_ORDER",
                message="Normalized saved_entities key ordering.",
                source=source,
                pointer="/saved_entities",
            )
        )
    data["saved_entities"] = ordered


def _normalize_saved_quests(
    data: dict[str, Any],
    *,
    source: str,
    diagnostics: list[Diagnostic],
) -> None:
    raw = data.get("saved_quests")
    if not isinstance(raw, Mapping):
        return
    container = {str(k): _deep_copy(v) for k, v in raw.items()}
    quests_raw = container.get("quests")
    if isinstance(quests_raw, Mapping):
        quests_sorted = _sorted_dict({str(k): _deep_copy(v) for k, v in quests_raw.items()})
        if list(quests_raw.keys()) != list(quests_sorted.keys()):
            diagnostics.append(
                _diag(
                    code="NORMALIZED_DICT_ORDER",
                    message="Normalized saved_quests.quests key ordering.",
                    source=source,
                    pointer="/saved_quests/quests",
                )
            )
        container["quests"] = quests_sorted
    ordered = _ordered_known_first(container, ("schema_version", "quests"))
    if list(container.keys()) != list(ordered.keys()):
        diagnostics.append(
            _diag(
                code="NORMALIZED_DICT_ORDER",
                message="Normalized saved_quests key ordering.",
                source=source,
                pointer="/saved_quests",
            )
        )
    data["saved_quests"] = ordered


def _normalize_simple_dict_container(
    data: dict[str, Any],
    *,
    key: str,
    source: str,
    diagnostics: list[Diagnostic],
) -> None:
    raw = data.get(key)
    if not isinstance(raw, Mapping):
        return
    sorted_container = _sorted_dict({str(k): _deep_copy(v) for k, v in raw.items()})
    if list(raw.keys()) != list(sorted_container.keys()):
        diagnostics.append(
            _diag(
                code="NORMALIZED_DICT_ORDER",
                message=f"Normalized {key} key ordering.",
                source=source,
                pointer=f"/{key}",
            )
        )
    data[key] = sorted_container


def normalize_save_payload(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> tuple[dict[str, Any], list[Diagnostic]]:
    if not isinstance(payload, Mapping):
        return {}, []
    if not _is_save_payload(payload):
        return ({str(k): _deep_copy(v) for k, v in payload.items()}, [])

    data: dict[str, Any] = {str(k): _deep_copy(v) for k, v in payload.items()}
    diagnostics: list[Diagnostic] = []

    if "scene" in data:
        scene_value = data.pop("scene")
        if "scene_path" not in data:
            data["scene_path"] = scene_value
            diagnostics.append(
                _diag(
                    code="NORMALIZED_KEY_RENAMED",
                    message="Renamed legacy '/scene' to '/scene_path'.",
                    source=source,
                    pointer="/scene_path",
                    context_extra={"old_pointer": "/scene"},
                    hint="Use scene_path for canonical save payloads.",
                )
            )
        else:
            diagnostics.append(
                _diag(
                    code="NORMALIZED_KEY_RENAMED",
                    message="Dropped legacy '/scene' because '/scene_path' is canonical.",
                    source=source,
                    pointer="/scene",
                    hint="Use scene_path for canonical save payloads.",
                )
            )

    for key, default_value in _DEFAULTS.items():
        if key not in data:
            data[key] = _deep_copy(default_value)
            diagnostics.append(
                _diag(
                    code="NORMALIZED_DEFAULT_ADDED",
                    message=f"Added default for missing optional field '/{key}'.",
                    source=source,
                    pointer=f"/{key}",
                )
            )

    _normalize_saved_entities(data, source=source, diagnostics=diagnostics)
    _normalize_saved_quests(data, source=source, diagnostics=diagnostics)
    _normalize_simple_dict_container(data, key="saved_flags", source=source, diagnostics=diagnostics)
    _normalize_simple_dict_container(data, key="saved_runners", source=source, diagnostics=diagnostics)
    _normalize_simple_dict_container(data, key="saved_time", source=source, diagnostics=diagnostics)

    ordered = _ordered_known_first(data, _KNOWN_TOP_LEVEL_ORDER)
    if list(data.keys()) != list(ordered.keys()):
        diagnostics.append(
            _diag(
                code="NORMALIZED_DICT_ORDER",
                message="Normalized top-level save payload key ordering.",
                source=source,
                pointer="/",
            )
        )

    return ordered, list(sort_diagnostics(diagnostics))
