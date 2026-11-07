# Watchfire R4: a conversation's line numbers after saving and reopening

A creator-trial fix (*The Last Watchfire*, Major 4). It is not a milestone. Base: `redesign/visual-editor` at `fc220b4`.

## What the trial saw

The trial wrote a conversation, saved, closed and reopened Studio. The first line had become the last one (line 9),
and the "Otherwise line" read 9. The story still played correctly.

## What actually changes on reopening (established first)

I reproduced this in Mesh Studio's real window on a disposable copy of the M23B clearing, using its own mouse and
keys (`tooling/watchfire_r4_dialogue.py`):

1. A Person was placed and renamed Warden.
2. An eleven-line conversation was written in the Dialogue tab:
   - its first line, then "+ Next line";
   - three separate lines;
   - a run of lines added with "+ Line after";
   - two choices on line 2: one sets `task_accepted` and branches to line 3, the other goes to line 4;
   - line 3 runs on to line 5;
   - an opening that needs `task_accepted`.
3. The room was saved, Studio closed, and the project reopened.

| | As written | After reopening (`fc220b4`) |
|---|---|---|
| Line ids, words, `next` links, choices' destinations and flags, start, openings | (saved) | **identical** |
| The number shown for "Traveller!" (`root`) | 1 | **11** |
| The number shown for "Safe travels." (`line_10`) | 10 | **1** |
| "Otherwise line" | 1 | **11** |
| The opening's "start at line" | 11 | **2** |
| "+ Next line" button | "+ Next line (after 11)" | **gone** |
| A line added "at the end" (`ops.add_line`: Studio's "+ Next line") | follows line 11 | **follows nothing** (left cut off) |
| In the game, and in an exported build | plays as written | **plays as written** |

So the authored data, the identifiers, the references and the game were all unaffected. What changed was:

1. **The numbers the editor shows.** A creator types those numbers into "Goes to line", "Next line", "Otherwise line"
   and the openings, so after a reopen the same number meant a different line.
2. **The editor's idea of "the last line".** "+ Next line" disappeared, and a line added at the end with `ops.add_line`
   was no longer linked into the conversation.

## Root cause

- **Saving sorts keys.** `Project.save` writes rooms with `json_io.dumps_stable`, which sorts every key; this is the
  repo-wide deterministic file format. A conversation's `nodes` therefore come back sorted by name: `line_10`,
  `line_11`, `line_2` … `line_9`, `root`. While editing, they are in the order they were written: `root`, `line_2`,
  `line_3` and so on.
- **The editor read that order as meaning.** The inspector numbered lines by the dictionary's order
  (`order = list(nodes)`). `project_ops.add_line` took the last line as `next(reversed(nodes))`, and `remove_line` took
  `next(iter(nodes))` for a new start.
- **The runtime is unaffected.** It follows ids (`start`, the openings, `next`, the choices' `next`), so the
  conversation itself never changed.

## The fix (no format change, no new ids)

Studio already gives lines ids in the order they are written: `root` first (`set_dialogue_text`), then `line_2`,
`line_3` and so on (`_new_line_id`). So the written order can be recovered from the ids alone, whatever order the file
keeps them in.

- **`project_ops.line_order(nodes)`** returns `root`, then `line_N` by number (so `line_10` comes after `line_9`), then
  any other names alphabetically. The name itself breaks any tie (`line_02` before `line_2`). The result never depends
  on the file's order, and is the same before and after saving.
- **`project_ops._new_line_id`** numbers a new line after every existing `line_N` (added after review). Before, it
  started from the line count, so after middle lines were deleted it could reuse a freed lower number and the new line
  would be numbered in the middle (see "Review round").
- **`studio_inspector` numbers lines with `line_order`.**
- **`project_ops.add_line`** treats the last line as numbered as "the end".
- **`project_ops.remove_line`**: when the start line is deleted and nothing follows it, the line now numbered 1 becomes
  the start.

Unchanged:

- the file format;
- existing ids (new ones are numbered as before, except that a freed number isn't reused);
- every link;
- the runtime (`Dialogue`);
- `conversation()`'s and `_graph`'s start fallback for old conversations saved without a `start`. These still take the
  file's first line, so the editor and the game agree on where such a conversation begins.

With the fix, inserting a line gives it the next number, and no other line moves. Deleting a line moves the lines
after it up by one, because they are renumbered. Both are display only.

## Evidence after the fix (same tool, same steps)

- **Reopening shows the same numbers** as written, along with the same "Otherwise line" (1), the same opening (11) and
  "+ Next line (after 11)". A line added at the end follows "Back already?" (line 11).
- **Edits after reopening work:** changing a line's words, inserting a line after line 3, changing choice b's
  destination, and deleting line 7. Undo restores the deleted line and redo removes it again. The numbers stay as the
  creator expects (the inserted line is 11, and the opening now reads 10 after the deletion).
- **Another room and back, then a save and reopen:** shown and stored are identical. Two more saves and reopens without
  edits write byte-identical files and show the same list.
- **Game and exported build** (`mesh export build`, its own engine copy): the conversation plays as edited. The choice
  sets `task_accepted`, the inserted line plays after "Bless you", the deleted line doesn't play, and talking again
  opens with "Back already?".

The reports are in `watchfire_r4_evidence/` (`before_fc220b4_report.json`, `after_fix_report.json`). Each holds the
inspector's list as shown and the conversation as stored, at every step.

## Tests

- **`tests/test_dialogue_line_order.py`** (fast, 7 tests). It uses a real save round trip (`dumps_stable`, then read
  back).
  - the written order;
  - saving reorders the file but not the numbers, words or links, and saving again changes nothing;
  - a line added at the end after reopening follows the last line;
  - deleting the first line makes the first numbered line the opening.
  - (after review) a line added after deleting middle lines is numbered last, the others keep their numbers, and the
    next one follows;
  - (after review) new ids stay sequential for new conversations and for an old one-list `dialogue_lines` conversation
    (`line_1` …);
  - (after review) names with the same number (`line_2`, `line_02`) are ordered by name, whatever the file order.

  Against the `fc220b4` engine files, the first 4 fail. Against the first-reviewed `f6dbf03`, the two edge cases fail
  and the compatibility test passes.
- **`tests/test_dialogue_reopen_gpu.py`** (GL-gated, 5 tests) runs the real-window scenario above. Against the
  `fc220b4` engine files, 4 fail. The fifth, the game and exported-build playthrough, passes both before and after,
  because the runtime was never affected.

The outputs on the base are in `before_tests_on_fc220b4_engine.txt`.

## Review round (`f6dbf03`: functional pass, merge hold)

The review found an edge case, reproduced with real `project_ops` calls and save round trips
(`watchfire_r4_evidence/review_deleted_lines_reuse.txt`):

- An 11-line conversation had lines 3 to 9 deleted, leaving `root`, `line_2`, `line_10` and `line_11`.
- `add_line` then made **`line_5`**, because the next id started from the line count. It was correctly linked after
  `line_11`, but numbered **3 of 5**.
- `line_10` and `line_11` moved from 3 and 4 down to 4 and 5, and the line numbered last was still `line_11`, which
  already has a next line. So "+ Next line" would have disappeared again.
- `line_order` of `line_2` and `line_02` followed the file's order.

With the correction, the new line is `line_12`, numbered 5 of 5. The other lines keep their numbers, the next new line
is `line_13`, and ties sort by name.

## Compatibility and limits

- **Saved files:** no change to the file format or ids. Existing projects open with their lines numbered `root`,
  `line_2`, `line_3` …: the order they were written in Studio.
- **Conversations with other line names** (hand-written or by an AI tool, e.g. `greet`, `farewell`) are numbered after
  Studio's own lines, alphabetically. Before, they were numbered in file order, which changed when Studio saved them.
  They are now numbered the same way before and after saving. If such a conversation has no `root`, its start line is
  not necessarily number 1.
- **An inserted line is numbered by when it was written** (the end of the list), not by where it sits in the flow. The
  list shows each line's flow (`> 11`) as before.
- **Not changed:**
  - the runtime and the game's start fallback;
  - AI authoring: `ai_ops.edit_dialogue` patches the conversation's data directly, never used `add_line`, and doesn't
    depend on node order.
