# F3: recoverable multi-file project saves (#422, P1)

## The defect

`Project.save()` (`engine/studio_project.py`) writes up to four kinds of files: an HD-2D room's map file resized with
its room, each changed room, the world file and the prefab catalogue (`assets/prefabs.json`, the shared player). Each
file was written atomically (`write_json_atomic`), but one after another. If a later write failed, the earlier ones
were already replaced, so the project on disk mixed new and old files while Save said it had failed.

Reproduced at the base (`2b4a291`): a blank project with two rooms, Start and Cellar. Both rooms, the start room
(world file) and the player's picture (prefab catalogue) were changed, and the second write was made to fail
(`OSError 28`):

```text
save raised OSError: [Errno 28] injected: no space left on device: '...\scenes\start.json'
  packs/core_regions/scenes/cellar.json: NEW (written)
  packs/core_regions/scenes/start.json: old
  packs/core_regions/worlds/main.json: old
  assets/prefabs.json: old
seen-on-disk recorded the half-saved room as saved: True
MIXED PROJECT ON DISK: True
```

The Cellar now named a start room that the world file didn't, and the shared player was saved in no file.

## The policy (`engine/project_save.py`)

`Project.save()` builds the complete list first: map files at their rooms' sizes, the changed rooms, the world file
and the catalogue. It refuses before anything is written if a map file can't be resized or the catalogue can't be
read: H1-F2's safeguard, unchanged. Then `save_documents` writes them as one save:

1. **Serialise** every document to its bytes (the same bytes as before: `dumps_stable` and a newline).
2. **Stage** beside each file:
   - the new bytes go to `<name>.save-<id>.new`;
   - a file already there is kept as `<name>.save-<id>.original`. This is a hard link: the same file under a second
     name, so nothing is copied, its time is kept, and replacing the file leaves it as it was. On a file system
     without hard links it is an exclusive copy with the file's time. Either way it is checked;
   - a file something else changed since Studio read it is also kept as `<name>.outside-change.bak`.

   A failure here deletes what was staged, and no project file has changed.

   **Only the save's own working files are touched.** `<id>` is 128 random bits, but randomness isn't what makes a
   file the save's own. Each working file and backup is created exclusively (`open(..., "xb")` or `os.link`), never
   over an existing file, and is recorded only once it has been created. Only recorded files are ever moved or deleted, and a
   file is dropped from the record as soon as it is moved. If a name is already taken, the save stops with
   `temporary_file_exists` and leaves that file as it is. A partly written working file is deleted only by the step
   that created it.
3. **Commit** in order. Before each `os.replace`, the target must still be the file that was copied, or still be
   absent. Otherwise the save stops with `changed_during_save` and that file is not replaced. A failure, or an
   interrupt, puts back every file already replaced, last first: from its `.original`, or by deleting a file that
   didn't exist before. Folders the save made are removed again.
4. **A put-back that fails** leaves that file as written and keeps its `.original`. The save fails with
   `recovery_required`, naming each file and where its previous version is. Nothing deletes that copy, not even a
   later successful save.
5. **A file changed after the save wrote it is never put back over.** Before putting a file back, the save checks
   that it still holds exactly the bytes the save wrote. If another program has since rewritten or removed it, the
   save leaves it as that program left it and keeps the `.original`. That file is reported as `needs_recovery` with
   `problem: "changed_after_save"`, and the save fails with `rollback_conflict`. This holds for files that existed
   before the save (the original is kept) and for files the save created (they are not deleted). Both versions
   survive, and the person chooses.

Only when every file is committed is the save a success. Its `.original` copies are then deleted and Studio's undo
and dirty marks are updated as before.

**On failure nothing in Studio changes:**
- the edits stay, unsaved, and undo, redo and the revision are as they were;
- what Studio last saw on disk is unchanged, apart from a file the save couldn't put back, which holds Studio's own
  version, so the next save doesn't take it for an outside change.

**Outside changes:**
- they are still kept as `.outside-change.bak`, whether or not the save then succeeds;
- an earlier backup with different contents is never overwritten: the next one is `.outside-change-2.bak`, and so on;
- a save that fails puts the outside version back in place.

## One report, three ways to see it

Every outcome is the same report: `SaveError.report` on failure, and `Project.last_save_report` either way.

