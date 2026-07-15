# Behaviours

Behaviour registry exported from Mesh.

## ActionListRunner
Runs an ordered list of actions when triggered by events.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_events | Event types to listen for | array | [] |
| event_filter | Filter events by payload values (dict) | object | {} |
| actions | Ordered list of action configs | array | [] |
| run_once | Only run actions once (ignore subsequent triggers) | bool | False |
| cooldown | Minimum time between runs (0 = no cooldown) | float | 0.0 |
| enabled | Whether the runner is active | bool | True |
| require_flags | Flags that must be true to trigger | array | [] |
| forbid_flags | Flags that must be false to trigger | array | [] |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ActionListRunner"],
  "behaviour_config": {
    "ActionListRunner": {
      "listen_events": "<value>"
    }
  }
}
```

## Animator
Cycles sprite textures using named animation states.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| animations | Mapping of state name to a list of texture paths | object | {} |
| animation_state | Initial animation state to play | string | idle |
| animation_frame_rate | Frames per second for the active animation | float | 8.0 |
| enable_auto_state | Automatically switch idle/walk based on movement | bool | False |
| idle_clip | Clip to use when speed is below threshold | string | idle |
| walk_clip | Clip to use when speed is above threshold | string | walk |
| speed_threshold | Minimum speed to consider the entity moving | float | 1.0 |
| override_duration | Default duration (seconds) for temporary state overrides | float | 0.2 |
| directional_mode | Direction handling: 'none' or '4-way' for directional idle/walk clips | string | none |
| facing_default | Initial facing direction (up/down/left/right) used with directional_mode | string | down |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Animator"],
  "behaviour_config": {
    "Animator": {
      "animations": "<value>"
    }
  }
}
```

## AutoAnimationByMovement
Switches sprite-sheet animations between idle/walk based on movement velocity.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| idle | Animation state name to use when stationary | string | idle |
| walk | Animation state name to use when moving | string | walk |
| speed_threshold | Speed cutoff used to decide between idle and walk | float | 0.01 |
| prefer | Fallback animation preference order if idle/walk is missing | array | ['walk', 'idle'] |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["AutoAnimationByMovement"],
  "behaviour_config": {
    "AutoAnimationByMovement": {
      "idle": "<value>"
    }
  }
}
```

## BreedingShrineZone
Creates a breeding egg when two sufficiently bonded companions visit the shrine.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| trigger_radius | Distance threshold for triggering | float | 0.0 |
| trigger_target | Name of the player sprite to watch | string | - |
| enabled | Whether the shrine can trigger | bool | True |
| enabled_flag | Optional game-state flag required to enable the shrine | string | - |
| cooldown_seconds | Cooldown after an attempt | float | 3.0 |
| bond_threshold | Minimum companion bond required to breed | float | 50.0 |
| max_eggs | Maximum pending eggs allowed | int | 1 |
| hatch_steps | Egg steps required before hatching | int | 200 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["BreedingShrineZone"],
  "behaviour_config": {
    "BreedingShrineZone": {
      "trigger_radius": "<value>"
    }
  }
}
```

## CameraFollow
Moves the window camera toward the entity each frame.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| lerp_factor | How quickly the camera catches up to the entity | float | 5.0 |
| follow_strength | Alias for lerp_factor (higher = snappier follow) | float | 5.0 |
| deadzone_px | Pixels of deadzone before the camera moves | float | 0.0 |
| deadzone_w | Deadzone width in screen pixels | float | 0.0 |
| deadzone_h | Deadzone height in screen pixels | float | 0.0 |
| max_speed | Clamp camera movement speed (px/sec), 0 disables | float | 0.0 |
| padding | Clamp padding applied before reaching bounds | float | 0.0 |
| offset_x | Horizontal offset applied before following | float | 0.0 |
| offset_y | Vertical offset applied before following | float | 0.0 |
| zoom | Optional zoom override (leave unset to inherit scene) | float | 1.0 |
| zoom_speed | How quickly zoom eases toward its target | float | 5.0 |
| min_zoom | Minimum zoom clamp when overriding zoom | float | 0.25 |
| max_zoom | Maximum zoom clamp when overriding zoom | float | 3.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["CameraFollow"],
  "behaviour_config": {
    "CameraFollow": {
      "lerp_factor": "<value>"
    }
  }
}
```

## ChaseTarget
Acquires a nearby target and chases it using grid-based pathfinding.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_entity_id | Authored entity id to chase (matches mesh_entity_data.id) | string | - |
| target_tag | Fallback: chase the nearest entity with this mesh_tag | string | - |
| acquire_radius_tiles | Acquire range in tiles | int | 8 |
| leash_radius_tiles | Stop chasing when target exceeds this range in tiles | int | 12 |
| stop_range_tiles | If within this range, stop moving but remain in chase state | int | 0 |
| speed | Chase movement speed | float | 90.0 |
| give_up_ticks | If no_path persists this many ticks, disengage | int | 30 |
| cooldown_ticks | Ticks to stay idle after giving up | int | 60 |
| los_required | If true, require grid line-of-sight to acquire target | bool | False |
| repath_min_ticks | Forwarded to FollowPath (deterministic throttle) | int | 2 |
| no_path_repath_ticks | Forwarded to FollowPath | int | 10 |
| emit_chase_step | Emit chase_step event each update (can be noisy) | bool | False |
| enabled | Whether chase behaviour is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ChaseTarget"],
  "behaviour_config": {
    "ChaseTarget": {
      "target_entity_id": "<value>"
    }
  }
}
```

