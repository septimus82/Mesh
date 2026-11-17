# M21C2: the weather outside, heard from indoors

Milestone 21 (Audio & Atmosphere), stage C, part 2. An indoor room can ask to hear its rain and wind, quietly, as the
weather outside it. Baseline `90208d39` (`redesign/visual-editor`). Evidence: `docs/reviews/m21c2_evidence/`.

**Technical: READY FOR INDEPENDENT REVIEW. Human listening: PENDING OWNER REVIEW** (section 8). The listening for
Stages A, B and C1 is still owed too; nothing here settles any of it.

## 1. The weather model, and where the indoor sound comes from

What was there:

- A room's rain is a particle effect in `settings.particles`; its wind is `settings.wind`; their sounds are
  `settings.weather_sounds` (`rain`, `wind`, two volumes).
- The rain's loudness followed the rain on screen: `engine.water.rain_rate` over the room's particle layer and
  which effects are on.
- A room with `settings.weather_exposure: "indoor"` has its rain and snow left out of that layer when it loads
  (`engine.scene_particles.configure`). So `rain_rate` is 0 there, and no rain is heard.

So a factor on the existing rain level would have multiplied zero. The indoor sound needs another source, and it is
this:

**The indoor room's own rain and wind settings are the weather outside it.** When the room asks
(`weather_sounds.indoors: true`), the soundscape reads how hard the room's `particles` ask the rain to fall, from
the settings as written, not from the layer on screen (`Soundscape.outside_rain`, found once as the room loads),
and the room's `wind` as it already did. Each is then heard at `INDOORS` = 0.35.

What follows from that, each tested:

| Requirement | How it holds |
|---|---|
| No rain is invented | a room with no rain effect (or one switched off, or only snow) has no rain outside, whatever sound is chosen |
| Nothing leaks from the last room | only the room's own settings are read; walking from a rainy village into a room with none set, the rain fades out and its player is released |
| A save loaded into the room, or a game started in it, sounds as walking in does | the source is the room, not the journey: the settled levels agree to within the engine's own resend step |
| An indoor room without the setting is as it was | no rain heard, nothing opened; its wind exactly as before |
| Rain or wind taken out of the room stops being heard | the room loads again without it |
| Outdoors unchanged | the setting does nothing in an outdoor room; levels identical with and without it |
| A sound that can't be played | silent, nothing raised, the other one plays |

No global weather, no state carried between rooms, no new player: the same two keyed loops (`weather:rain`,
`weather:wind`), so a door between two rooms with the same rain sound is the same loop easing down or up.

## 2. What is heard

- Indoors, asked for: the room's rain and wind at 0.35 of their outdoor loudness. One fixed number, the same as a
  sound behind a wall in C1. No slider.
- The change at a door takes the weather's existing pace (`WEATHER_EASE_S` = 1.2 s). Walking in, measured: the
  rain is 0.60 at the door, 0.38 a second later, 0.28 after two, 0.24 after three, 0.21 settled. Walking out it
  rises the same way.
- **Quieter, not muffled.** Volume only: the backend has no filters and none was added.
- This is the room's exposure, not acoustics: no roof, window or door is looked for.

## 3. Mesh Studio

The Sound panel, in any room, now shows:

- **Outdoors (rain and snow fall): On / Off** (the same switch as the 3D view's Weather particles panel; a 2D room
  had no way to be made indoors without editing its file);
- in an indoor room, its rain and wind labelled **Rain outside (not shown in here: this room is indoors)** and
  **Wind outside**, and the switch **Hear outside weather indoors: On / Off**;
- one line saying what is heard, or why nothing is:
  - "Outdoors: the rain and wind are heard as they fall and blow."
  - "Indoors: no rain falls or is heard in here. Turn on Hear outside weather indoors to hear this room's rain and
    wind quietly, as the weather outside."
  - "Indoors: the rain and wind set here are heard quietly, as the weather outside."
  - "Nothing will be heard from outside yet: this room has no rain or wind set, so there is no weather outside to
    hear." (in the error colour), or "... the rain has no sound chosen."

The switch is one edit: undone, redone and saved like any other; off removes the setting from the file. Turned on
before any sound is chosen it is kept (the op used to drop a `weather_sounds` with no file in it).

