"""Content indexing system for tracking assets across multiple roots."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .content_packs import Pack, load_all_packs, sort_packs


@dataclass
class ContentEntry:
    """Represents a file found in the content roots."""
    key: str  # Relative path (canonical key)
    resolved_path: Path
    providing_root: Path
    providing_pack_id: str = "unknown"
    shadowed_roots: List[Path] = field(default_factory=list)
    shadowed_pack_ids: List[str] = field(default_factory=list)

class ContentIndex:
    """Index of all content files across configured roots."""

    def __init__(self, roots: List[Path]) -> None:
        self.roots = roots
        self.packs: List[Pack] = []
        self._entries: Dict[str, ContentEntry] = {}
        self._built = False

    def build(self, refresh: bool = False) -> None:
        """Scan roots and build the index."""
        if self._built and not refresh:
            return

        self._entries.clear()

        # Load and sort packs
        raw_packs = load_all_packs(self.roots)
        self.packs = sort_packs(raw_packs)

        # Iterate packs in priority order (High -> Low)
        for pack in self.packs:
            root = pack.root
            if not root.exists():
                continue

            # Walk the directory
            for dirpath, _, filenames in os.walk(root):
                for f in filenames:
                    full_path = Path(dirpath) / f
                    try:
                        rel_path = full_path.relative_to(root)
                        # Use forward slashes for keys to be consistent
                        key = str(rel_path).replace("\\", "/")

                        if key in self._entries:
                            self._entries[key].shadowed_roots.append(root)
                            self._entries[key].shadowed_pack_ids.append(pack.id)
                        else:
                            self._entries[key] = ContentEntry(
                                key=key,
                                resolved_path=full_path,
                                providing_root=root,
                                providing_pack_id=pack.id
                            )
                    except ValueError:
                        continue

        self._built = True

    def get_entry(self, key: str) -> Optional[ContentEntry]:
        """Get entry for a relative path key."""
        # Normalize key
        key = key.replace("\\", "/")
        if not self._built:
            self.build()
        return self._entries.get(key)

    def resolve(self, key: str) -> Optional[Path]:
        """Resolve a key to a full path using the index."""
        entry = self.get_entry(key)
        return entry.resolved_path if entry else None

    @property
    def entries(self) -> Dict[str, ContentEntry]:
        if not self._built:
            self.build()
        return self._entries
