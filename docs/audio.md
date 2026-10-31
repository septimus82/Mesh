# Audio in Mesh

Mesh plays three kinds of sound, each on its own **bus**, and every bus is scaled by the **master** volume:

| Bus | What plays on it | Its volume |
|---|---|---|
| **Music** | a room's soundtrack; battle music | `music_volume` |
| **Ambience** | sounds in the world (a stream, birds in the trees) and the weather (rain, wind) | `ambience_volume` |
| **SFX** | one-shot sounds: footsteps, hits, interactions, UI | `sfx_volume` |

A sound's loudness is its own volume × its bus's volume × the master volume. Muting keeps the volumes, so unmuting restores them.

**When a change is heard:**
- **Music and ambience:** a volume change or a mute applies at once to the tracks and loops already playing, mid-crossfade included; nothing restarts.
- **Sound effects:** each one-shot takes its bus's level when it starts and keeps it. A change, or a mute, is heard from the next sound effect; any already sounding finish as they began (most last under a second).

**Where the volumes come from:**
- the project's `config.json` (`master_volume`, `music_volume`, `ambience_volume`, `sfx_volume`);
- the player's own settings: the Music, SFX and Ambience sliders in the pause menu's and the main menu's Settings, kept in `user_settings.json`;
- the console (`set volume`, `set music`, `set sfx`, `set ambience`).

## A room's music

A room's `settings` decide its music as it is entered: on walking in through a door, on loading a save, and on entering a room again.

In Mesh Studio: Audio > **Room music...** sets these for the room being edited: **Continue previous music** (no `music` setting), **Silence** (`null`) or **Play a track** (a project file; Import music file... copies one into `assets/music/`). Rooms > **Set as starting room** chooses the room a new game starts in (Milestone 23D).

| The room's settings | What plays |
|---|---|
| no `music` setting | **the music playing carries on**: a track from an earlier room, or silence |
| `"music": null` or `""` | **silence**: the music stops (or fades out) |
| `"music": "assets/music/theme.ogg"` | that track, at `music_volume` (0–1, default 1) |
| `"music"` set to the track already playing | it **carries on uninterrupted**: not restarted; only its volume eases to this room's |
| `"music"` set to a file that can't be played | the music playing carries on; the error is logged once, and the file isn't tried again until it changes |
| `"music"` set to anything else (a number, an object) | treated as no setting, with a warning |

Before Milestone 21A the scene loader gave every room `"music": null` when it had no music setting, so every room without music stopped it. Rooms written by Mesh's compact saving also lost an authored `"music": null` (it matched that default). Both are fixed.

**Loading a saved game:** a save records the music playing when it was made. A room with its own `music` setting plays that, as when it is entered. A room without one plays the music the save recorded. Saves made before Milestone 21A recorded no music: loading one into a room without a music setting keeps whatever is playing.

**Theme ambience:** a room with a `region_theme` and no music setting gets its theme's ambient track, when that file exists. None of the theme tracks (`forest_ambience.mp3`, `lava_rumble.mp3`, `void_hum.mp3`) ships yet, so these rooms keep the music playing.

## Crossfades

With `music_crossfade_enabled` on, in the project's `config.json` or a room's settings, a change of track is a crossfade:

- the new track starts at once while the old one fades out over `music_crossfade_out_s`;
- the new track fades in over `music_crossfade_in_s`;
- both play during the overlap;
- once the old track is silent, its player is stopped and released.

Off (the default), changes are immediate.

**Fading to silence:** with crossfade on, a room with `"music": null` fades the music out.

**Mid-crossfade changes:**
- **Going straight back** to a room whose track is still fading out fades that track back in from where it is; it doesn't restart.
- **Rapid room changes:** at most three tracks fade out at once; older ones are cut. Players can't pile up.

**Pausing:** fades continue while the game is paused (the music keeps playing under the pause menu).

## Sounds in the world (Milestone 21B)

A **sound emitter** is a sound heard from a place: a stream, birds in a tree, a humming machine. It plays louder as the player comes near and quieter as they leave, from their side in stereo. It works the same in 2D and HD-2D rooms.

