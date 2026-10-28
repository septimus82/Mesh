# Audio in Mesh

Mesh plays three kinds of sound, each on its own **bus**, and every bus is scaled by the **master** volume:

| Bus | What plays on it | Its volume |
|---|---|---|
| **Music** | a room's soundtrack; battle music | `music_volume` |
| **Ambience** | persistent loops: wind, water, birds, room tone (Milestone 21B adds emitters that place them in the world) | `ambience_volume` |
| **SFX** | one-shot sounds: footsteps, hits, interactions, UI | `sfx_volume` |

A sound's loudness is its own volume × its bus's volume × the master volume. Changing a volume, or muting, applies at once to what is already playing: nothing restarts. Muting keeps the volumes, so unmuting restores them.

**Where the volumes come from:** the project's `config.json` (`master_volume`, `music_volume`, `ambience_volume`, `sfx_volume`); the player's own settings (`user_settings.json`: music, SFX and ambience); the console (`set volume`, `set music`, `set sfx`, `set ambience`).

## A room's music

A room's `settings` decide its music as it is entered: on walking in through a door, on loading a save, and on entering a room again.

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

## Mesh Studio

The editor is silent. A room's music plays in play-tests (F4), as it would in the game, and stops when the play-test does.

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
| `play_loop(key, path, volume=, fade_in_s=)` | keeps one loop per key: asked again, it isn't duplicated |
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
- `scene_music` (default on): Studio's editor turns it off, so rooms leave the music alone.

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
