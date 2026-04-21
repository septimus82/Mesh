from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence
import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from .common import (
    INSPECTOR_MAX_LINE_CHARS,
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
    _safe_truncate,
    load_config_json,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


DEV_BROWSER_MAX_FILTER_CHARS = 80
DEV_BROWSER_MAX_ITEMS = 16
DEV_BROWSER_NO_RESULTS_MESSAGE = "No results match."


def _dev_browser_norm(text: object | None) -> str:
    return str(text or "").strip()


def _dev_browser_norm_key(text: object | None) -> str:
    return _dev_browser_norm(text).lower()


def _dev_browser_resolve_world_path_from_preset(preset: Any) -> str | None:
    """Extract a world path from a preset (pipeline step with --world)."""
    if not isinstance(preset, dict):
        return None
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


def build_dev_browser_world_source(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a stable list of world entries from safe presets.

    Each entry shape:
      {"label": str, "world_path": str, "preset": str | None, "world_id": str | None}

    Determinism:
    - Presets scanned in sorted name order
    - Worlds de-duped by normalized path (first wins)
    - Sorted by display label (case-insensitive), then by path
    """
    presets = config.get("presets") if isinstance(config, dict) else None
    presets = presets if isinstance(presets, dict) else {}

    from ..paths import resolve_path

    by_world_path_key: dict[str, dict[str, Any]] = {}

    for preset_name in sorted(presets.keys()):
        preset = presets.get(preset_name)
        world_path = _dev_browser_resolve_world_path_from_preset(preset)
        if not isinstance(world_path, str) or not world_path.strip():
            continue
        normalized = world_path.strip().replace("\\", "/")
        key = normalized.lower()
        if key in by_world_path_key:
            continue

        resolved = resolve_path(normalized)
        if not resolved.exists():
            continue
        world_id: str | None = None
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                wid = raw.get("id")
                if isinstance(wid, str) and wid.strip():
                    world_id = wid.strip()
        except Exception:
            world_id = None

        label_base = world_id or Path(normalized).stem or normalized
        label = f"{label_base} — {normalized}"
        by_world_path_key[key] = {
            "label": label,
            "world_path": normalized,
            "preset": str(preset_name),
            "world_id": world_id,
        }

    entries = list(by_world_path_key.values())
    entries.sort(key=lambda e: (_dev_browser_norm_key(e.get("label")), _dev_browser_norm_key(e.get("world_path"))))
    return entries


def build_dev_browser_scene_source() -> list[dict[str, Any]]:
    """Build a stable list of scene file entries.

    Sources:
    - scenes/*.json
    - packs/**/scenes/*.json

    Sorted by normalized file path.
    """
    roots = [Path("scenes"), Path("packs")]
    discovered: set[str] = set()

    def _add(path: Path) -> None:
        try:
            if not path.is_file():
                return
        except Exception:
            return
        rel = path.as_posix()
        if rel:
            discovered.add(rel)

    if roots[0].exists():
        for path in roots[0].glob("*.json"):
            _add(path)
    if roots[1].exists():
        for path in roots[1].glob("**/scenes/*.json"):
            _add(path)

    entries = [{"label": p, "scene_path": p} for p in sorted(discovered)]
    return entries


def filter_dev_browser_items(items: Sequence[dict[str, Any]], filter_text: str) -> list[dict[str, Any]]:
    """Deterministic, stable-order substring filter (case-insensitive)."""
    needle = _dev_browser_norm_key(filter_text)
    if not needle:
        return list(items)
    filtered: list[dict[str, Any]] = []
    for item in items:
        label = _dev_browser_norm_key(item.get("label"))
        if needle in label:
            filtered.append(item)
    return filtered


class DevBrowserOverlay(UIElement):
    """Developer Scene/World Browser overlay (modal, deterministic)."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.mode: str = "worlds"  # "worlds" | "scenes"
        self.filter_text: str = ""
        self.selected_index: int = 0
        self.preview_visible: bool = True
        self.jump_mode: bool = False
        self.jump_text: str = ""
        self.jump_list_open: bool = False
        self.jump_list_index: int = 0
        self.jump_list_items: list[dict[str, Any]] = []
        self._ignore_text_once: str | None = None
        self._preview_cache: dict[str, list[str]] = {}

        self._world_items: list[dict[str, Any]] = []
        self._scene_items: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._status_message: str | None = None

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def toggle(self) -> bool:
        self.set_visible(not self.visible)
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)
        if self.visible:
            self.mode = "worlds" if self.mode not in {"worlds", "scenes"} else self.mode
            self.filter_text = ""
            self.selected_index = 0
            self.preview_visible = True
            self.jump_mode = False
            self.jump_text = ""
            self.jump_list_open = False
            self.jump_list_index = 0
            self.jump_list_items = []
            self._ignore_text_once = None
            self._preview_cache = {}
            self._refresh_sources()
            self._apply_filter()

    def _refresh_sources(self) -> None:
        config_path = getattr(self.window, "config_path", "config.json") or "config.json"
        config = load_config_json(str(config_path))
        self._world_items = build_dev_browser_world_source(config)
        self._scene_items = build_dev_browser_scene_source()

    def _active_source(self) -> list[dict[str, Any]]:
        return self._world_items if self.mode == "worlds" else self._scene_items

    def _apply_filter(self) -> None:
        source = self._active_source()
        self._items = filter_dev_browser_items(source, self.filter_text)
        if not self._items:
            self.selected_index = 0
            self._status_message = DEV_BROWSER_NO_RESULTS_MESSAGE
        else:
            self.selected_index = max(0, min(self.selected_index, len(self._items) - 1))
            self._status_message = None

    def on_text(self, text: str) -> None:
        if not self.visible:
            return
        if not isinstance(text, str) or not text:
            return
        if self._ignore_text_once is not None and text == self._ignore_text_once:
            self._ignore_text_once = None
            return
        # Ignore obvious control characters; optional_arcade.arcade sends printable glyphs here.
        if any(ord(ch) < 32 for ch in text):
            return
        if self.jump_mode:
            if len(self.jump_text) >= DEV_BROWSER_MAX_FILTER_CHARS:
                return
            self.jump_text += text
            return

        if len(self.filter_text) >= DEV_BROWSER_MAX_FILTER_CHARS:
            return
        self.filter_text += text
        self.selected_index = 0
        self._apply_filter()

    def _toggle_mode(self) -> None:
        self.mode = "scenes" if self.mode == "worlds" else "worlds"
        self.selected_index = 0
        if self.mode != "scenes":
            self.jump_mode = False
            self.jump_text = ""
            self.jump_list_open = False
            self.jump_list_index = 0
            self.jump_list_items = []
            self._ignore_text_once = None
        self._apply_filter()

    def _move_cursor(self, direction: int) -> None:
        if not self._items:
            return
        self.selected_index = (self.selected_index + direction) % len(self._items)

    def _toast(self, message: str, *, seconds: float = 2.5) -> None:
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue(str(message), seconds=seconds)

    def _jump_norm_key(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text.lower()

    def _extract_zone_id(self, entity_data: dict[str, Any]) -> str | None:
        bcfg = entity_data.get("behaviour_config")
        if not isinstance(bcfg, dict):
            return None
        tz_cfg = bcfg.get("TriggerZone")
        if not isinstance(tz_cfg, dict):
            return None
        zone = tz_cfg.get("zone_id")
        if not isinstance(zone, str):
            return None
        zone = zone.strip()
        return zone or None

    def _build_jump_list_items(self) -> list[dict[str, Any]]:
        controller = getattr(self.window, "scene_controller", None)
        current_scene = getattr(controller, "current_scene_path", None) if controller is not None else None
        if not isinstance(current_scene, str) or not current_scene.strip():
            return []

        sprites = getattr(controller, "all_sprites", None) if controller is not None else None
        if sprites is None:
            return []

        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_zones: set[str] = set()
        seen_mesh: set[str] = set()

        def _meta(sprite: Any) -> tuple[str | None, str | None, str | None]:
            entity_data = getattr(sprite, "mesh_entity_data", None)
            if not isinstance(entity_data, dict):
                entity_data = {}
            raw_id = entity_data.get("id")
            raw_id = raw_id.strip() if isinstance(raw_id, str) else None
            zone_id = self._extract_zone_id(entity_data)
            mesh_name = getattr(sprite, "mesh_name", None)
            mesh_name = mesh_name.strip() if isinstance(mesh_name, str) else None
            return raw_id or None, zone_id or None, mesh_name or None

        def _add_item(*, display_key: str, spawn_key: str, entity_id: str | None, zone_id: str | None, mesh: str | None) -> None:
            items.append(
                {
                    "display_key": display_key,
                    "spawn_key": spawn_key,
                    "meta": {"id": entity_id, "zone_id": zone_id, "mesh_name": mesh},
                }
            )

        # 1) id entries (first wins by build order)
        for sprite in sprites:
            entity_id, zone_id, mesh = _meta(sprite)
            if not entity_id:
                continue
            norm = self._jump_norm_key(entity_id)
            if norm is None or norm in seen_ids:
                continue
            seen_ids.add(norm)
            _add_item(display_key=entity_id, spawn_key=norm, entity_id=entity_id, zone_id=zone_id, mesh=mesh)
            if len(items) >= 25:
                return items

        # 2) TriggerZone zone_id entries (first wins by build order)
        for sprite in sprites:
            entity_id, zone_id, mesh = _meta(sprite)
            if entity_id:
                continue
            if not zone_id:
                continue
            norm = self._jump_norm_key(zone_id)
            if norm is None or norm in seen_zones:
                continue
            seen_zones.add(norm)
            _add_item(display_key=zone_id, spawn_key=norm, entity_id=entity_id, zone_id=zone_id, mesh=mesh)
            if len(items) >= 25:
                return items

        # 3) mesh_name entries (first wins by build order)
        for sprite in sprites:
            entity_id, zone_id, mesh = _meta(sprite)
            if entity_id or zone_id:
                continue
            if not mesh:
                continue
            norm = self._jump_norm_key(mesh)
            if norm is None or norm in seen_mesh:
                continue
            seen_mesh.add(norm)
            _add_item(display_key=mesh, spawn_key=norm, entity_id=entity_id, zone_id=zone_id, mesh=mesh)
            if len(items) >= 25:
                return items

        return items

    def _toggle_jump_list(self) -> None:
        if not self.jump_list_open:
            self.jump_list_items = self._build_jump_list_items()
            self.jump_list_index = 0
            self.jump_list_open = True
            return
        self.jump_list_open = False

    def _move_jump_list_cursor(self, direction: int) -> None:
        if not self.jump_list_items:
            self.jump_list_index = 0
            return
        next_index = self.jump_list_index + direction
        self.jump_list_index = max(0, min(next_index, len(self.jump_list_items) - 1))

    def _truncate_jump_row(self, text: str, *, max_chars: int = 72) -> str:
        value = str(text or "")
        if len(value) <= max_chars:
            return value
        if max_chars <= 1:
            return "…"
        return value[: max_chars - 1] + "…"

    def _preview_key(self, kind: str, path: str) -> str:
        normalized_path = str(path or "").strip().replace("\\", "/")
        return f"{kind}:{normalized_path}"

    def _selected_entry(self) -> dict[str, Any] | None:
        if not self._items:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self._items):
            return None
        entry = self._items[self.selected_index]
        return entry if isinstance(entry, dict) else None

    def _read_json_for_preview(self, path_str: str) -> tuple[bool, dict[str, Any] | None, str]:
        from ..paths import resolve_path

        normalized = str(path_str or "").strip().replace("\\", "/")
        if not normalized:
            return False, None, "missing path"
        path = resolve_path(normalized)
        try:
            if not path.exists():
                return False, None, "file not found"
        except Exception:
            return False, None, "file not found"

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False, None, "invalid json"

        if not isinstance(raw, dict):
            return False, None, "invalid root"
        return True, raw, ""

    def _norm_key(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text.lower()

    def _entity_behaviours(self, entity: dict[str, Any]) -> list[str]:
        raw = entity.get("behaviours")
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    out.append(t)
            elif isinstance(item, dict):
                kind = item.get("type")
                if isinstance(kind, str) and kind.strip():
                    out.append(kind.strip())
        return out

    def _scene_preview_lines(self, scene_path: str, raw: dict[str, Any]) -> list[str]:
        entities = raw.get("entities")
        entities = entities if isinstance(entities, list) else []
        entity_dicts = [e for e in entities if isinstance(e, dict)]

        trigger_zone_count = 0
        transition_count = 0

        unique_ids: set[str] = set()
        dup_id_occurrences = 0
        missing_id = 0

        unique_zone_ids: set[str] = set()
        dup_zone_occurrences = 0
        missing_zone_id = 0

        unique_mesh: set[str] = set()
        dup_mesh_occurrences = 0

        for entity in entity_dicts:
            behaviours = self._entity_behaviours(entity)
            bcfg = entity.get("behaviour_config")
            bcfg = bcfg if isinstance(bcfg, dict) else {}

            has_trigger = ("TriggerZone" in behaviours) or ("TriggerZone" in bcfg)
            has_transition = ("SceneTransition" in behaviours) or ("SceneTransition" in bcfg)

            # id
            entity_id = entity.get("id")
            entity_id = entity_id.strip() if isinstance(entity_id, str) else ""
            if not entity_id:
                missing_id += 1
            else:
                kid = self._norm_key(entity_id)
                if kid is not None:
                    if kid in unique_ids:
                        dup_id_occurrences += 1
                    else:
                        unique_ids.add(kid)

            # trigger zone / zone_id
            if has_trigger:
                trigger_zone_count += 1
                tz = bcfg.get("TriggerZone")
                tz = tz if isinstance(tz, dict) else {}
                zid = tz.get("zone_id")
                zid = zid.strip() if isinstance(zid, str) else ""
                if not zid:
                    missing_zone_id += 1
                else:
                    kz = self._norm_key(zid)
                    if kz is not None:
                        if kz in unique_zone_ids:
                            dup_zone_occurrences += 1
                        else:
                            unique_zone_ids.add(kz)

            if has_transition:
                transition_count += 1

            mesh_name = entity.get("mesh_name") or entity.get("name") or entity.get("prefab_id")
            mesh_name = mesh_name.strip() if isinstance(mesh_name, str) else ""
            if mesh_name:
                km = self._norm_key(mesh_name)
                if km is not None:
                    if km in unique_mesh:
                        dup_mesh_occurrences += 1
                    else:
                        unique_mesh.add(km)

        lines = [
            "Preview (Scene)",
            f"file: {Path(scene_path).name}",
            f"entity_count: {len(entity_dicts)}",
            f"trigger_zone_count: {trigger_zone_count}",
            f"transition_count: {transition_count}",
            f"unique_ids_count: {len(unique_ids)}",
            f"duplicate_ids_count: {dup_id_occurrences}",
            f"zone_id_count: {len(unique_zone_ids)}",
            f"duplicate_zone_id_count: {dup_zone_occurrences}",
            f"mesh_name_count: {len(unique_mesh)}",
            f"duplicate_mesh_name_count: {dup_mesh_occurrences}",
            (
                "schema_strict: OK"
                if (missing_id + missing_zone_id + dup_id_occurrences + dup_zone_occurrences) == 0
                else (
                    f"schema_strict: missing_id={missing_id} "
                    f"missing_zone_id={missing_zone_id} "
                    f"duplicate_ids={dup_id_occurrences} "
                    f"duplicate_zone_ids={dup_zone_occurrences}"
                )
            ),
        ]
        return [_safe_truncate(line, INSPECTOR_MAX_LINE_CHARS) for line in lines]

    def _world_preview_lines(self, world_path: str, raw: dict[str, Any]) -> list[str]:
        world_id = raw.get("id")
        world_id = world_id.strip() if isinstance(world_id, str) else ""
        scenes = raw.get("scenes")
        scenes = scenes if isinstance(scenes, dict) else {}

        scene_ids = [str(k) for k in scenes.keys()]
        scene_ids_sorted = sorted(scene_ids)
        start_scene = raw.get("start_scene")
        start_scene = start_scene.strip() if isinstance(start_scene, str) else ""
        start_ok = bool(start_scene and start_scene in scenes)

        links = raw.get("links")
        link_count = len(links) if isinstance(links, list) else 0

        preview_ids = scene_ids_sorted[:8]
        preview_list = ",".join(preview_ids) if preview_ids else "-"

        start_label = start_scene or "-"
        start_suffix = "ok" if start_ok else "missing"
        if start_label == "-":
            start_suffix = "missing"

        lines = [
            "Preview (World)",
            f"file: {Path(world_path).name}",
            f"world_id: {world_id or '-'}",
            f"scene_count: {len(scene_ids_sorted)}",
            f"scenes: {preview_list}" + (f" (+{len(scene_ids_sorted) - len(preview_ids)})" if len(scene_ids_sorted) > len(preview_ids) else ""),
            f"start_scene: {start_label} ({start_suffix})",
            f"link_count: {link_count}",
        ]
        return [_safe_truncate(line, INSPECTOR_MAX_LINE_CHARS) for line in lines]

    def _get_preview_lines(self) -> list[str]:
        entry = self._selected_entry()
        if entry is None:
            return ["Preview", "no selection"]

        if self.mode == "worlds":
            path = _dev_browser_norm(entry.get("world_path"))
            if not path:
                return ["Preview (World)", "missing path"]
            cache_key = self._preview_key("world", path)
            if cache_key in self._preview_cache:
                return self._preview_cache[cache_key]
            ok, raw, err = self._read_json_for_preview(path)
            if not ok or raw is None:
                lines = ["Preview (World)", f"file: {Path(path).name}", f"error: {err}"]
                self._preview_cache[cache_key] = [_safe_truncate(line, INSPECTOR_MAX_LINE_CHARS) for line in lines]
                return self._preview_cache[cache_key]
            lines = self._world_preview_lines(path, raw)
            self._preview_cache[cache_key] = lines
            return lines

        path = _dev_browser_norm(entry.get("scene_path"))
        if not path:
            return ["Preview (Scene)", "missing path"]
        cache_key = self._preview_key("scene", path)
        if cache_key in self._preview_cache:
            return self._preview_cache[cache_key]
        ok, raw, err = self._read_json_for_preview(path)
        if not ok or raw is None:
            lines = ["Preview (Scene)", f"file: {Path(path).name}", f"error: {err}"]
            self._preview_cache[cache_key] = [_safe_truncate(line, INSPECTOR_MAX_LINE_CHARS) for line in lines]
            return self._preview_cache[cache_key]
        lines = self._scene_preview_lines(path, raw)
        self._preview_cache[cache_key] = lines
        return lines

    def _resolve_jump_target(self, typed: str) -> tuple[bool, str | None, str]:
        raw = str(typed or "")
        needle = raw.strip()
        if not needle:
            return False, None, f"Jump target not found: {raw}"

        controller = getattr(self.window, "scene_controller", None)
        current_scene = getattr(controller, "current_scene_path", None) if controller is not None else None
        if not isinstance(current_scene, str) or not current_scene.strip():
            return False, None, "Jump unavailable (no scene loaded)"

        ensure = getattr(controller, "_ensure_scene_index", None)
        idx = ensure() if callable(ensure) else None
        if idx is None:
            return False, None, "Jump unavailable (no scene loaded)"

        normalized = needle.lower()
        if getattr(idx, "get_by_id", None) and idx.get_by_id(needle) is not None:
            return True, normalized, f"Jumped to: {normalized}"
        if getattr(idx, "get_by_zone_id", None) and idx.get_by_zone_id(needle) is not None:
            return True, normalized, f"Jumped to: {normalized}"
        if getattr(idx, "get_first_by_mesh_name", None) and idx.get_first_by_mesh_name(needle) is not None:
            return True, normalized, f"Jumped to: {normalized}"

        return False, None, f"Jump target not found: {raw}"

    def _request_jump(self, spawn_id: str) -> None:
        spawn_id = str(spawn_id or "").strip()
        if not spawn_id:
            return
        set_spawn = getattr(self.window, "set_next_spawn_point", None)
        if callable(set_spawn):
            set_spawn(spawn_id)

        reload_current = getattr(self.window, "request_reload_current_scene", None)
        if callable(reload_current):
            reload_current()
            return

        controller = getattr(self.window, "scene_controller", None)
        current_scene = getattr(controller, "current_scene_path", None) if controller is not None else None
        if isinstance(current_scene, str) and current_scene.strip():
            self.window.request_scene_change(current_scene)

    def _apply_world_controller(self, world_path: str) -> dict[str, Any] | None:
        from ..migrations import migrate_payload
        from ..paths import resolve_path
        from ..world_controller import WorldController

        cfg = getattr(self.window, "engine_config", None)
        if cfg is not None:
            try:
                cfg.world_file = str(world_path)
            except Exception:
                _log_swallow("DEVB-001", "engine/ui_overlays/dev_browser.py pass-only blanket swallow")
                pass

        path = resolve_path(world_path)
        if not path.exists():
            self.window.world_controller = None
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                self.window.world_controller = None
                return None
            migrated = migrate_payload("world", raw)
            self.window.world_controller = WorldController(migrated)
            return migrated if isinstance(migrated, dict) else raw
        except Exception:
            self.window.world_controller = None
            return None

    def _resolve_start_scene_from_world(self, world_payload: dict[str, Any]) -> tuple[str | None, str | None]:
        scenes_value = world_payload.get("scenes")
        scenes = scenes_value if isinstance(scenes_value, dict) else {}
        start_key = world_payload.get("start_scene")
        spawn_id = world_payload.get("start_spawn")
        spawn_id = str(spawn_id).strip() if isinstance(spawn_id, str) else "default"
        if isinstance(start_key, str) and start_key.strip():
            entry = scenes.get(start_key)
            if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"].strip():
                return str(entry["path"]).strip(), spawn_id
        # Fallback: first scene by key
        if isinstance(scenes, dict) and scenes:
            for key in sorted(scenes.keys()):
                entry = scenes.get(key)
                if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"].strip():
                    return str(entry["path"]).strip(), spawn_id
        return None, spawn_id

    def _queue_scene_change(self, scene_path: str, *, spawn_id: str | None = None) -> None:
        scene_path = str(scene_path).strip().replace("\\", "/")
        requester = getattr(self.window, "queue_scene_change", None)
        if callable(requester):
            requester(scene_path, spawn_id=spawn_id or "default")
        else:
            self.window.request_scene_change(scene_path)

    def _activate_selected(self) -> bool:
        if not self._items:
            return False
        if self.selected_index < 0 or self.selected_index >= len(self._items):
            return False
        selected = self._items[self.selected_index]

        if self.mode == "worlds":
            world_path = _dev_browser_norm(selected.get("world_path"))
            if not world_path:
                return False
            payload = self._apply_world_controller(world_path)
            if payload is None:
                self._toast(f"Failed to load world: {world_path}")
                return False
            scene_path, spawn_id = self._resolve_start_scene_from_world(payload)
            if not scene_path:
                self._toast("World has no start scene")
                return False
            self._queue_scene_change(scene_path, spawn_id=spawn_id)
            self._toast(f"Loaded world: {world_path}")
            self.set_visible(False)
            return True

        # scenes
        if getattr(self.window, "world_controller", None) is None:
            self._toast("Scene load requires a world")
            return False
        scene_path = _dev_browser_norm(selected.get("scene_path"))
        if not scene_path:
            return False
        self._queue_scene_change(scene_path, spawn_id="default")
        self._toast(f"Loaded scene: {scene_path}")
        self.set_visible(False)
        return True

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.visible:
            return False

        # Hard modal capture.
        if key in (optional_arcade.arcade.key.P,):
            self.preview_visible = not self.preview_visible
            return True
        if key in (optional_arcade.arcade.key.ESCAPE,):
            if self.jump_mode:
                if self.jump_list_open:
                    self.jump_list_open = False
                    return True
                self.jump_mode = False
                self.jump_text = ""
                self.jump_list_open = False
                self.jump_list_index = 0
                self.jump_list_items = []
                self._ignore_text_once = None
                return True
            self.set_visible(False)
            return True
        if key in (optional_arcade.arcade.key.B,):
            self.set_visible(False)
            return True
        if key in (optional_arcade.arcade.key.TAB,):
            self._toggle_mode()
            return True
        if key in (optional_arcade.arcade.key.SLASH,) and self.mode == "scenes":
            if not self.jump_mode:
                self.jump_mode = True
                self.jump_text = ""
                self.jump_list_open = False
                self.jump_list_index = 0
                self.jump_list_items = []
                self._ignore_text_once = "/"
            return True
        if key in (optional_arcade.arcade.key.L,) and self.mode == "scenes" and self.jump_mode:
            self._toggle_jump_list()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            if self.jump_mode:
                if self.jump_text:
                    self.jump_text = self.jump_text[:-1]
                return True
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
                self.selected_index = 0
                self._apply_filter()
            return True
        if key == optional_arcade.arcade.key.UP:
            if self.jump_mode and self.jump_list_open:
                self._move_jump_list_cursor(-1)
                return True
            self._move_cursor(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            if self.jump_mode and self.jump_list_open:
                self._move_jump_list_cursor(1)
                return True
            self._move_cursor(1)
            return True
        if key == optional_arcade.arcade.key.ENTER:
            if self.jump_mode:
                if self.jump_list_open:
                    if not self.jump_list_items:
                        self._toast("Jump unavailable (no scene loaded)")
                        return True
                    selected = self.jump_list_items[
                        max(0, min(self.jump_list_index, len(self.jump_list_items) - 1))
                    ]
                    typed = str(selected.get("spawn_key") or selected.get("display_key") or "")
                    ok, resolved, message = self._resolve_jump_target(typed)
                    if ok and resolved:
                        self._request_jump(resolved)
                        self.jump_mode = False
                        self.jump_text = ""
                        self.jump_list_open = False
                        self.jump_list_index = 0
                        self.jump_list_items = []
                    self._toast(message)
                    return True
                ok, resolved, message = self._resolve_jump_target(self.jump_text)
                if ok and resolved:
                    self._request_jump(resolved)
                self._toast(message)
                return True
            self._activate_selected()
            return True

        return True

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(840.0, max(480.0, self.window.width - 140.0))
        height = min(520.0, max(260.0, self.window.height - 160.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        text_left = left + 40.0
        title_y = top - 20.0
        mode_label = "Worlds" if self.mode == "worlds" else "Scenes"

        optional_arcade.arcade.draw_text(
            f"Dev Browser [{mode_label}]",
            text_left,
            title_y,
            optional_arcade.arcade.color.WHITE,
            20,
            anchor_y="top",
        )

        filter_preview = self.filter_text
        optional_arcade.arcade.draw_text(
            f"Filter: {filter_preview}",
            text_left,
            title_y - 32.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
            anchor_y="top",
        )

        y_offset = 64.0
        if self.mode == "scenes" and self.jump_mode:
            optional_arcade.arcade.draw_text(
                f"Jump: {self.jump_text}",
                text_left,
                title_y - 48.0,
                optional_arcade.arcade.color.LIGHT_GRAY,
                12,
                anchor_y="top",
            )
            y_offset = 84.0

        if not self._items:
            message = self._status_message or DEV_BROWSER_NO_RESULTS_MESSAGE
            optional_arcade.arcade.draw_text(
                message,
                text_left,
                title_y - (y_offset + 8.0),
                optional_arcade.arcade.color.LIGHT_GRAY,
                13,
                width=width - 80.0,
                multiline=True,
                anchor_y="top",
            )
        else:
            y = title_y - y_offset
            line_height = 18.0
            max_lines = min(DEV_BROWSER_MAX_ITEMS, int((height - 140.0) / line_height))
            start = max(0, min(self.selected_index - max_lines // 2, max(0, len(self._items) - max_lines)))
            end = min(len(self._items), start + max_lines)
            for index in range(start, end):
                entry = self._items[index]
                prefix = "▶ " if index == self.selected_index else "  "
                label = _dev_browser_norm(entry.get("label"))
                color = optional_arcade.arcade.color.WHITE if index == self.selected_index else optional_arcade.arcade.color.LIGHT_GRAY
                optional_arcade.arcade.draw_text(
                    f"{prefix}{label}",
                    text_left,
                    y,
                    color,
                    13,
                    anchor_y="top",
                )
                y -= line_height

        help_line = "Type to filter • Up/Down select • Enter load • Tab mode • P preview • Esc close"
        if self.mode == "scenes" and not self.jump_mode:
            help_line = "Type to filter • Up/Down select • Enter load • Tab mode • / jump • P preview • Esc close"
        if self.mode == "scenes" and self.jump_mode:
            help_line = "Jump mode • Type target • Enter jump • L list • P preview • Esc cancel"
        if self.mode == "scenes" and self.jump_mode and self.jump_list_open:
            help_line = "Jump list • Up/Down select • Enter jump • P preview • Esc close list"
        optional_arcade.arcade.draw_text(
            help_line,
            text_left,
            bottom + 24.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
        )

        if self.preview_visible and not (self.jump_mode and self.jump_list_open):
            lines = self._get_preview_lines()
            panel_width = min(360.0, max(240.0, width - 520.0))
            panel_left = right - 20.0 - panel_width
            panel_right = panel_left + panel_width
            panel_top = top - 16.0
            panel_bottom = bottom + 44.0

            _draw_rectangle_filled(
                center_x=(panel_left + panel_right) / 2.0,
                center_y=(panel_top + panel_bottom) / 2.0,
                width=panel_width,
                height=(panel_top - panel_bottom),
                color=(10, 10, 10, 230),
            )
            _draw_lrtb_rectangle_outline(panel_left, panel_right, panel_top, panel_bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

            y = panel_top - 12.0
            for line in lines[:14]:
                optional_arcade.arcade.draw_text(
                    _safe_truncate(str(line), INSPECTOR_MAX_LINE_CHARS),
                    panel_left + 12.0,
                    y,
                    optional_arcade.arcade.color.LIGHT_GRAY,
                    12,
                    anchor_y="top",
                )
                y -= 16.0

        if self.mode == "scenes" and self.jump_mode and self.jump_list_open:
            panel_width = min(460.0, max(280.0, width - 180.0))
            panel_height = min(360.0, max(180.0, height - 200.0))
            panel_left = right - 30.0 - panel_width
            panel_bottom = bottom + 54.0
            panel_right = panel_left + panel_width
            panel_top = panel_bottom + panel_height

            _draw_rectangle_filled(
                center_x=(panel_left + panel_right) / 2.0,
                center_y=(panel_top + panel_bottom) / 2.0,
                width=panel_width,
                height=panel_height,
                color=(12, 12, 12, 230),
            )
            _draw_lrtb_rectangle_outline(panel_left, panel_right, panel_top, panel_bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

            optional_arcade.arcade.draw_text(
                "Jump Targets",
                panel_left + 16.0,
                panel_top - 12.0,
                optional_arcade.arcade.color.WHITE,
                14,
                anchor_y="top",
            )

            if not self.jump_list_items:
                optional_arcade.arcade.draw_text(
                    "No entities available",
                    panel_left + 16.0,
                    panel_top - 36.0,
                    optional_arcade.arcade.color.LIGHT_GRAY,
                    12,
                    anchor_y="top",
                )
                return

            y = panel_top - 36.0
            line_height = 18.0
            max_lines = min(25, int((panel_height - 60.0) / line_height))
            start = max(
                0,
                min(self.jump_list_index - max_lines // 2, max(0, len(self.jump_list_items) - max_lines)),
            )
            end = min(len(self.jump_list_items), start + max_lines)

            for index in range(start, end):
                entry = self.jump_list_items[index]
                meta_value = entry.get("meta")
                meta = meta_value if isinstance(meta_value, dict) else {}
                raw_id = meta.get("id") if isinstance(meta.get("id"), str) else None
                raw_zone = meta.get("zone_id") if isinstance(meta.get("zone_id"), str) else None
                raw_mesh = meta.get("mesh_name") if isinstance(meta.get("mesh_name"), str) else None
                row = (
                    f"{entry.get('display_key')} "
                    f"(id:{raw_id or '-'}, zone:{raw_zone or '-'}, mesh:{raw_mesh or '-'})"
                )
                prefix = "> " if index == self.jump_list_index else "  "
                color = optional_arcade.arcade.color.WHITE if index == self.jump_list_index else optional_arcade.arcade.color.LIGHT_GRAY
                optional_arcade.arcade.draw_text(
                    self._truncate_jump_row(f"{prefix}{row}"),
                    panel_left + 16.0,
                    y,
                    color,
                    12,
                    anchor_y="top",
                )
                y -= line_height


