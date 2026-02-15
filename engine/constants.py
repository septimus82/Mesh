"""Shared constants for Mesh Engine."""

from engine.combat_constants import EVENT_DAMAGE_APPLIED_ALIAS

# Event Names
EVENT_COLLECTED = "collected"
EVENT_COLLECTIBLE_PICKED = "collectible_picked"
EVENT_DAMAGE_APPLIED = EVENT_DAMAGE_APPLIED_ALIAS
EVENT_LEVEL_UP = "level_up"
EVENT_ENTERED_ZONE = "entered_zone"
EVENT_ANIMATION_EVENT = "animation_event"
EVENT_QUEST_LOG_OPENED = "quest_log_opened"
EVENT_QUEST_LOG_CLOSED = "quest_log_closed"
EVENT_INVENTORY_OVERLAY_OPENED = "inventory_overlay_opened"
EVENT_INVENTORY_OVERLAY_CLOSED = "inventory_overlay_closed"

# Common Keys
KEY_ANIMATION_STATE = "animation_state"
KEY_MOVEMENT_STATE = "movement_state"
KEY_INVENTORY = "inventory"
KEY_QUESTS = "quests"
KEY_NEXT_SPAWN_POINT = "next_spawn_point"

# Configuration
DEBUG_STRICT_EXCEPTIONS = False
