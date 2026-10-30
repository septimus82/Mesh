"""H3 diagnostic (temporary, #425): what caches a CI runner holds at one point in a job, as JSON metadata only.

    python tooling/h3_env_snapshot.py h3diag/after_full_suite.json

Read-only. Records file counts, sizes and digests (file contents hashed only for fontconfig's per-user cache and
``.mesh/``), never file contents, for: Python bytecode and pytest's assertion-rewrite caches under the repository,
``.pytest_cache``, ``.mesh/``, fontconfig's caches, Mesa's shader caches, the top level of ``~/.cache``,
``~/.config`` and ``~/.local/share``, pytest's temporary directories, and GL/Mesa/XDG/Python environment variables
(names that look like secrets are left out).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
ENV_KEYS = re.compile(r"^(MESA|LIBGL|GALLIUM|__GL|EGL|XDG|DISPLAY|FONTCONFIG|FC_|PYTHON|PYTEST|MESH_|PYGLET|ARCADE)")
SECRET = re.compile(r"TOKEN|SECRET|KEY|PASS|AUTH|CRED", re.I)


def _files(root: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for base, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(base, name)
            if not os.path.islink(path) and os.path.isfile(path):
                out.append((os.path.relpath(path, root).replace(os.sep, "/"), os.path.getsize(path)))
    return sorted(out)


def _tree(root: Path, hash_contents: bool = False) -> dict[str, Any]:
    if not root.exists():
        return {"exists": False}
    files = _files(root)
    info: dict[str, Any] = {"exists": True, "files": len(files), "bytes": sum(size for _, size in files),
                            "listing_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest()[:16]}
    if hash_contents:
        info["contents"] = {rel: {"bytes": size, "sha256": hashlib.sha256((root / rel).read_bytes()).hexdigest()[:16]}
                            for rel, size in files}
    return info


def _top_level(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {}
    return {entry.name: {k: v for k, v in _tree(Path(entry.path)).items() if k != "listing_sha256"}
            if entry.is_dir(follow_symlinks=False) else {"file_bytes": entry.stat(follow_symlinks=False).st_size}
            for entry in sorted(os.scandir(root), key=lambda e: e.name)}


def _bytecode() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for top in ("engine", "mesh_cli", "tooling", "tests"):
        plain = rewritten = plain_bytes = rewritten_bytes = 0
        for rel, size in _files(REPO / top):
            if rel.endswith(".pyc"):
                if "-pytest-" in rel:
                    rewritten, rewritten_bytes = rewritten + 1, rewritten_bytes + size
                else:
                    plain, plain_bytes = plain + 1, plain_bytes + size
        out[top] = {"pyc": plain, "pyc_bytes": plain_bytes, "pytest_rewritten": rewritten,
                    "pytest_rewritten_bytes": rewritten_bytes}
    return out


def snapshot() -> dict[str, Any]:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache")
    tmp = Path(tempfile.gettempdir())
    image_sizes = REPO / ".mesh" / "cache" / "image_sizes.json"
    return {
        "python": {"version": sys.version, "dont_write_bytecode": sys.dont_write_bytecode,
                   "pycache_prefix": sys.pycache_prefix},
        "env": {k: v for k, v in sorted(os.environ.items()) if ENV_KEYS.match(k) and not SECRET.search(k)},
        "bytecode": _bytecode(),
        "pytest_cache": _tree(REPO / ".pytest_cache"),
        "mesh_dir": _tree(REPO / ".mesh", hash_contents=True),
        "image_sizes_entries": len(json.loads(image_sizes.read_text(encoding="utf-8"))) if image_sizes.is_file() else None,
        "fontconfig_user": _tree(cache / "fontconfig", hash_contents=True),
        "fontconfig_system": _tree(Path("/var/cache/fontconfig")),
        "mesa": {name: _tree(cache / name) for name in sorted(os.listdir(cache)) if "mesa" in name.lower()}
        if cache.is_dir() else {},
        "home_cache": _top_level(cache),
        "home_config": _top_level(HOME / ".config"),
        "home_local_share": _top_level(HOME / ".local" / "share"),
        "tmp_pytest": {e.name: _tree(Path(e.path)) for e in os.scandir(tmp)
                       if e.is_dir(follow_symlinks=False) and (e.name.startswith("pytest-of-") or "mesh" in e.name.lower())},
    }


if __name__ == "__main__":
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"h3-diag: wrote {target}")
