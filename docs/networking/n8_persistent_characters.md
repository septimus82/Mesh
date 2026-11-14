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
  a damaged file (`PRAGMA quick_check`), a foreign SQLite file, a newer schema, a read-only file. Its content is not
  changed. (Opening it runs SQLite's own crash recovery: a `-wal` journal a crashed server left behind is folded into
  the file, keeping every committed change; tested.)
- **Bounds:** 1000 characters per store, 16 distinct items per character, 999 of one item (and the item's own
  `max_stack`), 8 items per claim, 64 unlock rules. A world refuses at load a drop a character could never hold (a
  quantity above 999) and an enemy id too long for a claim key.
- **After a failed rollback** the store refuses every later write (`StoreError`, "restart the server") rather than
  guess at its connection's state; the journal rolls the transaction back on the next open.
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
- A completion the store fails to write is owed, never dropped: it is written to a journal beside the store before
  the player is told, and recorded when the store works again or by the next server (N8J).

## N8J: completions a failing store owes (#496)

The defect: a completion the store failed to write lived only in the server's memory (a retry queue of 64). A
server stopped or killed while the store was still failing lost it; the player had earned an unlock that was never
recorded. Reproduced with a real server process (`n8_owed_evidence/repro_before_fix.json`): unlock earned, the
completion's transaction fails, the process is killed, a new server opens the same store: no unlock, `completed` 0.

What happens now (`mesh_net/owed.py`, `Progress` in `mesh_net/persistence.py`):

- **Owed, and written down first.** A completion the store does not take is *owed*. Before the player is told
  anything it is appended to a journal beside the store, `<store>.owed`, and `fsync`ed. One write covers every
  character of the event.
- **The player is told what is true.** `unlock_owed`: earned, not yet recorded, kept. Never `unlocked` until the
  store has committed it. If the journal fails too: `unlock_not_kept` (held only in this server's memory), and the
  server's log names it at ERROR.
- **Recorded when the store works again,** oldest first, at most 8 a tick (each is a commit), with one journal write
  a tick to settle them. While the store still fails there is one attempt a tick, not one per owed completion.
- **Recorded by the next server.** A server reads the journal before it listens and records what it holds
  (`Mesh owed completions: N recorded from earlier runs, M still owed`). A server stopped or killed with completions
  owed loses none that reached the journal.
- **Counted once, however often it is tried.** A journal record names the character, the run that earned it, the
  completion and the unlock: the store's own key for "counted once". Replay uses the earning run, and
  `begin_run(keep=)` keeps that run's claims until its records are settled (every start used to delete all earlier
  claims, which would have let a replay count twice). So a crash during recovery, a repeated restart, or a commit
  that happened although the server was told it failed all end with the completion counted exactly once. A
  completion earned again later, in another run, is a different key and counts as its own.
- **No new expedition while anything is owed** (`storage_unavailable` at the door). Expeditions under way go on:
  their rooms exist, so a party can still move between them and walk out. What they earn is owed too. That bounds
  what can be owed (rooms that exist × their rules × who is there), so nothing is ever dropped for lack of room: the
  64-entry limit is gone.
- **Space kept in advance.** The journal is made 64 KiB of zeros when a server first opens the store, and records
  overwrite that space. A full disk, the likeliest reason for the store to fail, does not stop the journal on a file
  system that writes in place. It is started over (a fresh file, moved into place) whenever nothing is owed.
- **Never repaired, never ignored.** A journal record that does not check out (checksum, fields, a settlement of
  nothing, data after the end) refuses the store: the server does not start, says which byte, and changes nothing.
  The one thing tolerated is a last record cut short by a crash while it was being written: that write never
  completed, nobody was told it had, and it is cleared.
- **A completion the store refuses for its own reason** (the rules no longer define the unlock, the character is
  gone) stays in the journal, is named in the log at each start and by the owed command, and blocks nothing.

For the server's owner:

    python -m mesh_net.characters owed STORE     # what is still owed (reads the journal; the store is not opened)

- Keep `<store>.owed` with the store: back them up and restore them together.
- If the server says the store's storage is failing: free space or fix the disk; the server records what is owed by
  itself. Restarting is safe at any point and loses nothing that is in the journal.
- If the server refuses a damaged journal: nothing was changed. Keep the file. To start without it (giving up the
  completions it holds, which the owed command cannot list either) move it aside by hand; nothing does that for you.

Guarantees and their tests (`tests/test_mesh_net_owed.py`; real processes are `tests/net_owed_server.py`):

