from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    severity: Severity
    path: Optional[str] = None
    scene: Optional[str] = None
    hint: Optional[str] = None
    fix_commands: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    ok: bool
    exit_code: int
    issues: list[Issue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        *,
        issues: Optional[list[Issue]] = None,
        suggestions: Optional[list[str]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> "ToolResult":
        return cls(
            ok=True,
            exit_code=0,
            issues=list(issues or []),
            suggestions=list(suggestions or []),
            meta=dict(meta or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        exit_code: int = 1,
        issues: Optional[list[Issue]] = None,
        suggestions: Optional[list[str]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> "ToolResult":
        return cls(
            ok=False,
            exit_code=int(exit_code) or 1,
            issues=list(issues or []),
            suggestions=list(suggestions or []),
            meta=dict(meta or {}),
        )

    @classmethod
    def from_issues(
        cls,
        issues: list[Issue],
        *,
        suggestions: Optional[list[str]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> "ToolResult":
        has_error = any(i.severity == "error" for i in issues)
        return cls(
            ok=not has_error,
            exit_code=1 if has_error else 0,
            issues=list(issues),
            suggestions=list(suggestions or []),
            meta=dict(meta or {}),
        )

    def to_doctor_report_dict(self) -> dict[str, Any]:
        target = self.meta.get("target")
        runs = list(self.meta.get("runs") or [])

        errors: list[dict[str, str | None]] = []
        warnings: list[dict[str, str | None]] = []
        for issue in self.issues:
            item: dict[str, str | None] = {
                "source": issue.code or "doctor",
                "message": issue.message,
                "file": issue.path,
                "hint": issue.hint,
            }
            if issue.severity == "error":
                errors.append(item)
            elif issue.severity == "warn":
                warnings.append(item)

        suggested = list(dict.fromkeys(self.suggestions))
        return {
            "version": 1,
            "target": target,
            "summary": {"errors": len(errors), "warnings": len(warnings), "checks": len(runs)},
            "runs": runs,
            "errors": errors,
            "warnings": warnings,
            "suggested_next_commands": suggested,
        }

    @classmethod
    def from_doctor_report_dict(cls, report: dict[str, Any]) -> "ToolResult":
        issues: list[Issue] = []
        for item in report.get("errors", []) or []:
            if isinstance(item, dict) and "message" in item:
                issues.append(
                    Issue(
                        code=str(item.get("source") or "doctor"),
                        message=str(item.get("message") or ""),
                        severity="error",
                        path=item.get("file"),
                        hint=item.get("hint"),
                    )
                )
        for item in report.get("warnings", []) or []:
            if isinstance(item, dict) and "message" in item:
                issues.append(
                    Issue(
                        code=str(item.get("source") or "doctor"),
                        message=str(item.get("message") or ""),
                        severity="warn",
                        path=item.get("file"),
                        hint=item.get("hint"),
                    )
                )

        suggested = list(report.get("suggested_next_commands", []) or [])
        runs = list(report.get("runs", []) or [])
        target = report.get("target")

        exit_code = 1 if int(report.get("summary", {}).get("errors", 0)) > 0 else 0
        return cls(
            ok=exit_code == 0,
            exit_code=exit_code,
            issues=issues,
            suggestions=suggested,
            meta={"target": target, "runs": runs},
        )
