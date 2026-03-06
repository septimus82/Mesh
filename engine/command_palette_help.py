"""Side-effect-free command-palette help content builder."""
from __future__ import annotations

from engine import command_palette_registry_defs as _defs


_STRUCTURED_ARG_FORMS: dict[str, tuple[str, ...]] = {
    "selection.align": (
        "token: left|center|right|top|middle|bottom",
        "kv: axis=<x|y>|mode=<...>|reference=<primary|group>",
    ),
    "selection.distribute": (
        "token: distribute_x_gap|distribute_x_center|distribute_y_gap|distribute_y_center",
        "kv: axis=<x|y>|mode=<gap|center>|reference=<group|primary>",
    ),
    "selection.snap_to_grid": (
        "token: snap_nearest|snap_floor|snap_ceil|snap_x_nearest|snap_y_nearest",
        "kv: step=<int>|axes=<x|y|xy>|mode=<nearest|floor|ceil>",
    ),
    "selection.nudge": (
        "token: <left|right|up|down> [x<count>] [step=<float>]",
        "kv: dx=<float>|dy=<float>|count=<int>|step=<float>",
    ),
    "selection.rotate": (
        "token: cw|ccw|180|<degrees>",
        "kv: deg=<float>|about=<self|group|primary>",
    ),
}


def _get_meta(command_id: str) -> dict[str, tuple[str, ...] | str]:
    entry = _defs.COMMAND_HELP_METADATA.get(command_id)
    if isinstance(entry, dict):
        return entry
    return {}


def _get_examples(command_id: str, *, meta: dict[str, tuple[str, ...] | str]) -> tuple[str, ...]:
    raw = meta.get("examples")
    if isinstance(raw, tuple):
        cleaned = tuple(str(v).strip() for v in raw if str(v).strip())
        if cleaned:
            return cleaned[:3]
    from engine.command_palette_preview import build_arg_suggestions  # noqa: PLC0415

    suggestions = tuple(build_arg_suggestions(command_id, ""))
    if suggestions:
        return suggestions[:3]
    return ("(no args)",)


def _get_arg_forms(command_id: str, *, meta: dict[str, tuple[str, ...] | str]) -> tuple[str, ...]:
    raw = meta.get("arg_forms")
    if isinstance(raw, tuple):
        cleaned = tuple(str(v).strip() for v in raw if str(v).strip())
        if cleaned:
            return cleaned
    return _STRUCTURED_ARG_FORMS.get(command_id, ())


def build_command_help_rows(
    command_id: str,
    *,
    command_title: str = "",
    command_section: str = "",
) -> list[str]:
    """Return deterministic help rows for command-palette rendering."""
    command_key = str(command_id or "").strip()
    title = str(command_title or "").strip()
    section = str(command_section or "").strip()
    meta = _get_meta(command_key)

    description = str(meta.get("description") or "").strip()
    if not description:
        display = title or command_key or "(none)"
        description = f"Run {display} from the command palette."

    examples = _get_examples(command_key, meta=meta)
    arg_forms = _get_arg_forms(command_key, meta=meta)

    rows: list[str] = []
    rows.extend(_defs.COMMAND_PALETTE_HELP_INTRO_LINES)
    rows.append(f"command: {command_key or '(none)'}")
    if title:
        rows.append(f"title: {title}")
    if section:
        rows.append(f"section: {section}")
    rows.append(f"description: {description}")
    rows.append("examples:")
    for example in examples:
        rows.append(f"- {example}")
    if arg_forms:
        rows.append("accepted args:")
        for form in arg_forms:
            rows.append(f"- {form}")
    return rows
