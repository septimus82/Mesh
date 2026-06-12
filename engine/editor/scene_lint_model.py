"""Pure scene lint model for editor Problems panel.

Detects common scene issues and provides deterministic, headless-safe helpers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, List, Literal

from .editor_shell_layout import TAB_HEADER_HEIGHT, Rect

PROBLEMS_LINE_HEIGHT = 18.0
PROBLEMS_PADDING = 8.0
PROBLEMS_DETAIL_LINES = 6
PROBLEMS_BUTTON_GAP = 6.0
PROBLEMS_SCAN_W = 48.0
PROBLEMS_FIX_ALL_W = 96.0


@dataclass(frozen=True, slots=True)
class ProblemsPanelLayout:
    """Layout rectangles for the Problems panel."""

    header_rect: Rect
    scan_rect: Rect
    fix_all_rect: Rect
    search_rect: Rect
    list_rect: Rect
    detail_rect: Rect


@dataclass(frozen=True, slots=True)
class SceneLintIssue:
    """Represents a single lint issue found in a scene."""

    issue_id: str
    kind: str
    message: str
    entity_id: str | None
    scene_id: str | None
    severity: str
    risk: Literal["safe", "risky"]
    fix_kind: str | None
    fixable: bool
    meta: dict[str, object] = field(default_factory=dict)


def build_scene_lint_issues(
    scene_json: dict[str, Any],
    repo_root: Path,
    *,
    prefab_resolver: Callable[[str], bool],
) -> list[SceneLintIssue]:
    """Build lint issues for a scene.

    Issues are returned in deterministic order.
    """
    issues: list[SceneLintIssue] = []
    entities = scene_json.get("entities")
    if not isinstance(entities, list):
        return []

    scene_id = _resolve_scene_id(scene_json)
    id_to_indices: dict[str, list[int]] = {}
    existing_ids: set[str] = set()
    missing_indices: list[int] = []

    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        raw_id = _extract_entity_id(entity)
        if raw_id:
            existing_ids.add(raw_id)
            id_to_indices.setdefault(raw_id, []).append(idx)
        else:
            missing_indices.append(idx)

    # Duplicate IDs
    used_ids = set(existing_ids)
    for dup_id in sorted(id_to_indices.keys()):
        indices = id_to_indices[dup_id]
        if len(indices) <= 1:
            continue
        renames: list[dict[str, object]] = []
        for idx in indices[1:]:
            new_id = _next_unique_id(used_ids, dup_id, "_fix_")
            used_ids.add(new_id)
            entity = entities[idx] if idx < len(entities) and isinstance(entities[idx], dict) else {}
            field_path = _resolve_id_field(entity)
            renames.append({"index": idx, "field_path": field_path, "after": new_id})
        issues.append(
            SceneLintIssue(
                issue_id=f"duplicate_id:{dup_id}",
                kind="DUPLICATE_ID",
                message=f"Duplicate entity id '{dup_id}'",
                entity_id=dup_id,
                scene_id=scene_id,
                severity="ERROR",
                risk="safe",
                fix_kind="rename_id",
                fixable=bool(renames),
                meta={"dup_id": dup_id, "renames": renames},
            )
        )

    # Missing IDs
    for idx in missing_indices:
        new_id = _next_available_entity_id(used_ids)
        used_ids.add(new_id)
        entity = entities[idx] if idx < len(entities) and isinstance(entities[idx], dict) else {}
        field_path = _resolve_id_field(entity)
        issues.append(
            SceneLintIssue(
                issue_id=f"missing_id:{idx}",
                kind="MISSING_ID",
                message=f"Missing entity id at index {idx}",
                entity_id=None,
                scene_id=scene_id,
                severity="ERROR",
                risk="safe",
                fix_kind="assign_id",
                fixable=True,
                meta={"index": idx, "field_path": field_path, "after": new_id},
            )
        )

    # Entity-level checks
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        entity_id = _extract_entity_id(entity)

        # Invalid prefab reference
        prefab_key, prefab_ref = _get_prefab_ref(entity)
        if prefab_ref and not prefab_resolver(prefab_ref):
            issues.append(
                SceneLintIssue(
                    issue_id=f"invalid_prefab_ref:{prefab_ref}:{idx}",
                    kind="INVALID_PREFAB_REF",
                    message=f"Invalid prefab ref '{prefab_ref}'",
                    entity_id=entity_id,
                    scene_id=scene_id,
                    severity="WARN",
                    risk="safe",
                    fix_kind="clear_prefab",
                    fixable=True,
                    meta={
                        "index": idx,
                        "prefab_key": prefab_key,
                        "prefab_value": prefab_ref,
                    },
                )
            )

        # Missing asset path
        for field_path, asset_path in _iter_asset_fields(entity):
            if not asset_path:
                issues.append(
                    SceneLintIssue(
                        issue_id=f"missing_asset:{entity_id or idx}:{field_path}",
                        kind="MISSING_ASSET",
                        message="Missing asset path",
                        entity_id=entity_id,
                        scene_id=scene_id,
                        severity="WARN",
                        risk="safe",
                        fix_kind="clear_asset",
                        fixable=True,
                        meta={"index": idx, "field_path": field_path},
                    )
                )
                continue
            full_path = _resolve_asset_path(repo_root, asset_path)
            if not full_path.exists():
                issues.append(
                    SceneLintIssue(
                        issue_id=f"missing_asset:{entity_id or idx}:{field_path}",
                        kind="MISSING_ASSET",
                        message=f"Missing asset '{asset_path}'",
                        entity_id=entity_id,
                        scene_id=scene_id,
                        severity="WARN",
                        risk="safe",
                        fix_kind="clear_asset",
                        fixable=True,
                        meta={"index": idx, "field_path": field_path},
                    )
                )

        # Invalid transform values
        invalid_fields = _collect_invalid_transform_fields(entity)
        if invalid_fields:
            issues.append(
                SceneLintIssue(
                    issue_id=f"invalid_transform:{entity_id or idx}",
                    kind="INVALID_TRANSFORM",
                    message="Invalid transform value",
                    entity_id=entity_id,
                    scene_id=scene_id,
                    severity="WARN",
                    risk="safe",
                    fix_kind="sanitize_transform",
                    fixable=True,
                    meta={"index": idx, "fields": invalid_fields},
                )
            )

    issues.sort(key=_issue_sort_key)
    return issues


def filter_lint_issues(issues: Iterable[SceneLintIssue], query_text: str) -> list[SceneLintIssue]:
    """Filter lint issues by query text."""
    text = str(query_text or "").strip().casefold()
    if not text:
        return list(issues)
    result: list[SceneLintIssue] = []
    for issue in issues:
        if text in issue.message.casefold():
            result.append(issue)
            continue
        if issue.entity_id and text in issue.entity_id.casefold():
            result.append(issue)
            continue
        if text in issue.kind.casefold():
            result.append(issue)
            continue
        if text in issue.issue_id.casefold():
            result.append(issue)
            continue
    return result


def clamp_issue_index(index: int, count: int) -> int:
    if count <= 0:
        return -1
    if index < 0:
        return 0
    return min(index, count - 1)


def compute_problems_window(cursor: int, count: int, max_visible: int) -> tuple[int, int]:
    if count <= 0 or max_visible <= 0:
        return (0, 0)
    start_idx = 0
    if cursor > max_visible / 2:
        start_idx = max(0, int(cursor - max_visible / 2))
    visible = min(count - start_idx, max_visible)
    return (start_idx, visible)


def compute_problems_panel_layout(dock: Rect) -> ProblemsPanelLayout:
    """Compute deterministic layout rects for the Problems panel."""
    content_top = dock.top - TAB_HEADER_HEIGHT - PROBLEMS_PADDING
    header_top = content_top
    header_bottom = header_top - PROBLEMS_LINE_HEIGHT

    search_top = header_bottom
    search_bottom = search_top - PROBLEMS_LINE_HEIGHT

    detail_bottom = dock.bottom + PROBLEMS_PADDING
    detail_top = detail_bottom + PROBLEMS_LINE_HEIGHT * PROBLEMS_DETAIL_LINES

    list_top = search_bottom
    list_bottom = detail_top

    fix_right = dock.right - PROBLEMS_PADDING
    fix_left = fix_right - PROBLEMS_FIX_ALL_W
    scan_right = fix_left - PROBLEMS_BUTTON_GAP
    scan_left = scan_right - PROBLEMS_SCAN_W

    header_rect = Rect(
        left=dock.left + PROBLEMS_PADDING,
        right=dock.right - PROBLEMS_PADDING,
        bottom=header_bottom,
        top=header_top,
    )
    scan_rect = Rect(left=scan_left, right=scan_right, bottom=header_bottom, top=header_top)
    fix_all_rect = Rect(left=fix_left, right=fix_right, bottom=header_bottom, top=header_top)
    search_rect = Rect(
        left=dock.left + PROBLEMS_PADDING,
        right=dock.right - PROBLEMS_PADDING,
        bottom=search_bottom,
        top=search_top,
    )
    list_rect = Rect(
        left=dock.left + PROBLEMS_PADDING,
        right=dock.right - PROBLEMS_PADDING,
        bottom=list_bottom,
        top=list_top,
    )
    detail_rect = Rect(
        left=dock.left + PROBLEMS_PADDING,
        right=dock.right - PROBLEMS_PADDING,
        bottom=detail_bottom,
        top=detail_top,
    )

    return ProblemsPanelLayout(
        header_rect=header_rect,
        scan_rect=scan_rect,
        fix_all_rect=fix_all_rect,
        search_rect=search_rect,
        list_rect=list_rect,
        detail_rect=detail_rect,
    )


def build_problems_panel_lines(
    active: bool,
    query: str,
    issues: List[SceneLintIssue],
    selected_index: int,
) -> list[str]:
    """Build deterministic ASCII lines for the Problems panel."""
    if not active:
        return []
    from engine.editor.panel_search_model import format_search_bar_text

    lines: list[str] = []
    lines.append(f"Problems ({len(issues)})  Scan  Fix All Safe")
    lines.append(format_search_bar_text(query, False))
    if not issues:
        lines.append("  (No problems)")
        return lines
    for idx, issue in enumerate(issues):
        prefix = "> " if idx == selected_index else "  "
        severity_tag = format_issue_severity_tag(issue)
        tag = format_issue_risk_tag(issue)
        lines.append(f"{prefix}{severity_tag} {tag} {issue.kind}: {issue.message}")
    return lines


def _issue_sort_key(issue: SceneLintIssue) -> tuple[int, str, bool, str, str]:
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    severity_rank = order.get(issue.severity, 99)
    entity_none = issue.entity_id is None
    entity_key = str(issue.entity_id or "")
    return (severity_rank, issue.kind, entity_none, entity_key, issue.issue_id)


def format_issue_risk_tag(issue: SceneLintIssue) -> str:
    """Return an ASCII risk tag for list rendering."""
    risk = str(getattr(issue, "risk", "safe") or "safe").strip().lower()
    if risk == "risky":
        return "[RISKY]"
    return "[SAFE]"


def format_issue_severity_tag(issue: SceneLintIssue) -> str:
    """Return an ASCII severity badge for list rendering."""
    severity = str(getattr(issue, "severity", "") or "").strip().lower()
    labels = {
        "error": "ERROR",
        "err": "ERROR",
        "warning": "WARN",
        "warn": "WARN",
        "info": "INFO",
    }
    return f"[{labels.get(severity, 'INFO')}]"


def _resolve_scene_id(scene_json: dict[str, Any]) -> str | None:
    for key in ("id", "name"):
        value = scene_json.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_entity_id(entity: dict[str, Any]) -> str | None:
    for key in ("id", "entity_id"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_id_field(entity: dict[str, Any]) -> str:
    if "id" in entity:
        return "id"
    if "entity_id" in entity:
        return "entity_id"
    return "id"


def _get_prefab_ref(entity: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("prefab_id", "prefab", "prefab_path"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return None, None


def _iter_asset_fields(entity: dict[str, Any]) -> Iterable[tuple[str, str]]:
    if "sprite" in entity:
        value = entity.get("sprite")
        if isinstance(value, str):
            yield ("sprite", value)
    if "asset" in entity:
        value = entity.get("asset")
        if isinstance(value, str):
            yield ("asset", value)
    components = entity.get("components")
    if isinstance(components, dict):
        sprite_comp = components.get("sprite")
        if isinstance(sprite_comp, dict):
            value = sprite_comp.get("asset")
            if isinstance(value, str):
                yield ("components.sprite.asset", value)


def _resolve_asset_path(repo_root: Path, asset_path: str) -> Path:
    raw = Path(asset_path)
    if raw.is_absolute():
        return raw
    return repo_root / raw


def _collect_invalid_transform_fields(entity: dict[str, Any]) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    top_level = {
        "x": 0.0,
        "y": 0.0,
        "rotation": 0.0,
        "rotation_deg": 0.0,
        "scale": 1.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
    }
    for key, default in top_level.items():
        if key in entity and _is_invalid_number(entity.get(key)):
            fields.append({"field_path": key, "after": float(default)})

    components = entity.get("components")
    if isinstance(components, dict):
        transform = components.get("transform")
        if isinstance(transform, dict):
            comp_fields = {
                "x": 0.0,
                "y": 0.0,
                "rot": 0.0,
                "rotation": 0.0,
                "scale": 1.0,
            }
            for key, default in comp_fields.items():
                if key in transform and _is_invalid_number(transform.get(key)):
                    fields.append({"field_path": f"components.transform.{key}", "after": float(default)})
    return fields


def _is_invalid_number(value: Any) -> bool:
    try:
        return not math.isfinite(float(value))
    except Exception:  # noqa: BLE001  # REASON: non-numeric lint values should not be treated as invalid finite numbers
        return False


def _next_unique_id(existing: set[str], base: str, suffix: str) -> str:
    base_val = str(base or "").strip() or "entity"
    n = 1
    while True:
        candidate = f"{base_val}{suffix}{n}"
        if candidate not in existing:
            return candidate
        n += 1


def _next_available_entity_id(existing: set[str]) -> str:
    n = 1
    while True:
        candidate = f"entity_{n}"
        if candidate not in existing:
            return candidate
        n += 1