## Collectible
Automatically collects when a named entity overlaps the sprite.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| collect_by_name | Name of the sprite allowed to pick this up | string | player |
| auto_remove | Whether to remove the sprite after collection | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Collectible"],
  "behaviour_config": {
    "Collectible": {
      "collect_by_name": "<value>"
    }
  }
}
```

## Combat
Allows an entity to attack and deal damage.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| damage | Damage dealt per attack | float | 1.0 |
| cooldown | Time in seconds between attacks | float | 1.0 |
| range | Attack range (offset from center) | float | 32.0 |
| hitbox_size | Size of the damage area | float | 32.0 |
| target_tag | Tag of entities to damage (e.g. 'enemy') | string | enemy |
| attack_anim | Animation state to play on attack | string | attack |
| attack_sound | Sound to play on attack | string | assets/sounds/attack.wav |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Combat"],
  "behaviour_config": {
    "Combat": {
      "damage": "<value>"
    }
  }
}
```

## ConditionalActivator
Enables a sprite only when required flags are set and forbidden flags remain false.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| require_flags | List of flag names that must be true | array | [] |
| forbid_flags | List of flag names that must remain false | array | [] |
| refresh_rate | Seconds between requirement checks (0 = every frame) | float | 0.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ConditionalActivator"],
  "behaviour_config": {
    "ConditionalActivator": {
      "require_flags": "<value>"
    }
  }
}
```

## CutsceneTrigger
Starts a cutscene when the configured event fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_event | Event to listen for | string | cutscene |
| cutscene_id | Cutscene id to play | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["CutsceneTrigger"],
  "behaviour_config": {
    "CutsceneTrigger": {
      "listen_event": "<value>"
    }
  }
}
```

## DamageOnTouch
Emits a damage event when colliding with the target sprite.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_name | Name of the sprite that should receive damage | string | player |
| damage | Damage value applied on contact | float | 1.0 |
| cooldown | Seconds between damage ticks while in contact (0 = every frame) | float | 0.0 |
| once | If true, damage applies only on the first hit | bool | False |
| destroy_on_hit | Remove the damaging sprite after contact | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["DamageOnTouch"],
  "behaviour_config": {
    "DamageOnTouch": {
      "target_name": "<value>"
    }
  }
}
```

## Dialogue
Displays speaker-tagged lines when interacted with or when events fire.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| start_event | Mesh event name that auto-starts this dialogue | string | - |
| event_field | Payload field to match when start_event triggers | string | - |
| event_value | Optional value that the payload field must equal | string | - |
| auto_start | Show this dialogue once automatically after load | bool | False |
| once | Prevent replaying the dialogue after it finishes | bool | True |
| dialogue | Inline dialogue object (speaker, lines, nodes, start, once) | object | {} |
| role | Role of the speaker (e.g. Merchant, Guard) | string | - |
| dialogue_lines | Legacy array of dialogue line entries | array | [] |
| dialogue_nodes | Graph-based dialogue nodes map | object | {} |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Dialogue"],
  "behaviour_config": {
    "Dialogue": {
      "start_event": "<value>"
    }
  }
}
```

## DialogueRunner
Runs dialogue scripts with branching choices.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| script | Dialogue script (dict of nodes) | object | {} |
| start_node | Initial node ID to start from | string | start |
| auto_advance | Advance to next node automatically (no choices) | bool | False |
| dialogue_id | Optional identifier for this dialogue | string | - |
| enabled | Whether the dialogue runner is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["DialogueRunner"],
  "behaviour_config": {
    "DialogueRunner": {
      "script": "<value>"
    }
  }
}
```

## DoorLock
Unlocks when a specific event is received.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| unlock_event | Event ID that unlocks this door | string | - |
| starts_locked | If true, starts in locked state | bool | True |
| open_sprite | Sprite path for open state | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["DoorLock"],
  "behaviour_config": {
    "DoorLock": {
      "unlock_event": "<value>"
    }
  }
}
```

## DropTable
Rolls item/gold drops when a configured event fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_event | Event name to listen for. | string | died |
| drops | List of drop entries. | array | [] |
| match_self | If true, require actor/entity to be this sprite. | bool | True |
| seed | Optional RNG seed for deterministic rolls. | int | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["DropTable"],
  "behaviour_config": {
    "DropTable": {
      "listen_event": "<value>"
    }
  }
}
```

## EmitEventOnEvent
Listens for an event and emits another event.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_event | - | string | - |
| payload_field | - | string | - |
| payload_value | - | string | - |
| emit_event | - | string | - |
| emit_payload | - | object | {} |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["EmitEventOnEvent"],
  "behaviour_config": {
    "EmitEventOnEvent": {
      "listen_event": "<value>"
    }
  }
}
```

