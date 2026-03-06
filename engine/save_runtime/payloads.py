from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Protocol

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path
from engine.migrations import migrate_payload
from engine.paths import resolve_path
from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_runtime import constants
from engine.save_runtime.entity_state import serialize_entities, apply_entities
from engine.save_runtime.errors import single_line_error
from engine.save_runtime.normalize import normalize_save_payload
from engine.save_runtime.quest_state import serialize_quests, apply_quests
from engine.save_runtime.restore_policy import RestorePolicy, SLOT_POLICY, SNAPSHOT_POLICY
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION
from engine.world_controller import WorldController

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__ + "._swallow").debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def _diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str = "$",
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
        level=level,
        code=code,
        message=single_line_error(message),
        context=context,
        hint=hint,
    )


def _append_diagnostic(diagnostics: list[Diagnostic], diagnostic: Diagnostic) -> None:
    diagnostics.append(diagnostic)


def _collect_restore_diagnostics(target: Any, diagnostics: list[Diagnostic]) -> None:
    restore_diags = getattr(target, "_last_restore_diagnostics", ())
    if isinstance(restore_diags, (list, tuple)):
        for item in restore_diags:
            if isinstance(item, Diagnostic):
                diagnostics.append(item)


def _has_errors(diagnostics: list[Diagnostic]) -> bool:
    return any(item.level == DiagnosticLevel.ERROR for item in diagnostics)


def _finalize_apply_diagnostics(
    diagnostics: list[Diagnostic],
    aggregator: SaveDiagnosticsAggregator | None,
) -> tuple[Diagnostic, ...]:
    ordered = sort_diagnostics(diagnostics)
    if aggregator is not None:
        aggregator.add(ordered)
    return ordered


def build_snapshot_payload(window: object) -> dict[str, Any]:
    controller = getattr(window, "game_state_controller", None)
    if controller is None:
        return {
            "save_format_version": SAVE_FORMAT_VERSION,
            "version": constants.SNAPSHOT_VERSION,
            "world_file": None,
            "world_id": None,
            "scene_id": None,
            "spawn_zone_id": None,
            "gold": 0,
            "flags": [],
        }
    return build_snapshot_payload_from_controller(controller)


def build_snapshot_payload_from_controller(game_state: object) -> dict[str, Any]:
    window = getattr(game_state, "window", None)
    state = getattr(game_state, "state", None)

    world_file = None
    world_id = None
    scene_id = None

    engine_cfg = getattr(window, "engine_config", None)
    if engine_cfg is not None:
        world_file = getattr(engine_cfg, "world_file", None)

    world_controller = getattr(window, "world_controller", None)
    if world_controller is not None:
        world_id = getattr(world_controller, "id", None)

    scene_controller = getattr(window, "scene_controller", None)
    if scene_controller is not None:
        scene_id = getattr(scene_controller, "current_scene_path", None)

    flags_dict = getattr(state, "flags", {}) if state is not None else {}
    counters = getattr(state, "counters", {}) if state is not None else {}
    variables = getattr(state, "variables", {}) if state is not None else {}

    spawn_zone_raw = None
    if isinstance(variables, dict):
        spawn_zone_raw = variables.get("last_zone_id")
    spawn_zone_id = str(spawn_zone_raw or "").strip() or None

    flags_true = sorted([str(k) for k, v in (flags_dict or {}).items() if bool(v) and str(k).strip()])

    gold_raw = 0
    if isinstance(counters, dict):
        gold_raw = counters.get("gold", 0)
    try:
        gold = int(gold_raw)
    except (TypeError, ValueError):
        gold = 0

    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "version": constants.SNAPSHOT_VERSION,
        "world_file": str(world_file) if world_file else None,
        "world_id": str(world_id) if world_id else None,
        "scene_id": str(scene_id) if scene_id else None,
        "spawn_zone_id": spawn_zone_id,
        "gold": gold,
        "flags": flags_true,
    }


