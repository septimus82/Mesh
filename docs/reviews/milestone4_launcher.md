# Milestone 4 — project launcher and templates: test results and notes

Branch `redesign/visual-editor`. Summary and status: [`MESH_REBUILD.md`](../../MESH_REBUILD.md).

## Graphical acceptance test

`py -3.13 tooling/acceptance_launcher.py --out DIR --old <older project> ...` (Windows).

How it works:
- It starts Mesh the way a double-click does: `Mesh Engine.bat`, which runs `pyw` with no console.
- It finds the launcher and Mesh Studio windows by title.
- It drives them with OS-level mouse and keyboard input, including the Windows folder picker. The test types the path and presses the dialog's own OK button, found by its standard control ID, so it works in any Windows language.
- The windows' opt-in layout dumps are read only to locate things and check state.
- Recent projects, logs and the default games folder go to temporary folders, so a run never touches your real profile or Documents.
- Older projects are opened from copies, and each original's files are fingerprinted before and after.

**Final run: 20/20 passed.** Report: [`milestone4_screens/report.json`](milestone4_screens/report.json).

| # | Step | What was checked | Result |
|---|---|---|---|
| 1 | Launch Mesh | `Mesh Engine.bat` | Pass |
| 2 | Launcher appears | Window "Mesh Engine"; New Project and Open Project...; no recent projects for a new user | Pass |
| 3 | New Project | Both templates shown as picture cards | Pass |
| 4 | Pick Top-down Adventure | Clicked the Blank card, then the Adventure card | Pass |
| 5 | Name and destination | Name "Village Quest". **Browse...** opens the Windows folder picker, and the test chooses `…\Mina spel – Åäö` (spaces, a dash, non-ASCII letters, outside the engine folder). | Pass |
| 6 | Create & Open | Mesh Studio opens on the new game; the launcher closes itself | Pass |
| 7 | Example content | Rooms Village and House; Player, Guide, Door to House; a 24×16 map with 55 wall tiles | Pass |
| 8 | Change map and dialogue | Painted a row of flowers; gave the Guide a new line | Pass |
| 9 | Play and talk | F4, walk to the Guide, E: the dialogue box shows the new line, spoken by "Guide" | Pass |
| 10 | Save and stop | Back to editing, Ctrl+S, nothing unsaved | Pass |
| 11 | Close the application | The Studio's own X button; no Mesh window left | Pass |
| 12 | Launch again | `Mesh Engine.bat` | Pass |
| 13 | Open from Recent projects | "Village Quest" listed with its path; clicked it | Pass |
| 14 | Changes persisted | Tiles identical cell by cell; the Guide's new line | Pass |
| 15 | Create a Blank Project | "Empty Canvas", in a typed folder | Pass |
| 16 | No monster or demo content | 12 files, none to do with monsters, battles or quests. Only the player; an empty grass map; one room. | Pass |
| 17 | Add a room and an object; play | "+ New room" "Cave", placed a Person, saved, F4: the player walks | Pass |
| 18 | Older projects | A Milestone 3 project (two tilesets and an above-player layer) and a copy of your hand-test project `mygame` (Milestone 2) open in the Studio. The originals' files are unchanged. | Pass |
| 19 | Bad and missing paths | Covered below; every case gives a clear message and changes nothing on disk. | Pass |
| 20 | Engine folder unchanged | `git status` identical before and after; recent projects saved in the user folder | Pass |

**What step 19 covered:**
- **A folder without `config.json`:** "There's no Mesh project in … Choose the folder that contains config.json."
- **A moved project:** it stays in Recent projects, shown red as "Missing". Clicking it explains; **Remove** takes it off the list and leaves the folder alone.
- **An existing game's name:** "There is already a Mesh project at …", and Create & Open refuses.
- **A `?` in the name:** a warning that names can't contain those characters.
- **The engine folder as the destination:** "Choose a folder outside the Mesh engine folder."

**Regression:** the three earlier real-window tests pass on this code:
- Milestone 1 (`acceptance_first_workflow.py`): 15/15.
- Milestone 2 (`acceptance_map_building.py`): 23/23.
- Milestone 3 (`acceptance_map_tools.py`): 15/15.

**Not tested graphically:** an actual double-click in Explorer. The test runs the same `.bat` through `cmd`, as Explorer does, but no click on the file itself.

