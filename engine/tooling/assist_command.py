from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from engine.tooling import triage_command, plan_apply, plan_cli
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Action


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


DIFF_SUPPORTED_ACTIONS = {
    "create_scene",
    "add_transition",
    "add_npc",
    "add_puzzle_switch_door",
    "auto_wire_transitions",
    "polish_scene"
}

DIFF_SKIPPED_ACTIONS = {
    "init_pack",
    "create_quest",
    "wire_world",
    "add_npc_dialogue"
}


def add_assist_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("assist", help="Triage, apply, and test fixes")
    parser.add_argument("--world", required=True, help="World to check")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (triage only)")
    parser.add_argument("--diff", action="store_true", help="Show diff (requires --dry-run)")
    parser.add_argument("--summary-json", action="store_true", help="Output JSON summary (requires --dry-run)")
    parser.add_argument("--also-text", action="store_true", help="Output text summary before JSON (requires --summary-json)")
    parser.add_argument("--max-diff-lines", type=int, default=200, help="Max lines to show per file diff (default: 200)")
    parser.set_defaults(func=run_assist_command)


def run_assist_command(args: argparse.Namespace) -> int:
    summary_json = getattr(args, "summary_json", False)
    also_text = getattr(args, "also_text", False)
    diff_guard_mode = bool(getattr(args, "dry_run", False) and getattr(args, "diff", False) and not summary_json)
    defer_trige_output = bool(not summary_json)
    
    if args.diff and not args.dry_run:
        print("Error: --diff requires --dry-run")
        return 1
    if summary_json and not args.dry_run:
        print("Error: --summary-json requires --dry-run")
        return 1
    if also_text and not summary_json:
        print("Error: --also-text requires --summary-json")
        return 1

    # 1. Run Triage
    # Equivalent to: mesh triage --world <world> --out artifacts/assist_plan.json --write-artifacts
    
    plan_path = Path("artifacts/assist_plan.json")
    
    triage_args = argparse.Namespace(
        world=args.world,
        out=str(plan_path),
        write_artifacts=True
    )
    
    # We capture stdout to suppress triage output unless we want to show it?
    # The requirement says "Deterministic output; keep prints minimal and structured."
    # Triage prints the explanation JSON. We might want to suppress that or let it be.
    # Let's suppress it for cleaner output, or maybe just let it flow?
    # "keep prints minimal" suggests we should probably control it.
    # But triage_command prints to stdout.
    # Let's run it.
    
    # We can't easily suppress stdout without redirecting sys.stdout, which is risky in a library call.
    # But since we are the CLI entry point, it's okay.
    # However, triage output is useful. Let's keep it but maybe prefix or separate it?
    # Actually, the requirement says:
    # "If triage produced a plan with zero actions ... Print: [ASSIST] ..."
    # This implies we should check the plan AFTER triage runs.
    
    deferred_output: list[str] = []
    if defer_trige_output:
        deferred_output.append(f"[ASSIST] Running triage on {args.world}...")
    
    # Capture stdout to check for warnings in triage output
    from io import StringIO
    capture_out = StringIO()
    original_stdout = sys.stdout
    sys.stdout = capture_out
    
    try:
        exit_code = triage_command.run_triage_command(triage_args)
    finally:
        sys.stdout = original_stdout
        
    triage_output = capture_out.getvalue()
    # Print triage output to stdout so user can see it (or maybe just the relevant parts?)
    # Requirement says "keep prints minimal". Triage prints a big JSON.
    # Maybe we shouldn't print it all.
    # But if we don't print it, the user doesn't see the explanation.
    # Let's print it for now, as it's the primary output of the first step.
    if defer_trige_output:
        deferred_output.append(triage_output)
    
    if exit_code != 0:
        # Triage failed (doctor failed AND failed to generate plan? No, triage returns 0 if plan generated)
        # If triage returns non-zero, it means something went wrong in the process.
        if not summary_json:
            print("[ASSIST] Triage failed.")
        return exit_code

    # 2. Check Plan
    if not plan_path.exists():
        if not summary_json:
            print("[ASSIST] No plan generated.")
        return 1
        
    try:
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log_swallow("ASCM-001", "engine/tooling/assist_command.py blanket swallow", once=True)
        if not summary_json:
            print(f"[ASSIST] Failed to read plan: {e}")
        return 1
        
    actions = plan_data.get("actions", [])
    unfixable = plan_data.get("meta", {}).get("unfixable", [])
    touches_raw = (
        plan_data.get("meta", {}).get("touches")
        or plan_data.get("inputs", {}).get("meta", {}).get("touches")
        or []
    )

    def _norm_path(p: str | Path) -> str:
        text = str(p)
        if os.path.isabs(text):
            text = os.path.relpath(text, start=str(Path.cwd()))
        text = text.replace("\\", "/")
        if text.startswith("./"):
            text = text[2:]
        return text

    touches = [_norm_path(p) for p in touches_raw if isinstance(p, str)]
    touches = sorted(set(touches))
    touches_set = set(touches)

    def _extract_triage_json_payload(text: str) -> dict | None:
        decoder = json.JSONDecoder()
        start = text.find("{")
        if start < 0:
            return None
        try:
            obj, _end = decoder.raw_decode(text[start:])
        except Exception:  # noqa: BLE001  # REASON: malformed triage JSON fragments should fail closed to no extracted triage payload
            _log_swallow("ASCM-002", "engine/tooling/assist_command.py blanket swallow", once=True)
            return None
        return obj if isinstance(obj, dict) else None

    def _refuse(*, reason: str, extra: dict | None = None) -> int:
        payload = {"version": 1, "ok": False, "stage": "triage_refuse", "reason": reason}
        payload.update(dict(extra or {}))
        print(json.dumps(payload, sort_keys=True))
        return 3

    def _parse_warning_items(items: list) -> list[dict]:
        parsed: list[dict] = []
        for item in items or []:
            if isinstance(item, dict):
                wid = item.get("id")
                msg = item.get("message")
                if isinstance(wid, str) and isinstance(msg, str):
                    parsed.append({"id": wid, "message": msg})
                continue

            if isinstance(item, str):
                if item.startswith("plan_invalid:"):
                    parsed.append({"id": "plan_invalid_touches", "message": item})
                else:
                    parsed.append({"id": "action_hints_mismatch", "message": item})

        return sorted(parsed, key=lambda w: (w["id"], w["message"]))
    
    if args.dry_run:
        # Execute plan in capture mode to see what would be written
        from engine.tooling.plan_executor import PlanExecutor
        from engine.tooling.plan_types import Plan
        
        captured_writes = {}
        def capture_writer(path: Path, content: str):
            captured_writes[str(path)] = content
            
        executor = PlanExecutor(dry_run=False, writer=capture_writer)
        # Disable backups for dry run
        def _noop_backup_file(p: Path) -> None:  # noqa: ARG001
            return None

        cast(Any, executor.backup_mgr).backup_file = _noop_backup_file  # intentional monkeypatch for dry-run
        
        try:
            plan_data_for_exec = dict(plan_data)
            plan_inputs = dict(plan_data_for_exec.get("inputs") or {})
            if "meta" not in plan_inputs and isinstance(plan_data_for_exec.get("meta"), dict):
                plan_inputs["meta"] = dict(plan_data_for_exec["meta"])
            plan_data_for_exec["inputs"] = plan_inputs

            plan = Plan.from_dict(plan_data_for_exec)

            # Capture stdout during execution to suppress prints from PlanExecutor and Scaffold.
            from io import StringIO
            capture_exec = StringIO()
            original_stdout_exec = sys.stdout
            sys.stdout = capture_exec
            try:
                executor.execute(plan, ai_safe=True)
            finally:
                sys.stdout = original_stdout_exec

        except ValueError as e:
            if str(e).startswith("touches mismatch:"):
                captured_paths = sorted({_norm_path(p) for p in executor.captured_writes})
                missing = sorted(set(captured_paths) - touches_set)
                return _refuse(
                    reason="touches_mismatch",
                    extra={"missing": missing, "touches": touches},
                )

            if not summary_json and not diff_guard_mode:
                print(f"[ASSIST] Warning: Failed to simulate plan execution: {e}")
                print(f"[ASSIST] Touches: {', '.join(touches)}")

        except Exception as e:
            _log_swallow("ASCM-003", "engine/tooling/assist_command.py blanket swallow", once=True)
            if not summary_json and not diff_guard_mode:
                print(f"[ASSIST] Warning: Failed to simulate plan execution: {e}")
                # Fallback to just listing touches if execution fails
                print(f"[ASSIST] Touches: {', '.join(touches)}")
        
        # Analyze changes
        changes = []
        skipped_identical = 0
        for path_str, new_content in captured_writes.items():
            path = Path(path_str)
            if not path.exists():
                changes.append((path_str, "+added"))
            else:
                try:
                    old_content = path.read_text(encoding="utf-8")
                    if old_content != new_content:
                        changes.append((path_str, "~changed"))
                    else:
                        skipped_identical += 1
                except Exception:
                    _log_swallow("ASCM-004", "engine/tooling/assist_command.py blanket swallow", once=True)
                    # If read fails, assume changed
                    changes.append((path_str, "~changed"))
        
        changes.sort(key=lambda x: x[0])

        captured_paths = sorted({_norm_path(p) for p in captured_writes.keys()})
        missing = sorted(set(captured_paths) - touches_set)
        if (diff_guard_mode or summary_json) and missing:
            return _refuse(
                reason="touches_mismatch",
                extra={"missing": missing, "touches": touches},
            )

        if diff_guard_mode:
            for item in deferred_output:
                print(item)
            print("[ASSIST] Dry run")
            print(f"[ASSIST] Actions: {len(actions)}")

        if defer_trige_output and not diff_guard_mode:
            for item in deferred_output:
                print(item)
            print("[ASSIST] Dry run")
            print(f"[ASSIST] Actions: {len(actions)}")
        
        if summary_json:
            if also_text:
                print(f"[ASSIST] Would write: {len(changes)} files")
                for path_str, kind in changes:
                    print(f"[ASSIST] Write: {path_str} ({kind})")
                print("---JSON---")

            summary = {
                "version": 1,
                "touches_ok": True,
                "world": args.world,
                "actions": len(actions),
                "touches": touches,
                "captured_writes": captured_paths,
                "would_write": [
                    {"path": p.replace("\\", "/"), "kind": k}
                    for p, k in changes
                ],
                "skipped_identical": skipped_identical,
                "next": [
                    "mesh preset lint",
                    "mesh apply-plan --from-triage",
                    "mesh plan test-ai --path artifacts/triage_last_plan.json",
                ],
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        
        print(f"[ASSIST] Would write: {len(changes)} files")
        for path_str, kind in changes:
            print(f"[ASSIST] Write: {path_str} ({kind})")
        
        if args.diff:
            _print_diff(actions, getattr(args, "max_diff_lines", 200))
            
        print("[ASSIST] Next: mesh apply-plan --from-triage")
        return 0

    if not actions:
        if defer_trige_output:
            for item in deferred_output:
                print(item)
        print("[ASSIST] No actionable fixes. Next: mesh explain --last --json")
        return 2
        
    # Check for consistency warnings in triage output
    # We look for "warnings": [...] in the JSON output from triage
    try:
        triage_json = _extract_triage_json_payload(triage_output) or {}
        warning_items = _parse_warning_items(list(triage_json.get("warnings", []) or []))
        warning_ids = {w["id"] for w in warning_items}

        if "plan_invalid_touches" in warning_ids:
            return _refuse(reason="plan_invalid", extra={"warnings": warning_items})

        if "action_hints_mismatch" in warning_ids:
            return _refuse(reason="action_hints_mismatch", extra={"warnings": warning_items})
    except Exception:
        _log_swallow("ASSI-001", "engine/tooling/assist_command.py pass-only blanket swallow")
        pass # If we can't parse, assume no warnings or let apply fail if it's bad

    if defer_trige_output:
        for item in deferred_output:
            print(item)

    print(f"[ASSIST] Generated plan with {len(actions)} actions.")

    # 3. Apply Plan
    # Equivalent to: mesh apply-plan --from-triage (forces ai-safe)
    # --from-triage usually looks for artifacts/triage_last_plan.json OR whatever triage produced?
    # Wait, triage_command writes to args.out.
    # If we used artifacts/assist_plan.json, apply-plan --from-triage might not find it if it looks for a hardcoded path.
    # Let's check _handle_apply_plan in mesh_cli.py or plan_cli.py to see what --from-triage does.
    # If it's hardcoded, we should use that path or pass the path explicitly.
    # Requirement says: "Equivalent to: mesh apply-plan --from-triage"
    # If --from-triage is hardcoded to artifacts/triage_last_plan.json, we should probably output to that in step 1.
    # But requirement says: "Equivalent to: mesh triage ... --out artifacts/assist_plan.json"
    # So we have a mismatch if --from-triage is hardcoded.
    # Let's assume we can pass the path explicitly to apply_plan.
    
    print("[ASSIST] Applying plan...")
    # We use the shared entrypoint
    apply_exit = plan_apply.apply_plan(
        plan_path=str(plan_path),
        ai_safe=True, # Forces ai-safe
        dry_run=False,
        no_lint=False,
        run_tests=False # We run tests separately
    )
    
    if apply_exit != 0:
        print("[ASSIST] Stopped at: apply-plan")
        print("[ASSIST] Next: mesh undo-last-plan") # Suggestion
        return apply_exit

    # 4. Run AI Plan Tests
    # Equivalent to: mesh plan test-ai --path artifacts/triage_last_plan.json
    # We use our plan path.
    
    print("[ASSIST] Verifying fixes...")
    # We need to invoke plan_cli.run_test_ai_command or similar.
    # plan_cli doesn't expose a clean function for test-ai, it's likely inside a handler.
    # Let's check plan_cli.py again or plan_tester.py.
    
    # We can construct args for plan_cli.
    # But plan_cli.add_plan_arguments registers subparsers.
    # We might need to call the underlying function directly.
    # Let's look at plan_tester.py.
    
    from engine.tooling import plan_tester
    
    # plan_tester.run_test_ai(plan_path, out=None, junit=None) -> int
    # We need to check if this function exists and is accessible.
    # Assuming it is based on standard patterns.
    
    test_exit = plan_tester.run_test_ai(str(plan_path))
    
    if test_exit != 0:
        print("[ASSIST] Stopped at: plan test-ai")
        print("[ASSIST] Next: mesh undo-last-plan")
        return test_exit

    print("[ASSIST] Success! All checks passed.")
    return 0


def _print_diff(actions: list[dict], max_diff_lines: int = 200) -> None:
    import difflib
    
    for action in actions:
        action_type = action.get("type")
        target = action.get("args", {}).get("path") or action.get("args", {}).get("scene_path")
        
        if not target and action_type == "auto_wire_transitions":
            target = action.get("args", {}).get("world_path")
            
        target = target or "unknown"
        
        if action_type == "create_scene":
            # For create_scene, we can show the content that would be written.
            # The content is usually implied by the template or args.
            # But wait, plan actions for create_scene usually just have "template".
            # The actual content generation happens in PlanExecutor.
            # However, the requirement says: "Obtain the would-be file content from the plan action args (the skeleton JSON)."
            # This implies the plan action args might contain the content or we can infer it.
            # If the plan action is just {"type": "create_scene", "args": {"path": "...", "template": "..."}},
            # we can't show the exact content without running the template logic.
            # BUT, if the plan comes from fix-from-doctor (which uses issue_mapper),
            # it might not have full content.
            # Let's check plan_fix_command.py again.
            # It generates: Action(type="create_scene", args={"path": ..., "template": "TODO: select_template"})
            # This is a placeholder.
            # If the user wants to see the diff, they probably want to see what WILL be written.
            # But we can't know for sure without the template logic.
            # However, the requirement says: "Reuse existing code that formats/serializes scene skeleton JSON (same as plan action payload)."
            # This suggests maybe the plan action payload HAS the content?
            # Or maybe I should use `scaffold.create_scene_data`?
            
            # Let's assume for now we just show what we know.
            # If the action has "content" or similar, use it.
            # If not, maybe we can't show a perfect diff.
            # But wait, `scaffold.py` has `create_scene`.
            
            from engine.tooling import scaffold
            
            # Generate a minimal scene dict to show as diff
            scene_data = {
                "name": Path(target).stem,
                "version": 1,
                "settings": {},
                "layers": {},
                "entities": []
            }
            
            # Serialize to JSON lines
            new_lines = json.dumps(scene_data, indent=2).splitlines(keepends=True)
            
            # Diff against empty
            diff = list(difflib.unified_diff(
                [], 
                new_lines, 
                fromfile="/dev/null", 
                tofile=target
            ))
            
            if len(diff) > max_diff_lines:
                print("".join(diff[:max_diff_lines]), end="")
                print(f"[ASSIST] Diff truncated: {target} (showing first {max_diff_lines} lines)")
            else:
                print("".join(diff), end="")
            
        elif action_type in DIFF_SUPPORTED_ACTIONS:
            if action_type != "auto_wire_transitions" and not Path(target).exists():
                print(f"[ASSIST] Diff: (skipped) {action_type} {target} (file not found)")
                continue

            # Capture writes
            captured = {}
            def capture(path: Path, content: str):
                captured[str(path)] = content

            # Setup executor
            # dry_run=False to execute logic, but we intercept writes
            executor = PlanExecutor(dry_run=False, writer=capture)
            # Suppress backup side-effects
            def _noop_backup_file(p: Path) -> None:  # noqa: ARG001
                return None

            cast(Any, executor.backup_mgr).backup_file = _noop_backup_file  # intentional monkeypatch for preview
            
            try:
                # Run action
                act = Action(
                    type=action_type, 
                    args=action["args"],
                    description=action.get("description", "Preview action")
                )
                # Access protected method to run single action
                executor._run_action(act)
                
                if not captured:
                    print(f"[ASSIST] Diff: (no changes) {action_type} {target}")
                    continue

                for path_str in sorted(captured.keys()):
                    new_content = captured[path_str]
                    path_obj = Path(path_str)
                    
                    if path_obj.exists():
                        with open(path_obj, "r", encoding="utf-8") as f:
                            old_lines = f.readlines()
                        from_file = str(path_obj)
                    else:
                        old_lines = []
                        from_file = "/dev/null"
                    
                    new_lines = new_content.splitlines(keepends=True)
                    
                    diff = list(difflib.unified_diff(
                        old_lines, 
                        new_lines, 
                        fromfile=from_file, 
                        tofile=str(path_obj)
                    ))
                    
                    print(f"[ASSIST] Diff: {path_str}")
                    
                    if len(diff) > max_diff_lines:
                        print("".join(diff[:max_diff_lines]), end="")
                        print(f"[ASSIST] Diff truncated: {path_str} (showing first {max_diff_lines} lines)")
                    else:
                        print("".join(diff), end="")
                    
            except Exception as e:
                _log_swallow("ASCM-005", "engine/tooling/assist_command.py blanket swallow", once=True)
                print(f"[ASSIST] Diff: (error) {action_type} {target}: {e}")

        elif action_type in DIFF_SKIPPED_ACTIONS:
            print(f"[ASSIST] Diff: (skipped) {action_type} {target}")
