# S1-0 part D: can a developer actually make a game? Real workflows, end to end

Checked against **`9d3580b9`** (`redesign/visual-editor`, after #633), on top of parts A–C (`7ebae9bc`). This is investigation only: no production code or tests changed. #622 is treated as still present (its fix, PR #635, is approved but not merged).

**Method** (same rules as parts A–C):
- Every script ran on its own, one Python process at a time, with `py -3.13` and `PYTHONPATH=<this worktree>`. Each printed `engine from Mesh-S10/engine/__init__.py`.
- The chain script's game phases are child processes started one after another while the parent waits. The multiplayer script runs the real server as a child for a few seconds.
- Projects are created by `mesh new` (mesh_cli `main`, in-process) in a fresh temp folder that the script deletes afterwards.
- They are changed through Studio's project model (`engine.studio_project.Project`, under Studio's ownership lock), `mesh author apply` (`engine.authoring_session.apply`) and MCP `apply_ops` (`engine.mcp_server.tools`). No scene file is edited by hand, except the one documented workaround (D-4).
- Projects are played through **their own `main.py`**, with `GameWindow.run` replaced by a driver. The window is hidden, muted and never activated (`tooling.hidden_windows.no_activate`, `visible=False`).
- The driver uses only the game's own input path: `on_key_press` / `on_key_release` / `on_update`, dispatched to the window as pyglet's loop does. That covers walking, E to interact, SPACE to attack, F5 to quicksave and F9 to quickload. No OS input is used.
- The export is `mesh export build`. The exported game is then run from its own folder with its **own bundled engine**: PYTHONPATH is removed, and APPDATA / XDG_DATA_HOME point to a temp folder so that nothing touches the real per-user save folder.
- Output below is trimmed to the lines that matter. Temp paths are shortened to `<tmp>`.
- **Severity scale and classes:** as in parts A–C.

**No P0 found.** Five new P1s, all confirmed through the real runtime:
- **NEW-16:** Health starts at 1 HP unless `hp` is written, and the player ignores its stats. This hits the shipped campaign and every Studio "Has health".
- **NEW-17:** no project Mesh creates has an item list, so every item feature fails.
- **NEW-18:** campaign exits gated on a flag appear only after leaving and re-entering the room (65 exits in 63 shipped scenes).
- **NEW-19:** Studio's Shopkeeper can never be opened.
- **NEW-20 to NEW-22:** P2/P3.

### Evidence scripts (`docs/s1/evidence/`)

| Script | What it drives | Exit at tip |
|---|---|---|
| `e2e_creation_to_export_chain.py` | The whole chain: `mesh new` → Studio imports and rooms → `mesh author apply` → quests (CLI and MCP) → play `main.py` → F5 → reopen → F9 → `mesh export build` → exported game play / save / reopen / load | 1 |
| `scan_project_templates.py` | Every shipped template: `mesh new --template T`, `mesh doctor`, then its `main.py`: start room, player, walk, draw | 1 (2 templates) |
| `repro_core_regions_gates.py` | Act1_Chapter2_Ambush end to end (switch → gate → exit), then all 18 shipped DoorLock scenes: locked / walk-round / unlocked | 1 |
| `repro_health_starts_at_one.py` | Health/Combat as Studio writes them, as shipped scenes write them, and in the shipped Ambush and cellar | 1 |
| `repro_shopkeeper_never_opens.py` | A Studio-authored Shopkeeper and the three shipped merchants, opened through the game's input | 1 |
| `e2e_multiplayer_characters.py` | `mesh_net.characters` CLI, then progress, then the real `mesh_net.server --expedition --store`, then two socket clients: restore, drop/resume, the one-session rule | 0 |

Each script makes and removes its own temp folder, contains no personal paths, and changes nothing outside that temp folder.

---

## 1. Workflow matrix

