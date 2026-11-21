# Milestone 11: First-Time Creator Experience & Studio Usability

**Goal:** someone new to Mesh launches Mesh Studio, makes a character, builds connected rooms, gives characters
behaviours and saves their game, without hidden knowledge, JSON or undocumented shortcuts. The Hollowmere trial
(`docs/reviews/usability_trial_hollowmere.md`) found where that broke; this milestone fixes those places.

Branch `redesign/visual-editor` (draft PR #344, unmerged). Commits: see "Commits" at the end.

## What changed, by priority

### P1: one player for the whole game (`97fbc69`)

- **The player is defined once.** The definition is the project's `assets/prefabs.json` entry `player`
  (`metadata.shared_player: true`). It holds picture, animation, size, movement, collision and behaviours.
  - Each room keeps only `{"id", "x", "y", "prefab_id": "player"}`: where the player starts there.
  - The runtime resolves it with the prefab system it already had (`PrefabManager.resolve`). There is no second
    mechanism, and nothing is copied on save.
- **Studio edits the one definition.**
  - `Project.scene()` shows each room with the player expanded; storing a room splits it back.
  - The player is part of every undo step and is saved with the prefabs, keeping the other entries.
  - Studio puts unsaved changes into the live `PrefabManager`, so a play-test shows them.
- **New rooms** get the player as it is now; templates write the shared form.
- **Older projects** (a full player in every room) are migrated when Studio opens them, on purpose and visibly:
  - If every room's player is the same, Studio shares it: one undo step, with a message saying so.
  - If they differ, a **Players** panel lists what differs, room by room ("size 1.0 vs 1.5"), and offers
    "Use <room>'s player" or "Keep them separate".
    - Keeping them separate changes nothing. The inspector then notes "This room has its own player" and offers
      "Use one player in every room...".
  - The project is saved only when the creator saves.
- **Saves are untouched.** A save stores a full snapshot of the room, the player included, so old saves load as
  they did (with the player as it was when saved).
- **Feet colliders by default.** `components.collider = {"kind": "box", "auto": true}` is a box at the feet sized
  to the picture: 60% of its width and a quarter of its height (at least 8 px). It follows a new picture or size.
  - The player and the Person use it. **Whole picture** and **Circle** are still in the Collision tab.
  - Dragging a handle makes an explicit box.

### P2: behaviours in plain language (`ba59057`)

- `engine/behaviour_guide.py` is a presentation layer over the registry: label, one-line summary, category and the
  settings worth showing first, per behaviour.
  - Registry names, stored data and settings are unchanged.
  - A behaviour the guide doesn't know still shows, under Advanced, with its name made readable.
- **The picker** is a category list: Movement, Interaction, Dialogue and events, Appearance, Lighting, Gameplay,
  Advanced.
  - Plumbing (`ActionListRunner`, `EventLogger`, `PlayerController`...) is under Advanced.
  - The search covers every behaviour, by plain words ("walk") or the internal name.
- **Settings:**
  - Labels are readable ("Route", "Speed"), and the main settings come first. The rest is under **More settings**.
  - Aliases (e.g. `points` beside `patrol_points`) are hidden.
  - Invalid or missing settings say what is wrong ("It needs at least two points to walk between").

### P3: patrol routes on the map (`ba59057`)

- **Editing:**
  - **Edit route on the map** opens a route editor. Click to add a point, drag to move one, click and press Delete
    to remove it, then **Done** (or Esc).
  - The route is drawn with numbered points and arrows, closing back to the first point.
  - Every change is one undoable edit, through the same validated operation as the settings box.
- **Checks:** `engine/route_check.py` reuses the engine's A* (`build_nav_grid_from_scene_payload`,
  `line_of_sight_clear`, `astar`) and the room's solid objects. It reports, in plain words:
  - points off the map;
  - points inside a wall or solid object;
  - legs with no way through;
  - legs the patrol can't walk straight (Patrol walks in straight lines).
- **Saved like any other setting** and reopened as drawn.

### P4: the game menu in a play-test (`3ded927`)

