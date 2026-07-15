"""Markdown documentation generator for Mesh Engine."""

from __future__ import annotations

import argparse
import filecmp
import tempfile
from pathlib import Path
from typing import Any, Iterable, cast

import engine.optional_arcade as optional_arcade
from mesh_cli.version_info import get_tool_version

from ..behaviours import list_behaviours, load_builtin_behaviours
from ..input import InputManager

arcade_mod = optional_arcade.arcade
from .project_index import build_project_index

SCENE_SPEC_PATH = Path("docs/mesh_scene_spec.md")
DOC_FILENAMES = {
    "behaviours": "behaviours.md",
    "input": "input.md",
    "console": "console.md",
    "scenes": "scenes.md",
}

EXAMPLE_COMMANDS: dict[str, list[str]] = {
    "entity": ["entity", "entity Player"],
    "entity <i|name>": ["entity 0", "entity Player"],
    "entity set <ref> ...": ["entity set 0 x 128", "entity set Player pos 64 320"],
    "spawn <sprite> <x> <y>": ["spawn assets/coin.png 100 200"],
    "spawn_like <ref> <x> <y>": ["spawn_like Player 200 350"],
    "dumpstate [path]": ["dumpstate", "dumpstate saves/test_state.json"],
    "loadstate <path>": ["loadstate saves/test_state.json"],
    "dump_scene [path]": ["dump_scene exports/scene_copy.json"],
    "validate_scene [path]": ["validate_scene scenes/test_scene.json"],
    "index [output] [scenes]": ["index", "index mesh_index.json custom_scenes"],
    "ai_context [path]": ["ai_context", "ai_context mesh_ai_context.json"],
    "docs [dir]": ["docs", "docs docs/mesh_docs"],
    "camera": ["camera"],
    "camera zoom <value>": ["camera zoom 1.2"],
    "camera shake <duration> <amplitude> [freq] [falloff]": [
        "camera shake 0.35 12",
        "camera shake 1.0 20 24 1.5",
    ],
    "camera areas": ["camera areas"],
    "camera stopshake": ["camera stopshake"],
}


def generate_docs(out_dir: Path | str = "docs") -> None:
    """Generate markdown docs describing the Mesh engine state."""

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    load_builtin_behaviours(force=True)
    behaviours = list_behaviours()
    input_bindings = _build_input_bindings_snapshot()
    console_sections = _fetch_console_help_sections()
    try:
        project_index = build_project_index()
    except Exception as exc:  # noqa: BLE001  # REASON: project-index generation failures should fall back to an error-shaped scenes doc payload
        project_index = {
            "error": str(exc),
            "scenes": [],
            "behaviours": [],
        }

    _write_behaviours_doc(output_dir / DOC_FILENAMES["behaviours"], behaviours)
    _write_input_doc(output_dir / DOC_FILENAMES["input"], input_bindings)
    _write_console_doc(output_dir / DOC_FILENAMES["console"], console_sections)
    _write_scenes_doc(output_dir / DOC_FILENAMES["scenes"], project_index)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Mesh markdown documentation")
    parser.add_argument(
        "--out-dir",
        default="docs",
        help="Directory where markdown files should be written (default: docs)",
    )
    parser.add_argument("--verify", action="store_true", help="Verify generated docs are up to date")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            return verify_docs(args.out_dir)
        generate_docs(args.out_dir)
    except Exception as exc:  # noqa: BLE001  # REASON: docs CLI failures should report the error and return a controlled nonzero exit code
        print(f"[Mesh][Docs] ERROR: {exc}")
        return 1

    target = Path(args.out_dir).resolve()
    print(f"[Mesh][Docs] Generated documentation in {target}")
    return 0


def verify_docs(out_dir: Path | str = "docs") -> int:
    """Return nonzero when committed generated docs differ from fresh output."""

    target = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix="mesh-docs-verify-") as temp_dir:
        temp_path = Path(temp_dir)
        generate_docs(temp_path)

        mismatches: list[str] = []
        for filename in DOC_FILENAMES.values():
            expected = temp_path / filename
            existing = target / filename
            if not existing.exists():
                mismatches.append(f"{filename}: missing")
                continue
            if not filecmp.cmp(expected, existing, shallow=False):
                mismatches.append(f"{filename}: stale")

    if mismatches:
        print("[Mesh][Docs] Verification FAILED:")
        for mismatch in mismatches:
            print(f"  - {mismatch}")
        print("[Mesh][Docs] Run 'python -m engine.tooling.generate_docs --out-dir docs' to regenerate.")
        return 1

    print("[Mesh][Docs] Verification PASSED.")
    return 0


