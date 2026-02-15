from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from engine.persistence_io import dumps_json_deterministic


class DiagnosticLevel(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


_LEVEL_ORDER = {
    DiagnosticLevel.ERROR: 0,
    DiagnosticLevel.WARN: 1,
    DiagnosticLevel.INFO: 2,
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    level: DiagnosticLevel
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "code": str(self.code),
            "message": str(self.message),
            "context": {str(k): self.context[k] for k in sorted(self.context.keys())},
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Diagnostic":
        raw_level = str(payload.get("level", "info")).strip().lower()
        if raw_level == "error":
            level = DiagnosticLevel.ERROR
        elif raw_level == "warn":
            level = DiagnosticLevel.WARN
        else:
            level = DiagnosticLevel.INFO
        context_raw = payload.get("context")
        context = context_raw if isinstance(context_raw, dict) else {}
        return cls(
            level=level,
            code=str(payload.get("code", "") or ""),
            message=str(payload.get("message", "") or ""),
            context={str(k): context[k] for k in sorted(context.keys())},
            hint=(None if payload.get("hint") is None else str(payload.get("hint"))),
        )


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    def _key(item: Diagnostic) -> tuple[int, str, str, str, str]:
        context_blob = dumps_json_deterministic(
            {str(k): item.context[k] for k in sorted(item.context.keys())},
            indent=None,
            sort_keys=True,
            trailing_newline=False,
        )
        return (
            _LEVEL_ORDER.get(item.level, 99),
            str(item.code),
            str(item.message),
            context_blob,
            "" if item.hint is None else str(item.hint),
        )

    return tuple(sorted(diagnostics, key=_key))


def diagnostics_to_json(diagnostics: Iterable[Diagnostic]) -> str:
    ordered = sort_diagnostics(tuple(diagnostics))
    payload = [item.to_dict() for item in ordered]
    return str(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))


def diagnostics_to_text(diagnostics: Iterable[Diagnostic]) -> str:
    ordered = sort_diagnostics(tuple(diagnostics))
    lines: list[str] = []
    for item in ordered:
        context = item.to_dict().get("context", {})
        if isinstance(context, dict) and context:
            context_part = ", ".join(f"{key}={context[key]}" for key in sorted(context.keys()))
            lines.append(f"[{item.level.value}] {item.code}: {item.message} ({context_part})")
        else:
            lines.append(f"[{item.level.value}] {item.code}: {item.message}")
        if item.hint:
            lines.append(f"  hint: {item.hint}")
    return ("\n".join(lines) + "\n") if lines else ""