## EncounterCleared
Emits an event once all live entities with the configured tag are gone.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| enemy_tag | Sprite tag counted as part of the encounter. | string | enemy |
| clear_event | Event emitted when the encounter clears. | string | encounter_cleared |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["EncounterCleared"],
  "behaviour_config": {
    "EncounterCleared": {
      "enemy_tag": "<value>"
    }
  }
}
```

## EnemyAI
Simple AI that chases and attacks a target.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_tag | Tag of the entity to chase | string | player |
| detect_radius | Distance to start chasing | float | 300.0 |
| lose_radius | Distance to stop chasing | float | 360.0 |
| attack_radius | Distance to start attacking | float | 40.0 |
| speed | Movement speed | float | 100.0 |
| attack_cooldown | Seconds between attacks | float | 1.0 |
| attack_anim_duration | Seconds to play attack animation (if Animator attached) | float | 0.25 |
| repath_interval | Seconds between chase direction updates | float | 0.2 |
| use_patrol | If true, idle/patrol when not chasing | bool | True |
| flee_below_health | Fraction of max health below which enemy flees (0 disables) | float | 0.0 |
| attack_event | Event emitted on attack | string | enemy_attack |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["EnemyAI"],
  "behaviour_config": {
    "EnemyAI": {
      "target_tag": "<value>"
    }
  }
}
```

## EventLogger
Logs specific events to the console.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| events | Comma-separated list of events to log (or '*' for all) | string | * |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["EventLogger"],
  "behaviour_config": {
    "EventLogger": {
      "events": "<value>"
    }
  }
}
```

## FleeFromTarget
Flees from nearby threats to a safe distance.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| threat_tags | Tags that identify threat entities | array | [] |
| threat_entity_id | Specific entity ID to flee from (overrides tags) | string | - |
| detection_radius | Radius in tiles to detect threats | float | 6.0 |
| flee_distance | Distance in tiles to flee from threat | float | 10.0 |
| safe_distance | Distance at which fleeing completes successfully | float | 8.0 |
| speed | Movement speed while fleeing | float | 100.0 |
| repath_interval_ticks | Ticks between path recalculation while fleeing | int | 10 |
| max_flee_ticks | Maximum ticks to flee before giving up | int | 300 |
| cooldown_ticks | Ticks to wait after completing a flee | int | 30 |
| enabled | Whether flee behaviour is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["FleeFromTarget"],
  "behaviour_config": {
    "FleeFromTarget": {
      "threat_tags": "<value>"
    }
  }
}
```

## FollowPath
Moves toward a target using A* pathfinding over the tile collision grid.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_name | Name of the sprite to pathfind toward (uses find_sprite_by_name) | string | - |
| goal_x | Optional goal X world coordinate (used if target_name is empty) | float | - |
| goal_y | Optional goal Y world coordinate (used if target_name is empty) | float | - |
| speed | Movement speed in units per second | float | 80.0 |
| arrive_dist | Distance threshold to consider the goal reached | float | 4.0 |
| repath_interval | Seconds between path recomputation | float | 0.25 |
| repath_min_ticks | Minimum update() ticks between path recomputation (deterministic throttle) | int | 2 |
| no_path_repath_ticks | Ticks to wait before retrying when no path exists | int | 10 |
| diag | If true, allow diagonal movement in A* | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["FollowPath"],
  "behaviour_config": {
    "FollowPath": {
      "target_name": "<value>"
    }
  }
}
```

## FollowTarget
Moves toward another sprite using a constant speed.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| follow_target | Name of the sprite to follow | string | - |
| follow_speed | Movement speed in units per second | float | 100.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["FollowTarget"],
  "behaviour_config": {
    "FollowTarget": {
      "follow_target": "<value>"
    }
  }
}
```

## GrantExperience
Grants experience to the player when this entity dies.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| xp | XP awarded on death | int | 10 |
| event | Event name to listen for | string | died |
| target_tag | Tag of player to reward | string | player |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["GrantExperience"],
  "behaviour_config": {
    "GrantExperience": {
      "xp": "<value>"
    }
  }
}
```

## Health
Tracks hit points and signals when the entity dies.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| max_hp | Maximum health value | float | 1.0 |
| hp | Initial health value | float | 1.0 |
| invulnerable | Disable damage processing when true | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Health"],
  "behaviour_config": {
    "Health": {
      "max_hp": "<value>"
    }
  }
}
```