**Status values:** works / **FAILS** / workaround (works only with a step a creator wouldn't know).

**"Real-path tests"** means tests that drive the step through the same entry point with real objects (not MagicMock). Coverage was found by grep and reading, so it is approximate.

### W1: Create and edit a project in Studio

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| `mesh new` (starter, the default) | works | chain A: `exit 0` | `test_cli_new_project_command_contract.py`; installed wheel: `installed_product_check` via `test_wheel_bundles_engine_data.py` (blank, hd2d_rpg) | — |
| Every shipped template creates *and starts* | **FAILS** for `lighting_playground`, `demo_slice` | `scan_project_templates.py` (§3) | `test_project_templates_contract.py:40-73` asserts the broken file shape and never starts the game | **NEW-21** |
| Add a 2D room and an HD-2D room (Studio model), save under the Studio lock | works | chain B: `kit installed=True, wrote [glade.json, shed.json, worlds/main.json]` | Studio project tests (F15, S4) | — |
| Change rooms through `mesh author apply` (48 changes: walls, NPC, conversation, choices, behaviours, doors, structure, shared player) | works (the write itself) | chain C: `48 changes, wrote [...start.json, assets/prefabs.json]` | 25 test files use `authoring_session` | what was written is wrong for Health (**NEW-16**) |
| MCP `list_scenes` sees the project's rooms | **FAILS** (returns `[]`) | chain D: `MCP list_scenes on this project: [] (its rooms: ['glade', 'shed', 'start'])` | none on a `mesh new` layout | **NEW-22** (P3) |

### W2: Import and place artwork and HD-2D assets

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| Import a picture, a tileset, a sound and a Blender .glb (Studio model) | works | chain B: `assets/sprites/merchant_pic.png, assets/tilesets/my_tiles.json, assets/ambience/hum.wav, assets/models/my_crate.glb` | 11 test files name `import_sprite`/`import_tileset`/`import_sound`/`import_model` | — |
| Place the imported picture, sound emitter and model (`set_picture`, `set_sound_emitter`, `place_structure`) | works | chain C (written), E (Merchant built with SoundEmitter; Glade drawn with the model) | HD-2D structure tests | — |
| Reimport the model from a new export: placed copies kept, provenance updated | works | chain B2: `sha changed: True \| placed: ['assets/models/my_crate.glb']` | `hd2d` catalog reimport tests | — |
| Provenance contents | KNOWN LIMITATION (P3) | chain B: the catalogue keeps the creator's **absolute** source path (`source.file`). The export's copy of the catalogue does not hold it (`exported catalog holds the creator's absolute source path: False`) | — | — |

### W3: Implement interactions, quests, dialogue, combat and shops

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| Dialogue with a "once" reward choice: paid once within a visit | works | chain E: `gold_after_first 25.0, gold_after_second_talk 25.0` | none through the game's keys | — |
| …not paid again after re-entry | **FAILS** | chain E: `once_reward_not_repaid_after_reentry: gold 55.0` (25 + 5 drop + 25 again) | none | **#620** |
| Quest authoring on a fresh project | **workaround** | chain D: MCP `add_quest_definition` → `File not found: <tmp>\chain\assets\data\quests.json`; `mesh new-quest NAME` → exit 1; with `--target` → a list-rooted file the runtime ignores, after which MCP refuses (`quests root must be an object`); works only after hand-writing `{"quests": []}` | `test_ai_ops_world_quest.py:52-55` pre-writes `quests.json`; `test_cli_migration_pass7.py:23` checks only `--help` | **NEW-20** |
| Quest: start on a dialogue choice, stage on `door_unlocked`, stage on a flag, reward | works | chain E: `active/open_gate` → `enter_vault` → `completed`, `vault_badge 1.0` | quest tests use the lightweight manager (part B §1.3) | — |
| Pick up an item ("Can be picked up") | **FAILS** | chain E: `pickup_item: potions 0, still_there true`; log `Interaction behaviour PickupCollectible failed: FileNotFoundError('Item database not found at <tmp>\chain\assets\data\items.json')` | none in a created project | **NEW-17** |
| Shop ("Shopkeeper") opens on E | **FAILS** | chain E: the Vendor isn't even built (`Failed to instantiate 'Vendor': Item database not found`). With an item list (checkout), `repro_shopkeeper_never_opens.py`: `E -> shop open: False` | none | **NEW-17** and **NEW-19** |
| Shop purchase | **FAILS** (shop never opens) | chain E: `potions 0, gold 25.0` | #619/#625 tests call `handle_buy_request` directly | **NEW-19** |
| Enemy: Health, EnemyAI, DropTable gold, GrantExperience; the player attacks with SPACE | works, but wrong numbers | chain E: `attacks: 1 … gold: 30.0, player_hp: 1.0`. The enemy authored with "Health" 3 died in one hit of 1 damage; the player authored with "Health" 50 has 1 HP | `test_combat.py` builds Health/Combat directly; `_b01_arena.py:23,28` always writes `hp` | **NEW-16** |
| Button ("Button") unlocks the gate ("Locked until an event") | works | chain E: `lever_unlocks_gate` | — | — |
| Walk through the unlocked gate | **FAILS** | chain E: `blocked at (422.5, 246.9), gate_in_solid_sprites true` | none | **#639** |
| Treasure chest pays out | **FAILS** | chain E (gate removed from `solid_sprites` to reach it): `looted true, gold 30.0 -> 30.0` | none | **#636** |
| Zone (Studio zone tool = TriggerVolume) sets a flag | works | chain E: `reached_vault` set, quest completed | — | (#640 affects the other zone, TriggerZone) |
| Doors to a 2D room and an HD-2D room and back; the HD-2D room is walkable and draws | works | chain E: `room glade, hd2d true, hd2d_error None`, `moved 75.0`, back in `start` | `test_n1_player_hp_across_rooms.py`, HD-2D GPU lane | — |

### W4: Play the game and progress through its content

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| A created project's `main.py` starts, the player walks, a frame draws | works for 5 of 7 templates | `scan_project_templates.py` | installed-export H7 (adventure, hd2d_rpg) | **NEW-21** |
| Shipped campaign: Act1_Chapter2_Ambush, switch → gate → exit | **workaround** (passable only by walking round the gate, then leaving and re-entering) | `repro_core_regions_gates.py` (§3) | none | **#639**, **NEW-18** |
| Shipped campaign: survive combat | **FAILS** (the player has 1/1 HP and deals 1 damage; the raiders have 64–70 HP) | `repro_health_starts_at_one.py`: `Player: hp 1.0 / max_hp 1.0`, `Combat damage 1.0 (stats attack 5.0)` | none | **NEW-16** |
| Shipped shops (Ashen, Hollow Grove) | **FAILS**; Ridge Outpost works | `repro_shopkeeper_never_opens.py` | none | **NEW-19** |
| Room memory: a defeated enemy stays gone after re-entry and after load | works | chain E/F: `wolf_present False` both times | `test_state_lifecycle.py` | — |
| Gate and button state on re-entry | **FAILS** | chain: `gate_locked: true` after coming back from the Glade | — | **#639** |

### W5: Save, exit, reopen and continue

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| F5 quicksave in the game (`main.py`) | works | chain E: `slots: ['quicksave']` | save tests (F3), H7 | — |
| New process, F9 quickload: room, gold, flags, inventory, room memory, quest | works | chain F: all `ok` (`start`, `55.0`, `True`, `True`, `0`, `False`, `completed`) | F3, B-01/B-09 | — |
| Gate stays unlocked after load | **FAILS** | chain F: `gate locked after load: True` | — | **#639** |
| Once-only dialogue and chest after load | **FAILS** (the instance state is not saved) | part A/B repros; in the chain the #620 overpayment is carried in the save | — | **#620**, **#636** |
| Save folder for a created project | works on this path | `main.py` chdirs, so `saves/` is the project's own (part A: #623 does not hit `main.py`, Studio or exports) | — | #623 only on `run_game(project_root=)` / the legacy project switch |

### W6: Export a standalone playable build

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| `mesh export build --deterministic` | works | chain G: `exit 0`; `OK (1083 files, ~10.9 MB)` | `test_export_bundle.py`, `test_export_bundle_replacement.py`, H7 | — |
| The export carries the quests, imported picture, sound, model and HD-2D room | works | chain G: all `True` | `bundle_problems` in H7 | — |
| The exported `main.py` runs on its own bundled engine, walks, gives the dialogue reward | works | chain G: `engine: <tmp>\chain\dist\bundle\engine\__init__.py`, `moved 75.0`, `gold 25.0` | H7 (`installed_product_check.GAME`) | — |
| Exported: F5, new process, F9 restores | works | chain G: `slots ['quicksave']; gold 25.0 -> 25.0` | H7 resume mode | — |
| Saves go to the per-player folder; nothing is written into the bundle | works | chain G: `<player data>\MeshMind Studios\chain-<id>\saves`; `writes nothing into its own folder: True` | H9 tests | — |
| Dev saves (project `saves/`) visible to the export | no, by design | chain G: `dev saves visible to the export: []` | — | KNOWN LIMITATION (H9 design) |
| An export runs without Mesh's dependencies installed | no | `installed_product_check` docstring: "An export needs those dependencies (arcade, pillow, jsonschema): it is not self-contained" | H7 | KNOWN LIMITATION |

### W7: A basic multiplayer session with preserved character progress

| Step | Status | Evidence | Real-path tests | Blocking issue |
|---|---|---|---|---|
| `python -m mesh_net.characters new-store` / `create NAME --key-file` | works | `1. admin CLI exit codes: [0, 0, 0]` | `test_mesh_net_characters.py::test_the_admin_command_never_prints_a_key` | — |
| Earn progress (party, Layer 2, guardian, loot) | works (driven by the tests' `Driver`, which teleports; not the client path) | `2. earned: {'Ada': ({'guardian_sigil': 1}, ['ruins_layer_2_completed']), 'Bo': (...)}` | `test_mesh_net_characters.py` | — |
| The real host `python -m mesh_net.server --expedition --store`; two socket clients rejoin with their key files after the restart | works | `3. Ada … items=[['guardian_sigil', 1]] unlocks=['ruins_layer_2_completed'] -> kept` (and Bo) | `test_characters_survive_a_full_server_restart_over_sockets` (in-process server) | — |
| A dropped connection resumes as the same player in the same room | works | `4. Ada rejoined: player 1 -> 1, room same: True, at [203.0, 256.0] -> [203.0, 256.0] -> resumed` | `test_mesh_net_resume.py` | — |
| A second session for an online character is refused | works | `4. a second session for Bo while online: character_in_use` | `test_one_session_per_character` | — |
| Multiplayer with **the creator's own project** | not possible | `mesh_net.server` hosts only its packaged scenes (`--coop`: `mesh_net/coop`, `--expedition`: `mesh_net/expedition`; `server.py:313-386`). No option takes a project. The M4 demo world needs `tooling/` (part C D5) | — | KNOWN LIMITATION (prototype) |

---

## 2. The end-to-end chain: does creation-to-play compose?

**Partly.** The chain was: `mesh new` → Studio imports and rooms → `mesh author apply` → quests → play → save → reopen → export → exported play and save/load.

**The plumbing composes:**
- project creation;
- Studio's project model, imports, reimport and HD-2D room;
- the authoring transaction;
- room transitions, including into and out of an HD-2D room;
- room memory;
- quicksave/quickload across processes;
- the export;
- the exported game, which runs on its own engine and saves per player.

**The gameplay a creator authors does not.** Of the elements the brief listed, these break on the real path:

| Element | Outcome in the chain | Cause |
|---|---|---|
| Door to another room | works | — |
| NPC with dialogue and a once-only reward | paid again after re-entry (and from saves) | #620 |
| Quest | works, **but only after hand-writing `{"quests": []}`**; no Studio or `mesh author` operation exists | NEW-20 |
| Shop | never opens. Without an item list its Vendor isn't even built | NEW-17, NEW-19 |
| Chest | reports looted, grants nothing | #636 |
| Pickup (added) | raises inside the interaction; the item stays | NEW-17 |
| Enemy | dies and drops gold, **but every "Has health" starts at 1 HP** (the creator's 3 HP enemy and 50 HP player both had 1) | NEW-16 |
| Lever-gate puzzle | the button unlocks the gate, but the gate still blocks; it is locked again on re-entry and on load | #639 |
| HD-2D room | works (enter, walk, draw, return) | — |
| Save → reopen → load | works for gold, flags, quests, inventory and room memory; loses the gate | #639 |
| Export → exported build starts, plays, saves, reloads | works. It uses its own per-player save folder, so the dev save is not carried over (by design) | — |

**Where earlier defects break the chain:**
- **#639** cuts it in two: everything behind the gate (here the chest and the quest's last stage) can't be reached without a code change. The chain only went on by removing the gate from `solid_sprites` itself, as a stand-in for the fix.
- **#636** then pays nothing.
- **#620** makes the reward farmable, and the overpayment is saved.
- **#640** does not hit this chain: Studio's zone tool writes TriggerVolume, not TriggerZone. It is masked in the shipped Ambush too, because its SetGameStateOnEvent listens for `entered_zone` filtered by zone name and has `once`/`forbid_flags`.
- **#623** does not hit it: `main.py` chdirs into the project.
- **#642:** no cutscene was authored here. Part B's repro shows that one MCP cutscene edit stops the project starting at all.

---

## 3. Are the shipped chapters and templates impassable?

### Act1_Chapter2_Ambush (`repro_core_regions_gates.py`, exit 1)

```
Ambush: player at (120.0, 300.0), switch at (360.0, 300.0), door at (460.0, 300.0) (64x64, solid=True, locked=True)
  walked to the switch: arrived; pressed E -> door locked: False
  straight east along the lane to ToRuinedGateFromAmbush: blocked at (396, 300)
  around the gate (up, east, back to the lane and on to the exit): ['arrived', 'arrived', 'arrived']
  pressed E where the exit should be: still in Act1_Chapter2_Ambush.json | act1_ch2_ambush_cleared=True | exit door built: False
  workaround: back round the gate to ReturnToChapter2Camp: ['arrived', 'arrived', 'arrived, then E -> Act1_Chapter2_Camp.json']
  from the Camp, ToChapter2Ambush: arrived, then E -> Act1_Chapter2_Ambush.json
  re-entered the Ambush: exit built now: True | gate locked again: True
  round the gate once more and use the exit: ['arrived', 'arrived'] arrived, then E -> Act1_Chapter2_RuinedGate.json
  => Act1_Chapter2_Ambush impassable: False (now in Act1_Chapter2_RuinedGate.json)
```

**Not impassable, but not passable as designed.** The player was made invulnerable for this probe; without that, NEW-16 gives the player 1 HP against three raiders.
- The unlocked gate blocks the lane (#639).
- The scene has **no walls**, so the gate is a lone 64×64 sprite the player walks round.
- The objective flag is set by the clear zone, and the toast says "Gate unlocked". But the exit (`require_flags: act1_ch2_ambush_cleared`) **does not appear until the room is left and re-entered** (NEW-18).

### All 18 shipped DoorLock scenes (same script)

```
Act1_Chapter3_Archive.json: solid=True | locked: straight=blocked at (496, 300), around=arrived | unlocked=True: straight=blocked at (496, 308)
Act1_Chapter4_Bastion.json: solid=True | locked: straight=blocked at (396, 300), around=arrived | unlocked=True: straight=blocked at (396, 308)
Act1_Chapter5_Gauntlet.json: solid=True | locked: ... around=arrived | unlocked=True: straight=blocked at (406, 308)
Ridge Outpost_dungeon.json (+ variants b, c, d, f, g, h, i, k), Hollowmere_outskirts_variant_k/n: the same pattern
Ashen_dungeon.json, Hollow Grove_dungeon.json, preset_test_dungeon.json: solid=False (the gate never blocked)
```

- **All 15 solid gates still block after unlocking (#639).**
- **14 of the 15 can be walked round while still locked.** None of these scenes has a collision layer (static scan: `walls: False` for every core_regions DoorLock scene), so every switch puzzle is optional.
- The one exception in the generic probe (Ambush) is only because a crate stands on the probe's detour line; the Ambush walk above goes round it.
- Classification: CONFIRMED, P2 content defect. File it with #639 or as a content follow-up. The fix is content: walls or a tilemap around each gate.
- **No shipped chapter is strictly impassable.** But the campaign's intended flow is broken in three places: the gate (#639), the exit (NEW-18) and the player's health (NEW-16).

### Templates (`scan_project_templates.py`, exit 1)

```
blank                launcher=True  new=0 doctor=0 data={'items.json': False, 'quests.json': False} play={... 'player': True, 'moved': 50.0, 'drew': True}
adventure            launcher=True  new=0 doctor=0 data={'items.json': False, 'quests.json': False} play={... 'player': True, 'moved': 50.0, 'drew': True}
starter              launcher=False new=0 doctor=0 data={'items.json': False, 'quests.json': False} play={... 'player': True, 'moved': 50.0, 'drew': True}
hd2d_rpg             launcher=True  new=0 doctor=0 data={'items.json': False, 'quests.json': False} play={... 'player': True, 'hd2d': True, 'moved': 50.0}
monster              launcher=False new=0 doctor=0 data={'items.json': False, 'quests.json': False} play={... 'player': True, 'moved': 50.0, 'drew': True}
lighting_playground  launcher=False new=0 doctor=1 ... play={'crashed': '... SchemaValidationError: ... Additional properties are not allowed (\'format_version\', \'scene_id\', \'world_ambient_light\' were unexpected)'}
demo_slice           launcher=False new=0 doctor=1 ... play={'crashed': '... SchemaValidationError: ... (\'format_version\', \'scene_id\' were unexpected)'}
```

- The three launcher templates and the starter/monster templates start and walk.
- **`lighting_playground` and `demo_slice` create projects that cannot start** (NEW-21). `mesh new` reports success; only `mesh doctor` notices.
- **No template ships an item list or a quest file** (NEW-17, NEW-20).

---

## 4. New confirmed defects (issue-ready)

Numbering continues from part C (NEW-15). None duplicates #612, #620–#624, #627, #631, #632 or #636–#650.

### NEW-16 (P1): a Health whose `hp` isn't written starts at 1 HP, and the player's Health and Combat ignore its level stats

**Title:** Scene behaviours are built with every default filled in, so Health's "hp not given → start full" and the player's stats never apply. Studio's "Has health" starts at 1 HP, as do the shipped campaign's players.

**Severity:** P1. Wrong outcome on Studio's picker and on shipped content, silently:
- the campaign's player has 1/1 HP and deals 1 damage against 64–70 HP raiders;
- a creator's "Health 50" enemy dies in one hit.

**Reachability:**
- every scene entity with Health and no `hp` key: **102 of 154 shipped Health configs**, including every core_regions chapter Player (`Health` with no config) and `scenes/cellar.json` Rat1 (`{"max_hp": 10}`);
- every Health added through Studio's picker, `mesh author` or MCP `add_behaviour`. The picker shows "Health" (max_hp) first; "Starts with" (hp) sits under More and is written as 1;
- every player Combat without a `damage` key (the stats' `attack` is ignored).

**Repro:** `docs/s1/evidence/repro_health_starts_at_one.py` (exit 1):

```
1. written by add_behaviour + max_hp=50: {'hero': {'max_hp': 50.0, 'hp': 1.0, 'invulnerable': False}, 'wolf': {...same}}
   the player's stats say max_hp: 30.0 | attack: 5.0
1. Hero: hp 1.0 / max_hp 50.0 (player)
1. Wolf: hp 1.0 / max_hp 50.0
2. Hero: Combat damage 1.0 (stats attack 5.0; 'damage' explicit: True)
2. Hero: hp 1.0 / max_hp 1.0 (player)
2. Bear: hp 1.0 / max_hp 50.0                          <- hand-written {"max_hp": 50}, no hp
3. Player: hp 1.0 / max_hp 1.0 (player)                <- shipped Act1_Chapter2_Ambush
3. Act1Ch2Raider: hp 70.0 / max_hp 70.0
3. Rat1: hp 1.0 / max_hp 10.0                          <- shipped scenes/cellar.json
3. shipped Health configs: 154, without an 'hp': 102
DEFECT REPRODUCED
```

The chain shows the same: `Wolf's authored Health after add_behaviour + max_hp=3: {'hp': 1.0, ...}` and `enemy_defeated: attacks 1 … player_hp 1.0`.

**Root cause:**
- `engine/scene_controller_parts/entity_factory.py:224-229` builds behaviours through `engine/behaviours/registry.py:create_behaviour` (:202). That calls `normalize_config(..., fill_defaults=True)` (:230). For every declared field that is missing, it inserts the default (`registry.py:105-108`).
- `Behaviour._merge_param_config` (`behaviours/base.py:211-216`) then marks every field as explicit.
- `engine/behaviours/health.py:85-90` takes max_hp from the player's stats only when the config has none, and sets `hp = max_hp` only `if "hp" not in self._explicit_params`. Both conditions are now always false, so `hp` and `max_hp` keep the declared default of 1.0 (`health.py:43-47`).
- The same dead branch is in `combat.py:100` (player damage from stats), `camera_follow.py:120,129` and `light_source.py:143`.
- Separately, `project_ops.add_behaviour` (`project_ops.py:352-354`) writes every default into the file. A Studio-authored Health therefore carries an explicit `hp: 1.0` even after the runtime is fixed.
- Both have been there since the initial import (`56007013`).

**Missed by tests:**
- `tests/test_combat.py:75,97,118,142` construct `Health(...)` / `Combat(...)` directly, not through `create_behaviour`, so `_explicit_params` holds only the keyword arguments given.
- The real-window arena (`tests/_b01_arena.py:23,28`) always writes `hp`.
- No test loads a scene entity whose Health lacks `hp` and checks its HP.

**Bounded fix (one PR):**
1. In the factory path, build with `fill_defaults=False`, or have `normalize_config` return the set of keys actually provided and pass it on. Then `_explicit_params` means "written by the author" again. Check every behaviour that reads `_explicit_params` (the four above).
2. In `project_ops.add_behaviour`, don't write defaults for fields whose meaning is "derived when absent": Health `hp`, Combat `damage` on the player. Simplest: write only what the picker's basics need, or write `hp` equal to `max_hp` and update it with `max_hp` until the creator sets "Starts with".
3. Old saves are unaffected (Health's `saveable_state` carries hp/max_hp).

**Regression requirements (real hidden window, scenes loaded by the real factory):**
- `{"max_hp": 50}` with no hp starts at 50;
- a player with Health and no config gets the stats' max_hp; with Combat and no damage, the stats' attack;
- an explicit `hp: 10, max_hp: 50` keeps 10;
- a Studio `add_behaviour` + "Health" 50 starts at 50;
- the shipped Ambush player starts at the stats' max_hp;
- mutation proof: restoring `fill_defaults=True` in the factory fails the tests.

### NEW-17 (P1): no project Mesh creates has an item list, so every item feature fails in it

**Title:** New projects (all 7 templates; `mesh new`, the launcher, Studio) have no `assets/data/items.json`. The item database raises FileNotFoundError, so pickups, shopkeepers, item drops and chest items fail, and Studio has no way to create the list.

**Severity:** P1. Studio's picker offers "Can be picked up", "Shopkeeper", "Drops items when defeated" and "Treasure chest" (item). None can work in any project made by Mesh. The failure is a log line and nothing on screen. Pickups raise inside the interaction (it is caught and logged), and a Shopkeeper silently loses its Vendor.

**Reachability:**
- every created project (`scan_project_templates.py`: `items.json: False` for all 7);
- Studio Play (`mesh edit` chdirs into the project: `game_launch.py:41-42`);
- `python main.py`, `mesh play`, exports.

It is masked in the engine checkout, whose own `assets/data/items.json` sits in the CWD (so the repo's scenes and tests work). The only item editor is the legacy editor's (`engine/editor/item_editor_model.py`, #347, off the normal path).

**Repro:** `docs/s1/evidence/e2e_creation_to_export_chain.py` (step E). A starter project with a Studio-authored potion pickup and a Shopkeeper:

```
[FAIL] E pickup_item: {"walk": "arrived", "potions": 0, "still_there": true}
[FAIL] E shop_opens_on_interact: {"walk": "arrived", "merchant_behaviours": ["SoundEmitter"]}
log: [Mesh][Behaviour] ERROR: Failed to instantiate 'Vendor': Item database not found at <tmp>\chain\assets\data\items.json
log: ERROR:engine.game_state_controller:[Mesh][GameState] ERROR loading item database for equipment bonuses: Item database not found ...
log: WARNING:engine.interaction:Interaction behaviour PickupCollectible failed: FileNotFoundError('Item database not found at <tmp>\chain\assets\data\items.json')
```

**Root cause:**
- `engine/inventory.py:45-49`: `ItemDatabase.load` reads `<CWD>/assets/data/items.json` and raises when it is missing.
- `Inventory._max_stack` (`inventory.py:104`) calls it on every `can_add` / `add_item`, so every grant path raises. That covers PickupCollectible, DropTable item drops (`drop_table.py:113`), InventoryHolder, the Vendor constructor (`vendor.py:59`) and equipment bonuses (`game_state_controller.py:257,313`).
- No template or scaffold writes the file (`engine/project_templates.py`, `engine/project_scaffold.py`). `pyproject.toml` doesn't ship the engine's list either.

**Missed by tests:** item tests run from the checkout, whose CWD has `assets/data/items.json` (`test_inventory.py`, the #619/#625 vendor tests). No test grants an item in a `mesh new` project.

**Bounded fix:**
1. The scaffold writes a small starter `assets/data/items.json` (for example a healing potion and a key), with an allow-listed copy in the wheel's data-files if it comes from the engine.
2. `load_item_database` returns an empty database (and logs once) when the file is missing, instead of raising. Unknown ids are then refused with the existing "unknown item" messages (#619 path), and the game never raises from an interaction.
3. Later, give Studio (or `mesh author`) an item operation. Until then, document that items live in `assets/data/items.json`.

**Regression requirements:**
- `mesh new` (each launcher template), then a pickup and a shop purchase through the real window: they work;
- a project with the file deleted: the pickup is refused with a message, nothing raises, the Vendor is still built;
- mutation proof: removing the scaffold's file fails the first test.

### NEW-18 (P1): exits gated on a flag appear only when the room is built, so 65 campaign exits stay missing after their objective

**Title:** Entity-level `require_flags` / `forbid_flags` are applied only when a room is loaded (gated entities are not spawned). A shipped exit whose flag is set in the same room never appears until the player leaves and comes back.

**Severity:** P1. Wrong outcome on shipped content: **65 exits in 63 core_regions scenes**, the main Act 1–3 progression. Each exit's flag is set in its own room. The player completes the objective, is told so (Ambush: "Objective complete: Ambush cleared. Gate unlocked."), and finds no exit.

**Reachability:**
- static scan of `packs/` and `scenes/` for entities whose `require_flags` names a flag that something in the same scene sets: 79 entities in 63 scenes, 65 of them SceneTransitions (Act1_Chapter2_Ambush `ToRuinedGateFromAmbush`, Act1_Chapter3_Archive `ToChapter3Courtyard`, …, Act3_Chapter3_Outcome `ToAct3Chapter4Entry`);
- Creator Mode's door plan writes entity `require_flags` too (`creator_door_plan.py:29,102`; code read, not run).

Studio's "Show only when flags allow" uses ConditionalActivator, which re-evaluates at runtime and is not affected.

**Repro:** `docs/s1/evidence/repro_core_regions_gates.py` (Ambush part, §3):
- `pressed E where the exit should be: still in Act1_Chapter2_Ambush.json | act1_ch2_ambush_cleared=True | exit door built: False`;
- after leaving and returning: `exit built now: True` … `then E -> Act1_Chapter2_RuinedGate.json`.

**Root cause:**
- `engine/scene_lifecycle_controller.py:356-360` filters `scene["entities"]` with `filter_entities_by_flags` before spawning. Nothing re-runs it when a flag changes.
- The runtime already re-checks the same gates at use time (`behaviours/scene_transition.py:215,242`; `interaction.py:275`; `scene_entity_gating.runtime_entity_passes_flag_gates`). The load-time filter is what makes the entity absent.

**Missed by tests:** no test sets a gating flag mid-room and then looks for the gated entity. Shipped-content checks are static.

**Bounded fix:**
- Spawn gated entities always, but inactive: not drawn, not solid and not interactable while the gates fail (the use-time checks already exist). Re-evaluate visibility and solidity on the flag-change event, as ConditionalActivator does.
- Alternatively, on flag change, spawn the newly allowed entities and despawn the newly forbidden ones through the entity store. That is more invasive.
- Room memory and saves are unaffected.

**Regression requirements (real window):**
- set the flag in the room; the exit appears and works without re-entry;
- clearing a `forbid_flags` flag mid-room shows its entity;
- a gated solid entity doesn't block while hidden;
- the shipped Ambush: clear zone, then exit, then RuinedGate in one visit;
- save/load and re-entry are unchanged;
- mutation proof: restoring the load-time-only filter fails the first test.

### NEW-19 (P1): Studio's "Shopkeeper" can never be opened; two shipped merchants likewise

**Title:** Vendor opens only when an `open_shop` event reaches the bus. It has no interact handler, nothing Studio authors can send that event (`set_choice` can't add a choice event), and the shipped Ashen and Hollow Grove merchants have nothing that sends it.

**Severity:** P1. A Studio picker behaviour ("Opens a shop with the items you list") silently does nothing, the same class as #640/#622. It also hits shipped content.

**Reachability:**
- Studio picker "Shopkeeper" (`behaviour_guide.py:79`); MCP / `mesh author` `add_behaviour Vendor`;
- shipped: `packs/core_regions/scenes/Ashen_hub.json` (Ashen_Merchant: Dialogue `{"role": "merchant"}` + Vendor) and `Hollow Grove_hub.json`;
- `scenes/showcase_interior.json` configures `"inventory": [...]`, which Vendor doesn't read (no `stock`), so even an opened shop would be empty;
- Ridge Outpost_hub (a hand-written choice event) and `scenes/door_interior.json` (EmitEventOnEvent) work.

**Repro:** `docs/s1/evidence/repro_shopkeeper_never_opens.py` (exit 1; checkout, so the item list exists):

```
1. Studio-authored Shopkeeper ['Vendor']: E -> shop open: False
3. same Shopkeeper after an 'open_shop' event on the bus: shop open: True
2. Ashen_hub.json Ashen_Merchant: keys 1 -> shop open: False | lines seen: ['']
2. Hollow Grove_hub.json Hollow Grove_Merchant: keys 1 -> shop open: False | lines seen: ['']
2. Ridge Outpost_hub.json RidgeMerchant: keys 4 -> shop open: True
```

**Root cause:**
- `engine/behaviours/vendor.py:50,61-63,80-84`: Vendor subscribes to `listen_event` (default `open_shop`) and opens the panel only there. It defines no `on_interact` / `can_interact_with`.
- `project_ops.set_choice` (`project_ops.py:2264-2266`) has no `event` parameter, although Dialogue honours a choice's `event` (`behaviours/dialogue.py:698-708`).
- Every Vendor in a room listens on the same global event name.

**Missed by tests:** vendor tests call `handle_buy_request` directly (#619/#625). No test opens a shop through interaction.

**Bounded fix:**
1. Give Vendor `can_interact_with` / `on_interact`, opening its own stock (respecting `shop_id`). When the entity also has Dialogue, keep the conversation and add the shop as the conversation's end, or open on a choice. Pick one rule and document it.
2. Add `event` (type + payload) to `set_choice`, so Studio can author "Let me see your wares".
3. Content: Ashen and Hollow Grove merchants get the Ridge pattern; `showcase_interior` gets `stock`.

**Regression requirements (real window, keys):**
- E on a Studio-authored Shopkeeper opens its shop and a purchase works;
- two Vendors in one room open only their own stock;
- the shipped Ashen merchant opens;
- mutation proof.

### NEW-20 (P2): a fresh project can't get its first quest through any supported tool

**Title:** There is no Studio or `mesh author` quest operation. MCP `add_quest_definition` can't create `quests.json`, and `mesh new-quest` crashes without `--target`. With `--target` it writes a list-rooted, stage-less file that the runtime ignores and MCP then refuses.

**Severity:** P2. Quests are a core workflow; the workaround is hand-writing `{"quests": []}`. No data is lost.

**Reachability:** every created project (no template ships `assets/data/quests.json`), through the AI path (MCP `apply_ops`) and the CLI.

**Repro:** `docs/s1/evidence/e2e_creation_to_export_chain.py` (step D):

```
[FAIL] D MCP add_quest_definition on a fresh project: add_quest_definition failed: File not found: <tmp>\chain\assets\data\quests.json
[Mesh][CLI] Error creating quest: argument should be a str or an os.PathLike object where __fspath__ returns a str, not 'NoneType'
[FAIL] D mesh new-quest NAME (no --target): exit 1
[FAIL] D mesh new-quest --target assets/data/quests.json makes a file the runtime loads: exit 0; file root is a list; runtime reads a 'quests' key: False
[FAIL] D MCP add_quest_definition after mesh new-quest: quests root must be an object
[ok] D MCP add_quest_definition after hand-writing {"quests": []} (workaround): Upserted quest 'vault_quest'
```

**Root cause:**
- `engine/ai_ops.py:378-381`: `add_or_update_quest_definition` → `_load_json` raises FileNotFoundError (`ai_ops.py:17-21`), and a list root is refused.
- `mesh_cli/authoring.py:41-43,101` passes `args.target` (help: "Target entity/location") as `scaffold.create_quest`'s `target_file` (`engine/tooling/scaffold.py:575`). `None` crashes, and an entity name becomes a file name.
- `create_quest` writes a top-level list with no stages (`scaffold.py:581-613`). The runtime reads only `payload["quests"]` from a dict (`engine/quests.py:56`).

**Missed by tests:** `tests/test_ai_ops_world_quest.py:52-55` writes `{"quests": {}}` first; `tests/test_cli_migration_pass7.py:23` runs only `new-quest --help`.

**Bounded fix:**
1. `add_or_update_quest_definition` creates `{"quests": []}` when the file is missing (atomic, under the existing ownership).
2. `mesh new-quest`: make `--target` an output path with the default `assets/data/quests.json`, write the object form with one stage skeleton, and refuse a list root with a clear message (or migrate it).
3. Later: a quest operation in `authoring` (Studio, `mesh author`, MCP).

**Regression requirements:**
- `mesh new`, then MCP `add_quest_definition`: the quest loads in a real window;
- `mesh new-quest X`, then the runtime sees quest X;
- `mesh new-quest`, then MCP add works.

### NEW-21 (P2): the `lighting_playground` and `demo_slice` templates create projects that can't start

**Title:** `mesh new --template lighting_playground|demo_slice` succeeds but writes a start scene in a pre-schema format (`format_version`, `scene_id`, `layers` dict, `type: npc`). The game refuses it with SchemaValidationError.

**Severity:** P2. These are CLI-only templates (not offered by the launcher), but `mesh new --help` advertises `--template` with ids from `engine.project_templates`. The crash is on the first start, and `mesh new` exits 0.

**Repro:** `docs/s1/evidence/scan_project_templates.py` (§3): `new=0 doctor=1 play={'crashed': '... SchemaValidationError ... (\'format_version\', \'scene_id\' were unexpected)'}`.

**Root cause:** `engine/project_templates.py:263-344` (`_apply_lighting_playground`, `_apply_demo_slice`). Also, `demo_slice` writes `packs/core_regions/quests/intro.json`, which no loader reads (quests load from `assets/data/quests.json`).

**Missed by tests:** `tests/test_project_templates_contract.py:40-73` asserts exactly the old shape (`data["layers"]["lights"]`, `type == "npc"`). Nothing starts a template's game.

**Fix:** retire both templates (my recommendation, given "Mesh Studio can't edit these", `project_templates.py:43`), or port them to the current scene format. Add one test that runs every listed template's start scene through the real loader (`scan_project_templates.py` is the shape of it).

### NEW-22 (P3): MCP `list_scenes` returns nothing for a `mesh new` project

- **Root cause:** `engine/mcp_server/tools.py:70-79` lists only `<root>/scenes/*.json`. Projects keep their rooms in `packs/core_regions/scenes/` (the world file lists them).
- **Repro:** chain D: `MCP list_scenes on this project: [] (its rooms: ['glade', 'shed', 'start'])`.
- **Fix:** list the world file's rooms (as `read_project` does), falling back to `scenes/`.
- **Regression:** `mesh new`, then `list_scenes` names `packs/core_regions/scenes/start.json`.

### Also found (not filed separately)

- **Shipped switch gates can be walked round while locked** (14 of 15 solid DoorLock scenes; no collision layer). CONFIRMED, P2 content: §3. File with the #639 content follow-up.
- **Model provenance stores the creator's absolute source path** in the project's `assets/models/catalog.json` (`source.file`). The export's copy does not include it. P3 (privacy, if a project folder is shared): store a project-relative or basename path.
- **After a load, `scene_controller.current_scene_path` is the save slot**, and `room_path` is the room (B-09 design). Not a defect. A tool reading `current_scene_path` to name the room after a load gets `quicksave`; my chain's first version did. Worth a docstring.

---

## 5. Engine loop, packaging and templates (as they affect the workflows)

- **Core loop and scene lifecycle on the play path:**
  - room changes (2D↔2D, 2D↔HD-2D), room memory, queued scene changes and quicksave/quickload across processes all behaved correctly in the chain, both in the project and in the export;
  - the failures are all in behaviours (#620, #636, #639, NEW-16, NEW-17, NEW-19) and in load-time gating (NEW-18), not in the loop;
  - a checkout (no launched project) boots into the project browser overlay, which blocks game input until closed. Scripts that load scenes in a checkout window must close it (`repro_core_regions_gates.py` does).
- **Asset reimport and provenance:** works (W2). The HD-2D catalogue swaps all-or-nothing (part A); the Studio reimport rollback is non-atomic (part A, P3).
- **Packaging, from `pyproject.toml`:**
  - the wheel holds `engine*`, `mesh_cli*` and `mesh_net*` (`:58`), the engine schemas, the mesh_net coop/expedition JSON (`:63-64`) and the data-file allow-list (`:72+`: starter sprites, tileset, sounds, ambience, HD-2D kit, branding, icons, template previews, locales, monster data);
  - **it excludes** `tooling/` (part C: the M4 demo needs a checkout), `packs/` (the whole core_regions campaign and dev_sandbox), `scenes/` (the showcase), `worlds/` and `assets/data/items.json` / `quests.json`;
  - so the shipped campaign and showcase exist only in a source checkout. A pip-installed Mesh can create, play and export projects (H5/H7 prove that in CI), but those projects have no items (NEW-17) and no quests file (NEW-20).
- **Exports:** carry the engine source and the project's referenced assets (1083 files, ~10.9 MB for the chain project), save per player (H9), and need Mesh's dependencies on the player's Python (KNOWN LIMITATION, H7).

---

## 6. What I could not check

- **Studio's GUI itself:** panels, the picker UI, Studio's Play button / `runtime_play`. I used Studio's project model (`engine.studio_project.Project`, under Studio's ownership lock) and its authoring operations, not a Studio window. The picker → `project_ops.add_behaviour` link is from code (`studio.py:1057-1059`).
- **Real key input to a visible window** (by rule). Input went through the window's own `on_key_press` / `on_update` dispatch; no OS events.
- **The installed wheel path:** no wheel was built (CPU rule). H5/H7's `installed_product_check` covers it in CI. `mesh play` (`mesh_cli/legacy_impl.py:312`) was not run; the chain used the project's `main.py`, which Studio Play and the export also use.
- **Multiplayer progress through the client path:** the loot was earned through the tests' `Driver` (teleporting between fights). Only the restore, resume and one-session steps went over real sockets to the real server CLI. Multiplayer for a creator's own project doesn't exist (KNOWN LIMITATION, W7).
- **Combat damage to the player:** in the gate probe the player was invulnerable, and in the chain the enemy died first. That the 1-HP player dies in one hit is inferred from NEW-16's numbers, not observed.
- **Audio:** never played aloud (master volume 0). The imported sound was only placed (a SoundEmitter was built).
- **Cutscenes (#642, #622 B) and ActionLists (#622 A)** were not authored in the chain. Parts A/B cover them.
- **The campaign beyond the Ambush:** NEW-18's other 64 exits and the remaining chapters were checked statically (the gate scenes at runtime, the exits by scan), not walked one by one.
- **Creator Mode's door plan** writing entity `require_flags` (NEW-18 reachability): code read only.
- **Web build** (`build-web`), `package-player` and `release`/`dist` were not exercised.
- **Exported games on another machine,** or with a different Python than the one that built them.
- **Scratchpad hygiene:** my exploration files went into this session's scratchpad (`a1.py`–`a4.py`, `dbg.py`–`dbg3.py`, `ops.json`, `chain.txt`, `gates.txt`), which other sessions share. I left them in place rather than delete files I can't prove I created first.