def load_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"flags": {}, "counters": {"gold": 0}}

    version = payload.get("version")
    if version != constants.SNAPSHOT_VERSION:
        return {"flags": {}, "counters": {"gold": 0}}

    flags_list = payload.get("flags")
    flags: dict[str, bool] = {}
    if isinstance(flags_list, list):
        for item in flags_list:
            name = str(item or "").strip()
            if name:
                flags[name] = True

    gold_raw = payload.get("gold", 0)
    try:
        gold = int(gold_raw)
    except (TypeError, ValueError):
        gold = 0

    return {"flags": dict(sorted(flags.items())), "counters": {"gold": gold}}


def apply_snapshot_to_game_state(game_state: object, payload: dict[str, Any]) -> None:
    state = getattr(game_state, "state", None)
    if state is None:
        return

    update = load_snapshot(payload)
    flags = update.get("flags") or {}
    counters = update.get("counters") or {}

    if isinstance(flags, dict):
        state.flags = dict(flags)
    else:
        state.flags = {}

    gold = 0
    if isinstance(counters, dict):
        try:
            gold = int(counters.get("gold", 0))
        except (TypeError, ValueError):
            gold = 0
    state.counters = {"gold": gold}


def _apply_world_from_snapshot(
    window: object,
    world_file: str | None,
    *,
    diagnostics: list[Diagnostic],
    source: str,
) -> None:
    if not world_file:
        return

    cfg = getattr(window, "engine_config", None)
    if cfg is not None:
        try:
            cfg.world_file = str(world_file)
        except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-001", "world_file assignment", once=True)
            _append_diagnostic(
                diagnostics,
                _diagnostic(
                    level=DiagnosticLevel.WARN,
                    code="save.snapshot.world_file_assign_failed",
                    message=f"Failed to assign world_file '{world_file}': {exc}",
                    source=source,
                    pointer="/world_file",
                    hint="Engine config world_file is read-only in this runtime.",
                ),
            )

    path = resolve_path(world_file)
    if not path.exists():
        return

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw = migrate_payload("world", raw)
        setattr(window, "world_controller", WorldController(raw))
    except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
        _log_swallow("PYLD-002", "world load", once=True)
        _append_diagnostic(
            diagnostics,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.snapshot.world_load_failed",
                message=f"Failed to load world '{world_file}': {exc}",
                source=source,
                pointer="/world_file",
                hint="Ensure world_file points to a valid migrated world JSON.",
            ),
        )