## Hitbox
Temporary entity that deals damage on contact.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| damage | Damage to deal | float | 1.0 |
| target_tag | Tag of entities to damage | string | enemy |
| duration | How long the hitbox lasts (seconds) | float | 0.2 |
| width | Width of the hitbox | float | 32.0 |
| height | Height of the hitbox | float | 32.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Hitbox"],
  "behaviour_config": {
    "Hitbox": {
      "damage": "<value>"
    }
  }
}
```

## IncrementCounterOnEvent
Listens for a Mesh event and increments a global counter.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| event_type | Mesh event name to react to (required) | string | - |
| payload_field | Optional payload key to filter by | string | - |
| payload_value | Value that payload_field must match | string | - |
| counter | Name of the counter to increment | string | - |
| amount | Amount to increment by | float | 1.0 |
| scope | Scope of the counter ('global' or 'quest') | string | global |
| quest_id | Quest ID if scope is 'quest' | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["IncrementCounterOnEvent"],
  "behaviour_config": {
    "IncrementCounterOnEvent": {
      "event_type": "<value>"
    }
  }
}
```

## Interactable
Emits on_interact when a nearby entity presses the interact key.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| interact_radius | Maximum distance for interaction | float | 48.0 |
| interact_key | Key binding name for interaction (e.g., 'interact', 'use') | string | interact |
| interact_event | Event type to emit on interaction | string | on_interact |
| interact_label | UI label shown when in range | string | Interact |
| target_tags | Tags of entities that can interact (empty = 'player') | array | ['player'] |
| cooldown | Minimum time between interactions (seconds) | float | 0.5 |
| one_shot | If true, can only be interacted with once | bool | False |
| enabled | Whether interaction is active | bool | True |
| require_line_of_sight | Require unobstructed path to interactor | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Interactable"],
  "behaviour_config": {
    "Interactable": {
      "interact_radius": "<value>"
    }
  }
}
```

## InventoryHolder
Stores configured inventory items and can transfer them into the shared inventory bucket.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| items | List of item ids or {id, amount} objects tied to assets/data/items.json. | array | [] |
| consume_on_transfer | Remove held items after transfer_to_inventory runs. | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["InventoryHolder"],
  "behaviour_config": {
    "InventoryHolder": {
      "items": "<value>"
    }
  }
}
```

## LightSource
Adds a dynamic light that follows the entity.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| radius | - | float | 160.0 |
| color | - | string | #ffffff |
| color_rgba | - | array | - |
| mode | - | string | soft |
| offset_x | - | float | 0.0 |
| offset_y | - | float | 0.0 |
| enabled | - | bool | True |
| cookie_id | - | string | - |
| cookie_scale | - | float | 1.0 |
| cookie_rotation_deg | - | float | 0.0 |
| cookie_offset_px | - | array | - |
| flicker_enabled | Whether the light radius should flicker over time. | bool | False |
| flicker_seed | - | int | - |
| flicker_amount | Flicker intensity scale (0..1); values >1 treated as legacy pixel radius. | float | 20.0 |
| flicker_radius_px | Override radius flicker in pixels (legacy). | float | - |
| flicker_intensity | Override intensity flicker scale (0..1). | float | - |
| flicker_speed | Flicker speed in cycles per second (roughly). | float | 5.0 |
| shafts_enabled | - | bool | False |
| shafts_length_px | - | float | 220.0 |
| shafts_width_px | - | float | 140.0 |
| shafts_rotation_deg | - | float | 0.0 |
| shafts_alpha | - | float | 0.35 |
| shafts_noise_speed | - | float | 0.08 |
| shafts_noise_amount | - | float | 0.15 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["LightSource"],
  "behaviour_config": {
    "LightSource": {
      "radius": "<value>"
    }
  }
}
```

## ListenForEvent
Invokes reactions when a Mesh event with the desired payload arrives.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| event_type | Mesh event name to react to | string | - |
| payload_field | Optional payload field that must be present | string | - |
| payload_value | Optional value to match on the payload field | string | - |
| forward_as | Re-emit the payload under this event name when matched | string | - |
| message | Console message template when triggered (format with payload) | string | - |
| once | Stop listening after the first match | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ListenForEvent"],
  "behaviour_config": {
    "ListenForEvent": {
      "event_type": "<value>"
    }
  }
}
```

## MainMenuBehaviour
Handles the main menu logic and rendering.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| _No config fields_ | | | |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["MainMenuBehaviour"],
  "behaviour_config": {
    "MainMenuBehaviour": {
      "config_field": "<value>"
    }
  }
}
```

## MessageOnZoneEnter
Logs a console message whenever a configured zone is entered.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| zone_name | Name of the TriggerZone entity to watch | string | - |
| message | Optional message template (supports {actor} and {zone}) | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["MessageOnZoneEnter"],
  "behaviour_config": {
    "MessageOnZoneEnter": {
      "zone_name": "<value>"
    }
  }
}
```

