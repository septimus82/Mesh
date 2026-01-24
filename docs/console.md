# Dev Console

Command reference based on GameWindow help sections and runtime defaults.

## meta
- **help / ?** -- Show this help
- **save <slot> [--compact]** -- Save game state to a slot
- **load <slot>** -- Load game state from a slot
- **clear** -- Clear console scrollback
- **pause** -- Toggle paused state
- **strict_on** -- Enable strict exception mode (crash on error)
- **strict_off** -- Disable strict exception mode (log errors)
- **selftest** -- Run engine self-checks (behaviours/scenes/worlds)
- **flag [get|set|toggle]** -- Inspect or mutate global flags
- **counter [get|set|add]** -- Inspect or mutate global counters
- **encounter [reroll|overlay]** -- Debug encounter system
- **xp [get|add|set]** -- Inspect or mutate player xp/level
- **stats** -- Show derived player stats
- **gstate** -- Show chapter, main quest, and playtime
- **quest [list|start|complete]** -- Inspect or manipulate quest states
- **cutscene <id>** -- Start a cutscene by id
- **world [scenes|neighbors]** -- Inspect loaded world metadata
- **ai_bundle [dir]** -- Build full AI bundle (index, context, docs)
- **ai_job <path>** -- Apply an AI job JSON and reload scene
- **daynight [on|off]** -- Toggle day/night cycle
- **day_night [on|off]** -- Alias: toggle day/night cycle
- **time_of_day** -- Show current time-of-day hour
- **set_time_of_day <hour>** -- Set time-of-day hour
- **lighting [on|off]** -- Show or toggle lighting
- **lighting_limit [static|dynamic] [value|none]** -- View or set lighting caps

## scenes
- **reload** -- Reload the current scene
- **reload_scene [path]** -- Reload the current scene or a specific path
- **scene <path>** -- Load a different scene JSON
- **scene save [path]** -- Save current state to JSON (default: overwrite)
- **scene dump [path]** -- Dump raw scene state to JSON (debug)

## behaviours
- **behaviours** -- List registered behaviours
- **behaviour <name>** -- Show info for a behaviour
- **beh list [entity]** -- List runtime behaviour parameters
- **beh get <ref> <beh> <param>** -- Inspect a behaviour parameter
- **beh set <ref> <beh> <param> <value>** -- Update a behaviour parameter at runtime
- **reload_behaviours** -- Reload behaviour modules (run reload_scene afterwards)

## entities
- **entity** -- List all entities with indices
  *Examples:*
    - `entity`
    - `entity Player`
- **entity <i|name>** -- Show details for entity by index or name
  *Examples:*
    - `entity 0`
    - `entity Player`
- **entity set <ref> ...** -- Modify entity position, tag, or scale
  *Examples:*
    - `entity set 0 x 128`
    - `entity set Player pos 64 320`
- **entity beh list <ref>** -- List behaviours + config for an entity
- **entity beh set <ref> <beh> <field> <value>** -- Set per-entity behaviour config
- **entity beh reload <ref>** -- Rebuild behaviours for an entity
- **spawn <sprite> <x> <y>** -- Spawn a new entity at runtime
  *Examples:*
    - `spawn assets/coin.png 100 200`
- **spawn_like <ref> <x> <y>** -- Clone an existing entity at new coords
  *Examples:*
    - `spawn_like Player 200 350`

## collision
- **rules** -- List collision rules

## assets
- **assets** -- Show texture cache info
- **assets clear** -- Clear texture cache

## audio
- **sound <path>** -- Play a one-shot sound
- **music <path>** -- Play music (looped)
- **stopmusic** -- Stop current music

## config
- **config** -- Print current config values
- **bindings** -- List current input bindings
- **bind <action> <key>** -- Add a key binding
- **unbind <action> [key]** -- Remove one or all keys for an action
- **saveconfig** -- Save config to disk
- **set volume <0..1>** -- Set global volume scale
- **set master <0..1>** -- Set master volume
- **set music <0..1>** -- Set music volume
- **set sfx <0..1>** -- Set SFX volume
- **set fullscreen <on|off>** -- Toggle fullscreen
- **set vsync <on|off>** -- Toggle vsync
- **set show_fps <on|off>** -- Toggle FPS overlay
- **set debug_on_start <on|off>** -- Toggle debug on start

## inventory
- **inventory [list]** -- Show current inventory contents
- **inventory add <id> [amount]** -- Grant an item using items.json ids
- **inventory remove <id> [amount]** -- Remove an item from the shared inventory
- **inventory clear** -- Empty the shared inventory bucket
- **inventory show|hide|toggle** -- Control the inventory overlay visibility

## camera
- **camera** -- Inspect camera state or subcommands
  *Examples:*
    - `camera`
- **camera zoom <value>** -- Set the zoom target immediately
  *Examples:*
    - `camera zoom 1.2`
- **camera shake <duration> <amplitude> [freq] [falloff]** -- Trigger a temporary camera shake
  *Examples:*
    - `camera shake 0.35 12`
    - `camera shake 1.0 20 24 1.5`
- **camera stopshake** -- Clear any active camera shake
  *Examples:*
    - `camera stopshake`
- **camera areas** -- List configured camera areas
  *Examples:*
    - `camera areas`

## hotkeys
- **F1 / ` / Insert** -- Toggle console
- **Ctrl+F1** -- Toggle command palette (debug)
- **F2** -- Toggle capture mode (debug)
- **F3** -- Toggle debug mode and overlay
- **F4** -- Toggle editor mode
- **H** -- Toggle help overlay
- **V** -- Toggle variant picker
- **Q** -- Toggle quest log
- **TAB** -- Toggle inventory overlay
- **C** -- Toggle character panel
- **I** -- Toggle inspector panel (editor)
- **F5** -- Quick save (debug)
- **F6** -- Quick load (debug)
- **F8** -- Toggle encounter debug overlay
- **F9** -- Toggle paused state (debug: copy snippet when inspector is active)
- **F10** -- Toggle scene inspector overlay
- **F11** -- Toggle tile paint mode (debug)
- **F12** -- Toggle selection lock from hover (debug)
- **Esc** -- Toggle settings overlay
- **PgUp/PgDn/Home/End** -- Scroll console
- **Up/Down** -- Navigate console history
