"""Milestone 21B.1: the game's Settings pages as a player sees them, checked in a hidden window.

    py -3.13 tooling/settings_ui_check.py OUT

A fresh starter project (silent: master volume 0; the player's settings file in OUT, never a checkout's). For the
pause menu's Settings and the main menu's Settings: where each slider's label text actually is (its rendered box) and
where its bar is, so an overlap is measured, not guessed; a picture; five presses of LEFT on the first slider and the
messages the game shows meanwhile; the value kept for the next game."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))


def _slider_overlaps(layout: Any) -> list[dict[str, Any]]:
    """Each slider's label box (as the text renders at the menu's size) against its bar's top."""
    import engine.optional_arcade as optional_arcade

    arcade = optional_arcade.arcade
    out: list[dict[str, Any]] = []
    label: dict[str, Any] | None = None
    for instruction in layout.instructions:
        payload = instruction.payload if isinstance(instruction.payload, dict) else {}
        if instruction.kind == "slider_label_text":
            size = int(payload.get("font_size", 16) or 16)
            text = arcade.Text(str(payload.get("text", "")), 0, 0, font_size=size)
            top = float(payload.get("y", 0.0))
            label = {"label": payload.get("text"), "label_bottom": round(top - float(text.content_height), 1)}
        elif instruction.kind in ("slider_track", "slider_knob") and label is not None:
            rect = payload.get("rect")
            label.setdefault("bar_top", round(float(rect.top), 1))
            label["bar_top"] = max(label["bar_top"], round(float(rect.top), 1))
            if instruction.kind == "slider_knob":
                label["overlaps"] = label["bar_top"] > label["label_bottom"]
                out.append(label)
                label = None
    return out


def check(out: Path) -> dict[str, Any]:
    from hd2d_demo import HiddenGame

    project = out / "game"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = 0.0
    (project / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    game = HiddenGame(project, size=(1280, 720))
    keys = game.arcade.key
    report: dict[str, Any] = {}
    try:
        game.load("packs/core_regions/scenes/start.json")
        game.step(20)
        hud = game.window.player_hud
        for name in ("pause", "main"):
            hud._toast_manager.clear()
            overlay = game.window.pause_menu if name == "pause" else game.window.main_menu_overlay
            if name == "pause":
                overlay.toggle()
                overlay.state, overlay._settings_index = "settings", 0
                overlay._invalidate_layout()
                layout = overlay.layout_current_state()
                sliders = _slider_overlaps(type("L", (), {"instructions": layout.instructions})())
            else:
                overlay.open()
                overlay.state, overlay._settings_index = "settings", 0
                sliders = []  # (its settings are cards with values, not sliders)
            game.step(2)
            game.draw().convert("RGB").save(out / f"{name}_settings.png")
            before = float(game.window.runtime_settings.music_volume)
            for _ in range(5):
                game.window.dispatch_event("on_key_press", keys.LEFT, 0)
                game.window.dispatch_event("on_key_release", keys.LEFT, 0)
                game.step(6)  # a tenth of a second between presses, as a player taps
            game.draw().convert("RGB").save(out / f"{name}_settings_after_5_presses.png")
            from engine.runtime_settings_storage import load_runtime_settings

            report[name] = {"sliders": sliders, "music_before_after": [before, float(game.window.runtime_settings.music_volume)],
                            "saved": float(load_runtime_settings(os.environ["MESH_RUNTIME_SETTINGS_PATH"]).music_volume),
                            "toasts_showing": hud._toast_manager.get_active_toasts()}
            if name == "pause":
                overlay.toggle()
            else:
                overlay.close() if callable(getattr(overlay, "close", None)) else None
            game.window.runtime_settings.music_volume = 1.0
            game.step(2)
    finally:
        game.window.close()
        os.chdir(game._cwd)
    return report


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    (out / "user_settings.json").unlink(missing_ok=True)  # each run starts from the defaults
    report = check(out)
    (out / "settings_ui.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
