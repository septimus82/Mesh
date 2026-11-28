# Art QA: cottage interior exit door (commit 2c202df, feature/hd2d-interior-door)

Reviewer: independent art QA, read-only. I judged from the implementer's evidence (`idoor\out`, `idoor\accept`) and from
my own hidden-window renders of the final template at HEAD 2c202df (`qa_art\r1\`, script `qa_art\qa_render.py`). All
measurements are at gameplay scale (indoors 3x, 96 px/m, 1280x720).

## Verdict

| Item | Verdict |
|---|---|
| Diagnosis | **Correct.** One gap in the wording: the old spot was in the wrong wall, not only half a sprite off. |
| Placement | **Pass.** The door covers the south doorway with no slivers, seams or z-fighting, and is not embedded or floating. |
| Shadow | **Acceptable (minor).** It is not misplaced, but it is longer than a 2 m door would cast. |
| Overall | **APPROVE with minor notes.** No blocker. No major defect. |

## 1. Diagnosis: correct

- **Old door position.** The door was centred at (5.6, 7.6) m and its bottom was at y 6.6 m (`out\diag.json`). Its hit box spanned x 4.85–6.35 m.
- **Through the west wall.** The west wall's outer face is at x 5.0 m and its inner face at x 5.2 m. The 1.5 m door art therefore passed through the wall and stuck out 0.15 m beyond the outer face into the void.
- **In the pictures.** In `accept\compare_inside_door.png` (left), the door's left edge (x≈233) sits outside the wall's outer edge (x≈245). The west wall's cap is also drawn over the door's lower-left.
- **Standing free.** The door's base was 1.7 m in front of the north wall's inner face, on open floor. It read as a panel leaning in the corner. The implementer's description is right.
- **Gap in the wording.** Even with correct bottom-edge contact, (5.6, 7.6) is in the west wall, which has no opening. The template had picked a spot with no doorway, so the real defect was the wrong wall, not just centre-versus-feet. The fix addresses both.

## 2. Placement at 3x: pass

My measurements are from `accept\after_inside.png` and `before_inside.png`, row by row.

| Check | Result |
|---|---|
| Width | The opening is x 260–378 on screen (≈1.23 m). The door spans x 245–393. Its dark frame overlaps each wall end by 15 px (≈0.16 m), so it reads as a door casing. |
| Slivers | None beside it, none below it and none above it. The doorway has no lintel, and the door's top is above the wall cap. |
| Bottom edge | The door's last row (350) sits directly on the wall/threshold base line (row 354). That line is the same as in the "before" picture, so there is no floor sliver and no gap. |
| Not floating | The door is not floating. |
| Seams and z-fighting | None at the wall ends or the threshold. I checked at 3x zoom from the centred, 1.5 m west and 1.5 m east cameras (`qa_art\zoom_door_edges.png`). |
| Side cameras | From the west and east cameras the door leans like a keystone. This is the 12° lens's perspective. The room's outer corners lean the same way, so it reads as correct. |
| Embedded | No. The door stands 2 cm in front of the outer face and in front of the wall ends. |

## 3. Shadow: plausible, over-long; minor

Measured on the final template (`qa_art\r1\final_shadow_mask.png`, `qa.json`).

**Where it falls**
- **Size.** The door's own sun shadow is 7,134 px, 0.77% of the frame. Before, there was about 13,600 px of shadow detached on the floor.
- **No lightening.** No pixels get brighter when the door is added.
- **Location.**
  - On screen it covers x 716–900, y 324–416.
  - On the floor it runs x 8.8–10.8 m, y 4.9–6.1 m.
  - It is a band about 0.9 m deep where it shows above the wall cap. It runs from the door's top-right corner to the east wall, across Tomas's feet.

**Is it misplaced? No.**
- **Anchored.** It starts at the door's edge where the door meets the wall cap.
- **Direction.** It falls north-east, which matches the sun.
- **Matches the characters.**
  - In the same frames, the player's shadow falls north-east onto the bed and Tomas's falls onto the east wall.
  - The characters' shadows follow the same stretched-height rule and look alike.
- **Matches the door's apparent height.** On screen the door looks taller than the wall, so a shadow reaching past the wall's own shadow is believable.
- **Correct physics.** It also replaces the lit band of sun that came through the open doorway, which is right for a closed door.

**Why it is still a defect**
- **Size of a real 2 m door's shadow.** A 2 m door would cast a shadow ending at about y 5.05 m.
- **The wall hides that.** The wall hides the floor up to about y 5.24 m.
- **So all of the visible shadow is extra.** Every visible pixel of the door's shadow comes from the 1/cos stretch (3.4 m).
- **Readability cost is small.** It slightly dims the floor around Tomas. It does not hide him.

- **Severity:** minor.
- **Fix:** none now. The cause is the engine-wide billboard shadow-height rule, and changing it would alter every character's shadow (out of scope). Log it against that rule.

## 4. Readability and composition: pass

- **Arrival (9.2, 6.2).** The player is fully visible, between the table and the bed and just north-west of Tomas, clear of the door's line (`r1\full_sun_door.png`).
  - In the implementer's `out\` run (old arrival 8.0/5.6), the door hid the player's legs. The final arrival fixes that.
- **Nothing important hidden.** The door hides only the threshold floor behind it. The table, the room's centre, Tomas and the bed stay clear.
- **The room still reads well.** The door is the biggest object near the bottom centre. It draws the eye, but that suits an exit. The whole room still fits in the frame.
- **Arrival prompt.** On arrival, the prompt "E: Interact: Tomas" shows straight away, because the player arrives within Tomas's interaction radius. This is neutral, maybe even welcoming.

## 5. Leaving clip

- **The implementer's clip is too short to judge.** `accept\compare_leaving.webp` has only 2 frames: the last 7 game frames before the room change. It is not a walk.
- **My own film covers the whole walk.** `qa_art\r1\walk.webp` and `walk_sheet.png` follow the walk from the arrival, west to the door's line, then south and out. Nothing pops and nothing clips through the wall.
- **What happens at the exit.**
  - The exit fires with the player's feet at y≈5.58 m, about 1.9 m north of the wall's inner face. The door's 2 m sprite reaches y 5.42 into the room, so that is where its touch box ends.
  - For the last ~5 frames the player's legs are hidden behind the door's top bar, so the player seems to stand just behind the door, then cuts to outside (`r1\walk_07.png`).
- **Severity:** minor. It reads as "walked up to the door". The depth order is correct, because the door is nearer the camera.

## 6. Regressions: none

- **Outside unchanged.** `before_outside.png` vs `after_outside.png`, and `before_outside_door.png` vs `after_outside_door.png`, are byte-identical (0 pixels differ). The exterior door from #372 is unchanged.
- **Inside.** The only changes are the door, its shadow, the player's arrival and Tomas's line.

## Defects

| # | Severity | Defect | Evidence | Fix |
|---|---|---|---|---|
| 1 | minor (art direction, owner's call) | The door rises 57 px (≈0.6 m on screen) above the 2.2 m wall cap. On screen it is 1.39x the wall's height (192 px vs 135 px), so it reads as a tall door in a low wall. This is inherent to the billboard convention: the door is in proportion to the characters (1.33x the player) but not to the foreshortened wall. Even so, the door and opening read as one piece. | `r1\full_sun_door.png`: door top y 343, wall cap y≈400, base 535 | No clean fix within the scope rules. The alternatives are a doorless exit affordance (open doorway plus mat) or a renderer change. Accept, or decide as art direction. |
| 2 | minor | The sun shadow is longer than a 2 m door would cast. All of the visible 7.1k px (a 0.9 m band towards Tomas) comes from the 1.74x stretch. It is not misplaced. | `r1\final_shadow_mask.png`, `r1\qa.json` | Engine-wide shadow-height rule. Track it separately; don't patch it here. |
| 3 | minor | The exit triggers about 1.9 m inside the room, and the player's legs are hidden by the door's top for about 5 frames before the cut. | `r1\walk_07.png`, `r1\walk.webp` | Optional: a shallower door trigger (hit box) for the inside door. Acceptable as is. |
| 4 | nit | With sun shadows off, the door's soft blob shadow lands on the black void below the room. It is 4.9k px, darkened by about 6 levels out of 255, and practically invisible. | `qa_art\zoom_nosun_door_base.png` | None needed. |
| 5 | nit (evidence) | The implementer's "filmed walk out" holds 2 frames, and `out\` used the old arrival. | `accept\compare_leaving.webp` | My `r1\walk.webp` covers it. |
| 6 | nit (text) | "The door in the south wall" uses a compass direction the player has no reference for. | `starter_village.py` | Optional: "the door at the front of the room". |

## Overall: APPROVE with minor notes

The door now occupies the real south doorway, as the owner required:
- It is centred on the doorway, its base is on the threshold line and its frame covers the opening with no slivers.
- There are no seams or z-fighting, and it is not embedded or floating.
- There is no added geometry and the exterior is unchanged.
- The disclosed shadow is consistent with how every billboard in the engine casts. It is not misplaced, and it is about half the size of the old stray shadow (52%).

The one thing the owner may still dislike is the door standing taller than its wall (defect 1). It is a consequence of the convention, not of the placement, and fixing it is the owner's art-direction call.
