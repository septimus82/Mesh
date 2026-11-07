# M21A: Audio Foundation and Scene Music

Milestone 21 (Audio & Atmosphere), stage A: scene music that behaves as documented, real crossfades, three audio buses, and players that are released. Built on `redesign/visual-editor` at `c386384`. The reference for creators and engine code is [`docs/audio.md`](../audio.md).

## 1. What Mesh had (audited on `c386384`)

**Working, kept as it was:**
- **`AudioManager` (`engine/audio.py`):** short sounds cached; `.wav`, `.ogg` and `.mp3`; master, SFX and music volumes.
- **Positional sound** (`play_sound_at`, `play_world_sfx`):
  - distance attenuation (linear, inverse, square) and stereo pan;
  - an occlusion query and `*_muffled` variants for occluded sounds;
  - recent plays kept for diagnostics.
- **Hot reload** of cached sound effects, keeping the last good version.
- **Battle music hand-off** (`snapshot_music` / `restore_music`).
- **Per-frame update:** `engine/game_runtime/tick.py` calls `audio.update` every frame, also while paused.
- **Startup:** `engine/game_parts/audio_coordinator.py` creates the manager and applies the config's and the player's volumes.
- **Settings:** the player's music and SFX volumes in the pause, settings and main menus, saved in `user_settings.json`. The console has `music`, `stopmusic` and `set volume|music|sfx`.

**Partly there:**
- **The crossfade** was sequential: the old track faded out and stopped, then the new one started and faded in. They never overlapped, and it was off by default.
- **Theme ambient music** (`region_theme`) pointed at three `.mp3` files that were never shipped, and its code could never run (see defect 1).

**Missing:**
- an ambience bus, and any persistent loop;
- muting;
- releasing audio when the game closes;
- any record of the music in a save.

## 2. Defects reproduced, then fixed

Each was reproduced on `c386384` first. The probes use the same scratch starter project with the repository's two music loops:
- a hidden game window on the real audio driver;
- Mesh Studio driven through its own input events.

| # | Defect, as reproduced | Fix |
|---|---|---|
| 1 | **A room without music stopped the music.** The scene loader's defaults gave every room `"music": None`, so the lifecycle's "no setting: carry on" branch never ran. Entering `no_music_setting` after `with_music` gave `music None`. | `music` removed from `DEFAULT_SETTINGS`. Missing means carry on; `null` means silence. |
| 2 | **The same track restarted** on entering a room that plays the track already playing: "Stopped music", then "Playing music" from 0:00. | The track playing carries on; only its volume eases to the room's. |
| 3 | **The crossfade was sequential**: fade out, stop, start, fade in. Each new change also restarted the fade-out timer, so the volume jumped back to full. | A real overlapping crossfade (below). |
| 4 | **Music players leaked.** Stopping music only paused its player, which stayed registered with Arcade. Baseline, crossfade off (the default): after 5 Studio Play/Stop cycles and 20 room changes, **33 players were registered, and still 33 after the window closed**. | Players are released with `arcade.stop_sound`. Same probe on this branch: 0 registered at every step, 0 after closing. |
| 5 | **Mesh Studio's editor played the room's music.** It played on opening, restarted on each edit's reload, and carried on after a play-test's Stop. | The editor is silent; music plays only in play-tests and stops with Stop. |
| 6 | **Closing the game released nothing.** | `GameWindow.close` calls `audio.shutdown()`. |
| 7 | **A missing music file** was tried and logged again on every entry (5 entries, 5 errors), and the room fell silent. A **missing sound effect** likewise logged an error on every play (a missing footstep: once per step). | Each is logged once and not retried until the file changes; the music playing carries on. |
| 8 | **Compact saving dropped an authored `"music": null`**: it equalled the old default. | It's kept now that the default is gone. |
| 9 | **Theme ambient music** would point rooms at unshipped files once defect 1 was fixed. | It applies only when the file exists. |

**Checked, not a defect:** a room with a malformed `music` or `music_volume` fails the scene validator, and the loader loads an empty fallback room. That is unchanged. The music code also tolerates such values (treated as unset, warning once), in case validation is bypassed.

