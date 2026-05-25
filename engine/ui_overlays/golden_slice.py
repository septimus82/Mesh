from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence
import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
    _safe_truncate,
    load_config_json,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def build_golden_slice_variant_picker_presets(config: dict[str, Any]) -> list[str]:
    """Return only Golden Slice picker presets (excluding other categories like Act 1)."""
    source = build_golden_slice_variant_picker_source(config)
    categories = source.get("categories")
    if not isinstance(categories, list):
        names = source.get("names")
        return list(names) if isinstance(names, list) else []

    allow_ids = {"ridge_outpost", "hollowmere_outskirts"}
    flattened: list[str] = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        if str(cat.get("id") or "") not in allow_ids:
            continue
        names = cat.get("names")
        if isinstance(names, list):
            flattened.extend([str(name) for name in names])
    return flattened


def _extract_run_preset_targets(preset: Any) -> list[str]:
    if not isinstance(preset, dict):
        return []
    steps = preset.get("steps")
    if not isinstance(steps, list):
        return []
    targets: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("cmd") != "run-preset":
            continue
        args = step.get("args") or []
        if not isinstance(args, list) or len(args) != 1:
            continue
        name = args[0]
        if not isinstance(name, str):
            continue
        cleaned = name.strip()
        if cleaned:
            targets.append(cleaned)
    return targets


def _run_preset_cycle_reachable(presets: dict[str, Any], start: str) -> bool:
    edges: dict[str, list[str]] = {}
    for preset_name in sorted(presets.keys()):
        edges[preset_name] = sorted(_extract_run_preset_targets(presets.get(preset_name)))

    visited: set[str] = set()
    stack: set[str] = set()

    def _walk(name: str) -> bool:
        if name in stack:
            return True
        if name in visited:
            return False
        visited.add(name)
        stack.add(name)
        for target in edges.get(name, []):
            if _walk(target):
                return True
        stack.remove(name)
        return False

    return _walk(start)


def build_golden_slice_variant_picker_source(config: dict[str, Any]) -> dict[str, Any]:
    """
    Return a stable, JSON-friendly description of the picker source.

    Shape:
      {
        "ok": bool,
        "message": str | None,
        "categories": [
          {"id": str, "label": str, "ok": bool, "message": str | None, "names": list[str], "missing_presets": list[str]},
          ...
        ],
        "names": list[str],
        "missing_presets": list[str],
      }
    """
    presets = config.get("presets") or {}
    if not isinstance(presets, dict):
        return {
            "ok": False,
            "message": "No variants available (invalid config).",
            "categories": [],
            "names": [],
            "missing_presets": [],
        }

    def _build_category(*, category_id: str, label: str, index_preset: str) -> dict[str, Any]:
        root = presets.get(index_preset)
        if not isinstance(root, dict):
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": f"No variants available (missing {index_preset}).",
                "names": [],
                "missing_presets": [],
            }

        if _run_preset_cycle_reachable(presets, index_preset):
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": f"Invalid {index_preset} (run-preset recursion detected).",
                "names": [],
                "missing_presets": [],
            }

        targets = _extract_run_preset_targets(root)
        if not targets:
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": f"No variants available (no run-preset steps in {index_preset}).",
                "names": [],
                "missing_presets": [],
            }

        missing: set[str] = set()
        seen: set[str] = set()
        flattened: list[str] = []

        def _walk(name: str) -> None:
            preset = presets.get(name)
            next_targets = _extract_run_preset_targets(preset)
            if not next_targets:
                if name not in seen:
                    seen.add(name)
                    flattened.append(name)
                if name not in presets:
                    missing.add(name)
                return
            for next_name in next_targets:
                _walk(next_name)

        for target in targets:
            _walk(target)

        if not flattened:
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": f"No variants available ({index_preset} produced no presets).",
                "names": [],
                "missing_presets": [],
            }
        return {
            "id": category_id,
            "label": label,
            "ok": True,
            "message": None,
            "names": flattened,
            "missing_presets": sorted(missing),
        }

    def _build_static_category(*, category_id: str, label: str, names: Sequence[str]) -> dict[str, Any]:
        wanted = [str(name).strip() for name in names if str(name).strip()]
        if not wanted:
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": "No variants available.",
                "names": [],
                "missing_presets": [],
            }

        present = [name for name in wanted if name in presets]
        if not present:
            return {
                "id": category_id,
                "label": label,
                "ok": False,
                "message": f"No variants available (missing {label} presets).",
                "names": [],
                "missing_presets": sorted(set(wanted)),
            }

        for name in present:
            if _run_preset_cycle_reachable(presets, name):
                return {
                    "id": category_id,
                    "label": label,
                    "ok": False,
                    "message": f"Invalid {label} presets (run-preset recursion detected).",
                    "names": [],
                    "missing_presets": [],
                }

        missing = sorted({name for name in wanted if name not in presets})
        return {
            "id": category_id,
            "label": label,
            "ok": True,
            "message": None,
            "names": list(wanted),
            "missing_presets": missing,
        }

    categories = [
        _build_category(
            category_id="ridge_outpost",
            label="Ridge Outpost",
            index_preset="golden_slice_index",
        ),
        _build_category(
            category_id="hollowmere_outskirts",
            label="Hollowmere Outskirts",
            index_preset="golden_slice2_index",
        ),
        _build_static_category(
            category_id="act1",
            label="Act 1",
            names=(
                "act1_index",
                "act1_prologue",
                "act1_chapter1",
                "act1_demo",
            ),
        ),
    ]

    flattened: list[str] = []
    missing_all: set[str] = set()
    any_ok = False
    recursion_messages: list[str] = []
    for cat in categories:
        if cat.get("ok"):
            any_ok = True
            flattened.extend(list(cat.get("names") or []))
            for missing in cat.get("missing_presets") or []:
                missing_all.add(str(missing))
        msg = cat.get("message")
        if isinstance(msg, str) and "recursion" in msg.lower():
            recursion_messages.append(msg)

    message: str | None = None
    if not any_ok:
        message = recursion_messages[0] if recursion_messages else "No variants available."

    return {
        "ok": any_ok,
        "message": message,
        "categories": categories,
        "names": flattened,
        "missing_presets": sorted(missing_all),
    }