| Field | Meaning |
| --- | --- |
| `ok`, `stage`, `reason`, `message` | `stage` is null on success; the message is written for a person |
| `documents` | each file's `path`, `kind` (`map`, `room`, `world`, `prefabs`), whether it `existed`, and its `result` (`saved`, `restored`, `not_written`, `needs_recovery`) |
| `committed`, `restored` | which files hold the new version, and which were put back |
| `recovery_required`, `needs_recovery` | each file to recover: its `path`, the `problem` (`put_back_failed`, or `changed_after_save` when another program changed it after the save wrote it), its previous version (`original`, or null if it didn't exist) and the `action` to take |
| `outside_change_backups`, `leftovers` | backups made of outside changes, and working files that couldn't be deleted |
| `unsaved_edits_kept` | true in Studio; false for `mesh author` and MCP, which keep no edits |

| Stage | Reason | What it means |
| --- | --- | --- |
| `validate` | `map_file_conflict` | An HD-2D map file is missing, unreadable or has tiles of its own. Nothing was written. |
| `validate` | `prefab_catalogue_unreadable` | `assets/prefabs.json` can't be read as a list (H1-F2). Nothing was written. |
| `serialize` | `serialize_failed` | A document isn't JSON. Nothing was written. |
| `stage` | `stage_failed` | Staging or copying a file failed. No project file changed. |
| `stage` | `temporary_file_exists` | A working file's name was already taken. That file was left alone, and no project file changed. |
| `commit` | `commit_failed` | Replacing a file failed. Every file already written was put back. |
| `commit` | `changed_during_save` | Something else changed a file during the save. That file wasn't replaced, and the others were put back. |
| `rollback` | `rollback_incomplete` | A file couldn't be put back. Recovery is needed: see `needs_recovery`. |
| `rollback` | `rollback_conflict` | Another program changed a file after the save wrote it. It was left as that program left it, and its previous version was kept. Recovery is needed: see `needs_recovery`. |

- **Studio:** says `Couldn't save: <message>` and adds that the changes are still there, unsaved. The live read
  (`read_project` on an open Studio) includes `last_save`, so an AI helping the person can see the failure. It is
  read-only and adds no new protocol.
- **`mesh author apply`, MCP `apply_changes` and `apply_ops`:** answer `ok: false, reason: "save_failed"` with the
  report as `save`. Before, the exception escaped: an `OSError` reached the CLI as `bad_input`, and an `OpError` as a
  traceback. `mesh author` exits 1.

## Limits

- **Recovery from failures Mesh sees, not power loss.** Files are replaced one at a time and nothing is fsynced. A
  crash or a killed process during the commit can still leave a mix, with `.save-<id>.new` and `.original` files
  beside them. An `.original` is the previous version: keep it until checked.
- **The change checks aren't atomic.** They run just before each replace and each put-back, so an edit made in the
  microseconds between a check and its replace isn't caught.
- **The hard link shares the file until the commit.** An `.original` that is a hard link is the same file as the
  target until the target is replaced. A program writing into the target in place before then changes both. The
  commit-time check sees the change, and the save stops without replacing that file.
- **No retries.** A Windows file held open by another program fails the save, which is put back. The person saves
  again.
- **Unchanged outside `Project.save()`:** files written straight away, such as new map skeletons, imported tilesets
  and pictures (F11).

## Evidence

- **Tests:** `tests/test_project_save_transaction.py` (integration, 39 tests). Each test injects a failure at one of
  the service's file steps (`_write_new`, `_preserve`, `_replace`, `_unlink`) on a real project on disk. It compares
  every file's bytes and modification time, and Studio's documents, dirty flags, undo and redo, revision and
  seen-on-disk times, before and after.
- **Review corrections:**
  - Working-file names already taken by someone else's `.new` or `.original`, for the first and for a later file,
    with hard links and without: the save is refused, and the whole tree, including that file, is byte- and
    time-identical.
  - Without hard links, a failed save is still put back to the byte and the time.
  - The working-file name carries 128 random bits.
  - Another program rewrites or deletes a committed file, then a later commit fails. The other program's version
    stands exactly, and the previous version is kept. This is covered for an existing file and for a new one.
  - Studio, `mesh author` and MCP each get `rollback_conflict` with `changed_after_save`.
- **Mutation check:** each guard was removed in turn and the suite rerun:

  | Guard removed | Tests that fail (of 39) |
  | --- | --- |
  | rollback | 21 |
  | commit-time change check | 1 |
  | rollback's change check | 6 |
  | record `.new` only once created | 2 |
  | record `.original` only once created | 4 |
  | keep the original without overwriting (`copy2`) | 4 |
  | exclusive fallback copy | 2 |
- **Cost:** a save of a 5 MB room and four small files, measured interleaved (median of 20, Windows):

  | Version | Time |
  | --- | --- |
  | base write loop | 58 ms |
  | first review head (`f065608`, which copied originals) | 70 ms |
  | this head (hard links) | 68 ms |

  An exclusive Python copy instead would have cost 82 ms, because each `open()` on Windows costs about 1 ms. The
  saved bytes are the same as before.
- **Also fixed:** `mesh author apply` left the changes file open (a `ResourceWarning`). The new CLI test caught it.
- **The same scenario at this commit:** `SaveError` with stage `commit`, reason `commit_failed`, Cellar restored.
  All four files are as they were and the project is still dirty, with undo and revision unchanged.
