"""Command palette - command definition and filtering.

This module provides the command palette infrastructure for Mesh Engine.
Commands are defined declaratively in DEFAULT_COMMAND_DEFS and converted
to CommandSpec objects at runtime by build_default_commands().

The refactored design separates:
- Static command definitions (this module)
- Helper functions (command_palette_registry.py)
- Runtime conversion (build_default_commands)
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, TypedDict
import engine.optional_arcade as optional_arcade


@functools.lru_cache(maxsize=1)
def _list_prefab_ids_from_assets() -> tuple[str, ...]:
    """Return cached list of prefab IDs from assets/prefabs.json."""
    try:
        from engine.paths import resolve_path  # noqa: PLC0415

        path = resolve_path("assets/prefabs.json")
        if not Path(path).exists():
            return ()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ()

    ids: list[str] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            pid = entry.get("id")
            if isinstance(pid, str) and pid.strip():
                ids.append(pid.strip())
    elif isinstance(raw, dict):
        for pid in raw.keys():
            if isinstance(pid, str) and pid.strip():
                ids.append(pid.strip())
    return tuple(sorted(set(ids)))


def _list_behaviour_names() -> tuple[str, ...]:
    """Return cached list of behaviour names from the registry."""
    try:
        from engine.behaviours import BEHAVIOUR_REGISTRY  # noqa: PLC0415

        return tuple(sorted({str(k).strip() for k in BEHAVIOUR_REGISTRY.keys() if isinstance(k, str) and str(k).strip()}))
    except Exception:  # noqa: BLE001
        return ()


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PromptSpec:
    """Specification for a command prompt (text input or picker)."""
    kind: str  # "text" | "pick"
    placeholder: str
    default_value_fn: Callable[[Any], str]
    options_provider: Callable[[Any], list[tuple[str, str]]] | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Specification for a command in the command palette."""
    id: str
    title: str
    section: str
    keywords: tuple[str, ...]
    is_enabled: Callable[[Any], tuple[bool, str]]
    prompt: PromptSpec | None
    action: Callable[[Any, str | None], None]
    prompts: tuple[PromptSpec, ...] | None = None
    hotkey_hint: str | None = None
    repeat_macro_id: str | None = None
    macro_id: str | None = None
    macro_asset_path: str | None = None
    macro_defaults: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _normalize_query(query: str) -> str:
    """Normalize a search query for matching."""
    return " ".join(str(query or "").strip().lower().split())


def filter_commands(commands: Iterable[CommandSpec], query: str) -> list[CommandSpec]:
    """Filter and rank commands by query match."""
    q = _normalize_query(query)
    out: list[tuple[tuple[int, int, str, str], CommandSpec]] = []
    for cmd in commands:
        title = str(cmd.title or "").strip()
        if not title:
            continue
        title_l = title.lower()

        if not q:
            out.append(((0, 0, title_l, str(cmd.id)), cmd))
            continue

        rank = 999
        pos = 999
        if title_l.startswith(q):
            rank = 0
            pos = 0
        else:
            p = title_l.find(q)
            if p >= 0:
                rank = 1
                pos = p
            else:
                kw_pos = None
                for kw in (cmd.keywords or ()):
                    kw_l = str(kw).strip().lower()
                    if not kw_l:
                        continue
                    kp = kw_l.find(q)
                    if kp >= 0:
                        kw_pos = kp if kw_pos is None else min(kw_pos, kp)
                if kw_pos is not None:
                    rank = 2
                    pos = int(kw_pos)

        if rank != 999:
            out.append(((int(rank), int(pos), title_l, str(cmd.id)), cmd))

    out.sort(key=lambda pair: pair[0])
    return [cmd for _score, cmd in out]


