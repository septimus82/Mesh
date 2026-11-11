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

  If step 2 fails (instance limit, preparation error), nothing has changed and the player stays where they were
  with a notice. If step 4 fails (destination full), the player is put back in the source room. Each outcome is a
  named `TransferResult`. Server-side there is no in-between state anyone can observe.
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
- **Cleanup.** An expedition instance with no online players and no retained ones is destroyed in the tick it
  empties. The hub is never destroyed.
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
