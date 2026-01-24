from __future__ import annotations

import json
import os
from typing import Any, Callable

from engine.console_runtime.models import ParsedCommand
from engine.console_runtime.parse import parse_command_line
from engine.console_runtime import handlers


Handler = Callable[[Any, list[str]], bool]


def _dispatch_table() -> dict[str, Handler]:
    entries: list[tuple[str, Handler]] = []

    def add(name: str, handler: Handler) -> None:
        entries.append((name, handler))

    add("help", lambda c, a: (c._help(), True)[1])
    add("?", lambda c, a: (c._help(), True)[1])

    add("clear", handlers.handle_clear)
    add("pause", handlers.handle_pause)
    add("strict_on", handlers.handle_strict_on)
    add("strict_off", handlers.handle_strict_off)
    add("selftest", handlers.handle_selftest)
    add("flag", handlers.handle_flag)
    add("counter", handlers.handle_counter)
    add("encounter", handlers.handle_encounter)
    add("gstate", handlers.handle_gstate)
    add("quest", handlers.handle_quest)
    add("cutscene", handlers.handle_cutscene)
    add("xp", handlers.handle_xp)
    add("stats", handlers.handle_stats)
    add("world", handlers.handle_world)
    add("entity", lambda c, a: (c._entity_command(a), True)[1])
    add("spawn", lambda c, a: (c._spawn_command(a), True)[1])
    add("spawn_like", lambda c, a: (c._spawn_like_command(a), True)[1])
    add("behaviours", lambda c, a: (c._list_registered_behaviours(), True)[1])
    add("behaviour", lambda c, a: (c._behaviour_detail(a), True)[1])
    add("beh", lambda c, a: (c._beh_command(a), True)[1])
    add("events", lambda c, a: (c._events_command(), True)[1])
    add("update_order", lambda c, a: (c._update_order_command(), True)[1])

    def _dumpstate(c, a):
        target_path = a[0] if a else "mesh_dump.json"
        c._dump_state(target_path)
        return True

    add("dumpstate", _dumpstate)

    def _dump_scene(c, a):
        target_path = a[0] if a else "mesh_scene.json"
        c._dump_scene(target_path)
        return True

    add("dump_scene", _dump_scene)

    def _loadstate(c, a):
        if not a:
            c.log("Usage: loadstate <path>")
        else:
            c._load_state(a[0])
        return True

    add("loadstate", _loadstate)

    add("index", lambda c, a: (c._build_project_index(a), True)[1])

    def _ai_context(c, a):
        target_path = a[0] if a else "mesh_ai_context.json"
        c._ai_context(target_path)
        return True

    add("ai_context", _ai_context)

    def _docs(c, a):
        target_dir = a[0] if a else "docs"
        c._generate_docs(target_dir)
        return True

    add("docs", _docs)

    def _ai_bundle(c, a):
        target_dir = a[0] if a else "mesh_ai_bundle"
        c._ai_bundle(target_dir)
        return True

    add("ai_bundle", _ai_bundle)

    def _ai_job(c, a):
        if not a:
            c.log("Usage: ai_job <job_path>")
            return True
        c._ai_job(a[0])
        return True

    add("ai_job", _ai_job)

    def _daynight(c, a):
        dn = getattr(c.window, "day_night", None)
        if dn is None:
            c.log("Day/night system not available.")
            return True
        if not a:
            c.log(f"Day/night enabled = {dn.enabled}")
            return True
        mode = a[0].lower()
        dn.enabled = mode == "on"
        c.log(f"Day/night enabled set to {dn.enabled}")
        return True

    add("daynight", _daynight)

    def _time_of_day(c, _a):
        dn = getattr(c.window, "day_night", None)
        if dn is None:
            c.log("Day/night system not available.")
            return True
        c.log(f"time_of_day = {dn.hour:.2f}h")
        return True

    add("time_of_day", _time_of_day)

    def _set_time_of_day(c, a):
        if not a:
            c.log("Usage: set_time_of_day <hour>")
            return True
        dn = getattr(c.window, "day_night", None)
        if dn is None:
            c.log("Day/night system not available.")
            return True
        try:
            dn.set_hour(float(a[0]))
            c.log(f"time_of_day set to {dn.hour:.2f}h")
        except ValueError:
            c.log("Invalid hour value.")
        return True

    add("set_time_of_day", _set_time_of_day)

    def _day_night(c, a):
        dn = getattr(c.window, "day_night", None)
        if dn is None:
            c.log("Day/night system not available.")
            return True
        if not a:
            c.log(f"Day/night enabled = {dn.enabled}")
            return True
        mode = a[0].lower()
        if mode in {"on", "off"}:
            dn.set_enabled(mode == "on")
            c.log(f"Day/night enabled set to {dn.enabled}")
        else:
            c.log("Usage: day_night [on|off]")
        return True

    add("day_night", _day_night)

    def _lighting(c, a):
        lighting = getattr(c.window, "lighting", None)
        if lighting is None:
            c.log("[Lighting] LightManager not present")
            return True
        if not a:
            stats = lighting.get_stats()
            c.log(
                f"[Lighting] enabled={stats['enabled']} available={stats['available']} "
                f"static={stats['static_count']}/{stats['max_static']} "
                f"dynamic={stats['dynamic_count']}/{stats['max_dynamic']}"
            )
            return True
        mode = a[0].lower()
        if mode in {"on", "off"}:
            lighting.enabled = mode == "on"
            c.log(f"[Lighting] enabled set to {lighting.enabled}")
        else:
            c.log("[Lighting] usage: lighting [on|off]")
        return True

    add("lighting", _lighting)

    def _lighting_limit(c, a):
        lighting = getattr(c.window, "lighting", None)
        if lighting is None:
            c.log("[Lighting] LightManager not present")
            return True
        if len(a) < 2:
            stats = lighting.get_stats()
            c.log(f"[Lighting] max_static={stats['max_static']} max_dynamic={stats['max_dynamic']}")
            return True
        which = a[0].lower()
        value = a[1]
        if which not in {"static", "dynamic"}:
            c.log("[Lighting] usage: lighting_limit [static|dynamic] [value|none]")
            return True
        if value.lower() == "none":
            val = None
        else:
            try:
                val = int(value)
            except ValueError:
                c.log("[Lighting] value must be an integer or 'none'")
                return True
        if which == "static":
            lighting.set_max_static_lights(val)
        else:
            lighting.set_max_dynamic_lights(val)
        stats = lighting.get_stats()
        c.log(f"[Lighting] max_static={stats['max_static']} max_dynamic={stats['max_dynamic']}")
        return True

    add("lighting_limit", _lighting_limit)

    def _lighting_debug(c, a):
        lighting = getattr(c.window, "lighting", None)
        if lighting is None:
            c.log("[Lighting] LightManager not present")
            return True
        if not a:
            enabled = bool(getattr(lighting, "debug_geometry_enabled", False))
            c.log(f"[Lighting] debug_geometry={enabled}")
            return True
        mode = a[0].lower()
        if mode == "toggle":
            toggle = getattr(lighting, "toggle_debug_geometry", None)
            if callable(toggle):
                enabled = bool(toggle())
            else:
                enabled = not bool(getattr(lighting, "debug_geometry_enabled", False))
                setattr(lighting, "debug_geometry_enabled", enabled)
            c.log(f"[Lighting] debug_geometry set to {enabled}")
            return True
        if mode in {"on", "off"}:
            enabled = mode == "on"
            setattr(lighting, "debug_geometry_enabled", enabled)
            c.log(f"[Lighting] debug_geometry set to {enabled}")
            return True
        c.log("[Lighting] usage: lighting_debug [on|off|toggle]")
        return True

    add("lighting_debug", _lighting_debug)

    def _shadows_mode(c, a):
        lighting = getattr(c.window, "lighting", None)
        if lighting is None:
            c.log("[Lighting] LightManager not present")
            return True
        if not a:
            mode = getattr(lighting, "shadows_mode", "none")
            c.log(f"[Lighting] shadows_mode={mode} (allowed: none, hard, direct)")
            return True
        mode = a[0].strip().lower()
        allowed = {"none", "hard", "direct"}
        if mode not in allowed:
            c.log(f"Invalid shadows_mode: {mode}. Allowed: none, hard, direct")
            return True
        setter = getattr(lighting, "set_shadows_mode", None)
        if callable(setter):
            try:
                mode = setter(mode)
            except Exception:  # noqa: BLE001
                c.log(f"Invalid shadows_mode: {mode}. Allowed: none, hard, direct")
                return True
        else:
            setattr(lighting, "shadows_mode", mode)
        c.log(f"[Lighting] shadows_mode set to {mode}")
        return True

    add("shadows_mode", _shadows_mode)
    add("shadow_mode", _shadows_mode)

    def _lighting_stats(c, _a):
        lighting = getattr(c.window, "lighting", None)
        if lighting is None:
            c.log("[Lighting] LightManager not present")
            return True
        scene_controller = getattr(c.window, "scene_controller", None)
        scene_path = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        tilemap_present = bool(getattr(scene_controller, "tilemap_instance", None)) if scene_controller is not None else False
        collision_layer_id = None
        try:
            scene_data = getattr(scene_controller, "current_scene_data", None) if scene_controller is not None else None
            if isinstance(scene_data, dict):
                tilemap_cfg = scene_data.get("tilemap")
                if isinstance(tilemap_cfg, dict):
                    collision_layer_id = tilemap_cfg.get("collision_layer_id")
        except Exception:  # noqa: BLE001
            collision_layer_id = None
        getter = getattr(lighting, "get_lighting_stats", None)
        stats = getter() if callable(getter) else {}
        mode = stats.get("shadows_mode", getattr(lighting, "shadows_mode", "none"))
        c.log(
            "[Lighting] scene=%s tilemap_present=%s collision_layer_id=%s shadows_mode=%s static_light_count=%s dynamic_light_count=%s selected_shadow_light_type=%s selected_shadow_light_pos=%s selected_shadow_light_radius=%s nearest_occluder_distance_est=%s cull_square_intersects_any_occluder=%s occluder_count=%s culled_occluder_count=%s shadow_poly_count=%s mask_rendered=%s mask_backend=%s composite_ok=%s fallback_drawn=%s"
            % (
                scene_path,
                tilemap_present,
                collision_layer_id,
                mode,
                stats.get("static_light_count", 0),
                stats.get("dynamic_light_count", 0),
                stats.get("selected_shadow_light_type", None),
                stats.get("selected_shadow_light_pos", None),
                stats.get("selected_shadow_light_radius", None),
                stats.get("nearest_occluder_distance_est", None),
                stats.get("cull_square_intersects_any_occluder", False),
                stats.get("occluder_count", 0),
                stats.get("culled_occluder_count", 0),
                stats.get("shadow_poly_count", 0),
                stats.get("mask_rendered", False),
                stats.get("mask_backend", None),
                stats.get("composite_ok", None),
                stats.get("fallback_drawn", False),
            )
        )
        return True

    add("lighting_stats", _lighting_stats)
    add("lighting_state", _lighting_stats)

    add("reload_behaviours", lambda c, a: (c._reload_behaviours(), True)[1])

    def _validate_scene(c, a):
        target_path = a[0] if a else (c.window.scene_controller.current_scene_path or "scenes/test_scene.json")
        c._validate_scene(target_path)
        return True

    add("validate_scene", _validate_scene)
    add("reload", lambda c, a: (c.window.reload_scene(), True)[1])

    def _reload_scene(c, a):
        target = a[0] if a else None
        c.window.reload_scene(target)
        return True

    add("reload_scene", _reload_scene)

    def _scene(c, a):
        if not a:
            return False
        sub = a[0].lower()
        if sub == "save":
            c._save_scene(a[1:])
            return True
        if sub == "dump":
            target_path = a[1] if len(a) > 1 else "mesh_scene_dump.json"
            c._dump_scene(target_path)
            return True
        target = a[0]
        c.log(f"Switching scene to '{target}'")
        c.window.request_scene_change(target)
        return True

    add("scene", _scene)

    add("camera", lambda c, a: (c._camera_command(a), True)[1])

    def _rules(c, _a):
        c.log("collision_rules:")
        for pair, value in sorted(c.window.collision_rules.items(), key=lambda item: str(item[0])):
            c.log(f"  {pair}: {value}")
        return True

    add("rules", _rules)
    add("assets", lambda c, a: (c._assets_command(a), True)[1])

    def _extract_json_flag(args: list[str]) -> tuple[bool, list[str]]:
        json_enabled = False
        remaining: list[str] = []
        for arg in args:
            if str(arg).strip() == "--json":
                json_enabled = True
            else:
                remaining.append(arg)
        return json_enabled, remaining

    def _log_json(c, payload: dict[str, Any]) -> None:
        c.log(json.dumps(payload, separators=(",", ":")))

    def _resolve_prefab_id_from_hover(c) -> str | None:
        window = getattr(c, "window", None)
        if window is None:
            return None
        try:
            from engine.tooling_runtime.authoring_snippets import (
                get_effective_hover_payload,
                get_scene_inspector_payload,
            )
        except Exception:  # noqa: BLE001
            return None

        payload = get_scene_inspector_payload(window)
        if not isinstance(payload, dict):
            return None
        try:
            payload = get_effective_hover_payload(window, payload) or payload
        except Exception:  # noqa: BLE001
            payload = payload
        hover = payload.get("hover")
        if not isinstance(hover, dict):
            return None
        prefab_id = hover.get("prefab_id")
        if isinstance(prefab_id, str) and prefab_id.strip():
            return prefab_id.strip()
        return None

    def _prefab_source(c, a):
        json_enabled, args = _extract_json_flag(list(a) if a else [])
        prefab_id = str(args[0]).strip() if args and str(args[0]).strip() else None
        if prefab_id is None:
            prefab_id = _resolve_prefab_id_from_hover(c)
            if prefab_id is None:
                if json_enabled:
                    _log_json(
                        c,
                        {
                            "cmd": "prefab_source",
                            "prefab_id": None,
                            "source": None,
                            "ok": False,
                            "reason": "no_hovered_prefab",
                        },
                    )
                else:
                    c.log("No prefab_id from hover/selection. Usage: prefab_source <prefab_id>")
                return True
        try:
            from engine.prefabs import get_prefab_manager

            manager = get_prefab_manager()
            manager.load()
            sources = manager.prefab_sources
            source = sources.get(prefab_id) if isinstance(sources, dict) else None
        except Exception:  # noqa: BLE001
            source = None
        if not isinstance(source, str) or not source.strip():
            source = None
        if json_enabled:
            _log_json(
                c,
                {
                    "cmd": "prefab_source",
                    "prefab_id": prefab_id,
                    "source": source,
                    "ok": bool(source),
                },
            )
            return True
        source_text = source or "unknown"
        c.log(f"[Prefab] id={prefab_id} source={source_text}")
        return True

    def _prefab_source_chain(c, a):
        json_enabled, args = _extract_json_flag(list(a) if a else [])
        if not args or not str(args[0]).strip():
            if json_enabled:
                _log_json(
                    c,
                    {
                        "cmd": "prefab_source_chain",
                        "prefab_id": None,
                        "chain": [],
                        "ok": False,
                        "reason": "missing_prefab_id",
                    },
                )
            else:
                c.log("Usage: prefab_source_chain <prefab_id>")
            return True
        prefab_id = str(args[0]).strip()
        try:
            from engine.prefabs import get_prefab_manager

            manager = get_prefab_manager()
            manager.load()
            chains = manager.prefab_source_chain
            raw_chain = chains.get(prefab_id) if isinstance(chains, dict) else None
        except Exception:  # noqa: BLE001
            raw_chain = None

        chain: list[str] = []
        if isinstance(raw_chain, list):
            for entry in raw_chain:
                if isinstance(entry, str) and entry.strip():
                    chain.append(entry)
        if json_enabled:
            _log_json(
                c,
                {
                    "cmd": "prefab_source_chain",
                    "prefab_id": prefab_id,
                    "chain": chain,
                    "ok": bool(chain),
                },
            )
            return True
        chain_text = " -> ".join(chain) if chain else "unknown"
        c.log(f"[Prefab] id={prefab_id} chain={chain_text}")
        return True

    add("prefab_source", _prefab_source)
    add("prefab_source_chain", _prefab_source_chain)

    def _config(c, _a):
        cfg = getattr(c.window, "engine_config", None)
        if cfg is None:
            c.log("No config loaded.")
        else:
            c.log(f"Config: {cfg.width}x{cfg.height}, scene={cfg.start_scene}, vol={cfg.master_volume:.2f}")
            c._print_config()
        return True

    add("config", _config)

    add("bindings", lambda c, a: (c._bindings_command(), True)[1])
    add("bind", lambda c, a: (c._bind_command(a), True)[1])
    add("unbind", lambda c, a: (c._unbind_command(a), True)[1])

    def _sound(c, a):
        if not a:
            return False
        audio = getattr(c.window, "audio", None)
        if audio is not None:
            c.log(f"Playing sound '{a[0]}'")
            audio.play_sound(a[0])
        else:
            c.log("AudioManager not available")
        return True

    add("sound", _sound)

    def _music(c, a):
        if not a:
            return False
        audio = getattr(c.window, "audio", None)
        if audio is not None:
            c.log(f"Playing music '{a[0]}'")
            audio.play_music(a[0])
        else:
            c.log("AudioManager not available")
        return True

    add("music", _music)

    def _stopmusic(c, _a):
        audio = getattr(c.window, "audio", None)
        if audio is not None:
            c.log("Stopping music")
            audio.stop_music()
        else:
            c.log("AudioManager not available")
        return True

    add("stopmusic", _stopmusic)

    add("inventory", lambda c, a: (c._inventory_command(a), True)[1])
    add("inv", lambda c, a: (c._inventory_command(a), True)[1])
    add("equip", lambda c, a: (c._equip_command(a), True)[1])
    add("unequip", lambda c, a: (c._unequip_command(a), True)[1])
    add("set", lambda c, a: (c._handle_set(a), True)[1])

    def _save(c, a):
        if not a:
            c.log("Usage: save <slot_name> [--compact]")
            return True
        compact = "--compact" in a
        clean_args = [arg for arg in a if arg != "--compact"]
        if not clean_args:
            c.log("Usage: save <slot_name> [--compact]")
            return True
        c.window.save_manager.save_game(clean_args[0], compact=compact)
        return True

    add("save", _save)

    def _load(c, a):
        if not a:
            saves = c.window.save_manager.list_saves()
            if saves:
                c.log(f"Available saves: {', '.join(saves)}")
                c.log("Usage: load <slot_name>")
            else:
                c.log("No saves found. Usage: load <slot_name>")
            return True
        c.window.save_manager.load_game(a[0])
        return True

    add("load", _load)

    def _saveconfig(c, _a):
        c.log("Saving configuration to disk")
        c._save_config_to_disk()
        return True

    add("saveconfig", _saveconfig)

    entries.sort(key=lambda item: item[0])
    return dict(entries)


_DISPATCH = _dispatch_table()


def dispatch_command(controller: Any, cmd: str, args: list[str]) -> bool:
    handler = _DISPATCH.get(cmd)
    if handler is None:
        # Convenience: allow a tiny, explicit env toggle syntax for common debug flags.
        # Example: "mesh_shadows_trace=1" or "MESH_SHADOWS_TRACE=1"
        if not args and "=" in cmd:
            key, value = cmd.split("=", 1)
            key = str(key or "").strip().lower()
            value = str(value or "").strip()
            env_map = {
                "mesh_shadows_trace": "MESH_SHADOWS_TRACE",
                "mesh_shadows_fallback_draw": "MESH_SHADOWS_FALLBACK_DRAW",
            }
            env_key = env_map.get(key)
            if env_key is not None and value in {"0", "1"}:
                os.environ[env_key] = value
                logger = getattr(controller, "log", None)
                if callable(logger):
                    logger(f"[Lighting] {env_key}={value}")
                return True
        return False
    return bool(handler(controller, args))


def dispatch_keys() -> tuple[str, ...]:
    return tuple(_DISPATCH.keys())
