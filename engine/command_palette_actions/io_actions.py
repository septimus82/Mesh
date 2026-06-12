from __future__ import annotations

from pathlib import Path
from typing import Any


def action_scene_persist(w: Any, _arg: str | None) -> None:
    """Persist scene to disk (if armed)."""
    if not bool(getattr(w, "scene_persist_armed", False)):
        print("SCENE_PERSIST (not armed)")
        return
    persister = getattr(w, "persist_scene_to_disk", None)
    result = persister() if callable(persister) else None
    ok = bool(getattr(result, "ok", False))
    path = str(getattr(result, "path", "") or "").strip()
    print(f"SCENE_PERSIST {'ok' if ok else 'fail'} path={path or '-'}")


def action_scene_save_as(w: Any, arg: str | None) -> None:
    """Save scene to a new path."""
    saver = getattr(w, "save_scene_as", None)
    new_path = str(arg or "").strip()
    result = saver(new_path) if callable(saver) else None
    ok = bool(getattr(result, "ok", False))
    out_path = str(getattr(result, "path", "") or "").strip()
    if ok and out_path:
        print(f"TIP: python -m mesh_cli world add-scene worlds/main_world.json --key <key> --path {out_path}")


def action_scene_create(w: Any, arg: str | None) -> None:
    """Create a new empty scene file."""
    from engine.tooling_runtime.scene_create import create_empty_scene_file  # noqa: PLC0415
    path = str(arg or "").strip()
    if not path:
        print("SCENE_CREATE fail path=- reason=empty_path")
        return
    name = Path(path).stem
    result = create_empty_scene_file(path, name=name)
    reason = ",".join(result.errors) if result.errors else "-"
    print(f"SCENE_CREATE {'ok' if result.ok else 'fail'} path={result.path} reason={reason}")


def action_go_to_scene(w: Any, arg: str | None) -> None:
    """Go to a specific scene."""
    requester = getattr(w, "request_scene_change", None)
    if not callable(requester):
        return
    path = str(arg or "").strip()
    if not path:
        return
    requester(path)


def action_recent_scene(w: Any, arg: str | None) -> None:
    """Open a recent scene."""
    return action_go_to_scene(w, arg)
