from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path
from engine.persistence_io import migrate_save_payload, read_json, write_json_atomic
from engine.save_runtime.errors import single_line_error
from engine.save_runtime.normalize import normalize_save_payload
from engine.save_runtime.restore_policy import (
    SLOT_POLICY,
    SNAPSHOT_POLICY,
    RestorePolicy,
)
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from engine.save_runtime.schema import SaveValidationError, migrate_save, validate_save
from engine.swallowed_exceptions import _log_swallow

_LAST_LOAD_ATTEMPT: dict[str, Any] = {
    "kind": None,
    "path": None,
    "ok": None,
    "diagnostics": {"counts": {"total": 0, "errors": 0, "warnings": 0, "infos": 0}, "diagnostics": []},
}
_LAST_SAVE_ATTEMPT: dict[str, Any] = {
    "kind": None,
    "path": None,
    "ok": None,
    "diagnostics": {"counts": {"total": 0, "errors": 0, "warnings": 0, "infos": 0}, "diagnostics": []},
}


def _snapshot_attempt(
    *,
    kind: str,
    path: Path | None,
    ok: bool,
    aggregator: SaveDiagnosticsAggregator,
) -> dict[str, Any]:
    payload = aggregator.to_json()
    diagnostics = payload.get("diagnostics", [])
    if not isinstance(diagnostics, list):
        diagnostics = []
    return {
        "kind": str(kind),
        "path": (None if path is None else normalize_path(path)),
        "ok": bool(ok),
        "diagnostics": {
            "counts": payload.get("counts", {}),
            "diagnostics": diagnostics[:10],
        },
    }


def _update_last_attempt(
    *,
    slot: str,
    kind: str,
    path: Path | None,
    ok: bool,
    aggregator: SaveDiagnosticsAggregator,
) -> None:
    snapshot = _snapshot_attempt(kind=kind, path=path, ok=ok, aggregator=aggregator)
    if slot == "load":
        _LAST_LOAD_ATTEMPT.clear()
        _LAST_LOAD_ATTEMPT.update(snapshot)
    else:
        _LAST_SAVE_ATTEMPT.clear()
        _LAST_SAVE_ATTEMPT.update(snapshot)


def get_save_runtime_diagnostics_snapshot() -> dict[str, Any]:
    return {
        "last_save_attempt": {
            "kind": _LAST_SAVE_ATTEMPT.get("kind"),
            "path": _LAST_SAVE_ATTEMPT.get("path"),
            "ok": _LAST_SAVE_ATTEMPT.get("ok"),
            "diagnostics": _LAST_SAVE_ATTEMPT.get("diagnostics", {}),
        },
        "last_load_attempt": {
            "kind": _LAST_LOAD_ATTEMPT.get("kind"),
            "path": _LAST_LOAD_ATTEMPT.get("path"),
            "ok": _LAST_LOAD_ATTEMPT.get("ok"),
            "diagnostics": _LAST_LOAD_ATTEMPT.get("diagnostics", {}),
        },
    }


def write_diagnostics_sidecars(path: Path, aggregator: SaveDiagnosticsAggregator) -> tuple[Path, Path]:
    json_path = Path(f"{path.as_posix()}.diagnostics.json")
    txt_path = Path(f"{path.as_posix()}.diagnostics.txt")
    write_json_atomic(
        json_path,
        aggregator.to_json(),
        indent=2,
        sort_keys=True,
        trailing_newline=True,
        durable=True,
    )
    txt_path.write_text(aggregator.to_text(), encoding="utf-8")
    return json_path, txt_path


def record_load_attempt(
    *,
    kind: str,
    path: Path | None,
    ok: bool,
    aggregator: SaveDiagnosticsAggregator,
) -> None:
    _update_last_attempt(
        slot="load",
        kind=kind,
        path=path,
        ok=ok,
        aggregator=aggregator,
    )


def format_load_error(prefix: str, aggregator: SaveDiagnosticsAggregator) -> str:
    return _diagnostic_message(prefix, aggregator)


def _record_sidecar_write_failure(
    *,
    aggregator: SaveDiagnosticsAggregator,
    path: Path,
    source: str,
    exc: Exception,
) -> None:
    aggregator.add(
        (
            _diagnostic(
                level=DiagnosticLevel.WARN,
                code="save.load.sidecar_write_failed",
                message=f"{type(exc).__name__}: {exc}",
                file_label=normalize_path(path),
                pointer="$",
                hint=f"Unable to write diagnostics sidecars for {source}.",
            ),
        )
    )


