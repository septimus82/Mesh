"""AI-related console command handlers (ai_job, ai_bundle, docs, index)."""

from __future__ import annotations

from typing import Any

from engine.ai_ops import AIOps, load_job


def handle_ai_job(controller: Any, args: list[str]) -> bool:
    """``ai_job <job_path>``"""
    if not args:
        controller.log("Usage: ai_job <job_path>")
        return True
    job_path = args[0]
    try:
        job = load_job(job_path)
    except Exception as exc:  # noqa: BLE001  # REASON: malformed AI job files should report to the console without breaking the command loop
        controller.log(f"[AI] Failed to load job '{job_path}': {exc}")
        return True

    ops = AIOps(".")
    result = ops.apply_job(job)
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
