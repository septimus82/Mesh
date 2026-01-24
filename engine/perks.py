"""Perk system for Mesh Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import resolve_path
from .logging_tools import get_logger


logger = get_logger(__name__)


@dataclass
class Perk:
    id: str
    name: str
    description: str
    effects: Dict[str, float] = field(default_factory=dict)


class PerkManager:
    """Manages loading and lookup of perks."""

    def __init__(self) -> None:
        self._perks: Dict[str, Perk] = {}
        self._loaded = False

    def load_perks(self) -> None:
        """Load perks from assets/data/perks.json and all active packs."""
        if self._loaded:
            return

        # 1. Load global perks (legacy/fallback)
        global_path = resolve_path("assets/data/perks.json")
        if global_path.exists():
            self._load_from_file(global_path)

        # 2. Load from packs
        # We assume packs are in 'packs/' directory relative to CWD for now
        # In a real engine this would use the ContentPack system to resolve active packs
        packs_dir = Path("packs")
        if packs_dir.exists():
            for pack_dir in packs_dir.iterdir():
                if pack_dir.is_dir():
                    perks_file = pack_dir / "perks.json"
                    if perks_file.exists():
                        self._load_from_file(perks_file)

        logger.info("[Mesh][Perks] Loaded %d perks", len(self._perks))
        self._loaded = True

    def _load_from_file(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for perk_data in data.get("perks", []):
                self.register_perk(perk_data)
        except Exception as e:
            logger.error("[Mesh][Perks] Failed to load perks from %s: %s", path, e)

    def register_perk(self, data: Dict[str, Any]) -> None:
        perk_id = data.get("id")
        if not perk_id:
            return

        perk = Perk(
            id=perk_id,
            name=data.get("name", perk_id),
            description=data.get("description", ""),
            effects=data.get("effects", {})
        )
        self._perks[perk_id] = perk

    def get_perk(self, perk_id: str) -> Optional[Perk]:
        return self._perks.get(perk_id)

    def get_all_perks(self) -> List[Perk]:
        return list(self._perks.values())
