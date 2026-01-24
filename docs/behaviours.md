# Behaviours

Behaviour registry exported from Mesh.

## Animator
Cycles sprite textures using named animation states.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| animations | Mapping of state name to a list of texture paths | string | {} |
| animation_state | Initial animation state to play | string | idle |
| animation_frame_rate | Frames per second for the active animation | float | 8.0 |

Each entry inside `animations` can optionally specify a playback `mode`:

- `loop`: cycles frames `0 -> 1 -> ... -> last -> 0` continuously.
- `once`: plays through once and optionally transitions to the animation referenced by `next`.
- `ping-pong`: walks forward to the last frame and then back down `... -> 1 -> 0` before repeating.

Example configuration snippet:
```json
{
  "name": "ExampleEntity",
  "sprite": "assets/example.png",
  "behaviours": ["Animator"],
  "behaviour_config": {
    "Animator": {
      "animations": {
        "torch": {
          "frames": [
            "assets/sprites/torch_0.png",
            "assets/sprites/torch_1.png",
            "assets/sprites/torch_2.png"
          ],
          "fps": 6,
          "mode": "ping-pong"
        }
      }
    }
  }
}
```

## CameraFollow
Moves the window camera toward the entity each frame.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| lerp_factor | How quickly the camera catches up to the entity | float | 5.0 |
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

## DamageOnTouch
Emits a damage event when colliding with the target sprite.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_name | Name of the sprite that should receive damage | string | player |
| damage | Damage value applied on contact | float | 1.0 |
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

## Patrol
Moves between waypoints defined in the scene data.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| patrol_points | List of {x,y} waypoints to visit | array | [] |
| patrol_speed | Movement speed between points | float | 80.0 |

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

## SceneTransition
Requests a new scene when the player interacts or an event fires.

| Name | Description | Type | Default |
| --- | --- | --- | --- |
| target_scene | Path to the JSON scene that should load | string | - |
| spawn_id | Optional spawn marker ID to use in the destination scene | string | - |
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
| once | Apply the mutation only the first time the event fires | bool | False |
| message | Optional console message when the state update runs | string | - |

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
