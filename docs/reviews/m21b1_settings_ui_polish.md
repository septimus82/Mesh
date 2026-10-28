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

## 2. "UI_SETTINGS_SAVED", once per slider step

**Reproduced:** in both the pause menu and the main menu, five presses of LEFT gave five toasts reading `UI_SETTINGS_SAVED`.

**Causes:**
- `engine.i18n.tr` looked for `locales/en.json` in the game's own folder only. A game has none: the interface text is the engine's. So the key showed instead of "Settings saved". (Every `tr()` message had this problem.) A pip-installed Mesh didn't ship `locales/` at all.
- Each step saved, and each save raised a new toast.

**Fix:**
- `tr` falls back to the engine's own `locales/` (`repo_root.bundled_file`). A game's own `locales/` still wins.
- `locales/en.json` is on the wheel's allow-list.
- Both menus save through one helper (`_settings_data.toast_settings_saved`): "Settings saved", once while it shows. Many quick steps give one message, and a later change gives another.
- The HUD gains `active_toasts()` for that check.
- **After:** five presses give one toast: "Settings saved".

## Checks

**What is preserved:**
- keyboard, mouse and gamepad navigation (the existing pause-menu widget navigation tests pass unchanged);
- settings persistence (a value set in one run loads in the next);
- every row inside its panel from 640 × 480 to 1920 × 1080.

**Tests:**
- `tests/test_settings_ui_polish.py`, fast: the widget with and without a label line; the pause menu's labels clear of their bars; one "Settings saved" from many steps, and again later; `tr` from a game folder, and a game's own text winning; both menus using the helper; rows fitting their panel at four window sizes.
- `tests/test_settings_ui_gpu.py`, GPU: the check tool in a hidden window. No overlaps; one "Settings saved" in each menu; the value moved by 25% and kept.

**Pictures:** `m21b1_evidence/`, before and after, for each menu.

**Out of scope:** no other UI was changed. Other Studio usability findings are in [`m22_studio_usability_backlog.md`](m22_studio_usability_backlog.md).
