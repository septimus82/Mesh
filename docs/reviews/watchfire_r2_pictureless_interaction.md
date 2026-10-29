# Watchfire R2: talking to a campfire that has no picture

A creator-trial fix (*The Last Watchfire*). It is not a milestone. Base: `redesign/visual-editor` at `0f818c1`.

## The defect

Studio lets a creator give a campfire a conversation, but in play nothing happens when the player walks up to it and
presses E. The trial worked around this with a marker sign beside the fire that carries the conversation.

## Why

The interaction pipeline (`engine/interaction.py`) works like this:

1. `resolve_interaction_candidate` takes the room's sprites.
2. `_candidate_from_entity` checks the flag gates, the position, `_eligible_behaviours`, the reach (72 px by default,
   or the object's own radius) and the facing rule.
3. `select_interaction_candidate` ranks the candidates by priority, then facing, then distance, then id.
4. `perform_interaction` calls the chosen behaviour's `on_interact`; Dialogue opens the conversation.

The campfire fails at step 2, on the first line of `_eligible_behaviours`:

```python
if getattr(entity, "visible", True) is False:
    return ()  # hidden (e.g. by ConditionalActivator): nothing there to interact with
```

That line (`d2b2c61`, "Hidden objects can't be interacted with") was written for objects that `ConditionalActivator`
hides. It uses `visible` to mean "hidden", but `visible` also means something else.
`scene_controller_parts/entity_factory.py` makes every entity **without a picture** `visible = False` (and
`mesh_drawn = False`): those are logic-only objects such as arrival spots and triggers, and they are never drawn.
A campfire has no picture. The world draws it itself: `engine.fire` registers it, and the renderer draws its logs and
flames according to its "Show when" flags. So its sprite is never `visible`, and the gate reads it as hidden. The water
code already documents this distinction: `water.active`'s docstring says "a water object has no picture, so its
sprite is never visible: that isn't the test".

Confirmed on a scratch copy of the trial game, before the fix, on engine tree `0f818c1`. The marker's conversation was
moved onto the cold watchfire with Studio's own operations, and the marker removed. The player then accepted the
task, walked to two steps south of the fire, facing it, and pressed E. The cold fire's sprite showed `visible: false,
drawn: false`, and nothing happened. The result was the same from source and from an exported build.

## The fix (one function, existing path)

`engine/interaction.py` gets a new `_present(entity)`. The visibility gate in `_eligible_behaviours` uses it instead
of `visible`:

- **A drawn object**: exactly as before. It's there while it's `visible`, so `ConditionalActivator` and a collected
  pickup still hide it.
- **A picture-less object**: it's there only while the world draws it as a campfire. That means it is one of this
  room's `fire.fires_of(window)`, the same list (with its "Show when" flags) the renderer and the lights use.
- **Any other picture-less object** (an arrival spot, a trigger, a picture-less object with `ConditionalActivator`
  hiding it): still nothing there.

Nothing else changes:

- reach, facing, priority, ranking, labels, the HUD prompt and `perform_interaction`;
- 2D sprite and NPC interaction;
- the player-position picker, which never had the visibility gate;
- `Campfire` itself has no `on_interact`. A campfire without a conversation or other interaction is still not
  something to interact with.

## Evidence

`tooling/watchfire_r2_campfire.py` plays a scratch copy of the trial project in one real process, using the project's
own `main.py` in a hidden, silent window and the game's own keys. The trial project itself is never touched. With
`--bundle`, it plays the exported game (`mesh export build`) on its own engine copy. Reports and screenshots are in
`watchfire_r2_evidence/`:

| Run | E at the cold fire | "Strike the flint" | Fire | E by the lit fire |
|---|---|---|---|---|
| Before, source (0f818c1 tree) | nothing | not reachable | cold | nothing |
| Before, exported build (0f818c1) | nothing | not reachable | cold | nothing |
| After, source | "The kindling in the firepit is dry, …" with its two choices | sets `watchfire_lit` | burns | nothing (the cold one is hidden; the lit one has no conversation) |
| After, exported build | the same | the same | burns | nothing |

Screenshots, from the source runs:

- `before_e_at_the_fire_nothing_happens.png`
- `after_e_at_the_fire_its_conversation.png`
- `after_strike_the_flint_the_fire_burns.png`

## Tests

**`tests/test_interaction_pick_interactable.py`** gains two fast tests:

- A picture-less campfire with a conversation is picked, while a nearer picture-less non-campfire object is not.
- A campfire that its "Show when" flags hide is not picked, a shown one is, and a campfire not in this room's fires is
  not.

Against the old `interaction.py`, these 2 fail; the 4 existing tests pass either way (`before_unit_tests.txt`).

**`tests/test_campfire_interaction_gpu.py`** is GL-gated, a real hidden window on the M23B clearing:

- A campfire given a conversation with Studio's `set_dialogue_text` is walked up to with the arrow keys and answers E.
  The player reads on to the end.
- A picture-less trigger spot with a conversation, which the player provably reaches, says nothing.

This test fails against the old code (`before_real_window_test.txt`).

## Compatibility

- **What becomes interactable:** only picture-less campfires that carry an interacting behaviour (a conversation,
  usually) and that their "Show when" flags currently show. Projects that never gave a campfire a conversation see
  nothing new.
- **The prompt:** a campfire with a conversation now also shows the interaction prompt when the player is near it, as
  every interactable object does.
- **Rooms with a marker beside the fire** (like the trial game): if both the fire and the marker carry a conversation,
  the usual ranking (facing, then distance) picks between them. The trial game's own fires have none.
- **Not changed:**
  - Water bodies, which are also drawn by the world. Nothing has asked for interacting with water yet.
  - Editor selection and picking in the 3D view (a separate trial finding).

## Verification

Results are recorded in the PR: ruff gate, mypy (baseline 73), the interaction and dialogue tests, the full default
selection, the GPU tier, and required CI with its timing advisories reported separately.