AI tools: `set_weather_sounds(indoors=true)`, with `set_weather_exposure`, `set_rain` and `set_wind`. The loader,
validation and the export's asset list take a room with it. An older Mesh build opening such a room reports an
unknown weather-sounds setting and plays no weather in it (the existing rule).

## 4. Compatibility, and two things left as they are

- Off unless set. `weather_sounds` without `indoors` reads exactly as before.
- **An indoor room's wind was already heard at full outdoor strength** when the room had a wind and a wind sound:
  only rain is filtered indoors, and the wind's level never looked at the exposure. The brief says an existing
  indoor room keeps its behaviour unless it opts in, so this is unchanged, and Studio's line now says so ("The
  wind set here is heard at full strength, as outdoors."). With the setting on, the wind is quieter too. Whether an
  indoor room that hasn't asked should hear any wind is a decision for the owner.
- **Read-only helpers offered as operations.** The authoring layer treats any room function that returns a
  document as an edit. Three existing readers are caught by that (`weather_sounds_of`, `hd2d_camera_of`,
  `hd2d_sun_of`). The new status reader `indoor_weather` is excluded, with a test; the three existing ones are left
  for the explicit-registry work in #392.

## 5. The demonstration

`tooling/indoor_weather_demo.py` makes a throwaway copy of the HD-2D starter game: the village, and its cottage's
inside, which the template already marks indoors. Nothing of yours is opened or written.

```
py -3.13 tooling/indoor_weather_demo.py listen artifacts/m21c2_listen
```

Run it from this branch's folder. It gives the village steady rain and a strong wind, sets the same in the cottage
as its weather outside with the switch on, and walks it through the speakers for under a minute, captioned: outside,
along the road, in through the cottage's door, inside, out again. To walk it yourself afterwards:

```
cd artifacts/m21c2_listen/listen
py -3.13 -m mesh_cli play
```

The cottage is west of where you start; its door is on its south side. The sounds are Mesh's own
`assets/ambience/rain_loop.wav` (cut from a CC0 recording) and `wind_loop.wav` (synthesised by Mesh); authors and
sources are in `assets/NOTICE.md`. No new asset.

A software mix of the same walk (the engine's levels applied to the files, not a recording of the sound card) is
made by `setup`, `studio`, `walk`, `mix`; a copy is in this worktree's ignored `artifacts/m21c2/`.

## 6. Measurements

**The walk** (silent: master volume 0; real audio backend; `walk.json`, `walk_levels.csv`). The project was authored
entirely by Studio's own controls.

| | room | rain | wind | rain effects on screen | players |
|---|---|---|---|---|---|
| outside | village | 0.595 | 0.35 | 1 | 2 |
| at the cottage's door | village | 0.599 | 0.39 | 1 | 2 |
| inside | cottage | 0.211 | 0.13 | 0 | 2 |
| inside, later | cottage | 0.211 | 0.13 | 0 | 2 |
| outside again | village | 0.599 | 0.35 | 1 | 2 |

(The wind gusts, so its level moves.) Largest change in one frame: rain 0.008, wind 0.005. Lowest level after the
first three seconds: rain 0.21, wind 0.12: never cut. Two loops and two players from start to end.

| also | rain | rain on screen |
|---|---|---|
| a quick save made in the cottage, loaded from the village | 0.211 | 0 |
| a game started in the cottage | 0.209 | 0 |
| a play-test started in the cottage from Studio | 0.211 | 0 |
| the switch turned off, played | 0 (and the wind 0.40, as before this change) | 0 |
| the exported build, its own engine: village / cottage | 0.599 / 0.211 | 1 / 0 |

Players after every close and every Play/Stop: 0.

**Cost** (`perf.json`; 2,000 soundscape updates per room per run, three runs each, alternated):

| | village, mean | cottage, mean | players in the cottage |
|---|---|---|---|
| baseline engine (`90208d39`) | 19.2 to 20.1 us | 17.0 to 17.5 us | 1 (its wind) |
| this build, cottage not asking | 19.4 to 19.7 us | 17.3 to 18.0 us | 1 |
| this build, cottage hearing outside | 19.2 to 19.4 us | 16.0 to 16.4 us | 2 (rain and wind) |

No measurable cost. The room's rain setting is read once as the room loads; each update does one more test.

## 7. Tests

- `tests/test_indoor_weather.py` (20, fast tier, headless on the counting stand-in backend): the setting; outdoors
  unchanged; an indoor room without it as it was; with it, rain and wind at 0.35 on the same two loops; light,
  steady and heavy rain; no rain invented (none set, only snow, switched off); calm, and no sound chosen; particles
  the game can't use, entered from a rainy room; in and out with no jump, no cut and no new player; no leak into a
  room with none set; loading straight in; the setting turned off; rain or wind removed; six trips through the
  door and four play-tests leaving no player; an unplayable file; ambience volume and muting; the op (off is no
  setting, kept while no sound is chosen); every sentence Studio shows; an AI tool's change, undo, redo, save and
  reopen; the loader and the export's list.
- `tests/test_indoor_weather_gpu.py` (7, GPU lane, real hidden windows, real audio backend, silent): the whole of
  it by Studio's controls from the template as made, each sentence checked on screen; undo, redo, save, reopen;
  the walk from Studio and in the game alone; play-tests started outside and inside; the switch off; a save made
  indoors; a game started indoors.
- **Deliberate faults** (`faults.json`, `mutate_indoor.py.txt`): 16 of 16 fail a test. The three the brief names:
  weather audible in an indoor room that didn't ask (2 headless, 1 real-window test fail); the weather lost (the
  rain still taken from the screen: 8 and 3); a second loop at every door (11 and 4). Also: the setting working
  outdoors, not quieter, only the rain quieter, the last room's rain kept, a switched-off rain counting, on by
  default, any value accepted, the op's two rules, Studio's two sentences, the switch or the sentence missing.

  The first run left one alive: reading the room's rain only when it had asked. That condition changed nothing
  that could be seen (the value is only used when the room asks), so it is removed rather than kept untested.
