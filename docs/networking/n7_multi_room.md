# N7: multiple rooms, transitions and parties

N7 extends the optional `mesh_net` experiment so two players can meet in a shared hub, form a party, travel through
two Studio-authored expedition rooms with shared combat and interactions, return, and reconnect. It builds on N6
(`docs/networking/n6_scene_integration.md`, merged as `5a9d8f6`). It is a foundation, not an MMO: one process,
loopback only, no persistence.

## N7A: architecture decision

### What N6 gives us

- `mesh_net.scene_room.SceneRoom` is a self-contained, graphics-free authority for one Studio scene: `join`,
  `leave`, `input`, `step`, `snapshot`, with deterministic stepping and no global state. Its entity ids (`eid`) are
  room-local counters. Its identity hashes the resolved scene and its collision geometry.
- `mesh_net.server.Server` hosts one such room: one asyncio clock at 20 Hz, one snapshot broadcast to every
  connection, resume tokens retained 30 s.
- `mesh_net.scene_client.SceneArena` loads the room through `GameWindow.load_scene`, strips every behaviour except
  `Animator` (and the local avatar's `CameraFollow`) and places what each snapshot says.

### Existing single-player transitions (what an authored door means)

Studio's "door to a new room" (`engine.project_ops.link_rooms`) writes, in each room, an entity with
`SceneTransition {target_scene: <world key>, spawn_id: "from_<this key>", trigger_on_touch}` and an arrival
marker (`tag: "spawn_point"`, `spawn_id`). The world file (`packs/core_regions/worlds/main.json`) maps keys to
scene paths and carries a `tags` list per room. In single-player, walking into the door's area
(`SceneTransition.update`: the player picture's bounds against `area_width` x `area_height` round the door) loads
the target scene and puts the player on the marker (`engine.scene_runtime.spawn.find_spawn_marker`).

N7 reads exactly these definitions. It adds nothing to the scene, world or save formats.

### Options compared

| | A. Many rooms in one server process | B. One room per process + coordinator |
|---|---|---|
| Transfer | Move a player record between two in-memory rooms inside one tick: atomic, nothing in between to lose | A hand-off protocol between processes: prepare, commit, acknowledge, with partial failure on either side |
| Trust | One authority; clients never name a destination | The coordinator must authenticate processes and players across them |
| Failure modes | Destination preparation fails -> put the player back (same tick) | Destination process down, slow or restarted mid-transfer; tokens across processes |
| Determinism and tests | One clock steps every room in a fixed order; tests drive it tick by tick | Multi-process timing in every transfer test |
| Cost | One Python process. N6 measured ~0.25 ms per player-tick | One process per room plus coordinator |
| Scale ceiling | One CPU core | Many cores/machines (not needed now) |

**Decision: A.** It is the simplest design that can be tested deterministically, and every N7 requirement
(isolation, transfers, parties, reconnect) is a property of in-memory ownership rather than of networking. B's
only advantage is scale beyond one process, which is explicitly out of scope; A does not preclude it later (a
room instance is already a self-contained object a future process could host).

### Authority boundaries

| State | Owner | Clients may |
|---|---|---|
| Player identity (`pid`), resume token | World | present the token once to resume |
| Party membership, leader, invitations | World | ask (create, invite, accept, decline, leave); every request is checked against server state |
| Which room instance a player is in, their room-local `eid` | World | nothing; the server tells them (`enter`) |
| Movement, interactions, combat, loot within a room | That room's `SceneRoom` (N6 rules) | send input frames for their own `eid` in their current room |
| Transitions | World, from the authored door the player's avatar walked into | nothing: a client cannot name a destination or an instance |
| Instance creation and destruction | World | nothing |

### Design

- **Room definitions.** At start the world loads every room in the world file once (an N6 `SceneRoom` each, with all
  N6 refusals), plus its doors and arrival markers. Every door must lead to a room in the world and to an arrival
  marker that exists there, and must be a walk-in door with an authored area (`passage` / `map_art` style):
  a picture door's area is Arcade's hit box, which the server cannot compute without Arcade (the same reason N6
  refuses picture hit boxes). Unsupported doors are refused at load.
- **Room kinds** come from the world file's existing `tags`: a room tagged `expedition` is instanced per party;
  every other room has one shared instance for the server's lifetime.
- **Instances.** An instance is a fresh copy of the validated room (no file reads at transfer time), with its own
  id (`<key>:<n>`, a counter never reused), its own tick, its own `eid` counter and its own enemies, levers, drops
  and loot. Entity ids are room-scoped: the same number in two rooms names two different players, so every
  message about a room carries the room id.
- **Transfers.** After each room steps, the world checks each player against that room's doors. A door fires when
  the avatar's picture bounds overlap its area and did not on the previous tick (edge-triggered, so an arrival spot
  inside a door's area never ping-pongs). The transfer then runs inside the same tick:
  1. resolve the destination: the door's target key, and the instance the player may use (shared room, or their
     party's instance of an expedition room; no party, no expedition);
  2. prepare the destination (find or create the instance; bounded);
  3. remove the player from the source room (its inputs are no longer applied there);
  4. join the destination at the arrival marker, getting a new room-local `eid`;
  5. queue `enter` (destination id, key, `eid`, full snapshot) for that player.

  If the destination is full or cannot be prepared (instance limit, preparation error), nothing has changed and the
  player stays where they were with a notice. If joining fails after leaving (never observed; guarded), the player is
  put back where they stood and any half-made avatar is removed. Each outcome is a named `TransferResult`. Server-side there is no in-between state anyone can observe.
- **Client order independence.** Input frames carry the room id; a frame for any room but the player's current one
  is dropped (it was in flight during a transfer). `room_state` frames carry the room id; the client applies only
  frames for the room its last `enter` named, with strictly increasing ticks within it.
- **Parties.** Server-side records keyed by `pid`, never by `eid`. Create; the leader invites an online player who
  is not in a party; the invitee accepts or declines; anyone leaves. A leader who disconnects passes leadership to
  the longest-standing online member. Bounded: 4 members, 4 pending invitations per player, invitations expire.
  Leaving a party while in its expedition sends you to the hub.
- **Reconnect.** A disconnected player keeps their party membership, room and position for 30 s (N5's retention).
  The room's instance is kept alive while a retained player belongs to it. Resuming puts them back; if that is no
  longer allowed (party gone, instance gone, room full), they arrive in the hub.
- **Cleanup.** A party's expedition (its instances of every expedition room) lasts while any member, online or
  retained, is in one of them, and ends in the tick the last one leaves (see "Expedition lifetime" below). The hub
  and other shared rooms are never destroyed.
- **Client.** A `GameWindow` client per player. On every `enter` it loads the destination through
  `GameWindow.load_scene` and builds the same presentation N6 does (the N6 client's scene part, extracted into a
  reusable `SceneView`).

### Limits (all checked)

8 connections and 16 characters (online + retained), as N5; 8 players per room, as N6; 8 room instances (hub
included); 4 players per party; 4 pending invitations per player, 60 s each; 8 frames per connection per tick;
one frame at most 8192 bytes, checked at load for each room's largest possible snapshot.

### Gate

None of this needs changes to `GameWindow`, `SceneController`, Mesh Studio, the single-player simulation or the
scene, world and save formats. The only change outside `mesh_net` is optional bookkeeping in N6's `SceneRoom`
(doors, arrival markers, drop tables kept for re-rolling), which N6's own hosting ignores. N7 proceeds.

## What was built

| Milestone | Where | What |
|---|---|---|
| N7B rooms | `mesh_net/world.py` (`World`, `room_defs`, `Instance`) | Every room of the world file validated once; shared instances, per-party expedition instances, ids never reused, room-scoped `eid`s, per-room snapshots, bounded counts, cleanup |
| N7C transitions | `World.step`, `World.transfer` | Walk-in doors (edge-triggered), destination resolution, preparation, leave/join in one tick, `TransferResult`, rollback, stale-input drop, a bounded event history (`World.history`) |
| N7D parties | `World.party`, `_leave_party`, `_fix_leader` | Create, invite, accept, decline, leave; leadership hand-over; expedition access only through party membership |
| N7E demonstration | `mesh_net/expedition/`, `tooling/make_expedition.py` | Adventurer's Hub, Ancient Ruins - Layer 1 (walls, lever and gate, bandit), Layer 2 (lever and gate, guardian), built with Studio's own operations |
| Server and client | `mesh_net/server.py` (`WorldServer`, `--expedition`), `mesh_net/world_client.py` | Frames moved by the server as the world decides; a GameWindow client that loads each room it enters |

N6's window client was split so a world client can reuse it: `mesh_net/scene_client.py` now has `SceneView` (one
room's presentation) and `SceneArena` (N6's single-room client, unchanged in behaviour, built on it).

### Expedition lifetime (changed during implementation)

The first version destroyed an expedition instance as soon as nobody was in it. That made going down to Layer 2
and back reset Layer 1. A party's expedition now lasts while any member (online or retained) is in any of the
party's instances, and ends in the tick the last one leaves. Each instance still has its own state.

## Protocol (version 1 framing, new frame types)

Client to server:

| Frame | Fields | Checked |
|---|---|---|
| `join` | `resume` | as N5 |
| `input` | `room`, `entity`, `seq`, `dx`, `dy`, optional `action` | `room` must be the player's current room (otherwise dropped: it was in flight during a transfer), then N6's `parse_input` |
| `party` | `op` (`create`, `invite` + `player`, `accept`/`decline` + `party`, `leave`) | exact fields, numbers only; refusals answer with a `notice` |

Server to client:

| Frame | Fields |
|---|---|
| `welcome` | `session`, `player` (stable id), `resume`, `world` (identity of every room) |
| `enter` | `room`, `key`, `entity`, `state` (full N6 `scene_state`) |
| `room_state` | `room`, `state` |
| `party` | `you`, `party`, `leader`, `members` `[pid, online, room key]`, `invites` `[party, inviter]`, `nearby` `[pid, eid]` (this room only) |
| `notice` | `code` (one of `mesh_net.world.NOTICES`) |

Clients validate every frame (`check_welcome`, `check_frame`, and N6's `check_state` against the room's identity).
The world refuses to start if any room's largest possible `enter` frame would exceed 8192 bytes.

## Try it

```
python -m mesh_net.server --expedition --port 46870
python -m mesh_net.world_client --port 46870   # in two terminals
```

In the hub: P creates a party, I invites the nearest player, Y/N accepts or declines. Walk right into the hub's door
together. In Layer 1, E at the lever opens the gate; the door down is beyond it. Space attacks, E takes loot. Walk
back through the doors to return. F2 disconnects, R resumes.

## Hosted failures fixed in N7.1

- **Leaving could hang the client (Windows gpu lane, Extended 42978577824).** F2 cancels the world client's session.
  On Python 3.11 (the CI version), `asyncio.wait_for` drops a cancellation that lands just as its inner result
  arrives (fixed in 3.12; local runs used 3.13). The session cancelled its send and receive loops and only then
  closed the connection, so a loop that missed its cancellation kept the session waiting on it forever. The hosted
  record showed exactly that: the server still had player B with its last input on the current tick, 15 s after
  F2. The session now closes the connection first, and the send loop stops once the connection is closing.
  `test_leaving_ends_the_session_even_if_a_cancellation_is_swallowed` reproduces 3.11's behaviour and fails without
  the fix. The window keeps a timestamped trace (`WorldArena.trace`) and the world a bounded history of connects,
  resumes, disconnects and transfers; the two-window test prints both if it fails.
- **CI policy checks.** The world tests built a `welcome` frame with a literal `"session"` key, which the scanner
  for editor session state rightly flags. The frame is now made by `mesh_net.world.welcome`, which the server uses
  too. Two client tests lacked a tier marker and are now `integration` (they use a project folder).

### N6's two-window test (inherited instability)

N6's two-window test fails when, after holding DOWN to y <= 262 below the gate gap, the avatar overshoots past
about 14 px: below y = 248 its feet catch the wall under the gap, and the next RIGHT is blocked (the failures seen
had it at y = 241). N7 does not change anything that test runs except moving N6's client code into `SceneView`
(same calls, same order). A measuring harness drove the same probe and server from each checkout, alternating,
four runs of ten releases each:

| Checkout | Overshoot per release (px), mean of runs | Largest | Probe round trip (median) |
|---|---|---|---|
| base `64dd1067` | 4.2, 3.5, 3.5, 5.8 | 13.5 | 0.2 ms |
| N7 | 3.5, 5.0, 5.0, 3.5 | 8.5 | 0.2 ms |

Overshoot comes in whole ticks (7.5 px) on both, and the base's own tail reaches 13.5 px, at the test's margin.
Alternating full runs of the test came out 8/8 on each. The evidence points to that test's thin margin, not to N7;
it cannot rule out a small difference. Making N6's test walk in short steps near the gap (as N7's test does) would
remove the margin problem; that change is outside N7.

## Single-player findings and limits

- **Room memory in a network client.** Single-player room memory records objects removed during play and leaves them
  out when the room loads again. The network client removes the scene's player definition (every avatar comes
  from the server), so a return visit, or a resume into the room on screen, loaded the room without it. The world
  client clears the room path and the memory before each load (`world_client.WorldArena.draw`); nothing in the
  engine changed.
