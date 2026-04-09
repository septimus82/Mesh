from __future__ import annotations

import argparse
import json

from engine.config import load_config
from engine.tooling import preset_commands, validate_all
from engine.tooling.plan_apply import apply_plan
from engine.tooling.tool_result import Issue, ToolResult


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def launch_demo(start_scene: str | None = None, world_path: str | None = None) -> int:
    """Patchable wrapper for launching the demo without importing `arcade` at module import time."""
    from engine.tooling.demo_runner import launch_demo as _launch_demo

    return int(_launch_demo(start_scene=start_scene, world_path=world_path))


def _preset_lint_or_exit(config) -> tuple[bool, dict]:
    lint_stage = preset_commands.build_preset_lint_stage_result(config)
    if not lint_stage["ok"]:
        print(json.dumps(lint_stage, sort_keys=True))
        return False, lint_stage
    return True, lint_stage


def run_pipeline_result(
    *,
    plan_path: str,
    path: str,
    ai_safe: bool = False,
    dry_run: bool = False,
    strict: bool = False,
    strict_compact: bool = False,
    check_reachability: bool = False,
    check_orphans: bool = False,
    check_refs: bool = False,
    demo: bool = False,
    preset: str | None = None,
) -> ToolResult:
    """Orchestrate apply-plan -> validate-all -> (optional) demo/preset."""
    issues: list[Issue] = []

    # 0. Preset Lint (mirror `mesh check` behavior)
    config = load_config()
    ok, _lint_stage = _preset_lint_or_exit(config)
    if not ok:
        return ToolResult.failure(exit_code=2, issues=issues)

    def _print_next() -> None:
        print("[PIPELINE] Next:")
        print("  mesh preset lint")
        print(f"  mesh doctor --world {path}")
        print("  mesh explain --last")

    def _run_step(name: str, runner) -> int:
        try:
            result = runner()
        except SystemExit as e:  # noqa: BLE001  # REASON: embedded pipeline steps may terminate via SystemExit and should be converted into pipeline failure codes
            code = e.code if isinstance(e.code, int) else 1
            print(f"[PIPELINE] {name} -> FAILED")
            issues.append(Issue(code=name, message=f"{name} failed", severity="error"))
            return int(code)
        except Exception as e:  # noqa: BLE001  # REASON: embedded pipeline steps can fail with mixed exception types and should collapse into a deterministic pipeline failure
            print(f"[PIPELINE] {name} -> FAILED: {e}")
            issues.append(Issue(code=name, message=f"{name} failed: {e}", severity="error"))
            return 1

        if result != 0:
            print(f"[PIPELINE] {name} -> FAILED")
            issues.append(Issue(code=name, message=f"{name} failed", severity="error"))
            return int(result)

        print(f"[PIPELINE] {name} -> ok")
        return 0

    rc = _run_step(
        "apply-plan",
        lambda: apply_plan(
            plan_path=plan_path,
            ai_safe=ai_safe,
            dry_run=dry_run,
            no_lint=False,
            run_tests=False,
        ),
    )
    if rc != 0:
        _print_next()
        return ToolResult.failure(exit_code=rc, issues=issues)

    tool_argv = [path]
    if strict_compact:
        tool_argv.append("--strict-compact")
    if strict:
        tool_argv.append("--strict")
    if check_reachability:
        tool_argv.append("--check-reachability")
    if check_orphans:
        tool_argv.append("--check-orphans")
    if check_refs:
        tool_argv.append("--check-refs")

    rc = _run_step("validate-all", lambda: validate_all.main(tool_argv))
    if rc != 0:
        _print_next()
        return ToolResult.failure(exit_code=rc, issues=issues)

    if demo:
        # Attempt to resolve start_scene from the validated world file
        start_scene = None
        world_path = None
        if path.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Check if it looks like a world file
                    if isinstance(data, dict) and "start_scene" in data and "scenes" in data:
                        world_path = path
                        s_id = data["start_scene"]
                        scenes = data["scenes"]
                        if isinstance(scenes, dict) and s_id in scenes:
                            scene_entry = scenes[s_id]
                            if isinstance(scene_entry, dict) and "path" in scene_entry:
                                start_scene = scene_entry["path"]
            except Exception: # noqa: S110
                _log_swallow("PIPE-001", "engine/tooling/pipeline_runner.py pass-only blanket swallow")
                pass

        rc = _run_step("demo", lambda: launch_demo(start_scene=start_scene, world_path=world_path))
        if rc != 0:
            _print_next()
            return ToolResult.failure(exit_code=rc, issues=issues)

    if preset:
        preset_args = argparse.Namespace(name=preset)
        def _run_preset() -> int:
            preset_commands.run_preset_command(preset_args)
            return 0

        rc = _run_step("preset", _run_preset)
        if rc != 0:
            _print_next()
            return ToolResult.failure(exit_code=rc, issues=issues)

    return ToolResult.success(issues=issues)


def run_pipeline(
    *,
    plan_path: str,
    path: str,
    ai_safe: bool = False,
    dry_run: bool = False,
    strict: bool = False,
    strict_compact: bool = False,
    check_reachability: bool = False,
    check_orphans: bool = False,
    check_refs: bool = False,
    demo: bool = False,
    preset: str | None = None,
) -> int:
    return int(
        run_pipeline_result(
            plan_path=plan_path,
            path=path,
            ai_safe=ai_safe,
            dry_run=dry_run,
            strict=strict,
            strict_compact=strict_compact,
            check_reachability=check_reachability,
            check_orphans=check_orphans,
            check_refs=check_refs,
            demo=demo,
            preset=preset,
        ).exit_code
    )