def write_json_pretty_atomic(path: Path, payload: Any) -> None:
    aggregator = SaveDiagnosticsAggregator()
    try:
        normalized_payload = payload
        if isinstance(payload, dict):
            normalized_payload, norm_diags = normalize_save_payload(
                payload,
                source=normalize_path(path),
            )
            aggregator.add(norm_diags)
        write_json_atomic(
            path,
            normalized_payload,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
            durable=True,
        )
        _update_last_attempt(slot="save", kind="write_json", path=path, ok=True, aggregator=aggregator)
    except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
        aggregator.add_exception(
            "save.write.failed",
            exc,
            source=normalize_path(path),
            pointer="$",
            hint="Check write permissions and parent directory.",
        )
        _update_last_attempt(slot="save", kind="write_json", path=path, ok=False, aggregator=aggregator)
        try:
            write_diagnostics_sidecars(path, aggregator)
        except Exception as sidecar_exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("SRIO-001", "engine/save_runtime/io.py blanket swallow", once=True)
            _record_sidecar_write_failure(
                aggregator=aggregator,
                path=path,
                source="write_json_pretty_atomic",
                exc=sidecar_exc,
            )
        raise


def _diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    file_label: str,
    pointer: str = "$",
    hint: str | None = None,
    context_extra: dict[str, Any] | None = None,
) -> Diagnostic:
    context: dict[str, Any] = {
        "file": file_label,
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


def _source_label(source: str, payload_input: Any) -> str:
    if isinstance(payload_input, Path):
        return normalize_path(payload_input)
    source_text = str(source or "").strip()
    if source_text:
        return normalize_path(source_text)
    return "<memory>"


def _read_payload(path_or_text: Any) -> Any:
    if isinstance(path_or_text, Path):
        return read_json(path_or_text)
    if isinstance(path_or_text, bytes):
        return json.loads(path_or_text.decode("utf-8"))
    if isinstance(path_or_text, str):
        stripped = path_or_text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(path_or_text)
        return read_json(Path(path_or_text))
    return path_or_text


def load_and_validate_payload(
    path_or_text: Any,
    *,
    source: str,
    strict_schema: bool | None = None,
    aggregator: SaveDiagnosticsAggregator | None = None,
    policy: RestorePolicy | None = None,
) -> tuple[bool, dict[str, Any] | None, tuple[Diagnostic, ...]]:
    """Load + migrate + validate save payload with deterministic diagnostics."""
    file_label = _source_label(source, path_or_text)
    diagnostics: list[Diagnostic] = []
    strict_schema_effective = (
        bool(policy.strict_schema)
        if policy is not None
        else bool(True if strict_schema is None else strict_schema)
    )

    try:
        raw_payload = _read_payload(path_or_text)
    except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("SRIO-002", "engine/save_runtime/io.py blanket swallow", once=True)
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.read_error",
                message=str(exc),
                file_label=file_label,
                hint="Ensure the save file exists and contains valid JSON.",
            )
        )
        ordered = sort_diagnostics(diagnostics)
        if aggregator is not None:
            aggregator.add(ordered)
        return False, None, ordered

    if not isinstance(raw_payload, dict):
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.invalid_root",
                message="Save payload must be an object",
                file_label=file_label,
                hint="Top-level JSON must be an object.",
            )
        )
        ordered = sort_diagnostics(diagnostics)
        if aggregator is not None:
            aggregator.add(ordered)
        return False, None, ordered

    payload = dict(raw_payload)
    try:
        payload = migrate_save_payload(payload)
    except ValueError as exc:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.format_migration_error",
                message=str(exc),
                file_label=file_label,
                pointer="$/save_format_version",
                hint="Update the save to a supported save_format_version.",
            )
        )
        ordered = sort_diagnostics(diagnostics)
        if aggregator is not None:
            aggregator.add(ordered)
        return False, None, ordered

    try:
        payload = migrate_save(payload)
    except SaveValidationError as exc:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.schema_migration_error",
                message=str(exc),
                file_label=file_label,
                pointer=f"$/{exc.path}" if exc.path else "$",
                hint="Fix malformed schema fields before loading.",
            )
        )
        ordered = sort_diagnostics(diagnostics)
        if aggregator is not None:
            aggregator.add(ordered)
        return False, None, ordered
    except ValueError as exc:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.schema_migration_error",
                message=str(exc),
                file_label=file_label,
                pointer="$/save_schema_version",
                hint="Use a save created by this version or a compatible migrator.",
            )
        )
        ordered = sort_diagnostics(diagnostics)
        if aggregator is not None:
            aggregator.add(ordered)
        return False, None, ordered

    if strict_schema_effective:
        try:
            validate_save(payload)
        except SaveValidationError as exc:
            diagnostics.append(
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.load.schema_validation_error",
                    message=str(exc),
                    file_label=file_label,
                    pointer=f"$/{exc.path}" if exc.path else "$",
                    hint="Correct the invalid field type/value in the save payload.",
                )
            )
            ordered = sort_diagnostics(diagnostics)
            if aggregator is not None:
                aggregator.add(ordered)
            return False, None, ordered
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("SRIO-003", "engine/save_runtime/io.py blanket swallow", once=True)
            diagnostics.append(
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="save.load.schema_validation_error",
                    message=str(exc),
                    file_label=file_label,
                    pointer="$",
                    hint="Inspect schema fields and rerun validation.",
                )
            )
            ordered = sort_diagnostics(diagnostics)
            if aggregator is not None:
                aggregator.add(ordered)
            return False, None, ordered
    else:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.WARN,
                code="save.load.schema_not_validated",
                message="Schema validation skipped (compat mode)",
                file_label=file_label,
                context_extra={"schema_not_validated": True},
                hint="Enable strict schema validation for slot-safe loading.",
            )
        )

    ordered = sort_diagnostics(diagnostics)
    normalized_payload, normalize_diags = normalize_save_payload(
        payload,
        source=file_label,
    )
    ordered = sort_diagnostics((*ordered, *normalize_diags))
    if aggregator is not None:
        aggregator.add(ordered)
    return True, normalized_payload, ordered


