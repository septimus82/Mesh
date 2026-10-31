# Cottage door: independent visual QA (commit c3c7d7a, feature/hd2d-cottage-b)

**Verdicts**
- **Diagnosis:** correct.
- **Fix at 2× (gameplay scale):** it fixes the owner's complaint. But it **introduces one new seam** (D1). I would not sign it off until that is fixed. The fix is a one-number change, and I verified it by rendering.
- **Fix at 4×:** the same seam is clearer. There is also a cosmetic overlap with the lintel (D2), which I accept as it is.

## Defects

| # | Severity | What | Evidence | Fix |
|---|---|---|---|---|
| D1 | **Medium**: visible at 2×, introduced by this fix | The timber sill beam that runs along the top of the plinth (z 0.85–1.0 m) is drawn **in front of** the door's left and right edges. The door is 1.5 m wide and the opening 1.2 m, so the door overlaps the wall by 0.15 m on each side. There the beam's cut ends cover the door's dark frame border. This is a notch of about 9–10 px on each side over 9 rows at 2×, and about 18–19 px on each side over 18 rows at 4×. It reads as the beam passing in front of the door, which breaks the "one piece" read. **Cause:** the beam's front face is at wall − 0.05 m in the GLB (`cottage.glb` parts 10/11, y = −2.05), and the door plane is at wall − 0.02 m. So the door is 3 cm *behind* the beam. It is solid depth occlusion, not z-fighting: the same rows appear from the c, w and e cameras. | Door visible width by row (door vs no-door diff): 2× rows 300–308 are 75 px wide against 94 elsewhere; 4× rows 243–260 are 147 px against 183. See `zoom_after_close_door.png` and `zoom_beside.png` (right panel), and `zoom_2x_doors.png` (bottom row). | Put the door's bottom edge **0.06 m** in front of the wall face (`COTTAGE_DOOR = (6.0, 8.0 - 2.0 - 0.06 + 1.0)`), and update the test's "just in front" tolerance to match. I verified it with my own hidden-window renders (`gap/`, `gap_compare.png`): at 0.06 m and 0.08 m the notch is gone at 2× and 4×. There is still no gap above the door (0 darker px above it). The only addition is a 1–2 px soft contact shadow on the door's right edge, which looks plausible. The posts (−0.07 m) and window frames (−0.06 m) do not overlap the door's x-range (±0.75 m), so 0.06 m is clear. The alternative is to stop the beam 0.15 m short of each jamb, which is a kit change. |
| D2 | Low, cosmetic, inherent | The door covers about the lower half of the lintel, which hides the lintel's centre nail. Its top corners overhang the lintel ends by about 0.15 m onto the plaster and the upper timber band. At 4× it reads as a door "a size large for its frame" laid over the doorway. At 2× the remaining lintel strip reads as a door head, and the whole thing looks coherent. **Cause:** the billboard is stretched by 1/cos 30°, so the 62 px art stands about 2.24 m tall in the world, against a lintel at 2.0 m (lintel spans z 2.0–2.5). The art is also 1.5 m wide against a 1.2 m opening. | `zoom_4x_top.png` (flush_sun_door against flush_sun_nodoor) and `compare_front_close.png` | Leave it; following the owner, don't resize the door. If it ever matters, the clean route is to size the kit's opening and lintel to the door (about 1.5 × 2.25 m), not to shrink the door. |
| I1 | Info, pre-existing, not the door | In the last two frames of the walk-in clip, every pixel of the frame shimmers at sub-pixel level as the follow camera starts moving: 42–47k changed px, and the change is not a whole-pixel shift. The nearest-filtered textures resample. | `clip_diff_6_7.png` | Out of scope; this is camera snapping. |
| I2 | Info, evidence labelling | In `diag.json`, `opening_shown_beside_door_px` actually counts pixels the door *hides* that are darker without it, which is coverage. It is not opening "beside" the door, and flush > template there is good. `door_shadow_px` for flush (8197) is mostly coverage too. The door's true cast shadow at flush is 29 px: a 5-row eave shadow on the door's own top, with 0 px on the wall. | My `measure.py` | Rename or recompute these if they are reused. |

