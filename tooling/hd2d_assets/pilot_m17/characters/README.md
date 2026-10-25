# M17 pilot: PixelLab player-character candidate (`hero_m17.png`)

## Stage 1B: pixel-edit repairs (h2, h3, h4)

### Files
- **Sheets:** `hero_m17_h2.png`, `hero_m17_h3.png` and `hero_m17_h4.png`.
  - Same format as Stage 1: 4x4 frames of 32x48; rows down/left/right/up; columns stand/step/stand/step; idle =
    column 0.
  - All frames have binary alpha and feet on row 47.
- **Script:** `build_hero_1b.py` derives all three from the unchanged `hero_m17.png`. It makes no PixelLab calls and
  is deterministic: run `py -3.13 tooling/hd2d_assets/pilot_m17/characters/build_hero_1b.py`.
- **Evidence:** `gameplay_1b/` holds the gameplay-scale evidence from `tooling/m17_visual_pilot.py compare --set hero`:
  `hero.json`, the 1:1 + 4x strips per spot, and the 1:1 walk clip.
- **Record:** `provenance.json` → `stage_1b` lists every edit with pixel counts, the h4 iterations and the
  measurements.

### What each candidate changes
- **h2 "repaired"** (Stage 1 colours only):
  - **Front/back walk rebuilt** as [stand, step A, stand, step B] around one canonical upper body per row (down_0
    rows 0-34, up_0 rows 0-35). The stand has both feet planted; it is built by mirroring the planted leg: down about
    x=16, up about x=15. The steps keep their original order:
    - down: down_0 (right foot up), then down_1's legs (left foot up);
    - up: up_0 (left foot up), then up_3's legs (right foot up).
  - **Dropped frames:** down_2 (the different, sterner face and wide arms), down_3, up_1 and up_2. In Stage 1 no
    down/up frame had both feet down: down_3 lifts the right foot about 4 px.
  - **Effect:** the idle stands, the rhythm alternates evenly, the head stays level and the face is identical in all
    four frames.
  - **Side rows:**
    - red removed from the legs (the scarf red bleeding into west frames 1 and 3, and red boot-top pixels): dark red
      → dark trouser, red → boot brown;
    - red removed from the west mouth and the east cheek/forehead → skin shades;
  - **Satchel removed:** it appeared in only 2 of 16 frames (east 1 and 2): cleared and re-outlined in east 2, merged
    into the back-arm shadow in east 1.
- **h3 "moss tunic":** h2 with the grey tunic ramp (rows 17-37 only) → moss `#4f5a34 / #66733f / #7d8a4f`, at about
  the old values. The grey still used by hair, boot and trouser highlights is kept.