def build_golden_slice_variant_picker_presets_from_file(config_path: str = "config.json") -> list[str]:
    return build_golden_slice_variant_picker_presets(load_config_json(config_path))


GOLDEN_SLICE_DEMO_HUD_MAX_CHARS = 140


def is_golden_slice_demo_context(
    *,
    preset_id: str | None,
    world_id: str | None,
    world_file: str | None,
) -> bool:
    preset = str(preset_id or "").strip()
    world = str(world_id or "").strip()
    world_path = str(world_file or "").strip()
    if preset.startswith("golden_slice"):
        return True
    if world.startswith("golden_slice"):
        return True
    return "golden_slice" in world_path.replace("\\", "/").lower()


def is_act1_demo_context(
    *,
    preset_id: str | None,
    world_id: str | None,
    world_file: str | None,
) -> bool:
    preset = str(preset_id or "").strip()
    world = str(world_id or "").strip()
    world_path = str(world_file or "").strip()
    if preset.startswith("act1_"):
        return True
    if world.startswith("act1_"):
        return True
    return "act1_" in world_path.replace("\\", "/").lower()


def _act1_world_label(*, preset_id: str | None, world_id: str | None, world_file: str | None) -> str:
    wid = str(world_id or "").strip()
    if wid:
        return wid
    wf = str(world_file or "").strip().replace("\\", "/")
    if wf:
        stem = wf.rsplit("/", 1)[-1]
        if stem.lower().endswith(".json"):
            stem = stem[:-5]
        if stem:
            return stem
    pid = str(preset_id or "").strip()
    return pid or "unknown"


def build_act1_demo_hud_status_line(
    *,
    preset_id: str | None,
    world_id: str | None,
    world_file: str | None,
    active_quest: str | None,
    gold_delta: int,
    new_flags: int,
    show_picker_hint: bool,
) -> str:
    world_label = _safe_truncate(
        _act1_world_label(preset_id=preset_id, world_id=world_id, world_file=world_file),
        36,
    )
    quest = _safe_truncate(str(active_quest or "-").strip() or "-", 42)
    signed_gold = f"{int(gold_delta):+d}"
    flags = int(new_flags)
    suffix = " | V picker" if show_picker_hint else ""
    line = f"Act 1: {world_label} | quest:{quest} | +gold:{signed_gold} +flags:{flags}{suffix}"
    return _safe_truncate(line, GOLDEN_SLICE_DEMO_HUD_MAX_CHARS)


