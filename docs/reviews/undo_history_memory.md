# Studio undo history: memory retention

Finding (Astra, 12 November): Studio's undo history keeps a full copy of every open room for every step, so the
memory it holds grows with the size of the project and not with the size of the edits.

The finding was reproduced and measured on `f1cacfe`, the history was changed so that steps share one private copy
of every room they did not change, and the result was measured again with the same workload. What the person gets
back from undo and redo is byte for byte what it was before the change.

Evidence: `undo_history_memory_evidence/` (`before_f1cacfe.json`, `after.json`, `comparison.txt`,
`tests_on_unchanged_engine.txt`, `protection_removal.json`). Tool: `tooling/undo_history_memory.py`.

## Reproduction

`py -3.13 tooling/undo_history_memory.py OUT [--entities 500] [--repeat 3] [--only SCENARIO,...]`

The tool builds a project (the starter project, a room `Small` with ten people, and large rooms of `--entities`
objects each written straight to their files), and runs each scenario in a process of its own on a copy of it. Every
edit moves one person in `Small`: a small edit, in a small room.

| Scenario | What the person does |
|---|---|
| `small_room_only` | 100 edits; undo all; redo all; undo half; one new edit (the redo steps go) |
| `after_one_large_room` | looks into one large room first, then the same |
| `after_three_large_rooms` | looks into three large rooms first, then the same |
| `past_the_limit` | looks into one large room, then 150 edits (the limit is 100 steps) |

Measured at 25, 50, 100 (and 150) steps, after undoing all, after redoing all, after the new edit, and after the
history is dropped:

* **history**: what Python allocated and still holds (tracemalloc) at that point, less the same once the history is
  dropped at the end. This is the number the history is judged by.
* **process**: the process's private bytes, as a second view only. No conclusion rests on it alone.
* **peak per step**: the peak of allocations during one edit, undo or redo above what was held before it.
* **wall time** per edit, undo and redo: from a second session without tracemalloc, which slows every allocation.
* a digest of every document at each point, to show both engines produce the same documents.

A session ends itself if its process passes 3 GB.

## Root cause

`Project._snapshot` (`engine/studio_project.py`) made a deep copy of every room that is open (`_copy(self.scenes)`),
and every edit, transaction, undo and redo takes a snapshot. A room is open from the moment it is first looked at
until the project is closed. So each of up to 100 undo steps held its own copy of every room ever looked at, and
`_restore` copied all of them back on every undo and redo.

On `f1cacfe`, 100 small edits after looking into one room of 500 objects (6 MB of documents) held 309 MB of history;
after three such rooms, 908 MB (process: 2.3 GB). An earlier, larger run (one room of 3,000 objects, 36 MB of
documents) held 1.8 GB at 100 steps. The history grows linearly with steps and with the size of everything open.

## Who owns what

