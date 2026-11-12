"""#500: HUD compositing regressions, each applied alone to engine/game_runtime/tick.py; the HUD check must FAIL."""
import json
import os
import subprocess
import sys
from pathlib import Path

WT = Path(r"D:\Games\Mesh-l4h")
BT = r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4h\bt_hudmut"
TICK = "engine/game_runtime/tick.py"
UI = "    window.ui_controller.draw()\r\n"
HAZE_AFTER = UI + (
    "    if hd2d is not None and getattr(hd2d, '_composite', None) is not None and hd2d.last_stage != 'blit':"
    "  # MUTATION: the haze pass re-run over the window, HUD included\r\n"
    "        _ctx = window.ctx\r\n"
    "        _size = window.get_framebuffer_size()\r\n"
    "        _tex = _ctx.texture(_size, components=4, data=_ctx.active_framebuffer.read(components=4))\r\n"
    "        with _ctx.enabled_only():\r\n"
    "            hd2d._composite.render(hd2d._blit, _tex, hd2d._fbo_parts[1])\r\n"
    "        _tex.delete()\r\n")
MUTATIONS = [
    ("haze_after_hud", UI, HAZE_AFTER),
    ("hud_before_world", "    try:\r\n        lighting = getattr(window, \"lighting\", None)\r\n",
     "    window.ui_controller.draw()  # MUTATION: the HUD first, the world over it\r\n"
     "    try:\r\n        lighting = getattr(window, \"lighting\", None)\r\n"),
]


def main() -> None:
    results = {}
    path = WT / TICK
    original = path.read_bytes()
    text = original.decode("utf-8")
    for name, old, new in MUTATIONS:
        assert text.count(old) == 1, (name, text.count(old))
        mutated = text.replace(old, new)
        if name == "hud_before_world":  # (and not again after it)
            mutated = mutated.replace(UI, "", 1) if mutated.count(UI) == 1 else mutated
            assert mutated.count("window.ui_controller.draw()") == 1, name
        path.write_bytes(mutated.encode("utf-8"))
        try:
            ran = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={BT}",
                                  "tests/test_hd2d_haze_gpu.py", "-k", "hud"], cwd=WT, capture_output=True, text=True,
                                 timeout=1800, env={**os.environ, "MESH_GL_SMOKE": "1"})
        finally:
            path.write_bytes(original)
        report = json.loads((WT / "artifacts" / "hd2d_haze" / "frames_win32.json.log").read_text(encoding="utf-8"))
        results[name] = {"caught": ran.returncode != 0, "summary": (ran.stdout.strip().splitlines() or [""])[-1],
                         "hud": report.get("hud")}
        print(name, json.dumps(results[name]), flush=True)
    assert path.read_bytes() == original
    Path(BT + ".json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("caught", sum(r["caught"] for r in results.values()), "of", len(results))


if __name__ == "__main__":
    main()
