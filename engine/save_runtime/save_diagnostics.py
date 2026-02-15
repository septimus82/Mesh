from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from engine.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    diagnostics_to_json,
    diagnostics_to_text,
    sort_diagnostics,
)
from engine.log_utils import normalize_path
from engine.save_runtime.errors import single_line_error


class SaveDiagnosticsAggregator:
    """Deterministic collection/formatting for save and restore diagnostics."""

    def __init__(self) -> None:
        self._items: list[Diagnostic] = []
        self._sorted_cache: tuple[Diagnostic, ...] | None = None

    def add(self, diags: Iterable[Diagnostic]) -> None:
        for item in diags:
            if isinstance(item, Diagnostic):
                self._items.append(item)
                self._sorted_cache = None

    def add_exception(
        self,
        code: str,
        exc: Exception,
        *,
        source: str,
        pointer: str | None = None,
        hint: str | None = None,
    ) -> None:
        context: dict[str, Any] = {
            "source": normalize_path(str(source or "<unknown>")),
            "pointer": str(pointer or "$"),
        }
        self.add(
            (
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code=str(code or "save.restore.exception"),
                    message=single_line_error(f"{type(exc).__name__}: {exc}"),
                    context=context,
                    hint=(None if hint is None else single_line_error(hint)),
                ),
            )
        )

    def extend(self, other: "SaveDiagnosticsAggregator") -> None:
        if isinstance(other, SaveDiagnosticsAggregator):
            self.add(other.finalize_sorted())

    def has_errors(self) -> bool:
        return any(item.level == DiagnosticLevel.ERROR for item in self.finalize_sorted())

    def finalize_sorted(self) -> list[Diagnostic]:
        if self._sorted_cache is None:
            self._sorted_cache = sort_diagnostics(self._items)
        return list(self._sorted_cache)

    def counts(self) -> dict[str, int]:
        ordered = self.finalize_sorted()
        return {
            "total": len(ordered),
            "errors": sum(1 for item in ordered if item.level == DiagnosticLevel.ERROR),
            "warnings": sum(1 for item in ordered if item.level == DiagnosticLevel.WARN),
            "infos": sum(1 for item in ordered if item.level == DiagnosticLevel.INFO),
        }

    def to_json(self) -> dict[str, Any]:
        ordered = self.finalize_sorted()
        return {
            "counts": self.counts(),
            "diagnostics": [item.to_dict() for item in ordered],
            "diagnostics_json": diagnostics_to_json(ordered),
        }

    def to_text(self, max_lines: int = 50) -> str:
        ordered = self.finalize_sorted()
        raw_text = diagnostics_to_text(ordered)
        if max_lines <= 0:
            return ""
        lines = raw_text.splitlines()
        if len(lines) <= max_lines:
            return raw_text
        head = lines[:max_lines]
        omitted = len(lines) - max_lines
        head.append(f"... ({omitted} more line(s) omitted)")
        return "\n".join(head) + "\n"

    def primary(self) -> Diagnostic | None:
        ordered = self.finalize_sorted()
        if not ordered:
            return None
        return ordered[0]
