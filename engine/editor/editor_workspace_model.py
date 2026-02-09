"""Pure helpers for editor workspace persistence planning."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Mapping

from engine.workspace_settings import WorkspaceSettings


PathLikeStr = str | Path


@dataclass(frozen=True)
class WorkspacePaths:
    repo_root: Path
    workspace_path: Path | None
    projects_path: Path | None
    user_settings_path: Path | None


@dataclass(frozen=True)
class WorkspaceSnapshot:
    settings: WorkspaceSettings
    recent_projects: tuple[str, ...] = ()
    last_project: str | None = None


@dataclass(frozen=True)
class ProjectsPayload:
    version: int = 1
    recent_roots: tuple[str, ...] = ()
    last_root: str | None = None


@dataclass(frozen=True)
class UserSettingsPayload:
    version: int = 1
    settings: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspacePlan:
    paths: WorkspacePaths
    allow_io: bool


def compute_workspace_paths(
    repo_root: PathLikeStr,
    platform: str | None,
    is_web: bool,
) -> WorkspacePaths:
    root = Path(repo_root)
    if is_web:
        return WorkspacePaths(
            repo_root=root,
            workspace_path=None,
            projects_path=None,
            user_settings_path=None,
        )
    return WorkspacePaths(
        repo_root=root,
        workspace_path=root / "workspace.json",
        projects_path=root / "projects.json",
        user_settings_path=root / "user_settings.json",
    )


def resolve_settings_precedence(
    defaults: Mapping[str, Any] | None,
    project: Mapping[str, Any] | None,
    workspace: Mapping[str, Any] | None,
    user: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for payload in (defaults, project, workspace, user):
        if not isinstance(payload, Mapping):
            continue
        for key, value in payload.items():
            result[key] = value
    return result


def normalize_project_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    try:
        resolved = Path(text).expanduser()
        if resolved.exists():
            resolved = resolved.resolve()
        return str(resolved)
    except Exception:  # noqa: BLE001
        return text


def update_recent_projects(
    current: list[str],
    opened_path: str,
    now_iso: str,  # noqa: ARG001
    max_entries: int,
) -> list[str]:
    normalized = normalize_project_path(opened_path)
    if not normalized:
        return list(current)
    result = [normalized] + [item for item in current if normalize_project_path(item) != normalized]
    return result[:max_entries]


def merge_user_settings(
    defaults: Mapping[str, Any] | None,
    user_settings: Mapping[str, Any] | None,
    workspace_settings: Mapping[str, Any] | None,
    project_settings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return resolve_settings_precedence(defaults, project_settings, workspace_settings, user_settings)


def build_save_payload(snapshot: WorkspaceSnapshot) -> dict[str, Any]:
    return asdict(snapshot.settings)


def build_projects_payload(payload: ProjectsPayload) -> dict[str, Any]:
    return {
        "version": int(payload.version),
        "recent_roots": list(payload.recent_roots),
        "last_root": payload.last_root,
    }


def build_user_settings_payload(payload: UserSettingsPayload) -> dict[str, Any]:
    settings = payload.settings if isinstance(payload.settings, dict) else {}
    return {
        "version": int(payload.version),
        **settings,
    }


def apply_loaded_payload(
    current_snapshot: WorkspaceSnapshot,
    payload: Mapping[str, Any] | None,
) -> WorkspaceSnapshot:
    data = payload if isinstance(payload, Mapping) else {}
    settings = WorkspaceSettings.from_dict(dict(data))
    return WorkspaceSnapshot(
        settings=settings,
        recent_projects=current_snapshot.recent_projects,
        last_project=current_snapshot.last_project,
    )