| Object | Owner | May it be changed in place? |
|---|---|---|
| `Project.scenes[key]`, `world`, `player` | the project: the documents being edited | yes (operations return new documents; nothing forbids in-place changes, and the history does not rely on their absence) |
| `_State.scenes[key]` in `_undo` / `_redo` | the history. Created only by `_snapshot` (`save` makes states with other dirty flags by `dataclasses.replace`: same documents). Only read afterwards: `_record` (ids), `_maps`, `_release`, `_ready_maps`, the transaction's "did anything change" comparison, `_restore` | no, and nothing does |
| `_frozen[key]` (new) | the history: the newest copy it holds of each room, with that copy's pickle | no |
| `_as_read[key]` (#462 S2) | the project: each room as first read. Now the same object as the history's copy of the unchanged room | no, and nothing does (`_restore` and `_maps` read it) |
| `ids_seen`, `keys_seen` (#462 S1-ID) | the project: plain sets of strings, only added to; never part of a state | — |
| `_made`, `_saved_maps`, `kept_files` (#462 S4) | the project: paths and tokens, not documents; unchanged | — |
| `dirty`, `world_dirty`, `player_dirty` | copied into each state as immutable values, as before | — |
| A dry run's project (`clone`) | shares the read-only `_frozen` copies, has documents and a history of its own | — |
| AI proposal bases (`engine/studio_ai.py`, `engine/authoring.py`) | their own `copy.deepcopy(all_documents())`: not part of the undo history, unchanged | — |

The rule the change keeps: **a document being edited is never an object the history holds**, in either direction.
A step gets a copy (`_freeze`); a restored room is a copy of the step's (`_thaw`).

## Alternatives

| | Outcome |
|---|---|
| **A. Structural sharing** | **Chosen**, at room level, with the sharing decided by content rather than by tracking. `_State` keeps its shape, so everything that reads a state (`_record`, map ownership, save, the transaction comparison) is untouched. |
| B. Changed-document snapshots (a step records only the rooms it changed) | Same memory in the end, but a state would no longer be a whole project: every reader of `_State` and the #462 S2/S4 logic (rooms first read after earlier steps, map files of rooms that come and go) would have to reconstruct it. A wider change for no further gain. |
| C. Compact snapshots (keep each step as pickle bytes, perhaps compressed) | Smaller by a constant factor only: still one copy of everything open per step, and undo still rebuilds everything. Does not address the cause. |
| D. Retain | Not justified: hundreds of megabytes to gigabytes for a person who looks into a few large rooms and makes small edits. |

Sharing by content, not by tracking: `_freeze` pickles the room and compares the bytes with the pickle of the copy
the history already has. Equal bytes: the step holds that same copy. Otherwise a new copy is made from those bytes.
Nothing has to know which operation touched which room, so an in-place change, a failed batch or a code path added
later cannot make the history share something that differs. The comparison is exact where `==` is not: `1`, `1.0`
and `True`, or two keys that changed places, are different rooms (tests cover each). If two equal rooms should ever
pickle differently, the cost is a copy, never a wrong document. A room that will not pickle is deep-copied, as
before.

Undo and redo take a snapshot of the present first, as before. A room whose copy in that snapshot is the very object
in the state being restored is already what it is to become, and is left alone; every other room is replaced by a
copy of the state's.

World and player are still copied per step: together about 1.5 KB.

## Results

Windows 11, Python 3.13.3, 16 logical CPUs. 500 objects per large room. Medians (before: 2 sessions per scenario;
after: 3). The spread between sessions is under 0.1 MB for every history figure. Wall times are from untraced
sessions.

History held, MB:

| Scenario (documents) | steps | before | after |
|---|---|---|---|
| small room only (0.2 MB) | 25 / 50 / 100 | 2.4 / 5.0 / 10.2 | 1.9 / 4.0 / 8.1 |
| after one large room (6.2 MB) | 25 / 50 / 100 | 74.6 / 152.9 / 309.4 | 2.3 / 4.4 / 8.5 |
| after three large rooms (18.3 MB) | 25 / 50 / 100 | 219.3 / 448.9 / 908.1 | 3.0 / 5.1 / 9.3 |
| past the limit (6.2 MB) | 100 / 150 | 312.9 / 312.9 | 8.6 / 8.7 |

After the change the history costs 80 to 95 KB a step here (the edited small room, the world and the player),
whatever else is open. Before, each step also cost one copy of everything open.

| Scenario | process at 100 steps, MB | edit, ms (median; p95) | undo, ms (median; max) | redo, ms (median) | peak per edit; per undo, MB |
|---|---|---|---|---|---|
| small room only | 74 → 71 | 2.37; 2.76 → 2.30; 2.58 | 0.46; 0.80 → 0.29; 0.59 | 0.45 → 0.30 | 0.2 → 0.1; 0.2 → 0.1 |
| after one large room | 794 → 88 | 8.50; 14.29 → 4.91; 5.41 | 13.00; 175.5 → 2.68; 5.1 | 12.41 → 2.64 | 3.8 → 1.1; 7.0 → 1.1 |
| after three large rooms | 2280 → 131 | 23.20; 54.72 → 9.60; 10.21 | 44.48; 571.9 → 7.29; 10.9 | 43.58 → 7.27 | 11.3 → 1.1; 20.5 → 1.1 |
| past the limit (150 edits) | 804 → 95 | 8.92; 15.89 → 4.91; 5.44 | – | – | 3.8 → 1.1; – |

* Undoing all and redoing all leaves the history the size it was (one large room: 312.7 → 8.7 MB); a new edit after
  undoing half leaves half (159.6 → 4.6 MB); past the limit it stays level in both engines.
* After the history is dropped, both engines hold the documents only (history 0.0).
* The documents' digests at every point are identical on both engines and across all sessions.

## Tests

`tests/test_studio_undo_history_sharing.py` (16 tests, about 10 s, `integration`):

* steps hold one copy of a room they did not change, and it is the copy kept of the room as first read; a changed
  room gets a new copy and later steps share that one;
* the history after 40 small edits is not materially larger with a 1,500-object room open than without it (a ratio
  between two runs in the same process: no absolute threshold);
* the limit of 100 steps and the clearing of redo by a new edit let the copies go;
* a long seeded session (220 turns: moves, new objects, accepted and failed batches, a new room, room changes,
  saves, runs of undo and redo) against an independent record of every state: undo and redo give back exactly what
  was there, with dirty flags, across rooms and saves;
* a change that `==` cannot see (int to float, flag to number, key order) is a change;
* nothing done to the documents afterwards, in place, reaches a step already taken, or the copy of a room as first
  read;
* undo leaves the object of a room it does not change alone and replaces one it does;
* a failed batch puts everything back and the history goes on sharing; an accepted batch is one step;
* save, undo, save, redo, save, reopen with a large room open;
* a room that will not pickle; a dry run's copy of the project.

On the unchanged engine 7 of the 16 fail (`tests_on_unchanged_engine.txt`), the growth test with 48,572,765 bytes
against 1,399,605. The other 9 pass there: they state what undo already guaranteed, and must go on holding.

Protection removal (`protection_removal.json`): ten one-line changes to the new code, each run against these tests
and the existing `test_studio_room_undo_save.py` and `test_studio_project.py`. All ten are caught:

| Change | Failing tests |
|---|---|
| every step gets its own copy again (the old behaviour) | 7 |
| a step holds the room being edited itself, not a copy | 2 |
| unchanged is judged by `==`, not exactly | 3 |
| a room is taken for unchanged whenever the history has a copy of it | 22 |
| a restored room is the history's own copy, not a copy of it | 2 |
| undo keeps every room that is open as it is | 15 |
| undo keeps a room whenever its copy equals the one wanted (not: is the very one) | 3 |
| undo and redo copy every room back again (the old cost) | 1 |
| a room first read after a step comes back as the history's own copy | 1 |
| the room as first read is the room being edited itself | 3 |

## Compatibility

* No file format, public method or AI interface changes. `_State` has the same fields. `_restore` takes one more
  optional argument. The undo internals are used only inside `engine/studio_project.py`.
* Revisions, write-set checks, id-reuse protection and room/map file ownership (#462 S1–S4) read the same data as
  before.

## Limits

* An edit still pickles every open room once to compare it (about 2.5 ms per 6 MB room here, 1.1 MB transient): the
  time per edit still grows with what is open (2.3 ms with nothing else open, 4.9 ms with one large room, 9.6 ms
  with three; before: 8.5 and 23.2 ms). Removing that needs change tracking on every path that can alter a room,
  which is the dependence this design avoids.
* The history keeps, per room, one copy and its pickle beyond the steps themselves (for a room never changed, the
  copy is the one already kept of the room as first read).
* A step that changes a large room still holds a full copy of that room. Sharing below room level was not attempted.
* Rooms stay open until the project is closed, as before.
* AI proposal bases and dry runs copy all documents on their own (`studio_ai`, `authoring`): not part of this change.
* Measured on one Windows machine. The required tests assert a ratio, not megabytes or milliseconds.
