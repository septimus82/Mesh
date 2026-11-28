# M3-5/M3-6: two clients in one HD-2D room (evidence)

Plan: `docs/plans/hd2d_online_investigation.md` §6, M3 items 5–6 (and the client guard in §3.3).

## Where the pictures come from

The pictures come from the **evidence script** (`tooling/m3_two_client_evidence.py`), not from the CI test. The script
plays the same scenario that `tests/test_mesh_net_hd2d_gpu.py` asserts, with the same code: the runner's `run`, with
frame capture turned on. The gpu-lane test runs that scenario without capturing frames and writes nothing into the
repository.

That run uses one real authority (`mesh_net.server.WorldServer`) and two real hidden client windows
(`tooling/net_world_probe.py`), each its own process with its own copy of the project. Every window fact is read from
that window's own objects. The pictures are those windows' framebuffers, read back; they are not OS screenshots.

The script keeps a run's pictures only if the acceptance tests' own assertions all hold on that run's facts.
[run.json](run.json) lists the nine checks that passed. [facts.json](facts.json) holds everything the run recorded:
server positions, window facts, camera states, refusal texts, the transfer history, each walk's legs, and `foreign_keys`.

**`foreign_keys` was 0 in both windows.** It counts key events a window received that the probe never sent; the probe
stops such events (see "Probe settings" below).

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

- **Windows never activate.** Every process with a window installs `tooling.hidden_windows.no_activate`: both probes,
  and the script itself for its hidden Studio window. A read-only foreground monitor ran for the whole session (this
  run and the gpu-lane test run). It saw no test or probe window take the foreground, become active or take focus.
- **The controls hint is off.** Net clients never call `PlayerHUD.update` (the HUD isn't ticked in their loop), so a
  toast never expires. The room's 4 s controls hint would stay over the middle of every picture for good. The probe
  turns that hint off for project runs. Making net clients tick the HUD is a product follow-up.
- **Only the probe's own keys reach the client.** The probe marks the keys it sends, and stops and counts any other key
  event.

## The pictures

Each picture shows window A on the left and window B on the right, at 640 x 360. A peer's avatar is drawn tinted. Where
a picture can't show the claim, the caption says so and points at the facts.

| Picture | What it shows | Backed by |
|---|---|---|
| [01_start](01_start.png) | The start, both on the ground. B has taken one step aside so the two avatars don't overlap at the spawn: A at (512, 144) px, B at (557, 144). | `test_each_player_climbs_onto_the_deck_and_back_down` |
| [02_a_on_deck](02_a_on_deck.png) | A has climbed the west stairs onto the deck: 2 m, `bridge_6m/col_deck`. A's window follows A up there. B's window follows B on the ground, and A is out of B's view. | `test_each_player_climbs_onto_the_deck_and_back_down`: the server, A's window and B's window all hold A at 64 px on the deck. |
| [02_b_on_deck](02_b_on_deck.png) | A is back down, by the cottage; B is on the deck. | the same test, for B |
| [03_a_over_b_under](03_a_over_b_under.png) | A on the deck at (527, 654) px. B is beneath it on the ground at (534.5, 654), between the guard and the bandit. B has just walked under A, from south of the deck to north of it (y 504 → 744), and back. | `test_one_stands_on_the_deck_while_the_other_passes_beneath`, `test_each_camera_follows_its_own_character` |
| [seq_b_passes_beneath_a.gif](seq_b_passes_beneath_a.gif) | B walking under A, one frame per 20 px B walks (both windows, half size). | `test_one_stands_on_the_deck_while_the_other_passes_beneath`: 70 server samples. A never moved; B stayed on `ground`, within 16 px of A's x. |
| [04_a_struck_from_deck](04_a_struck_from_deck.png) | Just after A struck, from the deck at (497, 654) px, at the bandit beneath. The bandit is the figure under the deck, right of the guard; it stands. B waits south of the deck, in front of nobody. A faced the bandit with its hitbox on it in plan, so only the floors could refuse the strike. The server ran the swing (its cooldown started), and the bandit's HP stayed 1 (`c.a_planar_hit`, `c.a_swung`, `c.after_a_attack`). | `test_no_attack_through_the_deck` |
| [05_a_reached_for_loot](05_a_reached_for_loot.png) | B came up to the bandit and felled it (it is gone). The loot, a small gold circle, lies beside B's head in both windows. A, on the deck 50.3 px from the loot, asked to take it (its window sent `take`), and the loot stays (`c.after_a_take`). | `test_no_attack_through_the_deck`, `test_no_looting_through_the_deck` |
| [06_b_took_loot](06_b_took_loot.png) | B stepped to 33.5 px from the loot (the run's `LOOT_Y` step, well inside the 72 px reach) and took it: the circle is gone. Both windows' snapshots record B holding it (`c.loot_seen`). | `test_no_looting_through_the_deck` |
| [07_a_over_door](07_a_over_door.png) | A walked west across the door's area on the deck. **The door is an invisible Passage, so it isn't drawn**; it lies under the deck at (15, 20.5) m. The run recorded A's level at every moment its picture was on the area: always 64 px on `bridge_6m/col_deck` (`door.a_contact_levels`). There was no transfer in the server or A's window. A's walk is released late on a slow runner, so A may end past the deck's west end on the plateau, also 2 m up; here it stopped on the deck at x 459.5. | `test_no_door_through_the_deck` |
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

In this run, window A drew B's feet at row 139 (expected 139.6; the deck's row there is 90.0). B's window drew A's feet at
row 98 (expected 97.9; the ground's row is 151.6).

## Regenerate

```
py -3.13 tooling/m3_two_client_evidence.py docs/reviews/m3_two_client [--work DIR]
```

This builds the room in a hidden Studio window, adds the bandit and the door, plays the run with frame capture, checks
it with the acceptance tests' assertions, and writes these files. It takes about 2.5 minutes. `--work` keeps the built
project, the raw frames and the full facts.

Run it with `MESH_GL_SMOKE=1`, and with `PYTHONPATH` set to the checkout when an editable install points elsewhere. It
uses hidden, never-activating windows only, plays no sound (master volume 0), and sends no OS input.

## Machine

These files were generated at commit `ac51eef5`.

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4070/PCIe/SSE2 |
| OS | Windows 11 |
| Python | 3.13.3 |
| Build and run | 140 s |
