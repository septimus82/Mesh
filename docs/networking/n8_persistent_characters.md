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

## N8C: storage

`mesh_net/characters.py`, one SQLite file per server (schema version 1, `PRAGMA application_id` "MSH1"):

| Table | Holds | Constraints |
|---|---|---|
| `meta` | `schema_version` | |
| `characters` | id, name, key hash, created, `completed` | id 32 chars; name 1-24, unique without case; hash 32 bytes; integers typed |
| `inventory` | (character, item) -> quantity | quantity 1-999; deleted with the character |
| `unlocks` | (character, key) -> granted | one row per key |
| `claims` | (character, run, claim) | primary key: a claim is granted once; earlier runs' rows are deleted at start |

- **Every write is one transaction** (`BEGIN IMMEDIATE ... COMMIT`; rollback on any error). A claim inserts its claim row
  and updates the inventory together; a completion inserts its row, counts it and grants the unlock together.
- **Crash safety:** WAL journal, `synchronous=FULL`. A transaction killed before `COMMIT` is rolled back when the file
  next opens; one killed after it is complete. Tested by killing a real process at both points.
- **One server per store:** `locking_mode=EXCLUSIVE`; the lock is taken by the start-up write and held until close,
  so a second server (or a stale one) is refused ("in use by another server").
- **Refused, never repaired:** a missing file (unless `new-store`), an existing file for `new-store`, a non-database,
  a damaged file (`PRAGMA quick_check`), a foreign SQLite file, a newer schema, a read-only file. The file is left
  byte for byte as it was.
- **Bounds:** 1000 characters per store, 16 distinct items per character, 999 of one item (and the item's own
  `max_stack`), 8 items per claim.
- **Migrations:** the schema version is checked at open; a store with another version is refused, never upgraded
  implicitly. A future version adds a migration step that runs only on request and only after a backup.
- **Backup and restore:** `python -m mesh_net.characters backup STORE COPY` (SQLite's online backup, consistent while
  the server runs) writes a new file and never replaces one. To restore, stop the server and copy the backup into
  place (remove the old file's `-wal`/`-shm` siblings with it). WAL needs a local filesystem, not a network share.
- **Where it lives:** wherever the server's owner points `--store`. Nothing is written to a game's folder or
  saves; tests use temporary folders only.

## N8D: inventory rules

- Item definitions are the project's `assets/data/items.json`, read by `engine.inventory.ItemDatabase` (the format
  every Mesh game uses). A world refuses to start if an enemy can drop an item the database does not define.
- **Loot is personal.** When an enemy dies, each character in that room instance at that moment gets its own roll of
  the enemy's `DropTable` (N6's `roll_drops`). "Take" beside the enemy (interaction reach) claims it. The claim and
  the inventory change are one transaction, granted once per claim; until it commits, the drop stays claimable.
- A drop that does not fit (stack limit, 16 slots) is refused with `inventory_full` and stays claimable. A failed
  write is `storage_failed`: nothing granted, nothing spent. A drop's `gold` is not kept (no currency in N8).
- Clients never name items or quantities: they send "take"; the server decides what that is.
- A world without a store keeps N7's room-local loot (first to take it holds it).

## N8E: progression

- Rules live beside the world (`mesh_net/expedition/progression.json`, version 1): `{key: {label, room, defeat}}`.
  Each key is checked at load: well formed, its room an expedition room of this world, its enemy one of that room's.
- When that enemy dies, every character in that instance earns the unlock (once: `unlocks` has one row per key) and
  one completion (`completed`, counted once per instance). Nobody else does. There is no request a client can send
  to unlock anything; the store refuses keys outside the rules.
- A completion the store failed to write is retried each tick (up to 64 waiting) and reported as `storage_failed`.

## What persists and what resets

| Persists (the store) | Resets with the server (memory) |
|---|---|
| characters, names, access-key hashes | rooms, enemies, levers, gates, drops on the ground |
| inventories | loot entitlements not yet claimed |
| unlocks, completions | parties, invitations, positions, resume credentials |
| claims of the current run (pruned at the next start) | room instances (expeditions start anew) |

## Threat model (local prototype)

Loopback only, as N4-N7. The access key proves ownership; the character id and name never do. Keys are random
(256 bits), stored only as SHA-256, compared in constant time, never logged or printed (the admin command writes
them to a new file only, mode 0600 where the OS supports it). Not addressed: anything that can read the player's
key file or the server's process can act as that character; no transport encryption (loopback); no account
recovery. These are deliberate limits of a local prototype, not of the store.