def _golden_slice_variant_label(preset_id: str | None, world_id: str | None) -> str | None:
    raw = str(preset_id or "").strip() or str(world_id or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    prefix = "golden_slice_variant_"
    if lowered.startswith(prefix) and len(lowered) == len(prefix) + 1:
        return lowered[-1].upper()
    prefix2 = "golden_slice2_variant_"
    if lowered.startswith(prefix2) and len(lowered) == len(prefix2) + 1:
        return f"{lowered[-1].upper()}2"
    return raw



def build_golden_slice_demo_hud_status_line(
    *,
    preset_id: str | None,
    world_id: str | None,
    active_quest: str | None,
    gold_delta: int,
    new_flags: int,
    hint_keys: list[str],
    max_chars: int = GOLDEN_SLICE_DEMO_HUD_MAX_CHARS,
) -> str:
    variant = _golden_slice_variant_label(preset_id, world_id) or "?"
    quest = str(active_quest or "").strip() or "-"
    keys = ",".join([k for k in hint_keys if str(k).strip()])
    keys = keys or "-"
    line = f"GS {variant} | Quest: {quest} | Δg {int(gold_delta):+d} | +flags {int(new_flags)} | Keys: {keys}"
    return _safe_truncate(line, max_chars)




class GoldenSliceVariantPickerOverlay(UIElement):
    """Overlay that switches between Golden Slice variant presets (dev convenience)."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.selected_index: int = 0
        self._entries: list[dict[str, Any]] = []
        self._status_message: str | None = None
        self._categories: list[dict[str, Any]] = []
        self._category_index: int = 0

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
            self._category_index = 0
            self._refresh_entries()
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)
        if self.visible:
            self.selected_index = 0
            self._category_index = 0
            self._refresh_entries()

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def _refresh_entries(self) -> None:
        config_path = getattr(self.window, "config_path", "config.json") or "config.json"
        config = load_config_json(str(config_path))
        source = build_golden_slice_variant_picker_source(config)
        self._categories = list(source.get("categories") or []) if isinstance(source.get("categories"), list) else []
        names: list[Any] = []
        missing: set[str] = set()
        if self._categories:
            self._category_index = max(0, min(self._category_index, len(self._categories) - 1))
            active = self._categories[self._category_index]
            self._status_message = active.get("message") if isinstance(active.get("message"), str) else None
            if not active.get("ok"):
                self._entries = []
                return
            raw_names = active.get("names")
            names = raw_names if isinstance(raw_names, list) else []
            missing = (
                set(active.get("missing_presets") or [])
                if isinstance(active.get("missing_presets"), list)
                else set()
            )
        else:
            self._status_message = source.get("message") if isinstance(source.get("message"), str) else None
            if not source.get("ok"):
                self._entries = []
                return
            raw_names = source.get("names")
            names = raw_names if isinstance(raw_names, list) else []
            missing = (
                set(source.get("missing_presets") or [])
                if isinstance(source.get("missing_presets"), list)
                else set()
            )

        if not source.get("ok") and not names:
            self._entries = []
            return

        presets = config.get("presets") if isinstance(config, dict) else None
        presets = presets if isinstance(presets, dict) else {}

        entries: list[dict[str, Any]] = []
        for name in names:
            preset = presets.get(name)
            desc = ""
            notes = ""
            world_path = None
            is_missing = name in missing or preset is None
            if isinstance(preset, dict):
                desc = str(preset.get("description") or "")
                notes = str(preset.get("notes") or "")
                world_path = self._resolve_world_path_from_preset(preset)
            entries.append(
                {
                    "name": name,
                    "description": desc.strip(),
                    "notes": notes.strip(),
                    "world_path": world_path,
                    "missing": is_missing,
                }
            )

        self._entries = entries

    def _resolve_world_path_from_preset(self, preset: dict[str, Any]) -> str | None:
        steps = preset.get("steps")
        if not isinstance(steps, list):
            return None
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("cmd") != "pipeline":
                continue
            args = step.get("args") or []
            if not isinstance(args, list):
                continue
            for index, value in enumerate(args):
                if not isinstance(value, str):
                    continue
                if value == "--world" and index + 1 < len(args) and isinstance(args[index + 1], str):
                    candidate = str(args[index + 1]).strip()
                    return candidate or None
                if value.startswith("--world="):
                    candidate = value.split("=", 1)[1].strip()
                    return candidate or None
        return None

    def _resolve_dungeon_scene_from_world(self, world_path: str) -> str | None:
        from ..paths import resolve_path

        path = resolve_path(world_path)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _log_swallow("GLDN-001", "world JSON parse fallback", once=True)
            return None
        if not isinstance(raw, dict):
            return None
        scenes = raw.get("scenes") or {}
        if not isinstance(scenes, dict):
            return None
        dungeon = scenes.get("Ridge Outpost_dungeon")
        if isinstance(dungeon, dict) and isinstance(dungeon.get("path"), str) and dungeon["path"].strip():
            return str(dungeon["path"]).strip()
        start_key = raw.get("start_scene")
        if isinstance(start_key, str):
            start_def = scenes.get(start_key)
            if isinstance(start_def, dict) and isinstance(start_def.get("path"), str) and start_def["path"].strip():
                return str(start_def["path"]).strip()
        return None

    def _apply_preset_metadata(self, entry: dict[str, Any]) -> None:
        name = str(entry.get("name") or "").strip()
        if not name:
            return
        os.environ["MESH_ACTIVE_PRESET"] = name
        desc = str(entry.get("description") or "").strip()
        notes = str(entry.get("notes") or "").strip()
        if desc:
            os.environ["MESH_PRESET_DESCRIPTION"] = desc
        else:
            os.environ.pop("MESH_PRESET_DESCRIPTION", None)
        if notes:
            os.environ["MESH_PRESET_NOTES"] = notes
        else:
            os.environ.pop("MESH_PRESET_NOTES", None)

    def _apply_world_controller(self, world_path: str) -> None:
        from ..migrations import migrate_payload
        from ..paths import resolve_path
        from ..world_controller import WorldController

        cfg = getattr(self.window, "engine_config", None)
        if cfg is not None:
            try:
                cfg.world_file = str(world_path)
            except Exception:
                _log_swallow("GOLD-001", "engine/ui_overlays/golden_slice.py pass-only blanket swallow")
                pass
        path = resolve_path(world_path)
        if not path.exists():
            self.window.world_controller = None
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw = migrate_payload("world", raw)
                self.window.world_controller = WorldController(raw)
        except Exception:
            _log_swallow("GLDN-002", "world controller load fallback", once=True)
            self.window.world_controller = None

    def _activate_selected(self) -> bool:
        if not self._entries:
            return False
        if self.selected_index < 0 or self.selected_index >= len(self._entries):
            return False

        entry = self._entries[self.selected_index]
        if entry.get("missing"):
            hud = getattr(self.window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(enqueue):
                enqueue("Variant preset missing from config", seconds=2.5)
            return False
        world_path = entry.get("world_path")
        self._apply_preset_metadata(entry)

        target_scene = None
        if isinstance(world_path, str) and world_path.strip():
            world_path = world_path.strip()
            self._apply_world_controller(world_path)
            target_scene = self._resolve_dungeon_scene_from_world(world_path)

        if not isinstance(target_scene, str) or not target_scene.strip():
            hud = getattr(self.window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(enqueue):
                enqueue("Variant preset has no world configured", seconds=2.5)
            return False

        scene_path = target_scene.replace("\\", "/")
        try:
            requester = getattr(self.window, "queue_scene_change", None)
            if callable(requester):
                requester(scene_path, spawn_id="default")
            else:
                self.window.request_scene_change(scene_path)
        except Exception:
            _log_swallow("GLDN-003", "variant scene change fallback", once=True)
            return False

        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue(f"Loaded {entry.get('name')}", seconds=2.5)
        self.set_visible(False)
        return True

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            self.set_visible(False)
            return True
        if key == optional_arcade.arcade.key.LEFT:
            if self._categories:
                self._category_index = (self._category_index - 1) % len(self._categories)
                self.selected_index = 0
                self._refresh_entries()
            return True
        if key == optional_arcade.arcade.key.RIGHT:
            if self._categories:
                self._category_index = (self._category_index + 1) % len(self._categories)
                self.selected_index = 0
                self._refresh_entries()
            return True
        if not self._entries:
            return True
        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self.selected_index = (self.selected_index - 1) % len(self._entries)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_hover.wav")
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self.selected_index = (self.selected_index + 1) % len(self._entries)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_hover.wav")
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            if self._activate_selected() and hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_click.wav")
            return True
        return True

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(760.0, max(420.0, self.window.width - 140.0))
        height = min(420.0, max(220.0, self.window.height - 160.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 210),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        text_left = left + 40.0
        title_y = top - 20.0
        optional_arcade.arcade.draw_text(
            "Golden Slice Variant Picker",
            text_left,
            title_y,
            optional_arcade.arcade.color.WHITE,
            20,
            anchor_y="top",
        )

        if self._categories:
            labels: list[str] = []
            for i, cat in enumerate(self._categories):
                label = str(cat.get("label") or "")
                if i == self._category_index:
                    label = f"[{label}]"
                labels.append(label)
            optional_arcade.arcade.draw_text(
                " / ".join(labels),
                text_left,
                title_y - 28.0,
                optional_arcade.arcade.color.LIGHT_GRAY,
                12,
                anchor_y="top",
            )

        if not self._entries:
            message = self._status_message or "No variants available."
            optional_arcade.arcade.draw_text(
                message,
                text_left,
                title_y - 60.0,
                optional_arcade.arcade.color.LIGHT_GRAY,
                13,
                width=width - 80.0,
                multiline=True,
                anchor_y="top",
            )
        else:
            y = title_y - 56.0
            line_height = 18.0
            max_lines = int((height - 120.0) / line_height)
            start = max(0, min(self.selected_index - max_lines // 2, max(0, len(self._entries) - max_lines)))
            end = min(len(self._entries), start + max_lines)
            for index in range(start, end):
                entry = self._entries[index]
                prefix = "▶ " if index == self.selected_index else "  "
                label = str(entry.get("name") or "")
                if entry.get("missing"):
                    label = f"{label} (missing)"
                notes = str(entry.get("notes") or entry.get("description") or "").strip()
                if notes:
                    notes = f" - {notes}"
                if len(notes) > 44:
                    notes = notes[:41] + "..."
                color = optional_arcade.arcade.color.WHITE if index == self.selected_index else optional_arcade.arcade.color.LIGHT_GRAY
                optional_arcade.arcade.draw_text(
                    f"{prefix}{label}{notes}",
                    text_left,
                    y,
                    color,
                    13,
                    anchor_y="top",
                )
                y -= line_height

        optional_arcade.arcade.draw_text(
            "Up/Down to select • Enter to load • Esc to close",
            text_left,
            bottom + 24.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
        )
        if self._categories:
            optional_arcade.arcade.draw_text(
                "Left/Right to switch location",
                text_left,
                bottom + 8.0,
                optional_arcade.arcade.color.LIGHT_GRAY,
                10,
            )




class GoldenSliceDemoHUDStripOverlay(UIElement):
    """One-line Golden Slice status strip for demos; only renders in Golden Slice contexts."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._last_scene_id: str | None = None
        self._baseline_gold: int = 0
        self._baseline_true_flags: set[str] = set()

    @property
    def blocks_input(self) -> bool:
        return False

    def _current_scene_id(self) -> str | None:
        controller = getattr(self.window, "scene_controller", None)
        scene_id = getattr(controller, "current_scene_path", None) if controller is not None else None
        scene_id = str(scene_id or "").strip()
        return scene_id or None

    def _snapshot_baseline(self) -> None:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            self._baseline_gold = 0
            self._baseline_true_flags = set()
            return
        try:
            self._baseline_gold = int(gs.get_counter("gold", 0))
        except Exception:
            _log_swallow("GLDN-004", "baseline gold snapshot fallback", once=True)
            self._baseline_gold = 0
        try:
            flags = getattr(self.window.game_state, "flags", {})
            if isinstance(flags, dict):
                self._baseline_true_flags = {str(k) for k, v in flags.items() if bool(v)}
            else:
                self._baseline_true_flags = set()
        except Exception:
            _log_swallow("GLDN-005", "baseline flags snapshot fallback", once=True)
            self._baseline_true_flags = set()

    def update(self, dt: float) -> None:  # noqa: ARG002
        scene_id = self._current_scene_id()
        if scene_id != self._last_scene_id:
            self._last_scene_id = scene_id
            self._snapshot_baseline()

    def _active_quest_label(self) -> str | None:
        qm = getattr(self.window, "quest_manager", None)
        getter = getattr(qm, "get_quests_by_state", None) if qm is not None else None
        quests = getter("active") if callable(getter) else []
        if not isinstance(quests, list) or not quests:
            return None
        ids: list[str] = []
        for q in quests:
            qid = getattr(q, "id", None) if q is not None else None
            qid = str(qid or "").strip()
            if qid:
                ids.append(qid)
        if not ids:
            return None
        return sorted(ids)[0]

    def _gold_delta_and_new_flags(self) -> tuple[int, int]:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return 0, 0
        try:
            current_gold = int(gs.get_counter("gold", 0))
        except Exception:
            _log_swallow("GLDN-006", "current gold snapshot fallback", once=True)
            current_gold = 0
        try:
            flags = getattr(self.window.game_state, "flags", {})
            current_true = {str(k) for k, v in flags.items() if bool(v)} if isinstance(flags, dict) else set()
        except Exception:
            _log_swallow("GLDN-007", "current flags snapshot fallback", once=True)
            current_true = set()
        new_flags = len(current_true.difference(self._baseline_true_flags))
        return int(current_gold - self._baseline_gold), int(new_flags)

    def _should_draw(self) -> bool:
        preset = os.environ.get("MESH_ACTIVE_PRESET")
        wc = getattr(self.window, "world_controller", None)
        world_id = getattr(wc, "id", None) if wc is not None else None
        cfg = getattr(self.window, "engine_config", None)
        world_file = getattr(cfg, "world_file", None) if cfg is not None else None
        return is_golden_slice_demo_context(
            preset_id=preset,
            world_id=world_id,
            world_file=world_file,
        ) or is_act1_demo_context(
            preset_id=preset,
            world_id=world_id,
            world_file=world_file,
        )

    def draw(self) -> None:
        if not self._should_draw():
            return

        preset = os.environ.get("MESH_ACTIVE_PRESET")
        wc = getattr(self.window, "world_controller", None)
        world_id = getattr(wc, "id", None) if wc is not None else None
        cfg = getattr(self.window, "engine_config", None)
        world_file = getattr(cfg, "world_file", None) if cfg is not None else None

        gold_delta, new_flags = self._gold_delta_and_new_flags()

        if is_golden_slice_demo_context(
            preset_id=preset,
            world_id=str(world_id) if world_id is not None else None,
            world_file=world_file,
        ):
            hint_keys: list[str] = []
            if getattr(self.window, "variant_picker_overlay", None) is not None:
                hint_keys.append("V")
            if getattr(self.window, "help_overlay", None) is not None:
                hint_keys.append("H")
            line = build_golden_slice_demo_hud_status_line(
                preset_id=preset,
                world_id=str(world_id) if world_id is not None else None,
                active_quest=self._active_quest_label(),
                gold_delta=gold_delta,
                new_flags=new_flags,
                hint_keys=hint_keys,
            )
        else:
            line = build_act1_demo_hud_status_line(
                preset_id=preset,
                world_id=str(world_id) if world_id is not None else None,
                world_file=str(world_file) if world_file is not None else None,
                active_quest=self._active_quest_label(),
                gold_delta=gold_delta,
                new_flags=new_flags,
                show_picker_hint=getattr(self.window, "variant_picker_overlay", None) is not None,
            )

        x = 14.0
        y = float(self.window.height) - 10.0
        padding_x = 10.0
        padding_y = 6.0
        width = min(float(self.window.width) - 28.0, 760.0)
        height = 24.0

        _draw_rectangle_filled(
            center_x=x + width / 2.0,
            center_y=y - height / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 150),
        )
        optional_arcade.arcade.draw_text(
            line,
            x + padding_x,
            y - padding_y,
            optional_arcade.arcade.color.LIGHT_GRAY,
            11,
            anchor_y="top",
            width=width - padding_x * 2,
        )


