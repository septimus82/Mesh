# First-time creator trial: "Hollowmere" (2026-10-23)

**The task:** build a small atmospheric adventure in Mesh Studio from the normal `Mesh Engine.bat` launcher, using only Studio's visible controls. Then play it from start to finish, close it, reopen it and play again. Source code was opened only for genuine blockers.

**What was built (Blank project, 3 rooms):**
- **Village:** paths, a tree line, ruined walls, a pond, fences, flowers and lanterns.
- **Old House:** furnished, with a door in and out.
- **Shrine:** a forest clearing.
- **Elder Maren:** a conversation with a choice. Her choice opens the barred east gate (an object hidden by a flag), and she gives a different closing line once the shrine bell is rung (a conditional opening).
- **A patrolling watchman.**
- **Night lighting:** flickering lanterns, a candle and cold light, with wall shadows in all three rooms.
- **Saved progress:** F5 and F9.

**Played end to end three times. Close, reopen and load: progress restored.** Evidence: [`usability_trial_evidence/`](usability_trial_evidence/).

**How the run was done:**
- Mouse and keys were real OS input, through the GUI test driver.
- Screenshots were read the way a person reads the screen. The Studio layout dump was used only to find the coordinates of labels already visible.
- Character art: a Blank project has none, so I drew five simple 32×32 sprites outside the repository and imported them with Studio's own **Import PNG...**, as a creator bringing their own art would.

## Could an ordinary user do it without documentation?

| Task | Verdict | Why |
|---|---|---|
| Paint an outdoor area (paths, walls, details) | **Yes** | Palette with names on hover. Picking a wall tile switches to the Walls layer by itself. Brush, Rect and Fill are obvious. |
| A house you can enter and leave | **Yes, via right-click** | **Add door to a new room...** makes the room, both doors and both arrival points. The **+ New room** button doesn't mention doors. The new room's door floats mid-floor until dragged. |
| An NPC with dialogue and a choice | **Yes** | Placing a Person opens the Dialogue tab. Lines, choices, "sets flags" and the in-panel **Test conversation** are clear. |
| A character with patrol movement | **No** (before the fix: impossible) | The picker lists 62 internal class names with no descriptions. Patrol's point list could not be entered at all. A route is still typed as coordinates. |
| Flickering light and shadows | **Yes** | The Lighting panel: On, Night, + Add light, Flicker. Walls cast shadows. |
| A gameplay condition (unlock an exit) | **Yes in the editor; broken in play** (fixed) | Conditions → "Hidden once set" → **Pick** a flag is excellent. But the hidden gate kept blocking the road in the real game. |
| Room transitions | **Yes** | Doors work both ways. |
| Saved progress | **No** | F5 and F9 work but are invisible: nothing on screen mentions them, nothing confirms a save, and Esc does nothing in a play-test. |
| Your own characters | **Partly** | Import PNG is visible. Then come per-room player copies, a technical animation warning and a collision trap (below). |

## Problems, by severity

**Critical: blocks finishing the game**

1. **Patrol could not be set up** (fixed).
   - Typed waypoints were split on commas into `["464", "192 700", "192"]`. Patrol needs `{x, y}` points, so it disabled itself silently.
   - The box showed the broken value back as if it were fine.
   - The settings were raw names, duplicated (`patrol_points`/`points`, `patrol_speed`/`speed`).
2. **A gate hidden by a flag still blocked the way** (fixed). "Show when" told the solid list to drop the object, but looked for that list on the window, where it doesn't exist. The unit test passed only because its fake window had one.
3. **The player is too big for a two-tile gap.**
   - The player collides with its whole 64×64 picture, so it stops at narrow paths and doorways it visibly fits through.
   - The cure, Collision → **Footprint**, is there but nothing points to it.
   - It has to be done in every room (see 4).

**High: confusing or wrong, with a hard-to-find workaround**

4. **Every room has its own copy of the player.**
   - Giving the hero a picture in the village left the house's player as the placeholder, so the player changed look when entering the house.
   - Rooms made later copy whatever the player looked like at that moment.
   - Picture, size and collision must be repeated per room.
5. **A Blank project's characters look like error icons.** The player and every new Person use the same purple "no entry" placeholder sheet. On the map an NPC can't be told from the player.
6. **The behaviour picker speaks code.**
   - 62 class names (ActionListRunner, BreedingShrineZone, ...) with no descriptions.
   - A search for "patrol" offers NpcSchedule, Patrol, PatrolChase and PatrolPath, with nothing to choose between them.
7. **Dialogue choices were drawn upside down** (fixed). The first choice appeared last, and Down moved the highlight up the screen.
8. **Hard shadows drew black beams to the map's edge** (fixed). This was my own Milestone 10 extrusion; shadows now end at the light's reach.

**Medium**