## MonsterEncounterZone
Starts a monster battle when the target enters an eligible encounter zone.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| trigger_radius | Distance threshold for triggering | float | 0.0 |
| trigger_target | Name of the player sprite to watch | string | - |
| encounter_id | Stable encounter id for return context | string | - |
| enabled | Whether encounters can trigger | bool | True |
| enabled_flag | Optional game-state flag required to enable encounters | string | - |
| cooldown_seconds | Cooldown after a roll/start | float | 1.0 |
| chance | Encounter chance per eligible enter update | float | 1.0 |
| player_species_id | Temporary player-side species id for MON-0e | string | - |
| player_level | Temporary player-side level for MON-0e | int | 5 |
| encounter_table | Weighted encounter table | array | [] |
| companion_mode | Start a companion battle (auto-acting monster + Praise/Scold/Wait) | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["MonsterEncounterZone"],
  "behaviour_config": {
    "MonsterEncounterZone": {
      "trigger_radius": "<value>"
    }
  }
}
```

## NpcSchedule
Switches NPC position or patrol route based on time-of-day windows.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| schedules | List of schedule blocks with start/end hours and stand/patrol actions. | array | [] |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["NpcSchedule"],
  "behaviour_config": {
    "NpcSchedule": {
      "schedules": "<value>"
    }
  }
}
```

## OfferPerkChoice
Offers a choice of perks to the player via dialogue.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| start_event | Mesh event name that triggers this offer | string | - |
| interact | Trigger on player interaction | bool | True |
| text | Text to display in the dialogue | string | Choose a blessing... |
| speaker | Speaker name for the dialogue | string | Shrine |
| pool | List of perk IDs to offer (empty for all available) | array | [] |
| once | Only offer once per game session (persisted via game state) | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["OfferPerkChoice"],
  "behaviour_config": {
    "OfferPerkChoice": {
      "start_event": "<value>"
    }
  }
}
```

## ParticleEmitter
Spawns particle bursts or continuous emissions.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| mode | burst or rate | string | burst |
| count | Burst particle count | int | 8 |
| rate | Particles per second | float | 12.0 |
| preset | FX preset id | string | - |
| seed | Optional RNG seed | string | - |
| emitter_id | Stable id for per-emitter budgets | string | - |
| max_alive | Max alive particles for this emitter (0=unbounded) | int | 0 |
| offset | Spawn offset [x,y] | array | [0.0, 0.0] |
| spawn_shape | Spawn shape: point/circle/box/line | string | point |
| radius | Circle radius | float | 0.0 |
| radius_min | Circle inner radius | float | 0.0 |
| radius_max | Circle outer radius | float | 0.0 |
| box_size | Box size [w,h] | array | [] |
| line_from | Line start [x,y] | array | [] |
| line_to | Line end [x,y] | array | [] |
| line_len | Line length | float | 0.0 |
| line_angle_deg | Line angle in degrees | float | 0.0 |
| life_min | Min lifetime seconds | float | 0.3 |
| life_max | Max lifetime seconds | float | 0.6 |
| alpha_curve | Alpha over-life curve | string | linear |
| scale_curve | Scale over-life curve | string | linear |
| speed_min | Min speed | float | 1.0 |
| speed_max | Max speed | float | 3.0 |
| size | Circle texture size | float | 4.0 |
| color | RGB(A) list | array | [255, 255, 255] |
| shape | Generated shape | string | circle |
| sprite | Optional sprite texture path | string | - |
| rect | Sprite rect [x,y,w,h] | array | [] |
| frame | Sprite frame index | int | -1 |
| frame_size | Sprite frame size [w,h] | array | [] |
| frame_xy | Sprite frame coords [col,row] | array | [] |
| grid_cols | Sprite sheet columns (for frame index) | int | 0 |
| frames | Random frame choices | array | [] |
| frame_range | Random frame range [min,max] | array | [] |
| frame_weights | Weighted frame choices {index: weight} | object | {} |
| anim_frames | Animated frame sequence | array | [] |
| anim_frame_range | Animated frame range [min,max] | array | [] |
| anim_fps | Animation frames per second | float | 0.0 |
| anim_loop | Loop animation | bool | True |
| anim_phase | Animation phase sync or random | string | sync |
| additive | Additive blend draw | bool | False |
| scale0 | Start scale | float | 1.0 |
| scale1 | End scale | float | 0.0 |
| alpha0 | Start alpha | float | 255.0 |
| alpha1 | End alpha | float | 0.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ParticleEmitter"],
  "behaviour_config": {
    "ParticleEmitter": {
      "mode": "<value>"
    }
  }
}
```

## Patrol
Moves between waypoints defined in the scene data.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| patrol_points | List of {x,y} waypoints to visit | array | [] |
| patrol_speed | Movement speed between points | float | 80.0 |
| points | Alias for patrol_points | array | [] |
| speed | Alias for patrol_speed | float | 80.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Patrol"],
  "behaviour_config": {
    "Patrol": {
      "patrol_points": "<value>"
    }
  }
}
```

## PatrolChase
Patrols between waypoints and switches to pathfinding chase when a target is acquired.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| patrol_points | List of {x,y} waypoints to visit | array | [] |
| patrol_tag | If set, discover waypoint entities by mesh_tag (sorted deterministically) | string | - |
| patrol_speed | Movement speed while patrolling | float | 80.0 |
| chase_speed | Movement speed while chasing | float | 90.0 |
| acquire_radius_tiles | Acquire range in tiles | int | 8 |
| leash_radius_tiles | Stop chasing when target exceeds this range in tiles | int | 12 |
| stop_range_tiles | If within this range, stop moving but remain in chase state | int | 0 |
| give_up_ticks | If no_path persists this many ticks, disengage | int | 30 |
| cooldown_ticks | Ticks to stay idle after giving up | int | 60 |
| target_entity_id | Authored entity id to chase (matches mesh_entity_data.id) | string | - |
| target_tag | Fallback: chase the nearest entity with this mesh_tag | string | - |
| los_required | If true, require grid line-of-sight to acquire target | bool | False |
| return_to_patrol | If true, return to patrol route after disengaging | bool | True |
| resume_waypoint_mode | After returning, resume from nearest waypoint or continue to next | string | nearest |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["PatrolChase"],
  "behaviour_config": {
    "PatrolChase": {
      "patrol_points": "<value>"
    }
  }
}
```