| Case | What happens | Test |
|---|---|---|
| The store fails before the commit | owed, in the journal, `unlock_owed`; recorded when the store works | in process |
| A commit happened but was reported failed | owed; the store answers "already counted"; counted once | in process and killed process |
| Server killed with completions owed | the next server records each once | killed process (two characters) |
| Server killed while recording them | the next one finishes; each counted once | killed process |
| Server killed just after the journal write | recorded by the next server | killed process |
| Server killed before the journal write | nothing was durable and nobody was told; files sound | killed process |
| Several owed; several characters, one event | all kept in one write, all recorded | in process and killed process |
| The same completion delivered again | refused by the store as a duplicate | in process |
| Restart, and restart again | nothing changes; the earlier run's claims are forgotten once settled | in process and killed process |
| More owed than the old queue held (402) | all kept; recorded 8 a tick | in process |
| The journal fails too | `unlock_not_kept`, log at ERROR, no new expedition; kept as soon as the journal works | in process and killed process |
| The journal is damaged | the server does not start; journal and store unchanged | in process and the shipped server |
| The store works again | recorded, `unlocked`, expeditions open | in process |

Removing each protection makes these tests fail: 20 of 20 (`n8_owed_evidence/mutations.json`); with the journal
write alone removed, 6 of the 7 killed-process tests fail (`protection_off_crash_tests.txt`).

Cost on the 20 Hz tick (50 ms), Windows, Python 3.13, NVMe (`n8_owed_evidence/measure_*.json`):

| | Before | Now |
|---|---|---|
| Tick, 8 characters in the hub, nothing owed | 1.15 ms median, 1.37 p95 | 1.15 ms median, 1.36 p95 (no added work: one check) |
| Tick with 4 completions owed, store failing | 0.29 ms (4 failed attempts) | 0.14 ms (1 attempt) |
| The tick in which 4 completions become owed | no disk work | +5.0 ms median, 6.5 max: one journal write and `fsync` |
| A tick recording 8 owed completions | 4.1 ms for 4, all at once however many | 9.7 ms median, 13.1 max (8 commits, one journal write) |
| Server start (store + world) | 174 ms | 179 ms; 391 ms the first time (384 before), which makes the journal |

The journal write is on the tick thread on purpose, like commits: the completion must be durable before the frame
that tells the player goes out. It happens only in a tick where the store has just failed.

### Journal writes: short writes and failed appends (review of #510)

Found in independent review of #510: `_put` wrote with one raw `write` and did not look at its result. A raw write
may take fewer bytes than it is given, or none, without raising. The journal then counted an incomplete record as
written: the player was told `unlock_owed`, and a restart discarded the record as one cut short. Reproduced with a
scripted file, no disk filled (`n8_owed_evidence/short_write_before_fix.json`): in five of five short-write cases
the old code returned as if written, advanced its position by the full length, and a new server read the journal
without the record. And an append that failed left its bytes behind: after a flush failure, a shorter record written
at the same place left a line that does not check out, a journal the next server refuses.

Now:

- **A write is done when every byte is written and flushed.** `_put` reads each write's count and goes on from
  where it stopped. A write that takes nothing, or answers anything but a count of what it was given, is a failure:
  at most one write per byte, never a spin. `fsync` runs once, after the last byte. Only then does the record count
  and only then is the player told `unlock_owed`.
- **A failed append is finished before anything else is written.** Nothing of it counts and the journal remembers
  what it was writing. At the next write it reads what is on disk after the last counted record. That can only be
  the first part of those bytes followed by zeros: it writes the rest, flushes, and then the whole append counts.
  A write whose flush failed is not taken for unwritten and not written twice. Going on from a prefix keeps the file
  readable at every step (complete records, then at most one cut short), whenever the server is killed.
- **Nothing durable is touched.** Finishing only ever writes after the last counted record. Nothing is zeroed,
  rewritten or replaced while anything is owed.
- **Content that is not the server's own** after the last counted record is not built on, skipped or erased: the
  journal takes no more writes, completions are held in memory (`unlock_not_kept`), no new expedition starts, and
  the log says to stop the server and look at the file.
- **Nothing stale is left.** If the store recorded a completion while its journal write was unfinished, the record
  is settled as soon as the journal takes writes again; a restart that finds it first is refused by the store as a
  duplicate. Either way it counts once.
- **A record cut short, found at start,** is cleared last byte first, one byte a write, so that clearing can itself
  stop anywhere and leave a readable journal. An unfinished end longer than any record is damage, not a leftover.