def apply_loaded_payload(
    window: object,
    payload: dict[str, Any],
    *,
    mode: Literal["snapshot", "slot"],
    policy: RestorePolicy | None = None,
    strict_restore: bool | None = None,
    diagnostics: SaveDiagnosticsAggregator | None = None,
    source: str | None = None,
) -> bool:
    effective_policy = policy
    if effective_policy is None:
        effective_policy = SLOT_POLICY if mode == "slot" else SNAPSHOT_POLICY
    strict = bool(effective_policy.strict_restore) if strict_restore is None else bool(strict_restore)
    diagnostics_local: list[Diagnostic] = []
    source_label = normalize_path(source or f"save_runtime/payloads/{mode}")

    if not isinstance(payload, dict):
        _append_diagnostic(
            diagnostics_local,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.payload_invalid",
                message="Loaded payload must be an object.",
                source=source_label,
                hint="Expected dict payload from load_and_validate_payload.",
            ),
        )
        _finalize_apply_diagnostics(diagnostics_local, diagnostics)
        return False
    normalized_payload, normalize_diags = normalize_save_payload(payload, source=source_label)
    payload = normalized_payload
    diagnostics_local.extend(normalize_diags)

    if mode == "snapshot":
        world_file = payload.get("world_file")
        _apply_world_from_snapshot(
            window,
            str(world_file) if world_file else None,
            diagnostics=diagnostics_local,
            source=source_label,
        )

        controller = getattr(window, "game_state_controller", None)
        if controller is None:
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.snapshot.controller_missing",
                    message="game_state_controller is missing; cannot apply snapshot.",
                    source=source_label,
                    pointer="/game_state",
                    hint="Snapshot restore requires window.game_state_controller.",
                ),
            )
            _finalize_apply_diagnostics(diagnostics_local, diagnostics)
            return False
        try:
            apply_snapshot_to_game_state(controller, payload)
        except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-003", "snapshot apply_state", once=True)
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.snapshot.apply_state_failed",
                    message=f"apply_snapshot_to_game_state failed: {exc}",
                    source=source_label,
                    pointer="/game_state",
                    hint="Inspect snapshot game_state payload compatibility.",
                ),
            )

        spawn_zone_id = payload.get("spawn_zone_id")
        setter = getattr(window, "set_next_spawn_point", None)
        if callable(setter) and spawn_zone_id:
            try:
                setter(str(spawn_zone_id))
            except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
                _log_swallow("PYLD-004", "spawn_zone apply snapshot", once=True)
                _append_diagnostic(
                    diagnostics_local,
                    _diagnostic(
                        level=DiagnosticLevel.WARN,
                        code="save.snapshot.spawn_zone_apply_failed",
                        message=f"set_next_spawn_point failed: {exc}",
                        source=source_label,
                        pointer="/spawn_zone_id",
                        hint="Spawn point restore failed; continuing with default spawn.",
                    ),
                )
        _finalize_apply_diagnostics(diagnostics_local, diagnostics)
        return not (strict and _has_errors(diagnostics_local))

    state_block = payload.get("game_state") or payload.get("state")
    controller = getattr(window, "game_state_controller", None)
    if state_block and controller is not None:
        try:
            if hasattr(controller, "import_state"):
                controller.import_state(state_block)
            else:
                controller.replace_state(state_block)
        except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-005", "game_state apply", once=True)
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.restore.game_state_apply_failed",
                    message=f"Failed to apply game_state: {exc}",
                    source=source_label,
                    pointer="/game_state",
                    hint="Check game_state payload shape for import_state/replace_state.",
                ),
            )

    # Apply saved entity state (v2)
    saved_entities = payload.get("saved_entities")
    if isinstance(saved_entities, dict):
        entities_list = saved_entities.get("entities", [])
        scene_controller = getattr(window, "scene_controller", None)
        if scene_controller is not None and isinstance(entities_list, list):
            applied, missing = apply_entities(
                scene_controller,
                entities_list,
                strict=strict,
                diagnostics=diagnostics_local,
                source=source_label,
            )
            if missing > 0:
                _append_diagnostic(
                    diagnostics_local,
                    _diagnostic(
                        level=DiagnosticLevel.WARN,
                        code="save.restore.entities_missing",
                        message=f"{missing} saved entity entries could not be restored.",
                        source=source_label,
                        pointer="/saved_entities/entities",
                        context_extra={"applied": applied, "missing": missing},
                        hint="Missing entity ids are tolerated but should be reviewed.",
                    ),
                )
        elif scene_controller is None and isinstance(entities_list, list) and entities_list:
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.restore.scene_controller_missing",
                    message="scene_controller is missing; cannot apply saved_entities.",
                    source=source_label,
                    pointer="/saved_entities/entities",
                    hint="Slot restore requires window.scene_controller for entity state.",
                ),
            )
    elif saved_entities is not None:
        _append_diagnostic(
            diagnostics_local,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.saved_entities_invalid",
                message="saved_entities must be an object.",
                source=source_label,
                pointer="/saved_entities",
                hint="Expected {'schema_version': int, 'entities': list}.",
            ),
        )

    # Apply saved quest state (v2)
    saved_quests = payload.get("saved_quests")
    if isinstance(saved_quests, dict) and controller is not None:
        quest_manager = getattr(controller, "quests", None)
        if quest_manager is not None:
            apply_quests(
                quest_manager,
                saved_quests,
                diagnostics=diagnostics_local,
                source=source_label,
            )
            _collect_restore_diagnostics(quest_manager, diagnostics_local)
    elif saved_quests is not None and not isinstance(saved_quests, dict):
        _append_diagnostic(
            diagnostics_local,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.saved_quests_invalid",
                message="saved_quests must be an object.",
                source=source_label,
                pointer="/saved_quests",
                hint="Expected {'schema_version': int, 'quests': object}.",
            ),
        )

    spawn_zone_id = payload.get("spawn_zone_id")
    setter = getattr(window, "set_next_spawn_point", None)
    if callable(setter) and spawn_zone_id:
        try:
            setter(str(spawn_zone_id))
        except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-006", "spawn_zone apply slot", once=True)
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.WARN,
                    code="save.restore.spawn_zone_apply_failed",
                    message=f"set_next_spawn_point failed: {exc}",
                    source=source_label,
                    pointer="/spawn_zone_id",
                    hint="Spawn point restore failed; continuing with default spawn.",
                ),
            )

    if hasattr(window, "ui_controller"):
        try:
            window.ui_controller.reset_transient_state()
        except Exception as exc:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-007", "ui_controller reset", once=True)
            _append_diagnostic(
                diagnostics_local,
                _diagnostic(
                    level=DiagnosticLevel.WARN,
                    code="save.restore.ui_reset_failed",
                    message=f"ui_controller.reset_transient_state failed: {exc}",
                    source=source_label,
                    pointer="/ui_controller",
                    hint="Transient UI state could not be reset after load.",
                ),
            )

    _finalize_apply_diagnostics(diagnostics_local, diagnostics)
    return not (strict and _has_errors(diagnostics_local))


