# M17-W1 — waterfalls: evidence (never merge this branch)

Real Mesh engine output only: every picture is `Hd2dRenderer`'s own final picture from a hidden window (or, where
named "game window", the whole game window with its HUD; "studio" pictures are Mesh Studio's window). Nothing is
concept art or composed by hand; the sheets only lay real frames side by side with a label.

**The room** (`tooling/w1_waterfall_study.py`, made with the project ops as Studio or an AI would): a disposable
project from the HD-2D template, its start room turned into a glen — a plateau 3 m high in the north (sculpted), a
stone-painted cliff along y = 778 px, a natural pond at its foot (its bed sculpted 0.4 m down), a 3 m stream across the
plateau falling 2.9 m from its lip at the cliff's edge into the pond (`falls: [{"from": 2}]`, `mouth: "auto"`), its bed
carved (0.4 m), rocks scattered along the cliff top and round the pond, a boulder by the foot. Variants: evening (low
warm sun, the template's two lamps by the pond), evening + the room's haze ("evening") + warm bloom, the same stream
without its waterfall, and four more falls on parallel streams ("many"). The original Lakeside project is untouched.

## Sheets (`sheets/`)
| | |
|---|---|
| `01_day_evening_haze_bloom` | day, evening, evening with haze and bloom (the lamps glow, the water writes no emission), the game window |
| `02_angles` | front, from the east (yaw 70), from the west (yaw −60), high (pitch 55), low (pitch 12), from behind over the lip |
| `03_lip_and_foot` | the lip (stream → crest → curtain), the foot (boil, foam, ripples) by day and evening; the same river without its waterfall (what the engine drew for a steep stretch before) |
| `04_occlusion` | a character in front of the curtain (it hides it), rocks before its foot, from behind (the cliff top hides it), five waterfalls in one room |
| `05`–`07` | consecutive frames: the curtain (1/20 s apart), the lip and the foot (1/30 s): the streaks move down, the froth churns |
| `08_moving_camera` | the camera panning across the fall: the water's pattern stays put in the world |
| `09_curtain_animation.gif` | the eight frames of `05`, played (real frames, 50 ms each) |
| `10_studio_and_play` | Mesh Studio's River tool with the waterfall's controls, and the same room in Play |

`frames/` holds every full frame (1280 × 720) the sheets were cut from; `frames/studio/` Studio's and Play's windows.

## Data (`data/`)
- `checks_frames.json`, `checks_studio.json`: what the GPU tests assert (tests/test_river_falls_gpu.py), measured by
  tooling/w1_waterfall_checks.py on this machine (RTX 4070).
- `perf_rtx_720.json`, `perf_rtx_1080.json`, `perf_mesa_720.json`: timing (scripts/perf_w1.py; L4-4's method: modes of
  one room interleaved, order rotated, an untimed frame before each timed one, first 10 % dropped; GPU timer query on
  the RTX, wall time round `ctx.finish()` on llvmpipe).
- `plain_base_*.json`, `plain_head_*.json`: rooms without waterfalls on the base engine (1465258) and the branch's,
  the same project files (scripts/perf_plain.py).
- `no_waterfall_frames_base.json`, `no_waterfall_frames_branch.json`: SHA-256 of 24 frames of rooms without
  waterfalls (R1's streams, R4's stream into a pond, the village, M23B's campfire at night; three cameras, two times)
  from both engines: all identical, and the same draw calls (scripts/same_frames.py).
- `mutations.json`: 22 mutations, each caught by the test aimed at it (scripts/mutate.py).

## Scripts (`scripts/`)
`evidence.py` (frames and sheets), `perf_w1.py`, `perf_plain.py`, `same_frames.py`, `mutate.py`, `mesa_preload.py`
(loads Mesa's llvmpipe from a local copy of the pinned CI archive, for software-GL timing). They ran against the
feature worktree; paths in them are this machine's.
