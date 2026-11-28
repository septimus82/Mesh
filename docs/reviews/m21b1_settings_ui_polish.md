# M21B.1: Settings UI polish

These are the two settings-menu defects M21B found, fixed narrowly. Both were reproduced on the integration branch (`182a104`) first, by `tooling/settings_ui_check.py`. It runs a fresh starter project in a hidden window, silent, with the player's settings file in its scratch folder. It measures where each slider's label text actually renders against its bar, presses LEFT five times, and records the messages shown.

## 1. Slider labels overlapped their bars (the pause menu)

**Reproduced:**
- **Pause menu:** each bar reached about 21 px above its label's bottom, so the label was struck through (Music Volume: bar top 518.8, label bottom 497.6).
- **Main menu:** not affected. It draws its settings as cards with values, not sliders.
- **Settings overlay:** not affected. It already had its own local fix.

**Cause:** the `Slider` widget anchors its label at the top of its box and centres its bar in the same box. In a 34 px row, a 16 pt label (26 px as drawn) reaches the bar.

**Fix:**
- **Widget** (`engine/ui/widgets.py`): `Slider` gains `label_size`, the px its label line takes. With it set, the bar and knob stay in the band below the label. At 0 (the default) the geometry is exactly as before, so the settings overlay and every other slider are unchanged.
- **Pause menu:** its sliders are 50 px high with `label_size` 26.
- **After:** each bar's top is 4 px below its label's bottom.

**Merging M21B** brought the pause menu a third slider (Ambience), with the same label band. The Settings panel's minimum height went from 350 to 400 px, so every row still fits at 640 × 480.

## 1b. The main menu's Settings ran out of a small window

**Found while checking scaling, with M21B's sixth row in:** at 640 × 480 the cards ran past the panel and under its footer, and Back was off-screen.

**Pre-existing:** at `182a104`, with five rows, Back already overlapped the footer at that size (`before_main_settings_640x480_182a104.webp`). M21B made it worse.

**Fix** (`compute_menu_panel_layout`, only when the rows don't fit):
1. The panel uses more of the window, up to its height less 16 px.
2. The cards start just under the subtitle.
3. The rows close up, down to 48 px with 6 px gaps, so a card's name and value still fit.

Where they fitted before, nothing moves: 1280 × 720 is identical.

## 2. "UI_SETTINGS_SAVED", once per slider step

**Reproduced:** in both the pause menu and the main menu, five presses of LEFT gave five toasts reading `UI_SETTINGS_SAVED`.

**Causes:**
- `engine.i18n.tr` looked for `locales/en.json` in the game's own folder only. A game has none: the interface text is the engine's. So the key showed instead of "Settings saved". (Every `tr()` message had this problem.) A pip-installed Mesh didn't ship `locales/` at all.
- Each step saved, and each save raised a new toast.

**Fix:**
- `tr` falls back to the engine's own `locales/` (`repo_root.bundled_file`). A game's own `locales/` still wins.
- `locales/en.json` is on the wheel's allow-list.
- **Review correction (`5e1a96c`):** the fallback above applied only when a game had *no* locale file. Reproduced: a game whose `locales/en.json` lists only its own keys got `UI_SETTINGS_SAVED` back as a raw key. Now the engine's table is loaded as the defaults, and the game's file is laid over it key by key. The test (`test_a_game_with_a_partial_locale_file_keeps_its_own_text_and_the_engines`) checks four cases: the game's own key; its override of an engine key (`UI_CANCEL`); an engine key it didn't list; and an unknown key, which stays the key. It failed on `5e1a96c` and passes now.
- Both menus save through one helper (`_settings_data.toast_settings_saved`): "Settings saved", once while it shows. Many quick steps give one message, and a later change gives another.
- The HUD gains `active_toasts()` for that check.
- **After:** five presses give one toast: "Settings saved".

## Checks

**What is preserved:**
- keyboard, mouse and gamepad navigation (the existing pause-menu widget navigation tests pass unchanged);
- settings persistence (a value set in one run loads in the next);
- every row inside its panel from 640 × 480 to 1920 × 1080, in both menus.

**Tests:**
- `tests/test_settings_ui_polish.py`, fast: the widget with and without a label line; the pause menu's labels clear of their bars; one "Settings saved" from many steps, and again later; `tr` from a game folder, and a game's own text winning; both menus using the helper; rows fitting their panel at four window sizes (pause menu), and cards fitting above the footer, unchanged where they already fitted (main menu).
- `tests/test_settings_ui_gpu.py`, GPU: the check tool in a hidden window. No overlaps; one "Settings saved" in each menu; the value moved by 25% and kept.

**Pictures:** `m21b1_evidence/`, before and after, for each menu.

**Out of scope:** no other UI was changed. Other Studio usability findings are in [`m22_studio_usability_backlog.md`](m22_studio_usability_backlog.md).

## CI on the tested head (`0c1e416`)

**Windows:** passed. 10,020 tests passed, 188 skipped. The fast tier took 110.7 s at runner speed 1.11; the limit is 121.8 s.

**Linux:**
- **Tests:** all passed. 10,020 passed, 188 skipped, none failed.
- **Job:** it **failed on the timing gate alone**. The fast tier took 84.1 s against its 79.0 s threshold, and the exception scan 3.93 s against 3.56 s. The runner's speed was 1.15, at the top of its calibrated range. Rule F's advisory check also called both steps slow, so the gate failed the job.

**Why this is runner variance, not a regression from this PR:**
- **Earlier runs:** #407's three Linux runs (speed 0.77–0.80) took 59.5–60.7 s, 1.11 times the speed model's expectation. This run took 1.20 times.
- **Measured locally, back to back:** `-m fast` took 148.0 s on the base (`d3c4fd1`, cold) and 131.0 s on this head. This PR's new tests take about 2 s.

No budget was loosened, and the job wasn't rerun for a badge. The owner authorised merging once the functional checks pass, and they did.
