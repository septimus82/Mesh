from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.console_controller import ConsoleController

def handle_clear(controller: Any, _args: list[str]) -> bool:
    controller.lines.clear()
    controller.scroll_offset = 0
    return True

def handle_pause(controller: Any, _args: list[str]) -> bool:
    # Accessing private method _toggle_paused_state as in original code
    new_state = controller.window._toggle_paused_state()
    controller.log(f"Paused = {new_state}")
    return True

def handle_strict_on(controller: Any, _args: list[str]) -> bool:
    controller.window.strict_mode = True
    controller.log("Strict exception mode ENABLED")
    return True

def handle_strict_off(controller: Any, _args: list[str]) -> bool:
    controller.window.strict_mode = False
    controller.log("Strict exception mode DISABLED")
    return True

def handle_selftest(controller: Any, _args: list[str]) -> bool:
    # Moved from ConsoleController._selftest_command
    from engine.self_test import SelfTestManager
    mgr = SelfTestManager(controller.window)
    results = mgr.run_all()
    for line in mgr.summary(results).splitlines():
        controller.log(line)
    return True

def handle_flag(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[Flag] No game state controller.")
        return True

    if not args:
        flags = getattr(getattr(gs, "state", None), "flags", {}) or {}
        if not flags:
            controller.log("[Flag] (no flags)")
            return True
        controller.log("[Flag] Flags:")
        for name, value in sorted(flags.items()):
            controller.log(f"  {name} = {bool(value)}")
        return True

    sub = args[0].lower()
    if sub == "get" and len(args) >= 2:
        name = args[1]
        value = gs.get_flag(name, False)
        controller.log(f"[Flag] {name} = {value}")
        return True
    if sub == "set" and len(args) >= 3:
        name = args[1]
        val_str = args[2].lower()
        value = val_str in ("1", "true", "yes", "on")
        gs.set_flag(name, value)
        controller.log(f"[Flag] {name} set to {value}")
        return True
    if sub == "toggle" and len(args) >= 2:
        name = args[1]
        value = gs.toggle_flag(name)
        controller.log(f"[Flag] {name} toggled to {value}")
        return True

    controller.log("[Flag] usage:")
    controller.log("  flag                 # list flags")
    controller.log("  flag get <name>")
    controller.log("  flag set <name> <true|false>")
    controller.log("  flag toggle <name>")
    return True

def handle_counter(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[Counter] No game state controller.")
        return True

    if not args:
        counters = getattr(getattr(gs, "state", None), "counters", {}) or {}
        if not counters:
            controller.log("[Counter] (no counters)")
            return True
        controller.log("[Counter] Counters:")
        for name, value in sorted(counters.items()):
            controller.log(f"  {name} = {value}")
        return True

    sub = args[0].lower()
    if sub == "get" and len(args) >= 2:
        name = args[1]
        value = gs.get_counter(name, 0)
        controller.log(f"[Counter] {name} = {value}")
        return True
    if sub == "set" and len(args) >= 3:
        name = args[1]
        try:
            value = float(args[2])
        except ValueError:
            controller.log("[Counter] set value must be numeric")
            return True
        gs.set_counter(name, value)
        controller.log(f"[Counter] {name} set to {value}")
        return True
    if sub == "add" and len(args) >= 3:
        name = args[1]
        try:
            delta = float(args[2])
        except ValueError:
            controller.log("[Counter] add delta must be numeric")
            return True
        new_value = gs.add_counter(name, delta)
        controller.log(f"[Counter] {name} = {new_value}")
        return True

    controller.log("[Counter] usage:")
    controller.log("  counter                  # list counters")
    controller.log("  counter get <name>")
    controller.log("  counter set <name> <value>")
    controller.log("  counter add <name> <delta>")
    return True

def handle_gstate(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[GState] No game state controller.")
        return True
    chapter = gs.get_chapter()
    main_quest = gs.get_main_quest()
    playtime = gs.get_playtime_seconds()
    controller.log(f"[GState] chapter={chapter} main_quest={main_quest} playtime={playtime:.1f}s")
    return True

def handle_quest(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    qm = getattr(gs, "quests", None) if gs is not None else None
    if qm is None:
        controller.log("[Quest] No quest manager.")
        return True

    if not args:
        quests = qm.get_all_quests()
        if not quests:
            controller.log("[Quest] (no quests)")
            return True
        controller.log("[Quest] Quests:")
        for q in quests:
            controller.log(f"  {q.id} [{q.state}] - {q.title}")
        return True

    sub = args[0].lower()
    if sub == "active":
        quests = qm.get_quests_by_state("active")
        if not quests:
            controller.log("[Quest] (no active quests)")
            return True
        controller.log("[Quest] Active quests:")
        for q in quests:
            controller.log(f"  {q.id} - {q.title}")
        return True
    if sub == "start" and len(args) >= 2:
        qm.start_quest(args[1])
        controller.log(f"[Quest] started {args[1]}")
        return True
    if sub == "complete" and len(args) >= 2:
        qm.complete_quest(args[1])
        controller.log(f"[Quest] completed {args[1]}")
        return True

    controller.log("[Quest] usage:")
    controller.log("  quest               # list all quests")
    controller.log("  quest active        # list active quests")
    controller.log("  quest start <id>")
    controller.log("  quest complete <id>")
    return True

def handle_world(controller: Any, args: list[str]) -> bool:
    wc = getattr(controller.window, "world_controller", None)
    gs = getattr(controller.window, "game_state_controller", None)
    if wc is None:
        controller.log("[World] No world data loaded.")
        return True
    if not args:
        meta = wc.export_metadata()
        current_key = gs.get_var("world_scene_key") if gs is not None else None
        controller.log(
            f"[World] id={meta['id']} start_scene={meta['start_scene']} start_spawn={meta['start_spawn']}"
        )
        controller.log(f"[World] scenes: {', '.join(meta['scene_keys'])}")
        controller.log(f"[World] current_scene_key={current_key}")
        return True
    sub = args[0].lower()
    if sub == "scenes":
        meta = wc.export_metadata()
        controller.log("[World] scenes:")
        for key in meta["scene_keys"]:
            label = wc.get_scene_label(key) or key
            controller.log(f"  {key}: {label}")
        return True
    if sub == "neighbors" and len(args) >= 2:
        key = args[1]
        neighbors = wc.get_neighbors(key)
        if not neighbors:
            controller.log(f"[World] no neighbors for {key}")
        else:
            controller.log(f"[World] neighbors of {key}: {', '.join(neighbors)}")
        return True
    controller.log("[World] usage:")
    controller.log("  world")
    controller.log("  world scenes")
    controller.log("  world neighbors <scene_key>")
    return True

def handle_cutscene(controller: Any, args: list[str]) -> bool:
    cutscene_controller = getattr(controller.window, "cutscene_controller", None)
    if cutscene_controller is None:
        controller.log("[Cutscene] controller not available")
        return True
    if not args:
        ids = ", ".join(cutscene_controller.cutscenes.keys()) if cutscene_controller.cutscenes else "<none>"
        controller.log("[Cutscene] usage: cutscene <id>")
        controller.log(f"[Cutscene] known: {ids}")
        return True
    cid = args[0]
    if cutscene_controller.play_cutscene(cid):
        controller.log(f"[Cutscene] started '{cid}'")
    else:
        controller.log(f"[Cutscene] failed to start '{cid}'")
    return True

def handle_xp(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[XP] no game state")
        return True
    if not args or args[0] == "get":
        stats = gs.get_player_stats()
        needed = max(
            1,
            int(
                getattr(controller.window.engine_config, "xp_base", 50)
                + getattr(controller.window.engine_config, "xp_per_level", 25) * (stats["level"] - 1)
            ),
        )
        controller.log(f"[XP] level={stats['level']} xp={stats['xp']}/{needed}")
        return True
    sub = args[0]
    if sub == "add" and len(args) >= 2:
        try:
            amount = int(args[1])
        except ValueError:
            controller.log("[XP] add requires integer amount")
            return True
        result = gs.add_xp(amount)
        controller.log(f"[XP] added {amount}, level={result['level']} xp={result['xp']}")
        return True
    if sub == "set" and len(args) >= 2:
        try:
            value = int(args[1])
        except ValueError:
            controller.log("[XP] set requires integer value")
            return True
        gs.set_xp(value)
        controller.log(f"[XP] xp set to {value}")
        return True
    if sub == "level" and len(args) >= 2:
        try:
            lvl = int(args[1])
        except ValueError:
            controller.log("[XP] level requires integer value")
            return True
        gs.set_level(lvl)
        controller.log(f"[XP] level set to {lvl}")
        return True
    controller.log("[XP] usage: xp [get|add <n>|set <n>|level <n>]")
    return True

def handle_stats(controller: Any, args: list[str]) -> bool:
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[Stats] no game state")
        return True
    stats = gs.get_player_stats()
    controller.log(
        f"[Stats] level={stats['level']} hp={stats['max_hp']} atk={stats['attack']} def={stats['defense']} spd={stats['speed']:.2f}"
    )
    return True

def handle_encounter(controller: Any, args: list[str]) -> bool:
    # Profile check
    profile = getattr(controller.window.engine_config, "profile", "dev")
    if profile != "dev":
        controller.log("Error: Encounter commands are dev-only (profile != dev).")
        return True

    if not args:
        controller.log("Usage: encounter [reroll|overlay|show|set-budget|set-difficulty|set-layout]")
        return True

    sub = args[0].lower()

    if sub == "reroll":
        seed = None
        if len(args) > 1:
            try:
                seed = int(args[1])
            except ValueError:
                controller.log("Invalid seed")
                return True

        settings = controller.window.scene_controller.scene_settings
        if seed is None:
            # Deterministic fallback if no seed provided
            # Always use hash of scene ID to ensure stability
            scene_id = controller.window.scene_controller.current_scene_id or "unknown"
            # Simple deterministic hash
            seed = sum(ord(c) for c in scene_id) * 12345 % 1000000

        settings["encounter_seed"] = seed
        controller.log(f"Rerolling encounters with seed {seed}...")
        if hasattr(controller.window, "request_scene_reload"):
            controller.window.request_scene_reload()
        else:
            controller.window.reload_scene()
        return True

    if sub == "overlay":
        current = getattr(controller.window, "encounter_debug_overlay", False)
        controller.window.encounter_debug_overlay = not current
        state = "enabled" if not current else "disabled"
        controller.log(f"Encounter debug overlay {state}")
        return True

    if sub == "show":
        from engine.encounter_debug import get_encounter_debug_lines
        lines = get_encounter_debug_lines(controller.window.scene_controller)
        for line in lines:
            controller.log(line)
        return True

    if sub == "set-budget":
        if len(args) < 2:
            controller.log("Usage: encounter set-budget <amount>")
            return True
        try:
            amount = int(args[1])
            controller.window.scene_controller.scene_settings["encounter_budget"] = amount
            controller.log(f"Encounter budget set to {amount}")
            if hasattr(controller.window, "request_scene_reload"):
                controller.window.request_scene_reload()
            else:
                controller.window.reload_scene()
        except ValueError:
            controller.log("Invalid budget amount")
        return True

    if sub == "set-difficulty":
        if len(args) < 2:
            controller.log("Usage: encounter set-difficulty <profile>")
            return True
        profile = args[1]
        controller.window.scene_controller.scene_settings["encounter_budget_profile"] = profile
        controller.log(f"Encounter difficulty set to {profile}")
        if hasattr(controller.window, "request_scene_reload"):
            controller.window.request_scene_reload()
        else:
            controller.window.reload_scene()
        return True

    if sub == "set-layout":
        if len(args) < 2:
            controller.log("Usage: encounter set-layout <layout>")
            return True
        layout = args[1]
        controller.window.scene_controller.scene_settings["encounter_layout"] = layout
        controller.log(f"Encounter layout set to {layout}")
        if hasattr(controller.window, "request_scene_reload"):
            controller.window.request_scene_reload()
        else:
            controller.window.reload_scene()
        return True

    controller.log("Unknown encounter command")
    return True
