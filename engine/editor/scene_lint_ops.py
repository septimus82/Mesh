"""Pure operations for applying scene lint fixes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Tuple, cast

from .scene_lint_model import SceneLintIssue


@dataclass(frozen=True, slots=True)
class FixSceneIssueCommand:
    """Command to fix a single scene issue."""

    issue_id: str
    kind: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "FixSceneIssue",
            "issue_id": self.issue_id,
            "kind": self.kind,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FixSceneIssueCommand":
        return cls(
            issue_id=str(data.get("issue_id", "")),
            kind=str(data.get("kind", "")),
            payload=dict(data.get("payload", {}) or {}),
        )


@dataclass(frozen=True, slots=True)
class FixSceneIssuesCommand:
    """Command to fix multiple scene issues in one undo step."""

    commands: Tuple[FixSceneIssueCommand, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "FixSceneIssues",
            "commands": [cmd.to_dict() for cmd in self.commands],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FixSceneIssuesCommand":
        raw = data.get("commands", [])
        commands = tuple(FixSceneIssueCommand.from_dict(entry) for entry in raw)
        return cls(commands=commands)


def build_fix_command_for_issue(
    scene_json: dict[str, Any],
    issue: SceneLintIssue,
    repo_root: Any,
) -> FixSceneIssueCommand | None:
    """Build a fix command for a single issue."""
    if not issue.fixable or not issue.fix_kind:
        return None
    meta = dict(issue.meta or {})
    targets: list[dict[str, Any]] = []

    if issue.fix_kind in ("rename_id", "assign_id"):
        renames = meta.get("renames")
        if isinstance(renames, list):
            for entry in renames:
                target = _build_target_from_entry(scene_json, entry)
                if target:
                    targets.append(target)
        else:
            target = _build_target_from_entry(scene_json, meta)
            if target:
                targets.append(target)

    elif issue.fix_kind == "clear_prefab":
        index = meta.get("index")
        if isinstance(index, int):
            changes: list[dict[str, Any]] = []
            prefab_key = str(meta.get("prefab_key") or "prefab_id")
            changes.extend(_build_change_for_path(scene_json, index, prefab_key, after_present=False))
            changes.extend(_build_change_for_path(scene_json, index, "prefab_overrides", after_present=False))
            if changes:
                targets.append({"index": index, "changes": changes})

    elif issue.fix_kind == "clear_asset":
        index = meta.get("index")
        field_path = meta.get("field_path")
        if isinstance(index, int) and isinstance(field_path, str):
            changes = _build_change_for_path(scene_json, index, field_path, after_present=False)
            if changes:
                targets.append({"index": index, "changes": changes})

    elif issue.fix_kind == "sanitize_transform":
        index = meta.get("index")
        fields = meta.get("fields")
        if isinstance(index, int) and isinstance(fields, list):
            transform_changes: list[dict[str, Any]] = []
            for entry in fields:
                if not isinstance(entry, dict):
                    continue
                field_path = entry.get("field_path")
                after = entry.get("after")
                if not isinstance(field_path, str):
                    continue
                transform_changes.extend(_build_change_for_path(scene_json, index, field_path, after_value=after))
            if transform_changes:
                targets.append({"index": index, "changes": transform_changes})

    if not targets:
        return None

    payload: dict[str, object] = {"targets": targets}
    return FixSceneIssueCommand(issue_id=issue.issue_id, kind=issue.fix_kind, payload=payload)


def apply_fix_command(
    scene_json: dict[str, Any],
    cmd: FixSceneIssueCommand | FixSceneIssuesCommand,
    repo_root: Any,
) -> dict[str, Any]:
    """Apply a fix command to scene JSON."""
    if isinstance(cmd, FixSceneIssuesCommand):
        result = copy.deepcopy(scene_json)
        for sub in cmd.commands:
            result = apply_fix_command(result, sub, repo_root)
        return result

    result = copy.deepcopy(scene_json)
    entities = result.get("entities")
    if not isinstance(entities, list):
        return result

    payload = cmd.payload or {}
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        return result

    for target in targets:
        if not isinstance(target, dict):
            continue
        index = target.get("index")
        if not isinstance(index, int) or not (0 <= index < len(entities)):
            continue
        entity = entities[index]
        if not isinstance(entity, dict):
            continue
        changes = target.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            _apply_change(entity, change, use_after=True)
    return result


def invert_fix_command(
    scene_json_before: dict[str, Any],
    cmd: FixSceneIssueCommand | FixSceneIssuesCommand,
    scene_json_after: dict[str, Any],
) -> FixSceneIssueCommand | FixSceneIssuesCommand:
    """Invert a fix command for undo."""
    if isinstance(cmd, FixSceneIssuesCommand):
        inverted = tuple(
            _invert_single_fix_command(sub)
            for sub in reversed(cmd.commands)
        )
        return FixSceneIssuesCommand(commands=inverted)

    return _invert_single_fix_command(cmd)


def apply_fix_all(
    scene_json: dict[str, Any],
    issues: Iterable[SceneLintIssue],
    repo_root: Any,
) -> tuple[dict[str, Any], FixSceneIssuesCommand]:
    """Apply safe fixes and return new scene JSON and compound command."""
    result, commands, _skipped = _apply_safe_fix_commands(scene_json, issues, repo_root)
    return result, FixSceneIssuesCommand(commands=tuple(commands))


def is_fix_safe(issue: SceneLintIssue) -> bool:
    """Return True if a fix is marked safe."""
    return str(getattr(issue, "risk", "safe")) == "safe"


def apply_all_safe_fixes(
    scene_json: dict[str, Any],
    issues: Iterable[SceneLintIssue],
    repo_root: Any,
) -> tuple[dict[str, Any], int, int]:
    """Apply only safe fixes and return scene, applied count, skipped risky count."""
    result, commands, skipped = _apply_safe_fix_commands(scene_json, issues, repo_root)
    return result, len(commands), skipped


def compute_next_unique_id(existing_ids: set[str], base: str, *, suffix: str) -> str:
    """Compute a unique ID using a base and suffix."""
    base_val = str(base or "").strip() or "entity"
    n = 1
    while True:
        candidate = f"{base_val}{suffix}{n}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def sanitize_transform_value(value: Any, default: float) -> float:
    """Clamp NaN/inf to defaults."""
    try:
        num = float(value)
    except Exception:  # noqa: BLE001
        return float(default)
    if num != num or num in (float("inf"), float("-inf")):
        return float(default)
    return num


def _build_target_from_entry(scene_json: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    index = entry.get("index")
    field_path = entry.get("field_path")
    after = entry.get("after")
    if not isinstance(index, int) or not isinstance(field_path, str):
        return None
    changes = _build_change_for_path(scene_json, index, field_path, after_value=after)
    if not changes:
        return None
    return {"index": index, "changes": changes}


def _build_change_for_path(
    scene_json: dict[str, Any],
    index: int,
    field_path: str,
    *,
    after_value: Any = None,
    after_present: bool = True,
) -> list[dict[str, Any]]:
    entity = _get_entity_by_index(scene_json, index)
    if entity is None:
        return []
    before_present, before_value = _get_path(entity, field_path)
    return [{
        "path": field_path,
        "before": before_value,
        "after": after_value,
        "before_present": before_present,
        "after_present": after_present,
    }]


def _get_entity_by_index(scene_json: dict[str, Any], index: int) -> dict[str, Any] | None:
    entities = scene_json.get("entities")
    if not isinstance(entities, list):
        return None
    if 0 <= index < len(entities) and isinstance(entities[index], dict):
        return cast(dict[str, Any], entities[index])
    return None


def _invert_single_fix_command(cmd: FixSceneIssueCommand) -> FixSceneIssueCommand:
    payload = cmd.payload or {}
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        return cmd

    inv_targets: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        changes = target.get("changes", [])
        if not isinstance(changes, list):
            continue
        inv_changes: list[dict[str, Any]] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            inv_changes.append({
                "path": change.get("path"),
                "before": change.get("after"),
                "after": change.get("before"),
                "before_present": change.get("after_present", True),
                "after_present": change.get("before_present", True),
            })
        inv_targets.append({"index": target.get("index"), "changes": inv_changes})

    return FixSceneIssueCommand(issue_id=cmd.issue_id, kind=cmd.kind, payload={"targets": inv_targets})


def _apply_safe_fix_commands(
    scene_json: dict[str, Any],
    issues: Iterable[SceneLintIssue],
    repo_root: Any,
) -> tuple[dict[str, Any], list[FixSceneIssueCommand], int]:
    result = copy.deepcopy(scene_json)
    commands: list[FixSceneIssueCommand] = []
    skipped = 0
    for issue in issues:
        if not is_fix_safe(issue):
            skipped += 1
            continue
        cmd = build_fix_command_for_issue(result, issue, repo_root)
        if cmd is None:
            continue
        result = apply_fix_command(result, cmd, repo_root)
        commands.append(cmd)
    return result, commands, skipped


def _get_path(entity: dict[str, Any], path: str) -> tuple[bool, Any]:
    parts = path.split(".")
    current: Any = entity
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return (False, None)
        current = current.get(part)
    if not isinstance(current, dict):
        return (False, None)
    if parts[-1] in current:
        return (True, current.get(parts[-1]))
    return (False, None)


def _apply_change(entity: dict[str, Any], change: dict[str, Any], *, use_after: bool) -> None:
    path = change.get("path")
    if not isinstance(path, str) or not path:
        return
    if use_after:
        present = bool(change.get("after_present", True))
        value = change.get("after")
    else:
        present = bool(change.get("before_present", True))
        value = change.get("before")
    if present:
        _set_path(entity, path, value)
    else:
        _remove_path(entity, path)


def _set_path(entity: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = entity
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current.get(part)
    if isinstance(current, dict):
        current[parts[-1]] = value


def _remove_path(entity: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    current: Any = entity
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part)
    if isinstance(current, dict):
        current.pop(parts[-1], None)