## 3. What was built

**Scene music semantics** (`engine/scene_lifecycle_controller.apply_scene_music`):

| Case | Behaviour |
|---|---|
| 1. Entering a room with no music setting | the music carries on |
| 2. Explicit silence (`null`, `""`) | the music stops, or fades out |
| 3. The track already playing | it carries on, not restarted |
| 4. A new track | it crossfades in, or switches at once |
| 5. Returning to an earlier room | the same rules apply; a track still fading out fades back in from where it is |
| 6. Loading a save | a room with its own music plays it; a room without plays what the save recorded (new `meta.music`); older saves keep what is playing |
| 7. Old or malformed configuration | rejected by the validator as before, or treated as unset |

**Crossfade** (`AudioManager.transition_music`):
- **Overlap:** the new track starts at once while the old one fades out; both play, and the old one's player is released when silent.
- **Going back mid-fade:** fades the old track back in.
- **Rapid changes:** at most 3 tracks fade at once.
- **Explicit `play_music`** still means "from the top, now".
- The default stays **off**, as before (see the decision below).

**Buses:**
- **`music`, `ambience`, `sfx`,** each × master.
- **Muting:** `set_muted(muted, bus)` for everything or one bus, keeping volumes.
- **Live changes:** `set_*_volume` and muting apply at once to the music and ambience playing, mid-crossfade included. A one-shot sound effect takes the SFX bus's level when it starts: a change is heard from the next one.
- **Ambience volume** goes in `config.json`, `user_settings.json` and the console (`set ambience`). There's no menu slider until something plays on that bus (M21B).

**Ambience loops:**
- `play_loop(key, path)` and `stop_loop(key)`: one loop per key, never duplicated when a room loads again. A different path crossfades.
- These are the seam M21B's emitters use. No room or Studio authoring uses them yet.

**Lifecycle:**
- `shutdown()` on window close; Studio's editor calls it too.
- `diagnostics()`, and the `released_players` count.

## 4. Validation

