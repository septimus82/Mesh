# M21B: Spatial Environmental Audio and Studio Authoring

Milestone 21 (Audio & Atmosphere), stage B: sounds a creator places in Mesh Studio that grow louder as the player comes near, weather that is heard as it falls and blows, and an Ambience volume for players. Built on `redesign/visual-editor` at `182a104` (M21A merged). The reference is [`docs/audio.md`](../audio.md).

**Technical audio: CONDITIONAL PASS. Human listening: PENDING OWNER REVIEW** (checklist below).

## 1. Sound emitters: the scene representation and the runtime

**Representation.** A sound emitter is an object with the `SoundEmitter` behaviour: `engine/behaviours/sound_emitter.py`, registered like `WaterSurface`.
- **Settings:** `sound`, `volume`, `radius` (full strength within, px), `distance` (heard up to, px), `stereo`, `loop`, `enabled`, `fade_in`, `fade_out`; checked by `sound_emitters.parse_emitter` with reasons.
- **Position:** its own `x`, `y` and, in HD-2D, `elevation`. Its ID is the object's ID.
- **Inherited from objects:** placement, dragging, copying, deleting, undo and redo, saving, and the Conditions tab.
- **No picture:** the game never draws it.

**Runtime** (`engine/sound_emitters.py`):
- **Lifecycle:** one soundscape per window; `reset` as a room starts loading, beside `reset_water`; `update` every frame, beside `audio.update`.
- **Listener:** the player (`_find_player_sprite`), otherwise the camera's centre, the established fallback.
- **Gain:** 1 inside the radius, a smoothstep down to 0 at the distance, measured in 3D in HD-2D rooms.
- **Pan:** the direction's sideways part, at most 0.75, and less inside the radius.
- **Level changes:** eased over about 0.12 s, so there's no zipper noise when the player jumps.

**Players.**
- **Range:** each emitter is one keyed ambience loop, `emitter:<room>:<id>`. Only emitters within reach have a player; one out of reach has none and decodes nothing. There's a hysteresis margin at the edge, and an emitter that drifts out and straight back is revived, not restarted.
- **Caps:** at most 12 active (the loudest), and at most 3 copies of one file.
- **Starts:** at most 2 streams open per frame.

**`AudioManager` extension** (narrow; M21A's semantics unchanged).
- **`play_loop(..., pan=, loop=)`:** asked again with the same path, only its volume and pan change. Before, each call restarted the fade, so a call every frame would never finish fading in.
- **Revival:** a loop still fading out after `stop_loop` fades back in.
- **Pan** is applied only when it changes, the way Arcade pans.

**Room changes, saves, cleanup.**
- **Leaving a room** stops its emitters (fading).
- **Coming back** registers the same keys again.
- **A loaded save** is its room loading.
- **Studio's Stop and window close** release everything (M21A's `shutdown`).
- **The editor stays silent:** the M21A switch now covers sounds and weather too.

## 2. Mesh Studio: the authoring workflow

