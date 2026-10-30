"""Build Mesh's small ambience library (``assets/ambience/*.wav``, Milestone 21B) from CC0 recordings.

    py -3.13 tooling/make_ambience_library.py

Each sound is a 10 s mono 16-bit WAV at 22,050 Hz (WAV: every platform decodes it; MP3 and OGG need the system's
decoders). Four are cut from CC0 recordings listed in ``tooling/audio_test_assets.json`` (checked by SHA-256 before
use; kept outside the repository, in ``MESH_AUDIO_ASSETS``); the wind is synthesised here. Each is made to loop
without a seam: 10.5 s are taken and the extra half-second is crossfaded (equal power) into the start.

Which part of a recording: the steadiest 10.5 s (the window whose loudness varies least second by second), so a loop
doesn't repeat one loud event. Deterministic: the same sources give the same files, byte for byte."""

from __future__ import annotations

import hashlib
import json
import os
import wave
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "assets" / "ambience"
RATE, SECONDS, SEAM = 22050, 10.0, 0.5
# file -> (manifest id, member of an extracted archive or None, peak level, what it is)
FROM_RECORDINGS = {
    "rain_loop.wav": ("rain_loopable", "extracted/1.ogg", 0.5, "steady rain"),
    "birds_loop.wav": ("ambient_bird_sounds", None, 0.5, "birdsong"),
    "stream_loop.wav": ("sea_and_river", None, 0.5, "flowing river water"),
    "forest_loop.wav": ("forest_ambience", None, 0.5, "a forest or meadow: birds and leaves"),
}


def _decode(path: Path) -> tuple[np.ndarray, int]:
    """The whole file as float32 mono samples (-1..1) and its sample rate, through pyglet's decoders."""
    import pyglet

    source = pyglet.media.load(str(path), streaming=False)
    fmt = source.audio_format
    assert fmt is not None and fmt.sample_size == 16, f"{path.name}: not 16-bit audio"
    source = pyglet.media.load(str(path), streaming=True)  # a fresh read from the start
    chunks = []
    while (data := source.get_audio_data(1 << 16)) is not None:
        chunks.append(bytes(data.data))
    pcm = np.frombuffer(b"".join(chunks), dtype="<i2").astype(np.float32) / 32768.0
    mono = pcm.reshape(-1, fmt.channels).mean(axis=1)
    return mono, int(fmt.sample_rate)


def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE:
        return x
    n = int(len(x) * RATE / rate)
    return np.asarray(np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x), dtype=np.float32)


def _steadiest(x: np.ndarray, length: int) -> int:
    """Where the window of ``length`` samples whose per-second loudness varies least starts (whole seconds)."""
    second = RATE
    rms = np.sqrt(np.array([np.mean(x[i:i + second] ** 2) for i in range(0, len(x) - second, second)]) + 1e-12)
    span = int(np.ceil(length / second))
    best, where = None, 0
    for s in range(0, len(rms) - span):
        window = rms[s:s + span]
        score = float(np.std(window) / max(1e-6, float(np.mean(window))))
        if best is None or score < best:
            best, where = score, s * second
    return where


def _loop(x: np.ndarray, peak: float) -> np.ndarray:
    """``SECONDS`` of ``x`` (it holds ``SECONDS + SEAM``), its extra end crossfaded into its start, normalised."""
    n, c = int(SECONDS * RATE), int(SEAM * RATE)
    y = x[:n].copy()
    t = np.arange(c) / c
    y[:c] = x[:c] * np.sin(t * np.pi / 2) + x[n:n + c] * np.cos(t * np.pi / 2)
    return y * (peak / max(1e-6, float(np.max(np.abs(y)))))


def _wind() -> np.ndarray:
    """Wind: brown noise, softened, swelling slowly (two out-of-step swells), made to loop like the others."""
    rng = np.random.default_rng(21)
    n = int((SECONDS + SEAM) * RATE)
    brown = np.cumsum(rng.standard_normal(n)).astype(np.float64)
    brown -= np.convolve(brown, np.ones(4096) / 4096, mode="same")  # drift removed: only the rushing stays
    soft = np.convolve(brown, np.ones(6) / 6, mode="same")
    t = np.arange(n) / RATE
    swell = 0.65 + 0.25 * np.sin(2 * np.pi * t / SECONDS) + 0.1 * np.sin(2 * np.pi * 3 * t / SECONDS + 1.3)
    return np.asarray(soft * swell / np.max(np.abs(soft)), dtype=np.float32)


def _write(path: Path, y: np.ndarray) -> str:
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = REPO / "tooling" / "audio_test_assets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources: dict[str, Any] = {a["id"]: a for a in manifest["assets"]}
    root = Path(os.environ.get("MESH_AUDIO_ASSETS", "D:/Games/Mesh-audio-assets/downloads"))
    OUT.mkdir(parents=True, exist_ok=True)
    made: list[dict[str, Any]] = []
    for name, (asset_id, member, peak, what) in FROM_RECORDINGS.items():
        asset = sources[asset_id]
        archive = root / asset["file"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == asset["sha256"], f"{archive} isn't the recorded file"
        source = archive.parent / member if member else archive
        if member:  # a file from the archive: its own recorded hash
            want = asset["members"][member]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == want, f"{source} isn't the recorded file"
        x, rate = _decode(source)
        x = _resample(x, rate)
        start = _steadiest(x, int((SECONDS + SEAM) * RATE))
        y = _loop(x[start:start + int((SECONDS + SEAM) * RATE)], peak)
        made.append({"file": f"assets/ambience/{name}", "what": what, "from": asset_id, "member": member,
                     "excerpt_start_s": round(start / RATE, 1), "sha256": _write(OUT / name, y)})
    made.append({"file": "assets/ambience/wind_loop.wav", "what": "wind (synthesised: brown noise, swelling)",
                 "from": "Mesh (tooling/make_ambience_library.py)", "member": None, "excerpt_start_s": None,
                 "sha256": _write(OUT / "wind_loop.wav", _loop(_wind(), 0.45))})
    manifest["library"] = {"about": "Mesh's ambience library (assets/ambience): 10 s mono WAV loops at 22,050 Hz, made "
                                    "by tooling/make_ambience_library.py from the files above (CC0) and, for wind, "
                                    "synthesised. CC0 like their sources.", "files": made}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for m in made:
        print(m["file"], m["excerpt_start_s"], m["sha256"][:12])


if __name__ == "__main__":
    main()