def filter_options(options: Iterable[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    """Filter and rank options by query match."""
    q = _normalize_query(query)
    scored: list[tuple[tuple[int, int, str, str], tuple[str, str]]] = []
    for value, label in options:
        v = str(value or "").strip()
        l = str(label or "").strip()
        if not v and not l:
            continue
        l_l = l.lower()
        v_l = v.lower()
        if not q:
            scored.append(((0, 0, l_l, v_l), (v, l or v)))
            continue

        rank = 999
        pos = 999
        if l_l.startswith(q) or v_l.startswith(q):
            rank = 0
            pos = 0
        else:
            p = l_l.find(q)
            if p >= 0:
                rank = 1
                pos = p
            else:
                p2 = v_l.find(q)
                if p2 >= 0:
                    rank = 1
                    pos = p2
        if rank != 999:
            scored.append(((int(rank), int(pos), l_l, v_l), (v, l or v)))

    scored.sort(key=lambda pair: pair[0])
    return [opt for _score, opt in scored]


# ---------------------------------------------------------------------------
# Command definition type (for DEFAULT_COMMAND_DEFS)
# ---------------------------------------------------------------------------

class _PromptDef(TypedDict, total=False):
    """Definition for a prompt in a command definition."""
    kind: str
    placeholder: str
    default_value_fn: str  # Name of function in registry module
    options_provider: str | None  # Name of function in registry module
    field: str | None


class _CommandDef(TypedDict, total=False):
    """Definition for a command (converted to CommandSpec at runtime)."""
    id: str
    title: str
    section: str
    keywords: tuple[str, ...]
    is_enabled: str  # Name of function in registry module
    prompt: _PromptDef | None
    prompts: tuple[_PromptDef, ...] | None
    action: str  # Name of function in registry module
    hotkey_hint: str | None
    repeat_macro_id: str | None
    macro_id: str | None


# ---------------------------------------------------------------------------
# DEFAULT_COMMAND_DEFS - Static command definitions
# ---------------------------------------------------------------------------

DEFAULT_COMMAND_DEFS: tuple[_CommandDef, ...] = (
    {
        "id": "mode.tile_paint.toggle",
        "title": "Toggle Tile Paint",
        "section": "Modes",
        "keywords": ("tile", "paint", "tiles", "f11"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_toggle_tile_paint",
        "hotkey_hint": "F11",
    },
    {
        "id": "mode.entity_paint.toggle",
        "title": "Toggle Entity Paint",
        "section": "Modes",
        "keywords": ("entity", "paint", "prefab", "home"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_toggle_entity_paint",
        "hotkey_hint": "HOME",
    },
    {
        "id": "mode.palette.toggle",
        "title": "Toggle Palette Mode",
        "section": "Modes",
        "keywords": ("palette", "stamp", "brush", "f3"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_toggle_palette_mode",
        "hotkey_hint": "F3",
    },
    {
        "id": "mode.capture.toggle",
        "title": "Toggle Capture Mode",
        "section": "Modes",
        "keywords": ("capture", "stamp", "brush", "f2"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_toggle_capture",
        "hotkey_hint": "F2",
    },
    {
        "id": "view.ghost_originals.toggle",
        "title": "Toggle Ghost Originals",
        "section": "View",
        "keywords": ("ghost", "originals", "alt", "dup", "duplicate", "dim", "fade"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_toggle_ghost_originals",
        "hotkey_hint": None,
    },
    {
        "id": "scene.reload",
        "title": "Reload Scene",
        "section": "Scene",
        "keywords": ("scene", "reload", "r"),
        "is_enabled": "enabled_has_scene",
        "prompt": None,
        "action": "action_scene_reload",
        "hotkey_hint": "Ctrl+R",
    },
    {
        "id": "scene.goto",
        "title": "Go To Scene",
        "section": "Scene",
        "keywords": ("scene", "go", "goto", "open"),
        "is_enabled": "enabled_scene_index_nonempty",
        "prompt": {"kind": "pick", "placeholder": "Scene path", "default_value_fn": "default_empty", "options_provider": "options_all_scenes"},
        "action": "action_go_to_scene",
        "hotkey_hint": None,
    },
    {
        "id": "scene.recent",
        "title": "Open Recent Scene",
        "section": "Scene",
        "keywords": ("scene", "recent", "open"),
        "is_enabled": "enabled_recent_nonempty",
        "prompt": {"kind": "pick", "placeholder": "Recent scene", "default_value_fn": "default_empty", "options_provider": "options_recent_scenes"},
        "action": "action_recent_scene",
        "hotkey_hint": None,
    },
    {
        "id": "scene.persist_arm.toggle",
        "title": "Toggle Scene Persist Armed",
        "section": "Scene",
        "keywords": ("scene", "persist", "armed", "save", "s"),
        "is_enabled": "enabled_always",
        "prompt": None,
        "action": "action_scene_toggle_persist_armed",
        "hotkey_hint": "Ctrl+Shift+S",
    },
    {
        "id": "scene.persist",
        "title": "Persist Scene",
        "section": "Scene",
        "keywords": ("scene", "persist", "save", "s"),
        "is_enabled": "enabled_scene_persist_armed",
        "prompt": None,
        "action": "action_scene_persist",
        "hotkey_hint": "Ctrl+S",
    },
    {
        "id": "scene.save_as",
        "title": "Save Scene As (auto version)",
        "section": "Scene",
        "keywords": ("scene", "save", "saveas", "copy", "branch", "a"),
        "is_enabled": "enabled_scene_persist_armed",
        "prompt": {"kind": "text", "placeholder": "scene path (blank=auto)", "default_value_fn": "default_save_as"},
        "action": "action_scene_save_as",
        "hotkey_hint": "Ctrl+Shift+A",
    },
    {
        "id": "scene.create",
        "title": "Scene Create",
        "section": "Scene",
        "keywords": ("scene", "create", "new"),
        "is_enabled": "enabled_persist_armed_only",
        "prompt": {"kind": "text", "placeholder": "new scene path", "default_value_fn": "default_scene_create"},
        "action": "action_scene_create",
        "hotkey_hint": None,
    },
    {
        "id": "selection.set_prefab_id",
        "title": "Selection: Set Prefab ID...",
        "section": "Selection",
        "keywords": ("selection", "prefab", "set", "id"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "pick", "placeholder": "prefab id", "default_value_fn": "default_empty", "options_provider": "options_prefab_ids"},
        "action": "action_props_set_prefab_id",
        "hotkey_hint": None,
    },
    {
        "id": "selection.add_behaviour",
        "title": "Selection: Add Behaviour...",
        "section": "Selection",
        "keywords": ("selection", "behaviour", "behavior", "add"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "pick", "placeholder": "behaviour", "default_value_fn": "default_empty", "options_provider": "options_behaviour_names"},
        "action": "action_props_add_behaviour",
        "hotkey_hint": None,
    },
    {
        "id": "selection.remove_behaviour",
        "title": "Selection: Remove Behaviour...",
        "section": "Selection",
        "keywords": ("selection", "behaviour", "behavior", "remove"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "pick", "placeholder": "behaviour", "default_value_fn": "default_empty", "options_provider": "options_behaviours_in_selection"},
        "action": "action_props_remove_behaviour",
        "hotkey_hint": None,
    },
    {
        "id": "selection.set_name",
        "title": "Selection: Set Name (primary)...",
        "section": "Selection",
        "keywords": ("selection", "name", "set"),
        "is_enabled": "enabled_selection_has_primary_non_player",
        "prompt": {"kind": "text", "placeholder": "name", "default_value_fn": "default_empty"},
        "action": "action_props_set_name",
        "hotkey_hint": None,
    },
    {
        "id": "selection.set_tag",
        "title": "Selection: Set Tag...",
        "section": "Selection",
        "keywords": ("selection", "tag", "set"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "tag", "default_value_fn": "default_empty"},
        "action": "action_props_add_tag",
        "hotkey_hint": None,
    },
    {
        "id": "selection.tz_set_zone_id",
        "title": "TriggerZone: Set zone_id...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "triggerzone", "zone_id"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "zone_id", "default_value_fn": "default_empty"},
        "action": "action_config_tz_set_zone_id",
        "hotkey_hint": None,
    },
    {
        "id": "selection.tz_set_radius",
        "title": "TriggerZone: Set radius...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "triggerzone", "radius"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "trigger_radius (float)", "default_value_fn": "default_empty"},
        "action": "action_config_tz_set_radius",
        "hotkey_hint": None,
    },
    {
        "id": "selection.sgs_set_toast",
        "title": "SetGameStateOnEvent: Set toast...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "setgamestateonevent", "toast"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "toast[|seconds]", "default_value_fn": "default_empty"},
        "action": "action_config_sgs_set_toast",
        "hotkey_hint": None,
    },
    {
        "id": "selection.sgs_add_require_flag",
        "title": "SetGameStateOnEvent: Add require flag...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "setgamestateonevent", "require"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "flag key", "default_value_fn": "default_empty"},
        "action": "action_config_sgs_add_require_flag",
        "hotkey_hint": None,
    },
    {
        "id": "selection.sgs_add_forbid_flag",
        "title": "SetGameStateOnEvent: Add forbid flag...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "setgamestateonevent", "forbid"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "flag key", "default_value_fn": "default_empty"},
        "action": "action_config_sgs_add_forbid_flag",
        "hotkey_hint": None,
    },
    {
        "id": "selection.sgs_set_flag_true",
        "title": "SetGameStateOnEvent: Set flag true...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "setgamestateonevent", "set_flags"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "flag key", "default_value_fn": "default_empty"},
        "action": "action_config_sgs_set_flag_true",
        "hotkey_hint": None,
    },
    {
        "id": "selection.st_set_target_scene",
        "title": "SceneTransition: Set target scene...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "scenetransition", "target_scene"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "pick", "placeholder": "target scene", "default_value_fn": "default_empty", "options_provider": "options_scene_paths"},
        "action": "action_config_st_set_target_scene",
        "hotkey_hint": None,
    },
    {
        "id": "selection.st_set_spawn_id",
        "title": "SceneTransition: Set spawn id...",
        "section": "Selection / Config",
        "keywords": ("selection", "config", "scenetransition", "spawn_id"),
        "is_enabled": "enabled_selection_has_non_player",
        "prompt": {"kind": "text", "placeholder": "spawn id", "default_value_fn": "default_empty"},
        "action": "action_config_st_set_spawn_id",
        "hotkey_hint": None,
    },
    {
        "id": "macro.objective_zone",
        "title": "Macro: Objective Zone...",
        "section": "Authoring / Macros",
        "keywords": ("macro", "objective", "zone", "triggerzone", "setgamestateonevent"),
        "is_enabled": "enabled_has_scene_and_authored_payload",
        "prompt": None,
        "prompts": (
            {"kind": "pick", "placeholder": "anchor", "default_value_fn": "default_cursor", "options_provider": "options_macro_anchor", "field": "anchor"},
            {"kind": "text", "placeholder": "zone_id", "default_value_fn": "default_empty", "field": "zone_id"},
            {"kind": "text", "placeholder": "set_flag", "default_value_fn": "default_empty", "field": "set_flag"},
            {"kind": "text", "placeholder": "radius (float)", "default_value_fn": "default_radius_72", "field": "radius"},
            {"kind": "text", "placeholder": "toast (optional)", "default_value_fn": "default_empty", "field": "toast"},
        ),
        "action": "action_macro_objective_zone",
        "hotkey_hint": None,
        "repeat_macro_id": "macro.objective_zone",
        "macro_id": "macro.objective_zone",
    },
    {
        "id": "macro.door_transition",
        "title": "Macro: Door Transition...",
        "section": "Authoring / Macros",
        "keywords": ("macro", "door", "transition", "scenetransition"),
        "is_enabled": "enabled_has_scene_and_authored_payload",
        "prompt": None,
        "prompts": (
            {"kind": "pick", "placeholder": "anchor", "default_value_fn": "default_cursor", "options_provider": "options_macro_anchor", "field": "anchor"},
            {"kind": "pick", "placeholder": "target_scene", "default_value_fn": "default_empty", "options_provider": "options_all_scenes", "field": "target_scene"},
            {"kind": "text", "placeholder": "spawn_id", "default_value_fn": "default_empty", "field": "spawn_id"},
        ),
        "action": "action_macro_door_transition",
        "hotkey_hint": None,
        "repeat_macro_id": "macro.door_transition",
        "macro_id": "macro.door_transition",
    },
    {
        "id": "macro.dialogue_choice_flag",
        "title": "Macro: Dialogue Choice Flag...",
        "section": "Authoring / Macros",
        "keywords": ("macro", "dialogue", "choice", "flag", "setgamestateonevent"),
        "is_enabled": "enabled_has_scene_and_authored_payload",
        "prompt": None,
        "prompts": (
            {"kind": "pick", "placeholder": "speaker_id", "default_value_fn": "default_empty", "options_provider": "options_dialogue_speakers", "field": "speaker_id"},
            {"kind": "text", "placeholder": "choice_id", "default_value_fn": "default_empty", "field": "choice_id"},
            {"kind": "text", "placeholder": "choice_text", "default_value_fn": "default_empty", "field": "choice_text"},
            {"kind": "text", "placeholder": "set_flag", "default_value_fn": "default_empty", "field": "set_flag"},
            {"kind": "text", "placeholder": "toast (optional)", "default_value_fn": "default_empty", "field": "toast"},
        ),
        "action": "action_macro_dialogue_choice_flag",
        "hotkey_hint": None,
        "repeat_macro_id": "macro.dialogue_choice_flag",
        "macro_id": "macro.dialogue_choice_flag",
    },
)


# ---------------------------------------------------------------------------
# build_default_commands - Converts definitions to CommandSpec instances
# ---------------------------------------------------------------------------

def build_default_commands(window: Any) -> list[CommandSpec]:
    """Build the list of default command palette commands.

    This function converts the static command definitions in DEFAULT_COMMAND_DEFS
    to runtime CommandSpec objects, and appends any dynamic macro asset commands.

    Args:
        window: The game window (used for dynamic command enablement).

    Returns:
        List of CommandSpec objects in deterministic order.
    """
    # Import registry functions
    from engine import command_palette_registry as reg  # noqa: PLC0415

    def _resolve_fn(name: str) -> Callable[..., Any]:
        """Resolve a function name to its implementation in the registry."""
        fn: Callable[..., Any] | None = getattr(reg, name, None)
        if fn is None:
            raise ValueError(f"Unknown registry function: {name}")
        return fn

    def _build_prompt(pdef: _PromptDef | dict[str, Any]) -> PromptSpec:
        """Convert a prompt definition to a PromptSpec."""
        opts_name = pdef.get("options_provider")
        return PromptSpec(
            kind=str(pdef.get("kind", "text")),
            placeholder=str(pdef.get("placeholder", "")),
            default_value_fn=_resolve_fn(str(pdef.get("default_value_fn", "default_empty"))),
            options_provider=_resolve_fn(opts_name) if opts_name else None,
            field=pdef.get("field"),
        )

    def _build_command(cdef: _CommandDef | dict[str, Any]) -> CommandSpec:
        """Convert a command definition to a CommandSpec."""
        prompt_def = cdef.get("prompt")
        prompts_defs = cdef.get("prompts")

        prompt = _build_prompt(prompt_def) if prompt_def else None
        prompts = tuple(_build_prompt(p) for p in prompts_defs) if prompts_defs else None

        return CommandSpec(
            id=str(cdef.get("id", "")),
            title=str(cdef.get("title", "")),
            section=str(cdef.get("section", "")),
            keywords=tuple(cdef.get("keywords", ())),
            is_enabled=_resolve_fn(str(cdef.get("is_enabled", "enabled_always"))),
            prompt=prompt,
            action=_resolve_fn(str(cdef.get("action", ""))),
            prompts=prompts,
            hotkey_hint=cdef.get("hotkey_hint"),
            repeat_macro_id=cdef.get("repeat_macro_id"),
            macro_id=cdef.get("macro_id"),
        )

    # Build commands from static definitions
    cmds = [_build_command(cdef) for cdef in DEFAULT_COMMAND_DEFS]

    # Append dynamic macro asset commands
    cmds.extend(_build_macro_asset_commands(reg))

    return cmds


def _build_macro_asset_commands(reg: Any) -> list[CommandSpec]:
    """Build dynamic macro asset commands.

    These are loaded from assets/macros/ at runtime and depend on
    the macro asset files present in the workspace.

    Args:
        reg: The command_palette_registry module.

    Returns:
        List of CommandSpec objects for macro assets, sorted deterministically.
    """
    try:
        from engine.tooling_runtime.macro_assets import (  # noqa: PLC0415
            iter_macro_paths,
            load_macro_asset,
            parse_macro_asset,
            validate_macro_asset,
        )
    except Exception:  # noqa: BLE001
        return []

    out: list[tuple[tuple[str, str, str], CommandSpec]] = []

    for rel_path in iter_macro_paths():
        try:
            payload = load_macro_asset(rel_path)
        except Exception:  # noqa: BLE001
            continue
        if validate_macro_asset(payload, rel_path=rel_path):
            continue
        try:
            asset = parse_macro_asset(payload, rel_path=rel_path)
        except Exception:  # noqa: BLE001
            continue
        if not asset.id or not asset.macro_id:
            continue
        runner = reg.MACRO_RUNNERS.get(asset.macro_id)
        if runner is None:
            continue

        # Build prompt specs for this macro asset
        prompts = _macro_asset_prompt_specs(asset=asset, reg=reg)

        # Create action closure
        def _action(w: Any, arg: str | None, *, _asset=asset, _runner=runner) -> None:
            try:
                overrides = json.loads(str(arg or "") or "{}")
            except Exception:  # noqa: BLE001
                overrides = {}
            if not isinstance(overrides, dict):
                overrides = {}
            merged: dict[str, Any] = dict(_asset.defaults or {})
            merged.update(overrides)
            _runner(w, json.dumps(merged, sort_keys=True))

        cmd = CommandSpec(
            id=f"macro_asset.{asset.pack_id}.{asset.id}",
            title=f"Macro: {asset.pack_id}/{asset.id}",
            section="Authoring / Macro Assets",
            keywords=("macro", asset.pack_id, asset.id, asset.macro_id),
            is_enabled=reg.enabled_has_scene_and_authored_payload,
            prompt=None,
            prompts=prompts,
            action=_action,
            hotkey_hint=None,
            repeat_macro_id=asset.macro_id,
            macro_id=asset.macro_id,
            macro_asset_path=asset.path,
            macro_defaults=dict(asset.defaults or {}),
        )
        out.append(((asset.pack_id, asset.id, asset.path), cmd))

    out.sort(key=lambda pair: pair[0])
    return [cmd for _k, cmd in out]


def _macro_asset_prompt_specs(*, asset: Any, reg: Any) -> tuple[PromptSpec, ...]:
    """Build prompt specs for a macro asset.

    Args:
        asset: The parsed macro asset.
        reg: The command_palette_registry module.

    Returns:
        Tuple of PromptSpec objects for the macro's prompts.
    """
    defaults = getattr(asset, "defaults", None)
    defaults = defaults if isinstance(defaults, dict) else {}
    steps = getattr(asset, "steps", None)
    steps = steps if isinstance(steps, list) else []
    macro_id = str(getattr(asset, "macro_id", "") or "").strip()

    # Default prompt sequences (match built-in macros).
    default_steps: list[dict[str, Any]] = []
    if macro_id == "macro.objective_zone":
        default_steps = [
            {"key": "anchor", "kind": "pick", "options": ["primary", "cursor", "player"]},
            {"key": "zone_id", "kind": "text"},
            {"key": "set_flag", "kind": "text"},
            {"key": "radius", "kind": "text"},
            {"key": "toast", "kind": "text"},
        ]
    elif macro_id == "macro.door_transition":
        default_steps = [
            {"key": "anchor", "kind": "pick", "options": ["primary", "cursor", "player"]},
            {"key": "target_scene", "kind": "pick", "source": "known_scenes"},
            {"key": "spawn_id", "kind": "text"},
        ]
    elif macro_id == "macro.dialogue_choice_flag":
        default_steps = [
            {"key": "speaker_id", "kind": "pick", "source": "dialogue_speakers"},
            {"key": "choice_id", "kind": "text"},
            {"key": "choice_text", "kind": "text"},
            {"key": "set_flag", "kind": "text"},
            {"key": "toast", "kind": "text"},
        ]

    wanted_steps = steps if steps else default_steps

    prompt_specs: list[PromptSpec] = []
    for step in wanted_steps:
        if not isinstance(step, dict):
            continue
        key = str(step.get("key") or "").strip()
        kind = str(step.get("kind") or "").strip().lower()
        if not key or kind not in {"text", "pick"}:
            continue

        placeholder = key
        if key == "radius":
            placeholder = "radius (float)"
        if key == "target_scene":
            placeholder = "target_scene"
        if key == "spawn_id":
            placeholder = "spawn_id"

        _defaults_copy: dict[str, Any] = dict(defaults) if defaults else {}

        def _default_for(_w: Any, *, _k: str = key, _defaults: dict[str, Any] = _defaults_copy) -> str:
            v = _defaults.get(_k, "")
            if isinstance(v, (int, float)):
                return str(v)
            return str(v or "")

        options_provider: Callable[[Any], list[tuple[str, str]]] | None = None
        if kind == "pick":
            src = str(step.get("source") or "").strip()
            if src == "known_scenes":
                options_provider = reg.options_all_scenes
            elif src == "dialogue_speakers":
                options_provider = reg.options_dialogue_speakers
            else:
                opts = step.get("options")
                if isinstance(opts, list):
                    raw_values = [str(v).strip() for v in opts if isinstance(v, str) and str(v).strip()]

                    def _provider(w: Any, *, _raw: list[str] = raw_values) -> list[tuple[str, str]]:
                        selected_ids, _p = reg._get_selection_ids_and_primary(w)
                        out = []
                        for v in _raw:
                            if v == "primary" and not selected_ids:
                                continue
                            out.append((v, v))
                        return out

                    options_provider = _provider

        prompt_specs.append(
            PromptSpec(
                kind=kind,
                placeholder=placeholder,
                default_value_fn=_default_for,
                options_provider=options_provider,
                field=key,
            )
        )

    return tuple(prompt_specs)
