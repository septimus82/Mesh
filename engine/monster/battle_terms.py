"""Project-configurable battle UI display terminology.

Pure module: no GameWindow, save, or arcade dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BattleTerms:
    """User-facing labels for capture items and move resources."""

    capture_item_name: str = "Pocket Ball"
    capture_item_plural: str = "Pocket Balls"
    capture_item_menu_label: str = "Ball"
    move_resource_label: str = "PP"

    def format_move_row(self, *, move_id: str, move_type: str, move_pp: int) -> str:
        return f"{move_id} {move_type} {self.move_resource_label} {move_pp}"

    def format_capture_bag_row(self, count: int) -> str:
        return f"{self.capture_item_name} x{count}"

    def format_no_capture_items_left(self) -> str:
        return f"No {self.capture_item_plural} left!"

    def format_threw_capture_item(self, *, opponent_name: str) -> str:
        return f"Threw a {self.capture_item_name}! {opponent_name} broke free."


DEFAULT_BATTLE_TERMS = BattleTerms()
