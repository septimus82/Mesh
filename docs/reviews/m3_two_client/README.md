# M3-5/M3-6: two clients in one HD-2D room (evidence)

Plan: `docs/plans/hd2d_online_investigation.md` §6, M3 items 5–6 (and the client guard in §3.3).

> **Frames to be regenerated after the P1 hidden-window fix.** These frames come from commit `4e21efe7`. Round 2 of
> #604 changed where some players stop: every walk now settles within 8 px rather than 4, A strikes from x 504 rather
> than 512, and B strikes from y 610 rather than 624. The frames still show round 1's spots. The facts quoted below are
> round 1's too. Local GPU runs are paused project-wide until that fix lands.

## Where the pictures come from

The pictures come from the **evidence script** (`tooling/m3_two_client_evidence.py`), not from the CI test. The script
plays the same scenario that `tests/test_mesh_net_hd2d_gpu.py` asserts, and it uses the same code: the runner's `run`
with frame capture turned on. The gpu-lane test runs that scenario without capturing frames and writes nothing into the
repository.

That run uses one real authority (`mesh_net.server.WorldServer`) and two real hidden client windows
(`tooling/net_world_probe.py`), each its own process with its own copy of the project. Every window fact is read from
that window's own objects. The pictures are those windows' framebuffers, read back; they are not OS screenshots.

The script keeps a run's pictures only if the acceptance tests' own assertions all hold on that run's facts.
[run.json](run.json) lists the checks that passed. [facts.json](facts.json) holds everything the run recorded: server
positions, window facts, camera states, refusal texts, the transfer history, each walk's legs, and `foreign_keys`.

`foreign_keys` counts key events a window received that the probe never sent. The probe stops such events (see
"Probe settings" below). It was 0 in both windows in this run.

## The room

The room is M1-B's **Crossing** (`tooling/hd2d_m1b_scene.py`), built in Mesh Studio with Studio's own input events. Its
ground is at 0 m, with a 2 m bridge deck, stairs up each side and an underpass beneath the deck.

Two things were then added on the ground directly under the deck. They were authored with the documented operations
(`mesh author apply`, the validated operations Studio and the MCP server use), never by editing scene files:

- **a bandit** at (17, 21) m: Studio's *Person*, renamed, tagged `enemy`, with Health (1 HP) and a DropTable that drops
  5 gold. That drop is the loot the run takes.
- **a walk-in door** at (15, 20.5) m: a 0.75 x 1 m invisible Passage, linked (`link_rooms`) to the starter's **Start**
  room, with a door back.

There is no water, so the authority runs the room. The shipped M1-B evidence scene is unchanged: the additions exist
only in the run's own copy.

## Probe settings that change the picture

