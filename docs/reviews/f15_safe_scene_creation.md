# F15 + F14: safe scene creation (#422)

## The defects

**F15 (P1).** `project_ops.new_room` named a new room's file after the first room key the *world* didn't use. It
never looked at the disk. A scene file that the world doesn't list (made by hand, by `create_scene`, or left behind
by a removed room) was therefore taken over: `Project.add_room("Cellar")` followed by Save replaced
`scenes/cellar.json`. There was no outside-change backup, because the project had never read it, and F3's
`.original` copy is deleted once a save succeeds.

**F14 (P3).** `AIOps.create_scene`, behind the MCP `create_scene` tool, ignored what the scaffold returned and always
answered "Created scene". An AI was told it had made a scene that already existed (and then edited the creator's
scene), or one that was never written.

**Reproduced at the base `3b90bb5`** on a blank project, with an unlisted `scenes/cellar.json`:

| Path | Base | This change |
| --- | --- | --- |
| Studio: `add_room("Cellar")`, then Save | no error, the creator's file **overwritten**, no backup | refused, naming the file; **kept** |
| Direct AI authoring (`authoring_session.apply` with `add_room`) | `ok: true`, file **overwritten** | `ok: false`, `invalid_change`, naming the file; **kept** |
| `AIOps.create_scene` over an existing scene | `ok: true`, "Created scene…" (nothing created) | `ok: false`, `already_exists`, naming the path |
| `AIOps.create_scene` with an unknown template | `ok: true`, "Created scene…" (nothing created) | `ok: false`, `unknown_template`, with the template list |

## The fix

**When a room is made** (`Project._claim_room_files`, for both `add_room` and `add_hd2d_room`), its scene file and
its map file must be free:
- no file, folder or link at either path;
- neither path is another room's file in the world.

Otherwise `OpError` names the path, and nothing changes: no room is registered, nothing is dirty, undo and the
revision are unchanged, no map file is written and no HD-2D kit is installed. The check runs before all of that.
`project_ops.new_room` stays pure; the disk belongs to the project layer.

**When it is saved** (`Project.save` → `project_save.save_documents(..., fresh)`): a room file the project has
never read or written (a new room's, or a listed room whose file was missing when it was read) must still be free.
Something that appeared there since fails the save before any file is replaced: stage `stage`, reason `path_taken`.
This runs inside F3's transaction, so it is all or nothing, with the same report and rollback. The person's work
stays unsaved; moving the newcomer away lets the save go ahead.

**The room is never quietly renamed or moved to another path.** The refusal says what is there and what to do:
"There is already a file at packs/core_regions/scenes/cellar.json that isn't one of this project's rooms, so the
room 'Cellar' wasn't added and nothing was changed: Mesh never takes over a file it didn't make. Give the room another
name, or move packs/core_regions/scenes/cellar.json out of the way first."

**Where people and agents see it:**
- **Studio** shows the refusal through its existing room-creation and save messages.
- **`mesh author apply`, MCP `apply_changes`/`apply_ops`, dry runs and Studio proposals** answer `invalid_change`,
  with the operation, its index and the message. A proposal for such a room is refused when it is staged, and again
  if the path is taken by the time the person accepts it.

**`AIOps.create_scene` (F14)** checks for anything at the target (file, folder or link), then for a known template,
then uses the scaffold's own result. It answers `ok: false` with `data.reason` `already_exists`, `unknown_template` or
`write_failed` and the path. On success it returns the same "Created scene '…'" as before.

## What remains

- **The checks aren't atomic with the writes.** A file created in the microseconds between the save's check and its
  `os.replace` is still caught: F3's commit-time check (`changed_during_save`) refuses to replace a path that was
  absent when staged. `create_scene` has a similar window between its check and the scaffold's own check and write.
- **Orphan map skeletons (F11).** A room made and then undone, or never saved, still leaves its map file. F11 is
  unchanged: those are files Mesh made, and they are never replaced.

## Evidence

- **Tests:** `tests/test_safe_scene_creation.py` (integration).
  - **The destructive case**, deterministically: the creator's file is kept byte for byte.
  - **What occupies the scene path:** a creator's scene, malformed JSON, a folder or a link, for both 2D and HD-2D
    rooms. Each check compares the whole tree (bytes and timestamps) and the project's world, rooms, dirty flags,
    undo and revision.
  - **An occupied map path**, and another room's registered file.
  - **A file or folder appearing after the room is made and before Save:** `path_taken`, all or nothing, and the
    work is kept and saved once the newcomer is moved.
  - **What still works:** a normal new 2D room, a normal new HD-2D room, and a listed room whose file is missing.
  - **The AI paths:** direct authoring, dry run, MCP and the CLI (exit 1); a Studio proposal refused at staging and
    at acceptance.
  - **`create_scene`:** success, an existing file or folder, an unknown template, and a failed write through the MCP
    tool.
- **Mutation check:** each guard removed in turn:

  | Guard removed | Tests that fail |
  | --- | --- |
  | the creation claim | 12 |
  | the HD-2D claim made after installing the kit | 4 |
  | the save-time check | 2 |
  | `create_scene`'s existing-target check | 2 |
  | ignoring the scaffold's result | 1 |
