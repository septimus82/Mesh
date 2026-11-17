# M21C1: a sound behind a wall

Milestone 21 (Audio & Atmosphere), stage C, part 1. A sound emitter can be set to be quieter while a wall stands
between it and the player. Baseline `7e72a25b` (`redesign/visual-editor`). Evidence: `docs/reviews/m21c1_evidence/`.

**Technical: READY FOR INDEPENDENT REVIEW. Human listening: PENDING OWNER REVIEW** (checklist in section 9; it also
carries the Stage A and Stage B listening that is still owed). No number here shows that this sounds right.

## 1. What was already there, and what is reused

| Existing | Used here |
|---|---|
| `engine/sound_emitters.py`: the soundscape, one keyed ambience loop per emitter in reach, level and pan set each update, levels eased, the loudest 12 and at most 3 of one file, the shared headroom | all of it. Occlusion is one more factor on an emitter's level and pan inside that update; nothing about players changed |
| `AudioManager.play_loop`: asked again with the same file, only volume and pan change | this is why a change of loudness never restarts or doubles a loop |
| the ambience bus and the master volume | unchanged: `volume x distance x occlusion x ambience x master` |
| a 2D room's navigation grid (`scene_controller.get_nav_grid`: the tile map's collision tiles) and `engine.pathfinding.los.raycast_tiles` | the 2D rule's walls and its line |
| an HD-2D room's `World.walls` (`engine/hd2d/world.py`: structures' `wall` colliders, as movement uses them) | the HD-2D rule's walls |
| `engine/audio.py`'s one-shot occlusion constants (0.35 volume, 0.4 pan) | the same two numbers, so a loop and a one-shot behind a wall agree |
| the Sound inspector, `set_sound_emitter`, `sound_emitter_of`, `parse_emitter` | one more setting through each |

**Two things found in the existing occlusion code, and left alone:**

- `engine/audio.py`'s occlusion of one-shot sound effects asks the scene controller or the window for
  `is_sound_occluded` (or `is_occluded`, `has_line_of_sight`, `line_of_sight_clear`). Nothing in the engine provides
  any of them; only tests do. So one-shot occlusion has never been active in a game. `engine/sound_occlusion.py`
  could be that provider. It is not wired up here: it would change how existing games' sound effects are heard.
- That code plays a `*_muffled` copy of a file when one exists. No such file exists in the repository, and a loop
  can't be swapped for another file without a second player and a restart or a crossfade. Not used for emitters.

## 2. The rules

**The setting.** `behaviour_config.SoundEmitter.occlusion`, true or false. Missing is false: a room made before
this sounds exactly as it did (tested by walking the same route with and without a wall, level for level).

**What is heard** (`engine/sound_emitters.py`):

