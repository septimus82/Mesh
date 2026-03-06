from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Iterable, Mapping


class DiagnosticLevel(str, Enum):
    ERROR = "error"
    WARN = "warning"
    INFO = "info"

    @classmethod
    def coerce(cls, value: Any) -> "DiagnosticLevel":
        if isinstance(value, DiagnosticLevel):
            return value
        raw = str(value or "").strip().lower()
        if raw in {"error", "err"}:
            return DiagnosticLevel.ERROR
        if raw in {"warn", "warning"}:
            return DiagnosticLevel.WARN
        if raw in {"info", "information"}:
            return DiagnosticLevel.INFO
        return DiagnosticLevel.WARN


_LEVEL_ORDER: dict[DiagnosticLevel, int] = {
    DiagnosticLevel.ERROR: 0,
    DiagnosticLevel.WARN: 1,
    DiagnosticLevel.INFO: 2,
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    # Legacy surface (used broadly in save/runtime + CLI tooling).
    level: DiagnosticLevel
    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)
    hint: str | None = None
    # Additive structured fields used by the new sink/pipeline.
    source: str | None = None
    location: str | None = None
    _seq: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", DiagnosticLevel.coerce(self.level))
        object.__setattr__(self, "code", str(self.code or "").strip() or "diagnostic.unknown")
        object.__setattr__(self, "message", str(self.message or "").strip() or "diagnostic message missing")
        object.__setattr__(self, "hint", None if self.hint is None else str(self.hint))
        object.__setattr__(self, "source", None if self.source is None else str(self.source))
        object.__setattr__(self, "location", None if self.location is None else str(self.location))
        # Freeze as a plain dict with deterministic key ordering in serialization.
        object.__setattr__(self, "context", dict(self.context or {}))

    @property
    def severity(self) -> str:
        return self.level.value

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "level": self.level.value,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        source = self.source or str((self.context or {}).get("source", "") or "").strip()
        if source:
            payload["source"] = source
        if self.location:
            payload["location"] = self.location
        if self.hint:
            payload["hint"] = self.hint
        if self.context:
            payload["context"] = dict(sorted(self.context.items(), key=lambda item: str(item[0])))
        return payload

    # Alias used by some new wiring code.
    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Diagnostic":
        context_value = payload.get("context")
        context = dict(context_value) if isinstance(context_value, Mapping) else {}
        level_raw = payload.get("level", payload.get("severity", "warning"))
        return cls(
            level=DiagnosticLevel.coerce(level_raw),
            code=str(payload.get("code", "diagnostic.unknown") or "diagnostic.unknown"),
            message=str(payload.get("message", "diagnostic message missing") or "diagnostic message missing"),
            context=context,
            hint=(None if payload.get("hint") is None else str(payload.get("hint"))),
            source=(None if payload.get("source") is None else str(payload.get("source"))),
            location=(None if payload.get("location") is None else str(payload.get("location"))),
        )


def _diagnostic_sort_key(item: Diagnostic) -> tuple[int, str, str, str, str, str, tuple[tuple[str, str], ...], int]:
    context = item.context if isinstance(item.context, Mapping) else {}
    context_pairs = tuple(sorted((str(k), repr(v)) for k, v in context.items()))
    source = item.source or str(context.get("source", "") or "")
    location = item.location or str(context.get("pointer", "") or "")
    return (
        _LEVEL_ORDER.get(item.level, 99),
        item.code,
        item.message,
        source,
        location,
        item.hint or "",
        context_pairs,
        int(item._seq),
    )


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(sorted(tuple(diagnostics), key=_diagnostic_sort_key))


