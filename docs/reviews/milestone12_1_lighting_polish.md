# Milestone 12.1: Character Shadows, Natural Light Flicker & Lighting Customisation

**Goal:** characters cast shadows from the lamps around them, through the Milestone 12 per-light compositor; lights
flicker like flames instead of a regular pulse; shadows can be tuned without losing the simple presets.

Branch `redesign/visual-editor` (draft PR #344, unmerged). Commits: see "Commits" at the end.

## Stage A: review

- **Compositor (M12, kept).** `final = diffuse * (ambient + sum_i light_i * (1 - occlusion_i))`. Each shadow-casting
  light gets its own occlusion mask, cleared and filled inside a scissor box. A light without shadows on screen is
  added in one instanced draw. The budget is 16 shadowed lights a frame; lights over it are drawn unshadowed and
  reported.
- **Characters before 12.1.** They had a contact shadow only: a dark ellipse under the feet (`shadow_enabled`). No
  light ever made a character cast anything.
- **Flicker before 12.1** (`FlickerNoise` + `apply_light_flicker`).
  - It eased between one random value per beat, every `1/speed` seconds, and moved only the light's reach.
  - Its brightness term never reached the screen: Arcade's `Light` keeps its colour private (`_color`) and rebuilds
    its buffer only when told. The code wrote to `light.color`, which does not exist.
  - The result was a regular in-and-out "breathing" of the lit circle. `tests/test_natural_flicker.py` pins it:
    every brightness peak of the old noise falls on its beat.
- **Decision.** Everything goes through the existing pieces:
  - characters through the compositor's occlusion masks, the same draw as walls;
  - flicker through the light manager's existing flicker states, with a new sampling function;
  - the controls through canonical `project_ops` operations, which are validated, undoable, saved, and usable by the
    AI authoring API.

  Nothing is drawn as an overlay, and there is no second implementation.

## Stage B: character cast shadows

**How it works** (`engine/lighting/light_compositor.py`).
- Each frame, `character_shadows()` lists the visible sprites that cast:
  - players and NPCs by default;
  - any other object when it is set to cast;
  - nothing that is set off.
- For each caster it takes the sprite's current picture from the texture atlas, so walk frames, facing and size
  changes all show.
- **The shadow's shape.** It is the picture's opaque rectangle laid on the ground:
  - it starts at the feet (the lowest opaque row);
  - it points straight away from each lamp within reach;
  - its tip is slightly wider than its base.
- **The shadow's length.** It is `clamp(distance * 1.25, 0.35 * height, 4 * height) * length`. Walking away from a
  lamp lengthens the shadow.
- **Height** comes from the character's opaque height and is cached per character. A walk cycle therefore does not
  make the shadow "breathe".
- **The fragment shader:**
  - samples the picture's alpha, so the silhouette is the character's own (head, arms, legs), not a box;
  - discards the character's own body pixels, so a shadow never darkens its caster.
- **Through the masks.** Character quads go into the same per-light occlusion mask as walls, pass by pass for soft
  edges. Each pass has its own depth, so a pixel covered by a wall and a character counts once.
  - The shadow removes only that lamp's light.
  - Ambient light and other lamps' light are untouched, and a shadow is never darker than the room without that lamp.
  - The soft styles widen the edge with distance, because the lamp is a disc.
- **Exceptions.** A lamp inside a character's own picture (a carried lamp) casts no shadow of it. A lamp set to
  "Casts shadows: Off", or turned off, casts no character shadows.
- **Contact shadows** (the ellipse under the feet) are unchanged and separately controllable ("Under feet").

**Per-character settings** (`project_ops.set_shadows`; entity schema `cast_shadow`, `shadow_enabled`). Only values
that differ from the defaults are stored.

| Setting | Default | Inspector (Look tab) |
|---|---|---|
| Under feet (contact) | on | "Under feet: On/Off" |
| From lamps (cast) | on for player/NPC, off otherwise | "From lamps: On/Off" |
| Height | from the picture | Fine-tune: "Height (px, empty: from picture)" |
| Darkness (strength) | 0.85 | Fine-tune: "Darkness (0-1)" |
| Length | 1.0 x | Fine-tune: "Length (x)" |

## Stage C: natural flicker

`engine/lighting/flicker.py`, `flicker_sample(profile, seed, time, strength, reduced) -> (brightness, reach)`.

**The building blocks:**
- **Smooth noise.** Catmull-Rom interpolation through hashed random knots. It is smooth, but no two stretches are
  alike.
- **Layered octaves.** Rates 1, 2.31 and 5.17 are deliberately unrelated, so the layers never line up into a beat.
  `irregularity` weights the faster layers.
- **Flares.** A slow noise above a threshold, squared: now and then a brighter moment.
- **A faulty lamp's dips.** At most one chance every 1.2 s. When one comes, there are 1-3 smooth drop-outs at least
  1/3 s apart: never faster than three a second (photosensitivity guidance) and never a hard cut.

**How it is applied:**
- Brightness scales the light's colour, through `set_light_colour`, which writes Arcade's private `_color` and marks
  the layer for a rebuild.
- Reach scales the radius, around the light's base.
- Every value is computed from the lighting clock. The same light therefore looks the same at the same moment at any
  frame rate, and the Studio's preview is the game's formula.
- Each light has its own seed: its own `flicker_seed`, else one derived from its position and index. Two torches
  side by side never flicker together.

**Presets**

| Preset | Speed (wavers/s) | Brightness (+/-) | Reach (+/-) | Irregularity | Extras | Description in the Studio |
|---|---|---|---|---|---|---|
| Steady | - | 0 | 0 | - | - | No flicker: a lamp, a magic light. |
| Candle | 1.6 | 0.10 | 0.015 | 0.35 | flares 0.10 | A gentle, uneven waver; the lit area hardly moves. |
| Torch | 2.4 | 0.20 | 0.04 | 0.60 | flares 0.30 | A lively flame with now and then a brighter moment. |
| Fire | 3.4 | 0.30 | 0.08 | 0.85 | flares 0.50 | A restless blaze: a fireplace, a bonfire. |
| Faulty lamp | 1.0 | 0.03 | 0 | 0.30 | dips 1.0 | Steady, then now and then it stutters or drops out. |
| Custom | owner's | owner's | owner's | owner's | - | Your own: speed, brightness, reach and irregularity. |

Brightness moves several times more than reach for every flame preset (tested), so the lit area hardly moves.

**Controls** (Lighting panel, a light selected):
- Six preset buttons, with a one-line description of the chosen one.
- "Calmer / Livelier" scale the flicker's strength (x0.75 / x1.33, kept between 0.1 and 3).
- More settings: Speed, Brightness, Reach and Irregularity. Changing one makes a custom copy of the preset it
  started from, so "Torch, then adjust" works and the lamp then shows as Custom.
- Choosing Custom again keeps the owner's own earlier custom values.
- Steady turns flicker off. The light's base reach and colour are restored exactly, because flicker always works
  from the base.

**Saved settings** (light keys): `flicker_enabled`, `flicker_preset`, `flicker_strength`, `flicker_speed`,
`flicker_brightness`, `flicker_reach`, `flicker_irregularity`.
- Older lights stay as they were. A light with only `flicker_enabled`, `flicker_amount` and `flicker_speed` reads as
  Custom, with amount mapping to brightness and reach and speed kept as speed.
- `flicker_intensity` and `flicker_radius_px` keep their old meanings.
- Nothing is rewritten on load.

**Accessibility.** "Calmer Flickering" (pause menu settings, `reduced_flicker` in user settings) applies everywhere:
- every flicker runs at 0.4 strength;
- a faulty lamp gets one soft, shallow dip instead of drop-outs.

It is off by default, and no default flicker flashes.

## Stage D: shadow customisation

The room's Lighting panel keeps **Sharp / Soft / Softer** and adds:
- a one-line description of each: "crisp", "gently feathered", "broad, atmospheric";
- a collapsed **"Fine-tune shadows"** section.

| Control | Room setting | Default | Effect |
|---|---|---|---|
| Edge width (px) | `lighting_shadow_edge` | the preset's | The soft edge's width, 0-48. Choosing a preset clears it. |
| Strength (0-1) | `lighting_shadow_strength` | 1 | How much of a lamp a wall or character blocks. This is occlusion, so a weaker shadow lets some of that lamp through; it never paints dark. |
| Quality: Low / Normal / High | `lighting_shadow_quality` | Normal | Samples per soft edge (0.5x / 1x / 1.75x): smoother versus cost. |
| Characters cast shadows | `lighting_character_shadows` | on | The room's switch for characters' cast shadows (walls keep theirs). |

The operation is `set_room_lighting(edge=, shadow_strength=, quality=, character_shadows=)`. The settings are applied
by `scene_lifecycle_controller.apply_shadow_look`. The scene loader and the shadow bench both use it, and every
setting falls back to its default, so one room's tuning never carries into the next.

## Stage E: the Lighting Polish Lab, screenshots, performance

### The lab

`tooling/lighting_polish_lab.py` runs in the real Mesh Studio window, driven by OS-level mouse and keys, and is
part of `tooling/runtime_gate.py`. It builds a disposable project:
- **Lamps:** L1 white, L2 warm (off at first), a wall, the player beside L1, and two NPCs patrolling (Walker and
  Guard).
- **Flicker:** seven lamps.

**Still checks** compare two screenshots of the edit view under two settings (characters' shadows on and off, a lamp
on and off). The floor's texture cancels out, and what is left is the shadow; the lab then measures where it lies
around the feet.

**Flicker checks** are time series. Every few frames the Studio's dump gives each lamp's reach and colour at the
lighting clock, and each sample must equal `flicker_sample` for that light's settings and seed at that clock.

| # | Item | Step | Result (last full run) |
|---|---|---|---|
| 1 | Stationary player shadow | `1_stationary_player_shadow` | 397 px of shadow, direction agreement 1.00, 0% on the lamp's side; at its middle 36.5 (lamp off: 30.4, lit: 72.3): never below the room light |
| 2 | Walking around a light | `2_3_7_walk_turn_patrol` | 6 stops round L1 in Play; the floor just past the feet 38-44 vs 79-112 beside it at the same distance from the lamp |
| 3 | Turning and animating without jumps | same | Every dump: each character's shadow starts inside its picture at the bottom (0 px off); 0 px jump against a standing character |
| 4 | Two lights independent | `4_two_lights_independent` | 457 px each side; L1 off: 0 px left on its side; inside L1's shadow 140.3 vs L2 alone 84.0 (L2's light all there) |
| 5 | Contact shadow under the feet | `5_contact_shadow` | 4.5 levels darker under the feet with "Under feet" on |
| 6 | Cast off, contact kept | `6_cast_off_contact_kept` | "From lamps: Off": 0 px of lamp shadow left; under the feet still 6.3 darker |
| 7 | NPCs with shadows | `7_npc_shadows` (still), `2_3_7_...` (patrolling) | Walker and Guard: direction agreement 1.00; while patrolling, 3 characters, 3 shadows at every stop |
| 8 | Sharp / Soft / Softer on walls and characters | `8_sharp_soft_softer` | Soft-edge width (px, 10-90% of the lamp's light): walls 0 / 79 / 209, characters 3 / 12 / 22 |
| 9 | Fine-tune without removing presets | `9_fine_tune_keeps_presets` | Edge 24 px: 214 edge px; strength 0.5 behind the wall 49.2 (full 30.5, lit 56.4); High: more passes; presets still there; choosing Soft clears the edge |
| 10-14 | Steady, candle, torch, fire, faulty | `10_to_14_16_flicker_presets` | 10 s, every sample the formula's (reach within 0.002 px, colour exact); colour spread: steady 0, candle 6.8 < torch 11.2 < fire 12.7; peak-gap spread 0.45-0.69 (no beat; the old flicker: 0) |
| 15 | Custom strength, speed and reach | `15_torch_then_custom` | Torch, Livelier (x1.33), speed 3.5, reach 0.12: stored as Custom, started from the torch's values; reach 100.4-121.6 px |
| 16 | Two lights flickering independently | `10_to_14_16_...` | Torch A and torch B differ sample by sample |
| 17 | Flicker off leaves no residue | `17_flicker_off_no_residue` | Steady: reach 110.0 and colour (255, 204, 136) in every sample; beside the lamp 88.8 before and after |
| 18 | Studio matches Play | `18_play_matches_studio` | Play's lamps: the same formula, seeds and settings (reach within 0.001 px) |
| 19 | Undo/redo | `19_undo_redo` | Ctrl+Z restores the custom flicker exactly; Ctrl+Y makes it steady again |
| 20 | Save, close, reopen | `20_save_close_reopen` | Lights, room settings and the player's settings identical; the reopened lamps are the same formula |
| 21 | A copy of an existing project | `21_compatibility_copy` | A copy of Hollowmere_Trial: its older flickering lamps read as Custom and follow the formula with their own amount and speed; Play: per-light renderer, the player's shadow; no room file rewritten; the original's files unchanged (hashed before and after) |
| 22 | Performance with moving casters | `22_performance` | See Performance |

Plus `gpu_pixel_tests`: the 33 exact-pixel GPU tests (characters' and walls' shadows) that pytest skips without
`MESH_GL_SMOKE=1`.

**Bugs the lab found in itself on the way.** Five full runs:
- The player stayed at the room's default spot.
- The "edge width" counted the lamp's own fall-off.
- A reference image for the contact shadow still had the lamp's shadow in it.
- Two clicks needed retries while the Studio was redrawing.

None of these was an engine defect.

### Screenshots (`milestone12_1_evidence/`)

| File | Shows |
|---|---|
| `c1_characters_off_on.png` | The Lamps room in Studio: characters' shadows off (contact shadows only) and on |
| `c2_two_lamps_then_l1_off.png` | Two lamps: a shadow from each; L1 off: its shadow goes, L2's stays |
| `c3_sharp_soft_softer.png` | The wall's and the player's shadow in the three styles |
| `c4_contact_and_cast.png` | Under feet off / on; lamp shadow off with the contact shadow kept |
| `c5_walking_round_the_lamp_play.png` | Six stops round the lamp in Play: the shadow at the feet, longer further away |
| `c6_zoomed_softer_two_lamps.png` | Zoomed in, Softer, both lamps: a soft shadow each way |
| `flicker_presets_vs_old.png` | 6 s of brightness (white) and reach (orange): the old flicker (flat brightness, reach on a beat) and every preset, two torch seeds |
| `flicker_calmer.png` | The same with Calmer Flickering |
| `flicker_series.png` | The lab's recording from the real window (each lamp's brightness and reach) |