| Case | What happens | Test (`tests/test_mesh_net_owed_writes.py`) |
|---|---|---|
| A write takes fewer bytes (once, several times, 7 at a time) | finished; one flush after the last byte; then counted | scripted file |
| A write takes nothing, or a negative count | fails at once; nothing counted or flushed | scripted file |
| Short write, then an error | fails; nothing counted; the durable entry untouched | scripted file |
| Short write in a batch of completions | finished; every record whole | scripted file |
| Failed batch, then a shorter record at the same place | the batch is finished first; the journal is sound | scripted file |
| Whole write, flush fails | not counted; flushed and counted at the next write; not written twice | scripted file |
| The same entries tried again | each written once | scripted file |
| Settlement fails part way | finished at the next write; nothing owed is lost | scripted file |
| The disk keeps failing | no further writes; nothing counted; then recovers | scripted file |
| Foreign content after the last record | refused; file left exactly as found | scripted file |
| Player notice | `unlock_owed` only after the last byte and the flush | world in process |
| A write that never completes | `unlock_not_kept`; a restart finds nothing kept: the two agree | world in process, restart |
| Failed then retried batch, two characters | both kept; a restart records each exactly once | world in process, restart |
| Store records before the journal works again | nothing stale; a restart replays nothing | world in process, restart |
| Journal works again much later | holds only what is still owed; each completion counts once | world in process, restart |
| Server killed in the middle of an append | the whole record counts once, the cut one is cleared | real killed process |
| Clearing a cut record is itself interrupted | readable at every point | scripted file |

Removing these protections fails the tests: 11 of 12 mutations, the twelfth being equivalent to another
(`n8_owed_evidence/mutations_writes.json`). The reviewed write path put back fails 18 tests, among them
`test_short_writes_are_finished_before_the_record_counts`; finishing a failed append switched off fails 7, among
them `test_a_whole_write_whose_flush_failed_is_not_taken_for_unwritten` with a journal a new server refuses.

Cost: the same single write and single flush as before when the write is taken whole (the usual case): 5.0 ms
median for four completions, as before (5.1). Finishing a failed append is one read of the journal's end and one
write, in the next tick that writes to the journal. The figures in the table above are from the corrected code.

## What persists and what resets

| Persists (the store) | Resets with the server (memory) |
|---|---|
| characters, names, access-key hashes | rooms, enemies, levers, gates, drops on the ground |
| inventories | loot entitlements not yet claimed |
| unlocks, completions | parties, invitations, positions, resume credentials |
| completions a failing store owes (`<store>.owed`) | room instances (expeditions start anew) |
| claims of the current run, and of an earlier run still owed something (otherwise pruned at the next start) | |

## Threat model (local prototype)

Loopback only, as N4-N7. The access key proves ownership; the character id and name never do. Keys are random
(256 bits), stored only as SHA-256, compared in constant time, never logged or printed (the admin command writes
them to a new file only, mode 0600 where the OS supports it). Not addressed: anything that can read the player's
key file or the server's process can act as that character; no transport encryption (loopback); no account
recovery. These are deliberate limits of a local prototype, not of the store.

## Known limits

- Items cannot be removed (no use, drop or trade in N8): a full stack or slot list stays full.
- With the store and its journal both failing, an owed completion exists only in the server's memory. The player is
  told `unlock_not_kept`, the log names it, no new expedition starts, and it is kept as soon as either takes a
  write; a server stopped or killed before that loses it. No storage took a write: this is said, never silent.
- A server killed in the tick an enemy dies, before the journal write, loses that completion, as a kill between the
  death and the store's commit always could: nothing durable existed yet and nobody had been told.
- The journal relies on `fsync` being honoured by the disk, and its space kept in advance helps only where files are
  overwritten in place (not on a copy-on-write file system). Power loss itself is not tested, only killed processes.
- An owed completion is a notice, not a line on the character sheet (the sheet shows what the store holds).
- A completion the store refuses for its own reason stays in the journal for good; while it is there the journal is
  not started over, so later records are appended after it (two short lines for each completion owed and settled).
- `backup` copies the store, not its journal: copy `<store>.owed` with it.
- A journal found to hold, after its last counted record, content the server did not write takes no more writes
  until the server is restarted (completions earned meanwhile are held in memory and said to be).
- Loot not yet taken is still kept in memory only (unchanged).
- A server pointed at a copy of a store could grant drops of its own run again: the store is the authority, and
  copies are the owner's business (backups are for restoring, not for running side by side).
- Only characters online in the instance when an enemy dies share its loot and unlocks (a retained, disconnected
  party member does not).
- After a server restart a window must join afresh (N): its old resume credential belonged to the old process.
- The `fault` hook in `CharacterStore` exists for fault-injection tests; nothing sets it in normal runs.
