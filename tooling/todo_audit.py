"""Scan repo for tech-debt markers with deterministic output."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MARKERS = ("TO" + "DO", "FIX" + "ME", "HA" + "CK")
DEFAULT_EXTS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".bat",
    ".ps1",
    ".sh",
    ".html",
    ".css",
    ".js",
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "artifacts",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}


@dataclass(frozen=True, slots=True)
class MarkerHit:
    path: str
    line: int
    tag: str
    text: str


def _should_skip_dir(path: Path) -> bool:
    return path.name in SKIP_DIRS


def iter_files(root: Path, exts: Iterable[str] = DEFAULT_EXTS) -> Iterable[Path]:
    ext_set = {e.lower() for e in exts}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if _should_skip_dir(path):
                # Skip directory subtree
                continue
            else:
                continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in ext_set:
            continue
        yield path


def scan_repo(root: Path) -> list[MarkerHit]:
    pattern = re.compile(r"\b(" + "|".join(MARKERS) + r")\b")
    hits: list[MarkerHit] = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if not match:
                continue
            tag = match.group(1)
            hits.append(MarkerHit(str(path).replace("\\", "/"), idx, tag, line.strip()))
    hits.sort(key=lambda h: (h.path, h.line, h.tag))
    return hits


def summarize(hits: list[MarkerHit]) -> dict[str, int]:
    counts = {m: 0 for m in MARKERS}
    for hit in hits:
        counts[hit.tag] = counts.get(hit.tag, 0) + 1
    counts["TOTAL"] = sum(counts.get(m, 0) for m in MARKERS)
    return counts


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    hits = scan_repo(root)
    counts = summarize(hits)
    print(counts)
    for hit in hits[:50]:
        print(f"{hit.path}:{hit.line} [{hit.tag}] {hit.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
