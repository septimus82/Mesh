# GPU lane performance, Phase 1 (#422)

Goal: shorten the Linux and Windows `gpu` lanes (Extended acceptance) without losing any tests, assertions,
simulation frames or rendering coverage. No selection, marker, threshold, xdist or sharding change; the required PR CI
is unchanged.

## What changed

1. **StudioDriver framebuffer capture** (`tooling/hd2d_studio_demo.py`).
   - **`advance(n)`** updates and draws `n` frames without reading the framebuffer back.
   - **`frame(n)`** is `advance(n)` plus the read-back, and still returns the picture.
   - **The driver's own input methods** (`key`, `click`, `drag`, panel scrolling, `button`, `type_into`) now call
     `advance()`.
   - **261 tooling statements** that discarded `frame()`'s picture now call `advance()`. An AST check confirms that every
     `advance()` call's value is unused.
   - **Kept as `frame()`:**
     - every call that uses the picture (screenshots, pixel checks, clip frames);
     - every frame inside a timing measurement (12 sites). One of them is `m20b._stroke`, whose `frame_ms` the terrain
       test asserts `< 60`. Those numbers still measure exactly what they did, so no limit gets easier.
   - **Caller audit:** only `d`, `d()` and `driver` receivers were converted, all of them StudioDrivers.
     `HiddenGame.step()` (update only) and `draw()` were left as they are.
2. **Dialogue scrolling** (`tooling/watchfire_r4_dialogue.py`).
   - **Before:** fixed 40-notch wheel sweeps (to the top, down through the list, and back) for every read of the
     inspector and every line lookup.
   - **Now:** scrolling stops when Studio's own "more above / below" count (`_panel_more`, the same boundary the
     driver's `_scroll_both` uses) says the end is reached.
   - **Coverage kept:** every scroll position is still read, now through to the real bottom.
   - **Bounded:** 100 notches, then a clear `AssertionError` naming the side that was never reached.
3. **Review media** (`tooling/review_media.py`).
   - **Encoding:** the studies' 11 animated-WebP encode sites go through `save_clip`, which encodes only when
     `MESH_REVIEW_MEDIA` is on. Most of them used `method=6`, WebP's slowest, and no test asserts on any of them.
   - **Default:** on when a study is run by hand. `tests/conftest.py` sets `MESH_REVIEW_MEDIA=0` for a test run unless it
     is already set, and `MESH_REVIEW_MEDIA=1` writes the clips during tests too.
   - **Frames kept:** every clip frame is still drawn and read back; only the encoding is skipped.
   - **Test:** `tests/test_review_media.py`.

## Local evidence (Windows, RTX 4070, Python 3.13, the full `gpu` lane at base `0c46e27` and at this branch)

A counting pytest plugin recorded framebuffer read-backs (`arcade.get_image`), animated WebP encodes, and drawn frames
and wheel events per module.

| | base | branch |
|---|---|---|
| selected tests | 268 | 268, same identities, every outcome identical |
| framebuffer read-backs | 7,758 (90.9 s) | 3,428 (36.6 s) |
| animated WebP encodes | 4 (45.6 s; the water pond pan alone 33.5 s) | 0 |
| dialogue module: frames drawn / wheel events | 1,537 / 1,289 | 514 / 266 (5/5 passed) |
| sum of test times | 1,062 s | 956 s (−10%) |

- **Pixel checks:** modules with pixel assertions (shadow corners, compositing and geometry; character shadows; viewport
  HUD; scene particles; HD-2D lighting) read back exactly as often as before.
- **Removed frames:** the only frames no longer drawn are the dialogue's wheel notches at a top or bottom, which Studio
  ignores (`on_mouse_scroll` changes nothing there).
- **A bug caught on the first local run:** the bulk conversion had also caught a chained line,
  `d.frame(2).convert("RGB").save(...)`, in `m19b_water_study`. It is fixed, and the AST check now guards against it.
- **Base failures on this machine:** 60 GPU tests fail locally at base too, mostly pixel and shadow checks on the
  physical NVIDIA card. CI's llvmpipe is the authority, so locally this only shows that the branch adds no new failure.

## CI evidence: Mesa llvmpipe, where the lane runs

Base: the two post-merge runs of `0c46e27`, 41342363305 (push) and 41342368535 (pull_request). Branch sample 1: run
41351787528 at `2b175ec`.

**Selection:** both systems ran 268 tests with identical identities and outcomes: 267 passed and 1 skipped, the skip
being "needs a physical GPU: this lane's GL is a software renderer", as at base.

| gpu lane | base push | base PR | branch sample 1 |
|---|---|---|---|
| Linux pytest | 1,008 s | 859 s | 1,269 s |
| Windows pytest | 2,344 s | 2,222 s | 1,934 s |
| Linux job | 17.7 min | 15.3 min | 22.2 min |
| Windows job | 41.2 min | 38.5 min | 33.7 min |

Hosted runners vary in speed. Sample 1's Linux runner was slower in **every** module, including the 23 this branch
provably leaves alone (identical read-backs, no WebP encode, not the dialogue). Its extended lane, which has no GL at
all, was slower too: 410 s against 278–346 s. So the raw numbers are adjusted by those untouched modules: they show how
fast that runner was, and the changed modules are compared at that speed.

| sample 1, runner-adjusted | runner speed from untouched modules | changed modules |
|---|---|---|
| Linux vs base PR / push | ×1.61 / ×1.36 slower | −8.3% / −7.3% |
| Windows vs base PR / push | ×0.89 / ×0.84 (faster) | −3.1% / −2.5% |

Selected modules (seconds; base push / base PR → branch sample 1):

| module | Linux | Windows |
|---|---|---|
| dialogue reopen | 197 / 168 → 203 | 386 / 359 → 289 |
| water | 77 / 66 → 83 | 249 / 242 → 178 |
| terrain | 129 / 108 → 170 | 318 / 299 → 273 |
| fire | 73 / 57 → 100 | 185 / 192 → 164 |
| scatter diagnostics | 17 / 16 → 26 | 34 / 32 → 23 |
| HD-2D lighting (untouched) | 15 / 13 → 21 | 27 / 26 → 23 |

## Assessment

- **Real, but small on CI:** the lane-wide gain is about **3–8% after adjusting for runner speed**. On a software
  renderer, drawing dominates a frame, so removing a read-back saves comparatively little. The largest single gains
  come from skipping the WebP encodes (water) and the no-op dialogue frames.
- **Phase 1 does not shorten the lanes substantially.** The remaining cost is the frames themselves: drawing on
  llvmpipe and real simulation steps.
- **One sample is noisy:** the untouched control modules add up to only 63–180 s per run. The second sample, at this
  document's commit, is reported on PR #444.