**Before / after.**
- *Before:* characters had only the ellipse under the feet. Lamps "breathed": the lit circle grew and shrank on a
  regular beat, and brightness never changed.
- *After:* each lamp casts each character's silhouette away from it. Flames waver irregularly in brightness, with
  the occasional flare, while the lit area barely moves.

### Subjective inspection

I looked at every lab screenshot and the plots.
- **Shadows.** They sit at the feet, follow the character's outline, lengthen away from the lamp, and fade into the
  soft styles without hard banding on the characters. On the walls, Softer shows faint fan-shaped streaks near the
  wall at Normal quality: each sample of the lamp disc. High quality smooths them (M12 behaviour, unchanged).
- **Flicker.** Candle is a calm waver; torch is lively with an occasional lift; fire is restless. The faulty lamp
  holds steady, then stutters in one to three quick dips. There is no rhythm.
- **Contact shadow.** In bright lamp light it is subtle (4-6 levels); that is its existing look, unchanged.

### Performance

**Bench** (`tooling/shadow_bench.py`, 240 frames, RTX 4070, GL 4.6; `bench_m12_1.json`). Times are ms per frame;
lighting pass = `lighting.end()`.

| Room | Frame | Lighting GPU | Lighting CPU |
|---|---|---|---|
| Two lamps, a few walls, 1 character | 1.57 | 0.037 | 0.75 |
| ... 6 characters | 1.63 | 0.037 | 0.81 |
| ... 6 characters, Soft | 2.12 | 0.054 | 1.28 |
| ... 6 characters, Softer | 2.37 | 0.081 | 1.49 |
| ... 6 characters, Softer, High quality | 2.88 | 0.118 | 2.01 |
| ... 6 characters, zoom 2 | 1.78 | 0.063 | 0.87 |
| ... two torches, 6 characters | 1.89 | 0.059 | 0.90 |
| ... 6 characters, room switch off | 1.79 | 0.067 | 0.83 |
| M12 room: crowded, 10 lights, 42 pillars | 4.25 (M12: 4.03) | 0.164 (0.181) | 2.22 (2.07) |