- **Opening it:** Esc (or the new **Menu (Esc)** button on the play bar) opens the existing pause menu: Resume,
  Settings, Save Game, Load Game, **Exit Play-Test**.
  - In a Studio play-test, Quit becomes Exit Play-Test and returns to editing instead of closing Studio.
- **One save system:** the existing SaveManager and its slots. Slots read "Quick save (F5)" or
  "Saved 23 Oct, 22:41:44"; an empty load list says "No saved games yet". F5 and F9 still work.
- **Feedback only after the fact:**
  - "Game saved" once the file is written.
  - "Couldn't save the game: <why>" when it fails.
  - "Game loaded" when a load succeeds.
  - "No saved game yet: save first (Esc, then Save Game; or F5)" with no save.
  - **Policy change:** a repeated save used to say nothing; now every explicit save or load confirms.
- **Root cause of the silence:** toasts were drawn after the health bar, and `PlayerHUD.draw` returned early when
  the player had no health stats. That is every Studio game. Toasts now draw on their own. The old runtime's
  "F2: Editor  I: Inspector" banner is skipped in Studio play-tests.

### P5: starter art (`ede5a43`)

- **Original art:** a hero and a villager (4-direction walking sheets, 32 x 48 frames) and a signpost, drawn by
  `tooling/make_starter_art.py`. Provenance: `docs/starter_art.md`. No third-party assets.
- **Templates:**
  - Blank and Adventure set the art up as Studio's "Set up walking" does.
  - A new **Sign** object sits beside Person; Adventure has a sign by the house.
  - Blank still has one room, the player and nothing else.
  - Existing projects and imported graphics are untouched; `animated_player.png` is still copied for old projects.
- **Engine defects found with the art:**
  - Arcade keeps a sprite's hit box when its texture changes. A character made from a whole sheet kept the sheet's
    box, so its shadow and depth sorting sat far below its feet. The Animator now fits the hit box to the frame
    (the frame-list animator already did).
  - An NPC moved by its position (Patrol) never walked or turned. The Animator now measures the movement.

### P6: targeted fixes (`42907b2`, `ede5a43`)