## PatrolPath
Patrols between waypoints with loop/pingpong modes.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| waypoints | List of {x, y} or marker names | array | [] |
| waypoint_tag | If set, discover waypoints by mesh_tag (sorted by x then y) | string | - |
| speed | Movement speed in units per second | float | 60.0 |
| mode | Patrol mode: 'loop', 'pingpong', or 'once' | string | loop |
| arrive_radius | Distance to consider a waypoint reached | float | 4.0 |
| wait_time | Time to wait at each waypoint (0 = no wait) | float | 0.0 |
| start_on_create | Start patrol immediately on creation | bool | True |
| enabled | Whether the patrol is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["PatrolPath"],
  "behaviour_config": {
    "PatrolPath": {
      "waypoints": "<value>"
    }
  }
}
```

## PickupCollectible
Allows a sprite to be collected via the interact action.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| collector_tag | Sprite tag required to collect | string | player |
| remove_on_collect | Remove sprite after pickup | bool | True |
| once | Only allow a single pickup | bool | True |
| item_id | Item id to grant when collected (uses assets/data/items.json) | string | - |
| item_amount | Quantity granted for item_id | int | 1 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["PickupCollectible"],
  "behaviour_config": {
    "PickupCollectible": {
      "collector_tag": "<value>"
    }
  }
}
```

## PlayerController
Handles WASD movement and interaction for the player sprite.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| speed | Movement speed in units per second (fixed at 150) | float | 150.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["PlayerController"],
  "behaviour_config": {
    "PlayerController": {
      "speed": "<value>"
    }
  }
}
```

## Projectile
Moves in a straight line and damages targets on impact.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| speed | Movement speed | float | 300.0 |
| damage | Damage to deal | float | 1.0 |
| target_tag | Tag of entities to damage | string | player |
| lifetime | Time in seconds before auto-destroy | float | 2.0 |
| direction | Direction in degrees (0 is right) | float | 0.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Projectile"],
  "behaviour_config": {
    "Projectile": {
      "speed": "<value>"
    }
  }
}
```

## QuestGiver
Starts a quest when an event occurs (e.g. after talking to an NPC).

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| quest_id | Quest id to start. | string | - |
| listen_event | Event name to listen for. | string | quest_start |
| auto_activate | Immediately start the quest when event fires. | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["QuestGiver"],
  "behaviour_config": {
    "QuestGiver": {
      "quest_id": "<value>"
    }
  }
}
```

## QuestHook
Listens for events and updates quest counters/steps.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| quest_id | Quest identifier | string | - |
| step_id | Step identifier within quest | string | - |
| listen_events | Event types to listen for | array | [] |
| counter_name | Name of counter to track | string | count |
| target_count | Target count to complete step (-1 = no limit) | int | 1 |
| increment | Amount to increment counter per event | int | 1 |
| event_filter | Filter events by payload values (dict) | object | {} |
| one_shot | Only trigger once then ignore events | bool | False |
| enabled | Whether the hook is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["QuestHook"],
  "behaviour_config": {
    "QuestHook": {
      "quest_id": "<value>"
    }
  }
}
```

## QuestProgressOnEvent
Listens for a Mesh event and forwards it to the QuestManager to start, advance, or complete a quest stage.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| quest_id | Quest identifier that should be updated | string | - |
| action | Action to perform (start, set_stage, complete_stage, complete_quest) | string | complete_stage |
| stage_id | Optional stage to target (falls back to current stage) | string | - |
| event_type | Mesh event that should trigger the quest update | string | - |
| payload_field | Payload key that must be present on the event | string | - |
| payload_value | Optional value that payload_field must equal | string | - |
| payload_equals | Object of payload key/value pairs that must match | object | {} |
| once | If true the behaviour only fires the first time | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["QuestProgressOnEvent"],
  "behaviour_config": {
    "QuestProgressOnEvent": {
      "quest_id": "<value>"
    }
  }
}
```

## RangedAttackAI
Attacks the player from a distance.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| attack_range | Maximum distance to attack from | float | 200.0 |
| attack_cooldown | Time between attacks in seconds | float | 2.0 |
| projectile_speed | Speed of the projectile | float | 300.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["RangedAttackAI"],
  "behaviour_config": {
    "RangedAttackAI": {
      "attack_range": "<value>"
    }
  }
}
```