9. **No visible save or load in play.** F5 and F9 work; Esc does nothing in a play-test, and nothing says "Saved". The Adventure template's description promises "Esc opens the menu to save and load".
10. **+ Line silently links the previous last line to the new line.** The elder's "gate is open" line ran straight on into the thank-you meant for later. I only noticed by reading "3. ... > 4".
11. **A patrol aimed at an unreachable point stops there for good** and can block the road (it did, in front of the exit). There is no warning, and the route isn't drawn on the map.
12. **Lighting can't follow the story.** "The lamps blaze back to life" can't be shown: no light or room-light setting responds to flags.
13. **Inside a light, a shadow is darker than plain night.** The overlay also paints over ambient light.
14. **Typing with no box selected pans the map** (W/A/S/D), silently.
15. **After importing a picture**, the message "Its animation expects a 256x128 sheet of 64x64 frames" comes with a red **Reset animation** button that looks destructive. A false "looks like a sheet of frames" warning followed every 32×32 import (fixed).

**Low**

16. Spawn points ("Arrival from ...") open the full object inspector, with Picture, Animation and Dialogue tabs.
17. A door's trigger area isn't drawn, so you can't tell whether an arrival point sits inside it.
18. The new-room Name box needs a click before typing. "Its door is next to its player" is obscure.
19. New Persons default to **Only once: On**.
20. The starter tiles have no roof or door: a house is a brick block.
21. Converting a room with Fill left the old floor under its border trees.
22. A lantern is two things: an object for the picture and a separate light on top.

## What worked well

- **The launcher:** clear, and the recent list reopens the game in one click.
- **Map painting:** painting, rooms with doors from a right-click, and copy/paste ("Paste Lantern here") were quick and obvious.
- **Dialogue:** the editor with its live **Test conversation** was the most pleasant part.
- **Conditions:** "Hidden once set" plus **Pick** reads like plain language.
- **Lighting:** the panel built the atmosphere in a few clicks, and the editor shows what the game will look like.
- **In play:** the "E: Interact: Elder Maren" prompt appears without any setup.
- **Reopening:** close, reopen, play and load all worked. The fresh play-test was a new game; the load restored flags, room and the open gate.

## Fixes made in this trial (committed with tests)

| Fix | Commit |
|---|---|
| A hidden object stops blocking in the real game; the scene loads with it | `ddc9a5c` |
| Dialogue choices top to bottom in the authored order | `7b887fa` |
| Shadows end at the light's reach (no beams) | `68d6777` |
| Point lists ("x,y; x,y"), JSON list text, setting descriptions, hidden alias duplicates | `cef260d` |
| No false "sheet of frames" warning on a single small picture | `1a74903` |

## The three changes that would help most

1. **One player for the whole game.** Today each room has its own Player copy.
   - Picture, size and collision belong to the game's hero and should apply in every room.
   - Characters should default to **Footprint** collision.
   - This removes problems 3 and 4, the two most likely to stop a newcomer.
2. **Behaviours in plain language, set on the map.**
   - Describe each behaviour in a sentence and hide or group engine-internal ones.
   - Let point settings (patrol routes) be clicked and dragged on the map, drawn as a path, with a warning when a point can't be reached.
   - This covers problems 1, 6 and 11.
3. **A first-run experience that looks and plays like a game.**
   - Distinct starter characters (player versus villager) instead of the "no entry" sheet.
   - A visible in-game menu with Save and Load and a "Saved" message.
   - This covers problems 5 and 9.

## Verdict

**Mesh Studio is becoming a game-making tool. It is not one yet for a newcomer.**

- **What's there:** the core of authoring. Maps, rooms and doors, conversations with choices and flags, conditions and lighting are visual, discoverable and pleasant. A complete small adventure was built without writing any JSON.
- **What's missing:** the glue between those systems. It took three engine or Studio bugs (patrol entry, hidden-object collision, choice order), all fixed here, plus two workarounds a newcomer wouldn't find:
  - Footprint collision on every room's own player copy;
  - F5 and F9 for saving.

Without those, the game would not have been finishable.

## Validation of the fixes

- **Headless tests:** the fast gate passed 4,262. The related default-suite tests (dialogue, shadows, lighting, conditions, Studio, behaviours) passed 989. Each fix has a test, and each new test fails on the old code.
- **Runtime gate** (real window; justified because collision, shadow drawing and the dialogue box changed): **9/9 suites, no FLAKY**.
  - Milestones 1–6: 15, 23, 15, 20, 17 and 14 steps.
  - Persistence 12/12, lighting 15/15, capability lab 36/36 (+1 KNOWN).
- **The trial game itself:** after the fixes it was played from the start through to the ending, closed, reopened and loaded from its quick-save.
- **The game:** `Documents/Mesh Projects/Hollowmere_Trial` (disposable; delete it when done).
