from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path


def encode_state(type_id: str, version: int, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(type_id),
        "state_version": int(version),
        "state": dict(state),
    }


def _diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str,
    hint: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=message,
        context={
            "pointer": pointer,
            "source": normalize_path(source),
        },
        hint=hint,
    )


def decode_state(
    payload: Mapping[str, Any] | None,
    expected_type_id: str,
    supported_versions: set[int],
    *,
    strict: bool,
    source: str,
    legacy_v0_predicate: Callable[[Mapping[str, Any]], bool] | None = None,
    legacy_v0_adapter: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    source_label = str(source or "<unknown>")

    if payload is None:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_MISSING",
                message="Missing state payload at '$'.",
                source=source_label,
                pointer="$",
                hint=f"Expected wrapped state for type '{expected_type_id}'.",
            )
        )
        return None, list(sort_diagnostics(diagnostics))

    if not isinstance(payload, Mapping):
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_NOT_OBJECT",
                message="State payload at '$' must be an object.",
                source=source_label,
                pointer="$",
                hint="Provide a JSON object with type/state_version/state keys.",
            )
        )
        return None, list(sort_diagnostics(diagnostics))

    payload_obj: dict[str, Any] = {str(key): value for key, value in payload.items()}

    has_wrapper = (
        "type" in payload_obj
        and "state_version" in payload_obj
        and "state" in payload_obj
    )
    if (
        not strict
        and not has_wrapper
        and legacy_v0_predicate is not None
        and legacy_v0_adapter is not None
        and legacy_v0_predicate(payload_obj)
    ):
        adapted = legacy_v0_adapter(payload_obj)
        if not isinstance(adapted, dict):
            diagnostics.append(
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SAVE_STATE_STATE_NOT_OBJECT",
                    message="Legacy adapter output at '/state' must be an object.",
                    source=source_label,
                    pointer="/state",
                    hint="Return a dict from legacy_v0_adapter.",
                )
            )
            return None, list(sort_diagnostics(diagnostics))

        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.WARN,
                code="SAVE_STATE_LEGACY_UPGRADED",
                message="Legacy v0 state payload upgraded to wrapped format.",
                source=source_label,
                pointer="$",
                hint="Re-save to persist wrapped state format.",
            )
        )
        return dict(adapted), list(sort_diagnostics(diagnostics))

    type_value = payload_obj.get("type")
    if not isinstance(type_value, str) or not type_value.strip():
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_TYPE_MISMATCH",
                message="Missing or invalid '/type' in state payload.",
                source=source_label,
                pointer="/type",
                hint=f"Expected type='{expected_type_id}'.",
            )
        )
    elif type_value != expected_type_id:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_TYPE_MISMATCH",
                message=f"Type mismatch at '/type': expected '{expected_type_id}', got '{type_value}'.",
                source=source_label,
                pointer="/type",
                hint=f"Use payload type='{expected_type_id}'.",
            )
        )

    if "state_version" not in payload_obj:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_VERSION_MISSING",
                message="Missing '/state_version' in state payload.",
                source=source_label,
                pointer="/state_version",
                hint="Include integer state_version.",
            )
        )
        state_version: int | None = None
    else:
        raw_version = payload_obj.get("state_version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            diagnostics.append(
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SAVE_STATE_VERSION_INVALID",
                    message=f"Invalid '/state_version': expected int, got '{type(raw_version).__name__}'.",
                    source=source_label,
                    pointer="/state_version",
                    hint="Use an integer state_version.",
                )
            )
            state_version = None
        else:
            state_version = int(raw_version)
            if state_version not in supported_versions:
                versions_text = ",".join(str(v) for v in sorted(supported_versions))
                diagnostics.append(
                    _diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SAVE_STATE_VERSION_UNSUPPORTED",
                        message=f"Unsupported '/state_version'={state_version}.",
                        source=source_label,
                        pointer="/state_version",
                        hint=f"Supported versions: {versions_text}.",
                    )
                )

    if "state" not in payload_obj:
        diagnostics.append(
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SAVE_STATE_STATE_MISSING",
                message="Missing '/state' in state payload.",
                source=source_label,
                pointer="/state",
                hint="Include object payload under /state.",
            )
        )
        inner_state: dict[str, Any] | None = None
    else:
        raw_state = payload_obj.get("state")
        if not isinstance(raw_state, Mapping):
            diagnostics.append(
                _diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SAVE_STATE_STATE_NOT_OBJECT",
                    message="Invalid '/state': expected object payload.",
                    source=source_label,
                    pointer="/state",
                    hint="Provide a JSON object for /state.",
                )
            )
            inner_state = None
        else:
            inner_state = {str(key): value for key, value in raw_state.items()}

    ordered = list(sort_diagnostics(diagnostics))
    if ordered:
        return None, ordered

    if inner_state is None:
        return None, ordered
    return inner_state, ordered
