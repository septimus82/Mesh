# Stranger test — 2026-10-22

**Goal:** measure the whole beginner path end to end, then let the blockers pick the next build.

**Setup:**
- Code: `main` at `f9d1cb0`.
- Install: fresh `git clone https://github.com/septimus82/Mesh.git` into an empty folder, fresh venv, `pip install -e .`.
- Machine: Windows 11, keyboard layout **sv-SE**.
- Driving: the real game window, via OS-level key and mouse input plus screenshots.

**Rules:** only `README.md`, `mesh --help` / `mesh <cmd> -h`, and what is visible in the app. Whenever a rule had to be broken to keep going, the step is marked **EXPERT** and logged as a finding.

**Mission (project `mesh new my_village`):**
1. A starting room with a person who greets you.
2. A second room, reachable through a door, with a second person.
3. Going back through the door works.
4. The game saves and loads.

## Result

| Step | Outcome | Time* | Expert steps |
|---|---|---|---|
| 0. Install (clone, venv, `pip install -e .`) + `mesh new` | ✅ | 35 s + 2.3 s | none |
| 1. Greeting person | ✅ via Creator Add Person | 7 m 48 s | none |
| 2. Second room + door + second person | ⚠️ only with workarounds | 5 m 58 s | **2**: ran `world link-scenes` with built-ins loaded; hand-added a player to the new room's JSON |
| 3. Back through the door | ✅ (with E, lands at start) | ~1 m | none (relies on step 2's workarounds) |
| 4. Save and load | ❌ save works silently; **load unreachable** | 2 m 27 s | 1 (guessed F5/F9/F10 from bindings) |

\*Wall-clock time including the tester's think time between actions. Use the times for relative cost, not as a human benchmark.

**Bottom line:** the front door and the first Creator verb hold up: install, `mesh new`, play, and Add Person through accept, save and talk. A stranger hits a wall at **"make a second room with a door"**: nothing in Creator does it, and every CLI route is broken or expert-only. A second wall comes at **"load my save"**.

## Friction table (ranked by severity)

**Severity:** **blocker** = can't proceed without expert knowledge · **confusing** = proceeded by guessing · **rough** = worked, but felt bad.

### Blockers

| # | Step | What I tried | What happened | What a beginner expects | Likely engine area (guess) |
|---|---|---|---|---|---|
| B1 | 2 | Creator Mode → Tools → **Door**, then **Map** | Nothing. The Tools list (Map, Person, Door, Monster Area, Battle, Quest, Item, Light) is inert labels. The door workflow only edits an *existing* door. | Clicking "Door" or "Map" starts making a door or a new room | `engine/editor/creator_mode/creator_state.py` `LEFT_TOOLS` are static strings; no "create room/door" verb exists |
| B2 | 2 | `mesh world link-scenes … --bidirectional` (after `world add-scene`) | **Exit 1.** Every entity errors with "behaviour 'PlayerController' / 'Dialogue' / 'SceneTransition' is not registered", and the edit is rolled back, so it can never succeed in a `mesh new` project. The same command run with built-in behaviours loaded works. | The documented command links the rooms | `mesh world link-scenes` post-edit validation runs without `load_builtin_behaviours()` |
| B3 | 2–3 | Walked into the new door | The house loads, but **there is no player**. `mesh new-scene` makes a room with no player and no arrival spawn, and `link-scenes`' `--to-spawn from_village` is never created. You arrive as nothing and can't move or go back. | New rooms are enterable and you appear by the door | `new-scene` 'empty' template; `world link-scenes` spawn creation; no player carry-over between scenes |
| B4 | 4 | Looked for save/load (Esc, H), then F5 / F9 / F10 | **F5 saves** (`saves/save_1.json`, log only). **F9 does nothing**, in-session or after a restart. **F10 opens "Scene Inspector (F10)"**, though it's also bound to `quickload_last_save`. There's no menu with Save/Load/Continue, and the starter has no main menu. | Pause → Save / Load, or Continue on next launch | quick_load handler or slot vs quick_save's `save_1`; F10 double-binding; starter `main_menu_scene: null` |
| B5 | 2 | `mesh room scaffold -h` ("create a new room scene and link it", exactly the need) | It needs **9 required args**, including `--door-macro`, `--to-stamp`, `--grid`, `--tile` and `--layers`, referring to assets a new project doesn't have. No example. | `mesh room scaffold house` | `mesh_cli` room scaffold is an expert pipeline tool exposed without defaults |

### Confusing

| # | Step | What I tried | What happened | What a beginner expects | Likely engine area (guess) |
|---|---|---|---|---|---|
| C1 | 1 | Read the editor's 5-step tour | It **never mentions Creator Mode / Shift+F5**, the README's main path. It says "Press **F6** to playtest", and F6 does nothing visible (C2). Step 5 says "**Edit scenes/** to add content": wrong folder for a scaffolded project (`packs/core_regions/scenes/`), and it implies hand-editing JSON. | The tour shows the README's path | `engine/editor/editor_first_launch_tour_controller.py` step copy |
| C2 | 1 | F6 in the editor (from the tour) | The scene reloads (log) but the editor stays up. Nothing is playable. | A playtest starts | editor `play_from_here` / play session |
| C3 | 1 | Creator top bar: **Test Play** (and Save / Fix Problems / Advanced Mode) | Clicking does nothing apart from deselecting. They look exactly like buttons. | Buttons do their thing | `creator_state.TOP_ACTIONS` are labels without click handling |
| C4 | 1 | Selected the Guide, and later my added person | Both show "**Conversation: Not set**", though both talk | It shows what they say, and lets me change it | Creator inspector reads a different field than the `Dialogue.dialogue` config |
| C5 | 1 | Wanted to change the Guide's greeting | No way: Creator offers Rename, Opacity and Move only. (I added a new person instead.) | "Edit what they say" on a selected person | Missing Creator verb (edit dialogue of an existing person) |
| C6 | 1 | Renamed "Person" → "Elder" via Creator Rename | The label changes, but the **dialogue box still says "Person"** | The speaker becomes "Elder" | Rename sets the display label only; `Dialogue.dialogue.speaker` is untouched |
| C7 | 2 | `mesh new-scene house` | Writes `scenes/house.json`, a different folder from the project's `packs/core_regions/scenes/`. It's not added to the world, and there's no "next step" hint. | The room joins my game and the output says how to link it | `mesh new-scene` scaffold paths vs project layout |
| C8 | 2 | Editor **Ctrl+O** (Scene Switcher) to open the house | It lists only "Starter Room"; filtering "house" gives "(No scenes)". The workaround is `mesh edit --scene scenes/house.json`, found via `mesh edit -h`. | All my rooms are listed | Scene switcher source (content index covers `packs/` only) |
| C9 | 3 | Used both doors | The village door triggers on **walk-in**; the house door needs **E**, with prompt "**Interact: TransitionTo_start**" (internal name, overflows its box) | Doors behave the same and have a readable label | `SceneTransition` trigger mode defaults (`link-scenes` output); interact prompt uses the entity name |
| C10 | 3 | Came back to the village | You arrive at the **room's start position**, not beside the door | You appear by the door you came through | Missing arrival spawns (B3) |
| C11 | 4 | Pressed **H** in play | No save/load listed. It says "F2: Editor" and "Esc: Pause" (Esc opens Settings), and shows engine-internal "V: Golden Slice Variants" and "Lighting demos: mesh run-preset …". Header text overlaps. | Accurate controls for *my* game | Help overlay content is engine-demo specific |
| C12 | 4 | Pressed **Esc** in play | Settings opens (keybinds, audio, rumble). No Save/Load/Quit. | Pause menu with Save/Load/Quit | Settings overlay bound to Esc; no pause menu in the starter |
| C13 | 2 | `mesh auto-wire-transitions packs/core_regions/worlds/main.json` | "No changes needed." **with exit code 1** | Exit 0 or an explanation | CLI exit code |

### Rough

| # | Step | What happened | Likely engine area (guess) |
|---|---|---|---|
| R1 | 0–4 | Placeholder art: every character is a ⊘ square that looks like a missing image. You can't tell which one is the player, and the player changes colour as it animates. | `assets/sprites/animated_player.png` placeholder sheet (needs real starter art) |
| R2 | 1 | Creator's right panel text runs **off the window edge** ("Stable ID remains: start_guide_320_128_…", "…matches the"). | Creator right-column width / truncation |
| R3 | 1 | Jargon throughout Creator and AI Proposals: "Stable ID", "Stage … Proposal", "Grid step", "Add prefab 'person'", "Dry-run OK - W0/E0", 32-hex proposal ids, `start_person_96_224_0_0`. | Creator copy; proposal summaries are the developer view |
| R4 | 1 | "Review in AI Proposals" **leaves Creator Mode**; after accepting you need Shift+F5 to get back. | Proposal handoff navigation |
| R5 | 1 | The **Outliner** tab is empty although the scene has entities. | Outliner/hierarchy panel population |
| R6 | 2 | Add Person drops the new person at the canvas centre, here **on top of the player**. | Add Person placement (no free-spot search) |
| R7 | 1 | Leaving and re-entering Creator **resets the Add Person draft** to "Hello!". | Creator state cleared on hide |
| R8 | 1 | The player **walks through NPCs** (no collision). | Starter NPC/person prefab not solid |
| R9 | 4 | Settings keybinds show **raw key codes** ("move_up: 119", "interact: 101"). | Settings overlay keybind formatting |
| R10 | 4 | F5 save gives **no on-screen feedback** (log only). | Save toast |
| R11 | 0 | The README install doesn't mention a venv: `pip install -e .` goes into whatever Python is first. | README quickstart |
| R12 | 2 | `mesh --help-all`'s usage line is a 128-command wall. Nothing points from "door/room" to `room` / `world`. | argparse usage formatting; help discoverability |

### What worked well
- Install in 35 s and `mesh new` in 2.3 s, with clear "Next:" steps. `mesh --help` is short and right.
- First `mesh play`: walk, talk, and the Guide's greeting all work.
- Creator Add Person end to end: type (Shift and layout work), stage, AI Proposals, Accept, Ctrl+S, play, talk. The status bar honestly flips Unsaved → Saved.
- Creator Rename staged and applied correctly (though see C6).
- Once two rooms were linked, door transitions worked in both directions.
- `mesh validate` and `validate-all` were clean throughout.

### Harness notes (not product findings)
- The first attempt showed variant-picker, character-sheet and inspector overlays. Traced to the test driver re-sending key-ups for already-released keys; fixed in the driver. Typing in focused Creator fields does **not** fire hotkeys (re-verified live with `cvil`).
- The Scene Switcher once appeared after Ctrl+S. I couldn't reproduce it headless and suspect the harness; not counted.
- Escape in a Creator field over an active tour is fixed separately in #342.

## Recommendations: what to build next

1. **"Add a room" with a linked door, from Creator Mode.** This clears B1, B2, B3, B5, C7, C8, C9 and C10.
   - **The verb:** one Creator action creates a new room in the project's own scenes folder, with a player arrival spawn, registered in the world and listed in the Scene Switcher. It places a **linked door pair** with arrival spawns on both sides, as one proposal.
   - **The building block:** fix `world link-scenes`' behaviour registration (B2) first. It's the existing plumbing this verb should reuse.
   - **Doors:** behave the same on both sides (walk-in or E, consistently), and show a readable label ("To House"), not the entity id.
2. **Make loading reachable and visible.** This clears B4, C11, C12 and R10.
   - **The menu:** Esc in play opens a pause menu with Save / Load / Settings / Quit, or the starter gets a main menu with Continue.
   - **The keys:** F9 actually loads the quick save, and F10 isn't double-bound.
   - **Feedback:** saving shows a toast, and H lists the real save/load keys.
3. **Make what's on screen true.** This clears C1–C6, C11, R2–R4.
   - **Tour:** it teaches the README's path (Shift+F5 Creator Mode, and the real playtest key).
   - **Help:** remove engine-demo entries from the player help.
   - **Top bar:** Creator's top-bar actions either work or stop looking like buttons.
   - **People:** Creator **shows and edits what a person says**. That fixes "Conversation: Not set" and lets you change the Guide's greeting, and rename should update the dialogue speaker.
   - **Copy:** plain-language proposal summaries for Creator-staged changes.

R1 (placeholder art) affects every screenshot in this report. It's a content decision rather than a build item, but it's the first thing a stranger sees.