def build_slot_payload(
    window: "_WindowWithSceneController",
    slot_name: str,
    *,
    compact: bool,
    timestamp: str,
) -> tuple[dict[str, Any], str]:
    snapshot = window.scene_controller.build_scene_snapshot(compact=compact)
    controller = getattr(window, "game_state_controller", None)
    if controller is not None:
        snapshot["game_state"] = controller.export_state()

    # Add saved entity state (v2)
    scene_controller = window.scene_controller
    snapshot["saved_entities"] = {
        "schema_version": 1,
        "entities": serialize_entities(scene_controller),
    }

    # Add saved quest state (v2)
    if controller is not None:
        quest_manager = getattr(controller, "quests", None)
        if quest_manager is not None:
            snapshot["saved_quests"] = serialize_quests(quest_manager)
        else:
            snapshot["saved_quests"] = {"schema_version": 1, "quests": {}}
    else:
        snapshot["saved_quests"] = {"schema_version": 1, "quests": {}}

    # Add save schema version
    snapshot["save_schema_version"] = SAVE_SCHEMA_VERSION
    snapshot, _ = normalize_save_payload(snapshot, source="save_runtime/build_slot_payload")

    content_to_hash = {
        "data": snapshot,
        "slot": slot_name,
        "scene_path": window.scene_controller.current_scene_path,
    }
    content_str = json.dumps(content_to_hash, sort_keys=True)
    content_hash = __import__("hashlib").md5(content_str.encode("utf-8")).hexdigest()

    snapshot["meta"] = {
        "slot": slot_name,
        "scene_path": window.scene_controller.current_scene_path,
        "timestamp": timestamp,
        "version": constants.SLOT_META_VERSION,
    }
    snapshot["save_format_version"] = SAVE_FORMAT_VERSION

    spawn_zone_id = None
    if controller is not None and hasattr(controller, "get_var"):
        try:
            spawn_zone_id = controller.get_var("last_zone_id", None)
        except Exception:  # noqa: BLE001  # REASON: payloads fallback isolation
            _log_swallow("PYLD-008", "last_zone_id get", once=True)
            spawn_zone_id = None
    cleaned_zone = str(spawn_zone_id or "").strip() or None
    snapshot["spawn_zone_id"] = cleaned_zone

    return snapshot, content_hash


class _WindowWithSceneController(Protocol):
    scene_controller: Any
    game_state_controller: Any
