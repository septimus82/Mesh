# M17 pilot: PixelLab player-character candidate (`hero_m17.png`)

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
