# H8 evidence: gameplay viewport and HUD toast (#422)

Real frames of Mesh's 2D (`adventure`) and HD-2D (`hd2d_rpg`) starter games, rendered in hidden windows by `tooling/h8_visual_evidence.py`:

- `before/`: the engine at `8ca1028`.
- `after/`: this branch, with the same script.

The local renderer was the NVIDIA RTX 4070 (Windows 11). `facts.json` in each folder holds measurements taken from the frames themselves:

- `border`: the toast's sky-blue outline (left, top, right, bottom; image rows).
- `changed_outside_border`: pixels that change when the toast is removed but lie outside its outline (text past the border).
- `corners`: the colour in each window corner.

| Frame | Before | After |
|---|---|---|
| 2D start room, 1280×720 (`adventure_1280x720`) | purple (102,102,153) round the room; hint text 609 px past its 360-px box | black round the room; hint on one line in a 598-px box |
| 2D start room, 1920×1080 | same | same |
| 2D start room, 560×420 (`adventure_560x420`) | hint 454 px past its box | hint wrapped to 2 lines, inside its box |
| 2D interior room (`adventure_house_1280x720`) | purple round the room | black round the room |
| HD-2D start room, 1280 / 1920 / 560 | hint text past its box (609 / 609 / 455 px) | inside (one line; 2 lines at 560) |
| HD-2D interior (`hd2d_rpg_cottage_1920x1080`) | the room's own dark sky (18,14,11) | unchanged |
| HD-2D map corner (`hd2d_rpg_1280x720_corner`) | ground to every edge | unchanged |
| Window resized 1280×720 → 560×420 (HD-2D) | 455 px past | re-wrapped to 2 lines, inside |
| Text scale 1.5 (Settings), 1280×720 | 2165 px past | wrapped to 2 lines, inside |
| Short toast "Game saved" | 182 × 36 box | 182 × 36 box (unchanged) |
