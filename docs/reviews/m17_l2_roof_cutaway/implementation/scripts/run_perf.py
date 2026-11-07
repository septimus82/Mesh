"""Alternate old / new engine processes three times each (perf.py)."""
import subprocess
import sys
from pathlib import Path

L2 = Path(sys.argv[1])
ENGINES = {"old": r"D:\Games\Mesh-l2", "new": r"D:\Games\Mesh-cut"}
for r in (1, 2, 3):
    for tag, repo in ENGINES.items():
        out = L2 / "perfrun" / f"{tag}_{r}.json"
        res = subprocess.run([sys.executable, str(L2 / "perf.py"), repo, str(L2 / "proj"), str(L2 / "shots.json"), str(out)],
                             capture_output=True, text=True, timeout=900)
        (L2 / "perfrun" / f"{tag}_{r}.log").write_text(res.stdout + res.stderr, encoding="utf-8")
        print(tag, r, "ok" if res.returncode == 0 else "FAILED", flush=True)
