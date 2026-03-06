from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from engine.command_palette_preview import build_arg_suggestions

if TYPE_CHECKING:
    from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


_SWALLOW_ONCE_TAGS: set[str] = set()


def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__ + "._swallow").debug("SWALLOW[%s] %s", tag, context, exc_info=True)


@dataclass
class CommandPalettePromptHistory:
    """In-memory prompt argument history keyed by command id."""

    max_entries_per_command: int = 32
    entries_by_command: dict[str, list[str]] = field(default_factory=dict)
    active_command_id: str = ""
    browse_index: int | None = None
    scratch_text: str = ""

    def push(self, command_id: str, raw_arg: str) -> bool:
        cmd_id = str(command_id or "").strip()
        if not cmd_id:
            return False
        value = str(raw_arg or "")
        if not value.strip():
            return False
        rows = self.entries_by_command.setdefault(cmd_id, [])
        if rows and rows[-1] == value:
            return False
        rows.append(value)
        if len(rows) > int(self.max_entries_per_command):
            del rows[: len(rows) - int(self.max_entries_per_command)]
        return True

    def reset_cursor(self, command_id: str, current_text: str) -> None:
        self.active_command_id = str(command_id or "").strip()
        self.browse_index = None
        self.scratch_text = str(current_text or "")

    def browse(self, command_id: str, current_text: str, direction: int) -> str:
        cmd_id = str(command_id or "").strip()
        typed = str(current_text or "")
        rows = self.entries_by_command.get(cmd_id, [])
        if not rows:
            self.reset_cursor(cmd_id, typed)
            return typed

        if self.active_command_id != cmd_id:
            self.reset_cursor(cmd_id, typed)

        if int(direction) < 0:
            if self.browse_index is None:
                self.scratch_text = typed
                self.browse_index = len(rows) - 1
            elif self.browse_index > 0:
                self.browse_index -= 1
            return rows[self.browse_index]

        if int(direction) > 0:
            if self.browse_index is None:
                return typed
            if self.browse_index < len(rows) - 1:
                self.browse_index += 1
                return rows[self.browse_index]
            self.browse_index = None
            return self.scratch_text

        return typed

    def get_entries(self, command_id: str) -> tuple[str, ...]:
        cmd_id = str(command_id or "").strip()
        rows = self.entries_by_command.get(cmd_id, [])
        return tuple(rows)


@dataclass
class CommandPaletteRecentCommands:
    """In-memory recent command ids (most-recent-first, deduped)."""

    max_entries: int = 12
    command_ids: list[str] = field(default_factory=list)

    def push(self, command_id: str) -> bool:
        cmd_id = str(command_id or "").strip()
        if not cmd_id:
            return False
        if self.command_ids and self.command_ids[0] == cmd_id:
            return False
        self.command_ids = [value for value in self.command_ids if value != cmd_id]
        self.command_ids.insert(0, cmd_id)
        if len(self.command_ids) > int(self.max_entries):
            del self.command_ids[int(self.max_entries) :]
        return True

    def get_entries(self) -> tuple[str, ...]:
        return tuple(self.command_ids)


def _get_prompt_history(window: Any) -> CommandPalettePromptHistory:
    hist = getattr(window, "_command_palette_prompt_history", None)
    if isinstance(hist, CommandPalettePromptHistory):
        return hist
    hist = CommandPalettePromptHistory()
    setattr(window, "_command_palette_prompt_history", hist)
    return hist


def get_command_palette_prompt_history_entries(window: Any, command_id: str) -> tuple[str, ...]:
    return _get_prompt_history(window).get_entries(command_id)


def _get_recent_commands(window: Any) -> CommandPaletteRecentCommands:
    recent = getattr(window, "_command_palette_recent_commands", None)
    if isinstance(recent, CommandPaletteRecentCommands):
        return recent
    recent = CommandPaletteRecentCommands()
    setattr(window, "_command_palette_recent_commands", recent)
    return recent


def get_command_palette_recent_command_ids(window: Any) -> tuple[str, ...]:
    return _get_recent_commands(window).get_entries()


def _ensure_persisted_palette_state_loaded(window: Any) -> None:
    if bool(getattr(window, "_command_palette_state_loaded", False)):
        return
    from engine.command_palette_state import load_command_palette_state  # noqa: PLC0415

    recent = _get_recent_commands(window)
    history = _get_prompt_history(window)
    loaded_recents, loaded_history = load_command_palette_state(
        max_recents=int(recent.max_entries),
        max_entries_per_command=int(history.max_entries_per_command),
    )
    recent.command_ids = list(loaded_recents)
    history.entries_by_command = {str(k): list(v) for k, v in loaded_history.items()}
    setattr(window, "_command_palette_state_loaded", True)


