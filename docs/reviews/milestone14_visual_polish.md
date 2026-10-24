# Milestone 14: Visual Polish & Creator Acceptance

Branch `redesign/visual-editor` (draft PR #344, unmerged), from `7649074` (Milestone 13).

**No test in this milestone moved the owner's mouse, pressed keys or showed a window.** Everything ran headless or
in hidden windows (`tooling/scene_snapshot.py`, `tooling/visual_polish_check.py`, `tooling/shadow_bench.py`), on this
machine's RTX 4070. The real-window gate (`runtime_gate.py --owner-present`) was not run. **Nothing here is human
visual acceptance:** the pictures are evidence for the owner to judge. The checks pending are listed at the end.

Evidence: [`milestone14_evidence/`](milestone14_evidence/). The inspection room "Yard" contains:

- two lamps (warm and cold) lighting an L of wall tiles from both sides, and a pillar;
- a rock, a bush, two trees and a fence on the walls layer;
- the player, a villager, a sign and a large (1.5×) goblin.

It was rendered at Sharp, Soft and Softer, in the game and in Studio.

## 1. Milestone 12.2 fixes confirmed

| M12.2 fix | Confirmed by | Evidence |
|---|---|---|
| Round tiles cast their outline, not a square | Rock, bush and trees in all three softness renders | `game_sharp.png`, `game_soft.png`, `game_softer.png` |
| No wedge on an L's own face at the joint (inside and outside corner, two lamps) | Clean faces at Sharp, Soft and Softer | `l_corners_two_lamps_confirmed.png` |
| Softer lamps beside walls no longer leak light behind them | Smooth penumbra at the pillar and the L | same |
| Doors: one SceneTransition, three looks; nothing of a passage or map-artwork door drawn in play; outlined in Studio | `visual_polish_check.py` 10/10 again | `doors_game_view.png`, `studio_passage_selected.png` |
| No round shadow under doors, passages, arrival spots | same check | same |
| Studio and game agree | Studio's map view matches the game render (same lamps, shadows and characters) | `studio_sharp.png` vs `game_sharp.png` |

## 2. New defects reproduced and corrected

| Defect | Cause | Fix | Before / after |
|---|---|---|---|
| **Character shadows at Soft/Softer split into separate streaks** | A character is ~12 px wide; each soft pass shifted its silhouette by the whole lamp disc (up to 22 px), so the copies stopped overlapping | Each character samples the lamp within half its own width (`light_compositor.CHARACTER_SPREAD`). Same passes, same cost | `character_streaks_before_after.png`; `tests/test_character_shadows_gpu.py::test_a_soft_character_shadow_is_one_shadow_not_streaks` (1–2 separate dips before, 0 after) |
| **Contact shadow a fixed 24×8 ellipse** (a speck under the big goblin, a slab under the sign's post) | One size for every sprite | Sized from the picture's opaque bottom rows, measured once per sprite (`scene_render_pipeline._ground_shadow_size`); a character's feet still give 24×8 | `contact_shadow_before_after.png`; `tests/test_ground_shadow_footprint.py` |
| **Studio labels cut off at the map edge** ("o Garden (passage)") | Labels are centred on the object; the side panel paints over whatever overhangs the map view | Every world label is kept inside the visible map view (`Studio._text`) | `label_clip_before_after.png` |
| **Wrapped labels split a word / lose a letter** ("It w / orks", "the m / ap") | A pyglet 2.1.11 bug: its word wrap picks the right break but draws the next word's first glyph at the end of the line before. Reproduced with plain `arcade.Text`, DPI-aware and unaware | Studio gives a wrapped label pyglet's own break points as line breaks (`studio.hard_wrap`), so pyglet never wraps it | `label_wrap_before_after.png`; `tests/test_studio_label_wrap_gpu.py` (also fails if a pyglet upgrade changes the private layout it reads) |

Not changed (checked, not a defect): labels for shadows ("Under feet" / "From lamps") and doors ("How it shows:
Door / Passage / Map artwork", "Walk in" / "Press E", map tags "(passage)" / "(map artwork)") read consistently
between the panel and the map. M12.2's short help lines for door styles stay. They are no longer needed but are not
wrong.

## 3. Transitions: the three styles behave as one door

`tests/test_door_styles_integration.py` (8 tests) runs on a real project on disk through `authoring.apply`, the
path AI clients use:

- **Destination.** Every style keeps the door's target room and arrival spot.
- **Activation.**
  - A passage or map-artwork door, saved and reopened, sends the player to the same room and arrival spot when they
    walk into its area, and not from outside it.
  - Set to "Press E", it waits for E.
- **Undo and redo.** One style change is one undo step, and redo restores it exactly.
- **Save and load.** Style, hidden picture, area and route survive save and reopen unchanged.
- **AI authoring.**
  - `set_door` is listed by `describe()` with all its settings.
  - A refused style changes nothing.

Hidden-window evidence: `visual_polish_check.py` 10/10, with the passage selected in Studio. Its area is outlined
and labelled, and the Look tab shows "How it shows". In play nothing of it is drawn: no sprite, outline or shadow.

No second transition system was added.

**Not verified (needs real input):**

- a live walk through a passage and a map-artwork door in a running game;
- selecting a passage by clicking its area;
- dragging it;
- typing a size into the door panel.

Each step's underlying op and behaviour is tested headless; the input path is not.

## 4. Performance

`tooling/shadow_bench.py`, 120 frames, hidden window, before and after the character change (`bench_compare.txt`).
All 15 scenarios are within run-to-run noise:

- 6 characters, Softer: 2.34 → 2.50 ms;
- 6 characters, Softer at High quality: 3.25 → 2.98 ms.

The pass count is unchanged. The footprint measurement runs once per picture.

## Tests

- New:
  - `test_ground_shadow_footprint.py` (3, fast);
  - `test_door_styles_integration.py` (8, fast);
  - `test_studio_label_wrap_gpu.py` (1, GPU);
  - one GPU test in `test_character_shadows_gpu.py` (8/8 in that file).
- Targeted runs:
  - `-k "studio or door or label or authoring or transition"`: 603 passed, 1 skipped (the GPU test, run below);
  - `-k "shadow or render or draw_plan or sprite or golden"`: 814 passed. This ran after the shadow changes and
    before the Studio label changes, which don't touch rendering;
  - GPU tier: 48 passed, all hidden.
- Gates: mypy gate ok (0 beyond the baseline), ruff gate ok, no `type: ignore` added.
- The full suite was not rerun (the brief asks for targeted checks).

## Limitations retained

1. **Softer, far edge of a lamp:** faint banding in the penumbra where a lamp's reach ends (`l_corners_*`, right edge).
   High quality reduces it.
2. **Outlines are convex.** A C-shaped tile casts its hull.
3. **Props cast no lamp shadow by default.** The goblin casts only its contact shadow unless "From lamps" is on.
   This is by design.
4. **The contact shadow is measured once per sprite.** An object that changes picture at run time keeps its first
   size.
5. **`hard_wrap` reads pyglet's private layout.** The GPU test guards it, and it goes once pyglet fixes its wrap.
6. **Unchanged, pending owner approval:** the wheel-packaging decision and the pause-menu "Soft Shadows" toggle.

## Human checks pending (not claimed)

1. Look at Soft and Softer character shadows near a lamp in a real game window. Do they read as one soft shadow?
2. Judge the contact shadow under large props and sign posts. Is the size right?
3. In Studio, click a passage's outlined area, drag it, type a width, undo, then press F4 and walk through it.
4. Do the same with a map-artwork door painted over a doorway.
5. Read Studio's wrapped help texts and edge labels at your monitor's scaling.
## Real-window gate (run with the owner's permission, after the report)

`runtime_gate.py --owner-present --only shadow_lab lighting_polish_lab lighting creator`:

| Suite | Result |
|---|---|
| lighting | 15/15 |
| shadow_lab | 14/14 |
| lighting_polish_lab | 18/18 |
| creator | 21/21 |

`creator` passed after three fixes. None of the three was a product defect:

1. **The suite could never create its game through the gate.** The gate's output folder is inside the engine folder,
   which the launcher refuses for new games. It now creates them in the temp folder.
2. **My label wrap fix put line breaks into Studio's reported label text.** Studio now reports the text as written.
3. **Step 12 had an intermittent race.** It typed into the next box before Studio had rebuilt the panel for the
   previous commit. The step now waits like the others.
   - Bisected: M11 passes. Failures from M12.1 on are intermittent: three bisect runs and one run at M13 failed,
     two bisect runs passed.

The gate's retry no longer crashes on a still-closing window.
