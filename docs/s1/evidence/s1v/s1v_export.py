"""S1v: `mesh export build --deterministic` in PROJECT (cwd = project, as a creator runs it)."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
os.chdir(root)
from mesh_cli.main import main as mesh  # noqa: E402

out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
    code = mesh(["export", "build", "--deterministic"])
bundle = root / "dist" / "bundle"
manifest = bundle / "bundle_manifest.json"
listed = {f["path"] for f in json.loads(manifest.read_text(encoding="utf-8"))["files"]} if manifest.is_file() else set()
print("export exit", code, "| bundle main.py:", (bundle / "main.py").is_file(), "| items.json in bundle:",
      "assets/data/items.json" in listed, "| engine in bundle:", (bundle / "engine" / "__init__.py").is_file())
print(out.getvalue()[-600:])
