# H1-F2: an unreadable prefab catalogue is never replaced by a save

Repository health finding **F2 / P1** (audit tracker #422). Base: `redesign/visual-editor` at `0f23890`.

## The failure

`assets/prefabs.json` holds the project's shared player and every other prefab: Person, Sign, and the creator's own.
When the shared player changes, `Project.save()` rewrites that file: the player's entry is replaced and every other
entry is kept.

`Project._read_prefabs()` returned `[]` in three situations:

- the file was missing;
- it couldn't be read, or wasn't valid JSON (`OSError`, `ValueError`);
- it didn't hold a list.

`save()` used that `[]` as the catalogue to keep, and wrote `[player]` over the file. The outside-change backup
(`_keep_outside_change`) only helped if Studio had recorded the file's time when it opened. It records that only when
the catalogue was readable and held a player at the time. A catalogue that was already broken when the project opened
was replaced with no backup at all.

Reproduced on `0f23890` with disposable projects (the starter template: player, Person, Sign). Each case damaged the
catalogue, made the shared player dirty and saved (`h1_f2_evidence/before_0f23890_save_with_damaged_catalogue.json`):

| Damage | Save | Catalogue after | Backup | Still dirty |
|---|---|---|---|---|
| Malformed JSON, before the project opened | "saved" | `[player]`: Person and Sign gone | none | no |
| Malformed JSON, after opening (an outside edit) | "saved" | `[player]` | `.outside-change.bak` | no |
| An object instead of a list, before opening | "saved" | `[player]` | none | no |

## The protection

`engine/studio_project.py`:

- **`_prefab_catalogue()`, for writing,** distinguishes the cases. It returns `[]` only when the file doesn't exist,
  because a new or older project starts a catalogue then. If the file exists but can't be read (permission, a folder,
  I/O), isn't valid JSON or UTF-8, or isn't a list, it raises `ops.OpError` with the reason and what to do: "Fix or
  restore that file, then save again; your changes are kept until then." It reads through `json_io.read_json`, which
  also accepts a UTF-8 BOM.
- **`save()` uses it when assembling what to write,** before the first file is replaced. A refused save therefore
  writes nothing, including rooms changed in the same session. It leaves the dirty flags and the undo/redo history as
  they were, so nothing is reported as saved.
- **`_read_prefabs()`, for reading the shared player when a project opens,** still reads an unreadable catalogue as
  none, so the project opens as before. It now goes through `_prefab_catalogue()`.

**Studio:** `Studio.save` already shows `Couldn't save: <reason>` (marked as a failure) for an `OpError`, returns
False, and keeps the window open on quit. **AI file edits** (`authoring_session`) call the same `save()`. The refusal
reaches their caller as an `OpError`, as an existing map-size refusal already does, and nothing is written.

Unchanged:

- the file format;
- the shared player's semantics: other entries keep their order and content;
- the outside-change backup for a valid file changed outside Studio;
- room and world saves when the player isn't dirty;
- project loading.

**Not done here:**

- No automatic repair of a damaged catalogue. That needs the creator's consent.
- No multi-file transactional save (F3). This fix only guarantees the refusal happens before any write.

## After the fix

The same reproduction (`h1_f2_evidence/after_fix_save_with_damaged_catalogue.json`): each case is refused with the
reason, for example "it isn't valid JSON: Expecting property name … line 253 column 1" or "it holds dict, not a list of
prefabs". The catalogue stays **byte-identical**, no file is written, and the project stays dirty with the change kept.

## Tests

`tests/test_prefab_catalogue_safety.py` (fast; temporary projects, one blank project created per module and copied per
test):

1. A valid catalogue keeps every other prefab, including a creator's own.
2. A missing catalogue starts a new one.
3. Malformed JSON, an object, a string and `null` (4 cases) each refuse the save. The catalogue and the room file are
   byte-identical, no backup is made, the change and its undo history are kept, and undo still works.
4. A read failure (a `PermissionError`, injected) refuses the save, and the file is kept.
5. After the file is fixed, the next save works, with all four other prefabs present without being rebuilt.
6. A valid catalogue changed outside Studio is still backed up, and the prefab added outside is kept.
7. Studio's own save path (`Studio.save`) says "Couldn't save: …" with the fix-and-retry advice, returns False, and
   keeps the project dirty.

Against `0f23890`, 7 fail and 3 pass (`h1_f2_evidence/before_tests_on_0f23890.txt`):

- **The 3 that pass** are the compatibility cases: a valid catalogue, a missing one, and the outside-change backup.
- **The read-failure test** fails there because the old module has no `read_json` to fault-inject. The old code would
  also have read that `PermissionError` as an empty list.

## Compatibility and limits

- **A catalogue saved with a UTF-8 BOM** (for example from a text editor) used to read as empty, so the shared player
  wasn't found. It now reads correctly.
- **A refused save holds back every file in that save,** not just the catalogue. This is deliberate: it stops a
  partial save of the player's rooms without the player.
- **A damaged catalogue still opens** with no shared player, as before. Studio says nothing about it until a save that
  needs the catalogue. Opening-time warnings aren't in this fix's scope.