## RangedEnemyAI
AI that keeps distance and shoots at the target.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_tag | Tag of the target entity | string | player |
| detect_radius | Radius to detect target | float | 400.0 |
| attack_radius | Radius to start shooting | float | 300.0 |
| flee_radius | Radius to flee if target gets too close | float | 150.0 |
| speed | Movement speed | float | 80.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["RangedEnemyAI"],
  "behaviour_config": {
    "RangedEnemyAI": {
      "target_tag": "<value>"
    }
  }
}
```

## RewardChest
Spawns or enables a reward when unlocked.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| unlock_event | Event ID that reveals the reward | string | - |
| item_id | Item ID to reward | string | - |
| gold | Amount of gold to reward | int | 0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["RewardChest"],
  "behaviour_config": {
    "RewardChest": {
      "unlock_event": "<value>"
    }
  }
}
```

## SceneExit
Triggers a scene change to a target scene/spawn when an event fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_event | Event name to listen for (e.g. from TriggerZone or Interact). | string | use_exit |
| target_scene | Path to the target scene JSON. | string | - |
| target_spawn | Spawn id in the target scene. | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["SceneExit"],
  "behaviour_config": {
    "SceneExit": {
      "listen_event": "<value>"
    }
  }
}
```

## SceneTransition
Requests a new scene when the player interacts or an event fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_scene | Path to the JSON scene that should load | string | - |
| spawn_id | Optional spawn marker ID to use in the destination scene | string | - |
| spawn_point | Alias for spawn_id | string | - |
| allow_interact | If true, allow the player interact button to trigger the transition | bool | True |
| event_type | Optional Mesh event name that triggers the transition | string | - |
| event_field | Optional payload field to check before reacting to the event | string | - |
| event_value | Optional value that event_field must equal | string | - |
| once | Prevent the transition from firing more than once | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["SceneTransition"],
  "behaviour_config": {
    "SceneTransition": {
      "target_scene": "<value>"
    }
  }
}
```

## SequencePlayer
Runs declarative cutscene steps such as waits, movement, dialogue, and events.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| steps | Ordered list of step dictionaries (type+fields) | array | [] |
| auto_start | Automatically begin once after the scene loads | bool | False |
| start_event | Mesh event that triggers the sequence | string | - |
| event_field | Optional payload field that must exist for start_event | string | - |
| event_value | Optional value that event_field must equal before starting | string | - |
| lock_player_input | Lock PlayerController input while the sequence is active | bool | True |
| lock_owner | Custom owner label for the input lock (defaults to entity name) | string | - |
| once | Prevent re-triggering after the sequence finishes | bool | True |
| default_move_speed | Fallback speed (units/sec) for move steps | float | 120.0 |
| move_tolerance | Distance threshold (px) treated as reaching the target | float | 2.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["SequencePlayer"],
  "behaviour_config": {
    "SequencePlayer": {
      "steps": "<value>"
    }
  }
}
```

## SetGameStateOnEvent
Listens for a Mesh event and toggles flags / increments counters when it fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| event_type | Mesh event name to react to (required) | string | - |
| payload_field | Optional payload key that must exist | string | - |
| payload_value | Optional value that payload_field must equal (string compare) | string | - |
| set_flags | Object mapping flag names to booleans | object | {} |
| clear_flags | List of flags that should be forced to false | array | [] |
| inc_counters | Object mapping counter names to amounts to add | object | {} |
| require_flags | List of flags that must be true to apply the mutation | array | [] |
| forbid_flags | List of flags that must be false to apply the mutation | array | [] |
| once | Apply the mutation only the first time the event fires | bool | False |
| message | Optional console message when the state update runs | string | - |
| toast | Optional HUD toast message when the state update runs | string | - |
| toast_seconds | Optional toast duration in seconds | float | 0.0 |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["SetGameStateOnEvent"],
  "behaviour_config": {
    "SetGameStateOnEvent": {
      "event_type": "<value>"
    }
  }
}
```

## Shooter
Allows an entity to shoot projectiles.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| projectile_speed | Speed of the projectile | float | 300.0 |
| damage | Damage dealt per shot | float | 1.0 |
| cooldown | Time in seconds between shots | float | 2.0 |
| range | Max range (lifetime * speed) | float | 400.0 |
| target_tag | Tag of entities to damage | string | player |
| shoot_sound | Sound to play on shoot | string | assets/sounds/shoot.wav |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Shooter"],
  "behaviour_config": {
    "Shooter": {
      "projectile_speed": "<value>"
    }
  }
}
```

## SwitchInteract
Emits an event when interacted with.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| event_id | Event ID to emit | string | - |
| one_shot | If true, can only be used once | bool | False |
| active_sprite | Sprite path for active state | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["SwitchInteract"],
  "behaviour_config": {
    "SwitchInteract": {
      "event_id": "<value>"
    }
  }
}
```