- **h4 "legible":** h3 plus three changes:
  - a deeper moss ramp `#38422a / #4b5733 / #61703f`, well below the grass (luma about 115) and dirt (about 122) in
    value;
  - every outline pixel darkened `#392a23` → `#1c1412` (L about 0.09, the baseline's darkest);
  - a continuous 1 px outline ring around the silhouette on the sides and top. The feet stay on row 47, so the figure
    becomes 44-45 px tall and 2 px wider: it still fits 32x48, with the widest stride at 25 px.

### Gameplay scale (the 720-line picture, art at 2x; the owner's rule: gameplay first)
Pixels covered / edge luma step / edge colour step, by spot:

| | cottage | path | centre |
|---|---|---|---|
| H0 baseline | 1721 / 32.8 / 52.6 | 2431 / 41.8 / 66.7 | 2392 / 44.6 / 75.1 |
| H1 Stage 1 | 1416 / 26.4 / 46.6 | 1888 / 37.4 / 60.1 | 1996 / 41.6 / 69.7 |
| H2 repaired | 1416 / 27.7 / 48.2 | 1940 / 36.9 / 59.3 | 2092 / 40.3 / 67.5 |
| H3 moss tunic | 1416 / 27.6 / 47.9 | 1940 / 36.9 / 59.3 | 2092 / 40.3 / 67.5 |
| **H4 legible** | **1785 / 36.1 / 56.4** | 2326 / **53.0 / 83.5** | **2476 / 54.7 / 91.8** |

- **H2 and H3:** these are repairs. Their edge contrast is about Stage 1's, still below H0 at every spot, so they fail
  the gameplay bar.
- **H4:** beats H0 on both contrast measures at all three spots:
  - cottage: +3.3 luma / +3.8 colour;
  - path: +11.2 / +16.8;
  - centre: +10.1 / +16.7.
  - It covers more pixels than H0 at the cottage and centre, and 4% fewer at the path.

### How h4 got there (the measured iterations)
1. **Outline `#241a17`:** won at the path and centre, but was short at the cottage (luma -0.8, colour -2.6), where the
   head is against the dark timber wall.
2. **Lighter chestnut hair:** no change at all. The metric reads only the outermost pixels, and the hair interior
   never touches them.
3. **Lighter hair with no ring around the head:** fixed the cottage but lost the path and centre.
4. **Darker ring/outline:** every spot's background is lighter than the outline, so darker means more contrast
   everywhere.
   - `#1c1412` clears H0 at all spots and was chosen.
   - `#120c0b` clears it by more (the cottage reaches +9.2 / +13.3), but it is near-black, which goes against Stage 1's
     direction against near-black outlines. It is the next step if more margin is wanted.

### Remaining defects
- **Front/back rows:** the arms no longer swing (one canonical upper body), and the steps lift a foot 3-4 px with
  little knee bend. The walk is classic-RPG even, but stiff.
- **Side rows:** these are untouched apart from the colour cleanups, so the head bob is 1 px uneven in west frame 1
  (42 px vs 43). East frame 1 keeps a dark back-arm mass where the satchel was.
- **h4's look:** at 4x the doubled dark edge (original outline plus ring) looks heavy, and it darkens the face and hair
  detail. At 1:1 it reads as a bold, clean figure.
- **Lighting:** still not verified per pixel for upper-left light (unchanged from Stage 1).

---

**Stage 1 record below (unchanged).**

One original traveller hero made with PixelLab (v2 API) and fitted to Mesh's character sheet format using exact pixel
operations only. The baseline is `assets/sprites/hd2d_hero.png`, which this pilot did not touch.

## Files
| File | What it is |
|---|---|
| `hero_m17.png` | The candidate: a 128x192 sheet, 4x4 frames of 32x48. **The standard format is unchanged.** |
| `hero_m17_frames/` | The raw PixelLab 56x56 walk frames (`<south\|west\|east\|north>_walk_<0-3>.png`), before cropping. |
| `contact_sheet.png` | The baseline (left) and the candidate (right), every frame, 6x nearest. |
| `walk_preview.webp` | Walk loop at 4x nearest, 8 fps, in all 4 directions (down, left, right, up), with the baseline row on top and the candidate below. |
| `palette_ref.png` | The 32-colour reference passed as `color_image` (derived from the HD-2D textures and the baseline hero). |
| `measurements.json` | Per-frame height, width, feet row, colours and semi-alpha for the candidate and the baseline, plus the assembly offsets. |
| `provenance.json` | Endpoints, full requests (no secrets), seeds, character and job ids, timestamps, costs and every post-processing step. |
| `../raw/characters/` | Untouched API downloads (job images, rotation PNGs, ZIP exports) and `calls.jsonl`. |

## Format mapping (no engine change)
- **Rows:** down = PixelLab `south`, left = `west`, right = `east`, up = `north`.
- **Columns:** PixelLab template `walking-4-frames`, frames 0-3 in order: 0 passing (stand), 1 contact, 2 passing, 3 other
  contact. This is exactly Mesh's "stand, step, stand, other-step".
  - Idle (column 0) is walk frame 0.
  - The separate rotation image was not used: its south face differs from the walk frames, so mixing them would make the
    figure flicker between idle and walk.
- **Fitting 56x56 into 32x48:**
  1. Fixed crop to x 12..44. PixelLab centres its pivot at x=28, which lands at frame x=16.
  2. Per-frame vertical shift so the lowest opaque pixel is on row 47 (the feet on the ground). The shifts are listed in
     `provenance.json`.
  3. No resampling, no recolouring, no hand edits.
  - Every frame fits: the widest stride is 23 px, the tallest frame 44 px.
- The `_walking()` call needs no change:
  `character_clips(sheet, 32, 48, 4, {"down":0,"left":1,"right":2,"up":3}, walk_count=4, idle_count=1, sheet_rows=4)`.
  The auto collider still derives from 32x48.

## Measurements (candidate vs baseline)
| | Candidate `hero_m17` | Baseline `hd2d_hero` |
|---|---|---|
| Figure height, down | 43 / 43 / 42 / 43 px | 41 / 40 / 41 / 40 |
| Figure height, left | 43 / 42 / 43 / 43 | 41 / 40 / 41 / 40 |
| Figure height, right | 43 / 43 / 43 / 43 | 41 / 40 / 41 / 40 |
| Figure height, up | 44 / 44 / 43 / 43 | 41 / 40 / 41 / 40 |
| Feet bottom row | 47 in every frame | 47 |
| Colours (sheet) | 30 (12-21 per frame) | 35 |
| Semi-transparent pixels | 0 (hard alpha straight from PixelLab; the 0.5 binarise changed 0 px) | 0 |
| Max saturation | 0.54 (3 colours above 0.45: skin and its highlight, an outline brown at 0.46) | 0.58 |
| Lightness range | 0.18-0.78 (the dark-brown outline at 0.18; skin and cream highlights at 0.76-0.78) | 0.09-0.77 |

- **Doorway check:** at 43 px (about 1.34 m), the figure fits the 64 px (2.0 m) cottage doorway as well as the baseline does.
- **Head ratio:** about 3.5 heads, close to the baseline.

## Comparison with the baseline
- **Silhouette:** clearly better. The baseline is a block, with no neck, no hands and straight-tube legs. The candidate has
  a hooded cloak/scarf, a narrowing torso, separate hands, and a stride that opens the legs into an A-shape in side view.
- **Anatomy:** believable for a stylised figure of about 3.5 heads, with readable shoulders, elbows and knees. The front
  view legs are stiffer than the side view ones.
- **Clothing detail:** a russet hood/scarf (the single accent colour), a belt, a satchel (east view), a tunic, trousers
  and boots, all readable at 1x. The baseline has only a sweater and trousers.
- **Animation:**
  - Side views are much better than the baseline: there is a real contact/passing stride, an arm swing and a 1 px body
    rise.
  - Front and back are subtle: the feet alternate but there's little knee lift. They are still better than the baseline,
    whose walk is a 1 px bob with no leg motion.
- **Palette:** muted and close to the environment. The browns, slate blue and outline come from the texture-derived
  reference, and the outline is a dark brown, not black. PixelLab's shading is soft and mostly frontal: I did not check per pixel
  that the light comes from the upper left, and it was not controllable through this endpoint.

## Weaknesses (honest)
1. **Wobbly identity between directions and frames:**
   - the satchel shows in east frames 0 and 2 but disappears in frames 1 and 3, and is absent from west;
   - the south face changes between frames (frame 2 looks sterner);
   - west has a reddish mouth/cheek pixel cluster;
   - west frame 1's back leg picks up the scarf red.
2. **Tunic colour:** the prompt asked for moss green, which rendered grey-brown. It is readable but drab next to the
   cloak.
3. **The front/back walk is weak** compared with the side views.
4. **Small palette drift:** about 30 colours across the sheet against a 13-colour base rotation; the walk frames add
   shades. The skin highlights exceed the S/L targets slightly.
5. **Head-bob consistency:** after per-frame foot alignment, the head moves by 1 px between frames. Intended, but up row
   frames 0-1 are 1 px taller than frames 2-3.
6. **No resizing was needed,** and none was done.

## What failed
- **Candidate A** (character `caca7da9-…`, `image_size` 48, `force_colors: true`) was rejected:
  - the figure was 52-53 px tall, too tall for a 48 px frame;
  - forcing the 32-colour palette collapsed it to 5 colours;
  - the "cream linen tunic" merged with the skin, so the character read as shirtless;
  - the hair came out red.
- **Fix for B:** `image_size` 40 (from A's measured ratio of 52 px figure per 48 requested), `force_colors: false` (the
  palette is guidance only), and a tunic colour that can't merge with skin.
  - B came in at 42-44 px and 13 base colours.
- **Image downloads:** the rotation image URLs return 403 to Python's default urllib User-Agent. A browser-like UA, or
  reading the base64 images in the job's `last_response`, works.

## View choice
`low top-down`: the Mesh camera looks 30 degrees down at an upright billboard, so the sprite should show a mostly
front-on body with a slight top-down hint (the top of the head and shoulders visible). `high top-down` would foreshorten
the body twice, once in the art and once from the camera tilt. `side` loses the 3/4 read on the down/up rows.

## Budget / balance
- **Balance:** 3568.7 generations at the start (21:01 UTC) and 3540.7 at the end (21:08 UTC). The account is shared with a
  concurrently running sibling pilot agent, so the 28-generation drop is not all this pilot's.
- **This pilot's cost: 6 generations.**
  - candidate A: 1 (job usage);
  - candidate B: 1 (job usage; the balance moved exactly 1 during its window);
  - 4-direction template walk: 4 (documented 1 per direction).
  - Worst case 9 if the whole walk-window balance move is attributed here. Within the 30-generation cap either way.