**Placing one in Mesh Studio:**
1. Open the room.
2. Choose **Sound** in the top bar, then **+ Add sound**; or **Sound** in the Objects list.
3. Click the map where it's heard from. In an HD-2D room that's the floor under the mouse, at its height.
4. In its inspector: **Choose sound...**, from the project's sounds or Mesh's sound library. A library sound is copied into the project's `assets/ambience`, so the game and its export have it. **Import sound file...** brings in your own (checked first: Studio says plainly if this computer can't play it).
5. Set its volume, how far it's heard and at full strength (in metres; 1 m is a tile), stereo, loop, on/off and fades. In an HD-2D room, also its height.
6. Drag it to move it; delete, copy, undo and redo it like any object. Its Conditions (Show when) work as any object's: a sound they leave out of the room when it loads is silent.
7. Save. Press Play (F4) to hear it.

While editing it shows as a speaker with two rings: full strength inside the filled one, silent beyond the outer one. The game never shows it.

**How it's heard:**
- Between the two rings the volume fades smoothly: there's no sudden change at either edge.
- In an HD-2D room heights count: a bird 4 m up in a tree is further from the player at its foot.
- Out of reach, an emitter has no player at all: nothing is decoded, so a room can have many.
- At most 12 play at once (the loudest), and at most 3 copies of one sound.
- Leaving a room stops its emitters (fading); coming back starts them again.

**Settings** (`behaviour_config.SoundEmitter`):

| Setting | Meaning | Default |
|---|---|---|
| `sound` | the file (`.wav`, `.ogg`, `.mp3`) | none |
| `volume` | 0–1, at full strength | 0.8 |
| `radius` | px: full strength within it | 64 (2 m) |
| `distance` | px: heard up to it (more than `radius`) | 320 (10 m) |
| `stereo` | heard from its side | on |
| `loop` | plays round (off: once each time the player comes near) | on |
| `enabled` | on or off | on |
| `fade_in`, `fade_out` | seconds, when it starts and stops | 1, 1 |

**Mesh's sound library** (`assets/ambience`): rain, wind, flowing water, birdsong, and a forest or meadow. These are 10 s mono WAV loops: they play on every computer, and they loop without a seam. The four recorded ones are cut from CC0 recordings (authors and sources in `assets/NOTICE.md`); the wind is synthesised by Mesh.

## Weather heard

A room's rain and wind have sounds. In Studio's **Sound** panel:
- **Rain:** Off, Light, Steady or Heavy. That's the room's rain itself: it falls in the game.
- **Wind:** Calm, Breeze, Strong or Gusty.
- **Rain sound** and **Wind sound**, and their volumes. Turning rain or wind on without a sound chooses Mesh's own and copies it in.

**How they're heard:**
- The rain is as loud as the rain actually falling: the same measure as the ripples on water.
- The wind is as loud as it blows where the player is, gusts included.
- Both ease in and out over a second or two: rain that stops fades, it doesn't cut off.
- A room entered with the same rain keeps the same loop playing.
- An indoor room (`weather_exposure`) has no rain, so none is heard. Muffled weather indoors is Milestone 21C.

In the file: `settings.weather_sounds` (`rain`, `wind`, `rain_volume`, `wind_volume`).

**Changing weather during play:** Mesh's weather is set per room, so the weather heard changes with the room. Within a room, each rain or snow effect has an on/off switch on the particle layer (`set_enabled`), the one Studio's weather preview uses. The sound follows it. There are no scripted weather changes yet.

**Loudness together:** when the ambience playing would add up past about two full-strength sounds, every ambience sound is turned down together, smoothly. A stream beside rain beside wind never piles up.

## Mesh Studio

The editor is silent. A room's music, sounds and weather play in play-tests (F4), as they would in the game, and stop when the play-test does.

## For engine code

`window.audio` is the `AudioManager` (`engine/audio.py`).

**Music:**