- **The controls hint is off.** Net clients never call `PlayerHUD.update` (the HUD isn't ticked in their loop), so a
  toast never expires. The room's 4 s controls hint would stay over the middle of every picture for good. The probe
  turns that hint off for project runs. Making net clients tick the HUD is a product follow-up.
- **Only the probe's own keys reach the client.** A hidden window can still be activated and take the keyboard. The
  probe marks the keys it sends, and stops and counts any other key event.

## The pictures

Each picture shows window A on the left and window B on the right, at 640 x 360. A peer's avatar is drawn tinted. Where
a picture can't show the claim, the caption says so and points at the facts.

| Picture | What it shows | Backed by |
|---|---|---|
| [01_start](01_start.png) | The start. Both avatars spawn at the same spot, so they overlap and read as one figure. Both are there, on the ground (`facts.json`: `a.a.other_before` is B at the spawn while A sets off). | `test_each_player_climbs_onto_the_deck_and_back_down` |
| [02_a_on_deck](02_a_on_deck.png) | A has climbed the west stairs onto the deck: 2 m, `bridge_6m/col_deck`. A's window follows A up there. B's window follows B on the ground, and A is out of B's view. | `test_each_player_climbs_onto_the_deck_and_back_down`: the server, A's window and B's window all hold A at 64 px on the deck. |
| [02_b_on_deck](02_b_on_deck.png) | A is back down; B is on the deck. | the same test, for B |
| [03_a_over_b_under](03_a_over_b_under.png) | A on the deck, B directly beneath A on the ground, both at (534.5, 654) px. B has just walked under A, from south of the deck to north of it, and back. | `test_one_stands_on_the_deck_while_the_other_passes_beneath`, `test_each_camera_follows_its_own_character` |
| [seq_b_passes_beneath_a.gif](seq_b_passes_beneath_a.gif) | B walking under A, one frame per 20 px B walks (both windows, half size). | `test_one_stands_on_the_deck_while_the_other_passes_beneath`: 66 server samples. A never moved; B stayed on `ground`, within 16 px of A's x, from y 504 to 751.5. |
| [04_a_struck_from_deck](04_a_struck_from_deck.png) | Just after A, on the deck, struck at the bandit beneath. A faced it with its hitbox on it in plan, so only the floors could refuse the strike. **B stands in front of the bandit and hides it in both windows.** The proof is in `facts.json` under `c`: `a_planar_hit` true, `a_swung` true (round 2 adds it), HP 1 before and after. | `test_no_attack_through_the_deck` |
| [05_a_reached_for_loot](05_a_reached_for_loot.png) | B felled the bandit with one strike (it is gone). Then A, on the deck 30.4 px from the loot, asked to take it, and the loot stays. **The loot marker, a 6 px circle, isn't visible at this size.** Both windows' snapshots list the drop (`c.drops_seen`). After A's take, it is still dropped and held by nobody (`c.after_a_take`). | `test_no_attack_through_the_deck`, `test_no_looting_through_the_deck` |
| [06_b_took_loot](06_b_took_loot.png) | B took the loot on the ground. Both windows' snapshots record B holding it (`c.loot_seen`). | `test_no_looting_through_the_deck` |
| [07_a_over_door](07_a_over_door.png) | A walked across the door's area on the deck. **The door is an invisible Passage, so it isn't drawn**; it lies under the deck at (15, 20.5) m. The run measured A's picture overlapping its area in plan (`door.a_touched_area`), with no transfer in the server or A's window. | `test_no_door_through_the_deck` |
| [08_b_through_door](08_b_through_door.png) | B walked into the door on the ground and went through to Start (B's window, a 2D room). A's window sees B gone. | `test_no_door_through_the_deck`: the run's only transfer is B's through this door. |

### What the pictures can't show

The two refused clients have no picture: a refused window never plays the room. Their part is in `facts.json` under
`e`, and two tests assert it.

- **Mismatched geometry.** The bridge's deck collider is 0.5 m higher in the client's own files. It is refused at
  welcome ("the server runs a different world") before loading any room.
  Test: `test_a_client_whose_geometry_differs_is_refused_and_the_room_plays_on`.
- **2D fallback.** The room's 3D build fails in the client, simulating a driver refusal. It loads the room in 2D,
  refuses to join it (the M1-A-2 guard) and leaves.
  Test: `test_a_client_whose_room_fell_back_to_2d_refuses_it_and_the_room_plays_on`.

In both cases the two players are untouched (same positions, both online, nobody else) and the server runs on.

### The rendered-height check

The test also checks, from these windows' framebuffers, that each avatar is drawn at its own height:

- the window renders the picture with each avatar and without it;
- the lowest changed row must sit within 6 px of where the renderer's camera puts that avatar's feet at the snapshot's
  elevation, and further than 6 px from the other floor's row.

In this run, window A drew B's feet at row 139 (expected 139.6; the deck's row there is 90.0), and B's window drew A's
feet at row 98 (expected 97.9; the ground's row is 151.6).

## Regenerate

```
py -3.13 tooling/m3_two_client_evidence.py docs/reviews/m3_two_client [--work DIR]
```

This builds the room in a hidden Studio window, adds the bandit and the door, plays the run with frame capture, checks
it with the acceptance tests' assertions, and writes these files. It takes about 2.5 minutes. `--work` keeps the built
project, the raw frames and the full facts.

Run it with `MESH_GL_SMOKE=1`, and with `PYTHONPATH` set to the checkout when an editable install points elsewhere. It
uses hidden windows only, plays no sound (master volume 0), and sends no OS input. Don't run it until the P1
hidden-window fix has landed: until then a hidden window can take keyboard focus from the foreground.

## Machine

These files were generated at commit `4e21efe7`.

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4070/PCIe/SSE2 |
| OS | Windows 11 |
| Python | 3.13.3 |
| Build and run | 133 s |