def _write_behaviours_doc(path: Path, behaviours: Iterable[Any]) -> None:
    lines: list[str] = ["# Behaviours", "", "Behaviour registry exported from Mesh."]
    if not behaviours:
        lines.append("\n_No behaviours registered._")
    for info in behaviours:
        lines.append("")
        lines.append(f"## {info.name}")
        description = info.description.strip() if info.description else "(no description)"
        lines.append(description)
        lines.append("")
        lines.extend(_format_behaviour_fields_table(info.config_fields))
        lines.append("")
        example_field = _first_field_name(info.config_fields)
        lines.append("Example configuration snippet:")
        lines.append("```json")
        example_field_name = example_field or "config_field"
        lines.append("{")
        lines.append('  "name": "ExampleEntity",')
        lines.append('  "sprite": "assets/example.png",')
        lines.append('  "behaviours": ["' + info.name + '"],')
        lines.append('  "behaviour_config": {')
        lines.append('    "' + info.name + '": {')
        lines.append(f'      "{example_field_name}": "<value>"')
        lines.append("    }")
        lines.append("  }")
        lines.append("}")
        lines.append("```")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_input_doc(path: Path, bindings: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# Input Bindings",
        "",
        "Runtime bindings are configured via `config.json` -> `input_bindings`.",
        "",
        "For the canonical, player-facing keybind contract, see `docs/INPUT_BINDS.md`.",
        "",
        "Engine fallback defaults are bound via `InputManager.bind_default_actions(arcade)` when config bindings are absent.",
        "",
        "| Action | Default Key Name |",
        "| --- | --- |",
    ]
    if not bindings:
        lines.append("| _none_ | |")
    for action, entry in sorted(bindings.items()):
        names = ", ".join(entry.get("key_names", [])) or "-"
        lines.append(f"| `{action}` | `{names}` |")

    lines.extend(
        [
            "",
            "Note: debug/authoring hotkeys (for example `F3` debug, `F4` editor, `F5/F6` quick save/load) are "
            "handled directly in `engine/input_runtime/capture_runtime.py` and are not part of the action bindings "
            "table above.",
            "",
            "---",
            "",
            "## Input Architecture",
            "",
            "### Keyboard Input",
            "",
            "Keyboard events flow through `capture_runtime.py` -> `capture_key_router.py` which resolves keys to "
            "action IDs based on the current focus scope, then dispatches to handler modules.",
            "",
            "### Mouse Input",
            "",
            "Mouse events are handled by the **capture mouse router** (`engine/input_runtime/capture_mouse_router.py`).",
            "",
            "**Architecture:**",
            "- **Router** (`capture_mouse_router.py`): Glue-only module that builds/caches the route table, resolves "
            "events to action IDs, and dispatches via prefix registry. Contains no handler logic.",
            "- **Model** (`capture_mouse_router_model.py`): Route table schema (`MouseRouteSpec`), builder "
            "(`build_mouse_routes()`), validation (`validate_route_table()`), and audit functions.",
            "- **Per-scope handlers** (`capture_mouse_router_handlers_<scope>.py`): Each scope (tile_paint, "
            "entity_select, confirm_modal, etc.) has its own handler module with a `dispatch_*_mouse()` function.",
            "",
            "**Key files:**",
            "| File | Purpose |",
            "| --- | --- |",
            "| `capture_mouse_router.py` | Main router (glue + prefix dispatch) |",
            "| `capture_mouse_router_model.py` | Route specs, builder, validation |",
            "| `capture_mouse_router_handlers_*.py` | Per-scope handler modules |",
            "| `capture_mouse_router_handlers_*_base.py` | Shared helper utilities (no routes) |",
            "",
            "**Adding new mouse handlers:**",
            "1. Create `capture_mouse_router_handlers_<scope>.py` with a `dispatch_<scope>_mouse()` function",
            "2. Add routes in `build_mouse_routes()` in the model",
            "3. Register prefix in `MOUSE_PREFIX_DISPATCH` in the router",
            "",
            "**Deprecated shims:**",
            "The old monolithic handlers (`capture_mouse_router_handlers_paint.py`, "
            "`capture_mouse_router_handlers_select.py`) are frozen and deprecated. They exist only for backward "
            "compatibility and emit `DeprecationWarning` on import. Policy tests prevent new shims.",
            "",
            "See module docstrings in `capture_mouse_router.py` for detailed developer notes.",
        ],
    )

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_console_doc(
    path: Path,
    sections: Iterable[tuple[str, list[tuple[str, str]]]],
) -> None:
    lines = ["# Dev Console", "", "Command reference generated from GameWindow help sections."]
    for section, commands in sections:
        lines.append("")
        lines.append(f"## {section}")
        if not commands:
            lines.append("_No commands in this section._")
            continue
        for command, description in commands:
            desc = description or ""
            bullet = f"- **{command}**"
            if desc:
                bullet += f" -- {desc}"
            lines.append(bullet)
            examples = EXAMPLE_COMMANDS.get(command)
            if examples:
                lines.append("  *Examples:*")
                for example in examples:
                    lines.append(f"    - `{example}`")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_scenes_doc(path: Path, project_index: dict[str, Any]) -> None:
    scenes = project_index.get("scenes", []) if isinstance(project_index, dict) else []
    lines = [
        "# Scenes",
        "",
        f"Mesh scene schema lives at `{SCENE_SPEC_PATH.as_posix()}`.",
        "",
        f"Engine version: {get_tool_version()}",
    ]
    if isinstance(project_index, dict) and project_index.get("error"):
        lines.append("")
        lines.append(f"_Indexer warning: {project_index['error']}_")
    if not scenes:
        lines.append("\n_No scenes discovered. Run project index to populate data._")
    for scene in scenes:
        path_value = scene.get("path", "<unknown>")
        lines.append("")
        lines.append(f"## {path_value}")
        valid = scene.get("valid")
        errors = scene.get("errors", [])
        warnings = scene.get("warnings", [])
        if valid:
            status = "[ok] Valid"
        elif errors:
            status = "[error] Errors detected"
        else:
            status = "[warn] Needs review"
        lines.append(status)
        lines.append("")
        meta_lines = [
            f"- Entities: {scene.get('entity_count', '?')}",
            f"- Layers: {', '.join(scene.get('layers', [])) or '-'}",
            f"- Tags: {', '.join(scene.get('tags', [])) or '-'}",
        ]
        lines.extend(meta_lines)
        if warnings:
            lines.append("- Warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")
        if errors:
            lines.append("- Errors:")
            for error in errors:
                lines.append(f"  - {error}")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _build_input_bindings_snapshot() -> dict[str, dict[str, Any]]:
    manager = InputManager()
    if arcade_mod is not None:
        manager.bind_default_actions(arcade_mod)
    bindings = manager.get_bindings()
    snapshot: dict[str, dict[str, Any]] = {}
    for action, codes in sorted(bindings.items()):
        key_codes = [int(code) for code in codes]
        snapshot[action] = {
            "key_codes": key_codes,
            "key_names": _key_names_for_codes(key_codes, arcade_mod=arcade_mod),
        }
    snapshot["save_game"] = {
        "key_codes": [],
        "key_names": ["Ctrl+F5"],
    }
    return snapshot


