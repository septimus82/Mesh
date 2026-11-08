"""Mutation checks for E1: each change applied alone, the named test file run, the file restored byte-for-byte.
py -3.13 mutate.py fast|gpu  (run from the E1 worktree, through run.sh)"""
import os
import subprocess
import sys
from pathlib import Path

S = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\e1")
GLB, REN = Path("engine/hd2d/glb.py"), Path("engine/hd2d/renderer.py")
FAST = [
    ("strength ignored", GLB, "min(max(float(c), 0.0), 1.0) * float(strength)", "min(max(float(c), 0.0), 1.0)"),
    ("default factor white", GLB, 'factor = mat.get("emissiveFactor", [0.0, 0.0, 0.0])',
     'factor = mat.get("emissiveFactor", [1.0, 1.0, 1.0])'),
    ("second UV map read", GLB, 'if em_ref.get("texCoord", 0) != 0:', "if False:"),
    ("sharpen base only", GLB, '(mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture"), mat.get("emissiveTexture"))',
     '(mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture"),)'),
    ("wrap collapsed to one axis", GLB, "        return modes[0], modes[1]\n", "        return modes[0], modes[0]\n"),
]
GPU = [
    ("added in display space", REN, "        lit = mix(l * 12.92, 1.055 * pow(l, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, l));\n",
     "        lit = clamp(lit, 0.0, 1.0) + e;\n"),
    ("texture not decoded", REN, "            e *= mix(t / 12.92, pow((t + 0.055) / 1.055, vec3(2.4)), step(0.04045, t));",
     "            e *= t;"),
    ("emission lit by the scene", REN, "        vec3 e = u_emissive;\n",
     "        vec3 e = u_emissive * light_at(v_world, normalize(v_nrm), false);\n"),
    ("one wrap for both axes", REN, "        texture.wrap_x, texture.wrap_y = mat.emissive_wrap\n",
     "        texture.wrap_x = texture.wrap_y = mat.emissive_wrap[0]\n"),
    ("linear blended in sRGB, decoded after (as before the fix)", REN,
     "        return mat.emissive, texture, 1 if mat.emissive_nearest else 2\n",
     "        texture.delete()\n"
     "        texture = ctx.texture(image.size, components=4, data=image.convert('RGBA').tobytes(), filter=(filt, filt))\n"
     "        texture.wrap_x, texture.wrap_y = mat.emissive_wrap\n"
     "        self._textures[-1] = texture\n"
     "        return mat.emissive, texture, 1\n"),
    ("linear: bytes read as linear (no sRGB texture)", REN,
     "                              internal_format=None if mat.emissive_nearest else GL_SRGB8_ALPHA8)\n",
     "                              internal_format=None)\n"),
]
kind = sys.argv[1]
cases, target = (FAST, "tests/test_hd2d_emissive.py") if kind == "fast" else (GPU, "tests/test_hd2d_emissive_gpu.py")
lines = []
for i, (label, path, old, new) in enumerate(cases):
    original = path.read_bytes()
    text = original.decode("utf-8")
    if "\r\n" in text:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert text.count(old) == 1, label
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "error",
                            f"--basetemp={S / 'tmp' / f'm{kind[0]}{i}'}", target], capture_output=True, text=True,
                           env=os.environ)
        tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or " passed" in ln or " failed" in ln]
        lines.append(f"{label}: exit {r.returncode}; " + " | ".join(tail[-6:]))
    finally:
        path.write_bytes(original)
    assert path.read_bytes() == original
print("\n".join(lines))
(S / f"mutations_{kind}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
