import argparse
import json
import os
import sys
from typing import Any

from engine.config import load_config
from engine.tooling import build_demo_command, release_command
from engine.tooling.preset_policy import validate_preset_python_step, get_preset_policy_snapshot, validate_preset_env

# Private alias for backward compatibility if needed, but prefer using the imported one
_validate_python_step = validate_preset_python_step


def run_preset_command(args: argparse.Namespace) -> None:
    """Run a command preset defined in config."""
    preset_name = args.name
    config = load_config()

    lint_stage = build_preset_lint_stage_result(config)
    if not lint_stage["ok"]:
        print(json.dumps(lint_stage, sort_keys=True))
        sys.exit(2)

    presets = getattr(config, "presets", {})
    if preset_name not in presets:
        print(f"[Mesh][Preset] ERROR: Preset '{preset_name}' not found in config.")
        print("Available presets:", ", ".join(presets.keys()))
        return

    preset = presets[preset_name]

    description = ""
    notes = ""
    steps = None

    if isinstance(preset, list):
        steps = preset
    elif isinstance(preset, dict):
        description = preset.get("description", "")
        notes = preset.get("notes", "")
        steps = preset.get("steps")

    # Prepare environment variables
    env_vars = {}
    if isinstance(preset, dict):
        env_vars = preset.get("env", {}).copy()

    # Always set preset metadata
    env_vars["MESH_ACTIVE_PRESET"] = preset_name
    if description:
        env_vars["MESH_PRESET_DESCRIPTION"] = description
    if notes:
        env_vars["MESH_PRESET_NOTES"] = notes

    # Store original env vars to restore later
    original_env = {}
    vars_to_set = {}

    for k, v in env_vars.items():
        vars_to_set[k] = str(v)

    for k, v in vars_to_set.items():
        if k in os.environ:
            original_env[k] = os.environ[k]
        os.environ[k] = v

    try:
        if steps is not None:
            for i, step in enumerate(steps):
                cmd = step.get("cmd")
                cmd_args = step.get("args", [])

                if cmd == "python":
                    import subprocess
                    print(f"[Mesh][Preset] Running python {' '.join(cmd_args)}...")
                    # Use sys.executable to ensure we use the same python environment
                    ret = subprocess.call([sys.executable] + cmd_args)
                    if ret != 0:
                        print(f"[Mesh][Preset] Python command failed with code {ret}.")
                        sys.exit(ret)
                    continue

                if cmd:
                    print(f"[Mesh][Preset] Running '{cmd}'...")
                    import mesh_cli

                    ret = mesh_cli.main([cmd] + cmd_args)
                    if ret != 0:
                        print(f"[Mesh][Preset] Command '{cmd}' failed with code {ret}.")
                        sys.exit(ret)
            return

        action = preset.get("action", "release-check")
        preset_args = preset.get("args", {})

        print(f"[Mesh][Preset] Running preset '{preset_name}' (Action: {action})...")

        # Construct a new Namespace merging CLI args (if any) with preset args
        # For now, we just use preset args.
        # We need to map dictionary args to Namespace attributes.

        # Create a dummy namespace with defaults
        # This is tricky because we don't know all defaults for the target command.
        # But the target command functions usually expect specific args.

        # Let's create a Namespace from the preset args
        cmd_args = argparse.Namespace(**preset_args)

        # We might need to fill in missing required args if they aren't in preset.
        # For release-check, 'world_path' is required.

        if action == "release-check":
            if not hasattr(cmd_args, "world_path"):
                # Fallback to config default world if not specified?
                # Or error out.
                if config.world_file:
                    cmd_args.world_path = config.world_file
                else:
                    print("[Mesh][Preset] ERROR: Preset for release-check must specify 'world_path' or config must have 'world_file'.")
                    return

            # Ensure other optional args exist as None if not present
            defaults = [
                "max_unused_assets", "max_unused_prefabs", "max_unused_items",
                "max_unused_quests", "ignore", "allow_packs", "baseline",
                "max_unused_delta", "diff_from", "emit_changelog", "profile"
            ]
            for d in defaults:
                if not hasattr(cmd_args, d):
                    setattr(cmd_args, d, None)

            release_command.release_check_command(cmd_args)

        elif action == "build-demo":
            # build-demo args: out (required?)
            if not hasattr(cmd_args, "out"):
                 print("[Mesh][Preset] ERROR: Preset for build-demo must specify 'out'.")
                 return

            build_demo_command.handle_build_demo(cmd_args)

        elif action == "check":
            # check command (from check.py)
            from engine.tooling import check
            # check command takes no args usually, or maybe scene_path?
            # check.main() takes argv.
            # Let's assume it's the simple check.
            check.main([])

        else:
            print(f"[Mesh][Preset] ERROR: Unknown action '{action}'. Supported: release-check, build-demo, check")

    finally:
        # Restore environment variables
        for k in vars_to_set:
            if k in original_env:
                os.environ[k] = original_env[k]
            else:
                if k in os.environ:
                    del os.environ[k]