- **Focus.** The client lets go of held keys when its window is deactivated (correct for a player switching
  windows). Hidden test windows are deactivated whenever another test window loads a room, so the test probe
  (`tooling/net_world_probe.py`) ignores deactivation. Whether a visible window loses focus on a room change was not
  checked by desktop automation (not authorised on the owner's machine).
- Picture doors, doors used with E, event or one-shot doors, HD-2D rooms and flag-gated objects are refused at load.
  A door's `spawn_id` must name an arrival marker in the destination (single-player falls back to the room's
  default position instead).
- Loot does not travel between rooms: there are no inventories (out of scope). A player who leaves a room leaves
  its loot held by nobody.
- Instances are a shared budget: 8 including the hub, and a one-person party gets its own expedition. A few solo
  players can therefore use every expedition slot (bounded, but first come, first served). A fairer split is a
  design decision for later.
- **Python 3.11 cancellation (remaining risk).** The leave fix closes the connection before waiting for the
  session's loops. A cancellation swallowed while a session is still connecting (opening the socket or reading the
  welcome) could still let that session continue as a new character for up to the server's 5 s read timeout
  (a loading client sends nothing). Not observed; bounded.
- **Leaving a party while away from the hub** assumes the hub can always take the player (online players never
  exceed one room's capacity); if that limit ever changed, `_leave_party` would need to handle a failed move.
- If the world itself raises while stepping, the server logs it, stops accepting and closes every connection
  rather than staying open but frozen.
- One process; loopback only; plaintext resume tokens (N4's trust limits). No persistence: a server restart starts
  every room anew. No matchmaking, guilds or friend lists.