def _key_names_for_codes(codes: Iterable[int], *, arcade_mod: object | None) -> list[str]:
    key_names = _key_name_map(arcade_mod=arcade_mod)
    names: list[str] = []
    for code in codes:
        names.append(key_names.get(int(code), f"KEY_{code}"))
    return names


def _key_name_map(*, arcade_mod: object | None) -> dict[int, str]:
    key_module = getattr(arcade_mod, "key", None) if arcade_mod is not None else None
    if key_module is None:
        return {}

    preferred: dict[int, tuple[int, str]] = {}
    for name in dir(key_module):
        if not name.isupper() or name.startswith("_"):
            continue
        value = getattr(key_module, name, None)
        if not isinstance(value, int):
            continue
        priority = _key_name_priority(name)
        current = preferred.get(int(value))
        if current is None or (priority, name) < current:
            preferred[int(value)] = (priority, name)
    return {code: name for code, (_, name) in preferred.items()}


def _key_name_priority(name: str) -> int:
    if len(name) == 1 and name.isalnum():
        return 0
    if name in {"SPACE", "TAB", "ESCAPE"}:
        return 1
    if name.startswith("F") and name[1:].isdigit():
        return 2
    return 3


def _format_behaviour_fields_table(fields: Iterable[Any]) -> list[str]:
    lines = ["| Name | Description | Type | Default |", "| --- | --- | --- | --- |"]
    any_rows = False
    for entry in fields or []:
        any_rows = True
        if isinstance(entry, dict):
            name = entry.get("name", "")
            description = entry.get("description", "")
            field_type = entry.get("type", "")
            default = entry.get("default", "")
        elif isinstance(entry, (tuple, list)):
            name = entry[0] if entry else ""
            description = entry[1] if len(entry) >= 2 else ""
            field_type = entry[2] if len(entry) >= 3 else ""
            default = entry[3] if len(entry) >= 4 else ""
        else:
            name = str(entry)
            description = ""
            field_type = ""
            default = ""
        lines.append(
            "| {name} | {desc} | {type} | {default} |".format(
                name=name or "-",
                desc=description or "-",
                type=field_type or "-",
                default=default if default not in (None, "") else "-",
            ),
        )
    if not any_rows:
        lines.append("| _No config fields_ | | | |")
    return lines


def _first_field_name(fields: Iterable[Any]) -> str | None:
    for entry in fields or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if name:
                return str(name)
        elif isinstance(entry, (tuple, list)) and entry:
            return str(entry[0])
    return None


def _fetch_console_help_sections() -> list[tuple[str, list[tuple[str, str]]]]:
    # Import lazily to avoid circular imports with engine.game.
    from ..console_controller import ConsoleController  # noqa: PLC0415 # REASON: lazy import avoids circular import with engine.game

    # We need an instance to get the help sections, but we can't easily create a GameWindow here.
    # However, ConsoleController.help_sections is an instance method but doesn't use self.
    # Let's try to call it as a static method or create a dummy controller if needed.
    # Actually, looking at ConsoleController, help_sections IS an instance method but it returns static data.
    # Let's just instantiate it with a dummy window or extract the data.
    # Better yet, let's just manually replicate the structure or fix the import.

    # The previous code was trying to call GameWindow.console_help_sections() which didn't exist.
    # The data is in ConsoleController.help_sections().

    # Let's try to instantiate a dummy controller.
    class DummyWindow:
        pass

    controller = ConsoleController(cast(Any, DummyWindow()))
    return controller.help_sections()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