def validate_presets(config) -> dict:
    """Validate presets in config and return result dict."""
    presets = getattr(config, "presets", {})
    
    issues: list[dict] = []
    presets_checked = 0

    def _add_issue(
        *,
        issue_id: str,
        preset: str,
        step_index: int | None,
        message: str,
        detail: dict | None = None,
    ) -> None:
        issue: dict[str, Any] = {
            "id": issue_id,
            "preset": preset,
            "step_index": int(step_index) if step_index is not None else None,
            "message": str(message),
        }
        if detail is not None:
            issue["detail"] = detail
        issues.append(issue)
    
    for preset_name, preset in presets.items():
        presets_checked += 1
        
        # Schema Validation
        if not isinstance(preset, dict):
            _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="Preset must be a dictionary")
            continue

        if "env" in preset:
            env_issues = validate_preset_env(preset.get("env"))
            for env_issue in env_issues:
                _add_issue(
                    issue_id="preset_env_invalid",
                    preset=preset_name,
                    step_index=None,
                    message=str(env_issue.get("message", "Invalid preset env")),
                    detail=dict(env_issue.get("detail") or {}),
                )
            
        if "description" not in preset:
            _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="Missing 'description'")
        elif not isinstance(preset["description"], str) or not preset["description"].strip():
            _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="Description must be a non-empty string")
            
        has_steps = "steps" in preset
        has_action = "action" in preset
        
        if not (has_steps or has_action):
            _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="Must have 'steps' or 'action'")
            
        if has_steps:
            steps = preset["steps"]
            if not isinstance(steps, list):
                _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="'steps' must be a list")
                continue
                
            if not steps:
                _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="'steps' cannot be empty")
                continue
                
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=i, message="Step must be a dictionary")
                    continue
                    
                if "cmd" not in step:
                    _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=i, message="Step missing 'cmd'")
                    continue
                    
                cmd = step["cmd"]
                if not isinstance(cmd, str):
                    _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=i, message="'cmd' must be a string")
                    continue
                    
                if "args" in step:
                    if not isinstance(step["args"], list):
                        _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=i, message="'args' must be a list")
                        continue
                    for arg in step["args"]:
                        if not isinstance(arg, str):
                            _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=i, message="Step args must be strings")
                
                # Python Step Validation
                if cmd == "python":
                    try:
                        _validate_python_step(step.get("args", []))
                    except ValueError as e:
                        _add_issue(
                            issue_id="preset_step_invalid",
                            preset=preset_name,
                            step_index=i,
                            message=str(e),
                            detail={"cmd": "python", "args": list(step.get("args", []))},
                        )

        if has_action:
            if not isinstance(preset["action"], str):
                _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="'action' must be a string")
            if "args" in preset and not isinstance(preset["args"], dict):
                _add_issue(issue_id="preset_step_invalid", preset=preset_name, step_index=-1, message="Action 'args' must be a dictionary")

    if issues:
        # Sort errors deterministically
        def _sort_key(item: dict) -> tuple:
            detail = item.get("detail") or {}
            key = str(detail.get("key") or "")
            step_index = item.get("step_index")
            step_sort = int(step_index) if isinstance(step_index, int) else 10**9
            return (
                str(item.get("preset") or ""),
                str(item.get("id") or ""),
                key,
                step_sort,
                str(item.get("message") or ""),
                json.dumps(detail, sort_keys=True),
            )

        issues.sort(key=_sort_key)
        
        return {
            "version": 1,
            "ok": False,
            "presets_checked": presets_checked,
            "issues": issues,
            "policy": get_preset_policy_snapshot()
        }
    else:
        return {
            "version": 1,
            "ok": True,
            "presets_checked": presets_checked,
            "issues": [],
            "policy": get_preset_policy_snapshot()
        }


def build_preset_lint_stage_result(config) -> dict:
    """Return a preset-lint stage result with a stable schema."""
    result = validate_presets(config)
    stage_result = dict(result)
    stage_result["stage"] = "preset_lint"

    stage_result.setdefault("version", 1)
    stage_result.setdefault("ok", True)
    stage_result.setdefault("presets_checked", 0)
    stage_result.setdefault("issues", [])
    stage_result.setdefault("policy", get_preset_policy_snapshot())

    return stage_result


def run_preset_lint_command(args: argparse.Namespace) -> int:
    """Lint all presets in config."""
    config = load_config()
    result = build_preset_lint_stage_result(config)
    print(json.dumps(result, sort_keys=True))
    return 2 if not result["ok"] else 0
