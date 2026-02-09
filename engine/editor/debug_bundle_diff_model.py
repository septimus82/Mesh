"""Pure helpers for diffing debug bundle snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class FieldDiff:
    path: str
    a: Any
    b: Any


@dataclass(frozen=True, slots=True)
class QuestChange:
    quest_id: str
    a: dict[str, Any]
    b: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DebugBundleDiff:
    changed: bool
    digests: tuple[FieldDiff, ...]
    quest_summary: tuple[FieldDiff, ...]
    quests_added: tuple[str, ...]
    quests_removed: tuple[str, ...]
    quests_changed: tuple[QuestChange, ...]
    diagnostics_added: tuple[str, ...]
    diagnostics_removed: tuple[str, ...]
    cutscene_summary: tuple[FieldDiff, ...]
    event_summary: tuple[FieldDiff, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "digests": [_diff_to_dict(d) for d in self.digests],
            "quests": {
                "summary": [_diff_to_dict(d) for d in self.quest_summary],
                "added": list(self.quests_added),
                "removed": list(self.quests_removed),
                "changed": [
                    {
                        "quest_id": change.quest_id,
                        "a": change.a,
                        "b": change.b,
                    }
                    for change in self.quests_changed
                ],
                "diagnostics_added": list(self.diagnostics_added),
                "diagnostics_removed": list(self.diagnostics_removed),
            },
            "cutscene": {"summary": [_diff_to_dict(d) for d in self.cutscene_summary]},
            "events": {"summary": [_diff_to_dict(d) for d in self.event_summary]},
        }


def diff_debug_bundles(payload_a: dict[str, Any], payload_b: dict[str, Any]) -> DebugBundleDiff:
    a = payload_a if isinstance(payload_a, dict) else {}
    b = payload_b if isinstance(payload_b, dict) else {}

    digests = _diff_fields(
        a,
        b,
        (
            "world.current",
            "lighting.plan_digest",
            "render.plan_digest",
        ),
    )

    quest_summary, quests_map = _extract_quest_summary(a)
    quest_summary_b, quests_map_b = _extract_quest_summary(b)
    quest_summary_diffs = _diff_dicts("quests.summary", quest_summary, quest_summary_b)

    quests_added, quests_removed, quests_changed = _diff_quests(quests_map, quests_map_b)
    diagnostics_added, diagnostics_removed = _diff_diagnostics(a, b)

    cutscene_summary = _diff_section(
        "cutscene.summary",
        _extract_summary(a, "cutscene"),
        _extract_summary(b, "cutscene"),
        (
            "is_running",
            "script_id",
            "command_index",
            "command_count",
            "current_command",
            "current_label",
            "wait_remaining",
        ),
    )

    event_summary = _diff_section(
        "events.summary",
        _extract_section(a, "events"),
        _extract_section(b, "events"),
        (
            "event_type_filter",
            "entity_id_filter",
            "limit",
            "total_events",
            "filtered_count",
        ),
    )

    changed = any(
        (
            bool(digests),
            bool(quest_summary_diffs),
            bool(quests_added),
            bool(quests_removed),
            bool(quests_changed),
            bool(diagnostics_added),
            bool(diagnostics_removed),
            bool(cutscene_summary),
            bool(event_summary),
        )
    )

    return DebugBundleDiff(
        changed=changed,
        digests=tuple(digests),
        quest_summary=tuple(quest_summary_diffs),
        quests_added=tuple(quests_added),
        quests_removed=tuple(quests_removed),
        quests_changed=tuple(quests_changed),
        diagnostics_added=tuple(diagnostics_added),
        diagnostics_removed=tuple(diagnostics_removed),
        cutscene_summary=tuple(cutscene_summary),
        event_summary=tuple(event_summary),
    )


def format_debug_bundle_diff_text(diff: DebugBundleDiff) -> str:
    lines = ["Debug Bundle Diff"]
    lines.extend(_format_field_section("Digests", diff.digests))
    lines.extend(
        _format_quests_section(
            diff.quest_summary,
            diff.quests_added,
            diff.quests_removed,
            diff.quests_changed,
            diff.diagnostics_added,
            diff.diagnostics_removed,
        )
    )
    lines.extend(_format_field_section("Cutscene Summary", diff.cutscene_summary))
    lines.extend(_format_field_section("Event Summary", diff.event_summary))
    return "\n".join(lines)


def _diff_to_dict(diff: FieldDiff) -> dict[str, Any]:
    return {"path": diff.path, "a": diff.a, "b": diff.b}


def _diff_fields(payload_a: dict[str, Any], payload_b: dict[str, Any], paths: Iterable[str]) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for path in paths:
        a_val = _get_nested(payload_a, path)
        b_val = _get_nested(payload_b, path)
        if a_val != b_val:
            diffs.append(FieldDiff(path=path, a=a_val, b=b_val))
    return diffs


def _diff_section(
    prefix: str,
    a_section: dict[str, Any],
    b_section: dict[str, Any],
    keys: Iterable[str],
) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for key in keys:
        a_val = a_section.get(key)
        b_val = b_section.get(key)
        if a_val != b_val:
            diffs.append(FieldDiff(path=f"{prefix}.{key}", a=a_val, b=b_val))
    return diffs


def _diff_dicts(prefix: str, a: dict[str, Any], b: dict[str, Any]) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    keys = sorted(set(a.keys()) | set(b.keys()))
    for key in keys:
        a_val = a.get(key)
        b_val = b.get(key)
        if a_val != b_val:
            diffs.append(FieldDiff(path=f"{prefix}.{key}", a=a_val, b=b_val))
    return diffs


def _extract_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    return section if isinstance(section, dict) else {}


def _extract_summary(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = _extract_section(payload, key)
    summary = section.get("summary")
    return summary if isinstance(summary, dict) else {}


def _extract_quest_summary(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    quests_section = payload.get("quests")
    if not isinstance(quests_section, dict):
        quests_section = {}
    inspector_state = quests_section.get("inspector_state")
    if not isinstance(inspector_state, dict):
        inspector_state = {}

    summary = {
        "total_quests": int(inspector_state.get("total_quests", 0) or 0),
        "active_count": int(inspector_state.get("active_count", 0) or 0),
        "completed_count": int(inspector_state.get("completed_count", 0) or 0),
        "inactive_count": int(inspector_state.get("inactive_count", 0) or 0),
    }

    quests_map: dict[str, dict[str, Any]] = {}
    quests_raw = inspector_state.get("quests")
    if isinstance(quests_raw, list):
        for entry in quests_raw:
            if not isinstance(entry, dict):
                continue
            quest_id = str(entry.get("id", "") or "")
            if not quest_id:
                continue
            current_stage = entry.get("current_stage")
            stage_id = None
            if isinstance(current_stage, dict):
                stage_id = str(current_stage.get("id", "") or "") or None
            quests_map[quest_id] = {
                "status": str(entry.get("status", "") or ""),
                "progress": str(entry.get("progress", "") or ""),
                "current_stage": stage_id,
                "awaiting_stage": str(entry.get("awaiting_stage", "") or "") or None,
            }

    return summary, quests_map


def _diff_quests(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[QuestChange]]:
    a_ids = set(a.keys())
    b_ids = set(b.keys())
    added = sorted(b_ids - a_ids)
    removed = sorted(a_ids - b_ids)
    changed: list[QuestChange] = []
    for quest_id in sorted(a_ids & b_ids):
        a_entry = a[quest_id]
        b_entry = b[quest_id]
        if a_entry != b_entry:
            changed.append(QuestChange(quest_id=quest_id, a=a_entry, b=b_entry))
    return added, removed, changed


def _diff_diagnostics(payload_a: dict[str, Any], payload_b: dict[str, Any]) -> tuple[list[str], list[str]]:
    a_entries = _normalize_diagnostics(payload_a)
    b_entries = _normalize_diagnostics(payload_b)
    added = sorted(set(b_entries) - set(a_entries))
    removed = sorted(set(a_entries) - set(b_entries))
    return added, removed


def _normalize_diagnostics(payload: dict[str, Any]) -> list[str]:
    quests_section = payload.get("quests")
    if not isinstance(quests_section, dict):
        return []
    diagnostics = quests_section.get("diagnostics")
    if not isinstance(diagnostics, list):
        return []
    rows: list[str] = []
    for diag in diagnostics:
        if not isinstance(diag, dict):
            continue
        quest_id = str(diag.get("quest_id", "") or "")
        step_id = str(diag.get("step_id", "") or "")
        event_type = str(diag.get("event_type", "") or "")
        matched = bool(diag.get("matched", False))
        reason = str(diag.get("reason", "") or "")
        if not quest_id or not step_id:
            continue
        tag = "match" if matched else "no-match"
        rows.append(f"{quest_id}:{step_id} {event_type} [{tag}] {reason}".strip())
    rows.sort()
    return rows


def _format_field_section(title: str, diffs: Iterable[FieldDiff]) -> list[str]:
    lines = [f"{title}:"]
    items = list(diffs)
    if not items:
        lines.append("  (no changes)")
        return lines
    for diff in items:
        lines.append(f"  - {diff.path}: {_format_value(diff.a)} -> {_format_value(diff.b)}")
    return lines


def _format_quests_section(
    summary_diffs: Iterable[FieldDiff],
    added: Iterable[str],
    removed: Iterable[str],
    changed: Iterable[QuestChange],
    diag_added: Iterable[str],
    diag_removed: Iterable[str],
) -> list[str]:
    lines = ["Quests:"]
    summary_items = list(summary_diffs)
    if summary_items:
        lines.append("  Summary:")
        for diff in summary_items:
            lines.append(f"    - {diff.path}: {_format_value(diff.a)} -> {_format_value(diff.b)}")
    else:
        lines.append("  Summary: (no changes)")

    added_list = list(added)
    removed_list = list(removed)
    changed_list = list(changed)

    lines.append("  Quests Added:" if added_list else "  Quests Added: (none)")
    for quest_id in added_list:
        lines.append(f"    - {quest_id}")

    lines.append("  Quests Removed:" if removed_list else "  Quests Removed: (none)")
    for quest_id in removed_list:
        lines.append(f"    - {quest_id}")

    if changed_list:
        lines.append("  Quests Changed:")
        for entry in changed_list:
            lines.append(f"    - {entry.quest_id}: {_format_quest_change(entry)}")
    else:
        lines.append("  Quests Changed: (none)")

    diag_added_list = list(diag_added)
    diag_removed_list = list(diag_removed)
    lines.append("  Diagnostics Added:" if diag_added_list else "  Diagnostics Added: (none)")
    for item in diag_added_list:
        lines.append(f"    - {item}")
    lines.append("  Diagnostics Removed:" if diag_removed_list else "  Diagnostics Removed: (none)")
    for item in diag_removed_list:
        lines.append(f"    - {item}")

    return lines


def _format_quest_change(change: QuestChange) -> str:
    parts: list[str] = []
    for key in ("status", "progress", "current_stage", "awaiting_stage"):
        a_val = change.a.get(key)
        b_val = change.b.get(key)
        if a_val != b_val:
            parts.append(f"{key}: {_format_value(a_val)} -> {_format_value(b_val)}")
    return "; ".join(parts) if parts else "(no fields changed)"


def _format_value(value: Any) -> str:
    if value is None:
        return "(none)"
    if value == "":
        return "(empty)"
    return str(value)


def _get_nested(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
