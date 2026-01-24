from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from engine.config import load_config
from engine.content_lock import build_lock, compute_content_fingerprint, read_lock
from engine.tooling import check, validate_all
from engine.tooling.tool_result import Issue, ToolResult


@dataclass(frozen=True)
class ToolRun:
    name: str
    exit_code: int
    output: str


class DoctorRunner:
    def __init__(self, lock_path: Path | None = None) -> None:
        self.lock_path = lock_path or Path("content.lock.json")

    def run_result(self, *, world: Optional[str]) -> ToolResult:
        target_path, target_err = self._resolve_target_path(world)
        issues: list[Issue] = []
        suggested: list[str] = []
        runs: list[ToolRun] = []

        if target_err:
            issues.append(Issue(code="doctor", message=target_err, severity="error"))
            suggested.append("mesh doctor --world worlds/main_world.json")
            return ToolResult.from_issues(
                issues,
                suggestions=suggested,
                meta={"target": target_path, "runs": [self._run_to_dict(r) for r in runs]},
            )

        assert target_path is not None
        if "dist" in Path(target_path).parts:
            issues.append(Issue(code="doctor", message=f"Refusing to read from dist/: {target_path}", severity="error"))
            suggested.append("mesh doctor --world worlds/main_world.json")
            return ToolResult.from_issues(
                issues,
                suggestions=suggested,
                meta={"target": target_path, "runs": [self._run_to_dict(r) for r in runs]},
            )

        # 1) validate-all (canonical validation)
        v_run = self._run_tool("validate-all", lambda: validate_all.main([target_path]))
        runs.append(v_run)
        v_errs, v_warns = self._extract_validate_all_findings(v_run.output)
        issues.extend(Issue(code="validate-all", message=msg, severity="error") for msg in v_errs)
        issues.extend(Issue(code="validate-all", message=msg, severity="warn") for msg in v_warns)
        if v_run.exit_code != 0:
            suggested.append(f"mesh validate-all {target_path}")
            return ToolResult.failure(
                exit_code=1,
                issues=issues,
                suggestions=suggested,
                meta={"target": target_path, "runs": [self._run_to_dict(r) for r in runs]},
            )

        # 2) check gate (quality gate)
        c_run = self._run_tool(
            "check",
            lambda: 0 if check.run_check(target_path, full=False, replay_trace=None, frozen=False) else 1,
        )
        runs.append(c_run)
        if c_run.exit_code != 0:
            issues.append(Issue(code="check", message="Quality gate failed. Fix reported issues and rerun.", severity="error"))
            suggested.append(f"mesh check --world {target_path}")
            return ToolResult.from_issues(
                issues,
                suggestions=suggested,
                meta={"target": target_path, "runs": [self._run_to_dict(r) for r in runs]},
            )

        # 3) lock audit / stale lock detection
        lock_run = self._run_lock_audit(target_path)
        if lock_run is not None:
            runs.append(lock_run)
            if lock_run.exit_code != 0:
                issues.append(Issue(code="lock", message="content.lock.json is out of date. Update it.", severity="error"))
                suggested.append("mesh lock-packs")
            else:
                if "WARN:" in lock_run.output:
                    issues.append(Issue(code="lock", message="content.lock.json not found. Generate one for reproducibility.", severity="warn"))
                    suggested.append("mesh lock-packs")

        return ToolResult.from_issues(
            issues,
            suggestions=suggested,
            meta={"target": target_path, "runs": [self._run_to_dict(r) for r in runs]},
        )

    def run(
        self,
        *,
        world: Optional[str],
        quiet: bool = False,
        json_output: bool = False,
    ) -> tuple[int, str]:
        exit_code, report = self.run_structured(world=world)
        return exit_code, self.format_report(report, quiet=quiet, json_output=json_output)

    def run_structured(self, *, world: Optional[str]) -> tuple[int, Dict[str, Any]]:
        result = self.run_result(world=world)
        report = result.to_doctor_report_dict()
        return int(result.exit_code), report

    def _resolve_target_path(self, world: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if world:
            return world, None

        cfg = load_config()
        if getattr(cfg, "world_file", None):
            return str(cfg.world_file), None

        return None, "No world provided and config has no world_file."

    def _run_tool(self, name: str, runner: Callable[[], int]) -> ToolRun:
        buf = io.StringIO()
        try:
            import contextlib

            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = int(runner())
        except SystemExit as e:  # noqa: BLE001
            code = int(e.code) if isinstance(e.code, int) else 1
        except Exception as e:  # noqa: BLE001
            code = 1
            buf.write(f"[DOCTOR][{name}] exception: {e}\n")
        return ToolRun(name=name, exit_code=code, output=buf.getvalue())

    def _run_to_dict(self, run: ToolRun) -> dict[str, Any]:
        return {"name": run.name, "exit_code": run.exit_code, "output": run.output}

    def _run_lock_audit(self, world_path: str) -> ToolRun | None:
        if "dist" in self.lock_path.resolve().parts:
            return None

        buf = io.StringIO()
        if not self.lock_path.exists():
            buf.write("[Mesh][Lock] WARN: content.lock.json not found\n")
            return ToolRun(name="lock", exit_code=0, output=buf.getvalue())

        try:
            current = build_lock(world_path=world_path)
            saved = read_lock(self.lock_path)
            curr_fp = compute_content_fingerprint(current)
            saved_fp = compute_content_fingerprint(saved)
            if curr_fp != saved_fp:
                buf.write("[Mesh][Lock] ERROR: content.lock.json is out of date\n")
                return ToolRun(name="lock", exit_code=1, output=buf.getvalue())
            buf.write("[Mesh][Lock] OK: content.lock.json is up to date\n")
            return ToolRun(name="lock", exit_code=0, output=buf.getvalue())
        except Exception as e:  # noqa: BLE001
            buf.write(f"[Mesh][Lock] ERROR: {e}\n")
            return ToolRun(name="lock", exit_code=1, output=buf.getvalue())

    def _extract_validate_all_findings(self, output: str) -> tuple[list[str], list[str]]:
        errs: list[str] = []
        warns: list[str] = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                except Exception:  # noqa: BLE001
                    payload = None
                if isinstance(payload, dict) and {"code", "path", "message"}.issubset(payload.keys()):
                    code = str(payload.get("code") or "")
                    msg = str(payload.get("message") or "").strip()
                    if not msg:
                        continue
                    if code.startswith("warn."):
                        warns.append(msg)
                    else:
                        errs.append(msg)
                    continue
            if "[Mesh][ValidateAll] ERROR:" in line:
                warns_part = line.split("[Mesh][ValidateAll] ERROR:", 1)[1].strip()
                errs.append(warns_part)
            if "[Mesh][ValidateAll] WARN:" in line:
                warns_part = line.split("[Mesh][ValidateAll] WARN:", 1)[1].strip()
                warns.append(warns_part)
        return errs, warns

    def _build_report(
        self,
        *,
        target_path: Optional[str],
        runs: List[ToolRun],
        errors: List[Dict[str, str]],
        warnings: List[Dict[str, str]],
        suggested: List[str],
    ) -> Dict[str, Any]:
        return {
            "version": 1,
            "target": target_path,
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "checks": len(runs),
            },
            "runs": [
                {"name": r.name, "exit_code": r.exit_code, "output": r.output}
                for r in runs
            ],
            "errors": list(errors),
            "warnings": list(warnings),
            "suggested_next_commands": list(dict.fromkeys(suggested)),
        }

    def format_report(
        self,
        report: Dict[str, Any],
        *,
        quiet: bool,
        json_output: bool,
        artifacts: List[str] | None = None,
    ) -> str:
        if json_output:
            checks = []
            # Add runs as checks
            for run in report.get("runs", []):
                checks.append(
                    {
                        "id": run["name"],
                        "ok": run["exit_code"] == 0,
                        "message": run["output"].splitlines()[0] if run["output"] else "Check ran",
                        "file": None,
                        "hint": None,
                    }
                )

            # Add specific issues
            for item in report.get("errors", []):
                checks.append(
                    {
                        "id": item.get("source"),
                        "ok": False,
                        "message": item.get("message"),
                        "file": item.get("file"),
                        "hint": item.get("hint"),
                    }
                )
            for item in report.get("warnings", []):
                checks.append(
                    {
                        "id": item.get("source"),
                        "ok": False,  # Warnings are considered issues
                        "message": item.get("message"),
                        "file": item.get("file"),
                        "hint": item.get("hint"),
                    }
                )

            output_obj = {
                "version": 1,
                "world": report.get("target"),
                "checks": checks,
                "next": report.get("suggested_next_commands"),
                "artifacts": artifacts or [],
            }
            return json.dumps(output_obj, indent=2) + "\n"

        summary = report["summary"]
        lines: list[str] = [f"[DOCTOR] Summary: errors={summary['errors']} warnings={summary['warnings']} checks={summary['checks']}"]

        if not quiet:
            lines.append("[DOCTOR] Errors:")
            if report["errors"]:
                for item in report["errors"]:
                    lines.append(f"  - {item['message']}")
            else:
                lines.append("  - (none)")

            lines.append("[DOCTOR] Warnings:")
            if report["warnings"]:
                for item in report["warnings"]:
                    lines.append(f"  - {item['message']}")
            else:
                lines.append("  - (none)")

        lines.append("[DOCTOR] Suggested next commands:")
        if report["suggested_next_commands"]:
            for cmd in report["suggested_next_commands"]:
                lines.append(f"  - {cmd}")
        else:
            lines.append("  - (none)")

        return "\n".join(lines) + "\n"