def diagnostics_to_json(diagnostics: Iterable[Diagnostic]) -> str:
    ordered = sort_diagnostics(diagnostics)
    payload = [item.to_dict() for item in ordered]
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def diagnostics_to_text(diagnostics: Iterable[Diagnostic]) -> str:
    ordered = sort_diagnostics(diagnostics)
    lines: list[str] = []
    for item in ordered:
        lines.append(f"[{item.severity}] {item.code}: {item.message}")
        context = item.context if isinstance(item.context, Mapping) else {}
        source = item.source or str(context.get("source", "") or "")
        location = item.location or ""
        if source:
            lines.append(f"  source: {source}")
        if location:
            lines.append(f"  location: {location}")
        if context:
            parts = [f"{str(k)}={context[k]}" for k in sorted(context.keys(), key=lambda key: str(key))]
            lines.append(f"  context: {', '.join(parts)}")
        if item.hint:
            lines.append(f"  hint: {item.hint}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


class DiagnosticsSink:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: list[Diagnostic] = []
        self._seq = 0

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._seq = 0

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        source: str,
        *,
        location: str | None = None,
        context: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> Diagnostic:
        normalized_level = DiagnosticLevel.coerce(severity)
        normalized_code = str(code or "").strip() or "diagnostic.unknown"
        normalized_message = str(message or "").strip() or normalized_code
        normalized_source = str(source or "").strip() or "unknown"
        normalized_location = str(location).strip() if location is not None else None
        normalized_context = dict(context or {})
        normalized_hint = None if hint is None else str(hint).strip() or None
        with self._lock:
            self._seq += 1
            diagnostic = Diagnostic(
                level=normalized_level,
                code=normalized_code,
                message=normalized_message,
                source=normalized_source,
                location=normalized_location,
                context=normalized_context,
                hint=normalized_hint,
                _seq=self._seq,
            )
            self._items.append(diagnostic)
            return diagnostic

    def warn(
        self,
        code: str,
        message: str,
        source: str,
        *,
        location: str | None = None,
        context: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> Diagnostic:
        return self.add("warning", code, message, source, location=location, context=context, hint=hint)

    def error(
        self,
        code: str,
        message: str,
        source: str,
        *,
        location: str | None = None,
        context: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> Diagnostic:
        return self.add("error", code, message, source, location=location, context=context, hint=hint)

    def info(
        self,
        code: str,
        message: str,
        source: str,
        *,
        location: str | None = None,
        context: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> Diagnostic:
        return self.add("info", code, message, source, location=location, context=context, hint=hint)

    def add_exception(
        self,
        code: str,
        exc: Exception,
        source: str,
        *,
        location: str | None = None,
        context: Mapping[str, Any] | None = None,
        severity: str = "error",
        hint: str | None = None,
    ) -> Diagnostic:
        message = f"{type(exc).__name__}: {exc}"
        return self.add(
            severity=severity,
            code=code,
            message=message,
            source=source,
            location=location,
            context=context,
            hint=hint,
        )

    def get_all(self) -> list[Diagnostic]:
        with self._lock:
            return list(sort_diagnostics(self._items))

    def as_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.get_all()]


_DEFAULT_SINK = DiagnosticsSink()


def get_sink() -> DiagnosticsSink:
    return _DEFAULT_SINK


def clear_diagnostics() -> None:
    _DEFAULT_SINK.clear()


def get_diagnostics() -> list[Diagnostic]:
    return _DEFAULT_SINK.get_all()


def get_diagnostics_payload() -> list[dict[str, Any]]:
    return _DEFAULT_SINK.as_dicts()


def warn(
    code: str,
    message: str,
    source: str,
    *,
    location: str | None = None,
    context: Mapping[str, Any] | None = None,
    hint: str | None = None,
) -> Diagnostic:
    return _DEFAULT_SINK.warn(code, message, source, location=location, context=context, hint=hint)


def error(
    code: str,
    message: str,
    source: str,
    *,
    location: str | None = None,
    context: Mapping[str, Any] | None = None,
    hint: str | None = None,
) -> Diagnostic:
    return _DEFAULT_SINK.error(code, message, source, location=location, context=context, hint=hint)


def info(
    code: str,
    message: str,
    source: str,
    *,
    location: str | None = None,
    context: Mapping[str, Any] | None = None,
    hint: str | None = None,
) -> Diagnostic:
    return _DEFAULT_SINK.info(code, message, source, location=location, context=context, hint=hint)


def add_exception(
    code: str,
    exc: Exception,
    source: str,
    *,
    location: str | None = None,
    context: Mapping[str, Any] | None = None,
    severity: str = "error",
    hint: str | None = None,
) -> Diagnostic:
    return _DEFAULT_SINK.add_exception(
        code=code,
        exc=exc,
        source=source,
        location=location,
        context=context,
        severity=severity,
        hint=hint,
    )


__all__ = [
    "Diagnostic",
    "DiagnosticLevel",
    "DiagnosticsSink",
    "add_exception",
    "clear_diagnostics",
    "diagnostics_to_json",
    "diagnostics_to_text",
    "error",
    "info",
    "get_diagnostics",
    "get_diagnostics_payload",
    "get_sink",
    "sort_diagnostics",
    "warn",
]
