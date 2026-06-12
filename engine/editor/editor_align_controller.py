"""Controller for multi-select align and distribute operations.

This module provides align (left/right/top/bottom/center) and
distribute (horizontal/vertical) operations for selected entities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EntityMoveSpec:
    """Specification for moving a single entity."""
    entity_id: str
    before_x: float
    before_y: float
    after_x: float
    after_y: float


@dataclass(frozen=True, slots=True)
class AlignEntitiesCommand:
    """Command for undo/redo of align/distribute operations."""
    operation: str  # 'align_left', 'align_right', etc.
    moves: Tuple[EntityMoveSpec, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "AlignEntities",
            "operation": self.operation,
            "moves": [
                {
                    "entity_id": m.entity_id,
                    "before": {"x": m.before_x, "y": m.before_y},
                    "after": {"x": m.after_x, "y": m.after_y},
                }
                for m in self.moves
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlignEntitiesCommand":
        raw_moves = data.get("moves", [])
        moves = tuple(
            EntityMoveSpec(
                entity_id=m.get("entity_id", ""),
                before_x=m.get("before", {}).get("x", 0.0),
                before_y=m.get("before", {}).get("y", 0.0),
                after_x=m.get("after", {}).get("x", 0.0),
                after_y=m.get("after", {}).get("y", 0.0),
            )
            for m in raw_moves
        )
        return cls(operation=data.get("operation", ""), moves=moves)


class EditorAlignController:
    """Handles align and distribute operations for multi-selected entities."""

    def __init__(self, editor: "EditorModeController") -> None:
        self.editor = editor

    def _get_selected_sprites_with_bounds(self) -> List[Tuple[str, Any, float, float, float, float]]:
        """Get selected sprites with their bounding boxes.

        Returns:
            List of (entity_id, sprite, left, right, bottom, top) tuples.
        """
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        selected_ids = getattr(self.editor, "_selected_entity_ids", [])
        if len(selected_ids) < 2:
            return []

        result = []
        for eid in selected_ids:
            sprite = get_sprite_for_entity_id(self.editor, eid)
            if sprite is None:
                continue

            cx = float(sprite.center_x)
            cy = float(sprite.center_y)
            w = float(getattr(sprite, "width", 32))
            h = float(getattr(sprite, "height", 32))

            left = cx - w / 2
            right = cx + w / 2
            bottom = cy - h / 2
            top = cy + h / 2

            result.append((eid, sprite, left, right, bottom, top))

        return result

    def _apply_moves(self, moves: List[EntityMoveSpec], operation: str) -> bool:
        """Apply moves to sprites and push undo command.

        Returns:
            True if any moves were applied.
        """
        if not moves:
            return False

        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        # Apply moves to sprites
        for spec in moves:
            sprite = get_sprite_for_entity_id(self.editor, spec.entity_id)
            if sprite:
                sprite.center_x = spec.after_x
                sprite.center_y = spec.after_y
                # Update entity data
                sc = getattr(self.editor.window, "scene_controller", None)
                if sc:
                    sc._apply_entity_mutation(sprite, x=spec.after_x, y=spec.after_y)

        # Push undo command
        cmd = AlignEntitiesCommand(operation=operation, moves=tuple(moves))
        self.editor._push_command(cmd.to_dict())

        logger.info("[Editor] %s: moved %d entities", operation, len(moves))
        return True

    # -------------------------------------------------------------------------
    # Align Operations
    # -------------------------------------------------------------------------

    def align_left(self) -> bool:
        """Align selected entities to the leftmost entity's left edge."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Find minimum left edge
        min_left = min(s[2] for s in sprites)  # s[2] = left

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(left - min_left) > 0.01:
                w = right - left
                new_cx = min_left + w / 2
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=new_cx,
                    after_y=sprite.center_y,
                ))

        return self._apply_moves(moves, "align_left")

    def align_right(self) -> bool:
        """Align selected entities to the rightmost entity's right edge."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Find maximum right edge
        max_right = max(s[3] for s in sprites)  # s[3] = right

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(right - max_right) > 0.01:
                w = right - left
                new_cx = max_right - w / 2
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=new_cx,
                    after_y=sprite.center_y,
                ))

        return self._apply_moves(moves, "align_right")

    def align_top(self) -> bool:
        """Align selected entities to the topmost entity's top edge."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Find maximum top edge
        max_top = max(s[5] for s in sprites)  # s[5] = top

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(top - max_top) > 0.01:
                h = top - bottom
                new_cy = max_top - h / 2
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=sprite.center_x,
                    after_y=new_cy,
                ))

        return self._apply_moves(moves, "align_top")

    def align_bottom(self) -> bool:
        """Align selected entities to the bottommost entity's bottom edge."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Find minimum bottom edge
        min_bottom = min(s[4] for s in sprites)  # s[4] = bottom

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(bottom - min_bottom) > 0.01:
                h = top - bottom
                new_cy = min_bottom + h / 2
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=sprite.center_x,
                    after_y=new_cy,
                ))

        return self._apply_moves(moves, "align_bottom")

    def align_center_horizontal(self) -> bool:
        """Align selected entities to horizontal center (average X)."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Calculate average center X
        avg_cx = sum(s[1].center_x for s in sprites) / len(sprites)

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(sprite.center_x - avg_cx) > 0.01:
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=avg_cx,
                    after_y=sprite.center_y,
                ))

        return self._apply_moves(moves, "align_center_h")

    def align_center_vertical(self) -> bool:
        """Align selected entities to vertical center (average Y)."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 2:
            self.editor.set_status("Select 2+ entities to align")
            return False

        # Calculate average center Y
        avg_cy = sum(s[1].center_y for s in sprites) / len(sprites)

        moves = []
        for eid, sprite, left, right, bottom, top in sprites:
            if abs(sprite.center_y - avg_cy) > 0.01:
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=sprite.center_x,
                    after_y=avg_cy,
                ))

        return self._apply_moves(moves, "align_center_v")

    # -------------------------------------------------------------------------
    # Distribute Operations
    # -------------------------------------------------------------------------

    def distribute_horizontal(self) -> bool:
        """Distribute selected entities evenly horizontally."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 3:
            self.editor.set_status("Select 3+ entities to distribute")
            return False

        # Sort by center X
        sorted_sprites = sorted(sprites, key=lambda s: s[1].center_x)

        # Keep first and last fixed, distribute others evenly
        first_cx = sorted_sprites[0][1].center_x
        last_cx = sorted_sprites[-1][1].center_x

        if abs(last_cx - first_cx) < 0.01:
            self.editor.set_status("Entities too close to distribute")
            return False

        step = (last_cx - first_cx) / (len(sorted_sprites) - 1)

        moves = []
        for i, (eid, sprite, left, right, bottom, top) in enumerate(sorted_sprites):
            target_cx = first_cx + i * step
            if abs(sprite.center_x - target_cx) > 0.01:
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=target_cx,
                    after_y=sprite.center_y,
                ))

        return self._apply_moves(moves, "distribute_h")

    def distribute_vertical(self) -> bool:
        """Distribute selected entities evenly vertically."""
        sprites = self._get_selected_sprites_with_bounds()
        if len(sprites) < 3:
            self.editor.set_status("Select 3+ entities to distribute")
            return False

        # Sort by center Y
        sorted_sprites = sorted(sprites, key=lambda s: s[1].center_y)

        # Keep first and last fixed, distribute others evenly
        first_cy = sorted_sprites[0][1].center_y
        last_cy = sorted_sprites[-1][1].center_y

        if abs(last_cy - first_cy) < 0.01:
            self.editor.set_status("Entities too close to distribute")
            return False

        step = (last_cy - first_cy) / (len(sorted_sprites) - 1)

        moves = []
        for i, (eid, sprite, left, right, bottom, top) in enumerate(sorted_sprites):
            target_cy = first_cy + i * step
            if abs(sprite.center_y - target_cy) > 0.01:
                moves.append(EntityMoveSpec(
                    entity_id=eid,
                    before_x=sprite.center_x,
                    before_y=sprite.center_y,
                    after_x=sprite.center_x,
                    after_y=target_cy,
                ))

        return self._apply_moves(moves, "distribute_v")