- Six characters cost about 0.06 ms of CPU over one, and no measurable GPU time.
- The CPU cost grows with soft-edge passes: Python builds each pass's quads. High quality at Softer is the most
  expensive setting, at about 2 ms.
- The M12 rooms are within about 10% of M12's figures. This run also advances flicker every frame (the bench now calls
  `update`), and frame-to-frame noise on this machine is of that order.

**Real window** (lab step 22, `MESH_LIGHTING_PROFILE`, 240 frames). Play in the Lamps room: two lamps, L1 a torch, the
player walking and two NPCs patrolling (5 character shadows a frame).

| Shadow style | Lighting GPU (ms) | Lighting CPU (ms) |
|---|---|---|
| Sharp | 0.148 | 1.36 |
| Soft | 0.210 | 1.56 |
| Softer | 0.244 | 1.65 |
| Studio zoomed to 1.56x (Softer) | 0.266 | 1.47 |

Zoomed in, the player's shadow is where it was: direction agreement 1.00, 0% on the lamp's side. While walking
(Sharp, one lamp): GPU 0.08 ms, CPU 1.15 ms.

**Budget and diagnostics.** The 16-light budget is unchanged; over budget is reported in the stats and the log.
The stats name `characters`, `character_shadows` and `character_feet`, as well as the shadow look (edge px, passes,
strength). No silent degradation: no lights went over budget and shadows never became unavailable in any lab
run.

