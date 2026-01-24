from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from engine.tooling.doctor import DoctorRunner
from engine.tooling.tool_result import ToolResult
from engine.tooling.issue_mapper import map_issue_to_hint


_DEFAULT_LAST_FAILURE_PATH = Path(".mesh") / "reports" / "doctor_last_failure.json"


class ExplainRunner:
    def __init__(
        self,
        *,
        doctor: DoctorRunner | None = None,
        last_failure_path: Path | None = None,
    ) -> None:
        self._doctor = doctor or DoctorRunner()
        self._last_failure_path = last_failure_path or _DEFAULT_LAST_FAILURE_PATH

    def run(
        self,
        *,
        world: Optional[str] = None,
        last: bool = False,
        json_output: bool = False,
    ) -> tuple[int, str]:
        if last:
            report = self.load_last_failure()
            if report is None:
                return 1, self._format_missing_last_failure(json_output=json_output)
            result = ToolResult.from_doctor_report_dict(report)
            return int(result.exit_code), self.explain_result(result, json_output=json_output)

        result = self._doctor.run_result(world=world)
        if result.exit_code != 0:
            self.store_last_failure(result)
        return int(result.exit_code), self.explain_result(result, json_output=json_output)

    def store_last_failure(self, report: Dict[str, Any] | ToolResult) -> None:
        if isinstance(report, ToolResult):
            report = report.to_doctor_report_dict()
        self._last_failure_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_failure_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load_last_failure(self) -> Dict[str, Any] | None:
        if not self._last_failure_path.exists():
            return None
        try:
            return json.loads(self._last_failure_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def explain_result(self, result: ToolResult, *, json_output: bool) -> str:
        return self.explain_report(result.to_doctor_report_dict(), json_output=json_output)

    def explain_report(self, report: Dict[str, Any], *, json_output: bool) -> str:
        groups = self._build_groups(report)
        if json_output:
            summary = f"Found {len(report.get('errors', []))} errors and {len(report.get('warnings', []))} warnings."
            root_causes = []
            files = set()
            suggested_fixes = []
            action_hints = []

            # Collect all issues to map to hints
            all_issues = []
            for item in report.get("errors", []):
                all_issues.append(item)
            for item in report.get("warnings", []):
                all_issues.append(item)
            
            for issue in all_issues:
                hint = map_issue_to_hint(issue.get("source", ""), issue.get("message", ""), issue.get("file"))
                if hint:
                    action_hints.append(hint)

            # Sort action_hints deterministically
            action_hints.sort(key=lambda x: (x["category"], x["target"], x["suggested_action"]))

            for group in groups:
                for issue in group["issues"]:
                    root_causes.append(issue["why"])
                    if issue["where"] and issue["where"] != "(unknown)":
                        files.add(issue["where"])
                    suggested_fixes.extend(issue["suggested_commands"])

            payload = {
                "version": 1,
                "summary": summary,
                "root_causes": list(dict.fromkeys(root_causes)),
                "files": sorted(list(files)),
                "suggested_fixes": list(dict.fromkeys(suggested_fixes)),
                "action_hints": action_hints,
            }
            return json.dumps(payload, indent=2, sort_keys=True) + "\n"
        return self._format_groups(groups)

    def _format_missing_last_failure(self, *, json_output: bool) -> str:
        if json_output:
            return (
                json.dumps(
                    {
                        "version": 1,
                        "summary": "No stored failure found.",
                        "root_causes": ["Explain --last needs a prior failing run to reference."],
                        "files": [".mesh/reports/doctor_last_failure.json"],
                        "suggested_fixes": ["mesh explain"],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

        return "\n".join(
            [
                "[EXPLAIN] plan: last",
                "  WHAT: No stored failure found.",
                "  WHY: Explain --last needs a prior failing run to reference.",
                "  WHERE: .mesh/reports/doctor_last_failure.json",
                "  FIX:",
                "    - mesh explain",
                "",
            ]
        )

    def _format_groups(self, groups: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for group in groups:
            lines.append(f"[EXPLAIN] {group['type']}: {group['id']}")
            for issue in group["issues"]:
                lines.append(f"  WHAT: {issue['what']}")
                lines.append(f"  WHY: {issue['why']}")
                lines.append(f"  WHERE: {issue['where']}")
                lines.append("  FIX:")
                for cmd in issue["suggested_commands"]:
                    lines.append(f"    - {cmd}")
            lines.append("")
        return "\n".join(lines)

    def _build_groups(self, report: Dict[str, Any]) -> list[dict[str, Any]]:
        target = report.get("target") or "worlds/main_world.json"

        issues: list[tuple[str, dict[str, str]]] = []
        for item in report.get("errors", []):
            if isinstance(item, dict) and "message" in item:
                issues.append(("ERROR", item))
        for item in report.get("warnings", []):
            if isinstance(item, dict) and "message" in item:
                issues.append(("WARN", item))

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for severity, issue in issues:
            source = issue.get("source", "doctor")
            message = issue.get("message", "")
            group_type, group_id, where = self._classify_issue(message, source=source)
            grouped.setdefault((group_type, group_id), []).append(
                {
                    "what": f"{severity}: {message}",
                    "why": self._why_sentence(group_type),
                    "where": where,
                    "suggested_commands": [self._suggest_command(source, group_type, group_id, where, target=target)],
                }
            )

        order = {"scene": 0, "pack": 1, "prefab": 2, "plan": 3}
        groups: list[dict[str, Any]] = []
        for (g_type, g_id), g_issues in sorted(grouped.items(), key=lambda x: (order.get(x[0][0], 99), x[0][1])):
            groups.append({"type": g_type, "id": g_id, "issues": g_issues})
        return groups

    def _why_sentence(self, group_type: str) -> str:
        if group_type == "scene":
            return "Scenes must validate cleanly to load and run correctly."
        if group_type == "prefab":
            return "Prefab data drives spawning and budgeting; invalid metadata can break encounters."
        if group_type == "pack":
            return "Pack content must be consistent to build, validate, and ship reliably."
        return "Plans must apply cleanly to keep content consistent and reproducible."

    def _suggest_command(self, source: str, group_type: str, group_id: str, where: str, *, target: str) -> str:
        if source == "lock":
            return "mesh lock-packs"
        if source == "check":
            return f"mesh check --world {target}"
        if source == "validate-all":
            if group_type == "scene" and where and where != "(unknown)":
                return f"mesh validate-all {where}"
            return f"mesh validate-all {target}"
        return f"mesh doctor --world {target}"

    def _classify_issue(self, message: str, *, source: str) -> tuple[str, str, str]:
        prefab_id = self._extract_prefab_id(message)
        if prefab_id:
            return "prefab", prefab_id, f"assets/prefabs.json (id={prefab_id})"

        scene_path = self._extract_scene_path(message)
        if scene_path:
            where = self._pack_aware_path(scene_path)
            return "scene", where, where

        pack_id, pack_path = self._extract_pack(message)
        if pack_id:
            where = self._pack_aware_path(pack_path or f"packs/{pack_id}")
            return "pack", pack_id, where

        if source in {"lock", "check"}:
            return "pack", "project", where_for_source(source)

        plan_path = self._extract_plan_path(message)
        if plan_path:
            where = self._pack_aware_path(plan_path)
            return "plan", where, where

        return "pack", "project", "(unknown)"

    def _extract_prefab_id(self, message: str) -> str | None:
        match = re.search(r"\bPrefab\s+'([^']+)'", message)
        if match:
            return match.group(1)
        match = re.search(r"\bprefab\s+'([^']+)'", message)
        if match:
            return match.group(1)
        return None

    def _extract_scene_path(self, message: str) -> str | None:
        for pattern in (r"\bScene\s+([^:]+):", r"\bWorld\s+([^:]+):"):
            match = re.search(pattern, message)
            if match:
                return match.group(1).strip()

        path = self._extract_first_path(message)
        if path and any(seg in path.replace("\\", "/") for seg in ("/scenes/", "/worlds/")):
            return path
        return None

    def _extract_plan_path(self, message: str) -> str | None:
        path = self._extract_first_path(message)
        if path and "plan" in path.replace("\\", "/"):
            return path
        if "apply-plan" in message:
            return "plan.json"
        return None

    def _extract_pack(self, message: str) -> tuple[str | None, str | None]:
        match = re.search(r"(packs[\\/])([^\\/]+)", message)
        if not match:
            return None, None
        pack_id = match.group(2)
        path = self._extract_first_path(message)
        return pack_id, path

    def _extract_first_path(self, text: str) -> str | None:
        match = re.search(r"([A-Za-z]:[\\/][^\\s'\"\\)\\]]+\\.(?:json|md|txt|py))", text)
        if match:
            return match.group(1)
        match = re.search(r"((?:packs|assets|worlds|scenes)[\\/][^\\s'\"\\)\\]]+\\.(?:json|md|txt|py))", text)
        if match:
            return match.group(1)
        return None

    def _pack_aware_path(self, path_str: str) -> str:
        raw = path_str.strip()
        if not raw:
            return "(unknown)"

        try:
            parts = Path(raw).parts
        except Exception:
            return raw.replace("\\", "/")

        lowered = [p.lower() for p in parts]
        for anchor in ("packs", "assets", "worlds", "scenes"):
            if anchor in lowered:
                idx = lowered.index(anchor)
                return "/".join(parts[idx:]).replace("\\", "/")

        return raw.replace("\\", "/")


def where_for_source(source: str) -> str:
    if source == "lock":
        return "content.lock.json"
    if source == "check":
        return "mesh check"
    return "(unknown)"
