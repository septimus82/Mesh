from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .runtime_settings import ensure_runtime_settings


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    title: str
    keywords: tuple[str, ...]
    run: Callable[[Any], None]


def _toggle_lights_tool(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None:
        return
    toggler = getattr(editor, "toggle_lights_tool", None)
    if callable(toggler):
        toggler()


def _toggle_occluder_tool(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None:
        return
    toggler = getattr(editor, "toggle_occluder_tool", None)
    if callable(toggler):
        toggler()


def _toggle_entity_panels(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_entity_panels", None)
    if callable(toggler):
        toggler()


def _save_scene(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return
    saver = getattr(editor, "save_current_scene", None)
    if callable(saver):
        saver()


def _play_from_here(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return
    starter = getattr(editor, "play_from_here", None)
    if callable(starter):
        starter()


def _stop_playing(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None:
        return
    stopper = getattr(editor, "stop_playing", None)
    if callable(stopper):
        stopper()


def _open_scene_browser(window: Any) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_scene_browser", None)
    if callable(toggler):
        toggler()


def _apply_lighting_preset(window: Any, index: int) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None:
        return
    apply_fn = getattr(editor, "apply_lighting_preset_hotkey", None)
    if callable(apply_fn):
        apply_fn(int(index))


def _toggle_fog(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.fog_enabled = not bool(settings.fog_enabled)
    settings.apply(window)


def _toggle_soft_shadows(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.soft_shadows_enabled = not bool(settings.soft_shadows_enabled)
    settings.apply(window)


def get_all_commands(_window: Any | None = None) -> list[Command]:
    return [
        Command(
            id="editor.light_tool.toggle",
            title="Toggle Light Tool",
            keywords=("light", "lighting", "tool"),
            run=_toggle_lights_tool,
        ),
        Command(
            id="editor.occluder_tool.toggle",
            title="Toggle Occluder Tool",
            keywords=("occluder", "shadow", "polygon"),
            run=_toggle_occluder_tool,
        ),
        Command(
            id="editor.entity_panels.toggle",
            title="Toggle Entity Panels",
            keywords=("entity", "outliner", "inspector", "panels"),
            run=_toggle_entity_panels,
        ),
        Command(
            id="editor.scene_browser.open",
            title="Open Scene Browser",
            keywords=("scene", "browser", "open"),
            run=_open_scene_browser,
        ),
        Command(
            id="editor.scene.save",
            title="Save Scene",
            keywords=("save", "scene"),
            run=_save_scene,
        ),
        Command(
            id="editor.play.start",
            title="Play From Here",
            keywords=("play", "start", "test"),
            run=_play_from_here,
        ),
        Command(
            id="editor.play.stop",
            title="Stop Playing",
            keywords=("stop", "play", "return"),
            run=_stop_playing,
        ),
        Command(
            id="editor.lighting_preset.1",
            title="Apply Lighting Preset 1",
            keywords=("lighting", "preset", "1"),
            run=lambda w: _apply_lighting_preset(w, 0),
        ),
        Command(
            id="editor.lighting_preset.2",
            title="Apply Lighting Preset 2",
            keywords=("lighting", "preset", "2"),
            run=lambda w: _apply_lighting_preset(w, 1),
        ),
        Command(
            id="editor.lighting_preset.3",
            title="Apply Lighting Preset 3",
            keywords=("lighting", "preset", "3"),
            run=lambda w: _apply_lighting_preset(w, 2),
        ),
        Command(
            id="editor.lighting_preset.4",
            title="Apply Lighting Preset 4",
            keywords=("lighting", "preset", "4"),
            run=lambda w: _apply_lighting_preset(w, 3),
        ),
        Command(
            id="runtime.fog.toggle",
            title="Toggle Fog",
            keywords=("fog", "atmosphere"),
            run=_toggle_fog,
        ),
        Command(
            id="runtime.soft_shadows.toggle",
            title="Toggle Soft Shadows",
            keywords=("soft", "shadows", "lighting"),
            run=_toggle_soft_shadows,
        ),
    ]


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _score_command(command: Command, query: str) -> tuple[int, int, int, str, str] | None:
    q = _normalize_query(query)
    title = str(command.title or "").strip()
    if not title:
        return None
    title_l = title.lower()

    if not q:
        return (0, 0, len(title_l), title_l, command.id)

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
            for kw in command.keywords:
                kw_l = str(kw or "").strip().lower()
                if not kw_l:
                    continue
                kp = kw_l.find(q)
                if kp >= 0:
                    kw_pos = kp if kw_pos is None else min(kw_pos, kp)
            if kw_pos is not None:
                rank = 2
                pos = int(kw_pos)

    if rank == 999:
        return None
    return (int(rank), int(pos), len(title_l), title_l, command.id)


def filter_commands(commands: Iterable[Command], query: str) -> list[Command]:
    scored: list[tuple[tuple[int, int, int, str, str], Command]] = []
    for cmd in commands:
        score = _score_command(cmd, query)
        if score is None:
            continue
        scored.append((score, cmd))
    scored.sort(key=lambda pair: pair[0])
    return [cmd for _score, cmd in scored]


def run_command(command_id: str, window: Any) -> bool:
    wanted = str(command_id or "").strip()
    if not wanted:
        return False
    for cmd in get_all_commands(window):
        if cmd.id == wanted:
            cmd.run(window)
            return True
    return False
