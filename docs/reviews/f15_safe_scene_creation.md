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

## Publication never replaces (review correction)

The checks above give clear early messages, but a check followed by a write always leaves a window. So the writes of
new files themselves never replace anything. `json_io.publish_new(src, dst)` moves a fully written file into place
only if nothing is at `dst` (a file, a folder or a link, even a broken one), atomically:

- **On Windows** it is a rename, which fails when the target exists (`MoveFileEx` without `MOVEFILE_REPLACE_EXISTING`).
- **Elsewhere** it is a hard link, which fails when the target exists, followed by removing the temporary name.
- **A file system that can do neither** raises an error and publishes nothing. There is no fallback that could
  replace.

It is used in two places:

- **Project saves:** for `fresh` room files (a new room's, or a listed room whose file was missing), in place of
  `os.replace`. Something put there at the very moment of publication stays exactly as it is, and the save fails as
  `commit`/`path_taken`. F3's rollback puts back every file already written. An error just after a hard link is
  recognised with `os.path.samefile` and put back too. Existing room files are still replaced as before.
- **`scaffold.create_scene` with `force=False`** (AI scene creation): `json_io.write_json_new` writes a temporary file
  of its own beside the target, then calls `publish_new`. A target that appears after the checks, or a broken link
  (even one pointing inside the project), is refused and never written through. `AIOps` answers `already_exists`.
  `force=True` keeps replacing, for the callers that ask for it; AI scene creation never passes it.

## What remains

- **Orphan map skeletons (F11).** A room made and then undone, or never saved, still leaves its map file. F11 is
  unchanged: those are files Mesh made, and they are never replaced.
- **Existing files are still replaced under F3's rules.** That is ordinary saving of a room the project owns, with its
  outside-change backup and commit-time check.

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
  - **Review corrections:**
    - a file, folder or broken link put at a new room's path inside the publication call itself (after every check), with the start room already written: the newcomer survives exactly, and the start room is put back to the byte and the time;
    - a file system that can't publish without replacing fails closed;
    - `publish_new` against each kind of occupant;
    - a broken link inside the project (AIOps and the scaffold both refuse it; nothing is made where it points);
    - a scene put there while it is being created;
    - `force=True` still overwrites.
- **Mutation check:** each guard removed in turn:

  | Guard removed | Tests that fail |
  | --- | --- |
  | the creation claim | 12 |
  | the HD-2D claim made after installing the kit | 4 |
  | the save-time check | 2 |
  | `create_scene`'s existing-target check | 2 |
  | ignoring the scaffold's result | 1 |
  | fresh room files replaced instead of published (review) | 4 |
  | the scaffold replacing when not forced (review) | 2 |
  | `publish_new` replacing on Windows (review) | 5 |