**Automated tests:** `tests/test_audio_buses_and_scene_music.py`, 21 fast tests on a stand-in backend that counts every player made and released:
- the 7 semantics cases;
- crossfade overlap, levels and release;
- going back mid-fade;
- rapid changes and the cap, ending with zero players;
- a missing file tried once;
- malformed settings;
- the editor switch;
- saves (recorded, restored, the room's own music winning, older saves);
- bus arithmetic, mid-crossfade volume changes, mute and unmute;
- SFX never touching music;
- loops not duplicated;
- shutdown releasing everything;
- `play_music`'s meaning kept.

The existing battle-music, spatial-audio and hot-reload contracts pass unchanged.

**Real audio files (owner's amendment):** both CC0 downloads come from their official pages; no paid assets and no accounts. They stay outside the repository, in `D:\Games\Mesh-audio-assets\downloads`. [`tooling/audio_test_assets.json`](../../tooling/audio_test_assets.json) records each file's author, source, licence, original name, size and SHA-256, and the smoke tool checks the hash before use.

| File | Author | Licence | What it tests |
|---|---|---|---|
| `TownTheme.mp3` (1.3 MB, 97 s) | cynicmusic | CC0 | long MP3 music, its crossfade and loop |
| `Forest_Ambience.mp3` (717 KB, 45 s) | TinyWorlds | CC0 | the ambience bus |

**Not downloaded:** Kenney's RPG Audio and Interface Sounds (CC0 on their pages). kenney.nl answered **403** to an automated download of its signed links, so I reported it rather than working around it. Mesh's own synthesised effects (`assets/sounds/*.wav`) stand in for SFX.

**Not yet:** the M21B sources (rain, birds, footsteps, river) wait for M21B.

**Decoding** (loaded, nothing played; Windows, pyglet's WAV decoder and Windows Media Foundation):

| File | Result |
|---|---|
| WAV (Mesh's loops and effects) | decoded, both stored and streamed |
| MP3 (both CC0 files) | decoded, both stored and streamed |
| OGG (one of the owner's RPG Maker files, read in place, never copied) | decoded |
| an empty `.wav` | refused (`EOFError`) |
| a text file named `.ogg` | refused ("no decoders") |
| truncated `.mp3` and `.wav` | load and play the part there is |

The repository's only `.ogg` is a 4-byte placeholder, so OGG coverage in the repository waits for a real CC0 file (Kenney's packs are OGG).

**Real backend, silent:** `tooling/audio_smoke.py` uses pyglet's **XAudio2** driver in hidden windows. The test project's master volume is **0**, so every player decodes, runs, advances and loops but outputs nothing. Levels are read before the master volume. The tool reads the backend's own state: registered players, and each player's `playing`, `time` and volume.

*Earlier runs, before the amendment, did play Mesh's short synthesised loops aloud for a few seconds each: about seven runs.*

**Game, crossfade on (1 s):**

| Check | Result |
|---|---|
| WAV → WAV crossfade | for 0.8 s both players played, each advancing 0.21 s per 0.2 s; old 0.4 → 0.1 (its room's 0.5 × fade), new 0.2 → 0.8; afterwards 1 player, the old one stopped |
| WAV → MP3 (Town Theme) | the same: old 0.8 → 0.2, new 0.2 → 0.8, both advancing |
| Room without music, same track | the same player carried on (time 1.3 → 2.0 → 3.3 s) |
| MP3 loop seam | sought to 0.5 s before the end: 96.99 s → 0.49 s, playing, the same player. Looping needs pyglet's end-of-stream event, which `arcade.run` delivers in a game; the harness now delivers it too |
| Explicit silence | 0 players |
| 60 rapid room changes | at most 3 registered, 1 at the end |
| Pause and resume | a crossfade started before pausing finished while paused; resumed, the same track carried on |
| Save and load | saved in a room without music (recorded the dungeon theme); silence; loading → the dungeon theme again |
| Missing, empty, not-audio | each left the music playing (the same player); each listed as unplayable, tried once |
| Truncated MP3 | played and looped on what there is |
| Ambience loop (Forest Ambience) | asked for three times: one player. The ambience bus at 0.5 → its level 0.4, the music's unchanged at 1.0. Stopped with a fade → released |
| Music bus mute and unmute | the same player throughout |
| Close | 0 registered |

**Game, crossfade off:** the same checks, with immediate switches; 60 rapid changes peaked at 1 player, 41 were released, 0 were left.

**Mesh Studio, with Town Theme as the start room's music:**
- **Editor:** silent on opening and after an edit's reload, with 0 players.
- **10 × Play/Stop:** each Play played Town Theme (1 player, playing); each Stop gave silence and 0 players.
- **Close:** 0.

**Export:** `mesh export build` copied all three tracks. The bundle, run on its own engine, played Town Theme (playing, 1.6 s in, 1 player); 0 after close.

**SFX:** silent runs don't play effects. `play_sound` skips a sound at volume 0, an M21A optimisation kept. The effects are covered by decoding and by the stand-in backend's bus tests.

**2D and HD-2D compatibility:** the smoke runs are on a fresh 2D starter project. The test gates below cover HD-2D (no HD-2D room sets music; Lakeside Village is untouched).

**Test gates:**
- **Default selection** (CI's tests tier, `-W error`): 9,973 passed. One failure, then fixed: the broad-exception ratchet (`test_scan_exception_policies_contract`), where a new catch counted as silent; it's now narrowed to `OSError`/`ValueError`.
- **Fast tests, after that fix:** 82 audio, ratchet and related tests passed.
- **GPU tier** (every hidden-window test, `MESH_GL_SMOKE=1`): 186 passed.
- **Evidence:** the smoke tool's reports are in [`m21a_evidence/`](m21a_evidence/), with local paths replaced by `<scratch>`.
- **ruff and the ruff gate:** ok.
- **mypy** (fresh cache): 73, the baseline.

## 5. The backend's limits

Arcade 3.3.3 on pyglet 2.1.11 supports what M21A needs:
- two streamed tracks overlapping, each with its own live volume;
- looping streamed tracks: Arcade's documentation says they can't loop, but with pyglet 2.1 they do.

The limits:
- **A streamed source plays once at a time:** a track never crossfades into itself. The same track carries on instead.
- **Players must be released** with `stop_sound`. Pausing alone leaks; that was defect 4.
- **No effects:** no DSP, filters, reverb or mixing graph. Volume and pan per player; occlusion uses pre-made `*_muffled` files.
- **No speaker check:** nothing confirms sound reaches a speaker, and without a device pyglet plays silently.
- **Platform decoders:** MP3 and OGG need the system's decoders (Media Foundation on Windows, where OGG needs Microsoft's optional codec; FFmpeg or GStreamer elsewhere). WAV plays everywhere.

No library replacement is proposed.

## 6. For M21B: environmental sound without another rewrite

**Emitters:** a Studio-placed emitter (water, wind, insects) becomes an ambience loop: `play_loop(f"{room}:{emitter_id}", path, volume=...)`.
- **Volume:** loading the room again asks for the same key, so nothing is duplicated.
- **Leaving the room:** an emitter not in the new room is stopped with `stop_loop(key, fade_out_s=...)`.
- **Spatial gain:** each frame, an emitter's volume is its distance gain (the existing `_attenuate`) × its own volume, through the same call.
- **Pan:** a small setter on `_Track` (pyglet's `player.position`, the way Arcade pans).

**Weather:** the room's weather (M18) maps rain and wind strength to loop volumes on the same bus.

**Player control:** an Ambience slider joins the menus beside Music and SFX once something plays on the bus; the setting already persists.

**Out of scope:** acoustic zones, occlusion of loops and adaptive music are M21C. They'd use the per-track volume and a second volume factor, not a new engine.

## 7. Owner decisions

- **Crossfade by default?** `music_crossfade_enabled` stays off, as it was, so existing games keep their immediate changes. Turning it on by default (1 s each way) would make every Mesh game crossfade. That is the owner's call.

## Listening checklist (for the owner)

Run it from the M21A worktree when you're at the PC. It plays about 70 s through the speakers at master volume 0.7, captioning each step in the terminal:

```
py -3.13 tooling/audio_smoke.py setup artifacts/listen
py -3.13 tooling/audio_smoke.py listen artifacts/listen
```

(`artifacts/` is ignored by git; delete `artifacts/listen` afterwards.)

Listen for:

1. **Crossfade smoothness.** At steps 3 and 4, does one track hand over to the next with no dip to silence, no sudden jump and no stutter?
2. **Relative volumes.** Is Town Theme much louder or quieter than Mesh's loops? Does the ambience (step 6) sit under the music? Are the four sound effects (step 8) too loud or too quiet beside the music?
3. **Clipping.** Any crackle or distortion when two tracks overlap, or at the loudest moments?
4. **Loop seams.** At the dungeon theme's 4-second loop (step 1) and Town Theme's end-to-start (step 5): any click, gap or jump?
5. **Unexpectedly loud sounds.** Anything that made you reach for the volume?
6. **Bus changes.** At steps 7 and 9, does only the intended category get quieter, without a restart?
7. **Silence.** At step 10 the music fades out over 1 s; is anything still audible after?

## Verdict

**Technical audio: CONDITIONAL PASS.**
- Music plays reliably, and tracks crossfade with real overlap (WAV and MP3).
- Music, ambience and SFX volumes are independent. Music and ambience change live; sound effects from the next one played.
- Room changes, Play/Stop cycles, saves, pauses, missing or broken files and closing leave no duplicated or leaked players, in deterministic tests and on the real backend.

Conditions:
1. the owner's review of the semantics change: rooms without music now carry the music on, where before they silenced it;
2. CI on the draft PR;
3. the crossfade-default decision;
4. OGG coverage in the repository, once a CC0 OGG can be fetched (Kenney blocked automated downloads).

**Human listening: PENDING OWNER REVIEW.** Nothing here shows the audio sounds right to a person. Decoding, players running and volume numbers are not proof that the mixing, loudness, seams or transitions are pleasing to hear. Final audio-quality acceptance waits for the checklist above.