- behind a wall, `OCCLUDED` = 0.35 of the level its distance gives, and `OCCLUDED_PAN` = 0.4 of its pan;
- it eases there and back (`OCCLUSION_EASE_S` = 0.25 s, then the level's own 0.12 s): in the demonstration, 0.58 at
  the moment the wall comes between, 0.24 half a second later, 0.18 after one second, settled by 1.5 s;
- an emitter that comes into reach already behind a wall starts quiet: it does not start until its answer is known;
- out of reach it is forgotten, and asked afresh when back.

**What a wall is** (`engine/sound_occlusion.py`):

| Room | A wall | Not a wall |
|---|---|---|
| 2D | a collision tile on the line of tiles from the listener's tile to the sound's; or two that meet at their corners with the line passing between | either end's own tile (a machine set in a wall is heard in front of it); tiles outside the map; solid objects |
| HD-2D | a `wall` collider at least 1.5 m tall (a person's height: `MIN_HEIGHT`) and 1 m long (`MIN_SPAN`), crossed by the line from the listener's ears (1.2 m over their feet) to the sound at its own height, in 3D; a turned wall in its own turned frame | fences and railings (1 m, 0.65 m), furniture, lamp and awning posts (0.1 to 0.24 m across), a door's lintel; floors, platforms and their raised ground; sculpted terrain; water; roofs (they have no collider, cut away or not); a wall either end is inside |

Of the starter village's 23 wall colliders, 12 pass that test: the cottage's and the shop's walls and the stairs'
sides. Because the line is 3D, a sound on a plateau is heard over a wall below it, and the cottage's doorway lets
sound through under its lintel.

**One answer per emitter:** blocked or not. Thickness, the number of walls and the way round are not measured.

**When the question is asked.** Only of emitters in reach with the setting on, and only when the listener or the
emitter has moved to another 8 px cell or the room's walls are other objects than last time (another room, a
reload, scatter repainted). At most four emitters are asked in one update, the longest unasked first; the others
keep their last answer until their turn. An emitter without the setting costs one test per update.

## 3. What the backend can't do

Arcade's `Sound` over pyglet gives each player a volume and a pan. There is no filter, no reverb, no mixing graph.
So this is **quieter, not muffled**: the sound behind a wall keeps its brightness. A real wall removes the high
frequencies first; this does not. Whether volume alone is convincing is a listening judgement (section 9). No DSP,
no new dependency and no new backend was added.

## 4. Mesh Studio

In a sound's inspector, between Loop and On: **Quieter behind walls: On / Off**. It says "Quieter while a wall is
between it and the player." or "Heard the same through walls." It is one edit: undone and redone like any other,
saved with the room. Turning it off removes the setting, so the file reads as before it was ever turned on.

AI tools: `set_sound_emitter(entity_id, occlusion=true)`. Scene loading, validation and the export's asset list take
a room with it (tested). An older Mesh build opening a room that has the setting reports an unknown setting for
that emitter and leaves it silent; that is the existing rule for any setting a build doesn't know.

## 5. The listening demonstration

`tooling/occlusion_demo.py` makes throwaway projects with Mesh's own authoring operations; nothing of yours is
opened or written.

```
py -3.13 tooling/occlusion_demo.py listen artifacts/m21c1_listen
```

It makes `artifacts/m21c1_listen/listen` (the HD-2D starter village, flowing water north of the cottage, master
volume 0.8) and walks it through the speakers for about a minute, each step captioned in the terminal. Then, to
walk it yourself:

```
cd artifacts/m21c1_listen/listen
py -3.13 -m mesh_cli play
```

The route: clear on the north path; south down the path until the cottage comes between; west along the road to
the cottage's door (the whole cottage between); back; then three quick steps behind the cottage's corner and out.

**The sound:** `assets/ambience/stream_loop.wav`, Mesh's own library loop, 10 s mono, cut by
`tooling/make_ambience_library.py` from a CC0 recording; author and source are in `assets/NOTICE.md`. No new
asset.

**A software mix** of the same walk (the engine's own levels and pans applied to the file, not a recording of the
sound card): `py -3.13 tooling/occlusion_demo.py setup OUT`, `walk OUT`, `mix OUT` writes
`OUT/behind_the_cottage_mix.wav` (34 s). A copy is in this worktree's ignored `artifacts/m21c1/`.

## 6. Measurements

**The walk** (silent: master volume 0; real audio backend; `walk.json`, `walk_hd2d_levels.csv`):

| | HD-2D village | 2D room |
|---|---|---|
| clear | 0.664 | 0.900 |
| behind the wall | 0.175 (0.269 nearer to it, at the cottage's door) | 0.316 (0.35 x 0.9) |
| clear again | 0.666 | 0.897 |
| pan, clear / behind | -0.75 / -0.24 | |
| largest change in one frame | 0.015 | 0.021 |
| frames with the loop silent | 0 | 0 |
| players while playing / after closing | 1 / 0 | 1 / 0 |
| wall questions asked | 237 in 2,050 updates | 71 in 646 |

Played from Mesh Studio, the HD-2D walk gives the same levels to four decimal places (`studio.json`).

**Cost** (`perf.json`): 60 emitters of one sound about the village, the player walking the route, 2,050 updates
timed per run, three or four runs each.

| | soundscape update, mean | median | p95 | wall questions per update | players | engine memory kept over the walk |
|---|---|---|---|---|---|---|
| baseline engine (`7e72a25b`) | 574 to 581 us | 515 to 521 | 643 to 660 | - | 3 | 723 kB |
| this build, none minding walls | 604 to 613 us | 548 to 553 | 671 to 689 | 0 | 3 | 723 kB |
| this build, all 60 minding walls | 726 to 741 us | 642 to 658 | 870 to 881 | 1.51 | 3 | 745 to 747 kB |

So a room made before this pays about 30 us more per update with 60 emitters (5 %), and the worst case here, every
one of 60 emitters minding walls, about 150 us more (26 %): under 1 % of a 60 fps frame. The 12-at-once and
3-of-one-file caps are untouched (3 players here: one file). With one emitter the cost is not measurable.

## 7. Tests

- `tests/test_sound_occlusion.py` (28, fast tier, headless on the counting stand-in backend): the setting and its
  reasons; the 2D and HD-2D rules case by case (through, round the end, over the top, a doorway, a turned wall, an
  end inside a wall, the corner squeeze, outside the map); clear, behind and between; distance behind a wall;
  easing with no jump and no restart; crossing an edge every five frames for four seconds; coming into reach
  already behind a wall; ten emitters of one sound whose turn to be asked comes late; several emitters with
  different answers; an emitter without the setting heard exactly as before, the walls never looked at; when the
  question is asked and how many times; a wall put up or taken down; another room and a reload; a 2D room; ambience
  and master volumes and muting; the editor; play and stop five times; a file that can't be played; the op, the
  generic setting path, an AI tool's change, undo, redo, save and reopen; the scene loader and the export's list.
- `tests/test_sound_occlusion_gpu.py` (5, GPU lane, real hidden windows, real audio backend, silent): Studio's
  switch clicked off and on, undone and redone twice, saved, reopened; played from Studio and alone, the walk of
  section 6 with its marks checked; three Play/Stop cycles leaving no player; the 2D room.
- **Deliberate faults** (`faults.json`, `mutate_occlusion.py.txt`): 23 of 23 fail a test. Among them: the wall
  question always answering no (16 headless and 3 real-window tests fail), the level not turned down, no easing,
  starting before the answer is known, no budget, nothing remembered, emitters out of reach asked, every emitter
  minding walls, the setting on by default, each geometry rule removed in turn.

  The first run left one alive: starting before the answer is known. The test for it only held because of the
  order Python happened to give ten objects. The order is now the emitters' own, and a test with ten emitters of
  one sound (only three may play, and they are the last asked) fails without the guard.
- Local, on the code as committed: the two modules above; the existing sound and audio modules; the fast tier
  (6,164 passed, 7 skipped); ruff and mypy gates. The whole GPU lane and the full default suite are left to CI and
  Extended on the pull request's head.

## 8. Limits

- Quieter, not muffled (section 3).
- A wall is between or it isn't: standing at a wall's corner, a step changes the answer, eased over about a second.
  There is no half-shadow.
- HD-2D: only wall colliders. A sound behind a hill, a plateau's side or a boulder under 1.5 m is not behind a wall.
  Structures without wall colliders (a custom model with none) never block.
- 2D: only collision tiles. A room built from solid objects without wall tiles has no walls for sound.
- The listener is the player, as for distance. A camera away from the player hears as the player does.
- A moving emitter is asked again whenever it changes cell; a room of many moving emitters would queue at four
  answers an update.
- Tested on Windows on a physical GPU and device; CI's runners have no audio device (pyglet's silent driver), so CI
  checks players and levels, as it does for Stage B, not sound.

## 9. Listening checklist (for the owner)

Stages A and B are still **PENDING OWNER REVIEW**; nothing here changes that. One sitting can cover all three.

**Stage A (music, buses, crossfades).** From any checkout of this branch:

```
py -3.13 tooling/audio_smoke.py setup artifacts/listen_a --audible
py -3.13 tooling/audio_smoke.py listen artifacts/listen_a
```

About 70 s, captioned. The seven questions are in `docs/reviews/m21a_audio_foundation.md` ("Listen for"):
crossfade smoothness, relative volumes, clipping, loop seams, anything unexpectedly loud, bus changes, silence.

**Stage B (sounds in the world, weather).** Open `D:\Games\Lakeside Village - Soundscape` (the authored copy; your
own Lakeside Village is untouched) in Mesh Studio from this branch, open Lakeside, Play, walk to the pond. Or play
`D:\Games\Mesh-audio-assets\evidence\m21b\lakeside_soundscape_mix.wav`. The eight questions are in
`docs/reviews/m21b_soundscape.md` ("Listening checklist"): distance, direction, relative volumes, rain starting and
stopping, loop seams, clipping, room changes, the Ambience slider.

**Stage C1 (behind a wall).** The command in section 5, with headphones if you can.

1. **Clear.** On the north path, is the water plain and to your left?
2. **Going behind.** Walking south, does it sink gradually as the cottage comes between? Any click, cut or restart?
3. **Behind.** Is it steady there? Does it still get a little louder as you walk nearer along the road?
4. **Is it a wall, or just a volume knob?** The sound stays as bright as it was. Does that read as "behind the
   cottage", or as "someone turned it down"? This is the question that decides C2.
5. **How much.** Is about a third the right amount? Too much, too little?
6. **How fast.** Is about a second right, or should it be quicker or slower?
7. **Direction behind the wall.** It is pulled toward the middle. Natural, or does it lose its place?
8. **Coming back.** Walking north again, does the same sound return, with no seam?
9. **The corner.** Stepping in and out three times: smooth each time, or does it pump?

## 10. Decisions for the owner, and C2

**Decisions:**

1. The listening above, for A, B and C1.
2. Whether new sounds placed in Studio should have the setting on. It is off everywhere now, so nothing changes
   unless a creator asks for it.
3. Whether one-shot sound effects should use the same walls (section 1). It would change existing games.

**Recommendation for C2: indoor weather.** `docs/audio.md` has promised "muffled weather indoors" since Stage B, a
room already knows whether it is indoors (`weather_exposure`), and the weather loops go through the same update. It
needs no new geometry: a per-room factor on the rain and wind levels. It is the same kind of change as this one
and as small.

If question 4 comes back "just a volume knob", the alternative C2 is the smallest thing that does muffle: an
optional pre-filtered `*_muffled` copy of a loop, started beside the original and crossfaded with it while behind a
wall. That costs a second player per occluded emitter and needs a tool to make the copies; it should be designed
and listened to before it is built. Acoustic zones and adaptive music wait behind those.