| Trial finding | Fix |
|---|---|
| 10. + Line silently linked the last line to the new one | "+ Next line (after N)" and "+ Separate line"; the op gains `link=False` |
| 15. Red "Reset animation" after an import | Says what the mismatch means and what to do; the button is "Show it as it is" |
| 16. Arrival spots open six irrelevant tabs | An arrival spot explains itself; a door has Look, Conditions, Behaviours and says where it leads |
| 17. A door's trigger area isn't drawn | Drawn on the map (the door's picture, which is what the player walks into) |
| 18. "Its door is next to its player" | "Created Cave: walk into the new door here to go there. Cave has a door back beside where the player starts in it." The name box already had the keyboard; the acceptance test types without clicking |
| 14. Typing with no box selected pans the map | Any letter other than W A S D says "To type, click a box first" |
| 19. New Persons: Only once: On | New Persons and Signs answer every time; existing projects keep their setting |

## Defining acceptance test

`tooling/acceptance_creator.py`: 21 steps, from `Mesh Engine.bat`. OS-level mouse and keyboard only; the layout
dumps are read to find things and check state, never to act; files are only read.

**Result: 21/21** (the run of 23 Oct, ~2 minutes of driving).

| # | Step | What the run saw |
|---|---|---|
| 1 | New project from the launcher (Blank) | Studio opens with the one Player |
| 2 | Distinguishable player and NPC | `starter_hero.png` vs `starter_villager.png`; their on-screen pixels differ (mean colour distance 37) |
| 3 | Player appearance and footprint | Size 1.25; Whole picture, then Footprint → `{"kind": "box", "auto": true}` |
| 4 | Three connected rooms | Start → Forest → Cave, each by "Add door to a new room..." (name typed without clicking the box) |
| 5 | Player consistent in every room | Same picture, size and collider in all three |
| 6 | Change it once, every room follows | Size 0.9 set in Cave; Start and Forest show 0.9 |
| 7 | Add an NPC | A Person in Forest, renamed Ranger |
| 8 | Find patrol by its friendly name | Search "walk" → **Walk between points** |
| 9 | Click waypoints | Three points, "It can walk this route." |
| 10 | Unreachable waypoint warns | "Point 4 is inside a wall or a solid object: nobody can stand there." (point drawn red) |
| 11 | Correct it; the NPC patrols | Point dragged off the wall; in play the Ranger walks the route (its trail follows the points) |
| 12 | Dialogue with a flag | Line plus a choice that sets `asked_about_ranger` |
| 13 | Narrow passage | Stone wall with a one-tile gap: the player walks through at size 0.9 |
| 14 | Esc menu | Resume, Settings, Save Game, Load Game, Exit Play-Test |
| 15 | Save with confirmation | "Game saved"; `saves/save_20261023_232822.json` |
| 16 | Change room and state | Choice taken (flag set), walked through the door to Forest |
| 17 | Load and verify | "Game loaded"; Start room, player at the saved spot (128, 128), the flag gone |
| 18 | Exit play-test | Back to editing; Studio still open |
| 19 | Save and close Studio | Ctrl+S, the window's X |
| 20 | Reopen from the launcher | Recent list → the game; `prefabs.json` player size 0.9 and feet collider; three rooms; the Ranger's four route points |
| 21 | Play again; load works | Load list "Saved 23 Oct, 23:28:22" → "Game loaded", saved room and spot |

Getting to 21/21 took script fixes, not product fixes. The script clicked before a panel had rebuilt, and it read the
scene path, which after a load is the save file. One product gap was found and fixed on the way: the layout dump
had no labels, so a warning on screen couldn't be checked. Added to `tooling/runtime_gate.py` as `creator`.

## Compatibility

- **Old projects, real window.** Two copies of the Hollowmere trial (made before this milestone; the original was
  not touched) were opened in Studio.
  - **Identical players** (the trial as it is): Studio shared them on open. "Your rooms now share one player:
    change it once and every room follows. (Undo puts it back.)" After saving, `prefabs.json` is
    `["player", "person"]`.
  - **Different players** (the copy's Shrine player set to size 1.5 on disk first, to stand in for an older,
    inconsistent project): the **Players** panel opened.
    - It showed "Compared with Start's player: Shrine: different size" and offered Use Shrine's / Old House's /
      Start's player, or Keep them separate.
    - Choosing Shrine's reported "Every room now uses Shrine's player. Replaced: Start's size; Old House's size
      (Undo puts them back)."
  - **Saves:** in both, the trial's old quick save (written before Milestone 11) loaded with F9 into the shrine,
    with `bell_rung` and `east_gate_open` set. Evidence: `c1_old_project_players_differ.png`,
    `c2_old_quicksave_loads.png`.
- **Tests:** `tests/test_shared_player.py` covers lossless sharing, the reported differences, the runtime resolving
  the room's reference, undo, saving beside other prefabs, and the feet collider.
- **The runtime gate's launcher suite** opens `./mygame` (copied; checked unchanged) as its older project.
- **Unchanged on purpose:**
  - registry names and stored behaviour settings;
  - the `Dialogue.once` default (only the new templates' Person and Sign set it off);
  - `animated_player.png`, still shipped;
  - the save format.

## Regressions

- **Runtime gate (`tooling/runtime_gate.py`):** all 10 suites pass: creator 21/21, first workflow 15/15, map building 23/23, map tools 15/15, launcher 20/20, event authoring 17/17, AI co-authoring 14/14, persistence 12/12, lighting 15/15, capability lab 36/36. The full run (engine at `698aa64`) passed 5 of 10. The other five failed on expectations this milestone changed on purpose: the picker's plain names ("Has health", "Talk"), "+ Line" becoming "+ Next line"/"+ Separate line", the feet collider letting the player stand closer to walls, the player living in `prefabs.json`, and an older project now asking to save after its players are shared on open. Only those scripts changed (`7a58796`); each suite was then rerun alone and passes. No engine code changed after the full run.
- **Full suite:** 9,403 passed and 1 failed: the exception-policy ratchet, which the new acceptance script pushed
  over. Its catches were narrowed, and the file passes.
- **Slow/e2e:** 31 failed, 132 passed: the Milestone 9 known list (the `verify-all` chain and the wheel test).
- **Ruff gate and mypy island:** clean.
- **Type gate:** 258 beyond the baseline: 264 before this milestone, 272 after Milestone 10. Measured on a worktree
  of `2332d73`.
- **New tests fail on the old behaviour** (each checked by reverting its fix):
  - toasts for a player without health stats;
  - an NPC moved by its position walking and turning;
  - the Studio controls banner.
  - Template tests pin the new art and the "answers every time" default; the save/load toast tests pin the new policy.
- **Pinned behaviour that changed on purpose:**
  - the repeated-save and repeated-load silence (`test_saved_toast_idempotent.py`, `test_loaded_toast_idempotent.py`);
  - "Game Saved"/"Loaded" → "Game saved"/"Game loaded";
  - the prefab list now includes `sign`;
  - Studio's "Added Dialogue." → "Added: Talk." (two acceptance scripts updated).

## Commits

| Commit | What |
|---|---|
| `0e8dba8` | Scene loader knows `components`; the CLI contract test runs this checkout |
| `97fbc69` | One player for the whole game; feet colliders |
| `ba59057` | Behaviours in plain language; patrol routes on the map |
| `3ded927` | The game menu in play-tests; save/load feedback; toasts in Studio games |
| `ede5a43` | Starter art; Animator hit box and movement fixes |
| `42907b2` | Targeted Studio fixes from the trial |
| `f4c492a` | The 21-step acceptance test |
| `698aa64` | Type and exception ratchets |
| `7a58796` | Older acceptance suites follow the intended changes |

## Tradeoffs and decisions

- **The player is a prefab**, not a new kind of thing. It reuses the prefab resolver the runtime already had, the
  same operations (picture, size, collider...) and the same undo. The cost: Studio keeps an expanded view of each
  room and splits it back on store; `Project` owns that, and nothing else sees it.
- **Migration asks when it must.** Identical players are shared automatically, because nothing is lost. Differing
  ones are never merged silently.
- **Route checks follow the patrol's real movement** (straight lines), so a leg that only A* could walk counts as
  blocked.
- **Toasts confirm every explicit save/load.** The old "only when something changed" rule made a second save look
  broken.
- **WASD still pans in the editor.** Only other letters explain themselves; panning stays silent.

## Remaining usability issues

- **Long right-panel text runs a few pixels past the edge**: a word can look split ("walks t / hem"). Cosmetic;
  not investigated.
- **A loaded save reports the save file as its scene path.** The game is right (room, objects, flags), but tools
  that name the room from the path see `saves/...`.
- **A pre-Milestone-11 save keeps the player as it was saved.** A save stores the whole room snapshot, so later
  changes to the shared player appear only in new games and new saves.
- **Dialogue choices show with their line.** A one-line conversation with a choice shows both at once, and E picks
  the highlighted choice. That works, but a newcomer may expect to read first.
- **Not done from the trial list:**
  - Lighting that follows the story (#12) and darker-than-night shadows (#13): Milestone 12, shadows.
  - No roof or door tiles in the starter tileset (#20).
  - Fill leaving the old floor under border trees (#21).
  - A lantern being two objects (#22).
- **The pause menu still offers Settings** (music, effects, fog, soft shadows). They are the game's own settings,
  not the project's; that is unexplained in a Studio play-test.

## Evidence

Screenshots in `docs/reviews/milestone11_evidence/`:
- `d1`..`d4`: the game menu, "Game saved", "Game loaded", Exit Play-Test.
- `e1`..`e4`: the starter art, Adventure in Studio and in play, and the player's four facings.
- `acc_*`: from the acceptance run (the picker, the route warning, the patrol, the gap, save and load, reopening).
- `c1`, `c2`: an old project with differing players; its old quick save loading.