Screenshots from the final run:
- [Launcher](milestone4_screens/02_launcher_appears.png)
- [Choosing a template](milestone4_screens/04_choose_top_down_adventure.png)
- [The new adventure in the Studio](milestone4_screens/07_example_content.png)
- [Talking to the Guide](milestone4_screens/09_talking_to_the_guide.png)
- [Recent projects](milestone4_screens/12_launch_again.png)
- [Blank project](milestone4_screens/16_blank_has_no_monster_or_demo_content.png)
- [A Milestone 3 project opened](milestone4_screens/18_0_older_project_village.png)
- [A moved project](milestone4_screens/19a_moved_project.png)
- [Refusing to overwrite](milestone4_screens/19b_refused_existing_project.png)

## Priority 0: the tenth failure, and keeping games out of the engine

- **The cause.** The ruff gate ran `ruff check .` on the whole checkout. A game made inside the engine folder (`mygame/`) was therefore linted as engine code, and the gate failed on it.
- **The fix, at three levels:**
  1. **The gate.** It skips *untracked folders that are Mesh projects* (their own `config.json`). Tracked files and new engine files are still linted. `mygame/` is left exactly where it is.
  2. **New games.** The launcher refuses destinations inside the engine folder and defaults to `Documents\Mesh Projects`. `mesh new` run inside the engine folder uses that folder too, and an explicit `--dest` inside the engine is refused.
  3. **The generated code itself.** `main.py` lost a dead pyglet 1.5 patch and now sets the DPI mode before loading the engine. New games of every template pass ruff with the engine's settings, with no suppressions (tested).
- **The recent-projects list** no longer writes into the engine folder; it lives in `%APPDATA%\Mesh`. The tests now always use temporary recent-projects, user and default-games folders, so they can never touch the real ones.
- **Outcome:** the ruff-gate contract test passes with `mygame/` still present. The full suite is back to exactly the 9 baseline failures.

## The "ignored start-up clicks": found

The launcher and the Studio log their first input events: presses, mouse moves and focus changes, with clock times. Lined up with the GUI driver's own timestamped log, they showed two problems, both in the test tooling, not in Mesh.
1. **Leftover windows.** Two launcher windows left open by earlier failed probes had the same title as the new one. The driver attached to a stale window and clicked one it wasn't watching, which looked exactly like lost clicks. The driver now refuses to attach while two windows share a title.
2. **The foreground workaround.** When Windows wouldn't let the driver bring a window to the front, it minimised and restored the window. In the logs that left the window deactivated straight after activation. The driver now brings windows forward the way a person does, with a click on the window's title bar. This was tested with another window deliberately taking the foreground.

After both fixes:
- 8 of 8 launch-and-click trials registered the first click, and closing by the X button worked every time.
- No click has been lost in any GUI run since.

Whether the Milestone 1–3 drops had the same cause can no longer be shown, but they happened under the same driver code.

## Implementation notes

- **Launcher** (`engine/launcher.py`):
  - Built with `arcade.gui`, like the Studio. Its look and widgets come from the new shared `engine/studio_ui.py`: colours, buttons, the text field with clipboard keys, the OS file and folder pickers.
  - It adds no project format and no registry. Recent projects use `engine/projects.py`, games are made by `engine.project_scaffold.create_project`, and templates come from `engine.project_templates`.
  - Mesh Studio starts as its own process (`mesh_cli edit <folder>`) with the engine on `PYTHONPATH`, logging to `%APPDATA%\Mesh\logs\studio.log`. If the Studio quits before showing a window, the launcher shows that log's path.
  - Every check runs before anything touches the disk, and nothing is ever overwritten: an existing folder or project is refused, never reused. Enter in a field only confirms it; only **Create & Open** creates.
- **Entry point:** `Mesh Engine.bat`.
  - It sets `PYTHONPATH` to its own folder, checks for Python 3.13 with arcade, and starts the launcher through `pyw`, so there is no console window.
  - If Python is missing, it says what to install.
- **Templates:**
  - Each template is one entry (`Template`: id, title, description, `launcher`, `preview`) plus one builder function, so a new genre is one entry and one function.
  - **Blank** is a 24×16 grass map, the player, and the "Person" object type.
  - **Top-down Adventure** is a village and a house with two-way doors, a Guide who explains saving, and a Grandma indoors. It uses the starter tileset and is built entirely with `project_ops`, the same validated operations the Studio uses.
  - Save and load are the engine's own pause menu (Esc).
  - The launcher's pictures are drawn from what each template actually builds (`tooling/make_template_previews.py`).
- **Studio:** closing the window with unsaved changes now warns once ("Save with Ctrl+S, or close again to leave without saving") instead of discarding them.

## Not done in this milestone

These were kept out of scope deliberately:
- An installer or packaged app.
- A launcher screen that returns after the Studio closes.
- Project rename, move or delete from the launcher.
- More templates.

The in-game main-menu project browser still exists for the legacy flow; it uses the same registry and templates (see `MESH_SALVAGE.md`).