- Local, on the code as committed: the two modules above, the existing sound modules and their real-window tests
  (18 GPU tests in all), the fast tier (6,184 passed, 7 skipped), ruff and mypy. The whole GPU lane and the full
  suite are left to CI and Extended on the pull request's head. The export check (section 6) is part of the
  demonstration tool, not of a CI test.

**The first Extended run failed, and is kept** (head `1d295590`, run 44056973057; CI on that head passed). Both
systems' second GPU shard failed in two of the new real-window tests: the walk's log counted pyglet's registered
players for the whole process, and in the full lane other tests had left three registered before this one began,
so "2 players" read as 5. A fault of the demonstration tool's log, not of the game: its other counts were already
taken from before the game started, and this one now is too. Corrected in the next commit and checked with three
players registered beforehand. Not rerun.

## 8. Listening checklist (for the owner)

Stages A, B and C1 are still **PENDING OWNER REVIEW**: their checklists are in
`docs/reviews/m21c1_spatial_audio_occlusion.md`, section 9. For C2, the command in section 5:

1. **Outside.** Rain and wind both plain? Is either too loud beside the other?
2. **Going in.** Does the weather sink smoothly as you step through the door? Any click, cut or restart?
3. **Inside.** Does it read as "weather outside the walls", or as "the same rain, turned down"? It keeps its
   brightness; a real roof would dull it.
4. **How much.** Is about a third right for a cottage? Too present, too faint?
5. **How fast.** It takes two to three seconds to settle. Too slow for a door?
6. **Rain against wind indoors.** Both drop by the same amount. Should the wind drop more?
7. **Going out.** Does it rise back naturally, with no jump and no doubling?

## 9. Limits

- Quieter, not muffled (section 2).
- The weather outside an indoor room is what that room says it is. Nothing checks that it matches the room its door
  leads to: a creator can set rain in the cottage and none in the village.
- Indoors the weather is fixed for the visit. Outdoors a rain effect can be switched during play and its sound
  follows; indoors there is no effect on screen to switch.
- One level for the whole room: no louder by a window, no quieter in a cellar. That would be acoustic zones.
- Snow has no sound, indoors or out, as before.
- CI's runners have no audio device, so CI checks players and levels, not sound.

## 10. Decisions for the owner

1. The listening, for A, B, C1 and C2.
2. The amount (0.35) and whether rain and wind should share it.
3. Whether an indoor room that hasn't asked should still hear its wind (section 4).
