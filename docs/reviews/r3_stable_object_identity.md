# R3: stable identity for structures, rivers and conversation lines

#462 R3. In one Mesh Studio session, a structure, a river or a conversation line deleted and replaced gave its id
to the replacement, so an AI's proposal about the deleted one, accepted later, changed the replacement.

**Verdict: READY FOR RE-REVIEW** (after the independent review's two findings, section 8).

Base `f96703e8a241d07e2c19413d75c7b85e12990e2c`. Evidence: `docs/reviews/r3_stable_object_identity_evidence/`.

## 1. The defects, reproduced

A real `StudioAIHost` on its loopback bridge; the AI through `engine.authoring_session` (what the MCP tools and
`mesh author` call) with R1's `base_revision_id`, in the same session (R1's cross-session refusal plays no part);
the person edits with the operations Studio's own tools call, through `Project.edit_scene` as they do (the river
drawn with `RiverTool._new_id`); acceptance is `StudioAIHost.accept`, Studio's Accept (`repro_r3.py.txt`).

| | baseline `f96703e8` (`repro_before.json`) | with the fix (`repro_after.json`) |
|---|---|---|
| **A. structure** "crate" placed; the AI proposes turning it 90 degrees; the person deletes it and places another crate 25 m away | the new crate is **"crate"**; Accept: **ok**, the new crate turned 90 degrees | the new crate is "crate_3" (the room has "crate_1"/"crate_2"); Accept: **conflict** at `#crate/rotation`; the new crate unchanged |
| **B. river** drawn ("river"); the AI proposes `passable: block`; the person removes it and draws another elsewhere | the new river is **"river"**; Accept: **ok**, the new river blocks characters | the new river is "river-2"; Accept: **conflict** at `#river/passable`; unchanged |
| **C. line** added ("line_2", "The bridge is out."); the AI proposes speaker "Ghost"; the person deletes it and writes another ("The ferry runs at dawn.") | the new line is **"line_2"**; Accept: **ok**, the new words now spoken by "Ghost" | the new line is "line_3"; Accept: **conflict** at `nodes/line_2/speaker`; unchanged |

Each regression (`tests/test_studio_object_identity.py`, the first three tests) failed on the baseline:
"the replacement was given the deleted structure's id" (`'crate' != 'crate'`), "... river's id" (`'river'`),
"... line's id" (`'line_2'`) (`regression_before.txt`).

## 2. Root causes

Ordinary objects already never reuse an id within a session (#462 S1-ID): `Project.ids_seen` holds every object id
the session has seen, and `project_ops.retired_ids` lets `unique_entity_id` avoid them. These three kinds had their
own id makers, which looked only at what is in the room now:

- **Structures:** `unique_structure_id` took the model's name, or the next `_N` free *among the structures present*.
  Delete "crate", place a crate: "crate" again. An explicit `structure_id` was taken as given (any string).
- **Rivers:** Studio's River tool (`RiverTool._new_id`) chose "river", "river-2"... free *among the rivers present*.
  An AI's `add_river` names its id; one a deleted river had was taken.
- **Lines:** `_new_line_id` numbered after the highest `line_N` *present* (and the line count). Deleting the last line
  and adding one gave the deleted number again. A conversation removed (its Dialogue behaviour) and started again
  began at "root" again.

Accepting then compared the proposal's base with the project: the person's delete-and-replace left the same id
with new values, and the AI's property (rotation, passable, speaker) wasn't one the person had set, so no conflict;
replaying the change wrote it onto the replacement.

## 3. The mechanism

The smallest extension of the S1-ID one, sharing its upkeep:

- **Kept in the same set.** `Project.ids_seen` now also holds every structure's, river's and line's id the session has
  seen, each as a *scoped id* (`project_ops.scoped_id`): `structure/<room>/<id>`, `river/<room>/<id>`,
  `line/<room>/<object>/<id>` (joined by a control character no id contains). `studio_project._ids(key, room)` adds
  `project_ops.scoped_ids(key, room)` to a room's object ids. So everything that already keeps the set keeps these:
  a room read for the first time (also one first read by an edit or an AI batch), every stored edit, every state an
  edit leaves (`_record`: each step of a batch too), the preview's copy (`clone`), undo and redo (the set only grows).
- **The room being edited.** The id makers are pure functions of a room; which room they make things in is now said
  by `project_ops.in_room(key)`, entered by `Project.edit_scene` (every Studio edit) and by each change of an AI
  batch (`authoring._apply_one`), and by the River tool when it names a river. Outside Mesh Studio's edits (tools,
  templates, tests calling `project_ops` directly) nothing is retired and ids are made exactly as before.
