"""AI-related console command handlers (ai_job, ai_bundle, docs, index)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.ai_ops import AIOps, load_job


def _editing_here(window: Any) -> str:
    """Who edits the project in this window, or "": its unsaved work is in no file (#462 R4)."""
    if getattr(window, "studio", None) is not None:
        return "Mesh Studio"
    held = getattr(window, "project_ownership", None)
    editor = getattr(window, "editor_controller", None)
    return "the editor" if getattr(held, "held", False) is True or getattr(editor, "active", False) is True else ""


def handle_ai_job(controller: Any, args: list[str]) -> bool:
    """``ai_job <job_path>``: writes the project's files directly (``AIOps``), so only where nothing edits the project
    (#462 R4). Inside Mesh Studio (its play-test) or the editor it is refused, writing nothing: the window's own
    hold on the project is for its editor, never a pass for this. Elsewhere it owns the project it runs in
    (``project_ownership.ownership_root``: the project, wherever inside it) while it writes, as any outside writer
    does, and writes only that project's files (never a nested project's); if it can't own it, nothing is changed."""
    if not args:
        controller.log("Usage: ai_job <job_path>")
        return True
    editing = _editing_here(controller.window)
    if editing:
        controller.log(f"[AI] ai_job: nothing was changed. {editing} has this project open in this window, and ai_job "
                       "would write its files behind your unsaved work. Ask an AI through Mesh Studio's AI panel (its "
                       "changes come to you to accept), or close it and run the job in the game.")
        return True
    job_path = args[0]
    try:
        job = load_job(job_path)
    except Exception as exc:  # noqa: BLE001  # REASON: malformed AI job files should report to the console without breaking the command loop
        controller.log(f"[AI] Failed to load job '{job_path}': {exc}")
        return True

    from engine.editor import project_ownership  # noqa: PLC0415  # (the editor package is heavy: only when writing)
    from engine.paths import project_root  # noqa: PLC0415

    # (#675: the window's project, not the current folder's: after run_game(project_root=) or a main-menu switch they
    # differ, and the job wrote, under that folder's lock, into a project the window isn't playing. A current folder
    # inside the project still bases the job's paths, as before.)
    cwd, project = Path.cwd().resolve(), project_root()
    root = cwd if cwd.is_relative_to(project) else project
    try:
        held = project_ownership.acquire(project_ownership.ownership_root(root), project_ownership.AUTHORING, wait=0.5)
    except (project_ownership.OwnedElsewhere, project_ownership.OwnershipUnavailable) as exc:
        controller.log("[AI] " + project_ownership.refused_write("ai_job", exc))
        return True
    with held:
        result = AIOps(root, owner=held).apply_job(job)  # (only the held project's files)
    ok = result.get("ok", False)
    op_count = len(result.get("results") or [])
    scenes = {
        str(op.get("scene_path"))
        for op in job.get("operations", [])
        if isinstance(op, dict) and op.get("scene_path")
    }
    if ok:
        scene_hint = f" | scenes: {', '.join(sorted(scenes))}" if scenes else ""
        controller.log(f"[AI] Applied {op_count} operation(s) from {job_path}{scene_hint}")
        reloader = getattr(controller.window, "reload_scene", None)
        if callable(reloader):
            reloader()
    else:
        controller.log(f"[AI] Job failed ({op_count} op(s)); see details:")
        for entry in result.get("results") or []:
            if not entry.get("ok"):
                controller.log(f" - {entry.get('message')}")
    return True


def handle_ai_bundle(controller: Any, args: list[str]) -> bool:
    """``ai_bundle [dir]``"""
    controller.log("Command 'ai_bundle' is deprecated. Use 'mesh ai-bundle' CLI instead.")
    return True


def handle_ai_context(controller: Any, args: list[str]) -> bool:
    """``ai_context [path]``"""
    controller.log("Command 'ai_context' is deprecated. Use 'mesh ai-export-context' CLI instead.")
    return True


def handle_generate_docs(controller: Any, args: list[str]) -> bool:
    """``docs [dir]``"""
    target_dir = args[0] if args else "docs"
    from engine.tooling_runtime.generate_docs import generate_docs

    try:
        generate_docs(".", target_dir)
        controller.log(f"Docs generated in {target_dir}")
    except Exception as e:  # noqa: BLE001  # REASON: docs generation failures should be reported without breaking the command loop
        controller.log(f"Error generating docs: {e}")
    return True


def handle_build_project_index(controller: Any, args: list[str]) -> bool:
    """``index [output_path]``"""
    output = args[0] if args else "mesh_index.json"
    from engine.tooling_runtime.project_index import build_project_index

    try:
        build_project_index(".", output)
        controller.log(f"Project index built to {output}")
    except Exception as e:  # noqa: BLE001  # REASON: project index generation failures should be reported without breaking the command loop
        controller.log(f"Error building index: {e}")
    return True
