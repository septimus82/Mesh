"""Legacy content-audit shim backed by deterministic content_integrity."""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.log_utils import normalize_path

logger = logging.getLogger(__name__)


_ID_FROM_QUOTES = re.compile(r"'([^']+)'")


def _extract_id(message: str, *, fallback: str) -> str:
    match = _ID_FROM_QUOTES.search(str(message))
    if match is not None:
        candidate = str(match.group(1)).strip()
        if candidate:
            return candidate
    return fallback


def _normalize_issue_file(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "<unknown>"
    return normalize_path(raw)


def _integrity_issues_from_report(report: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    all_issues = tuple(getattr(report, "errors", ())) + tuple(getattr(report, "warnings", ()))
    for issue in all_issues:
        rows.append(
            {
                "file": _normalize_issue_file(str(getattr(issue, "file", "<unknown>") or "<unknown>")),
                "pointer": str(getattr(issue, "pointer", "$") or "$"),
                "code": str(getattr(issue, "code", "content.integrity.issue") or "content.integrity.issue"),
                "message": str(getattr(issue, "message", "") or ""),
            }
        )
    rows.sort(key=lambda item: (item["file"], item["pointer"], item["code"], item["message"]))
    return rows


def _legacy_unused_sections(
    *,
    issues: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    unused_assets: list[dict[str, str]] = []
    unused_prefabs: list[dict[str, str]] = []
    unused_items: list[dict[str, str]] = []
    unused_quests: list[dict[str, str]] = []

    for issue in issues:
        code = issue["code"]
        file = issue["file"]
        pointer = issue["pointer"]
        message = issue["message"]
        if "prefab" in code:
            unused_prefabs.append(
                {
                    "id": _extract_id(message, fallback=f"{file}:{pointer}"),
                    "type": "prefab",
                }
            )
            continue
        if ".items." in code or "item" in code:
            unused_items.append(
                {
                    "id": _extract_id(message, fallback=f"{file}:{pointer}"),
                    "type": "item",
                }
            )
            continue
        if ".quests." in code or "quest" in code:
            unused_quests.append(
                {
                    "id": _extract_id(message, fallback=f"{file}:{pointer}"),
                    "type": "quest",
                }
            )
            continue
        unused_assets.append(
            {
                "path": file,
                "pack": "integrity",
                "type": "asset",
                "category": "data",
                "code": code,
            }
        )

    unused_assets.sort(key=lambda item: (item["path"], item["code"]))
    unused_prefabs.sort(key=lambda item: item["id"])
    unused_items.sort(key=lambda item: item["id"])
    unused_quests.sort(key=lambda item: item["id"])
    return unused_assets, unused_prefabs, unused_items, unused_quests


def _adapter_warnings(
    *,
    ignore_patterns: Optional[List[str]],
    allow_packs: Optional[List[str]],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if ignore_patterns:
        warnings.append(
            {
                "file": "<adapter>",
                "pointer": "$/ignore_patterns",
                "code": "content.audit_legacy.ignore_patterns_ignored",
                "message": "legacy ignore_patterns is ignored by content_integrity shim",
            }
        )
    if allow_packs:
        warnings.append(
            {
                "file": "<adapter>",
                "pointer": "$/allow_packs",
                "code": "content.audit_legacy.allow_packs_ignored",
                "message": "legacy allow_packs is ignored by content_integrity shim",
            }
        )
    warnings.sort(key=lambda item: (item["file"], item["pointer"], item["code"], item["message"]))
    return warnings


def _build_legacy_report(
    *,
    world_path: str,
    ignore_patterns: Optional[List[str]],
    allow_packs: Optional[List[str]],
) -> Dict[str, Any]:
    modern = _run_content_integrity_audit(Path.cwd())
    integrity_issues = _integrity_issues_from_report(modern)
    adapter_warnings = _adapter_warnings(ignore_patterns=ignore_patterns, allow_packs=allow_packs)

    all_issue_rows = list(integrity_issues)
    all_issue_rows.extend(adapter_warnings)
    all_issue_rows.sort(key=lambda item: (item["file"], item["pointer"], item["code"], item["message"]))

    unused_assets, unused_prefabs, unused_items, unused_quests = _legacy_unused_sections(issues=all_issue_rows)

    total_assets = len(getattr(modern, "digests", ()))
    referenced_assets = max(0, total_assets - len(unused_assets))

    stats: dict[str, Any] = {
        "total_assets": total_assets,
        "referenced_assets": referenced_assets,
        "unused_assets_count": len(unused_assets),
        "unused_prefabs_count": len(unused_prefabs),
        "unused_items_count": len(unused_items),
        "unused_quests_count": len(unused_quests),
        "unused_by_category": {
            "audio": 0,
            "data": len(unused_assets),
            "texture": 0,
        },
        "integrity_error_count": len(getattr(modern, "errors", ())),
        "integrity_warning_count": len(getattr(modern, "warnings", ())) + len(adapter_warnings),
    }

    return {
        "ok": bool(getattr(modern, "ok", False)),
        "world_path": normalize_path(world_path),
        "unused_assets": unused_assets,
        "unused_prefabs": unused_prefabs,
        "unused_items": unused_items,
        "unused_quests": unused_quests,
        "stats": stats,
        "integrity_issues": all_issue_rows,
        "integrity": {
            "schema_version": int(getattr(modern, "schema_version", 1)),
            "report": modern.to_dict(),
        },
    }


def _run_content_integrity_audit(project_root: Path) -> Any:
    module = importlib.import_module("mesh_cli.content_integrity")
    run_fn = getattr(module, "run_content_audit")
    return run_fn(project_root)


@dataclass(slots=True)
class ContentAuditor:
    """Legacy adapter class kept for tooling compatibility."""

    world_path: str = "worlds/main_world.json"
    ref_assets: set[str] = field(default_factory=set)
    ref_prefabs: set[str] = field(default_factory=set)
    ref_items: set[str] = field(default_factory=set)
    ref_quests: set[str] = field(default_factory=set)
    def_prefabs: set[str] = field(default_factory=set)
    def_items: set[str] = field(default_factory=set)
    def_quests: set[str] = field(default_factory=set)
    available_files: Dict[str, str] = field(default_factory=dict)

    def audit(
        self,
        ignore_patterns: Optional[List[str]] = None,
        allow_packs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        report = audit_world(self.world_path, ignore_patterns=ignore_patterns, allow_packs=allow_packs)
        self.available_files = {
            str(item.get("file", "")): "integrity"
            for item in report.get("integrity_issues", [])
            if isinstance(item, dict) and item.get("file")
        }
        self.def_prefabs = {str(item.get("id", "")) for item in report.get("unused_prefabs", []) if item.get("id")}
        self.def_items = {str(item.get("id", "")) for item in report.get("unused_items", []) if item.get("id")}
        self.def_quests = {str(item.get("id", "")) for item in report.get("unused_quests", []) if item.get("id")}
        self.ref_assets = set()
        self.ref_prefabs = set()
        self.ref_items = set()
        self.ref_quests = set()
        return report

    def _build_report(
        self,
        ignore_patterns: Optional[List[str]] = None,
        allow_packs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.audit(ignore_patterns=ignore_patterns, allow_packs=allow_packs)

    def _scan_index(self) -> None:
        return None

    def _scan_definitions(self) -> None:
        return None

    def _scan_world(self) -> None:
        return None

    def _scan_scene(self, _path: str) -> None:
        return None

    def _scan_entity(self, _entity: Dict[str, Any]) -> None:
        return None


def audit_world(
    world_path: str = "worlds/main_world.json",
    ignore_patterns: Optional[List[str]] = None,
    allow_packs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Legacy convenience wrapper backed by deterministic content_integrity."""
    return _build_legacy_report(
        world_path=world_path,
        ignore_patterns=ignore_patterns,
        allow_packs=allow_packs,
    )


def run_content_audit(
    world_path: str = "worlds/main_world.json",
    ignore_patterns: Optional[List[str]] = None,
    allow_packs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Legacy entrypoint retained for callers expecting run_content_audit()."""
    return audit_world(
        world_path=world_path,
        ignore_patterns=ignore_patterns,
        allow_packs=allow_packs,
    )