def _diagnostic_message(prefix: str, aggregator: SaveDiagnosticsAggregator) -> str:
    primary = aggregator.primary()
    if primary is None:
        return f"{prefix} ERROR: unknown load failure"
    ctx = primary.context if isinstance(primary.context, dict) else {}
    file_label = str(ctx.get("file", "") or ctx.get("source", "") or "")
    pointer = str(ctx.get("pointer", "") or "")
    parts = [single_line_error(primary.message)]
    meta: list[str] = [f"code={primary.code}"]
    if file_label:
        meta.append(f"file={file_label}")
    if pointer:
        meta.append(f"pointer={pointer}")
    if primary.hint:
        meta.append(f"hint={single_line_error(primary.hint)}")
    parts.append(f"[{', '.join(meta)}]")
    return f"{prefix} ERROR: {' '.join(parts)}"


def load_snapshot_payload(
    path: Path,
    *,
    policy: RestorePolicy = SNAPSHOT_POLICY,
) -> tuple[bool, dict[str, Any] | str]:
    if not path.exists():
        return False, ""

    aggregator = SaveDiagnosticsAggregator()
    ok, payload, diagnostics = load_and_validate_payload(
        path,
        source=str(path),
        strict_schema=policy.strict_schema,
        aggregator=aggregator,
        policy=policy,
    )
    _update_last_attempt(slot="load", kind="snapshot", path=path, ok=bool(ok), aggregator=aggregator)
    if ok and payload is not None:
        return True, payload
    if diagnostics:
        try:
            write_diagnostics_sidecars(path, aggregator)
        except Exception as sidecar_exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("SRIO-004", "engine/save_runtime/io.py blanket swallow", once=True)
            _record_sidecar_write_failure(
                aggregator=aggregator,
                path=path,
                source="load_snapshot_payload",
                exc=sidecar_exc,
            )
        return False, _diagnostic_message("[Mesh][Snapshot]", aggregator)
    return False, ""


def load_slot_payload(
    path: Path,
    *,
    policy: RestorePolicy = SLOT_POLICY,
) -> tuple[bool, dict[str, Any] | str]:
    if not path.exists():
        return False, f"[Mesh][Save] Save file '{path}' not found"

    aggregator = SaveDiagnosticsAggregator()
    ok, payload, diagnostics = load_and_validate_payload(
        path,
        source=str(path),
        strict_schema=policy.strict_schema,
        aggregator=aggregator,
        policy=policy,
    )
    _update_last_attempt(slot="load", kind="slot", path=path, ok=bool(ok), aggregator=aggregator)
    if ok and payload is not None:
        return True, payload
    try:
        write_diagnostics_sidecars(path, aggregator)
    except Exception as sidecar_exc:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("SRIO-005", "engine/save_runtime/io.py blanket swallow", once=True)
        _record_sidecar_write_failure(
            aggregator=aggregator,
            path=path,
            source="load_slot_payload",
            exc=sidecar_exc,
        )
    return False, _diagnostic_message("[Mesh][Save]", aggregator)


def write_snapshot_atomic(path: Path, payload: dict[str, Any]) -> None:
    write_json_pretty_atomic(path, payload)