## TimeOfDayGate
Enables/disables an entity based on time-of-day windows.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| start_hour | Hour when gate becomes active. | float | 6.0 |
| end_hour | Hour when gate becomes inactive. | float | 20.0 |
| invert | If true, active outside the window. | bool | False |
| affect_visibility | Toggle entity visibility. | bool | True |
| open_event | Event to emit when becoming active. | string | - |
| close_event | Event to emit when becoming inactive. | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["TimeOfDayGate"],
  "behaviour_config": {
    "TimeOfDayGate": {
      "start_hour": "<value>"
    }
  }
}
```

## Timer
Emits an event after a duration, optionally repeating.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| duration | Time in seconds before firing | float | 1.0 |
| repeat | If true, restarts after firing | bool | False |
| repeat_count | Number of times to repeat (-1 = infinite) | int | -1 |
| timer_event | Event type to emit when timer fires | string | on_timer |
| auto_start | Start timer automatically on creation | bool | True |
| timer_id | Optional identifier for this timer | string | - |
| enabled | Whether the timer is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Timer"],
  "behaviour_config": {
    "Timer": {
      "duration": "<value>"
    }
  }
}
```

## ToggleSceneLights
Toggle or force on/off one or more scene lights in response to an event.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| listen_event | Name of the event to listen for. | string | - |
| group | Optional group name to match lights by their 'group' field. | string | - |
| indices | Optional list of indices into scene['lights']. | string | [] |
| mode | One of 'toggle', 'on', 'off'. | string | toggle |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ToggleSceneLights"],
  "behaviour_config": {
    "ToggleSceneLights": {
      "listen_event": "<value>"
    }
  }
}
```

## ToggleSwitch
Simple interactable switch that flips state and emits an event.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| allowed_tag | Sprite tag allowed to toggle the switch | string | player |
| label | Friendly name used in logs | string | - |
| initial_state | Starting ON/OFF state | bool | False |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["ToggleSwitch"],
  "behaviour_config": {
    "ToggleSwitch": {
      "allowed_tag": "<value>"
    }
  }
}
```

## TriggerVolume
Detects entities entering/exiting a rectangular or polygon volume.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| volume_type | Type of volume: 'rect' or 'polygon' | string | rect |
| width | Width of rectangular volume (if volume_type='rect') | float | 64.0 |
| height | Height of rectangular volume (if volume_type='rect') | float | 64.0 |
| polygon | List of [x, y] points relative to entity (if volume_type='polygon') | array | [] |
| target_tags | List of entity tags that can trigger (empty = all) | array | [] |
| target_name | Specific entity name to watch (empty = use tags) | string | - |
| on_enter_event | Event type to emit on enter (empty = 'on_enter') | string | on_enter |
| on_exit_event | Event type to emit on exit (empty = 'on_exit') | string | on_exit |
| one_shot | If true, only fire enter once per entity | bool | False |
| enabled | Whether the trigger is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["TriggerVolume"],
  "behaviour_config": {
    "TriggerVolume": {
      "volume_type": "<value>"
    }
  }
}
```

## TriggerZone
Fires once when a target sprite enters a radius.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| trigger_radius | Distance threshold for triggering | float | 0.0 |
| trigger_target | Name of the sprite to watch | string | - |
| on_trigger | Label describing the triggered event | string | - |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["TriggerZone"],
  "behaviour_config": {
    "TriggerZone": {
      "trigger_radius": "<value>"
    }
  }
}
```

## Vendor
Handles shop stock and opens the shop UI on events.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| shop_id | Logical id of this shop. | string | - |
| currency_counter | GameState counter used as currency. | string | gold |
| stock | List of {item_id, price, quantity} entries. | array | [] |
| listen_event | Mesh event to open this shop. | string | open_shop |
| buy_sound | Sound to play on successful purchase. | string | - |
| fail_sound | Sound to play on failed purchase. | string | - |
| buy_rate | Multiplier for prices when buying. | float | 1.0 |
| sell_rate | Multiplier for prices when selling to vendor. | float | 0.5 |
| sell_enabled | If false, vendor will not buy items. | bool | True |
| sell_whitelist | List of item_ids allowed to sell (if empty, allow all). | array | [] |
| sell_blacklist | List of item_ids vendor will never buy. | array | [] |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Vendor"],
  "behaviour_config": {
    "Vendor": {
      "shop_id": "<value>"
    }
  }
}
```

## Wander
Randomly wanders within a radius using pathfinding.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| wander_radius | Maximum distance in tiles from origin to wander | float | 5.0 |
| min_wander_distance | Minimum distance in tiles for each wander move | float | 2.0 |
| speed | Movement speed while wandering | float | 40.0 |
| idle_time_min | Minimum time to idle between wanders (seconds) | float | 1.0 |
| idle_time_max | Maximum time to idle between wanders (seconds) | float | 3.0 |
| anchor_to_spawn | If true, anchor to spawn position; else current position | bool | True |
| max_path_attempts | Maximum attempts to find a valid wander path | int | 5 |
| enabled | Whether wander is active | bool | True |

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Wander"],
  "behaviour_config": {
    "Wander": {
      "wander_radius": "<value>"
    }
  }
}
```