| Step | In Studio |
|---|---|
| Open a room | Rooms list |
| Add a sound emitter | top bar **Sound** > **+ Add sound**, or Objects > **Sound** |
| Place it | click the 2D map, or the floor in the 3D view (at its height) |
| Choose its file | its inspector: **Choose sound...** > the project's sounds, **Mesh's sound library** (copied into `assets/ambience`), or **Import sound file...** (checked first; Studio says plainly if this computer can't play it) |
| Adjust it | Volume (%), Full strength within (m), Heard up to (m), Height (m, HD-2D), Stereo, Loop, On, Fade in/out |
| Move or remove it | drag it; Delete object; every change is one undo step |
| Save, reopen | Save; reopen shows it as saved, nothing unsaved |
| Hear it | Play (F4) |

**While editing:**
- **2D:** a sound shows as a speaker with two rings.
- **3D view:** an upright post with the rings on the ground at its height.
- **Selecting:** a click on the marker selects it, in 2D and 3D. The 3D view needed its own ray test, as water has.
- **In play:** none of this is drawn.

**The Sound panel** also lists the room's sounds, and holds its weather: Rain (Off, Light, Steady, Heavy), Wind (Calm, Breeze, Strong, Gusty), and the rain and wind sounds with their volumes. Studio had no rain control before; rain existed only as hand-written particles.

**Mesh's sound library** (`assets/ambience`, 2.2 MB in the repository): rain, wind, flowing water, birdsong, and forest or meadow.
- **Format:** 10 s mono 16-bit WAV loops at 22,050 Hz, so they play everywhere, pan fully, and loop without a seam (an equal-power crossfade at the join).
- **Made by** `tooling/make_ambience_library.py`, reproducibly (byte for byte), from CC0 recordings. The wind is synthesised.
- **Shipped:** they're on the wheel's allow-list, with their notice.

## 3. Weather heard

**Investigated first.** Mesh's weather is per-room data:
- `settings.particles`: rain, snow and leaves, as a particle layer;
- `settings.wind`: speed, direction and gusts;
- `settings.weather_exposure`: indoor rooms have no rain.

Within a room, the only runtime control is the particle layer's per-effect switch, which Studio's weather preview uses. There is no scripted weather change, and none was invented.

**Built on it:**
- **Rain** is as loud as `water.rain_rate`: the same measure of falling rain that ripples the water.
- **Wind** is as loud as `wind.speed_at` where the listener is: the room's wind with its gusts.
- **Easing:** both ease with a 1.2 s time constant. Rain that stops is mostly gone in 3 s and silent within about 6 s.
- **Separate:** they're two loops, `weather:rain` and `weather:wind`, each with its own volume, so a room with the same rain keeps the same loop.
- **Shared headroom:** when ambience adds up past about two full-strength sounds, everything is scaled down together, smoothly.
- **Music is untouched.**

## 4. Ambience volume

An **Ambience Volume** slider, beside Music and SFX:
- **Where:** the shared settings rows, so it appears on the pause menu's Settings page and the main menu's.
- **Persistence:** it reads and writes the player's `RuntimeSettings.ambience_volume` (persisted since M21A).
- **Live:** it applies at once to the loops playing, without restarting them.

The old `SettingsOverlay` (`SettingsV1` storage) has no ambience field and was left alone.

**Checked in the game** (`tooling/soundscape_studio.py menu`, the Lakeside copy, a scratch settings file):
- two DOWN presses selected **Ambience Volume**;
- five LEFT presses set it to 0.75, saved for the next game;
- Music and SFX stayed at 1.0;
- the rain and wind playing turned down on the same players, without restarting.

**Two things on that page are already on the unchanged engine** (`menu_baseline_182a104.webp`), so they're not M21B's and weren't touched (no unrelated UI changes):
- each slider's label is drawn under its own bar;
- each change raises a raw `UI_SETTINGS_SAVED` toast.

Both are worth a small follow-up.

## 5. Validation

**Automated tests:**
- `tests/test_sound_emitters.py`, 18 fast tests: the curve and pan; rising and falling on a walk past, with one player and never a restart; nothing decoded out of reach; HD-2D heights; a crowd of 40 capped, and quiet when standing still; room exit and return; disabled and soundless emitters; the editor silent; rain following the falling rain and fading out; light versus steady rain; wind gusts; the same rain across rooms; headroom; and the `play_loop` extension.
- `tests/test_sound_authoring.py`, 9 fast tests: the ops and their refusals; rain strengths keeping the other weather; weather sounds; the library; broken files; import and listing; export references; the scene loader.
- `tests/test_soundscape_studio_gpu.py`, 6 GPU tests: the 2D Studio workflow below, end to end, including undo and redo of creating, moving and editing a sound.
- **Generated docs:** `docs/behaviours.md` gains `SoundEmitter`. `docs/console.md` gains M21A's `set ambience`, which had never been regenerated.
- **Updated:** three menu tests, for the new row.
- **Default selection** (`-W error`): 10,000 passed. Two failures, then fixed: the exception ratchet (the decoder check now records what it swallows) and the generated-docs count (66 behaviours).
- **mypy:** 73, the baseline. **ruff gate:** ok.
- **GPU tier** (`MESH_GL_SMOKE=1`): 192 passed. The first full run failed two of the new tests: they counted pyglet's process-wide players, which earlier GPU tests leave registered. They now count from the workflow's start, and the window's own players.

**Studio, 2D** (`tooling/soundscape_studio.py studio2d`; hidden window; Studio's own input events):
- **Placing:** Sound panel > + Add sound > a click on the map: placed and selected. Undo removed it, Redo brought it back, and a click on its marker selected it.
- **Choosing and setting:** Choose sound... > Flowing water copied the file into the project. Volume, reach and distance were typed in; undoing the reach restored the default, and Redo set it again.
- **Moving:** dragged, then Undo and Redo, to the exact pixel.
- **Weather:** Steady rain and Breeze set the weather and both sounds.
- **Silent while editing:** 0 players throughout.
- **Save and reopen:** saved, closed and reopened identical, with nothing unsaved.
- **Play:** walking east, the stream rose from 0 to 0.25 near it and fell to 0 walking away. The rain faded in on entering; the wind varied.
- **Play/Stop:** five cycles, each with the loops while playing and 0 players after Stop; 0 after closing.

**Studio, HD-2D** (Lakeside Village, a copy; the original was only read):
- **Placed in the 3D view:** pond water by the inlet (radius 2.5 m, heard 11 m); birds in the north-west trees, 4 m above their ground (radius 3 m, 14 m); a meadow ambience (radius 6 m, 16 m).
- **Weather:** Steady rain and Gusty wind.
- **Save and reopen:** identical, with nothing unsaved.
- **Play/Stop:** five cycles, each with 2 players (rain and wind; the start is out of reach of all three) and 0 after Stop.

**Walking Lakeside** (`walklake`; arrow keys). The first fixed route was blocked by the market stall's crate, and the next by a tree trunk. So between the pond and the birds, the player steers along the engine's own navigation route (`hd2d_world.path`), still with arrow keys.

| Point | Heard (before master) |
|---|---|
| 1. Entrance, calm | wind 0.17 |
| 2. Crossroads | wind 0.26 |
| 3. The pond (bridge's north end) | **water 0.55**, wind |
| 4. Away from the pond | water gone |
| 5. Under the birds | **birds 0.63** |
| 6. Rain starts (the layer's switch) | rain eases to 0.60; birds and wind unchanged |
| 7. Calm again | rain eased away |
| 8. Through the south door, into the Village | nothing (the Village has no sounds); the Lakeside loops stopped |
| 9. Back through the Village's east passage | the room's rain and wind resume |
| 10. At the pond again | water 0.80 (inside its radius), meadow 0.05 |

After closing: 0 players.

**Export** (`exportlake`):
- `mesh export build` included all five sounds.
- The bundle, on its own engine, played the room's 3 emitters (water 0.73 near the pond), rain and wind, with 4 players and nothing unplayable; 0 after closing.

**Performance:** the village with 48 more emitters, 51 in all, walked across.
- **Soundscape cost:** 0.22 ms a frame on average; 95th percentile 0.16 ms.
- **One-off costs:** the first frame costs 26 ms and the second 7 ms, once per game: the audio driver starting and the first streams opening. After that the worst frame is 3.3 ms, one stream opening, with at most 2 per frame.
- **Players** peaked at 14: 12 emitters plus rain and wind. Audio calls averaged 5 a frame while walking.

**Silence:** every real-backend run used master volume 0. Players decode and run, but nothing reaches a speaker. Levels are read before the master volume.

**A recording of the walk.** `lakeside_soundscape_mix.wav` is 46 s of stereo at 22,050 Hz, peaking at −9.3 dBFS with no clipped samples. It's kept outside the repository, in `D:\Games\Mesh-audio-assets\evidence\m21b\`. It's a **controlled software mix**: each loop the engine played, decoded and mixed in software at the level and pan the engine gave it, frame by frame. It is not a capture of the sound card: nothing was played aloud, and Mesh has no output-capture path. It shows what the engine asked for, not how the backend's mixer or a speaker rendered it.

## 6. Assets and licences

Downloaded from the official pages (licence checked on each), kept outside the repository, with SHA-256 hashes in `tooling/audio_test_assets.json`:

| Recording | Author | Licence |
|---|---|---|
| "Rain (loopable)": `Rain OGG.zip` | Ylmir | CC0 |
| "Ambient Bird Sounds": `birds-isaiah658.ogg` | isaiah658 | CC0 |
| "Sea and River Wave Sounds": `VistulaShort.mp3` | RandomMind | CC0 |
| "Forest Ambience" (M21A) | TinyWorlds | CC0 |

**Not downloaded:** the footsteps pack, which M21B doesn't use. Only the five 10 s WAV loops made from these are in the repository.

## 7. The showcase project

`D:\Games\Lakeside Village - Soundscape` is the copy authored above, kept as a project with its original `config.json`.

**What it differs from the original in:**
- the Lakeside room's three sounds and its weather (Steady rain, Gusty wind, their sounds);
- `assets/ambience` (the five library loops it uses);
- Studio's own session files.

## 8. Scope and safety

**Not built here:** a new backend, DSP or reverb, acoustic zones or indoor muffling, adaptive music, voice, or scripted weather changes.

**Evidence** (`docs/reviews/m21b_evidence/`, 715 KB):
- **Screenshots** (WebP): the 2D picker, inspector and Sound panel, play, the 3D view, the reopened pond sound, and the menu with its baseline.
- **Reports:** each phase's JSON, local paths replaced by `<scratch>`.

The 4 MB mix stays outside the repository.

**Changed outside audio:** Studio gained a Sound panel, a Sound object and the 3D marker; menus gained one row.

**Untouched:** `main`, #344, the owner's Lakeside Village project, `user_settings.json`, stashes and other worktrees. Tooling runs point the player's settings file at their scratch folder, never a checkout's.

**No new `type: ignore`.**

## Listening checklist (for the owner)

**Two ways to listen:**
- **The software mix:** `D:\Games\Mesh-audio-assets\evidence\m21b\lakeside_soundscape_mix.wav`, 46 s; it plays on any device.
- **The real game, which is the better test:** open **`D:\Games\Lakeside Village - Soundscape`** in Mesh Studio from this branch, open Lakeside, Play, and walk to the pond. That's the authored copy, at its original volume; your own Lakeside Village is unchanged. The rain is on in that room: the Sound panel's Rain > Off turns it off.

1. **Distance.** Walking toward the pond, does the water grow gradually, with no sudden step? Does it fade away smoothly as you leave?
2. **Direction.** With headphones, is the water on the side the pond is on? Does it swing naturally as you turn past it, without jumping hard into one ear?
3. **Relative volumes.** Water, birds, meadow, rain and wind together: is any one too loud or lost? Does rain over everything feel natural?
4. **Rain starting and stopping.** Does the rain fade in and out naturally? Is anything abrupt?
5. **Loop seams.** Each library loop repeats every 10 s: can you hear the join, or the repetition itself?
6. **Clipping or crackle**, especially with rain and a stream together.
7. **Room changes.** Going into the Village and back: anything cut off harshly, or lingering?
8. **Ambience slider** (Esc > Settings): does it turn the environment down without touching music or sound effects?
