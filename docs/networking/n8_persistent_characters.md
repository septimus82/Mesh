# N8: persistent multiplayer characters, inventory and progression

N8 adds durable, server-authoritative characters to N7's world (`docs/networking/n7_multi_room.md`, merged as
`f6bd91d6`): a character keeps its identity, items and unlocks across disconnects and full server restarts. It is
optional (a world started without a store behaves exactly as N7) and local: loopback only, no accounts.

## N8A: investigation and decision

### What N7 has

| Identity | Lifetime | Durable? |
|---|---|---|
| Room entity id (`eid`) | one room instance | no: a new one on every room entry |
| Room instance id (`key:n`) | one server run | no: the counter restarts with the process |
| Player id (`pid`) | one server run (`World.members`) | no |
| Party id | one server run | no |
| Resume token (N5) | one disconnect, 30 s, single use | no: in memory |

After a disconnect N7 keeps the player's in-memory avatar and party for 30 s, then forgets them. Nothing survives a
restart, and nothing in N7 is a character.

### What single-player has

- `engine.save_manager.SaveManager` is bound to one `GameWindow` and writes that window's game state (flags,
  counters, `values["inventory"]`, room memory) as JSON save slots through the F3 save service (atomic replace,
  rollback, ownership by exclusive create). It is one player's whole game, chosen by a person in a menu.
- `engine.inventory`: `ItemDatabase` reads `assets/data/items.json` (id, name, stackable, max stack); `Inventory`
  stores `{item_id: count}` inside a game state and silently caps at the stack limit. `DropTable` rolls drops and
  adds them to the window's inventory (and gold to a counter).

Neither is a multi-owner store with ownership checks, and changing SaveManager is a stopping condition. N8 reuses
the **item definitions** (`ItemDatabase`, the same `items.json` format) and N6's **drop rolls** (`roll_drops`,
DropTable's own algorithm), and keeps its own server-side store. No single-player file, class or behaviour changes.

### Options

| | A. SQLite (`sqlite3`, standard library) | B. Versioned JSON files via Mesh's atomic writers |
|---|---|---|
| Atomic multi-row update (claim + inventory) | one transaction | one file per character, rewritten whole; a claim spanning records needs a custom journal |
| Crash safety | WAL + `synchronous=FULL`: committed means on disk; an interrupted transaction rolls back on open | atomic replace per file; directory fsync and multi-file consistency are ours to get right |
| Constraints (unique names, quantity bounds, one claim) | declared in the schema, enforced by the engine | hand-written checks |
| Corruption detection | `PRAGMA quick_check`, page checksums of the format | JSON parse only |
| Dependencies | none (standard library) | none |
| Measured commit (this machine, claim + inventory) | WAL: 0.42 ms median, 0.64 ms p95 (rollback journal: 2.2 / 3.1 ms) | similar or slower (write + fsync + rename per file) |

**Decision: A.** SQLite gives the transactional and constraint guarantees N8 needs without new dependencies, and
its commit cost is small enough to stay on the simulation thread (no asynchronous writer needed). B would
re-implement a transaction log by hand. WAL needs a local filesystem (not a network share); documented.

### Architecture gate

No change to `GameWindow`, `SceneController`, Studio, `SaveManager` or any scene/save format. The only engine code
reused is read-only (`ItemDatabase.load`, N6's `roll_drops`). N8 proceeds.

### Data ownership

| State | Owner | Persists? |
|---|---|---|
| Character id, name, access-key hash, progression (`expeditions_completed`), inventory, unlocks | `CharacterStore` (SQLite) | yes |
| Loot claims of the current run | `CharacterStore` (`claims`, pruned at the next start) | until the next start |
| Which character a connection controls, its room, position, party | `World` (memory) | no (30 s retention, as N7) |
| Rooms, enemies, levers, drops on the ground, per-character loot entitlements | `World` instances (memory) | no: a restart starts every room anew |

### Identity and access

- **Character id:** 32 random hex characters, assigned once, never reused. Public: it identifies, it does not
  authorise.
- **Display name:** 1-24 letters, digits, spaces, `_` or `-`; unique regardless of case.
- **Access key:** 32 random bytes (64 hex), shown once when the character is created, stored only as its SHA-256.
  A connection controls a character only by presenting its id and key; comparison is constant-time. Never logged.
- **Creation** is a local server-side command (`python -m mesh_net.characters create`), which writes the key to a
  file the player's client reads. No registration over the network, no passwords, no email.
- **One session per character:** a second connection presenting a character that is online is refused
  (`character_in_use`); the first keeps control. A character that is disconnected but still retained (30 s) is
  resumed where it was; after that it starts in the hub.

## N8C-E: storage, inventory, progression (rules)

See the sections below (filled in with the implementation).