## Compatibility

- **Saved projects load unchanged.** No new key is required, and every new key is optional, defaults included.
  - Lights without `flicker_preset` keep their old settings, reading as Custom.
  - Entities without `cast_shadow` follow the defaults: players and NPCs cast.
  - Rooms without fine-tuning look as in Milestone 12.
- **Characters now cast shadows in existing projects with shadows on**, because players and NPCs cast by default.
  This is the point of the milestone, but it changes how existing rooms look. The room switch ("Characters cast
  shadows") or a character's "From lamps" turns it off.
- **Older flickering lamps change character.** They used to only move their reach on a beat; now `flicker_amount`
  also moves brightness, irregularly. The same numbers now mean a natural flicker of that size.
- **Two scripts used the old toggle.** `acceptance_lighting.py` and `shadow_lab.py` pressed the old Flicker toggle;
  they now press the preset buttons.
- **Golden tests changed on purpose.** The pause-menu rows and the user-settings golden file gained "Calmer
  Flickering".

## Known limitations

1. **Saturated colours brighten less.** Brightness flicker scales the light's colour, which Arcade holds as 0-255.
   A channel already at 255 (a white lamp, a warm lamp's red) cannot brighten, so flares show mostly in the other
   channels and dips show fully.
2. **A shadow is the picture laid flat.** It is an approximate, not a projected, silhouette. A very tall or very wide
   sprite casts a proportionally long or wide shadow; Height and Length per character tune it.
3. **Shadows only in shadow-casting rooms.** Character shadows need the room's shadows on and a lamp that casts.
   Lamps a character carries (a light inside its picture) cast none of it.
4. **Softer streaks on walls.** At Normal quality, Softer shows faint streaks near walls; High quality reduces them.
5. **Fine-tune is per room.** Edge width, strength and quality are room settings, not per light.
6. **No live preview while typing.** Flicker fields apply on Enter, as every Studio field does.
7. **Calmer Flickering is a player setting, in the game's pause menu.** The Studio has no switch to preview it; the
   plot `flicker_calmer.png` shows what it does.

## Unresolved

- The project-config defaults for the new room settings (a project-wide edge width or strength) are not added: rooms
  only.
- `FlickerNoise` / `apply_light_flicker` stay for any caller without a profile. Every light from scenes now has one,
  so they can be retired once nothing else uses them.

## Regression

**Headless.**
- **Full suite:** 9,423 passed, 41 skipped.
- **Slow/e2e:** 31 failed, the known 31; none added.
- **Gates:**
  - ruff gate clean;
  - type gate 259, unchanged from M12 (five new errors on the way were fixed);
  - type-ignore count 0, BLE001 and the arcade import policy unchanged.
- **The lighting contract's line-number baseline** was rebaselined for moved lines; its handler counts are the same.

**Real window** (`tooling/runtime_gate.py`, 12 suites, no retries).
- **The first combined run: 8/12.**
  - map_tools, event_authoring and shadow_lab passed on their own straight after: 15/15, 17/17 and 14/14.
  - The failures had come from input the window didn't get while the PC was in use. The driver refused to send
    input to a window not in front, and a key-up went to another window.
  - The Lighting Polish Lab then got three robustness fixes:
    - it returns to editing after a failed step;
    - it clears stuck keys and retries a walk once;
    - it retries clicks that land while the Studio redraws.
  - It then passed 18/18 in the gate.
- **The final combined run, on the final code:**
  - every suite through shadow_lab passed: first_workflow 15/15, map_building 23/23, map_tools 15/15,
    launcher 20/20, event_authoring 17/17, ai_coauthoring 14/14, persistence 12/12, lighting 15/15, creator 21/21,
    shadow_lab 14/14;
  - it was stopped during the last two suites to give the owner the computer back;
  - those two had passed on the same code, the Lighting Polish Lab (18/18, its own gate run) and the capability lab
    (36/36, the first combined run).

## Commits

- `572936e` Characters cast directional shadows from lamps, through the per-light masks
- `5c2d0f8` Character shadow settings: schema, canonical op, Studio's Look tab
- `a5ec5dc` Natural flicker presets and shadow fine-tuning
- `4066704` Lighting Polish Lab in the real window; fine-tune defaults not stored
- The report, evidence, MESH_REBUILD / MESH_SALVAGE, and the lab's robustness fixes (the commit after these).
