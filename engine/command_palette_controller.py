from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def handle_command_palette_cancel_or_close(window: Any) -> bool:
    if bool(getattr(window, "command_palette_prompt_active", False)):
        window.command_palette_prompt_active = False
        window.command_palette_prompt_text = ""
        window.command_palette_prompt_query = ""
        return True
    window.command_palette_enabled = False
    return True


def handle_command_palette_navigate(window: Any, direction: int) -> bool:
    if bool(getattr(window, "command_palette_prompt_active", False)):
        prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
        if prompt_kind == "pick":
            idx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
            window.command_palette_prompt_index = max(0, idx + direction)
        return True
    idx = int(getattr(window, "command_palette_index", 0) or 0)
    window.command_palette_index = max(0, idx + direction)
    return True


def handle_command_palette_activate(window: Any, snapshot: CaptureFocusSnapshot, *, repeat: bool) -> bool:
    """Handle command palette activation (ENTER or Ctrl+ENTER for repeat)."""
    import json as _json  # noqa: PLC0415
    from engine.command_palette import (  # noqa: PLC0415
        build_default_commands,
        filter_commands,
        filter_options,
    )

    commands = build_default_commands(window)
    by_id = {c.id: c for c in commands}

    if bool(getattr(window, "command_palette_prompt_active", False)):
        cmd_id = str(getattr(window, "command_palette_prompt_command_id", "") or "")
        cmd = by_id.get(cmd_id)
        if cmd is None:
            return True

        steps = getattr(window, "command_palette_prompt_steps", ())
        step_idx = int(getattr(window, "command_palette_prompt_step_index", 0) or 0)
        values = getattr(window, "command_palette_prompt_values", {})
        if not isinstance(values, dict):
            values = {}

        current_prompt = None
        if isinstance(steps, tuple) and steps and 0 <= step_idx < len(steps):
            current_prompt = steps[step_idx]
        elif getattr(cmd, "prompt", None) is not None:
            current_prompt = cmd.prompt

        if current_prompt is None:
            window.command_palette_prompt_active = False
            return True

        prompt_kind = str(getattr(current_prompt, "kind", "text") or "text").strip().lower()
        if prompt_kind == "pick":
            provider = getattr(current_prompt, "options_provider", None)
            options = provider(window) if callable(provider) else []
            filtered = filter_options(options, str(getattr(window, "command_palette_prompt_query", "") or ""))
            if not filtered:
                return True
            pidx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
            pidx = max(0, min(pidx, len(filtered) - 1))
            val: str | None = str(filtered[pidx][0])
        else:
            val = str(getattr(window, "command_palette_prompt_text", "") or "")

        if isinstance(steps, tuple) and steps:
            key_name = str(getattr(current_prompt, "field", None) or f"arg{step_idx}")
            values[key_name] = val
            window.command_palette_prompt_values = values
            next_idx = step_idx + 1
            if next_idx < len(steps):
                next_step = steps[next_idx]
                window.command_palette_prompt_step_index = next_idx
                window.command_palette_prompt_title = f"{cmd.title} ({next_idx + 1}/{len(steps)})"
                window.command_palette_prompt_placeholder = str(getattr(next_step, "placeholder", "") or "")
                window.command_palette_prompt_kind = str(getattr(next_step, "kind", "text") or "text")
                window.command_palette_prompt_index = 0
                try:
                    default_value = str(next_step.default_value_fn(window) or "")
                except Exception:  # noqa: BLE001
                    default_value = ""
                if str(window.command_palette_prompt_kind).strip().lower() == "pick":
                    window.command_palette_prompt_query = default_value
                    window.command_palette_prompt_text = ""
                else:
                    window.command_palette_prompt_text = default_value
                    window.command_palette_prompt_query = ""
                return True

            try:
                cmd.action(window, _json.dumps(values, sort_keys=True))
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                cmd.action(window, val)
            except Exception:  # noqa: BLE001
                pass

        print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
        window.command_palette_prompt_active = False
        window.command_palette_enabled = False
        window.command_palette_prompt_text = ""
        window.command_palette_prompt_query = ""
        return True

    # Not in prompt mode - activate selected command
    query = str(getattr(window, "command_palette_query", "") or "")
    filtered_cmds = filter_commands(commands, query)
    if not filtered_cmds:
        return True
    idx = int(getattr(window, "command_palette_index", 0) or 0)
    idx = max(0, min(idx, len(filtered_cmds) - 1))
    cmd = filtered_cmds[idx]

    # Handle repeat macro (Ctrl+Enter)
    if repeat and str(getattr(cmd, "macro_id", "") or "").strip():
        macro_id = str(getattr(cmd, "macro_id", "") or "").strip()
        last_args = getattr(window, "last_macro_args", None)
        last_args = last_args if isinstance(last_args, dict) else {}
        args = last_args.get(macro_id)
        if not isinstance(args, dict):
            print("AUTHOR_MACRO noop reason=no_last_args")
            return True
        cmd.action(window, _json.dumps(args, sort_keys=True))
        return True

    # Check enablement
    enabled, reason = True, ""
    try:
        enabled, reason = cmd.is_enabled(window)
    except Exception:  # noqa: BLE001
        enabled, reason = True, ""
    if not enabled:
        reason_text = str(reason or "disabled").strip()
        print(f"PALETTE_RUN noop id={cmd.id} reason={reason_text}")
        return True

    # Handle multi-step prompts
    steps = getattr(cmd, "prompts", None)
    if isinstance(steps, tuple) and steps:
        first = steps[0]
        window.command_palette_prompt_active = True
        window.command_palette_prompt_command_id = cmd.id
        window.command_palette_prompt_steps = steps
        window.command_palette_prompt_step_index = 0
        window.command_palette_prompt_values = {}
        window.command_palette_prompt_title = f"{cmd.title} (1/{len(steps)})"
        window.command_palette_prompt_placeholder = str(getattr(first, "placeholder", "") or "")
        window.command_palette_prompt_kind = str(getattr(first, "kind", "text") or "text")
        window.command_palette_prompt_index = 0
        try:
            default_value = str(first.default_value_fn(window) or "")
        except Exception:  # noqa: BLE001
            default_value = ""
        if str(window.command_palette_prompt_kind).strip().lower() == "pick":
            window.command_palette_prompt_query = default_value
            window.command_palette_prompt_text = ""
        else:
            window.command_palette_prompt_text = default_value
            window.command_palette_prompt_query = ""
        return True

    # Handle single prompt
    prompt = getattr(cmd, "prompt", None)
    if prompt is not None:
        window.command_palette_prompt_active = True
        window.command_palette_prompt_command_id = cmd.id
        window.command_palette_prompt_title = cmd.title
        window.command_palette_prompt_placeholder = str(getattr(prompt, "placeholder", "") or "")
        window.command_palette_prompt_kind = str(getattr(prompt, "kind", "text") or "text")
        window.command_palette_prompt_index = 0
        window.command_palette_prompt_steps = ()
        window.command_palette_prompt_step_index = 0
        window.command_palette_prompt_values = {}
        try:
            default_value = str(prompt.default_value_fn(window) or "")
        except Exception:  # noqa: BLE001
            default_value = ""
        if str(window.command_palette_prompt_kind).strip().lower() == "pick":
            window.command_palette_prompt_query = default_value
            window.command_palette_prompt_text = ""
        else:
            window.command_palette_prompt_text = default_value
            window.command_palette_prompt_query = ""
        return True

    # No prompt - run directly
    try:
        cmd.action(window, None)
    except Exception:  # noqa: BLE001
        pass
    print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
    window.command_palette_enabled = False
    return True


def handle_command_palette_toggle(window: Any) -> bool:
    window.command_palette_enabled = not bool(getattr(window, "command_palette_enabled", False))
    if bool(getattr(window, "command_palette_enabled", False)):
        window.command_palette_query = ""
        window.command_palette_index = 0
        window.command_palette_prompt_active = False
        window.command_palette_prompt_text = ""
        window.command_palette_prompt_kind = "text"
        window.command_palette_prompt_query = ""
        window.command_palette_prompt_index = 0
        window.command_palette_prompt_steps = ()
        window.command_palette_prompt_step_index = 0
        window.command_palette_prompt_values = {}
    return True
