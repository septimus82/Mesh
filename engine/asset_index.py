"""Asset indexing and search helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssetRow:
    rel_path: str
    kind: str
    display_name: str


def _get_kind(ext: str) -> str:
    ext = ext.lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tga", ".webp"):
        return "image"
    if ext in (".wav", ".ogg", ".mp3", ".flac"):
        return "audio"
    if ext in (".json",):
        return "json"
    return "other"


def scan_assets(repo_root: Path) -> list[AssetRow]:
    """Scans the assets directory for files."""
    assets_dir = repo_root / "assets"
    if not assets_dir.exists():
        return []

    rows: list[AssetRow] = []

    # Walk deterministic
    for root, _, files in sorted(os.walk(assets_dir, topdown=True), key=lambda t: t[0].lower()):
        # Sort files for determinism
        for filename in sorted(files, key=str.casefold):
            if filename.startswith("."):
                continue
            
            # Construct relative path
            full_path = Path(root) / filename
            try:
                rel_path = full_path.relative_to(repo_root).as_posix()
            except ValueError:
                continue

            rows.append(
                AssetRow(
                    rel_path=rel_path,
                    kind=_get_kind(full_path.suffix),
                    display_name=filename,
                )
            )

    return rows


def filter_assets(
    rows: list[AssetRow],
    text: str,
    kind_filter: str | None = None,
) -> list[AssetRow]:
    """Filters asset rows by text and kind."""
    text = text.strip().casefold()
    res: list[AssetRow] = []
    
    kind_target = (kind_filter or "All").lower()
    
    for row in rows:
        # Kind filter
        if kind_target != "all":
            if row.kind != kind_target:
                continue
        
        # Text filter
        if text:
            if text not in row.rel_path.casefold():
                continue
        
        res.append(row)
        
    return res