def _save_persisted_palette_state(window: Any) -> None:
    if not bool(getattr(window, "_command_palette_state_loaded", False)):
        return
    from engine.command_palette_state import save_command_palette_state  # noqa: PLC0415

    recent = _get_recent_commands(window)
    history = _get_prompt_history(window)
    save_command_palette_state(
        recents=recent.command_ids,
        history=history.entries_by_command,
        max_recents=int(recent.max_entries),
        max_entries_per_command=int(history.max_entries_per_command),
    )


def clear_command_palette_recent_commands(window: Any) -> int:
    recent = _get_recent_commands(window)
    count = len(recent.command_ids)
    recent.command_ids = []
    if count > 0:
        _save_persisted_palette_state(window)
    return int(count)


def _reset_prompt_history_cursor(window: Any, *, command_id: str | None = None, current_text: str | None = None) -> None:
    cmd_id = (
        str(command_id)
        if command_id is not None
        else str(getattr(window, "command_palette_prompt_command_id", "") or "")
    )
    text = (
        str(current_text)
        if current_text is not None
        else str(getattr(window, "command_palette_prompt_text", "") or "")
    )
    _get_prompt_history(window).reset_cursor(cmd_id, text)


def handle_command_palette_prompt_text_changed(window: Any) -> None:
    _reset_prompt_history_cursor(window)


def _push_prompt_history(window: Any, *, command_id: str, raw_arg: str, success: bool) -> bool:
    if not bool(success):
        return False
    return _get_prompt_history(window).push(command_id, raw_arg)


def _push_recent_command(window: Any, *, command_id: str, success: bool) -> bool:
    if not bool(success):
        return False
    return _get_recent_commands(window).push(command_id)


def handle_command_palette_history_navigate(window: Any, direction: int) -> bool:
    if not bool(getattr(window, "command_palette_prompt_active", False)):
        return False
    prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
    if prompt_kind != "text":
        return True
    command_id = str(getattr(window, "command_palette_prompt_command_id", "") or "")
    current_text = str(getattr(window, "command_palette_prompt_text", "") or "")
    next_text = _get_prompt_history(window).browse(command_id, current_text, int(direction))
    if next_text != current_text:
        window.command_palette_prompt_text = next_text
        window.command_palette_prompt_index = 0
    return True


def handle_command_palette_toggle_help(window: Any) -> bool:
    if not bool(getattr(window, "command_palette_enabled", False)):
        return False
    current = bool(getattr(window, "command_palette_help_enabled", False))
    window.command_palette_help_enabled = not current
    return True


def handle_command_palette_cancel_or_close(window: Any) -> bool:
    if bool(getattr(window, "command_palette_prompt_active", False)):
        window.command_palette_prompt_active = False
        window.command_palette_prompt_text = ""
        window.command_palette_prompt_query = ""
        _reset_prompt_history_cursor(window, current_text="")
        return True
    window.command_palette_enabled = False
    return True


def handle_command_palette_navigate(window: Any, direction: int) -> bool:
    if bool(getattr(window, "command_palette_prompt_active", False)):
        prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
        if prompt_kind == "pick":
            idx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
            window.command_palette_prompt_index = max(0, idx + direction)
        elif prompt_kind == "text":
            command_id = str(getattr(window, "command_palette_prompt_command_id", "") or "")
            current_text = str(getattr(window, "command_palette_prompt_text", "") or "")
            suggestions = build_arg_suggestions(command_id, current_text)
            if suggestions:
                idx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
                idx = max(0, min(idx + int(direction), len(suggestions) - 1))
                window.command_palette_prompt_index = idx
        return True
    idx = int(getattr(window, "command_palette_index", 0) or 0)
    window.command_palette_index = max(0, idx + direction)
    return True


