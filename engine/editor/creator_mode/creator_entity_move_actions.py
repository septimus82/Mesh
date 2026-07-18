"""Centralized semantic action IDs for Creator Mode entity movement."""

from __future__ import annotations

from typing import Final

ENTITY_MOVE_LEFT_ACTION_ID: Final = "entity.move_left"
ENTITY_MOVE_RIGHT_ACTION_ID: Final = "entity.move_right"
ENTITY_MOVE_UP_ACTION_ID: Final = "entity.move_up"
ENTITY_MOVE_DOWN_ACTION_ID: Final = "entity.move_down"

ENTITY_MOVE_ACTION_IDS: Final[tuple[str, ...]] = (
    ENTITY_MOVE_LEFT_ACTION_ID,
    ENTITY_MOVE_RIGHT_ACTION_ID,
    ENTITY_MOVE_UP_ACTION_ID,
    ENTITY_MOVE_DOWN_ACTION_ID,
)

ENTITY_MOVE_ACTION_ID_SET: Final[frozenset[str]] = frozenset(ENTITY_MOVE_ACTION_IDS)

DIRECTION_LEFT: Final = "left"
DIRECTION_RIGHT: Final = "right"
DIRECTION_UP: Final = "up"
DIRECTION_DOWN: Final = "down"

DIRECTION_BY_ACTION_ID: Final[dict[str, str]] = {
    ENTITY_MOVE_LEFT_ACTION_ID: DIRECTION_LEFT,
    ENTITY_MOVE_RIGHT_ACTION_ID: DIRECTION_RIGHT,
    ENTITY_MOVE_UP_ACTION_ID: DIRECTION_UP,
    ENTITY_MOVE_DOWN_ACTION_ID: DIRECTION_DOWN,
}

ACTION_ID_BY_DIRECTION: Final[dict[str, str]] = {
    DIRECTION_LEFT: ENTITY_MOVE_LEFT_ACTION_ID,
    DIRECTION_RIGHT: ENTITY_MOVE_RIGHT_ACTION_ID,
    DIRECTION_UP: ENTITY_MOVE_UP_ACTION_ID,
    DIRECTION_DOWN: ENTITY_MOVE_DOWN_ACTION_ID,
}

DIRECTION_LABELS: Final[dict[str, str]] = {
    DIRECTION_LEFT: "Move Left",
    DIRECTION_RIGHT: "Move Right",
    DIRECTION_UP: "Move Up",
    DIRECTION_DOWN: "Move Down",
}