- **The id makers avoid them.** `unique_structure_id` and the new `unique_river_id` (the River tool's naming,
  unchanged: "river", "river-2"...) skip ids their kind had in the room; `_new_line_id` numbers after every number
  the conversation had (so a new line is still numbered last); `set_dialogue_text` starting a conversation again
  gives its opening line a new id if "root" was had.
- **Explicit ids.** `place_structure(structure_id=...)` and `add_river(river_id=...)` naming an id one of that kind
  had in the room this session are refused, saying so (no silent redirect to another id, which "@N" references
  would then follow). A `structure_id` must now be a short name as a river's id is (`[a-z0-9][a-z0-9_-]{0,39}`);
  before, any string was stored. Lines have no explicit ids.

**Scopes.** A structure's and a river's id are unique in their room, a line's in its conversation (room and object).
Two rooms may both have "crate" and "river"; two people may both have "line_2". Room keys and object ids are never
reused in a session already (S4, S1-ID), so the scopes can't alias. **The shared player's conversation is one for the
whole project** (section 8): its lines are kept once, as `player-line/<id>`, whichever room it was edited in.

**Why per session is enough.** A proposal from an earlier session is refused by R1 (`revision_from_another_session`),
so ids need only never be reused within one; nothing new is saved, no file format changes, no migration, and loading
makes no ids (an existing id is the object's identity, kept as it is).

## 4. Creation paths examined

| path | protected |
|---|---|
| Studio's structure tool (`studio_hd2d`: `place_structure` in `Studio._edit`) | yes (`edit_scene`) |
| an AI's `place_structure`, with or without `structure_id` | yes (`_apply_one`); explicit had/invalid refused |
| Studio's River tool (`RiverTool._new_id`, chosen before the edit) | yes (its own `in_room`) |
| an AI's `add_river` (always names its id) | had/invalid refused |
| Studio's conversation editor (`+ Next line`, `+ Separate line`, `+ Line after`: `add_line`) | yes |
| an AI's `add_line` | yes |
| the shared player's conversation, edited in any room (Studio or an AI) | yes: project-wide (section 8) |
| an older one-list conversation brought up to date (`_graph`) | yes; same ids as before when nothing was had |
| a conversation started again (`set_dialogue_text` after the Dialogue behaviour was removed and added) | yes |
| `paste_entity` (copies a conversation under a new object id: a new scope) | nothing to do |
| `hd2d/starter_village` (explicit structure ids, outside any session) | unchanged (its ids are valid short names) |
| a new room (`add_room`, `add_hd2d_room`): a new room key, never had | nothing to do |

Not changed: unkeyed things (lights by index), id-less legacy structures (positional names, which no operation can
target: `find_structure` matches stored ids only), room keys and room files (S4), R1, R2.

## 5. Proposal correctness

The acceptance test is what happens to the object, not only that two ids differ (each of A, B, C): the AI's preview
names the original; the original is removed; a replacement is made; accepting the stale proposal is refused as a
**conflict** naming the original's id and property; the replacement is exactly as before; nothing else in the project
changed (every document compared with that kind taken out); a fresh proposal against the replacement is accepted.
The conflict comes from the existing comparison (#462 S1): the person removed the very property the AI changes.
Ordinary proposals are untouched: an unrelated edit since the read still lets a proposal apply (the existing F6 and
write-set suites, unchanged and passing).

## 6. Evidence

**Regressions** (`tests/test_studio_object_identity.py`, 31 tests (12 added in section 8), integration lane; real
host, bridge, acceptance):

- the three reproductions (above);
- four delete-and-make-again cycles of each kind: 4 distinct ids each (rivers "river" ... "river-4");
- one AI batch that places, removes and places a structure, and adds, removes and adds a line: new ids, and the
  preview's summary names the ids accepting made; the same batch giving a river or structure id again: refused at the
  third change, nothing staged;
- Studio and an AI: a river drawn and removed in Studio can't be taken by the AI; the AI's removed river isn't taken by
  the tool; the AI's removed structure isn't taken by Studio's structure tool;
- look-alikes: two crates on one spot, two lines with the same words: distinct ids; a stale change to the first never
  lands on the second;
- undo: undoing a deletion brings back the same object and id (the stale proposal then applies to it: it *is* the
  previewed object); redoing the deletion and placing again: a new id; a placement undone: its id isn't given back;
- the preview's copy makes the ids applying makes (`authoring.dry_run` vs acceptance);
- save and reopen: every id as it was; loading twice gives identical documents; the next session makes new ids
  beside them;
- an older one-list conversation: brought up to date with the same line ids in Studio as anywhere else;
- scopes: another conversation numbers its own lines; a room not read yet (the cottage) gets "crate" though the
  start room had crates; an id had in that room is refused there, a new one fine;
- invalid explicit ids (structure: not a short name, a number, too long; river: empty, not a short name): refused,
  nothing staged;
- a conversation started again: its opening line gets a new id; the stale proposal about the old opening is refused;
- R1: a revision of another session is still refused.

**Mesh Studio's River tool** (`tests/test_studio_object_identity_gpu.py`, GPU lane): drawn by clicks and Enter,
removed with Delete, three times: "river", "river-2", "river-3"; undo brings "river-3" itself back.

**Deliberate faults** (`faults.json`, `mutate.py.txt`): 13 of 13 fail a test: a new structure's id ignoring the ids structures had; a had structure id given, taken; a structure id given, unchecked; a new river's id ignoring the ids rivers had; a had river id given, taken; a new line's id ignoring the lines its conversation had; a conversation started again getting its old opening line's id; lines not remembered; none of the three remembered; an AI's change not saying its room; a Studio edit not saying its room; the River tool naming a river without what rivers had; the preview's copy forgetting the ids seen.

**Local** (Windows): the structure, river, dialogue, identity (#471), write-set, F6, R1, authoring-session and
proposal-memory modules, 380 passed; R2 ownership, 26 passed; the real-window River tool, dialogue reopen and new
identity tests, 10 passed; ruff and mypy. Linux is CI's.

## 7. Limits

- **Within a session.** A new session starts its set from the files; an id had only in an earlier session may be made
  again. A proposal from an earlier session is refused by R1, so it can't reach the new object.
- **A created object's id at acceptance.** The preview names the ids its changes would make at the time; if the
  person makes and deletes an object with that id before accepting, accepting makes the next one instead (it is still
  a new object; nothing existing is touched).
- **`structure_id` is now checked** (a short name of lowercase letters, digits, `-`, `_`), as a river's id is. A tool
  that gave other strings would now be refused; no caller in the repository does.
- **Not addressed:** unkeyed lights, room keys (S4), R1, R2.

## 8. Independent review remediation

The review of head `f9febde9` found two P2 issues. Base unchanged: `f96703e8a241d07e2c19413d75c7b85e12990e2c`.

### 8.1 The shared player's conversation lines (reproduced, fixed)

**Reproduced** (`repro_player.py.txt`), as section 1: the player given words in Studio, a line "line_2" added; the AI
proposes speaker "Ghost" for it with R1's `base_revision_id` in the same session; the person deletes it and writes
another, in the same room and, separately, in another room (the cottage, where the player is another reference).

| replacement written in | before (`repro_player_before.json`) | after (`repro_player_after.json`) |
|---|---|---|
| the same room | **"line_2"**; Accept: **ok**, the new words now spoken by "Ghost" | "line_3"; Accept: **conflict** at `player/.../nodes/line_2/speaker`; unchanged |
| another room | **"line_2"**; Accept: **ok**, "Ghost" (in every room) | "line_3"; **conflict**, as above; unchanged |

**Root cause.** Rooms hold only a reference to the shared player (`prefab_id: "player"`, where it starts); what it
is and says is `Project.player`. `ids_seen` was kept from stored rooms (`_store` splits the player out first, `_record`
read `before.scenes` only), so the player's lines were never in it; and the line id maker looked them up per room and
object, while each room's reference has its own object id.

**The correction (one scope for the project, no copy per room):**

- `project_ops.player_line_ids(definition)`: the player's lines as `player-line/<id>`, kept in `ids_seen` by
  `Project._store` (the definition an edit leaves) and `Project._record` (the definition before every edit, also each
  step of a batch; so also lines read from the files). The player is in every snapshot, so this covers undo and redo,
  the preview's copy and save/reopen as for rooms.
- `in_room(key, players)`: the room's shared-player references (`Project.shared_players(key)`, new, the accessor
  `is_shared_player` already computed), passed by `edit_scene` and each AI batch change. `_new_line_id` and
  `set_dialogue_text` ask `_lines_had(entity_id)`: the project-wide set for a shared-player reference, the room and
  object's for any other object, as before.
- Unchanged: an NPC's lines (room and object), a room's own full player in a project made before the player was shared
  (an object like any other: room and object), what is saved, operation names and arguments.

**Tests** (in `tests/test_studio_object_identity.py`): the reproduction, written in the same room and in another (each
also checks the replacement and every other document unchanged, and a fresh proposal made in the other room applying in
every room); four write-here, delete-there cycles: "line_2" ... "line_5"; undo of a deletion brings the line back in
every room and the stale proposal applies to it; redo never frees its id; a line made by one edit and undone isn't given
back; an NPC's next line unchanged; an AI batch adding, removing and adding the player's lines across two rooms: new
ids, the preview's copy has the ids accepting makes; save and reopen keeps the lines, and a saved line deleted in the
new session isn't given back; a room with its own player: its lines remembered for its room and object, not the
player's scope. Five of them fail with the reviewed implementation (`regression_before_player.txt`).

**Deliberate faults** (`faults_player.json`, `mutate_player.py.txt`): 6 of 6 fail a test: the line id maker ignoring
the player's lines; a Studio edit or an AI change not naming the room's player references; the player's lines not kept
after an edit, or before one; the player's lines scoped per room instead of the project.

### 8.2 A new river's id, lazily (`unique_river_id`)

It built a tuple of ~100,000 candidate names on every call (each time the River tool starts a river). Now
`itertools.chain(("river",), (f"river-{n}" for n in itertools.count(2)))`, first free taken: the same sequence, nothing
materialised, no upper bound. Measured with the two functions' own source, same process, same helpers, Python 3.13
(`river_id_bench.json`, `river_id_bench.py.txt`):

| room | before: peak allocation / time per call | after |
|---|---|---|
| no rivers | 6,791,690 B / 10.9 ms | 1,232 B / 1.7 us |
| 3 rivers and one had | 6,791,690 B / 11.3 ms | 1,322 B / 2.5 us |

Tested for the sequence only (no timing threshold): none, several present, had, present and had, high numbers, a run
of 2,000; and another room's had ids not counting.

### 8.3 Validation

Local (Windows): `test_studio_object_identity` 31; shared player, dialogue editor and line order, editor dialogue,
project-ops authoring, authoring and authoring session, river and River tool, write-set, F6 base revision, R1, proposal
memory, proposal inbox: 209 passed together; #471 identity, room file ownership, R2 ownership, Studio project: 87
passed, 1 skipped; undo history sharing 16; the real-window River tool, dialogue reopen and identity tests 10; ruff and
mypy.

**Observed, not changed (out of scope):** the AI's preview summary of a change to the shared player's conversation reads
"(no visible change)"; the conflict and the outcome are right, the summary's wording of player changes is a separate
matter.