def handle_command_palette_activate(window: Any, snapshot: "CaptureFocusSnapshot", *, repeat: bool) -> bool:
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
            typed = str(getattr(window, "command_palette_prompt_text", "") or "")
            suggestions = build_arg_suggestions(cmd.id, typed)
            if suggestions:
                pidx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
                pidx = max(0, min(pidx, len(suggestions) - 1))
                chosen = str(suggestions[pidx] or "")
                if chosen and chosen != typed:
                    window.command_palette_prompt_text = chosen
                    _reset_prompt_history_cursor(window)
                    return True
            val = typed

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
                except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
                    _log_swallow("CMDP-001", "next_step.default_value_fn failed in multi-step prompt")
                    default_value = ""
                if str(window.command_palette_prompt_kind).strip().lower() == "pick":
                    window.command_palette_prompt_query = default_value
                    window.command_palette_prompt_text = ""
                else:
                    window.command_palette_prompt_text = default_value
                    window.command_palette_prompt_query = ""
                _reset_prompt_history_cursor(window, command_id=cmd.id, current_text=window.command_palette_prompt_text)
                return True

            action_ok = True
            try:
                cmd.action(window, _json.dumps(values, sort_keys=True))
            except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
                _log_swallow("CMDP-002", f"cmd.action failed for multi-step command id={cmd.id}")
                action_ok = False
            changed = False
            if prompt_kind == "text" and isinstance(val, str):
                changed = _push_prompt_history(window, command_id=cmd.id, raw_arg=val, success=action_ok) or changed
            changed = _push_recent_command(window, command_id=cmd.id, success=action_ok) or changed
            if changed:
                _save_persisted_palette_state(window)
        else:
            action_ok = True
            try:
                cmd.action(window, val)
            except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
                _log_swallow("CMDP-003", f"cmd.action failed for single-prompt command id={cmd.id}")
                action_ok = False
            changed = False
            if prompt_kind == "text" and isinstance(val, str):
                changed = _push_prompt_history(window, command_id=cmd.id, raw_arg=val, success=action_ok) or changed
            changed = _push_recent_command(window, command_id=cmd.id, success=action_ok) or changed
            if changed:
                _save_persisted_palette_state(window)

        print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
        window.command_palette_prompt_active = False
        window.command_palette_enabled = False
        window.command_palette_help_enabled = False
        window.command_palette_prompt_text = ""
        window.command_palette_prompt_query = ""
        _reset_prompt_history_cursor(window, command_id=cmd.id, current_text="")
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
        if _push_recent_command(window, command_id=cmd.id, success=True):
            _save_persisted_palette_state(window)
        return True

    # Check enablement
    enabled, reason = True, ""
    try:
        enabled, reason = cmd.is_enabled(window)
    except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
        _log_swallow("CMDP-004", f"cmd.is_enabled failed for command id={cmd.id}")
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
        except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
            _log_swallow("CMDP-005", f"first.default_value_fn failed for multi-step command id={cmd.id}")
            default_value = ""
        if str(window.command_palette_prompt_kind).strip().lower() == "pick":
            window.command_palette_prompt_query = default_value
            window.command_palette_prompt_text = ""
        else:
            window.command_palette_prompt_text = default_value
            window.command_palette_prompt_query = ""
        _reset_prompt_history_cursor(window, command_id=cmd.id, current_text=window.command_palette_prompt_text)
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
        except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
            _log_swallow("CMDP-006", f"prompt.default_value_fn failed for command id={cmd.id}")
            default_value = ""
        if str(window.command_palette_prompt_kind).strip().lower() == "pick":
            window.command_palette_prompt_query = default_value
            window.command_palette_prompt_text = ""
        else:
            window.command_palette_prompt_text = default_value
            window.command_palette_prompt_query = ""
        _reset_prompt_history_cursor(window, command_id=cmd.id, current_text=window.command_palette_prompt_text)
        return True

    # No prompt - run directly
    action_ok = True
    try:
        cmd.action(window, None)
    except Exception:  # noqa: BLE001  # REASON: command palette controller fallback isolation
        _log_swallow("CMDP-007", f"cmd.action failed for no-prompt command id={cmd.id}")
        action_ok = False
    if _push_recent_command(window, command_id=cmd.id, success=action_ok):
        _save_persisted_palette_state(window)
    print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
    window.command_palette_enabled = False
    window.command_palette_help_enabled = False
    return True


def handle_command_palette_toggle(window: Any) -> bool:
    window.command_palette_enabled = not bool(getattr(window, "command_palette_enabled", False))
    if bool(getattr(window, "command_palette_enabled", False)):
        _ensure_persisted_palette_state_loaded(window)
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
        window.command_palette_help_enabled = False
        _reset_prompt_history_cursor(window, current_text="")
    else:
        window.command_palette_help_enabled = False
    return True
