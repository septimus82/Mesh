# Windows GPU test time (Astra, 12 November)

Question: where does the Windows `gpu` lane of Extended spend its time, and what can be removed without removing
coverage?

Short answer:

* The two most expensive tests are one dialogue test and one lighting-**controls** test (not `test_hd2d_lighting_gpu`,
  which is 23 s). Together: 19% of all Windows GPU test time.
* Neither is expensive because of what it asserts. Both are expensive because of how Mesh Studio's panels are worked:
  every mouse-wheel notch and every click makes Studio rebuild all of its panel widgets (about 0.3 s on a Windows
  runner), and the test driver then draws a frame (0.12 s on average there, 0.26 s in the dialogue's room).
* One bounded saving was found and made: the dialogue tool read an unchanged inspector twice, and scrolled back to the
  top after each read even when Studio was closed or the room left next. **63 of its 256 wheel notches removed; the
  tool's report is identical.** Locally 162 → 140 s (−14%); on a Windows runner about 40 s of that one test.
* The larger costs (Studio's full rebuild per notch; a drawn frame per notch) are not test redundancy. Changing them
  is a design decision, described at the end, and is **not** part of this change.

Evidence: `gpu_test_time_evidence/`.

## 1. Ranking from the existing JUnit files

Extended run 43751758799 (post-merge of #511 at `afc1757`, all green, attempt 1). `extended_43751758799_junit_ranking.txt`.

| gpu shard | tests | time in tests | job |
|---|---|---|---|
| Windows 1/2 | 271 | 1,408 s | 25.5 min |
| Windows 2/2 | 263 (+2 skipped) | 1,225 s | 22.4 min |
| Linux 1/2 | 238 | 710 s | 13.2 min |
| Linux 2/2 | 296 (+2 skipped) | 692 s | 13.1 min |

The same 534 tests take 2,633 s on Windows and 1,402 s on Linux (×1.88). Both use Mesa llvmpipe.

Ten most expensive tests on Windows (seconds; the same test on Linux):

| # | Windows | Linux | test |
|---|---|---|---|
| 1 | 277.0 | 136.8 | `test_dialogue_reopen_gpu` (one module fixture: `tooling/watchfire_r4_dialogue.py`) |
| 2 | 215.4 | 137.7 | `test_hd2d_lighting_controls_gpu::test_the_hd2d_panel_shows_only_what_the_renderer_reads` |
| 3 | 98.1 | 39.2 | `test_weather_authoring_gpu::test_the_environment_category_opens_the_weather_panel` |
| 4 | 72.1 | 36.8 | `test_hd2d_bloom_gpu::test_studio_glows_its_view_at_once_and_not_its_lines` |
| 5 | 68.7 | 53.9 | `test_terrain_gpu::test_studio_paints_live_one_stroke_one_undo_step` |
| 6 | 67.4 | 40.5 | `test_studio_workflow_polish_gpu::test_the_left_panel_scrolls_to_every_tool…[1280x720]` |
| 7 | 67.1 | 32.4 | `test_hd2d_post_gpu::test_studio_grades_its_view_at_once_and_not_its_lines` |
| 8 | 66.3 | 35.1 | `test_hd2d_haze_gpu::test_studio_hazes_its_view_at_once_and_not_its_lines` |
| 9 | 65.0 | 14.9 | `test_water_gpu::test_a_creator_places_shapes_turns_and_banks_water_in_studio` |
| 10 | 59.4 | 43.1 | `test_hd2d_asset_pipeline_gpu::test_models_import_through_studio_with_their_report` |

Most expensive modules on Windows: dialogue reopen 277 s, lighting controls 215 s, terrain 199 s, water 182 s, weather
authoring 148 s, fire 113 s, bloom 108 s, workflow polish 100 s. The 25 most expensive tests are 62% of the time.

**Critical path.** In that run it was Windows shard 1. Which Windows shard is slower is decided mostly by the runner
each one gets: in the measurement run below, shard 2 got the slower machine and took 32.5 min against shard 1's
28.5 min. On the same CPU model (Xeon Platinum 8573C, in different runs) shard 1 spent 1,446 s in pytest and shard 2
1,853 s: on equal hardware shard 2 is the longer one.

## 2. What the time goes to

A measurement-only pytest plugin (`gpu_cost_plugin.py.txt`; it wraps the test drivers from outside and changes nothing
they do) recorded, per test: setup, call and teardown time, and inside them the time in `Studio._rebuild`, in frames
drawn by the test drivers, in opening Studio or a game window, and in `subprocess.run`.

* **On CI:** branch `evidence/gpu-test-time-split` (`afc1757` plus the plugin on the gpu lane; never to be merged),
  Extended run 43763080838, all green. `ci_43763080838_split_*.txt` (the per-test files are that run's lane artifacts,
  `gpu_cost/`).
* **Locally:** the whole gpu lane at `afc1757`, Windows 11, a physical NVIDIA card, Python 3.13: 535 passed, 1 skipped,
  1,710 s in tests. `local_lane_split_afc1757.txt`.

| | Windows CI (both shards) | Linux CI (both shards) | local (physical GPU) |
|---|---|---|---|
| time in tests | 3,392 s | 1,561 s | 1,710 s |
| Studio panel rebuilds | 681 s, 20% (2,304; 0.30 s each) | 495 s, 32% (2,303; 0.21 s each) | 567 s, 33% (2,303; 0.25 s each) |
| frames drawn by the Studio driver | 1,273 s, 38% (10,717; 0.12 s each) | 410 s, 26% (10,784; 0.04 s each) | 239 s, 14% (10,793; 0.02 s each) |
| frames of the game-window driver | 26 s | 16 s | 19 s |
| opening Studio (its window, first rebuild and frame included) | 241 s, 7% (102) | 70 s, 5% | 124 s, 7% |
| subprocesses (exports, game launches) | 91 s, 3% | 36 s, 2% | 147 s, 9% |

* **Rendering on llvmpipe is the largest single cost on Windows** (38%), and it is where Windows and Linux differ
  most: the same frames cost three times as much there.
* **Panel rebuilds are Python, not GPU** (widget construction in the UI library). They cost about the same everywhere
  and are the largest cost on Linux and locally.
* Closing windows is 2–5 s for the whole lane. Exports and game launches are 3% on Windows. Fixed sleeps in the tools
  behind the top tests: half a second in each of the bloom, haze and grade tools (30 frames of Play at 1/60 s), and
  the terrain gate's deliberate slow frames (its fault injection). Nothing there to remove.
* The plugin sees only this process: what a tool does inside its own subprocess is counted as subprocess time.

The top two tests on a Windows runner (measurement run):

| | total | rebuilds | driver frames | Studio opens | subprocesses |
|---|---|---|---|---|---|
| dialogue reopen | 311.5 s | 136.6 s (359; 0.38 s) | 131.7 s (514; 0.26 s) | 12.4 s (5) | 10.7 s |
| lighting controls | 301.8 s | 126.9 s (331; 0.38 s) | 125.3 s (447; 0.28 s) | 4.4 s (2) | — |

Why a rebuild is slow: `Studio._rebuild` clears and rebuilds every widget of the top bar and both panels, about 55
buttons and 24 labels, for any change of state, including one wheel notch (`on_mouse_scroll`). Under a profiler, 60% of
a rebuild is the UI library binding each widget's properties, which inspects each listener's signature every time
(1.4 million binds in the dialogue run). An experiment that memoised that inspection (`experiment_listener_cache_not_for_merge.json`)
cut the dialogue run's rebuild time from 90.6 s to 66.5 s locally (−27%), with the same report. It patches the
library's internals and is not proposed.

## 3. What was redundant, and what was not

### Dialogue reopen (changed)

`tooling/watchfire_r4_dialogue.py` wrote, read, saved, reopened and edited a conversation with 256 wheel notches
(`dialogue_before_run*.json`: which line asked for each). Of those:

| | notches | |
|---|---|---|
| reading the inspector from top to bottom, 7 times | 63 down | needed, except the repeated read's 8 |
| going to the top before a read | 21 up | needed |
| finding lines to click (`label_of`): to the top, then down to the line | 109 | kept as it is |
| **the scroll back to the top after each read** | 63 up | 47 before Studio is closed, the room is left or the run ends: nothing uses the top. 8 before a lookup that goes to the top itself. 8 belong to the repeated read |
| of these, **the read at C repeated** to take one value from it (`C_next_line_button`) | 16 (8 down, 8 up) | the same panel, nothing done in between |

Changed:

1. `all_labels()` no longer scrolls back to the top. Whatever looks for something next goes to the top itself
   (`down_until` always starts with `to_top`), so the one read that is followed by a search (B) costs the same as
   before, and the five that are followed by a save and reopen, a room change or the end cost nothing.
2. `C_next_line_button` is taken from the read made one statement earlier.

Result: 256 → 193 notches, 359 → 296 rebuilds, 514 → 451 frames.

Not changed: every read still starts at the top and goes to the real bottom; every line lookup scrolls exactly as
before; the five Studio sessions, the saves, undo and redo, the room change, the two game launches and the export are
untouched. Scrolling up is still exercised: 99 notches up remain (78 in lookups, 21 before reads).

### Lighting controls (measured, not changed)

331 rebuilds, 180 of them wheel notches (`lighting_controls_wheel_notches.json`): 106 while finding each button to
click, 42 while finding each box to type into, 32 in five surveys of the panel. Every one belongs to a step the test
asserts on: the sweep clicks every button and types into every box for two lamps, and undoes each. The only notches
that read nothing new are the surveys' way back up (20 notches, about 13 s on Windows, 4% of the test), which the
shared driver does for every search. Changing the shared driver for that is not worth its risk. No change.

### Elsewhere

The remaining tests in the top ten each open Studio once or twice and do distinct work. No repeated project
construction, repeated export or duplicated window was found in them.

## 4. Before and after

The dialogue tool alone, driven directly (hidden windows, Windows 11, physical GPU), alternating versions:

| | runs | total | rebuilds | driver frames | wheel notches |
|---|---|---|---|---|---|
| before (`afc1757`) | 3 | 162.4, 165.3, 161.2 s | 359 (90.6, 89.7, 89.9 s) | 514 (30.7, 30.5, 30.6 s) | 256 |
| after | 4 | 140.7, 140.1, 139.7, 140.0 s | 296 (74.6, 74.3, 73.9, 73.9 s) | 451 (25.8, 25.8, 25.7, 25.7 s) | 193 |

Median 162.4 → 140.05 s: **−22.3 s, −13.8%**. Counts are exact and the same in every run.

**The report** (every recorded value: what is shown and stored at A–F, the files, the game's and the exported game's
conversation) is identical in all seven runs and between the versions, apart from the export's log text (it names the
output folder).

Expected on CI, from the per-rebuild and per-frame costs measured there: 63 × (0.38 + 0.26 s) ≈ **40 s on a Windows
runner** (13% of that test, about 2.5% of shard 1's test time) and 63 × (0.31 + 0.09 s) ≈ 25 s on Linux. The module is
in shard 1 on both systems. Whether Extended as a whole ends sooner depends on which Windows shard is the slower one
in that run (section 1). The PR records what CI measured.

## 5. Coverage

* Existing assertions: unchanged, on identical data.
* New: `test_each_look_at_the_conversation_reads_the_whole_inspector_once`. The tool now records, for each read of the
  inspector, that it started with nothing above and ended with nothing below (`inspector_reads`). The test requires
  six reads, each complete.
* Breakage checks (`breakage_checks.json`; each run against `tests/test_dialogue_reopen_gpu.py` in hidden windows):

| deliberate breakage | result |
|---|---|
| (none) | 6 passed |
| a read is made twice again | new test fails |
| a read stops before the inspector's last rows | new test fails; **the five existing tests pass** |
| a read takes only what the inspector shows first | new test and two existing tests fail |
| a search starts where the inspector happens to be, not at its top | all six fail |

  So a read that silently misses the end of the inspector was not caught before this change, and is now.
* The fixture's environment isolation (#505) is untouched; `tests/test_gpu_fixture_env_isolation.py` passes.

## 6. For design review (not done here)

1. **Studio rebuilds every panel widget on every wheel notch and click.** 20% of Windows GPU test time, 32% on Linux,
   and a creator pays it too: about a quarter of a second per notch on a fast desktop. Options: rebuild only the panel
   that scrolled (the top bar already has `_refresh_top_bar`), or keep widgets and move them. This is a change to
   production Studio code with its own risks (stale fields, focus, tooltips), so it needs its own brief.
2. **The drivers draw a frame after every wheel notch.** In the dialogue test half of the frames are that. On
   llvmpipe a frame of an HD-2D room costs 0.26 s. Not drawing between notches would reduce frames the tests draw,
   which the lane's rules protect; it is listed only so the cost is known.
3. **Looking before scrolling.** `label_of` goes to the top before every lookup even when the line is on screen
   (109 notches). A person would click what they see. It changes which scroll positions the clicks happen at, so it
   was left alone.

## 7. Limits

* One CI measurement run and one reference run; hosted runners differ by up to ×1.5 between runs (CPU model and
  calibration are in each lane's summary). Shares are more stable than seconds.
* Local timings are on a physical GPU, where frames are cheap. The CI figures are the ones that describe the lane.
* The saving is one test's: about 40 s of a 25-minute shard. It does not change the lane's shape.
