# M3-5/M3-6: two clients in one HD-2D room (evidence)

Plan: `docs/plans/hd2d_online_investigation.md` §6, M3 items 5–6 (and the client guard in §3.3).

These pictures come from the run that `tests/test_mesh_net_hd2d_gpu.py` asserts. That run uses one real authority
(`mesh_net.server.WorldServer`) and two real hidden client windows (`tooling/net_world_probe.py`), each its own process
with its own copy of the project. The test asserts on what each window's own objects say. The pictures are those same
windows' framebuffers, read back. They are not OS screenshots.

The script keeps a run's pictures only if all nine acceptance tests pass on that run's facts. [run.json](run.json)
lists them. [facts.json](facts.json) holds everything the run recorded: server positions, window facts, camera states,
refusal texts, the transfer history, and each walk's legs.

## The room

The room is M1-B's **Crossing** (`tooling/hd2d_m1b_scene.py`), built in Mesh Studio with Studio's own input events. Its
ground is at 0 m, with a 2 m bridge deck, stairs up each side and an underpass beneath the deck.

Three things were then added on the ground directly under the deck. They were authored with the documented operations
(`mesh author apply`, the validated operations Studio and the MCP server use), never by editing scene files:

- **a bandit**: Studio's *Person*, renamed, tagged `enemy`, with Health (1 HP) and a DropTable. Its loot is the item.
  It stands at (17, 21) m.
- **a walk-in door** at (15, 20.5) m: a 0.75 x 1 m invisible Passage, linked (`link_rooms`) to the starter's **Start**
  room, with a door back.

There is no water, so the authority runs the room. The shipped M1-B evidence scene is unchanged: the additions exist
only in the run's own copy.

## The pictures

Each picture shows window A on the left and window B on the right, at 640 x 360. A peer's avatar is drawn tinted.

| Picture | What it shows | Backed by |
|---|---|---|
| [01_start](01_start.png) | Both players at the start, on the ground. | `test_each_player_climbs_onto_the_deck_and_back_down` |
| [02_a_on_deck](02_a_on_deck.png) | A has climbed the west stairs onto the deck: 2 m, `bridge_6m/col_deck`. A's window follows A up there. B's window follows B on the ground; A is out of B's view. | `test_each_player_climbs_onto_the_deck_and_back_down`: the server, A's window and B's window all hold A at 64 px on the deck. |
| [02_b_on_deck](02_b_on_deck.png) | A is back down; B is on the deck. | the same test, for B |
| [03_a_over_b_under](03_a_over_b_under.png) | A on the deck, B directly beneath A on the ground, both at (534.5, 654) px. B has just walked under A from the south side of the deck to the north side and back. | `test_one_stands_on_the_deck_while_the_other_passes_beneath`, `test_each_camera_follows_its_own_character` |
| [seq_b_passes_beneath_a.gif](seq_b_passes_beneath_a.gif) | A frame sequence of B walking under A, one frame per 20 px B walks (both windows, half size). | `test_one_stands_on_the_deck_while_the_other_passes_beneath`: 66 server samples. A never moved; B stayed on `ground`, within 16 px of A's x, from y 504 to 751.5. |
| [04_a_struck_from_deck](04_a_struck_from_deck.png) | A has struck at the bandit beneath, from the deck. A was facing it with its hitbox on the bandit, so only the floors decide. The bandit stands with its HP unchanged. B is below the bandit. | `test_no_attack_through_the_deck` |
| [05_a_reached_for_loot](05_a_reached_for_loot.png) | B felled the bandit with one strike, and both windows' snapshots list its loot on the ground (the loot marker is a 6 px circle, barely visible at this size). Then A, on the deck 30.4 px from the loot, took: the loot stays. | `test_no_attack_through_the_deck`, `test_no_looting_through_the_deck` |
| [06_b_took_loot](06_b_took_loot.png) | B took the loot on the ground. Both windows' snapshots record B holding it. | `test_no_looting_through_the_deck` |
| [07_a_over_door](07_a_over_door.png) | A walked across the door's area on the deck, overlapping it in plan: no transfer, in the server or in A's window. | `test_no_door_through_the_deck` |
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
it with the acceptance tests, and writes these files. It takes about 2.5 minutes. `--work` keeps the built project, the
raw frames and the full facts.

Run it with `MESH_GL_SMOKE=1`, and with `PYTHONPATH` set to the checkout when an editable install points elsewhere. It
uses hidden windows only, plays no sound (master volume 0), and sends no OS input.

The gpu-lane test runs the same scenario without capturing frames, and writes nothing into the repository.

## Machine

These files were generated at commit `4e21efe7` (the branch's code; the evidence is committed on top).

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4070/PCIe/SSE2 |
| OS | Windows 11 |
| Python | 3.13.3 |
| Build and run | 133 s |