| Call | What it does |
|---|---|
| `transition_music(path, fade_out_s=, fade_in_s=, volume=, loop=)` | crossfade (the scene loader's call) |
| `play_music(path, volume=, loop=)` | from the start, at once |
| `stop_music()` | stops all music at once |
| `snapshot_music()` / `restore_music(snapshot)` | battle music's hand-off |

**Ambience:**

| Call | What it does |
|---|---|
| `play_loop(key, path, volume=, fade_in_s=, pan=, loop=)` | keeps one loop per key: asked again, it isn't duplicated. Asked every frame with the same path (a sound emitter), only its volume and pan change; one still fading out after `stop_loop` fades back in |
| `stop_loop(key, fade_out_s=)` | stops that loop |
| `loops()` | the loops playing |

**Sound effects:** `play_sound(path, volume)`, `play_sound_at(path, world_pos, ...)`, `play_world_sfx(...)`. Distance attenuation, stereo pan and occlusion are unchanged.

**Volumes:**

| Call | What it does |
|---|---|
| `set_master_volume`, `set_music_volume`, `set_ambience_volume`, `set_sfx_volume` | set a volume |
| `set_muted(muted, bus="master")`, `is_muted(bus)` | mute or unmute everything, or one bus |
| `bus_gain(bus)` | a bus's volume × master, 0 while muted |

**Lifecycle:**
- `update(dt)` advances fades. The game calls it every frame, paused or not.
- `shutdown()` releases every player. The game window calls it when closing.
- `diagnostics()` reports what is playing, what is fading, the players held, the players released and the files that failed.
- `scene_music` (default on): Studio's editor turns it off, so rooms leave the music, their sounds and their weather alone.

**Sounds in the world:** `engine/sound_emitters.py` holds the soundscape: `window.soundscape`, `reset` on each room, `update` every frame. The behaviour is `engine/behaviours/sound_emitter.py`. Studio and AI tools edit through `project_ops`:
- `set_sound_emitter` and `sound_emitter_of`;
- `set_weather_sounds` and `weather_sounds_of`;
- `set_rain` and `rain_strength`.

## The playback backend and its limits

Playback is Arcade's `Sound` over pyglet's media player: XAudio2 on Windows, OpenAL or PulseAudio elsewhere. Measured with Arcade 3.3.3 and pyglet 2.1.11:

**What works:**
- **Overlap:** two streamed tracks play at once, each with its own live volume, so crossfades really overlap.
- **Looping:** a streamed track loops. Arcade's documentation says streamed sounds can't loop; with pyglet 2.1 they do.

**Limits:**
- **One player per streamed source:** a streamed source can't be played twice at once. Mesh opens a new stream for each track it starts, and never crossfades a track into itself (the same track carries on instead).
- **Releasing players:** a player must be released with `arcade.stop_sound`, not only paused. A paused player stays registered with Arcade for the rest of the game. That was Mesh's music before Milestone 21A: every change of track left one behind.
- **No effects:** there is no reverb, filtering or mixing graph; volume and pan are what each player has. A muffled sound, for an occluded source, is a separate `*_muffled` file.
- **No device check:** Mesh can't check that sound reaches a speaker. With no audio device, pyglet's silent driver plays nothing, and the game runs on.
- **Decoding depends on the platform.** WAV is decoded by pyglet itself, everywhere. MP3 and OGG need a decoder from the system:
  - **Windows:** Media Foundation. It decodes MP3; OGG Vorbis only with Microsoft's optional codec extension installed.
  - **Other systems:** FFmpeg's libraries or GStreamer.

  A file no decoder can read is logged once ("Can't play …"), and the music playing carries on. WAV is the format that plays everywhere; test an OGG or MP3 on the platforms a game ships to.
- **Truncated files:** a damaged file whose header is intact still loads. It plays as much as there is, and a looping one loops on that part.
- **Pan:** a mono sound pans fully, the way Arcade pans it: a position on the listener's left-right axis. A stereo file may pan less, depending on the driver. Mesh's library is mono for this reason.
- **Starting a stream:** it costs a few milliseconds. The first sound of a game also starts the audio driver (about 25 ms once). So emitters coming into reach start at most two a frame.