## 1. Diagnosis: correct; a combination with one root cause
The root cause is the **misplaced sprite**: its bottom edge stood at y 8.9 m against the wall face at 10.0 m, so it was 1.1 m proud. That one error produced two dark areas:

- **To the right of the door: the projected sun shadow of the door.**
  - In template 4× c, 7,799 px are darkened by the sun only when the door is present.
  - 7,472 of them (96 %) lie to the right of the door, in bbox (405,251)–(527,413), on the plinth and wall.
  - None of them are above or to the left.
  - At 2× the same measure gives 1,968 px, 1,922 of them to the right. The w and e cameras give the same result.
  - These pixels are absent in `template_nosun_door` and `template_sun_nodoor`.
  - This is the owner's "dark rectangle behind and to its right".
- **Above the door: a geometric gap. The opening itself shows.**
  - Luminance down the door's centre, 4× c, rows 136–164: 33 with sun and 74 without, *identical* with and without the door.
  - So this is interior floorboards seen over the door's top, about 35 rows at 4× (≈0.3 m). It is dark only because the interior is in the roof's shadow; with the sun off it shows as lit planks.

After the fix:
- The door-cast shadow on the wall falls to 0 px from all three cameras.
- The rows above the door are the lintel. They are the same with and without the door (lum 27–32), not the opening.

## 2. Fix at 2× (gameplay scale; c, w, e cameras)
- No dark sliver above, beside or below the door. The old right-hand shadow is gone, and so is the doorway showing above the door.
- The bottom edge meets the ground and the plinth base cleanly.
- There is no z-fighting or flicker. The door is 2 cm in front of the wall at about 53 m camera distance, with near 0.1 and (assuming) a 24-bit depth buffer: about 1.7 mm per depth step, so about 12 steps of margin. It is also alpha-tested. Door pixels are stable in clip frames 1–6, where the only changes are the player.
- **Exception:** the sill-beam notch on both door edges (D1). Apart from that, the door and opening read as one piece from all three cameras.

## 3. Fix at 4×
- Same as 2×, with D1 clearly visible: the beam ends sit over the door's frame border.
- D2, the lintel overlap and corner overhang, is noticeable but acceptable.
- The eave shadow darkens the door's top border slightly: 34 → 14–29 over 3 px. This is physically plausible.

## 4. Proportions
- The door now overlaps the wall by 0.15 m on each side and covers the lower half of the lintel (D2).
- This follows from the 1/cos 30° stretch and the art's width. It is not a defect of this commit, and I don't recommend resizing the door.
- The only wrong-looking overlap is D1, which is a depth problem, not a size problem.

## 5. Player interplay
- **Beside the door** (feet 11.48, 9.64): the depth order is correct, with the player in front of the wall and window frame. The player's sun shadow falls north-east onto the plinth and ground, which is plausible.
- **Walk-in:**
  - The player overlaps the door's lower half as they arrive, with nothing popping or clipping.
  - The transition fires with the feet about 1.04 m south of the door plane (8.94 against 9.98). Before the fix it was 1.06 m, so this is unchanged.
- **Cutaway behind:** unchanged and correct. The door sits correctly in the wall below the cut circle. visible_px is 1730 both before and after.

## 6. Regressions in the rest of the frame
I aligned each before/after pair by the best shift (dy −34 to −37 px, which is the door's 1.08 m move north in screen space, plus 0–4 px of perspective in x). After alignment, every differing pixel lies inside the door, its old shadow, or (for arrived_outside) the player at the moved arrival point. The inside shot is identical (0 px). I found **no regressions** (`regr_*.png`, `regr_sheet.png`).

## Files (all mine, under this folder)
- `measure.py`: diagnosis numbers.
- `gap_probe.py` and `gap/`: hidden-window renders at gaps of 0.02, 0.04, 0.06 and 0.08 m. Its throwaway project copy has been deleted.
- `zoom_*.png`, `gap_compare.png`, `entering_*`, `clip_diff_6_7.png`, `regr_*.png`.
